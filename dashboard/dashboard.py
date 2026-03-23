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
from sqlalchemy import text

# =========================================================
# 1. CONFIGURACIÓN DE PÁGINA Y RUTAS
# =========================================================
st.set_page_config(page_title="Print Head Monitor", layout="wide", initial_sidebar_state="expanded")

# Ajuste de rutas para importar backend
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
backend_path = os.path.join(project_root, "backend")

if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

try:
    import image_processor
    from config import MACHINE_CONFIGS
except ImportError as e:
    st.error(f"Error al importar módulos del backend: {e}")
    st.stop()

# =========================================================
# 2. CONEXIÓN A BASE DE DATOS (POSTGRESQL)
# =========================================================
conn = st.connection("postgresql", type="sql")

def ejecutar_query(query_string, params=None):
    """Ejecuta consultas SELECT pasando el SQL como string para evitar errores de hash"""
    try:
        # Pasamos la cadena de texto directamente, no el objeto text()
        # El parámetro ttl=0 es vital para que veas cambios en tiempo real
        return conn.query(query_string, params=params, ttl=0)
    except Exception as e:
        st.error(f"Error en base de datos: {e}")
        return pd.DataFrame()

def ejecutar_comando(query, params=None):
    """Ejecuta INSERT, UPDATE, DELETE"""
    try:
        with conn.session as s:
            s.execute(text(query), params)
            s.commit()
        return True
    except Exception as e:
        st.error(f"Error al guardar: {e}")
        return False

# =========================================================
# 3. LÓGICA DE AUTENTICACIÓN
# =========================================================
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("## 🔐 Acceso al Sistema")
    with st.container(border=True):
        u_ingreso = st.text_input("Usuario").strip() # Quitamos espacios
        p_ingreso = st.text_input("Contraseña", type="password")
        
        if st.button("🚀 Entrar al Monitor", use_container_width=True):
            # Usamos una consulta simple. El parámetro :u es estándar para st.connection
            query_login = "SELECT * FROM usuarios WHERE LOWER(username) = LOWER(:u)"
            res = ejecutar_query(query_login, params={"u": u_ingreso})
            
            if not res.empty:
                # Extraemos los datos de la primera fila encontrada
                db_pass = str(res.iloc[0]['password']).strip()
                user_role = str(res.iloc[0]['role']).strip()
                
                # Hash de la contraseña ingresada para comparar
                input_hash = hashlib.sha256(p_ingreso.encode()).hexdigest()
                
                if p_ingreso == db_pass or input_hash == db_pass:
                    st.session_state.authenticated = True
                    st.session_state.username = u_ingreso
                    st.session_state.role = user_role
                    st.success("Acceso concedido")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ Contraseña incorrecta")
            else:
                st.error(f"❌ El usuario '{u_ingreso}' no existe en la base de datos.")
    st.stop()

# =========================================================
# 4. INTERFAZ PRINCIPAL (DASHBOARD)
# =========================================================

# Sidebar con controles
with st.sidebar:
    st.title(f"👤 {st.session_state.username}")
    st.caption(f"Rol: {st.session_state.role.upper()}")
    st.divider()
    
    sensibilidad = st.slider("Sensibilidad de Escaneo", 0.01, 0.20, 0.05)
    
    if st.button("🚪 Cerrar Sesión", type="primary", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# Tabs de navegación
tab1, tab2, tab3, tab4 = st.tabs(["📊 Estado Global", "📸 Captura Test", "📈 Historial", "⚙️ Admin"])

# --- TAB 1: ESTADO ACTUAL ---
with tab1:
    st.subheader("Estado de Inyectores por Máquina")
    # Traer el último test de cada máquina
    query_last = """
        SELECT DISTINCT ON (machine_name) machine_name, health_score, missing_nodes, timestamp 
        FROM test_results ORDER BY machine_name, timestamp DESC
    """
    df_actual = ejecutar_query(query_last)
    
    cols = st.columns(3)
    for i, (m_name, config) in enumerate(MACHINE_CONFIGS.items()):
        with cols[i % 3]:
            info_m = df_actual[df_actual['machine_name'] == m_name]
            with st.container(border=True):
                if not info_m.empty:
                    salud = info_m.iloc[0]['health_score']
                    nodos = info_m.iloc[0]['missing_nodes']
                    st.metric(m_name, f"{salud:.1f}%", f"-{nodos} inyectores", delta_color="inverse")
                    st.caption(f"Actualizado: {info_m.iloc[0]['timestamp'].strftime('%H:%M - %d/%m')}")
                else:
                    st.metric(m_name, "N/A", "Sin datos")

# --- TAB 2: CAPTURA ---
with tab2:
    st.subheader("Nueva Inspección de Cabezal")
    maquina_selec = st.selectbox("Seleccionar Máquina", list(MACHINE_CONFIGS.keys()))
    foto = st.camera_input("Tomar foto del test")
    
    if foto:
        temp_file = "temp_capture.jpg"
        with open(temp_file, "wb") as f:
            f.write(foto.getbuffer())
        
        with st.spinner("Procesando imagen..."):
            conf = MACHINE_CONFIGS[maquina_selec]
            mapa, img_res, msg = image_processor.process_test_image_v2(temp_file, conf, sensibilidad)
            
            if mapa is not None:
                salud = (np.sum(mapa) / mapa.size) * 100
                fallas = int(np.count_nonzero(mapa == 0))
                
                # Guardar resultado en Postgres
                query_ins = """
                    INSERT INTO test_results (machine_name, health_score, missing_nodes, timestamp)
                    VALUES (:m, :s, :f, :t)
                """
                exito = ejecutar_comando(query_ins, {
                    "m": maquina_selec, "s": salud, "f": fallas, "t": datetime.now()
                })
                
                if exito:
                    st.image(cv2.cvtColor(img_res, cv2.COLOR_BGR2RGB), caption="Resultado del Análisis")
                    st.success(f"Guardado. Salud: {salud:.2f}% | Fallas: {fallas}")
                    st.balloons()
            else:
                st.error("No se pudo procesar la imagen. Verifique la iluminación.")

# --- TAB 3: HISTORIAL ---
with tab3:
    st.subheader("Tendencia de Salud (Últimos 30 días)")
    df_hist = ejecutar_query("SELECT timestamp, machine_name, health_score FROM test_results ORDER BY timestamp ASC")
    if not df_hist.empty:
        # Gráfico de líneas dinámico
        df_pivot = df_hist.pivot(index='timestamp', columns='machine_name', values='health_score')
        st.line_chart(df_pivot)
    else:
        st.info("Aún no hay datos históricos para mostrar.")

# --- TAB 4: ADMIN ---
with tab4:
    if st.session_state.role == 'admin':
        st.subheader("Gestión de Usuarios")
        df_users = ejecutar_query("SELECT id, username, role FROM usuarios")
        st.dataframe(df_users, use_container_width=True)
        
        with st.expander("➕ Registrar Nuevo Operador"):
            nuevo_u = st.text_input("ID Usuario")
            nuevo_p = st.text_input("Password", type="password")
            if st.button("Crear Usuario"):
                h = hashlib.sha256(nuevo_p.encode()).hexdigest()
                ejecutar_comando("INSERT INTO usuarios (username, password, role) VALUES (:u, :p, :r)",
                                 {"u": nuevo_u, "p": h, "r": "operator"})
                st.success("Usuario registrado correctamente.")
                st.rerun()
    else:
        st.warning("Acceso restringido. Solo administradores pueden ver esta pestaña.")
