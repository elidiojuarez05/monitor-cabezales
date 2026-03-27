import sys
import os
import hashlib
import numpy as np
import cv2
import pandas as pd
import streamlit as st
from streamlit_cropper import st_cropper
from PIL import Image
from datetime import datetime, timedelta
import time
import json
import base64
from sqlalchemy import text
from config import MACHINE_CONFIGS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
from backend.image_processor import process_standard_manual

# =========================================================
# 1. CONFIGURACIÓN DE PÁGINA (PRIMER EL PRIMER COMANDO)
# =========================================================
st.set_page_config(page_title="Print Head Monitor", layout="wide")
# --- ESTILO VISUAL INDUSTRIAL ---
st.markdown("""
    <style>

        /* Color de los Tabs (Pestañas) */
        .stTabs [data-baseweb="tab-list"] {
            background-color: #1b263b;
            border-radius: 10px 10px 0 0;
            padding: 5px;
        }

        /* Color de las tarjetas de máquinas */
        div[data-testid="stMetricValue"] {
            background-color: #1b263b;
            border-radius: 10px;
            padding: 10px;
            border: 1px solid #415a77;
        }

        /* Texto de los headers */
        h1, h2, h3 {
            color: #778da9 !important;
        }

        /* Sidebar con tono más oscuro */
        [data-testid="stSidebar"] {
            background-color: #0b132b;
        }
    </style>
""", unsafe_allow_html=True)





# =========================================================
# 2. CONFIGURACIÓN DE RUTAS Y PATHS
# =========================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    backend_dir = os.path.join(sys._MEIPASS, "backend")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(BASE_DIR)
    backend_dir = os.path.join(project_root, "backend")

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

EVIDENCIAS_PATH = os.path.join(BASE_DIR, "evidencias")
REPORTES_PATH = os.path.join(BASE_DIR, "reportes")

for path in [EVIDENCIAS_PATH, REPORTES_PATH]:
    if not os.path.exists(path):
        os.makedirs(path)

# =========================================================
# 3. IMPORTS DE MÓDULOS PROPIOS Y CONEXIÓN A POSTGRES
# =========================================================
try:
    import image_processor
    from config import MACHINE_CONFIGS
    import crud 
except ImportError as e:
    st.error(f"Error crítico de importación: {e}")
    st.stop()

# --- CONEXIÓN NATIVA A POSTGRESQL ---
conn = st.connection("postgresql", type="sql")
# --- PARCHE DE EMERGENCIA PARA LA BASE DE DATOS ---
# Este bloque detecta qué columnas faltan y las crea automáticamente
def patch_database():
    # Definimos cada columna con su tipo
    columnas = {
        "health_map": "TEXT",
        "missing_nodes": "INTEGER",
        "evidence_path": "TEXT"
    }
    
    for nombre_col, tipo_col in columnas.items():
        try:
            # Ejecutamos cada una por separado en su propio bloque
            with conn.session as session:
                session.execute(text(f"ALTER TABLE test_results ADD COLUMN IF NOT EXISTS {nombre_col} {tipo_col};"))
                session.commit()
        except Exception:
            # Si ya existe (Error 42701), simplemente pasamos a la siguiente
            pass
            
patch_database()
    

def query_db(sql_string, params=None):
    try:
        with conn.session as session:
            result = session.execute(text(sql_string), params or {})
            df = pd.DataFrame(result.fetchall())
            if not df.empty:
                df.columns = result.keys()
                # Normalizar columnas a minúsculas
                df.columns = [c.lower() for c in df.columns]
            return df
    except Exception as e:
        return pd.DataFrame()

def commit_db(sql_string, params=None):
    try:
        with conn.session as session:
            session.execute(text(sql_string), params or {})
            session.commit()
        return True
    except Exception as e:
        st.error(f"Error de escritura: {e}")
        return False

# --- PARCHE: Asegurar que las columnas existen en Postgres ---
commit_db("ALTER TABLE test_results ADD COLUMN IF NOT EXISTS health_map TEXT;")
commit_db("ALTER TABLE test_results ADD COLUMN IF NOT EXISTS missing_nodes INTEGER;")

