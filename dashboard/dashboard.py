import streamlit as st
import pandas as pd
import hashlib
import time
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# =========================================================
# 1. CONFIGURACIÓN Y CONEXIÓN (SOLUCIÓN AL ERROR PEM)
# =========================================================
st.set_page_config(page_title="Industrial Monitor v2", layout="wide")

class GSheetsDB:
    def __init__(self):
        try:
            # Leemos los secrets
            creds = st.secrets["connections"]["gsheets"].to_dict()
            
            # LIMPIEZA AUTOMÁTICA DE LLAVE (Soluciona el error Byte 92 / barra invertida)
            if "private_key" in creds:
                # Convertimos el texto literal \n en saltos de línea reales de PEM
                creds["private_key"] = creds["private_key"].replace("\\n", "\n").replace('\\n', '\n').strip()
            
            self.url = creds.get("spreadsheet")
            
            # Filtramos argumentos para la conexión service_account
            auth_args = {k: v for k, v in creds.items() if k not in ["spreadsheet", "type"]}
            
            # Establecemos la conexión
            self.conn = st.connection("gsheets", type=GSheetsConnection, **auth_args)
        except Exception as e:
            st.error(f"❌ Error crítico de conexión: {e}")
            self.conn = None

    def safe_read(self, sheet_name):
        if not self.conn: return pd.DataFrame()
        try:
            # Leemos la pestaña asegurando datos frescos (ttl=0)
            return self.conn.read(spreadsheet=self.url, worksheet=sheet_name, ttl=0)
        except Exception as e:
            st.error(f"Error al leer '{sheet_name}': {e}")
            return pd.DataFrame()

    def update_sheet(self, df, sheet_name):
        if not self.conn: return False
        try:
            # Usamos el método oficial .update() de la librería
            self.conn.update(spreadsheet=self.url, worksheet=sheet_name, data=df)
            return True
        except Exception as e:
            st.error(f"Error al guardar en '{sheet_name}': {e}")
            return False

# INICIALIZACIÓN GLOBAL (Evita el NameError: 'db' is not defined)
db = GSheetsDB()

# =========================================================
# 2. LÓGICA DE LOGIN (Usando tus columnas confirmadas)
# =========================================================
class GSheetsDB:
    def __init__(self):
        try:
            # 1. Obtenemos los secretos crudos
            creds = st.secrets["connections"]["gsheets"].to_dict()
            
            # 2. LIMPIEZA DE LLAVE (Solución al error PEM / Byte 92)
            if "private_key" in creds:
                p_key = creds["private_key"].replace("\\n", "\n").replace('\\n', '\n').strip()
            else:
                st.error("No se encontró 'private_key' en los Secrets.")
                return

            # 3. CONSTRUCCIÓN DEL DICCIONARIO DE AUTENTICACIÓN
            # Aquí definimos EXACTAMENTE qué campos enviar a Google
            # Esto evita el error de "unexpected keyword argument 'project_id'"
            service_account_info = {
                "type": creds.get("type", "service_account"),
                "project_id": creds.get("project_id"),
                "private_key_id": creds.get("private_key_id"),
                "private_key": p_key,
                "client_email": creds.get("client_email"),
                "client_id": creds.get("client_id"),
                "auth_uri": creds.get("auth_uri"),
                "token_uri": creds.get("token_uri"),
                "auth_provider_x509_cert_url": creds.get("auth_provider_x509_cert_url"),
                "client_x509_cert_url": creds.get("client_x509_cert_url")
            }
            
            # 4. CONEXIÓN USANDO EL DICCIONARIO FILTRADO
            # spreadsheet se pasa por fuera, las credenciales por dentro
            self.url = creds.get("spreadsheet")
            self.conn = st.connection(
                "gsheets", 
                type=GSheetsConnection, 
                service_account_info=service_account_info
            )
            
            st.success("✅ Sistema conectado a la Nube")
            
        except Exception as e:
            st.error(f"❌ Error de configuración: {e}")
            self.conn = None

    def safe_read(self, sheet_name):
        if not self.conn: return pd.DataFrame()
        try:
            # Forzamos la lectura de la pestaña específica
            return self.conn.read(spreadsheet=self.url, worksheet=sheet_name, ttl=0)
        except Exception as e:
            st.error(f"Error al leer '{sheet_name}': {e}")
            return pd.DataFrame()

# Inicialización
db = GSheetsDB()

# =========================================================
# 3. INTERFAZ DE USUARIO
# =========================================================
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso al Sistema")
    _, c2, _ = st.columns([1, 1, 1])
    with c2:
        u = st.text_input("Usuario")
        p = st.text_input("PIN / Contraseña", type="password")
        if st.button("INGRESAR"):
            rol = check_login(u, p)
            if rol:
                st.session_state.auth = True
                st.session_state.user = u
                st.session_state.rol = rol
                st.rerun()
            else:
                st.error("Credenciales incorrectas o problema de conexión.")
    st.stop()

# Si llegamos aquí, el usuario está logueado
st.success(f"Bienvenido {st.session_state.user} ({st.session_state.rol})")

if st.button("Cerrar Sesión"):
    st.session_state.auth = False
    st.rerun()
