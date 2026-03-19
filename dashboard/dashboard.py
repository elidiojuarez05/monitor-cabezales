import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import hashlib
import time
from datetime import datetime
from PIL import Image
import numpy as np
import cv2
import os

# =========================================================
# CONFIGURACIÓN VISUAL INDUSTRIAL (DARK TECH)
# =========================================================
st.set_page_config(page_title="Industrial Monitor v2", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0d1117; color: #c9d1d9; }
    header {visibility: hidden;}
    .main-header {
        background: linear-gradient(90deg, #161b22 0%, #0d1117 100%);
        padding: 20px; border-radius: 10px; border-left: 5px solid #58a6ff;
        margin-bottom: 25px; box-shadow: 0 4px 12px rgba(0,0,0,0.5);
    }
    div[data-testid="stMetricValue"] { color: #58a6ff; font-family: 'Courier New', monospace; }
    .stButton>button {
        width: 100%; border-radius: 5px; background-color: #21262d; 
        color: #c9d1d9; border: 1px solid #30363d; transition: 0.3s;
    }
    .stButton>button:hover { border-color: #58a6ff; color: #58a6ff; background-color: #30363d; }
    .card {
        background-color: #161b22; padding: 20px; border-radius: 8px;
        border: 1px solid #30363d; margin-bottom: 15px;
    }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# GESTOR DE DATOS (CONEXIÓN SEGURA)
# =========================================================
# Reemplaza tu clase GSheetsDB o la parte de lectura con esto:
class GSheetsDB:
    def __init__(self):
        self.conn = st.connection("gsheets", type=GSheetsConnection)

    def safe_read(self, sheet_name):
        try:
            # Intentamos leer la pestaña
            return self.conn.read(worksheet=sheet_name, ttl="10s")
        except Exception as e:
            # Si da error 401, lo capturamos para que la app no se detenga
            if "401" in str(e):
                st.error(f"🚫 Error de Autorización (401): No tengo permiso para leer la pestaña '{sheet_name}'.")
                st.info("Asegúrate de que la hoja sea pública o que las credenciales en 'Secrets' sean correctas.")
            else:
                st.error(f"Error inesperado: {e}")
            return pd.DataFrame()

db = GSheetsDB()

# =========================================================
# LÓGICA DE NEGOCIO
# =========================================================

def check_login(user, pwd):
    df = db.safe_read("usuarios")
    
    if df.empty:
        st.error("La hoja de 'usuarios' está vacía o no se pudo leer.")
        return False

    # --- DIAGNÓSTICO INTELIGENTE ---
    # Limpiamos los nombres de las columnas para evitar errores de espacios o mayúsculas
    df.columns = [str(c).strip().lower() for c in df.columns]
    
    # Mostramos en pantalla qué columnas encontró realmente (Solo para depurar)
    # st.write("Columnas detectadas (limpias):", list(df.columns))

    # Verificamos si después de limpiar existe la columna 'usuario'
    if 'usuario' not in df.columns:
        st.error(f"No encontré la columna 'usuario'. Columnas actuales: {list(df.columns)}")
        return False

    # --- PROCESO DE LOGIN ---
    user_input = str(user).strip().lower()
    
    # Buscamos en la columna ya normalizada
    match = df[df['usuario'].astype(str).str.strip().lower() == user_input]
    
    if not match.empty:
        # Generamos el hash de la contraseña ingresada
        h_input = hashlib.sha256(pwd.strip().encode()).hexdigest()
        
        # Obtenemos la contraseña de la base de datos (columna 'contraseña' o 'contrasena')
        col_pass = 'contraseña' if 'contraseña' in df.columns else 'contrasena'
        db_pwd = str(match.iloc[0][col_pass]).strip()
        
        if db_pwd == h_input:
            return match.iloc[0]['rol']
    
    return False
# =========================================================
# INTERFAZ DE USUARIO
# =========================================================

if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.markdown("<div class='main-header'><h1>🔐 Acceso al Sistema Industrial</h1></div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1, 1])
    with c2:
        u = st.text_input("ID de Operador")
        p = st.text_input("PIN", type="password")
        if st.button("AUTENTICAR"):
            rol = check_login(u, p)
            if rol:
                st.session_state.auth = True
                st.session_state.user = u
                st.session_state.rol = rol
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
    st.stop()

# --- DASHBOARD PRINCIPAL ---
st.markdown(f"""
    <div class='main-header'>
        <h1 style='margin:0;'>🏭 Panel de Control Planta</h1>
        <small style='color:#8b949e;'>Usuario: {st.session_state.user} | Rol: {st.session_state.rol}</small>
    </div>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/554/554866.png", width=100)
    st.title("Opciones")
    menu = st.radio("Navegación", ["Monitor General", "Cargar Test", "Administración"])
    if st.button("Cerrar Sesión"):
        st.session_state.auth = False
        st.rerun()

# --- MÓDULO 1: MONITOR ---
if menu == "Monitor General":
    df_m = db.safe_read("maquinas")
    df_t = db.safe_read("tests")
    
    if not df_m.empty:
        cols = st.columns(3)
        for i, (idx, row) in enumerate(df_m.iterrows()):
            with cols[i % 3]:
                st.markdown(f"""
                <div class='card'>
                    <h3 style='margin-top:0; color:#58a6ff;'>{row['nombre']}</h3>
                    <p><b>Estado:</b> {row['estado']}</p>
                    <small>Act: {row['ultima_actulizacion']}</small><br>
                    <small>Op: {row['operador']}</small>
                </div>
                """, unsafe_allow_html=True)
                
                # Mostrar último test si existe
                if not df_t.empty:
                    last_test = df_t[df_t['maquina'] == row['nombre']].sort_values(by='fecha', ascending=False)
                    if not last_test.empty:
                        val = float(last_test.iloc[0]['salud'])
                        st.metric("Salud", f"{val}%", delta=f"{last_test.iloc[0]['fallas']} fallas", delta_color="inverse")

# --- MÓDULO 2: CARGAR TEST ---
elif menu == "Cargar Test":
    df_m = db.safe_read("maquinas")
    maquina = st.selectbox("Seleccione Máquina", df_m['nombre'] if not df_m.empty else [])
    
    img_file = st.camera_input("Capturar Test")
    if img_file:
        with st.spinner("Sincronizando con Google Sheets..."):
            # Aquí iría tu lógica de procesamiento de imagen
            # Simulamos resultados:
            salud_sim = 95.0
            fallas_sim = 4
            
            # 1. Guardar Test
            df_t = db.safe_read("tests")
            new_t = pd.DataFrame([{
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "maquina": maquina,
                "salud": salud_sim,
                "fallas": fallas_sim,
                "evidencias_url": "N/A"
            }])
            df_t_updated = pd.concat([df_t, new_t], ignore_index=True)
            db.update_sheet(df_t_updated, "tests")
            
            # 2. Actualizar Maquina
            df_m.loc[df_m['nombre'] == maquina, 'estado'] = "Operativa"
            df_m.loc[df_m['nombre'] == maquina, 'operador'] = st.session_state.user
            df_m.loc[df_m['nombre'] == maquina, 'ultima_actulizacion'] = datetime.now().strftime("%Y-%m-%d %H:%M")
            db.update_sheet(df_m, "maquinas")
            
            st.success("✅ Test registrado y base de datos actualizada.")
            time.sleep(2)
            st.rerun()

# --- MÓDULO 3: ADMIN ---
elif menu == "Administración":
    if st.session_state.rol != "admin":
        st.warning("Acceso restringido solo para administradores.")
    else:
        st.subheader("Gestión de Usuarios")
        df_u = db.safe_read("usuarios")
        st.dataframe(df_u, use_container_width=True)
        
        st.subheader("Estado de Máquinas")
        df_m = db.safe_read("maquinas")
        st.data_editor(df_m, key="editor_m")
        if st.button("Guardar Cambios"):
            db.update_sheet(st.session_state.editor_m, "maquinas")
            st.success("Cambios guardados.")
