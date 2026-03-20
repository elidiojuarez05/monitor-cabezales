import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="Monitor Industrial", layout="wide")

st.title("🏭 Monitor de Cabezales")

# =========================
# 🔐 CONEXIÓN GOOGLE SHEETS
# =========================
@st.cache_resource
def connect():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scope
    )

    client = gspread.authorize(creds)

    spreadsheet = client.open_by_url(
        st.secrets["connections"]["gsheets"]["spreadsheet"]
    )

    return spreadsheet

spreadsheet = connect()
sheet = spreadsheet.worksheet("tests")  # cambia nombre si es necesario

# =========================
# 📥 CARGA DE DATOS
# =========================
@st.cache_data(ttl=5)
def load_data():
    data = sheet.get_all_records()
    return pd.DataFrame(data)

df = load_data()

# =========================
# 🧠 PROCESAMIENTO
# =========================
if not df.empty:
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")

    total = len(df)
    fallas = len(df[df["estado"] == "Falla"])
    ok = len(df[df["estado"] == "OK"])

    porcentaje_fallas = (fallas / total) * 100 if total > 0 else 0
else:
    total = fallas = ok = porcentaje_fallas = 0

# =========================
# 📊 DASHBOARD
# =========================
col1, col2, col3, col4 = st.columns(4)

col1.metric("Total registros", total)
col2.metric("OK", ok)
col3.metric("Fallas", fallas)
col4.metric("% Fallas", f"{porcentaje_fallas:.2f}%")

st.divider()

# =========================
# 📈 GRÁFICA
# =========================
if not df.empty:
    st.subheader("📊 Estado de equipos")
    st.bar_chart(df["estado"].value_counts())

# =========================
# 📋 TABLA
# =========================
st.subheader("📋 Registros")

if df.empty:
    st.warning("No hay datos")
else:
    st.dataframe(df, use_container_width=True)

# =========================
# ➕ CREAR REGISTRO
# =========================
st.subheader("➕ Nuevo registro")

with st.form("crear"):
    fecha = st.date_input("Fecha", datetime.now())
    equipo = st.text_input("Equipo")
    estado = st.selectbox("Estado", ["OK", "Falla"])

    guardar = st.form_submit_button("Guardar")

    if guardar:
        sheet.append_row([str(fecha), equipo, estado])
        st.success("Registro agregado")
        st.cache_data.clear()

# =========================
# ✏️ EDITAR / ELIMINAR
# =========================
st.subheader("✏️ Editar / Eliminar")

if not df.empty:
    fila = st.number_input("Selecciona índice", min_value=0, max_value=len(df)-1)

    if st.button("Eliminar"):
        sheet.delete_rows(fila + 2)  # +2 por header
        st.success("Eliminado")
        st.cache_data.clear()

    if st.button("Editar estado"):
        nuevo_estado = st.selectbox("Nuevo estado", ["OK", "Falla"])
        col_estado = df.columns.get_loc("estado") + 1

        sheet.update_cell(fila + 2, col_estado, nuevo_estado)
        st.success("Actualizado")
        st.cache_data.clear()
