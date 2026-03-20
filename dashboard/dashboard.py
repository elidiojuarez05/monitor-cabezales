# =========================================
# DASHBOARD COMPLETO (STREAMLIT CONNECTIONS)
# - Google Sheets con st.connection
# - Sin gspread ni google-auth
# - Listo para Streamlit Cloud
# =========================================

import streamlit as st
import pandas as pd
import numpy as np
import cv2
from PIL import Image
from datetime import datetime, timedelta
import hashlib
import time

# =========================================
# CONFIG
# =========================================

st.set_page_config(page_title="Print Head Monitor", layout="wide")

st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
    color: white;
}
</style>
""", unsafe_allow_html=True)

# =========================================
# CONNECTION GOOGLE SHEETS
# =========================================

conn = st.connection("gsheets", type="gsheets")

@st.cache_data(ttl=5)
def load_data():
    try:
        return conn.read()
    except:
        return pd.DataFrame()


def save_data(df):
    conn.update(data=df)

# =========================================
# AUTH SIMPLE
# =========================================

USERS = {
    "admin": hashlib.sha256("system123".encode()).hexdigest()
}

if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso")
    u = st.text_input("Usuario")
    p = st.text_input("Contraseña", type="password")

    if st.button("Entrar"):
        if u in USERS and USERS[u] == hashlib.sha256(p.encode()).hexdigest():
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Credenciales incorrectas")
    st.stop()

# =========================================
# SIDEBAR
# =========================================

st.sidebar.title("⚙️ Configuración")
machine = st.sidebar.selectbox("Máquina", ["M1", "M2", "M3"])
sensibilidad = st.sidebar.slider("Sensibilidad", 0.01, 0.2, 0.05)

# =========================================
# PROCESAMIENTO
# =========================================

st.title("🖨️ Monitor Inteligente")

file = st.file_uploader("Subir imagen", type=["jpg", "png", "jpeg"])

if file:
    image = Image.open(file)
    st.image(image, caption="Imagen cargada", use_column_width=True)

    if st.button("Procesar Imagen"):
        img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        health = np.mean(gray) / 255 * 100
        fails = int(np.sum(gray < 50))

        df = load_data()

        new_row = pd.DataFrame([{
            "timestamp": datetime.now(),
            "machine": machine,
            "health": health,
            "fails": fails
        }])

        df = pd.concat([df, new_row], ignore_index=True)

        save_data(df)

        st.success(f"✅ Guardado {health:.2f}%")

# =========================================
# DASHBOARD
# =========================================

df = load_data()

if not df.empty:
    st.subheader("📊 Vista General")
    st.dataframe(df)

    if "machine" in df.columns:
        st.subheader("📈 Rendimiento por Máquina")
        chart = df.groupby("machine")["health"].mean()
        st.bar_chart(chart)

    if "timestamp" in df.columns:
        st.subheader("📅 Últimos 7 días")
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        recent = df[df["timestamp"] > datetime.now() - timedelta(days=7)]

        if not recent.empty:
            st.line_chart(recent.set_index("timestamp")["health"])
else:
    st.info("Sin datos aún")

# =========================================
# AUTO REFRESH
# =========================================

if "pause" not in st.session_state:
    st.session_state.pause = False

if not st.session_state.pause:
    time.sleep(10)
    st.rerun()


