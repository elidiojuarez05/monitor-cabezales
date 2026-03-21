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

# =========================================================
# 1. CONFIGURACIÓN DE PÁGINA (DEBE SER EL PRIMER COMANDO)
# =========================================================
st.set_page_config(page_title="Print Head Monitor", layout="wide", initial_sidebar_state="expanded")

# =========================================================
# 2. CONEXIÓN A BASE DE DATOS (POSTGRESQL / SUPABASE)
# =========================================================
class PostgresDB:
    def __init__(self):
        self.conn = st.connection("postgresql", type="sql", pool_pre_ping=True)

    def safe_read(self, table_name):
        try:
            query = f'SELECT * FROM "{table_name}"'
            return self.conn.query(query, ttl=0)
        except Exception as e:
            return pd.DataFrame()

    def execute_query(self, query, params=None):
        try:
            with self.conn.session as s:
                s.execute(query, params)
                s.commit()
            return True
        except Exception as e:
            st.error(f"Error DB: {e}")
            return False

db = PostgresDB()

def hash_password(password):
    return hashlib.sha256(password.strip().encode('utf-8')).hexdigest().lower()

# =========================================================
# 3. CONFIGURACIÓN DE RUTAS Y ASSETS
# =========================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    backend_dir = os.path.join(sys._MEIPASS, "backend")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(BASE_DIR)
    backend_dir = os.path.join(project_root, "backend")

if backend_dir not in sys.path: sys.path.insert(0, backend_dir)

# Importar lógica de procesamiento y configuraciones
try:
    import image_processor
    from config import MACHINE_CONFIGS
except ImportError as e:
    st.error(f"Error: No se encontró el backend o config. {e}")
    st.stop()

