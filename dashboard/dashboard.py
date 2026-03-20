import streamlit as st
import pandas as pd
import numpy as np
import cv2
from PIL import Image
from datetime import datetime
import hashlib

from streamlit_gsheets import GSheetsConnection

# =========================================
# CONFIG
# =========================================
st.set_page_config(layout="wide")

st.markdown("""
<style>
.stApp {
    background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
    color: white;
}
</style>
""", unsafe_allow_html=True)

# =========================================
# CONNECTION
# =========================================
conn = st.connection("gsheets", type=GSheetsConnection)

def load(sheet):
    try:
        return conn.read(worksheet=sheet)
    except:
        return pd.DataFrame()

def save(sheet, df):
    conn.update(worksheet=sheet, data=df)

# =========================================
# LOGIN REAL DESDE SHEETS
# =========================================
users = load("usuarios")

if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Login Industrial")

    u = st.text_input("Usuario")
    p = st.text_input("Contraseña", type="password")

    if st.button("Entrar"):
        hashed = hashlib.sha256(p.encode()).hexdigest()

        user = users[
            (users["usuario"] == u) &
            (users["contraseña"] == hashed)
        ]

        if not user.empty:
            st.session_state.auth = True
            st.session_state.user = u
            st.success("Acceso concedido")
            st.rerun()
        else:
            st.error("Credenciales incorrectas")

    st.stop()

# =========================================
# DATA
# =========================================
df_tests = load("tests")
df_maquinas = load("maquinas")

# =========================================
# SIDEBAR
# =========================================
st.sidebar.title("🏭 Control")

machine = st.sidebar.selectbox(
    "Máquina",
    df_maquinas["nombre"].unique() if not df_maquinas.empty else ["M1"]
)

# =========================================
# KPIs
# =========================================
st.title("📊 Monitor Industrial")

if not df_tests.empty:
    col1, col2, col3 = st.columns(3)

    col1.metric("Total Tests", len(df_tests))
    col2.metric("Salud Promedio", f"{df_tests['salud'].mean():.2f}%")

    last = df_tests.iloc[-1]["salud"]
    col3.metric("Último Test", f"{last:.2f}%")

# =========================================
# PROCESAMIENTO
# =========================================
st.subheader("📷 Análisis de Cabezal")

file = st.file_uploader("Subir imagen")

if file:
    img = Image.open(file)
    st.image(img, use_column_width=True)

    if st.button("Analizar"):
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)

        health = np.mean(img_cv) / 255 * 100

        # ESTADO INTELIGENTE
        if health > 80:
            estado = "OK"
        elif health > 50:
            estado = "ALERTA"
        else:
            estado = "CRITICO"

        # GUARDAR TEST
        new_test = pd.DataFrame([{
            "fecha": datetime.now(),
            "maquina": machine,
            "salud": health,
            "evidencia_url": "local"
        }])

        df_tests = pd.concat([df_tests, new_test], ignore_index=True)
        save("tests", df_tests)

        # ACTUALIZAR MAQUINA
        df_maquinas.loc[df_maquinas["nombre"] == machine, "estado"] = estado
        df_maquinas.loc[df_maquinas["nombre"] == machine, "ultima_actualizacion"] = datetime.now()
        df_maquinas.loc[df_maquinas["nombre"] == machine, "operador"] = st.session_state.user

        save("maquinas", df_maquinas)

        st.success(f"Estado: {estado} ({health:.2f}%)")

# =========================================
# HISTÓRICO
# =========================================
st.subheader("📈 Histórico")

if not df_tests.empty:
    hist = df_tests[df_tests["maquina"] == machine]

    if not hist.empty:
        st.line_chart(hist.set_index("fecha")["salud"])

# =========================================
# ESTADO DE MAQUINAS
# =========================================
st.subheader("🏭 Estado General")

if not df_maquinas.empty:
    st.dataframe(df_maquinas)

