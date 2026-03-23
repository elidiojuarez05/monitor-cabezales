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
# 1. CONFIGURACIÓN DE RUTAS Y BACKEND
# =========================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    backend_dir = os.path.join(sys._MEIPASS, "backend")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(BASE_DIR)
    backend_dir = os.path.join(project_root, "backend")

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Importación de tus módulos personalizados
try:
    import image_processor
    from config import MACHINE_CONFIGS
    # crud.py se usará para funciones específicas si es necesario
except ImportError as e:
    st.error(f"❌ Error al cargar módulos del backend: {e}")
    st.stop()

# =========================================================
# 2. CONFIGURACIÓN DE PÁGINA Y CONEXIÓN POSTGRES
# =========================================================
st.set_page_config(page_title="Print Head Monitor Pro", layout="wide", initial_sidebar_state="expanded")

# Conexión nativa de Streamlit a Postgres
conn = st.connection("postgresql", type="sql")

def query_db(sql, params=None):
    """Consulta segura que devuelve DataFrame"""
    try:
        return conn.query(sql, params=params, ttl=0)
    except Exception as e:
        st.error(f"Error SQL: {e}")
        return pd.DataFrame()

def commit_db(sql, params=None):
    """Ejecuta INSERT/UPDATE/DELETE"""
    try:
        with conn.session as s:
            s.execute(text(sql), params)
            s.commit()
        return True
    except Exception as e:
        st.error(f"Error de escritura: {e}")
        return False

# =========================================================
# 3. ESTADOS DE SESIÓN Y LOGICA DE CARRUSEL
# =========================================================
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'indice_carrusel' not in st.session_state:
    st.session_state.indice_carrusel = 0

