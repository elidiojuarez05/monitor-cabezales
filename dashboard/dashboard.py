import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import hashlib
import time
from datetime import datetime

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
class GSheetsDB:
    def __init__(self):
        try:
            # Conexión directa usando st.secrets
            self.conn = st.connection("gsheets", type=GSheetsConnection)
        except Exception as e:
            st.error(f"❌ Error de conexión: {e}")

    def safe_read(self, sheet_name):
        try:
            # ttl=0 asegura que traiga datos frescos del Excel
            return self.conn.read(worksheet=sheet_name, ttl=0)
        except Exception as e:
            st.error(f"Error al leer pestaña '{sheet_name}': {e}")
            return pd.DataFrame()

    def update_sheet(self, df, sheet_name):
        try:
            # Método oficial para escribir en la hoja
            self.conn.update(worksheet=sheet_name, data=df)
            return True
        except Exception as e:
            st.error(f"Error al guardar en '{sheet_name}': {e}")
            return False

db = GSheetsDB()

# =========================================================
# LÓGICA DE LOGIN
# =========================================================
def check_login(user, pwd):
    df = db.safe_read("usuarios")
    
    if df.empty:
        st.error("No se pudo acceder a la tabla de usuarios.")
        return False

    # Normalización de columnas para evitar errores de mayúsculas/espacios
    df.columns = [str(c).strip().lower() for c in df.columns]
    
    user_input = str(user).strip().lower()
    # Buscamos al usuario
    match = df[df['usuario'].astype(str).str.strip().lower() == user_input]
    
    if not match.empty:
        # Verificamos contraseña (soporta 'contraseña' o 'contrasena')
        col_pass = 'contraseña' if 'contraseña' in df.columns else 'contrasena'
        db_pwd = str(match.iloc[0][col_pass]).strip()
        
        h_input = hashlib.sha256(pwd.strip().encode()).hexdigest()
        
        if db_pwd == h_input:
            return str(match.iloc[0]['rol']).lower()
    
    return False

# =========================================================
# INTERFAZ Y NAVEGACIÓN
# =========================================================
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.markdown("<div class='main-header'><h1>🔐 Acceso al Sistema Industrial</h1></div>", unsafe_allow_html=True)
    _, c2, _ = st.columns([1, 1, 1])
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
                st.error("Credenciales incorrectas o usuario no encontrado.")
    st.stop()

# Dashboard Principal
st.markdown(f"""
    <div class='main-header'>
        <h1 style='margin:0;'>🏭 Panel de Control Planta</h1>
        <small style='color:#8b949e;'>Usuario: {st.session_state.user} | Rol: {st.session_state.rol.upper()}</small>
    </div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("Menú")
    menu = st.radio("Navegación", ["Monitor General", "Cargar Test", "Administración"])
    if st.button("Cerrar Sesión"):
        st.session_state.auth = False
        st.rerun()

# --- MONITOR GENERAL ---
if menu == "Monitor General":
    df_m = db.safe_read("maquinas")
    df_t = db.safe_read("tests")
    
    if not df_m.empty:
        cols = st.columns(3)
        for i, (idx, row) in enumerate(df_m.iterrows()):
            with cols[i % 3]:
                st.markdown(f"""
                <div class='card'>
                    <h3 style='margin-top:0; color:#58a6ff;'>{row.get('nombre', 'N/A')}</h3>
                    <p><b>Estado:</b> {row.get('estado', 'Desconocido')}</p>
                    <small>Act: {row.get('ultima_actualizacion', 'N/A')}</small>
                </div>
                """, unsafe_allow_html=True)

# --- CARGAR TEST ---
elif menu == "Cargar Test":
    df_m = db.safe_read("maquinas")
    if not df_m.empty:
        maquina = st.selectbox("Seleccione Máquina", df_m['nombre'].tolist())
        img_file = st.camera_input("Capturar Test")
        
        if img_file:
            with st.spinner("Actualizando registros..."):
                # Simulación de procesamiento
                salud_sim, fallas_sim = 98.5, 2
                fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M")
                
                # Actualizar Maquinas (Dataframe local y luego nube)
                df_m.loc[df_m['nombre'] == maquina, 'estado'] = "Operativa"
                df_m.loc[df_m['nombre'] == maquina, 'ultima_actualizacion'] = fecha_actual
                
                if db.update_sheet(df_m, "maquinas"):
                    st.success("✅ Datos sincronizados.")
                    time.sleep(1)
                    st.rerun()

# --- ADMINISTRACIÓN ---
elif menu == "Administración":
    if st.session_state.rol != "admin":
        st.warning("Acceso restringido.")
    else:
        st.subheader("Gestión de Usuarios")
        df_u = db.safe_read("usuarios")
        st.dataframe(df_u, use_container_width=True)
