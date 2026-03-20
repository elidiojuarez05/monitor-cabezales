# ===============================
# DASHBOARD MEJORADO
# - Base de datos migrada a Google Sheets
# - Fondo más profesional
# - Estructura original respetada
# ===============================

import streamlit as st
import pandas as pd
import numpy as np
import cv2
import os
import hashlib
from datetime import datetime
from PIL import Image
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ===============================
# CONFIGURACIÓN GOOGLE SHEETS
# ===============================

SCOPE = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

CREDENTIALS_FILE = "credentials.json"  # Debes colocar tu JSON aquí
SHEET_NAME = "PrintHeadDB"

@st.cache_resource
def connect_sheets():
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    return sheet

sheet = connect_sheets()

# ===============================
# ESTILO PROFESIONAL INDUSTRIAL
# ===============================

def set_background():
    st.markdown("""
        <style>
        .stApp {
            background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
            color: white;
        }
        .block-container {
            padding-top: 2rem;
        }
        </style>
    """, unsafe_allow_html=True)

set_background()

# ===============================
# FUNCIONES GOOGLE SHEETS
# ===============================

def save_test(machine, health, fails, path):
    sheet.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        machine,
        health,
        fails,
        path
    ])


def get_data():
    data = sheet.get_all_records()
    return pd.DataFrame(data)

# ===============================
# AUTH SIMPLE (SIN SQLITE)
# ===============================

USERS = {
    "admin": hashlib.sha256("system123".encode()).hexdigest()
}

if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Login")
    u = st.text_input("Usuario")
    p = st.text_input("Password", type="password")

    if st.button("Entrar"):
        if u in USERS and USERS[u] == hashlib.sha256(p.encode()).hexdigest():
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Credenciales incorrectas")
    st.stop()

# ===============================
# HEADER
# ===============================

st.title("🖨️ Monitor Industrial de Cabezales")

# ===============================
# SIDEBAR
# ===============================

machine = st.sidebar.selectbox("Seleccionar Máquina", ["M1", "M2", "M3"])
sensibilidad = st.sidebar.slider("Sensibilidad", 0.01, 0.2, 0.05)

# ===============================
# SUBIR IMAGEN
# ===============================

file = st.file_uploader("Subir imagen", type=["jpg", "png"])

if file:
    image = Image.open(file)
    st.image(image, caption="Imagen cargada")

    if st.button("Procesar"):
        img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        thresh = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)[1]

        health = np.mean(thresh) / 255 * 100
        fails = int(np.sum(thresh == 0))

        path = f"evidencia_{datetime.now().timestamp()}.jpg"
        cv2.imwrite(path, img)

        save_test(machine, health, fails, path)

        st.success(f"Guardado: {health:.2f}%")

# ===============================
# DASHBOARD
# ===============================

df = get_data()

if not df.empty:
    st.subheader("📊 Historial")
    st.dataframe(df)

    st.subheader("📈 Rendimiento")
    chart = df.groupby("machine")["health"].mean()
    st.bar_chart(chart)
else:
    st.info("Sin datos aún")

# ===============================
# AUTO REFRESH
# ===============================

import time

time.sleep(10)
st.rerun()

