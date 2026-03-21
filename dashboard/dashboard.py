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
# 1. CONFIGURACIÓN DE PÁGINA (VA PRIMERO)
# =========================================================
st.set_page_config(page_title="Print Head Monitor", layout="wide", initial_sidebar_state="expanded")

# --- Estilo Industrial ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #e0e6ed; }
    div[data-testid="stMetricValue"] { color: #00ff41; font-family: 'Courier New', Courier, monospace; font-weight: bold; }
    .stButton>button { background-color: #1e3a8a; color: white; border-radius: 4px; border: 1px solid #3b82f6; font-weight: bold; }
    .stButton>button:hover { background-color: #3b82f6; box-shadow: 0 0 10px rgba(59, 130, 246, 0.5); }
    section[data-testid="stSidebar"] { background-color: #111827; border-right: 1px solid #334155; }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. CONEXIÓN A BASE DE DATOS Y UTILIDADES
# =========================================================
class PostgresDB:
    def __init__(self):
        # Conexión nativa de Streamlit a PostgreSQL
        self.conn = st.connection("postgresql", type="sql", pool_pre_ping=True)

    def safe_read(self, table_name):
        try:
            query = f'SELECT * FROM "{table_name}"'
            return self.conn.query(query, ttl=0)
        except Exception as e:
            st.error(f"Error al leer tabla {table_name}: {e}")
            return pd.DataFrame()

    def execute_query(self, query, params=None):
        try:
            with self.conn.session as s:
                s.execute(query, params)
                s.commit()
            return True
        except Exception as e:
            st.error(f"Error de ejecución: {e}")
            return False

db = PostgresDB()

def hash_password(password):
    """Genera el hash SHA-256 consistente para todas las funciones."""
    return hashlib.sha256(password.strip().encode('utf-8')).hexdigest().lower()

# =========================================================
# 3. CONFIGURACIÓN DE RUTAS Y ARCHIVOS PROPIOS
# =========================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    backend_dir = os.path.join(sys._MEIPASS, "backend")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(BASE_DIR)
    backend_dir = os.path.join(project_root, "backend")

if backend_dir not in sys.path: sys.path.insert(0, backend_dir)

try:
    import image_processor
    from config import MACHINE_CONFIGS
except ImportError as e:
    st.error(f"Faltan módulos críticos: {e}")
    st.stop()

# =========================================================
# 4. INICIALIZACIÓN DE SESSION STATE
# =========================================================
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'user_role' not in st.session_state: st.session_state.user_role = None
if 'username' not in st.session_state: st.session_state.username = None
if 'indice_carrusel' not in st.session_state: st.session_state.indice_carrusel = 0
if 'estados_maquinas' not in st.session_state: st.session_state.estados_maquinas = {name: "Operativa" for name in MACHINE_CONFIGS.keys()}

# =========================================================
# 5. LÓGICA DE LOGIN (BLOQUEO TOTAL)
# =========================================================
if not st.session_state.authenticated:
    st.markdown("<style>section[data-testid='stSidebar'] {display: none;}</style>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br><h2 style='text-align: center;'>🏭 Acceso al Monitor</h2>", unsafe_allow_html=True)
        with st.container(border=True):
            u_ingreso = st.text_input("ID Operador")
            p_ingreso = st.text_input("PIN / Contraseña", type="password")
            if st.button("🚀 Entrar al Sistema", use_container_width=True):
                df_u = db.safe_read("usuarios")
                if not df_u.empty:
                    # Normalizar para búsqueda
                    df_u.columns = [str(c).lower().strip() for c in df_u.columns]
                    u_clean = u_ingreso.strip().lower()
                    
                    # Búsqueda segura con Pandas
                    match = df_u[df_u['usuario'].astype(str).str.strip().str.lower() == u_clean]
                    
                    if not match.empty:
                        stored_hash = str(match.iloc[0]['contrasena']).strip().lower()
                        input_hash = hash_password(p_ingreso)
                        
                        if input_hash == stored_hash:
                            st.session_state.authenticated = True
                            st.session_state.username = u_clean
                            st.session_state.user_role = str(match.iloc[0].get('rol', 'operador')).lower()
                            st.success("Acceso concedido.")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("Contraseña incorrecta.")
                    else:
                        st.error("Usuario no encontrado.")
                else:
                    st.error("Error de base de datos.")
    st.stop() # Detiene la app aquí si no está logueado

# =========================================================
# 6. SIDEBAR (DISEÑO ORIGINAL MIGRADO)
# =========================================================
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.username.upper()}")
    rol_display = str(st.session_state.user_role).upper()
    st.caption(f"🎖️ ROL: {rol_display}")
    
    st.divider()
    run_camera = st.toggle("📷 Activar Cámara de Inspección")
    
    st.divider()
    with st.expander("🔐 Mi Cuenta"):
        nueva_p = st.text_input("Cambiar PIN", type="password")
        if st.button("Actualizar mi PIN"):
            nuevo_h = hash_password(nueva_p)
            exito = db.execute_query(
                "UPDATE usuarios SET contrasena = :h WHERE usuario = :u",
                {"h": nuevo_h, "u": st.session_state.username}
            )
            if exito: st.success("PIN actualizado.")

    if st.button("🚪 Cerrar Sesión", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# =========================================================
# 7. DASHBOARD PRINCIPAL
# =========================================================
st.title("🖨️ Monitor de Inyectores - Planta")

tab_monitor, tab_admin = st.tabs(["📡 Monitor en Vivo", "⚙️ Gestión de Usuarios"])

with tab_monitor:
    # Lógica de las 11 máquinas (Basado en tu estructura original)
    cols = st.columns(3)
    lista_maquinas = list(MACHINE_CONFIGS.keys())
    
    for i, m_name in enumerate(lista_maquinas):
        with cols[i % 3]:
            estado = st.session_state.estados_maquinas.get(m_name, "Operativa")
            with st.container(border=True):
                st.subheader(m_name)
                st.write(f"Estado: {estado}")
                if estado == "Operativa":
                    st.metric("Salud", "98.5%", "-2 Nodos")
                else:
                    st.warning(f"⚠️ {estado}")

with tab_admin:
    if st.session_state.user_role != "admin":
        st.warning("Acceso restringido a administradores.")
    else:
        st.subheader("👥 Panel de Control de Usuarios")
        
        # Crear Usuario
        with st.expander("➕ Registrar Nuevo Usuario"):
            nu_user = st.text_input("Nombre de Usuario")
            nu_pass = st.text_input("Contraseña Inicial", type="password")
            nu_rol = st.selectbox("Rol", ["operador", "admin"])
            if st.button("Crear Usuario"):
                if nu_user and nu_pass:
                    h = hash_password(nu_pass)
                    q = "INSERT INTO usuarios (usuario, contrasena, rol) VALUES (:u, :h, :r)"
                    if db.execute_query(q, {"u": nu_user.lower(), "h": h, "r": nu_rol}):
                        st.success("Usuario creado.")
                        st.rerun()
        
        # Lista de Usuarios Actuales
        st.divider()
        st.write("Usuarios en el sistema:")
        df_users = db.safe_read("usuarios")
        if not df_users.empty:
            st.dataframe(df_users[['usuario', 'rol']], use_container_width=True)
            
            user_del = st.selectbox("Seleccionar usuario para eliminar", df_users['usuario'].tolist())
            if st.button("🗑️ Eliminar Usuario"):
                if user_del != st.session_state.username:
                    db.execute_query("DELETE FROM usuarios WHERE usuario = :u", {"u": user_del})
                    st.success("Eliminado.")
                    st.rerun()
                else:
                    st.error("No puedes eliminarte a ti mismo.")

# =========================================================
# 8. MOTOR DE REFRESCO (VERSION DASHBOARD)
# =========================================================
if not run_camera:
    time.sleep(15)
    st.rerun()
