from streamlit_gsheets import GSheetsConnection
import streamlit as st

conn = st.connection("gsheets", type=GSheetsConnection)

df = conn.read()

st.write(df)