def create_tables_if_not_exist():
    # Tabla Resultados
    commit_db("""
    CREATE TABLE IF NOT EXISTS test_results (
        id SERIAL PRIMARY KEY,
        machine_name VARCHAR(100),
        health_score FLOAT,
        missing_nodes INTEGER,
        health_map TEXT,
        evidence_path TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    # Tabla Usuarios
    commit_db("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) UNIQUE,
        password TEXT,
        role VARCHAR(20)
    );
    """)
    # Tabla Estados Sincronizados
    commit_db("""
    CREATE TABLE IF NOT EXISTS estados_maquinas (
        machine_name VARCHAR(50) PRIMARY KEY,
        estado VARCHAR(50) NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Crear admin por defecto si no hay usuarios
    res = query_db("SELECT id FROM usuarios LIMIT 1")
    if res.empty:
        h = hashlib.sha256("admin123".encode()).hexdigest()
        commit_db("INSERT INTO usuarios (username, password, role) VALUES ('admin', :p, 'admin')", {"p": h})

create_tables_if_not_exist()

# =========================================================
# 4. INICIALIZACIÓN DE SESSION STATE Y VARIABLES GLOBALES
# =========================================================
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'user_role' not in st.session_state: st.session_state.user_role = None
if 'username' not in st.session_state: st.session_state.username = None
if 'machine_selected' not in st.session_state: st.session_state.machine_selected = list(MACHINE_CONFIGS.keys())[0]

if 'estados_maquinas' not in st.session_state: st.session_state.estados_maquinas = {name: "Operativa" for name in MACHINE_CONFIGS.keys()}
if 'indice_carrusel' not in st.session_state: st.session_state.indice_carrusel = 0

if 'mapa_actual' not in st.session_state: st.session_state.mapa_actual = None
if 'img_resultado' not in st.session_state: st.session_state.img_resultado = None
if 'recortes' not in st.session_state: st.session_state.recortes = {}

if 'bloquear_refresco' not in st.session_state: st.session_state.bloquear_refresco = False
if 'mostrar_descarga_pdf' not in st.session_state: st.session_state.mostrar_descarga_pdf = False
if 'archivo_pdf_listo' not in st.session_state: st.session_state.archivo_pdf_listo = None

run_camera = False

# =========================================================
# 5. FUNCIONES DE APOYO Y BASE DE DATOS (MIGRADAS A POSTGRES)
# =========================================================
class MockObj:
    """Clase auxiliar para mantener la misma sintaxis orientada a objetos (user.role, test.timestamp)"""
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

def init_admin_user():
    admin_user = "admin"
    hashed_pw = hashlib.sha256("system123".encode()).hexdigest()
    res = query_db("SELECT * FROM usuarios WHERE username = :u", {"u": admin_user})
    if res.empty:
        commit_db("INSERT INTO usuarios (username, password, role) VALUES (:u, :p, :r)", 
                  {"u": admin_user, "p": hashed_pw, "r": "admin"})

init_admin_user()

def check_password(username, password):
    res = query_db("SELECT * FROM usuarios WHERE username = :u", {"u": username})
    if not res.empty:
        # Normalizar columnas a minúsculas
        res.columns = [c.lower() for c in res.columns]
        
        db_pass = str(res.iloc[0]['password']).strip()
        input_hash = hashlib.sha256(password.encode()).hexdigest()
        
        if db_pass == input_hash or db_pass == password:
            return MockObj(
                id=res.iloc[0]['id'], 
                username=res.iloc[0]['username'], 
                role=res.iloc[0]['role']
            )
    return None

def guardar_evidencia_fisica(imagen_pil, nombre_maquina):
    base_path = os.path.join(EVIDENCIAS_PATH, nombre_maquina)
    if not os.path.exists(base_path): os.makedirs(base_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    full_path = os.path.join(base_path, f"test_{timestamp}.jpg")
    imagen_pil.save(full_path, "JPEG")
    return full_path

def save_test_result(machine_name, health_score, missing_nodes, health_map, evidence_path):
    map_json = json.dumps(health_map)
    commit_db("""
        INSERT INTO test_results (machine_name, health_score, missing_nodes, health_map, evidence_path, timestamp)
        VALUES (:m, :s, :n, :map, :e, :t)
    """, {"m": machine_name, "s": health_score, "n": missing_nodes, "map": map_json, "e": evidence_path, "t": datetime.now()})

def render_machine_card(m_name, fecha_consulta, suffix=""):
    # Obtener el último test del día para esa máquina en Postgres
    fecha_str = fecha_consulta.strftime('%Y-%m-%d')
    res_test = conn.query("""
        SELECT * FROM test_results 
        WHERE machine_name = :m AND DATE(timestamp) = :d
        ORDER BY timestamp DESC LIMIT 1
    """, params={"m": m_name, "d": fecha_str}, ttl=10)
    
    last_test = None
    if not res_test.empty:
        last_test = MockObj(
            health_score=res_test.iloc[0]['health_score'],
            missing_nodes=res_test.iloc[0]['missing_nodes'],
            timestamp=res_test.iloc[0]['timestamp']
        )

    res_estado = query_db("SELECT estado FROM estados_maquinas WHERE machine_name = :m", {"m": m_name})
    estado_actual = res_estado.iloc[0]['estado'] if not res_estado.empty else "Operativa"
    fecha_ultimo = last_test.timestamp.strftime('%d/%m/%Y %I:%M %p') if last_test else "Sin registros"

    opciones_estilo = {
        "Operativa": {"color_b": "#28a745", "color_f": "rgba(40, 167, 69, 0.05)", "icon": "✅"},
        "Mantenimiento": {"color_b": "#6c757d", "color_f": "rgba(108, 117, 125, 0.1)", "icon": "🛠️"},
        "Falla Total": {"color_b": "#dc3545", "color_f": "rgba(220, 53, 69, 0.1)", "icon": "🚫"},
        "Falla de Slots": {"color_b": "#fd7e14", "color_f": "rgba(253, 126, 20, 0.1)", "icon": "🔌"},
        "Falla de Tarjetas": {"color_b": "#0dcaf0", "color_f": "rgba(13, 202, 240, 0.1)", "icon": "💾"}
    }
    estilo = opciones_estilo.get(estado_actual, opciones_estilo["Operativa"])
    
    if estado_actual == "Operativa" and last_test:
        salud = last_test.health_score
        if salud < 75: estilo["color_b"] = "#fd7e14"
        if salud < 50: estilo["color_b"] = "#dc3545"
        
        with st.container(border=True):
            st.markdown(f"""
                <div style="height: 60px; border-bottom: 1px solid {estilo['color_b']}; margin-bottom: 10px;">
                    <h3 style="margin: 0; color: {estilo['color_b']};">{estilo['icon']} {m_name}</h3>
                    <p style="color: gray; font-size: 0.8em; margin: 0;">Último test procesado: {fecha_ultimo}</p>
                </div>
            """, unsafe_allow_html=True)
            st.metric("Status", f"{salud:.1f}%", f"{last_test.missing_nodes} fallas", delta_color="inverse")
            
            history = query_db("""
                SELECT timestamp, health_score FROM test_results 
                WHERE machine_name = :m ORDER BY timestamp DESC LIMIT 10
            """, {"m": m_name})
            
            if not history.empty:
                st.area_chart(history.sort_values('timestamp').set_index('timestamp')['health_score'], height=150, color=[estilo["color_b"]])
    else:
        st.markdown(f"""
            <div style="height: 380px; border: 2px solid {estilo['color_b']}; border-radius: 10px; padding: 20px; background-color: {estilo['color_f']}; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; box-sizing: border-box;">
                <h1 style="font-size: 3em; margin: 0;">{estilo['icon']}</h1>
                <h2 style="margin: 10px 0;">{m_name}</h2>
                <div style="background-color: {estilo['color_b']}; color: white; padding: 5px 15px; border-radius: 20px; font-weight: bold; text-transform: uppercase;">
                    {estado_actual}
                </div>
                <p style="color: gray; font-size: 0.9em; margin-top: 20px;">
                    Modo restringido por estado de equipo.<br>Último test: {fecha_ultimo}
                </p>
            </div>
        """, unsafe_allow_html=True)

# =========================================================
# 6. LÓGICA DE AUTENTICACIÓN (LOGIN)
# =========================================================
if not st.session_state.authenticated:
    st.title("🔐 Acceso al Sistema")
    
    user_input = st.text_input("Usuario")
    pass_input = st.text_input("Contraseña", type="password")
    
    if st.button("Entrar", type="primary"):
        user = check_password(user_input, pass_input)
        if user:
            st.session_state.update({
                "authenticated": True, 
                "user_role": user.role, 
                "username": user.username
            })
            st.success(f"Bienvenido {user.username}")
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos")
            
    st.stop()

# =========================================================
# 7. INTERFAZ PRINCIPAL (POST-LOGIN)
# =========================================================
# --- HEADER ---
ruta_logo = os.path.join(BASE_DIR, "assets", "logo.png")
if os.path.exists(ruta_logo):
    with open(ruta_logo, 'rb') as f: bin_str = base64.b64encode(f.read()).decode()
    st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 5px; margin-bottom: 5px;">
            <img src="data:image/png;base64,{bin_str}" width="100">
            <h1 style="font-size: 40px; color: #FFFFFF; margin: 0; font-family: sans-serif; font-weight: 600;">
                🖨️ Monitor Inteligente / Status Impresoras
            </h1>
        </div>
    """, unsafe_allow_html=True)
