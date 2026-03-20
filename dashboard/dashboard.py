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
from streamlit_gsheets import GSheetsConnection

# =========================================================
# 1. CONFIGURACIÓN DE PÁGINA E IMAGEN INDUSTRIAL
# =========================================================
st.set_page_config(page_title="Industrial Print Monitor", layout="wide", initial_sidebar_state="expanded")

# CSS Personalizado: Estética de Terminal Industrial / Dark Mode Pro
st.markdown("""
    <style>
    .stApp { background-color: #0b0e14; color: #d1d5db; }
    [data-testid="stMetricValue"] { color: #00e5ff; font-family: 'IBM Plex Mono', monospace; font-size: 1.8rem !important; }
    .stButton>button {
        background-color: #1a202c; border: 1px solid #2d3748; color: #60a5fa;
        font-weight: 600; text-transform: uppercase; letter-spacing: 1px;
    }
    .stButton>button:hover { border-color: #3b82f6; color: white; background-color: #2563eb; }
    div[data-testid="stSidebar"] { background-color: #0f172a; border-right: 1px solid #1e293b; }
    .status-card {
        padding: 1.5rem; border-radius: 4px; border-left: 4px solid #3b82f6;
        background-color: #161b22; margin-bottom: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. CONEXIÓN Y LÓGICA DE DATOS (GOOGLE SHEETS)
# =========================================================
conn = st.connection("gsheets", type=GSheetsConnection)

class DataManager:
    """Manejo de datos basado en las pestañas específicas del usuario."""
    
    @staticmethod
    def get_user(username):
        df = conn.read(worksheet="usuarios", ttl=0)
        user_row = df[df['usuario'] == username]
        return user_row.iloc[0] if not user_row.empty else None

    @staticmethod
    def get_maquinas():
        return conn.read(worksheet="maquinas", ttl=0)

    @staticmethod
    def update_maquina_status(nombre, estado, operador):
        df = conn.read(worksheet="maquinas", ttl=0)
        idx = df.index[df['nombre'] == nombre].tolist()
        if idx:
            df.at[idx[0], 'estado'] = estado
            df.at[idx[0], 'operador'] = operador
            df.at[idx[0], 'ultima_actulizacion'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.update(worksheet="maquinas", data=df)

    @staticmethod
    def save_test(maquina, salud, fallas, url_evidencia):
        df = conn.read(worksheet="tests", ttl=0)
        nuevo_test = pd.DataFrame([{
            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "maquina": maquina,
            "salud": f"{salud:.2f}",
            "fallas": int(fallas),
            "evidencias_url": url_evidencia
        }])
        df_updated = pd.concat([df, nuevo_test], ignore_index=True)
        conn.update(worksheet="tests", data=df_updated)

    @staticmethod
    def get_last_test(maquina):
        df = conn.read(worksheet="tests", ttl=0)
        res = df[df['maquina'] == maquina].sort_values(by='fecha', ascending=False)
        return res.iloc[0] if not res.empty else None

# =========================================================
# 3. SESIÓN E INTERFAZ DE ACCESO
# =========================================================
if 'authenticated' not in st.session_state: st.session_state.authenticated = False

if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("<h2 style='text-align:center;'>CONTROL DE ACCESO INDUSTRIAL</h2>", unsafe_allow_html=True)
        user_in = st.text_input("Usuario (Operador)")
        pass_in = st.text_input("PIN / Contraseña", type="password")
        if st.button("INGRESAR AL SISTEMA", use_container_width=True):
            user_data = DataManager.get_user(user_in)
            if user_data is not None and user_data['contraseña'] == hashlib.sha256(pass_in.encode()).hexdigest():
                st.session_state.authenticated = True
                st.session_state.username = user_in
                st.session_state.role = user_data['rol']
                st.rerun()
            else:
                st.error("Acceso denegado. Verifique credenciales.")
    st.stop()

# =========================================================
# 4. DASHBOARD PRINCIPAL
# =========================================================

# --- BARRA LATERAL ---
with st.sidebar:
    st.markdown(f"### 🛠️ Estación: {st.session_state.username}")
    st.caption(f"Rol: {st.session_state.role}")
    st.divider()
    
    selected_m = st.selectbox("Seleccionar Máquina para Inspección", DataManager.get_maquinas()['nombre'])
    run_camera = st.toggle("🎥 Activar Cámara de Inspección", False)
    
    st.divider()
    if st.button("Cerrar Sesión", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# --- CUERPO DEL DASHBOARD ---
st.title("📊 Monitor de Inyectores en Tiempo Real")

# Sección de Cámara (Solo si se activa)
if run_camera:
    foto = st.camera_input("Capturar Test de Inyectores")
    if foto:
        with st.spinner("Procesando en la Nube..."):
            # Lógica de procesamiento simulada (Integrar aquí tu image_processor)
            salud_calculada = 98.5 # Ejemplo
            fallas_detectadas = 12 # Ejemplo
            
            # Guardar en GSheets (pestaña tests)
            DataManager.save_test(selected_m, salud_calculada, fallas_detectadas, "local_storage_or_cloud_url")
            # Actualizar estado de máquina (pestaña maquinas)
            DataManager.update_maquina_status(selected_m, "Operativa", st.session_state.username)
            
            st.success(f"Test registrado para {selected_m}")
            time.sleep(2)
            st.rerun()

# --- VISTA DE PLANTA (Pestaña maquinas y tests combinadas) ---
df_m = DataManager.get_maquinas()
cols = st.columns(3)

for i, row in df_m.iterrows():
    with cols[i % 3]:
        last_t = DataManager.get_last_test(row['nombre'])
        
        # Color según estado y salud
        border_color = "#10b981" # Verde
        if row['estado'] != "Operativa": border_color = "#ef4444" # Rojo
        elif last_t is not None and float(last_t['salud']) < 90: border_color = "#f59e0b" # Naranja

        st.markdown(f"""
            <div class="status-card" style="border-left-color: {border_color};">
                <h3 style="margin:0;">{row['nombre']}</h3>
                <p style="font-size:0.8rem; color:#94a3b8;">Estado: <b>{row['estado']}</b></p>
                <p style="font-size:0.7rem; color:#64748b;">Op: {row['operador']} | {row['ultima_actulizacion']}</p>
            </div>
        """, unsafe_allow_html=True)
        
        if last_t is not None:
            st.metric("Salud de Cabezal", f"{last_t['salud']}%", f"{last_t['fallas']} fallas", delta_color="inverse")
        else:
            st.caption("Sin historial de tests")

# --- HISTORIAL Y ANÁLISIS ---
st.divider()
with st.expander("📝 Ver Historial Reciente de Tests (Google Sheets)"):
    df_h = conn.read(worksheet="tests", ttl=0)
    st.dataframe(df_h.sort_values(by='fecha', ascending=False), use_container_width=True)

# Lógica de Refresco Automático (Sincronización Industrial)
if not run_camera:
    time.sleep(20) # Refresco cada 20 segundos para no saturar la API de Google
    st.rerun()
