# =========================================
# DASHBOARD COMPLETO ADAPTADO
# - Google Sheets (st.secrets)
# - Mantiene estructura original
# - Listo para Streamlit Cloud
# =========================================

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
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# =========================================
# CONFIGURACIÓN GENERAL
# =========================================

st.set_page_config(page_title="Print Head Monitor", layout="wide")

# Fondo industrial
st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
    color: white;
}
</style>
""", unsafe_allow_html=True)

# =========================================
# GOOGLE SHEETS (SECRETS)
# =========================================

SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def connect_sheets():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=SCOPE
    )
    client = gspread.authorize(creds)
    return client.open("PrintHeadDB").sheet1

sheet = connect_sheets()

# =========================================
# FUNCIONES DB (SHEETS)
# =========================================

def save_test(machine, health, fails, path):
    sheet.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        machine,
        float(health),
        int(fails),
        path
    ])


def load_data():
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# =========================================
# AUTH
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
# UPLOAD + PROCESAMIENTO
# =========================================

st.title("🖨️ Monitor Inteligente")

file = st.file_uploader("Subir imagen", type=["jpg", "png", "jpeg"])

if file:
    image = Image.open(file)
    st.image(image, caption="Imagen cargada", use_column_width=True)

    if st.button("Procesar Imagen"):
        img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)

        health = np.mean(gray) / 255 * 100
        fails = int(np.sum(gray < 50))

        path = f"evidencia_{datetime.now().timestamp()}.jpg"
        cv2.imwrite(path, img)

        save_test(machine, health, fails, path)

        st.success(f"✅ Guardado {health:.2f}%")

# =========================================
# DASHBOARD
# =========================================

df = load_data()

if not df.empty:
    df.columns = ["timestamp", "machine", "health", "fails", "path"]

    st.subheader("📊 Vista General")
    st.dataframe(df)

    st.subheader("📈 Rendimiento por Máquina")
    chart = df.groupby("machine")["health"].mean()
    st.bar_chart(chart)

    st.subheader("📅 Últimos 7 días")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
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