else:
    st.title("Monitor Inteligente de Cabezales 🖨️")

# --- SIDEBAR ---
with st.sidebar:
    st.write(f"👤 Usuario: **{st.session_state.username}**")
    st.write(f"🎖️ Rol: **{st.session_state.user_role.capitalize()}**")

    with st.expander("⚙️ Editar Mi Perfil"):
        new_user_val = st.text_input("Nuevo usuario", key="gestion_user", value=st.session_state.username)
        new_pass_val = st.text_input("Nueva Contraseña", type="password", key="gestion_pass", help="Dejar en blanco para no cambiar")
        confirm_pass_val = st.text_input("Confirmar Nueva Contraseña", type="password", key="gestion_confirm")
        st.divider()
        old_pw = st.text_input("Contraseña Actual", type="password")
        
        if st.button("💾 Guardar Cambios"):
            if old_pw:
                res_u = query_db("SELECT * FROM usuarios WHERE username = :u", {"u": st.session_state.username})
                if not res_u.empty and res_u.iloc[0]['password'] == hashlib.sha256(old_pw.encode()).hexdigest():
                    if new_pass_val == confirm_pass_val:
                        h_new = hashlib.sha256(new_pass_val.encode()).hexdigest() if new_pass_val else res_u.iloc[0]['password']
                        exito = commit_db("UPDATE usuarios SET username = :nu, password = :np WHERE id = :uid",
                                          {"nu": new_user_val, "np": h_new, "uid": res_u.iloc[0]['id']})
                        if exito:
                            st.session_state.username = new_user_val
                            st.success("✅ ¡Perfil actualizado correctamente!")
                            time.sleep(1)
                            st.rerun()
                    else: st.error("❌ Contraseñas nuevas no coinciden")
                else: st.error("❌ Contraseña actual incorrecta")
            else: st.error("❌ Introduce tu contraseña actual")

    st.divider()
    st.subheader("🛠️ Configuración Global")
    machine_selected_global = st.selectbox("Máquina destino (Cámara/Manual):", list(MACHINE_CONFIGS.keys()))
    sensibilidad = st.slider("Sensibilidad de Nozzles", 0.01, 0.20, 0.05)
    
    st.divider()
    st.subheader("🔍 Ajustes de Lente")
    zoom_level = st.slider("Zoom Digital (Recorte de bordes)", 0, 100, 0, help="Elimina el ruido de los bordes antes de procesar")
    st.subheader("📷 Control de Cámara")
    run_camera = st.checkbox("Activar Estación de Escaneo")

    st.divider()
    st.header("🛠️ Gestión de Equipos")
    maquina_a_configurar = st.selectbox("Seleccionar Máquina para Estado:", list(MACHINE_CONFIGS.keys()))
    
    # Consultamos el estado actual para mostrarlo por defecto en el selectbox
    res_est_actual = query_db("SELECT estado FROM estados_maquinas WHERE machine_name = :m", {"m": maquina_a_configurar})
    est_defecto = res_est_actual.iloc[0]['estado'] if not res_est_actual.empty else "Operativa"
    
    nuevo_est = st.selectbox("Definir estado:", 
                             ["Operativa", "Mantenimiento", "Falla Total", "Falla de Slots", "Falla de Tarjetas"], 
                             index=["Operativa", "Mantenimiento", "Falla Total", "Falla de Slots", "Falla de Tarjetas"].index(est_defecto))
    
    if st.button("🔄 Actualizar Estado"):
        # Guardamos el cambio directamente en PostgreSQL
        commit_db("""
            INSERT INTO estados_maquinas (machine_name, estado, updated_at)
            VALUES (:m, :e, CURRENT_TIMESTAMP)
            ON CONFLICT (machine_name) 
            DO UPDATE SET estado = EXCLUDED.estado, updated_at = CURRENT_TIMESTAMP;
        """, {"m": maquina_a_configurar, "e": nuevo_est})
        
        st.success(f"✅ Estado de {maquina_a_configurar} guardado en la red como {nuevo_est}")
        time.sleep(1)
        st.rerun()

    st.divider()
    fecha_consulta = st.date_input("📅 Consultar estado al día:", datetime.now().date())
    
    if st.sidebar.button("Cerrar Sesión"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# --- LÓGICA DE CÁMARA (MODO FOTO ) ---
foto = None
if run_camera:
    foto = st.camera_input("Capturar Test", key="cam_main")

if foto:
    st.session_state.bloquear_refresco = True
    contenedor_estado = st.empty()
    
    with st.spinner("🔍 Procesando captura..."):
        img_bytes = foto.getvalue()
        # Decodificar y redimensionar si es muy grande para evitar errores de memoria
        nparr = np.frombuffer(img_bytes, np.uint8)
        res = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if res is not None:
            # Redimensión preventiva para móviles (Max 1280px ancho)
            if res.shape[1] > 1280:
                scale = 1280 / res.shape[1]
                res = cv2.resize(res, None, fx=scale, fy=scale)

            try:
                # Ajuste de Zoom Digital con seguridad de límites
                if zoom_level > 0:
                    h, w = res.shape[:2]
                    margin_h = int(h * (zoom_level / 200))
                    margin_w = int(w * (zoom_level / 200))
                    # Asegurar que el recorte no sea mayor que la imagen
                    res = res[margin_h:h-margin_h, margin_w:w-margin_w]

                # --- PROCESAMIENTO ---
                temp_p = os.path.join(BASE_DIR, "temp_capture.jpg")
                cv2.imwrite(temp_p, res)
                
                config = MACHINE_CONFIGS[machine_selected_global]
                mapa, img_res, msg = image_processor.process_test_image_v2(temp_p, config, sensibilidad)
                
                if mapa is not None:
                    salud = (np.sum(mapa) / mapa.size) * 100
                    fallas = int(np.count_nonzero(mapa == 0))
                    img_pil = Image.fromarray(cv2.cvtColor(img_res, cv2.COLOR_BGR2RGB))
                    
                    ruta_evidencia = guardar_evidencia_fisica(img_pil, machine_selected_global)
                    
                    save_test_result(machine_selected_global, salud, fallas, mapa.tolist(), ruta_evidencia)
                    
                    contenedor_estado.success(f"✅ ¡{machine_selected_global} Actualizada! ({salud:.1f}%)")
                    st.balloons()
                    
                    st.session_state.bloquear_refresco = False
                    time.sleep(2)
                    st.rerun()
                    
            except Exception as e:
                st.error(f"❌ La imagen estaba borrosa o la cámara falló ({e}). Intenta tomar la foto de nuevo.")
                st.session_state.bloquear_refresco = False
        else:
            st.warning("⚠️ Esperando señal de la cámara...")
            st.session_state.bloquear_refresco = False

# --- TABS PRINCIPALES ---
st.divider()
hora_ajustada = datetime.now() - timedelta(hours=6)
fecha_mostrar = hora_ajustada.strftime('%d/%m/%Y')
es_hoy = (fecha_consulta == datetime.now().date())
st.subheader(f"📊 Monitoreo en Tiempo Real ({fecha_mostrar})" if es_hoy else f"📅 Historial de Planta: {fecha_consulta.strftime('%d/%m/%Y')}")

tab_carrusel, tab_planta, tab_analisis, tab_gestion = st.tabs(["🔄 Modo Carrusel", "🏬 Vista General", "✂️ Análisis Manual", "⚙️ Gestión y Reportes"])

lista_maquinas = list(MACHINE_CONFIGS.keys())

# TAB 1: CARRUSEL
with tab_carrusel:
    idx = st.session_state.indice_carrusel
    cols_car = st.columns(2)
    for i, m_name in enumerate(lista_maquinas[idx : idx + 2]):
        with cols_car[i]: render_machine_card(m_name, fecha_consulta, suffix="car")

# TAB 2: VISTA GENERAL
with tab_planta:
    for i in range(0, len(lista_maquinas), 2):
        cols = st.columns(2)
        for j, m_name in enumerate(lista_maquinas[i : i + 2]):
            with cols[j]: render_machine_card(m_name, fecha_consulta, suffix="gral")
# ===============================
    # 🔹 TAB3
    # ===============================
with tab_analisis:
    import json
    from PIL import Image
    import numpy as np

    # ===============================
    # 🔹 Estados persistentes
    # ===============================
    if 'recortes' not in st.session_state: st.session_state.recortes = {}
    if 'finalizado' not in st.session_state: st.session_state.finalizado = False

    # ===============================
    # ✅ Pantalla de éxito
    # ===============================
    if st.session_state.finalizado:
        st.success(f"### ✅ ¡{machine_selected_global} Sincronizada!")
        st.metric("SALUD TOTAL", f"{st.session_state.get('ultima_salud', 0):.2f}%")
        if st.button("🔄 Nuevo Análisis"):
            st.session_state.finalizado = False
            st.session_state.recortes = {}
            st.rerun()
        st.stop()  # evita parpadeo

    # ===============================
    # 📁 Carga del test
    # ===============================
    uploaded_file = st.file_uploader("Subir Test Vutek", type=['jpg', 'png'], key="up_vutek_final")

    if uploaded_file:
        img_raw = Image.open(uploaded_file)
        grados = st.slider("Ajuste de rotación", -10.0, 10.0, 0.0)
        img_rotated = img_raw.rotate(grados, expand=True)

        col_edit, col_prev = st.columns([2, 1])

        # ===============================
        # ✂️ Cropping y selección de cabezales
        # ===============================
        with col_edit:
            num_h = st.number_input("Total cabezales en test", 1, 12, 2)
            h_id = st.selectbox("Recortando cabezal:", range(1, num_h + 1))

            img_cropped = st_cropper(
                img_rotated,
                realtime_update=False,
                box_color='#FF0000',
                aspect_ratio=None,
                key=f"vutek_crop_{h_id}"
            )

            # Guardado robusto del crop
            if st.button(f"💾 Guardar Recorte {h_id}", type="primary"):
                if img_cropped is not None:
                    # Asegurar que sea PIL.Image
                    if not isinstance(img_cropped, Image.Image):
                        img_cropped = Image.fromarray(np.array(img_cropped))
                    st.session_state.recortes[h_id] = img_cropped.copy()
                    st.toast(f"Cabezal {h_id} guardado.")
                else:
                    st.warning("Primero ajusta el recorte.")

        # ===============================
        # 📸 Vista previa de recortes
        # ===============================
        with col_prev:
            st.subheader("Lista de Recortes")
            for idx in sorted(st.session_state.recortes.keys()):
                st.image(st.session_state.recortes[idx], caption=f"H-{idx}", use_column_width=True)

            # ===============================
            # 🚀 Procesamiento de todos los recortes
            # ===============================
            if len(st.session_state.recortes) >= num_h:
                st.divider()
                if st.button("PROCESAR Y SINCRONIZAR", use_container_width=True):
                    all_maps_list = []
                    t_missing, t_nodes = 0, 0
                    config_base = MACHINE_CONFIGS[machine_selected_global].copy()

                    for idx, img_save in st.session_state.recortes.items():
                        # Verificación de crop válido
                        if img_save is None:
                            st.warning(f"Cabezal {idx} no tiene recorte válido, se omite.")
                            continue
                        if not hasattr(img_save, "convert"):
                            st.warning(f"Cabezal {idx} no es una imagen válida, se omite.")
                            continue

                        # Procesamiento
                        porcentaje, mapa = process_standard_manual(img_save, config_base)

                        missing = int(np.count_nonzero(mapa == 0))
                        t_missing += missing
                        t_nodes += mapa.size
                        all_maps_list.append({"id": idx, "mapa": mapa.tolist()})

                        st.image(img_save, caption=f"Procesado H-{idx}", use_column_width=True)

                    # Cálculo de salud total
                    if t_nodes > 0:
                        salud = ((t_nodes - t_missing) / t_nodes) * 100
                    else:
                        salud = 0

                    st.session_state.ultima_salud = salud
                    st.session_state.finalizado = True

                    # Guardado en DB
                    map_json = json.dumps(all_maps_list)
                    params = {
                        "m": machine_selected_global,
                        "s": salud,
                        "n": t_missing,
                        "map": map_json
                    }
                    commit_db(
                        "INSERT INTO test_results (machine_name, health_score, missing_nodes, health_map, timestamp) VALUES (:m, :s, :n, :map, CURRENT_TIMESTAMP)",
                        params
                    )

                    st.session_state.analisis_completado = True
                    st.rerun()
# =========================================================
# 6. TAB DE GESTIÓN (SOLO ADMINISTRADORES)
# =========================================================
with tab_gestion:
    if st.session_state.user_role != "admin":
        st.warning("⚠️ Esta sección es exclusiva para el personal de administración.")
        st.image("https://cdn-icons-png.flaticon.com/512/7506/7506500.png", width=100)
    else:
        st.header("🛠️ Panel de Control Administrativo")
        
        # --- KPI GLOBAL ---
        st.subheader("📈 Rendimiento General (Últimos 7 días)")
        
        # Definir fechas
        f_inicio = (datetime.now() - timedelta(days=7)).date()
        f_fin = datetime.now().date()
        
        # Consulta con cast explícito a DATE para evitar errores de tipo en Postgres
        df_stats = query_db("""
            SELECT 
                machine_name, 
                health_score, 
                timestamp 
            FROM test_results 
            WHERE timestamp::date >= :fi AND timestamp::date <= :ff
        """, {"fi": f_inicio, "ff": f_fin})

        todas_las_maquinas = list(MACHINE_CONFIGS.keys())

        if not df_stats.empty:
            # Aseguramos que health_score sea numérico para evitar errores en mean()
            df_stats['health_score'] = pd.to_numeric(df_stats['health_score'], errors='coerce')
            
            # Agrupamos y calculamos el promedio
            promedio_real = df_stats.groupby("machine_name")["health_score"].mean()
            
            # Reindexamos para que aparezcan todas las máquinas, incluso las que tienen 0%
            grafica_final = promedio_real.reindex(todas_las_maquinas, fill_value=0)
            
            st.bar_chart(grafica_final, color="#28a745")
        else:
            # Si no hay datos, mostrar barras en cero para mantener el diseño
            chart_vacio = pd.Series(0, index=todas_las_maquinas)
            st.bar_chart(chart_vacio, color="#6c757d")
            st.info("No hay registros en los últimos 7 días.")

        # --- GESTIÓN DE USUARIOS ---
        col_u1, col_u2 = st.columns(2)
        
        with col_u1:
            with st.expander("👤 Crear Nuevo Acceso"):
                with st.form("crear_user", clear_on_submit=True):
                    new_u = st.text_input("Usuario")
                    new_p = st.text_input("Password", type="password")
                    new_r = st.selectbox("Rol", ["operator", "admin"])
                    if st.form_submit_button("Registrar en Sistema"):
                        if new_u and new_p:
                            h_pw = hashlib.sha256(new_p.encode()).hexdigest()
                            try:
                                commit_db("INSERT INTO usuarios (username, password, role) VALUES (:u, :p, :r)", 
                                          {"u": new_u, "p": h_pw, "r": new_r})
                                st.success("Usuario creado con éxito")
                                time.sleep(1); st.rerun()
                            except:
                                st.error("El usuario ya existe")
        
        with col_u2:
            with st.expander("🗑️ Eliminar Acceso"):
                # Consultamos explícitamente la columna
                users_df = query_db("SELECT username FROM usuarios")
                
                if not users_df.empty:
                    # Forzamos a que los nombres de columnas de Pandas estén en minúsculas 
                    # para evitar el KeyError independientemente de cómo responda Postgres
                    users_df.columns = [c.lower() for c in users_df.columns]
                    
                    # Ahora usamos 'username' con total seguridad
                    lista_nombres = [u for u in users_df['username'].tolist() if u != st.session_state.username]
                    
                    if lista_nombres:
                        u_eliminar = st.selectbox("Seleccionar usuario para borrar", lista_nombres)
                        confirm = st.checkbox("Confirmo eliminación permanente", key="conf_del")
                        if st.button("Eliminar Usuario", type="secondary"):
                            if confirm:
                                if commit_db("DELETE FROM usuarios WHERE username=:u", {"u": u_eliminar}):
                                    st.success(f"Usuario {u_eliminar} borrado")
                                    time.sleep(1)
                                    st.rerun()
                            else:
                                st.warning("Debes marcar la casilla de confirmación")
                    else:
                        st.info("No hay otros usuarios para eliminar.")
                else:
                    st.info("No se encontraron usuarios en la base de datos.")

        st.divider()

        # --- REPORTES ---
        st.subheader("📄 Generación de Documentos Oficiales")
        c_r1, c_r2 = st.columns(2)
        f_i = c_r1.date_input("Desde", value=datetime.now()-timedelta(days=7), key="admin_f1")
        f_f = c_r2.date_input("Hasta", key="admin_f2")
        
        if st.button("📊 Preparar Archivos para Descarga", use_container_width=True):
            st.session_state.bloquear_refresco = True
            
            datos = query_db("""
                SELECT machine_name as "Máquina", health_score as "Salud %", missing_nodes as "Nodos Caídos", timestamp as "Fecha"
                FROM test_results WHERE DATE(timestamp) >= :fi AND DATE(timestamp) <= :ff
            """, {"fi": f_i.strftime('%Y-%m-%d'), "ff": f_f.strftime('%Y-%m-%d')})
            
            if not datos.empty:
                # Usamos crud.py exclusivamente para la generación en PDF (como indicaste)
                st.session_state.archivo_pdf_listo = crud.generate_pdf_report(datos)
                st.session_state.archivo_csv_listo = datos.to_csv(index=False).encode('utf-8')
                st.session_state.mostrar_descargas = True
                st.success("✅ Archivos generados correctamente")
            else:
                st.warning("No hay registros en esas fechas")
            st.session_state.bloquear_refresco = False

        if st.session_state.get("mostrar_descargas"):
            cd1, cd2 = st.columns(2)
            cd1.download_button("💾 DESCARGAR PDF", st.session_state.archivo_pdf_listo, "Reporte.pdf", "application/pdf", use_container_width=True)
            cd2.download_button("📉 DESCARGAR CSV", st.session_state.archivo_csv_listo, "Datos.csv", "text/csv", use_container_width=True)

# =========================================================
# MOTOR DE SINCRONIZACIÓN CORREGIDO
# =========================================================
if st.session_state.authenticated:
    # Definimos qué actividades bloquean el refresco
    interactuando = (
        st.session_state.get("bloquear_refresco", False) or 
        run_camera or 
        st.session_state.get("mostrar_descargas", False) or
        st.session_state.get("editando_manual", False)
    )

    if not interactuando:
        # Tiempo de espera entre saltos del carrusel (ej. 10 segundos)
        TIEMPO_REFRESCO = 10 
        
        # Lógica de rotación de índice
        st.session_state.indice_carrusel = (st.session_state.indice_carrusel + 2) % len(lista_maquinas)
        
        # El truco para el autorefresh en Streamlit sin componentes externos:
        time.sleep(TIEMPO_REFRESCO)
        st.rerun()
    else:
        st.sidebar.warning("⏸️ Carrusel en pausa (Modo edición/cámara)")
        if st.sidebar.button("Reanudar Carrusel"):
            st.session_state.editando_manual = False
            st.session_state.bloquear_refresco = False
            st.rerun()

