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

# =========================================================
# 1. MANEJO DE RUTAS (REPOSITORIO / EJECUTABLE)
# =========================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    backend_dir = os.path.join(sys._MEIPASS, "backend")
    assets_dir = os.path.join(sys._MEIPASS, "assets")
else:
    # Ruta estándar para GitHub/Local
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    project_root = BASE_DIR # Ajustar si el dashboard está en una subcarpeta
    backend_dir = os.path.join(project_root, "backend")
    assets_dir = os.path.join(project_root, "assets")

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# =========================================================
# 2. IMPORTACIÓN DE MÓDULOS DEL BACKEND
# =========================================================
try:
    import image_processor
    import crud
    from config import MACHINE_CONFIGS
except ImportError as e:
    st.error(f"Faltan módulos en /backend: {e}")
    st.stop()

# =========================================================
# 3. CONFIGURACIÓN DE PÁGINA Y TEMA INDUSTRIAL
# =========================================================
st.set_page_config(page_title="Print Head Monitor", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #e0e6ed; }
    div[data-testid="stMetricValue"] { color: #00ff41; font-family: 'Courier New', Courier, monospace; font-weight: bold; }
    .stButton>button {
        background-color: #1e3a8a; color: white; border-radius: 4px; border: 1px solid #3b82f6; font-weight: bold;
    }
    div[data-testid="stContainer"] { border-color: #334155 !important; background-color: #1e293b; border-radius: 8px; }
    section[data-testid="stSidebar"] { background-color: #111827; }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 4. FUNCIONES DE APOYO Y DB (POSTGRESQL)
# =========================================================
def get_db():
    """Retorna la sesión de base de datos PostgreSQL de Supabase."""
    return st.connection("postgresql", type="sql", pool_pre_ping=True).session

def hash_pw(password):
    return hashlib.sha256(str(password).strip().encode('utf-8')).hexdigest().lower()

# =========================================================
# 5. INICIALIZACIÓN DE SESIÓN
# =========================================================
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'user_role' not in st.session_state: st.session_state.user_role = None
if 'username' not in st.session_state: st.session_state.username = None
if 'indice_carrusel' not in st.session_state: st.session_state.indice_carrusel = 0
if 'estados_maquinas' not in st.session_state: 
    st.session_state.estados_maquinas = {m: "Operativa" for m in MACHINE_CONFIGS.keys()}

# =========================================================
# 6. PANTALLA DE LOGIN
# =========================================================
if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br><h2 style='text-align: center;'>🏭 Control de Inyectores</h2>", unsafe_allow_html=True)
        with st.container(border=True):
            u_input = st.text_input("Usuario")
            p_input = st.text_input("Contraseña", type="password")
            if st.button("Ingresar al Sistema", use_container_width=True):
                with get_db() as db:
                    user = crud.get_user_by_username(db, u_input.lower())
                    if user and hash_pw(p_input) == user.password:
                        st.session_state.authenticated = True
                        st.session_state.username = user.username
                        st.session_state.user_role = user.role
                        st.rerun()
                    else:
                        st.error("Credenciales no válidas")
    st.stop()

# =========================================================
# 7. DASHBOARD PRINCIPAL (SIDEBAR Y LOGO)
# =========================================================
with st.sidebar:
    # --- INTEGRACIÓN DEL LOGO ---
    logo_file = os.path.join(assets_dir, "logo.png")
    if os.path.exists(logo_file):
        st.image(logo_file, use_container_width=True)
    else:
        st.subheader("PRINT MONITOR")

    st.markdown(f"👤 **{st.session_state.username}** | `{st.session_state.user_role}`")
    st.divider()

    selected_m = st.selectbox("Máquina Estación", list(MACHINE_CONFIGS.keys()))
    sensibilidad = st.slider("Sensibilidad Nozzle", 0.01, 0.20, 0.05)
    run_camera = st.toggle("📷 Cámara de Inspección")
    
    st.divider()
    if st.button("Cerrar Sesión", type="primary"):
        st.session_state.authenticated = False
        st.rerun()

# --- ÁREA DE TRABAJO ---
st.title("🖨️ Monitor Industrial en Tiempo Real")

if run_camera:
    foto = st.camera_input("Capturar Test de Inyectores")
    if foto:
        with st.spinner("Procesando telemetría..."):
            # Guardar temporal
            temp_img = "temp_scan.jpg"
            with open(temp_img, "wb") as f: f.write(foto.getbuffer())
            
            # Procesar con backend
            config = MACHINE_CONFIGS[selected_m]
            mapa, img_res, msg = image_processor.process_test_image_v2(temp_img, config, sensibilidad)
            
            if mapa is not None:
                salud = (np.sum(mapa) / mapa.size) * 100
                fallas = int(np.count_nonzero(mapa == 0))
                
                with get_db() as db:
                    crud.save_test_result(db, selected_m, salud, fallas, str(mapa.tolist()), "cloud_storage_path")
                
                st.success(f"Análisis completado: {salud:.2f}% Salud")
                st.image(img_res)
            else:
                st.error(msg)

# =========================================================
# 8. VISTA GLOBAL Y CARRUSEL
# =========================================================
tab_status, tab_history, tab_admin = st.tabs(["📊 Planta", "📈 Historial", "⚙️ Gestión"])

with tab_status:
    lista_m = list(MACHINE_CONFIGS.keys())
    idx = st.session_state.indice_carrusel
    
    # Mostrar de 2 en 2 (Carrusel)
    cols = st.columns(2)
    for i, m_name in enumerate(lista_m[idx : idx + 2]):
        with cols[i]:
            with st.container(border=True):
                with get_db() as db:
                    ultimo = crud.get_test_by_date(db, m_name, datetime.now().date())
                
                st.subheader(f"Machine: {m_name}")
                if ultimo:
                    st.metric("Salud", f"{ultimo.health_score:.1f}%", f"-{ultimo.missing_nodes} Nodos")
                else:
                    st.info("Sin registros el día de hoy")

with tab_admin:
    if st.session_state.user_role == "admin":
        st.subheader("Control de Usuarios")
        with get_db() as db:
            users = crud.get_all_users(db)
            if users:
                df_u = pd.DataFrame([{"ID": u.id, "User": u.username, "Rol": u.role} for u in users])
                st.dataframe(df_u, use_container_width=True)
    else:
        st.warning("Acceso restringido.")

# =========================================================
# 9. MOTOR DE REFRESCO AUTOMÁTICO
# =========================================================
if not run_camera:
    time.sleep(15)
    st.session_state.indice_carrusel = (st.session_state.indice_carrusel + 2) % len(lista_m)
    st.rerun()
