import streamlit as st
import pandas as pd
import numpy as np
import cv2
import os
import time
from PIL import Image
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# =========================================================
# 1. CONFIGURACIÓN DE PÁGINA (DEBE SER EL PRIMER COMANDO)
# =========================================================
st.set_page_config(
    page_title="Monitor de Inyectores - Cloud Sync",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos para asegurar visibilidad en modo claro y oscuro
st.markdown("""
    <style>
    .main { background-color: #0E1117; color: white; }
    [data-testid="stSidebar"] { background-color: #1a1c23; }
    .stButton>button { width: 100%; border-radius: 5px; }
    /* Mejorar visibilidad de títulos */
    h1, h2, h3 { color: #FAFAFA !important; }
    </style>
    """, unsafe_allow_html=True)

# =========================================================
# 2. CONEXIÓN A GOOGLE SHEETS
# =========================================================
conn = st.connection("gsheets", type=GSheetsConnection)

def get_data(worksheet_name):
    return conn.read(worksheet=worksheet_name, ttl="5s")

# =========================================================
# 3. ESTADO DE LA SESIÓN
# =========================================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "indice_carrusel" not in st.session_state:
    st.session_state.indice_carrusel = 0

# =========================================================
# 4. FUNCIONES DE LÓGICA
# =========================================================

def check_password(username, password):
    try:
        df_users = get_data("usuarios")
        user_row = df_users[(df_users['username'] == str(username)) & 
                            (df_users['password'].astype(str) == str(password))]
        return user_row.iloc[0] if not user_row.empty else None
    except:
        return None

def update_machine_status(m_name, new_status):
    df_m = get_data("maquinas")
    df_m.loc[df_m['nombre'] == m_name, ['estado', 'ultima_actualizacion']] = [new_status, datetime.now().strftime("%Y-%m-%d %H:%M")]
    conn.update(worksheet="maquinas", data=df_m)

# =========================================================
# 5. LOGIN (SIN PARPADEO)
# =========================================================
if not st.session_state.authenticated:
    st.title("🔐 Acceso al Sistema")
    c1, c2 = st.columns([1, 1])
    with c1:
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.button("Entrar", type="primary"):
            user = check_password(u, p)
            if user is not None:
                st.session_state.update({"authenticated": True, "user_role": user['role'], "username": user['username']})
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
    st.stop()

# =========================================================
# 6. DASHBOARD PRINCIPAL (DESPUÉS DEL LOGIN)
# =========================================================
st.sidebar.title(f"👤 {st.session_state.username}")
if st.sidebar.button("Cerrar Sesión"):
    st.session_state.authenticated = False
    st.rerun()

# --- SELECTOR DE MÁQUINAS ---
df_maq = get_data("maquinas")
lista_maquinas = df_maq['nombre'].tolist()
machine_selected = st.sidebar.selectbox("Seleccionar Máquina", lista_maquinas)

# --- PANEL DE CONTROL (CÁMARA) ---
st.sidebar.divider()
run_camera = st.sidebar.checkbox("📸 Activar Estación de Escaneo")
sensibilidad = st.sidebar.slider("Sensibilidad de Detección", 0, 100, 50)
zoom_level = st.sidebar.slider("Zoom Digital (%)", 0, 50, 0)

# =========================================================
# 7. LÓGICA DE CÁMARA (ESCUDO DE SEGURIDAD)
# =========================================================
foto = None 
if run_camera:
    st.header(f"📷 Escaneando: {machine_selected}")
    foto = st.camera_input("Capturar Test de Inyectores")

    if foto:
        st.session_state.bloquear_refresco = True
        with st.spinner("Procesando imagen..."):
            img_bytes = foto.getvalue()
            res = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
            
            if res is not None:
                try:
                    # Zoom y Procesamiento
                    if zoom_level > 0:
                        h, w = res.shape[:2]
                        m_h, m_w = int(h * (zoom_level / 200)), int(w * (zoom_level / 200))
                        res = res[m_h:h-m_h, m_w:w-m_w]
                    
                    # Simulación de resultado (Aquí integras tu image_processor)
                    salud_obtenida = np.random.uniform(85, 100) 
                    fallas_detectadas = int(np.random.randint(0, 10))
                    
                    # Guardar en Google Sheets
                    df_t = get_data("tests")
                    nuevo_test = pd.DataFrame([{
                        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "maquina": machine_selected,
                        "salud": round(salud_obtenida, 2),
                        "fallas": fallas_detectadas,
                        "operador": st.session_state.username
                    }])
                    df_upd = pd.concat([df_t, nuevo_test], ignore_index=True)
                    conn.update(worksheet="tests", data=df_upd)
                    
                    # Actualizar estado de la máquina
                    update_machine_status(machine_selected, "Operativa" if salud_obtenida > 90 else "Atención")
                    
                    st.success(f"✅ Test guardado: {salud_obtenida:.1f}% de salud.")
                    st.balloons()
                    time.sleep(2)
                    st.session_state.bloquear_refresco = False
                    st.rerun()
                except Exception as e:
                    st.error(f"Error en el análisis: {e}")
                    st.session_state.bloquear_refresco = False

# =========================================================
# 8. VISUALIZACIÓN DE ESTADOS (CARDS)
# =========================================================
st.divider()
st.subheader("🌐 Estado Actual de la Planta (Sincronizado)")

cols = st.columns(4)
for i, row in df_maq.iterrows():
    with cols[i % 4]:
        color = "green" if row['estado'] == "Operativa" else "orange" if row['estado'] == "Atención" else "red"
        st.markdown(f"""
            <div style="background-color: #1e2129; padding: 20px; border-radius: 10px; border-left: 5px solid {color}; margin-bottom: 10px;">
                <h4 style="margin:0;">{row['nombre']}</h4>
                <p style="margin:0; color: {color}; font-weight: bold;">{row['estado']}</p>
                <small>Último: {row['ultima_actualizacion']}</small>
            </div>
            """, unsafe_allow_html=True)
        if st.button(f"Reportar Falla", key=f"btn_{row['nombre']}"):
            update_machine_status(row['nombre'], "Falla")
            st.rerun()

# =========================================================
# 9. MOTOR DE SINCRONIZACIÓN (AUTO-REFRESH)
# =========================================================
if not run_camera and not st.session_state.get("bloquear_refresco", False):
    time.sleep(15)
    st.rerun()
