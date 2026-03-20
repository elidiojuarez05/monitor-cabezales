import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

# 🔑 SCOPES
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# 🔐 CREDENCIALES DESDE STREAMLIT
creds_dict = st.secrets["connections"]["gsheets"]

creds = Credentials.from_service_account_info(creds_dict, scopes=scope)

client = gspread.authorize(creds)

# 📄 ABRIR SHEET
spreadsheet = client.open_by_url(creds_dict["spreadsheet"])

# 📊 LEER HOJA
sheet = spreadsheet.worksheet("tests")
data = sheet.get_all_records()

df = pd.DataFrame(data)

st.write(df)
