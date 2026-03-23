import streamlit as st
import pandas as pd
import numpy as np
import cv2
import hashlib
import os
import sys
import time
from PIL import Image
from datetime import datetime, timedelta

# =========================================================
# 1. CONFIGURACIÓN DE RUTAS (BACKEND EN SUB-CARPETA)
# =========================================================
# Obtener la ruta absoluta de la carpeta donde está dashboard.py
current_dir = os.path.dirname(os.path.abspath(__file__))

# Subir un nivel (si dashboard.py está en una carpeta propia) 
# y luego entrar a 'backend'
project_root = os.path.dirname(current_dir)
backend_path = os.path.join(project_root, "backend")

# Si 'backend' está al mismo nivel que dashboard.py, usa esta:
# backend_path = os.path.join(current_dir, "backend")

if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# Ahora ya puedes importar sin el prefijo 'backend.'
try:
    import image_processor
    from config import MACHINE_CONFIGS
except ImportError as e:
    st.error(f"Error al importar módulos del backend: {e}")
    st.info(f"Ruta intentada: {backend_path}")
    st.stop()

# =========================================================
# 2. CONEXIÓN DIRECTA A POSTGRESQL
# ========================================================

# Conexión
conn = st.connection("postgresql", type="sql")

def ejecutar_query(query, params=None):
    """Ejecuta una consulta SELECT de forma segura"""
    try:
        # Usamos text() para que SQLAlchemy no confunda los dos puntos (:) 
        # con sintaxis interna de la base de datos
        return conn.query(text(query), params=params, ttl=0)
    except Exception as e:
        st.error(f"Error en la consulta: {e}")
        return pd.DataFrame()

# --- Bloque de Login ---
user_input = st.text_input("Usuario")
# ... resto del código ...
if st.button("Entrar"):
    # IMPORTANTE: Asegúrate de que los nombres coincidan con la tabla creada arriba
    res = ejecutar_query('SELECT * FROM usuarios WHERE username = :u', params={"u": user_input})

# Al llamar a la función en el login:
res = ejecutar_query('SELECT * FROM usuarios WHERE username = :u', params={"u": user_input})

def ejecutar_comando(query, params=None):
    """Ejecuta un comando que modifica datos (INSERT, UPDATE, DELETE)"""
    with conn.session as s:
        s.execute(query, params)
        s.commit()

# =========================================================
# 3. INTERFAZ DE LOGIN (SQL DIRECTO)
# =========================================================
st.set_page_config(page_title="Print Head Monitor", layout="wide")

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Acceso al Sistema")
    with st.form("login_form"):
        user_input = st.text_input("Usuario")
        pass_input = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar"):
            # Consulta directa a la tabla usuarios
            res = ejecutar_query('SELECT * FROM usuarios WHERE username = :u', params={"u": user_input})
            
            if not res.empty:
                db_pass = res.iloc[0]['password']
                # Verificamos si es hash o texto plano
                input_hash = hashlib.sha256(pass_input.encode()).hexdigest()
                
                if pass_input == db_pass or input_hash == db_pass:
                    st.session_state.authenticated = True
                    st.session_state.username = user_input
                    st.session_state.role = res.iloc[0]['role']
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta")
            else:
                st.error("Usuario no encontrado")
    st.stop()

# =========================================================
# 4. DASHBOARD PRINCIPAL
# =========================================================
st.title(f"🖨️ Monitor de Planta - {st.session_state.username}")

# Tabs para organizar la vista
tab1, tab2, tab3 = st.tabs(["📊 Estado Actual", "📸 Captura de Test", "⚙️ Administración"])

with tab1:
    st.subheader("Estado de las Máquinas en Tiempo Real")
    # Traemos los últimos resultados de cada máquina
    query_status = """
        SELECT DISTINCT ON (machine_name) 
        machine_name, health_score, missing_nodes, timestamp 
        FROM test_results 
        ORDER BY machine_name, timestamp DESC
    """
    df_actual = ejecutar_query(query_status)
    
    cols = st.columns(3)
    for i, (m_name, config) in enumerate(MACHINE_CONFIGS.items()):
        with cols[i % 3]:
            # Buscamos si hay datos en el DF para esta máquina
            info_m = df_actual[df_actual['machine_name'] == m_name]
            
            with st.container(border=True):
                if not info_m.empty:
                    salud = info_m.iloc[0]['health_score']
                    nodos = info_m.iloc[0]['missing_nodes']
                    st.metric(label=m_name, value=f"{salud:.1f}%", delta=f"-{nodos} nodos")
                    st.caption(f"Último update: {info_m.iloc[0]['timestamp']}")
                else:
                    st.metric(label=m_name, value="N/A", delta="Sin datos")

with tab2:
    st.subheader("Nueva Inspección")
    maquina = st.selectbox("Seleccionar Máquina", list(MACHINE_CONFIGS.keys()))
    foto = st.camera_input("Capturar Test")
    
    if foto:
        # Procesamiento con tu módulo de backend
        temp_file = "temp_capture.jpg"
        with open(temp_file, "wb") as f:
            f.write(foto.getbuffer())
        
        config_m = MACHINE_CONFIGS[maquina]
        mapa, img_res, msg = image_processor.process_test_image_v2(temp_file, config_m)
        
        if mapa is not None:
            salud = (np.sum(mapa) / mapa.size) * 100
            fallas = int(np.count_nonzero(mapa == 0))
            
            # GUARDAR EN POSTGRESQL DIRECTO
            insert_query = """
                INSERT INTO test_results (machine_name, health_score, missing_nodes, timestamp)
                VALUES (:m, :s, :f, :t)
            """
            ejecutar_comando(insert_query, {
                "m": maquina, 
                "s": salud, 
                "f": fallas, 
                "t": datetime.now()
            })
            
            st.success(f"Captura guardada. Salud: {salud:.2f}%")
            time.sleep(2)
            st.rerun()

with tab3:
    if st.session_state.role == 'admin':
        st.subheader("Gestión de Usuarios")
        usuarios_df = ejecutar_query("SELECT id, username, role FROM usuarios")
        st.dataframe(usuarios_df, use_container_width=True)
        
        with st.expander("Añadir Nuevo Operador"):
            new_u = st.text_input("Nuevo Usuario")
            new_p = st.text_input("Nueva Contraseña", type="password")
            if st.button("Registrar"):
                h = hashlib.sha256(new_p.encode()).hexdigest()
                ejecutar_comando("INSERT INTO usuarios (username, password, role) VALUES (:u, :p, :r)",
                                 {"u": new_u, "p": h, "r": "operator"})
                st.success("Usuario creado")
                st.rerun()
    else:
        st.warning("No tienes permisos de administrador.")

# Botón para refrescar manualmente
if st.sidebar.button("🔄 Sincronizar Datos"):
    st.rerun()

st.sidebar.button("Log out", on_click=lambda: st.session_state.update({"authenticated": False}))
