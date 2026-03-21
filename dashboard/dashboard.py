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
# 1. CONFIGURACIÓN DE PÁGINA Y TEMA INDUSTRIAL
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
    hr { border-color: #334155; }
    /* Estilo para los expanders */
    .streamlit-expanderHeader { background-color: #1e293b !important; color: #3b82f6 !important; font-weight: bold !important; border: 1px solid #334155 !important; }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. DEFINICIÓN DE LA BASE DE DATOS (POSTGRESQL / SUPABASE)
# =========================================================
class PostgresDB:
    def __init__(self):
        self.conn = st.connection("postgresql", type="sql", pool_pre_ping=True)

    def safe_read(self, table_name):
        try:
            return self.conn.query(f'SELECT * FROM "{table_name}"', ttl=0)
        except Exception as e:
            st.error(f"Error al leer {table_name}: {e}")
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

    def get_test_by_date(self, m_name, fecha_consulta):
        df = self.safe_read("tests")
        if df.empty or 'timestamp' not in df.columns: return None
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        mask = (df['machine_name'] == m_name) & (df['timestamp'].dt.date == fecha_consulta)
        res = df[mask]
        if not res.empty: return res.sort_values('timestamp', ascending=False).iloc[0]
        return None

    def get_machine_history(self, m_name, limit=10):
        df = self.safe_read("tests")
        if df.empty or 'timestamp' not in df.columns: return pd.DataFrame(columns=['timestamp', 'health_score'])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df[df['machine_name'] == m_name].sort_values('timestamp', ascending=False).head(limit)

    def save_test_result(self, machine_name, health, missing, mapa, ruta):
        q = """INSERT INTO tests (machine_name, timestamp, health_score, missing_nodes, ruta_evidencia) 
               VALUES (:m, :t, :h, :n, :r)"""
        p = {"m": machine_name, "t": datetime.now(), "h": health, "n": missing, "r": ruta}
        self.execute_query(q, p)

    def get_history_range(self, start, end):
        df = self.safe_read("tests")
        if df.empty or 'timestamp' not in df.columns: return pd.DataFrame()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        mask = (df['timestamp'].dt.date >= start) & (df['timestamp'].dt.date <= end)
        return df[mask]

db = PostgresDB()

def hash_pw(password):
    return hashlib.sha256(str(password).strip().encode('utf-8')).hexdigest().lower()

# =========================================================
# 3. CONFIGURACIÓN DE RUTAS Y PATHS
# =========================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    backend_dir = os.path.join(sys._MEIPASS, "backend")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(BASE_DIR)
    backend_dir = os.path.join(project_root, "backend")

if backend_dir not in sys.path: sys.path.insert(0, backend_dir)

EVIDENCIAS_PATH = os.path.join(BASE_DIR, "evidencias")
REPORTES_PATH = os.path.join(BASE_DIR, "reportes")

for path in [EVIDENCIAS_PATH, REPORTES_PATH]:
    if not os.path.exists(path): os.makedirs(path)

# =========================================================
# 4. IMPORTS DE MÓDULOS PROPIOS
# =========================================================
try:
    import image_processor
    from config import MACHINE_CONFIGS
except ImportError as e:
    st.error(f"Error crítico de importación: {e}")
    st.stop()

# =========================================================
# 5. INICIALIZACIÓN DE SESSION STATE
# =========================================================
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'user_role' not in st.session_state: st.session_state.user_role = None
if 'username' not in st.session_state: st.session_state.username = None
if 'estados_maquinas' not in st.session_state: st.session_state.estados_maquinas = {name: "Operativa" for name in MACHINE_CONFIGS.keys()}
if 'indice_carrusel' not in st.session_state: st.session_state.indice_carrusel = 0
if 'recortes' not in st.session_state: st.session_state.recortes = {}
if 'bloquear_refresco' not in st.session_state: st.session_state.bloquear_refresco = False

# =========================================================
# 6. FUNCIONES DE APOYO E INTERFAZ
# =========================================================
def guardar_evidencia_fisica(imagen_pil, nombre_maquina):
    base_path = os.path.join(EVIDENCIAS_PATH, nombre_maquina)
    if not os.path.exists(base_path): os.makedirs(base_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    full_path = os.path.join(base_path, f"test_{timestamp}.jpg")
    imagen_pil.save(full_path, "JPEG")
    return full_path

def render_machine_card(m_name, fecha_consulta, suffix=""):
    last_test = db.get_test_by_date(m_name, fecha_consulta)
    estado_actual = st.session_state.estados_maquinas.get(m_name, "Operativa")
    fecha_ultimo = last_test.timestamp.strftime('%d/%m/%Y %H:%M') if last_test is not None else "Sin registros"

    opciones_estilo = {
        "Operativa": {"color_b": "#10b981", "color_f": "rgba(16, 185, 129, 0.05)", "icon": "✅"},
        "Mantenimiento": {"color_b": "#64748b", "color_f": "rgba(100, 116, 139, 0.1)", "icon": "🛠️"},
        "Falla Total": {"color_b": "#ef4444", "color_f": "rgba(239, 68, 68, 0.1)", "icon": "🚫"},
        "Falla de Slots": {"color_b": "#f59e0b", "color_f": "rgba(245, 158, 11, 0.1)", "icon": "🔌"},
        "Falla de Tarjetas": {"color_b": "#06b6d4", "color_f": "rgba(6, 182, 212, 0.1)", "icon": "💾"}
    }
    estilo = opciones_estilo.get(estado_actual, opciones_estilo["Operativa"])
    
    if estado_actual == "Operativa" and last_test is not None:
        salud = float(last_test.health_score)
        if salud < 75: estilo["color_b"] = "#f59e0b"
        if salud < 50: estilo["color_b"] = "#ef4444"
        
        with st.container(border=True):
            st.markdown(f"""
                <div style="height: 60px; border-bottom: 2px solid {estilo['color_b']}; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="margin: 0; color: #f8fafc; font-weight: 700;">{estilo['icon']} {m_name}</h3>
                    <span style="background-color: {estilo['color_b']}; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem;">{estado_actual}</span>
                </div>
            """, unsafe_allow_html=True)
            st.metric("Status de Salud", f"{salud:.1f}%", f"-{last_test.missing_nodes} Nodos", delta_color="inverse")
            st.caption(f"Último escaneo: {fecha_ultimo}")
            history = db.get_machine_history(m_name, limit=10)
            if not history.empty:
                st.line_chart(history.set_index('timestamp')['health_score'], height=120, color=estilo["color_b"])
    else:
        st.markdown(f"""
            <div style="height: 380px; border: 2px dashed {estilo['color_b']}; border-radius: 10px; padding: 20px; background-color: {estilo['color_f']}; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center;">
                <h1 style="font-size: 3.5em; margin: 0; text-shadow: 0 0 10px {estilo['color_b']};">{estilo['icon']}</h1>
                <h2 style="margin: 10px 0; color: #f8fafc;">{m_name}</h2>
                <div style="background-color: {estilo['color_b']}; color: white; padding: 5px 15px; border-radius: 4px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px;">{estado_actual}</div>
                <p style="color: #94a3b8; font-size: 0.9em; margin-top: 20px;">Modo restringido.<br>Último test: {fecha_ultimo}</p>
            </div>
        """, unsafe_allow_html=True)

# =========================================================
# 7. LÓGICA DE LOGIN
# =========================================================
if not st.session_state.get('authenticated', False):
    st.markdown("<style>section[data-testid='stSidebar'] {display: none;}</style>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br><h2 style='text-align: center;'>🏭 Print Head Monitor</h2>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("### 🔐 Acceso al Sistema")
            u_ingreso = st.text_input("ID Operador")
            p_ingreso = st.text_input("Contraseña / PIN", type="password")
            if st.button("🚀 Entrar al Monitor", use_container_width=True):
                res_u = db.safe_read("usuarios")
                if not res_u.empty:
                    u_clean = u_ingreso.strip().lower()
                    match = res_u[res_u['usuario'].astype(str).str.lower() == u_clean]
                    if not match.empty and hash_pw(p_ingreso) == str(match.iloc[0]['contrasena']).strip().lower():
                        st.session_state.authenticated = True
                        st.session_state.username = u_clean
                        st.session_state.user_role = str(match.iloc[0].get('rol', 'operador')).lower()
                        st.rerun()
                    else: st.error("❌ Credenciales inválidas")
    st.stop()

# =========================================================
# 8. SIDEBAR (CONFIGURACIONES DINÁMICAS)
# =========================================================
with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.username} | {st.session_state.user_role.upper()}")
    
    # --- FILTRADO POR FECHA (SHOW/HIDE) ---
    with st.expander("📅 Filtro de Fecha", expanded=False):
        fecha_consulta = st.date_input("Consultar Turno:", datetime.now().date())
    
    # --- CONTROL DE PLANTA (SHOW/HIDE) ---
    with st.expander("🛠️ Estados de Planta", expanded=False):
        m_cfg = st.selectbox("Máquina:", list(MACHINE_CONFIGS.keys()))
        est_cfg = st.selectbox("Estado:", ["Operativa", "Mantenimiento", "Falla Total", "Falla de Slots", "Falla de Tarjetas"])
        if st.button("🔄 Actualizar Estado", use_container_width=True):
            st.session_state.estados_maquinas[m_cfg] = est_cfg
            st.toast(f"{m_cfg} -> {est_cfg}")

    st.divider()
    st.subheader("📷 Inspección")
    run_camera = st.toggle("Activar Lente", value=False)
    m_active = st.selectbox("Inspeccionar máquina:", list(MACHINE_CONFIGS.keys()))
    sens = st.slider("Sensibilidad", 0.01, 0.20, 0.05)
    
    if st.button("🚪 Salir", type="primary", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# --- LÓGICA DE CÁMARA (PROCESAMIENTO) ---
if run_camera:
    foto = st.camera_input("Captura de Inyectores")
    if foto:
        st.session_state.bloquear_refresco = True
        with st.spinner("Analizando..."):
            img_bytes = foto.getvalue()
            res = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
            temp_p = os.path.join(BASE_DIR, "temp.jpg")
            cv2.imwrite(temp_p, res)
            mapa, img_res, _ = image_processor.process_test_image_v2(temp_p, MACHINE_CONFIGS[m_active], sens)
            if mapa is not None:
                salud = (np.sum(mapa)/mapa.size)*100
                ruta = guardar_evidencia_fisica(Image.fromarray(cv2.cvtColor(img_res, cv2.COLOR_BGR2RGB)), m_active)
                db.save_test_result(m_active, salud, int(np.count_nonzero(mapa==0)), str(mapa.tolist()), ruta)
                st.success(f"Test guardado: {salud:.1f}%")
                st.session_state.bloquear_refresco = False
                time.sleep(1); st.rerun()

# =========================================================
# 9. TABS PRINCIPALES
# =========================================================
tab_car, tab_planta, tab_analisis, tab_gestion = st.tabs(["🔄 Auto-Monitor", "🏭 Planta", "✂️ Ingesta", "⚙️ Hub Admin"])

lista_maquinas = list(MACHINE_CONFIGS.keys())

with tab_car:
    idx = st.session_state.indice_carrusel
    cols = st.columns(2)
    for i, m in enumerate(lista_maquinas[idx:idx+2]):
        with cols[i]: render_machine_card(m, fecha_consulta)

with tab_planta:
    for i in range(0, len(lista_maquinas), 2):
        cols = st.columns(2)
        for j, m in enumerate(lista_maquinas[i:i+2]):
            with cols[j]: render_machine_card(m, fecha_consulta)

with tab_analisis:
    up = st.file_uploader("Subir test", type=['jpg','png'])
    if up:
        img_rot = Image.open(up).rotate(st.slider("Ángulo", -180, 180, 0), expand=True)
        crop = st_cropper(img_rot, realtime_update=False, key="manual_crop")
        if st.button("🚀 Procesar Recorte"):
            st.info("Procesando módulo manual...")
            # Lógica de procesar manual similar a la cámara...

with tab_gestion:
    if st.session_state.user_role != "admin":
        st.warning("⚠️ Acceso restringido.")
    else:
        t_u, t_r = st.tabs(["👥 Usuarios", "📊 Telemetría"])
        
        with t_u:
            # MOSTRAR/OCULTAR GESTIÓN DE USUARIOS
            df_u = db.safe_read("usuarios")
            st.dataframe(df_u[['usuario', 'rol']], use_container_width=True, hide_index=True)
            
            c1, c2 = st.columns(2)
            with c1:
                with st.expander("➕ Nuevo Usuario", expanded=False):
                    nu = st.text_input("ID")
                    npw = st.text_input("PIN", type="password")
                    nr = st.selectbox("Rol", ["operador", "admin"])
                    if st.button("💾 Crear"):
                        db.execute_query("INSERT INTO usuarios (usuario, contrasena, rol) VALUES (:u,:p,:r)", {"u":nu.lower(),"p":hash_pw(npw),"r":nr})
                        st.rerun()
            with c2:
                with st.expander("🗑️ Borrar Usuario", expanded=False):
                    ud = st.selectbox("Usuario a eliminar:", df_u['usuario'].tolist())
                    if st.button("❌ Eliminar", type="primary"):
                        db.execute_query("DELETE FROM usuarios WHERE usuario = :u", {"u":ud})
                        st.rerun()

        with t_r:
            st.subheader("Rendimiento 7 Días")
            df_s = db.get_history_range(datetime.now()-timedelta(days=7), datetime.now())
            if not df_s.empty: st.bar_chart(df_s.groupby("machine_name")["health_score"].mean())
            
            with st.expander("📥 Exportar Reportes CSV", expanded=False):
                fi = st.date_input("Inicio", datetime.now()-timedelta(days=7))
                ff = st.date_input("Fin", datetime.now())
                if st.button("📊 Generar CSV"):
                    d = db.get_history_range(fi, ff)
                    st.download_button("Descargar", d.to_csv().encode('utf-8'), "reporte.csv")

# =========================================================
# MOTOR DE REFRESCO
# =========================================================
if st.session_state.authenticated and not st.session_state.bloquear_refresco and not run_camera:
    time.sleep(15)
    st.session_state.indice_carrusel = (st.session_state.indice_carrusel + 2) % len(lista_maquinas)
    st.rerun()
