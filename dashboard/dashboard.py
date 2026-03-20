import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# 👇 SOLO credenciales limpias
creds_dict = st.secrets["gcp_service_account"]

creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

# 👇 URL separada
spreadsheet = client.open_by_url(st.secrets["gsheets"]["spreadsheet"])

sheet = spreadsheet.worksheet("tests")

data = sheet.get_all_records()
df = pd.DataFrame(data)

st.write(df)

st.write(df)
