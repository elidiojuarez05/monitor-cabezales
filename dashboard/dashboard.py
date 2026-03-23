import sys
import os
import hashlib
import numpy as np
import cv2
import pandas as pd
import streamlit as st
from streamlit_cropper import st_cropper
from PIL import Image
from datetime import datetime, timedelta
import time
import base64
from sqlalchemy import text

# =========================================================
# 1. CONFIGURACIÓN DE RUTAS (BACKEND Y ASSETS)
# =========================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    # En ejecutable, los paths cambian según donde PyInstaller extraiga los archivos
    backend_dir = os.path.join(sys._MEIPASS, "backend")
    assets_dir = os.path.join(sys._MEIPASS, "assets")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    # Asumiendo estructura: proyecto/dashboard/dashboard.py y proyecto/backend/
    project_root = os.path.dirname(BASE_DIR)
    backend_dir = os.path.join(project_root, "backend")
    assets_dir = os.path.join(project_root, "assets")

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Directorios de datos locales para caché de imágenes
EVIDENCIAS_PATH = os.path.join(BASE_DIR, "evidencias")
for path in [EVIDENCIAS_PATH]:
    if not os.path.exists(path): os.makedirs(path)

# =========================================================
# 2. IMPORTS DE MÓDULOS DE BACKEND (Carpeta backend/)
# =========================================================
try:
    import image_processor
    import crud
    from config import MACHINE_CONFIGS
except ImportError as e:
    st.error(f"Error al importar módulos del backend: {e}")
    st.stop()

