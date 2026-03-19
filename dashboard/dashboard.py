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
import base64
from streamlit_gsheets import GSheetsConnection

# =========================================================
# 1. CONFIGURACIÓN DE PÁGINA (DEBE SER EL PRIMER COMANDO)
# =========================================================
st.set_page_config(page_title="Print Head Monitor", layout="wide")

# Mantenemos tus estilos personalizados
st.markdown("""
    <style>
    [data-testid="stSidebarNav"] { background-color: rgba(100, 100, 100, 0.1); }
    .st-emotion-cache-1avcm0n { color: orange !important; }
    </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. CONEXIÓN A GOOGLE SHEETS
# =========================================================
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FUNCIONES DE PERSISTENCIA ---
def leer_maquinas():
    return conn.read(worksheet="maquinas", ttl="5s")

def leer_tests():
    return conn.read(worksheet="tests", ttl="5s")

def actualizar_maquina_gsheet(m_name, nuevo_est, user):
    df = leer_maquinas()
    df.loc[df['nombre'] == m_name, ['estado', 'ultima_actualizacion', 'operador']] = \
        [nuevo_est, datetime.now().strftime("%Y-%m-%d %H:%M"), user]
    conn.update(worksheet="maquinas", data=df)

def guardar_test_gsheet(m_name, salud, fallas, user):
    df_tests = leer_tests()
    nuevo = pd.DataFrame([{
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "maquina": m_name,
        "salud": round(salud, 2),
        "fallas": fallas,
        "operador": user
    }])
    df_final = pd.concat([df_tests, nuevo], ignore_index=True)
    conn.update(worksheet="tests", data=df_final)

# =========================================================
# 3. SEGURIDAD (LOGIN CORREGIDO)
# =========================================================
def check_password(username, password):
    try:
        # Forzamos TTL=0 para que no use memoria caché mientras pruebas
        df_users = conn.read(worksheet="usuarios", ttl="0")
        
        # LIMPIEZA TOTAL: Quitamos espacios y pasamos a minúsculas para comparar
        u_ingresado = str(username).strip().lower()
        p_ingresado = str(password).strip()

        # Limpiamos también los datos que vienen de Google Sheets
        df_users['username_clean'] = df_users['username'].astype(str).str.strip().str.lower()
        df_users['password_clean'] = df_users['password'].astype(str).str.strip()

        # Buscamos coincidencia
        user_match = df_users[
            (df_users['username_clean'] == u_input) & 
            (df_users['password_clean'] == p_input)
        ]
        
        if not user_match.empty:
            return user_match.iloc[0]
        else:
            # Esto te ayudará a saber si leyó la hoja pero no encontró al usuario
            st.sidebar.warning(f"Usuario '{u_ingresado}' no encontrado en la lista de {len(df_users)} usuarios.")
            return None
    except Exception as e:
        st.error(f"Error crítico de conexión: {e}")
        return None

# =========================================================
# 4. DISEÑO DE TARJETAS (MISMA VISUALIZACIÓN ANTERIOR)
# =========================================================
def render_machine_card(m_name, row_maquina):
    # Buscamos el último test de esta máquina en la hoja de tests
    df_all_tests = leer_tests()
    last_test = df_all_tests[df_all_tests['maquina'] == m_name].tail(1)
    
    estado_actual = row_maquina['estado']
    fecha_ultimo = row_maquina['ultima_actualizacion']

    opciones_estilo = {
        "Operativa": {"color_b": "#28a745", "icon": "✅"},
        "Mantenimiento": {"color_b": "#6c757d", "icon": "🛠️"},
        "Falla Total": {"color_b": "#dc3545", "icon": "🚫"},
        "Atención": {"color_b": "#fd7e14", "icon": "🔌"}
    }
    estilo = opciones_estilo.get(estado_actual, opciones_estilo["Operativa"])
    
    with st.container(border=True):
        st.markdown(f"""
            <div style="height: 60px; border-bottom: 2px solid {estilo['color_b']}; margin-bottom: 10px;">
                <h3 style="margin: 0; color: {estilo['color_b']};">{estilo['icon']} {m_name}</h3>
                <p style="color: gray; font-size: 0.8em; margin: 0;">Actualizado: {fecha_ultimo}</p>
            </div>
        """, unsafe_allow_html=True)
        
        if not last_test.empty:
            salud = float(last_test['salud'].values[0])
            fallas = int(last_test['fallas'].values[0])
            st.metric("Salud", f"{salud}%", f"{fallas} fallas", delta_color="inverse")
        else:
            st.info("Sin registros de tests")

# =========================================================
# 5. INTERFAZ PRINCIPAL (SIDEBAR Y TABS)
# =========================================================
# --- HEADER ---
st.title("🖨️ Monitor Inteligente de Cabezales")

with st.sidebar:
    st.write(f"👤 Usuario: **{st.session_state.username}**")
    st.write(f"🎖️ Rol: **{st.session_state.user_role}**")
    st.divider()
    
    # Selector de máquina para la cámara
    df_maq = leer_maquinas()
    machine_selected = st.selectbox("Máquina para Escanear:", df_maq['nombre'].tolist())
    run_camera = st.checkbox("📸 Activar Cámara")
    
    if st.button("Cerrar Sesión"):
        st.session_state.authenticated = False
        st.rerun()

# --- LÓGICA DE CÁMARA ---
if run_camera:
    foto = st.camera_input("Capturar Test")
    if foto:
        with st.spinner("Procesando..."):
            # Aquí iría tu image_processor (simulamos resultado para el ejemplo)
            salud_simulada = 95.5
            fallas_simuladas = 2
            
            # Guardamos en Google Sheets
            guardar_test_gsheet(machine_selected, salud_simulada, fallas_simuladas, st.session_state.username)
            actualizar_maquina_gsheet(machine_selected, "Operativa", st.session_state.username)
            
            st.success("✅ Datos sincronizados con la nube")
            time.sleep(1)
            st.rerun()

# --- TABS (MISMA ESTRUCTURA ANTERIOR) ---
tab_carrusel, tab_planta, tab_gestion = st.tabs(["🔄 Modo Carrusel", "🏬 Vista General", "⚙️ Gestión"])

# TAB 1: CARRUSEL
with tab_carrusel:
    idx = st.session_state.indice_carrusel
    lista_m = df_maq['nombre'].tolist()
    cols_car = st.columns(2)
    # Mostramos 2 máquinas a la vez
    for i in range(2):
        m_idx = (idx + i) % len(lista_m)
        name = lista_m[m_idx]
        datos_m = df_maq[df_maq['nombre'] == name].iloc[0]
        with cols_car[i]:
            render_machine_card(name, datos_m)

# TAB 2: VISTA GENERAL
with tab_planta:
    for i in range(0, len(df_maq), 2):
        cols = st.columns(2)
        for j in range(2):
            if i + j < len(df_maq):
                row = df_maq.iloc[i + j]
                with cols[j]:
                    render_machine_card(row['nombre'], row)

# TAB 3: GESTIÓN
with tab_gestion:
    st.subheader("🛠️ Cambiar Estado de Equipos")
    col_g1, col_g2 = st.columns(2)
    m_edit = col_g1.selectbox("Máquina:", df_maq['nombre'].tolist(), key="edit_m")
    nuevo_est = col_g2.selectbox("Nuevo Estado:", ["Operativa", "Mantenimiento", "Falla Total", "Atención"])
    
    if st.button("Actualizar en Nube"):
        actualizar_maquina_gsheet(m_edit, nuevo_est, st.session_state.username)
        st.success("Sincronizado!")
        st.rerun()

# =========================================================
# 6. MOTOR DE SINCRONIZACIÓN
# =========================================================
if not run_camera:
    time.sleep(12)
    # Avanzamos el carrusel
    st.session_state.indice_carrusel = (st.session_state.indice_carrusel + 2) % len(df_maq)
    st.rerun()
