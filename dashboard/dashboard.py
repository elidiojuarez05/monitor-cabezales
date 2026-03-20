import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

st.title("📊 Dashboard Monitor")

# Scopes
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Credenciales desde secrets
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=scope
)

client = gspread.authorize(creds)

# Abrir spreadsheet
spreadsheet = client.open_by_url(
    st.secrets["connections"]["gsheets"]["spreadsheet"]
)

# Leer hoja
sheet = spreadsheet.worksheet("tests")  # ⚠️ cambia si tu hoja se llama distinto

data = sheet.get_all_records()

df = pd.DataFrame(data)

# Mostrar
st.dataframe(df)