# =========================================================
# 3. CONFIGURACIÓN DE PÁGINA Y DISEÑO
# =========================================================
st.set_page_config(page_title="Print Head Monitor", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #e0e6ed; }
    div[data-testid="stMetricValue"] { color: #00ff41; font-family: 'Courier New', Courier, monospace; font-weight: bold; }
    .stButton>button {
        background-color: #1e3a8a; color: white; border-radius: 4px; border: 1px solid #3b82f6; font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton>button:hover { background-color: #3b82f6; border: 1px solid #60a5fa; box-shadow: 0 0 10px rgba(59, 130, 246, 0.5); }
    div[data-testid="stContainer"] { border-color: #334155 !important; background-color: #1e293b; border-radius: 8px; }
    section[data-testid="stSidebar"] { background-color: #111827; border-right: 1px solid #334155; }
    h1, h2, h3 { color: #f8fafc; font-family: 'Arial', sans-serif; }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 4. CONEXIÓN A POSTGRESQL (SUPABASE)
# =========================================================
# Usamos el conector oficial de Streamlit para SQL (Postgres)
def get_db_session():
    # Requiere que configures [connections.postgresql] en .streamlit/secrets.toml
    return st.connection("postgresql", type="sql", pool_pre_ping=True).session

def hash_pw(password):
    return hashlib.sha256(str(password).strip().encode('utf-8')).hexdigest().lower()

# =========================================================
# 5. LÓGICA DE INTERFAZ Y COMPONENTES
# =========================================================
def render_machine_card(m_name, fecha_consulta):
    with get_db_session() as db:
        last_test = crud.get_test_by_date(db, m_name, fecha_consulta)
        
    estado_actual = st.session_state.estados_maquinas.get(m_name, "Operativa")
    
    with st.container(border=True):
        st.markdown(f"### {m_name}")
        if last_test:
            st.metric("Salud", f"{last_test.health_score:.1f}%", f"-{last_test.missing_nodes} Nodos", delta_color="inverse")
            st.caption(f"Última lectura: {last_test.timestamp.strftime('%H:%M')}")
        else:
            st.warning("Sin datos hoy")
            st.caption(f"Estado: {estado_actual}")

# =========================================================
# 6. INICIALIZACIÓN DE ESTADOS
# =========================================================
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'user_role' not in st.session_state: st.session_state.user_role = None
if 'username' not in st.session_state: st.session_state.username = None
if 'estados_maquinas' not in st.session_state: 
    st.session_state.estados_maquinas = {name: "Operativa" for name in MACHINE_CONFIGS.keys()}

# =========================================================
# 7. LOGIN
# =========================================================
if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("<br><br><h2 style='text-align: center;'>🏭 Acceso a Planta</h2>", unsafe_allow_html=True)
        with st.container(border=True):
            u = st.text_input("Usuario")
            p = st.text_input("Password", type="password")
            if st.button("Ingresar", use_container_width=True):
                with get_db_session() as db:
                    user = crud.get_user_by_username(db, u.lower())
                    if user and hash_pw(p) == user.password:
                        st.session_state.authenticated = True
                        st.session_state.username = user.username
                        st.session_state.user_role = user.role
                        st.rerun()
                    else:
                        st.error("Credenciales incorrectas")
    st.stop()

# =========================================================
# 8. DASHBOARD PRINCIPAL
# =========================================================

# --- SIDEBAR CON LOGO ---
with st.sidebar:
    # Integración del Logo desde la carpeta assets
    logo_path = os.path.join(assets_dir, "logo_empresa.png")
    if os.path.exists(logo_path):
        st.image(logo_path, use_container_width=True)
    else:
        st.markdown("### [LOGO EMPRESA]") # Placeholder si no existe el archivo
        
    st.markdown(f"**Usuario:** {st.session_state.username}")
    st.divider()
    
    machine_selected = st.selectbox("Seleccionar Máquina", list(MACHINE_CONFIGS.keys()))
    sensibilidad = st.slider("Sensibilidad de Nozzles", 0.01, 0.20, 0.05)
    run_camera = st.toggle("Activar Cámara de Inspección")
    
    if st.button("Cerrar Sesión"):
        st.session_state.authenticated = False
        st.rerun()

# --- HEADER ---
st.title("🖨️ Print Head Monitor - Industrial Dashboard")

# --- PROCESAMIENTO DE CÁMARA ---
if run_camera:
    foto = st.camera_input("Capturar Test")
    if foto:
        with st.spinner("Analizando inyectores..."):
            # Guardar temporalmente para procesar
            temp_path = "temp_capture.jpg"
            with open(temp_path, "wb") as f:
                f.write(foto.getbuffer())
            
            config = MACHINE_CONFIGS[machine_selected]
            mapa, img_res, msg = image_processor.process_test_image_v2(temp_path, config, sensibilidad)
            
            if mapa is not None:
                salud = (np.sum(mapa) / mapa.size) * 100
                fallas = int(np.count_nonzero(mapa == 0))
                
                # Guardar en Postgres vía CRUD
                with get_db_session() as db:
                    crud.save_test_result(db, machine_selected, salud, fallas, str(mapa.tolist()), "ruta_placeholder")
                
                st.success(f"Test completado: {salud:.2f}% de salud.")
                st.image(img_res, caption="Resultado del análisis")
            else:
                st.error(f"Error en análisis: {msg}")

# --- TABS DE VISUALIZACIÓN ---
tab_global, tab_admin = st.tabs(["📊 Vista de Planta", "⚙️ Administración"])

with tab_global:
    # Grid de máquinas
    m_list = list(MACHINE_CONFIGS.keys())
    for i in range(0, len(m_list), 3):
        cols = st.columns(3)
        for j, m_name in enumerate(m_list[i:i+3]):
            with cols[j]:
                render_machine_card(m_name, datetime.now().date())

with tab_admin:
    if st.session_state.user_role != "admin":
        st.warning("Acceso restringido a administradores.")
    else:
        st.subheader("Gestión de Usuarios")
        # Aquí puedes llamar a crud.get_all_users(db) y mostrar un dataframe
        with get_db_session() as db:
            usuarios = crud.get_all_users(db)
            if usuarios:
                df_u = pd.DataFrame([{"ID": u.id, "User": u.username, "Rol": u.role} for u in usuarios])
                st.table(df_u)
