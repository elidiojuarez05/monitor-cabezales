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
from sqlalchemy import text

# =========================================================
# 1. CONFIGURACIÓN DE PÁGINA (SIEMPRE PRIMERO)
# =========================================================
st.set_page_config(page_title="Print Head Monitor", layout="wide", initial_sidebar_state="expanded")

# Estilos CSS Profesionales
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #e0e6ed; }
    div[data-testid="stMetricValue"] { color: #00ff41; font-family: 'Courier New', Courier, monospace; font-weight: bold; }
    .stButton>button {
        background-color: #1e3a8a; color: white; border-radius: 4px; border: 1px solid #3b82f6; font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton>button:hover { background-color: #3b82f6; border: 1px solid #60a5fa; box-shadow: 0 0 10px rgba(59, 130, 246, 0.5); }
    section[data-testid="stSidebar"] { background-color: #111827; border-right: 1px solid #334155; }
    .streamlit-expanderHeader { background-color: #1e293b !important; color: #3b82f6 !important; font-weight: bold !important; border-radius: 5px; }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. CONEXIÓN Y DB
# =========================================================
class PostgresDB:
    def __init__(self):
        self.conn = st.connection("postgresql", type="sql", pool_pre_ping=True)

    def safe_read(self, table_name):
        try:
            return self.conn.query(f'SELECT * FROM "{table_name}"', ttl=0)
        except Exception:
            return pd.DataFrame()

    def execute_query(self, query, params=None):
        try:
            with self.conn.session as s:
                s.execute(text(query), params or {})
                s.commit()
            return True
        except Exception as e:
            st.error(f"Error SQL: {e}")
            return False

    def get_test_by_date(self, m_name, fecha):
        df = self.safe_read("tests")
        if df.empty: return None
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        mask = (df['machine_name'] == m_name) & (df['timestamp'].dt.date == fecha)
        res = df[mask]
        return res.sort_values('timestamp', ascending=False).iloc[0] if not res.empty else None

    def get_machine_history(self, m_name, limit=10):
        df = self.safe_read("tests")
        if df.empty: return pd.DataFrame()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df[df['machine_name'] == m_name].sort_values('timestamp', ascending=False).head(limit)

    def save_test_result(self, machine_name, health, missing, mapa, ruta):
        q = "INSERT INTO tests (machine_name, timestamp, health_score, missing_nodes, ruta_evidencia) VALUES (:m,:t,:h,:n,:r)"
        self.execute_query(q, {"m": machine_name, "t": datetime.now(), "h": health, "n": missing, "r": ruta})

    def get_history_range(self, start, end):
        df = self.safe_read("tests")
        if df.empty: return pd.DataFrame()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df[(df['timestamp'].dt.date >= start) & (df['timestamp'].dt.date <= end)]

db = PostgresDB()

def hash_pw(password):
    return hashlib.sha256(str(password).strip().encode('utf-8')).hexdigest().lower()

# =========================================================
# 3. RUTAS E IMPORTS
# =========================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    backend_dir = os.path.join(sys._MEIPASS, "backend")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(os.path.dirname(BASE_DIR), "backend")

if backend_dir not in sys.path: sys.path.insert(0, backend_dir)

try:
    import image_processor
    from config import MACHINE_CONFIGS
except ImportError as e:
    st.error(f"Faltan módulos: {e}")
    st.stop()

# =========================================================
# 4. SESSION STATE
# =========================================================
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'user_role' not in st.session_state: st.session_state.user_role = None
if 'username' not in st.session_state: st.session_state.username = None
if 'estados_maquinas' not in st.session_state: st.session_state.estados_maquinas = {name: "Operativa" for name in MACHINE_CONFIGS.keys()}
if 'indice_carrusel' not in st.session_state: st.session_state.indice_carrusel = 0
if 'bloquear_refresco' not in st.session_state: st.session_state.bloquear_refresco = False

# =========================================================
# 5. LÓGICA DE LOGIN (SÓLIDA)
# =========================================================
if not st.session_state.authenticated:
    st.markdown("<style>section[data-testid='stSidebar'] {display: none;}</style>", unsafe_allow_html=True)
    _, col_login, _ = st.columns([1, 1.5, 1])
    with col_login:
        st.markdown("<br><br><h1 style='text-align: center;'>🏭 Print Head Monitor</h1>", unsafe_allow_html=True)
        with st.container(border=True):
            st.subheader("🔐 Acceso de Personal")
            u_in = st.text_input("Usuario / ID")
            p_in = st.text_input("PIN / Password", type="password")
            if st.button("🚀 Ingresar", use_container_width=True):
                df_u = db.safe_read("usuarios")
                if not df_u.empty:
                    u_clean = u_in.strip().lower()
                    match = df_u[df_u['usuario'].astype(str).str.lower() == u_clean]
                    if not match.empty and hash_pw(p_in) == str(match.iloc[0]['contrasena']).strip().lower():
                        st.session_state.authenticated = True
                        st.session_state.username = u_clean
                        st.session_state.user_role = str(match.iloc[0].get('rol', 'operador')).lower()
                        st.rerun()
                    else: st.error("❌ Credenciales incorrectas.")
                else: st.error("❌ No hay conexión con la base de datos.")
    st.stop()

# =========================================================
# 6. SIDEBAR (POST-LOGIN)
# =========================================================
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.username.upper()}")
    st.caption(f"🎖️ Rol: {st.session_state.user_role.upper()}")
    
    # --- REAPARICIÓN: EDITAR PERFIL ---
    with st.expander("⚙️ Mi Perfil", expanded=False):
        new_pw = st.text_input("Nuevo PIN", type="password")
        conf_pw = st.text_input("Confirmar PIN", type="password")
        if st.button("💾 Actualizar PIN"):
            if new_pw == conf_pw and new_pw:
                db.execute_query("UPDATE usuarios SET contrasena = :p WHERE usuario = :u", 
                                 {"p": hash_pw(new_pw), "u": st.session_state.username})
                st.success("✅ Actualizado")
            else: st.error("❌ Error en PIN")

    st.divider()
    
    # --- FILTRO DE FECHA ---
    with st.expander("📅 Consultar Fecha", expanded=False):
        fecha_consulta = st.date_input("Día del turno:", datetime.now().date())
    
    # --- CONTROL DE PLANTA ---
    with st.expander("🛠️ Control de Máquinas", expanded=False):
        m_cfg = st.selectbox("Máquina:", list(MACHINE_CONFIGS.keys()))
        est_cfg = st.selectbox("Estado:", ["Operativa", "Mantenimiento", "Falla Total"])
        if st.button("🔄 Cambiar Estado", use_container_width=True):
            st.session_state.estados_maquinas[m_cfg] = est_cfg
            st.toast(f"{m_cfg} ahora en {est_cfg}")

    st.divider()
    run_camera = st.toggle("📷 Abrir Cámara", value=False)
    m_active = st.selectbox("Inyectores de:", list(MACHINE_CONFIGS.keys()))
    
    if st.button("🚪 Cerrar Sesión", type="primary", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# =========================================================
# 7. DASHBOARD PRINCIPAL
# =========================================================
st.markdown("<h2 style='margin-top:-50px;'>📊 Panel de Telemetría</h2>", unsafe_allow_html=True)

tab_car, tab_planta, tab_admin = st.tabs(["🔄 Carrusel", "🏭 Mapa Total", "⚙️ Gestión Admin"])

# Lógica de renderizado de tarjetas (simplificada para el ejemplo)
def render_card(name, fecha):
    last = db.get_test_by_date(name, fecha)
    estado = st.session_state.estados_maquinas.get(name, "Operativa")
    with st.container(border=True):
        st.subheader(f"{name}")
        if estado == "Operativa" and last is not None:
            st.metric("Salud", f"{last.health_score:.1f}%", f"-{last.missing_nodes} iny")
        else:
            st.warning(f"Estado: {estado}")

with tab_car:
    idx = st.session_state.indice_carrusel
    lista = list(MACHINE_CONFIGS.keys())
    c1, c2 = st.columns(2)
    with c1: render_card(lista[idx], fecha_consulta)
    with c2: render_card(lista[(idx+1)%len(lista)], fecha_consulta)

with tab_planta:
    lista = list(MACHINE_CONFIGS.keys())
    for i in range(0, len(lista), 3):
        cols = st.columns(3)
        for j, m in enumerate(lista[i:i+3]):
            with cols[j]: render_card(m, fecha_consulta)

with tab_admin:
    if st.session_state.user_role != "admin":
        st.warning("⚠️ Acceso denegado.")
    else:
        # GESTIÓN DE USUARIOS CON HIDE/SHOW
        st.subheader("👥 Control de Usuarios")
        df_u = db.safe_read("usuarios")
        st.dataframe(df_u[['usuario', 'rol']], use_container_width=True, hide_index=True)
        
        c_add, c_del = st.columns(2)
        with c_add:
            with st.expander("➕ Nuevo Usuario", expanded=False):
                nu = st.text_input("ID Operador")
                np = st.text_input("PIN Inicial", type="password")
                nr = st.selectbox("Rol", ["operador", "admin"], key="rol_add")
                if st.button("💾 Crear Cuenta"):
                    db.execute_query("INSERT INTO usuarios (usuario, contrasena, rol) VALUES (:u,:p,:r)", 
                                     {"u":nu.lower(), "p":hash_pw(np), "r":nr})
                    st.rerun()
        with c_del:
            with st.expander("🗑️ Eliminar Usuario", expanded=False):
                ud = st.selectbox("Cuenta a borrar:", df_u['usuario'].tolist())
                if st.button("❌ Ejecutar Borrado", type="primary"):
                    if ud != st.session_state.username:
                        db.execute_query("DELETE FROM usuarios WHERE usuario = :u", {"u":ud})
                        st.rerun()
                    else: st.error("No puedes borrarte a ti mismo.")

# =========================================================
# 8. MOTOR DE REFRESCO
# =========================================================
if not run_camera:
    time.sleep(15)
    st.session_state.indice_carrusel = (st.session_state.indice_carrusel + 2) % len(MACHINE_CONFIGS)
    st.rerun()