# =========================================================
# 4. SISTEMA DE AUTENTICACIÓN (DISEÑO DEL NUEVO DASHBOARD)
# =========================================================
if not st.session_state.authenticated:
    st.markdown("""
        <style>
        .login-box { background-color: #f0f2f6; padding: 2rem; border-radius: 10px; border: 1px solid #d1d5db; }
        </style>
    """, unsafe_allow_dict=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("https://cdn-icons-png.flaticon.com/512/2554/2554030.png", width=80)
        st.title("Acceso al Monitor")
        with st.container(border=True):
            u = st.text_input("Usuario").strip()
            p = st.text_input("Contraseña", type="password")
            if st.button("INGRESAR AL SISTEMA", use_container_width=True, type="primary"):
                res = query_db("SELECT * FROM usuarios WHERE LOWER(username) = LOWER(:u)", {"u": u})
                if not res.empty:
                    db_pass = str(res.iloc[0]['password']).strip()
                    input_hash = hashlib.sha256(p.encode()).hexdigest()
                    if p == db_pass or input_hash == db_pass:
                        st.session_state.authenticated = True
                        st.session_state.username = u
                        st.session_state.role = res.iloc[0]['role']
                        st.rerun()
                    else:
                        st.error("Contraseña incorrecta")
                else:
                    st.error("Usuario no registrado")
    st.stop()

# =========================================================
# 5. SIDEBAR (DETALLES EXACTOS DEL NUEVO DASHBOARD)
# =========================================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/9351/9351296.png", width=100)
    st.markdown(f"### 👷 {st.session_state.username.upper()}")
    st.caption(f"Status: Conectado a PostgreSQL | Rol: {st.session_state.role}")
    st.divider()
    
    st.subheader("Configuración de Vista")
    refresco_auto = st.toggle("Refresco Automático (15s)", value=True)
    sensibilidad = st.slider("Sensibilidad de Escaneo", 0.01, 0.20, 0.05)
    
    if st.button("Cerrar Sesión", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# =========================================================
# 6. CUERPO PRINCIPAL - TABS
# =========================================================
t1, t2, t3, t4 = st.tabs(["📊 ESTADO GLOBAL", "📸 CAPTURA TEST", "📈 HISTORIAL", "⚙️ ADMIN"])

# --- TAB 1: ESTADO GLOBAL (CARRUSEL DINÁMICO) ---
with t1:
    lista_maquinas = list(MACHINE_CONFIGS.keys())
    idx = st.session_state.indice_carrusel
    
    # Seleccionamos 2 máquinas para mostrar (efecto carrusel)
    maquinas_visibles = [lista_maquinas[idx % len(lista_maquinas)], 
                         lista_maquinas[(idx + 1) % len(lista_maquinas)]]
    
    c1, c2 = st.columns(2)
    for i, m_name in enumerate(maquinas_visibles):
        with [c1, c2][i]:
            # Traer último dato de Postgres
            last_test = query_db("""
                SELECT health_score, missing_nodes, timestamp 
                FROM test_results WHERE machine_name = :m 
                ORDER BY timestamp DESC LIMIT 1
            """, {"m": m_name})
            
            with st.container(border=True):
                st.subheader(f"📟 {m_name}")
                if not last_test.empty:
                    val = last_test.iloc[0]['health_score']
                    nodos = last_test.iloc[0]['missing_nodes']
                    ts = last_test.iloc[0]['timestamp']
                    
                    st.metric("Salud de Inyectores", f"{val:.2f}%", f"-{nodos} caídos", delta_color="inverse")
                    st.progress(val/100)
                    st.caption(f"Último Test: {ts.strftime('%d/%m/%Y %H:%M')}")
                else:
                    st.warning("Sin registros recientes")

# --- TAB 2: CAPTURA TEST (PROCESAMIENTO) ---
with t2:
    col_a, col_b = st.columns([1, 1])
    with col_a:
        maquina = st.selectbox("Seleccione Máquina para Inspección", lista_maquinas)
        foto = st.camera_input("Capturar Test de Inyectores")
    
    if foto:
        with col_b:
            with st.spinner("Analizando matriz de inyectores..."):
                temp_path = "temp_scan.jpg"
                with open(temp_path, "wb") as f:
                    f.write(foto.getbuffer())
                
                config = MACHINE_CONFIGS[maquina]
                mapa, img_res, msg = image_processor.process_test_image_v2(temp_path, config, sensibilidad)
                
                if mapa is not None:
                    salud = (np.sum(mapa) / mapa.size) * 100
                    fallas = int(np.count_nonzero(mapa == 0))
                    
                    # Guardar en Postgres
                    commit_db("""
                        INSERT INTO test_results (machine_name, health_score, missing_nodes, timestamp)
                        VALUES (:m, :s, :f, :t)
                    """, {"m": maquina, "s": salud, "f": fallas, "t": datetime.now()})
                    
                    st.image(cv2.cvtColor(img_res, cv2.COLOR_BGR2RGB), caption="Escaneo Finalizado")
                    st.success(f"Resultados guardados: {salud:.2f}% de inyectores activos.")
                else:
                    st.error(f"Error de procesamiento: {msg}")

# --- TAB 3: HISTORIAL ---
with t3:
    st.subheader("Análisis de Tendencia")
    df_h = query_db("SELECT timestamp, machine_name, health_score FROM test_results ORDER BY timestamp ASC")
    if not df_h.empty:
        chart_data = df_h.pivot(index='timestamp', columns='machine_name', values='health_score')
        st.line_chart(chart_data)
        st.dataframe(df_h.sort_values(by='timestamp', ascending=False), use_container_width=True)

# --- TAB 4: ADMIN ---
with t4:
    if st.session_state.role == 'admin':
        st.subheader("Gestión de Usuarios y Base de Datos")
        users = query_db("SELECT id, username, role FROM usuarios")
        st.table(users)
        
        with st.expander("Añadir Personal"):
            new_u = st.text_input("Username")
            new_p = st.text_input("Password", type="password")
            if st.button("Registrar"):
                commit_db("INSERT INTO usuarios (username, password, role) VALUES (:u, :p, :r)",
                          {"u": new_u, "p": new_p, "r": "operator"})
                st.rerun()
    else:
        st.lock_icon()
        st.info("Esta sección es solo para el perfil Administrador.")

# =========================================================
# 7. MOTOR DE SINCRONIZACIÓN (ANTI-LOGOUT)
# =========================================================
if refresco_auto and st.session_state.authenticated:
    # Si no hay una foto en proceso, refrescamos cada 15 seg para el carrusel
    if not foto:
        time.sleep(15)
        st.session_state.indice_carrusel = (st.session_state.indice_carrusel + 2) % len(lista_maquinas)
        st.rerun()
