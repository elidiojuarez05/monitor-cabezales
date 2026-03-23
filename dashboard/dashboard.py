import sys
import os
import hashlib
import numpy as np
import cv2
import pandas as pd
import streamlit as st
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

# Importación de módulos internos del proyecto
try:
    import image_processor
    from config import MACHINE_CONFIGS
except ImportError as e:
    st.error(f"❌ Error al cargar módulos del backend: {e}")
    st.stop()

# =========================================================
# 2. CONFIGURACIÓN DE PÁGINA Y CONEXIÓN POSTGRES
# =========================================================
st.set_page_config(page_title="Print Head Monitor", layout="wide", initial_sidebar_state="expanded")

# Mantenemos el estilo visual exacto del dashboard.py original
st.markdown("""
    <style>
    [data-testid="stSidebarNav"] { background-color: rgba(100, 100, 100, 0.1); }
    .st-emotion-cache-1avcm0n { color: orange !important; }
    .main { background-color: #0E1117; }
    </style>
    """, unsafe_allow_html=True)

# Conector a PostgreSQL (Configurado en los Secrets de Streamlit)
conn = st.connection("postgresql", type="sql")

def query_db(sql, params=None):
    return conn.query(sql, params=params, ttl=0)

def commit_db(sql, params=None):
    with conn.session as s:
        s.execute(text(sql), params)
        s.commit()

# =========================================================
# 3. SEGURIDAD Y SESIÓN
# =========================================================
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'indice_carrusel' not in st.session_state:
    st.session_state.indice_carrusel = 0

def check_password(u, p):
    hp = hashlib.sha256(p.encode()).hexdigest()
    res = query_db("SELECT username, role FROM usuarios WHERE username = :u AND password = :p", 
                   params={"u": u, "p": hp})
    return res.iloc[0] if not res.empty else None

# --- INTERFAZ DE LOGIN ---
if not st.session_state.authenticated:
    st.title("🔐 Acceso al Sistema (PostgreSQL)")
    col1, col2 = st.columns([1, 2])
    with col1:
        u_input = st.text_input("Usuario")
        p_input = st.text_input("Contraseña", type="password")
        if st.button("Ingresar", type="primary"):
            user = check_password(u_input, p_input)
            if user is not None:
                st.session_state.authenticated = True
                st.session_state.username = user['username']
                st.session_state.role = user['role']
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
    st.stop()

# =========================================================
# 4. FUNCIONES VISUALES (REPLICA EXACTA DE DASHBOARD.PY)
# =========================================================
def render_machine_card(name):
    # Obtener último test de Postgres
    last_test = query_db("""
        SELECT health_score, fail_count, timestamp 
        FROM test_results WHERE machine_name = :n 
        ORDER BY timestamp DESC LIMIT 1
    """, params={"n": name})
    
    # Obtener estado actual
    m_info = query_db("SELECT status, last_update FROM machines WHERE name = :n", params={"n": name})
    
    estado = m_info.iloc[0]['status'] if not m_info.empty else "Desconectada"
    
    colores = {
        "Operativa": "#28a745", "Mantenimiento": "#6c757d",
        "Falla Total": "#dc3545", "Atención": "#fd7e14"
    }
    color = colores.get(estado, "#ffffff")

    with st.container(border=True):
        st.markdown(f"<h3 style='color:{color}; margin:0;'>{name}</h3>", unsafe_allow_html=True)
        st.caption(f"Estado: {estado}")
        
        if not last_test.empty:
            salud = last_test.iloc[0]['health_score']
            fallas = last_test.iloc[0]['fail_count']
            st.metric("Salud de Cabezales", f"{salud}%", f"{fallas} inyectores tapados", delta_color="inverse")
            st.progress(salud / 100)
        else:
            st.warning("Sin registros recientes")

# =========================================================
# 5. SIDEBAR Y CONTROLES
# =========================================================
with st.sidebar:
    st.title("📊 Panel de Control")
    st.write(f"Conectado como: **{st.session_state.username}**")
    st.divider()
    
    # Obtener lista de máquinas desde Postgres
    df_m = query_db("SELECT name FROM machines ORDER BY id ASC")
    lista_maquinas = df_m['name'].tolist() if not df_m.empty else []
    
    machine_selected = st.selectbox("Seleccionar Máquina", lista_maquinas)
    run_camera = st.checkbox("📸 Activar Escáner")
    
    st.sidebar.divider()
    if st.button("Cerrar Sesión"):
        st.session_state.authenticated = False
        st.rerun()

# =========================================================
# 6. LÓGICA DE CÁMARA E IMAGEN (MIGRADO)
# =========================================================
if run_camera:
    foto = st.camera_input("Capturar Test de Inyectores")
    if foto:
        with st.spinner("Procesando imagen y sincronizando con Postgres..."):
            img = Image.open(foto)
            img_np = np.array(img)
            
            # Llamada al procesador que ya tenías
            res_salud, res_fallas, img_procesada = image_processor.process_test(img_np)
            
            # Guardar en base de datos PostgreSQL
            commit_db("""
                INSERT INTO test_results (machine_name, health_score, fail_count, operator)
                VALUES (:n, :s, :f, :o)
            """, {"n": machine_selected, "s": res_salud, "f": res_fallas, "o": st.session_state.username})
            
            # Actualizar estado de máquina
            nuevo_status = "Operativa" if res_salud > 90 else "Atención"
            commit_db("UPDATE machines SET status = :s, last_update = NOW() WHERE name = :n",
                      {"s": nuevo_status, "n": machine_selected})
            
            st.success(f"✅ Sincronizado: {res_salud}% de salud detectada.")
            time.sleep(1)
            st.rerun()

# =========================================================
# 7. ESTRUCTURA DE TABS (REPLICA VISUAL)
# =========================================================
t1, t2, t3, t4 = st.tabs(["🔄 Carrusel", "🏬 Planta General", "📈 Historial", "⚙️ Admin"])

with t1:
    # Lógica de Carrusel (2 en 2)
    if lista_maquinas:
        idx = st.session_state.indice_carrusel
        c1, c2 = st.columns(2)
        with c1: render_machine_card(lista_maquinas[idx % len(lista_maquinas)])
        with c2: render_machine_card(lista_maquinas[(idx + 1) % len(lista_maquinas)])

with t2:
    # Grid de todas las máquinas
    for i in range(0, len(lista_maquinas), 3):
        cols = st.columns(3)
        for j in range(3):
            if i + j < len(lista_maquinas):
                with cols[j]: render_machine_card(lista_maquinas[i+j])

with t3:
    st.subheader("Histórico de Pruebas (PostgreSQL)")
    hist = query_db("SELECT * FROM test_results ORDER BY timestamp DESC LIMIT 50")
    st.dataframe(hist, use_container_width=True)

with t4:
    if st.session_state.role == 'admin':
        st.subheader("Gestión de Equipos")
        # Aquí puedes poner los controles de CRUD que tenías en dashboard(9)
        if st.button("Resetear todos los estados a Operativa"):
            commit_db("UPDATE machines SET status = 'Operativa'")
            st.rerun()
    else:
        st.info("Acceso restringido a administradores.")

# =========================================================
# 8. MOTOR DE SINCRONIZACIÓN (AUTO-REFRESH)
# =========================================================
if st.session_state.authenticated and not run_camera:
    time.sleep(12) # Intervalo de refresco
    # Avanzar carrusel
    if len(lista_maquinas) > 0:
        st.session_state.indice_carrusel = (st.session_state.indice_carrusel + 2) % len(lista_maquinas)
    st.rerun()