# =========================================================
# 4. ESTILOS Y ASSETS (LOGO)
# =========================================================
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #e0e6ed; }
    [data-testid="stMetricValue"] { color: #00ff41; font-family: 'Courier New'; font-weight: bold; }
    .stButton>button { background-color: #1e3a8a; color: white; border-radius: 4px; border: 1px solid #3b82f6; }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 5. INITIALIZACIÓN DE ESTADO
# =========================================================
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'user_role' not in st.session_state: st.session_state.user_role = None
if 'username' not in st.session_state: st.session_state.username = None
if 'indice_carrusel' not in st.session_state: st.session_state.indice_carrusel = 0
if 'estados_maquinas' not in st.session_state: st.session_state.estados_maquinas = {name: "Operativa" for name in MACHINE_CONFIGS.keys()}
if 'recortes' not in st.session_state: st.session_state.recortes = {}

# =========================================================
# 6. LÓGICA DE ACCESO (LOGIN)
# =========================================================
if not st.session_state.authenticated:
    st.markdown("<style>section[data-testid='stSidebar'] {display: none;}</style>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br><h2 style='text-align: center;'>🔐 Acceso al Sistema</h2>", unsafe_allow_html=True)
        with st.container(border=True):
            u_in = st.text_input("ID Operador")
            p_in = st.text_input("PIN", type="password")
            if st.button("🚀 Entrar", use_container_width=True):
                df_u = db.safe_read("usuarios")
                if not df_u.empty:
                    df_u.columns = [str(c).lower().strip() for c in df_u.columns]
                    u_clean = u_in.strip().lower()
                    match = df_u[df_u['usuario'].astype(str).str.strip().str.lower() == u_clean]
                    if not match.empty:
                        if hash_password(p_in) == str(match.iloc[0]['contrasena']).strip().lower():
                            st.session_state.authenticated = True
                            st.session_state.username = u_clean
                            st.session_state.user_role = str(match.iloc[0].get('rol', 'operador')).lower()
                            st.rerun()
                        else: st.error("PIN incorrecto.")
                    else: st.error("Usuario no existe.")
    st.stop()

# =========================================================
# 7. SIDEBAR (CÁMARA, ZOOM Y CONFIGURACIÓN)
# =========================================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2972/2972199.png", width=80) # Logo Genérico
    st.markdown(f"### Operador: {st.session_state.username.upper()}")
    st.caption(f"🎖️ Rol: {st.session_state.user_role.upper()}")
    
    st.divider()
    run_camera = st.toggle("📷 Cámara de Inspección")
    if run_camera:
        m_target = st.selectbox("Asignar Test a:", list(MACHINE_CONFIGS.keys()))
        sensibilidad = st.slider("Sensibilidad Nozzle", 0.01, 0.20, 0.05)
        zoom_level = st.slider("Zoom Digital (Bordes)", 0, 100, 0)
        foto = st.camera_input("Capturar Test")
        if foto:
            # Lógica de procesamiento de imagen (Zoom y detección de bordes)
            st.info("Procesando imagen capturada...")
            # Aquí se llamaría a image_processor.process_test_image_v2(...)

    st.divider()
    st.subheader("🛠️ Estatus Manual")
    m_status = st.selectbox("Máquina:", list(MACHINE_CONFIGS.keys()))
    nuevo_est = st.selectbox("Estado:", ["Operativa", "Mantenimiento", "Falla Total", "Falla de Slots", "Falla de Tarjetas"])
    if st.button("Actualizar Estatus"):
        st.session_state.estados_maquinas[m_status] = nuevo_est
        st.toast(f"{m_status} actualizada.")

    st.divider()
    fecha_consulta = st.date_input("📅 Filtrar por fecha:", datetime.now().date())
    
    if st.button("🚪 Salir"):
        st.session_state.authenticated = False
        st.rerun()

# =========================================================
# 8. MONITOR PRINCIPAL (TABS)
# =========================================================
st.markdown(f"## 📡 Monitor Industrial - {datetime.now().strftime('%d/%m/%Y')}")

tab_car, tab_gral, tab_manual, tab_admin = st.tabs(["🔄 Carrusel (10s)", "🏭 Vista General", "✂️ Procesamiento Manual", "⚙️ Gestión Admin"])

lista_maquinas = list(MACHINE_CONFIGS.keys())

# --- FUNCION PARA RENDERIZAR MAQUINAS ---
def render_maquina(name):
    est = st.session_state.estados_maquinas.get(name, "Operativa")
    color = "#10b981" if est == "Operativa" else "#ef4444"
    with st.container(border=True):
        st.markdown(f"### {name}")
        st.write(f"Estado: **{est}**")
        st.metric("Vida Útil", "94.2%", "-1.5%")
        # Simulación de gráfica interna
        st.line_chart(np.random.randn(10), height=100)
        st.caption(f"Último test: {datetime.now().strftime('%H:%M')}")

# --- TAB CARRUSEL (2 EN 2) ---
with tab_car:
    idx = st.session_state.indice_carrusel
    c1, c2 = st.columns(2)
    with c1: render_maquina(lista_maquinas[idx])
    with c2: render_maquina(lista_maquinas[(idx + 1) % len(lista_maquinas)])

# --- TAB VISTA GENERAL (LAS 11) ---
with tab_gral:
    for i in range(0, len(lista_maquinas), 3):
        cols = st.columns(3)
        for j, m_name in enumerate(lista_maquinas[i:i+3]):
            with cols[j]: render_maquina(m_name)

# --- TAB PROCESAMIENTO MANUAL (CROPPER) ---
with tab_manual:
    up = st.file_uploader("Subir imagen de test", type=['jpg','png'])
    if up:
        img = Image.open(up)
        cropped = st_cropper(img, realtime_update=True, box_color='#00ff41')
        if st.button("Procesar Recorte"):
            st.success("Analizando inyectores en el área seleccionada...")

# --- TAB ADMINISTRACIÓN (USUARIOS Y REPORTES) ---
with tab_admin:
    if st.session_state.user_role != "admin":
        st.warning("⚠️ Acceso solo para Administradores.")
    else:
        col_u, col_r = st.columns(2)
        with col_u:
            st.subheader("Usuarios")
            with st.expander("➕ Nuevo Usuario"):
                nu = st.text_input("Usuario")
                np_ = st.text_input("PIN", type="password")
                nr = st.selectbox("Rol", ["operador", "admin"])
                if st.button("Guardar"):
                    db.execute_query("INSERT INTO usuarios (usuario, contrasena, rol) VALUES (:u, :h, :r)", 
                                    {"u":nu.lower(), "h":hash_password(np_), "r":nr})
                    st.rerun()
            
            df_view = db.safe_read("usuarios")
            st.dataframe(df_view[['usuario','rol']], use_container_width=True)
            
        with col_r:
            st.subheader("Reportes Semanales")
            if st.button("📉 Generar Status PDF"):
                st.info("Generando reporte de las 11 máquinas...")
                # Lógica de PDF aquí

# =========================================================
# 9. MOTOR DE REFRESCO (10 SEG PARA CARRUSEL)
# =========================================================
if st.session_state.authenticated and not run_camera and not up:
    time.sleep(10)
    st.session_state.indice_carrusel = (st.session_state.indice_carrusel + 2) % len(lista_maquinas)
    st.rerun()
