import sys
import os
import hashlib
import numpy as np
import cv2
import pandas as pd
import streamlit as st
from streamlit_cropper import st_cropper
from PIL import Image
from datetime import datetime
import time
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase, WebRtcMode
import qrcode
from io import BytesIO
import shutil
import base64
from sqlalchemy import func  # <-- Asegúrate de que esta línea esté al inicio

# importaciones de directorio
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EVIDENCIAS_PATH = os.path.join(BASE_DIR, "evidencias")

def guardar_evidencia_fisica(imagen_pil, nombre_maquina):
    # Ruta absoluta basada en la ubicación del script
    folder_path = os.path.join(EVIDENCIAS_PATH, nombre_maquina)
    # En dashboard.py
    if getattr(sys, 'frozen', False):
        # Si es un ejecutable, usa la carpeta donde está el .exe
        BASE_DIR = os.path.dirname(sys.executable)
    else:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    full_path = os.path.join(folder_path, f"test_{timestamp}.jpg")
    imagen_pil.save(full_path, "JPEG")
    return full_path


# =========================================================
# 1. CONFIGURACIÓN DE RUTAS Y PATHS (PRIMERO QUE NADA)
# =========================================================
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
backend_dir = os.path.join(project_root, "backend")

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# =========================================================
# 2. IMPORTS DE MÓDULOS PROPIOS (DESPUÉS DEL PATH)
# =========================================================
try:
    import database
    import models
    import crud
    import image_processor
    from config import MACHINE_CONFIGS
except ImportError as e:
    st.error(f"Error crítico de importación: {e}")
    st.stop()

# =========================================================
# 3. FUNCIONES DE APOYO (LOGIN E INICIALIZACIÓN)
# =========================================================
def init_admin_user(db_session):
    """Crea el usuario admin:system123 si la tabla está vacía."""
    admin_user = "admin"
    admin_pass = "system123"
    hashed_pw = hashlib.sha256(admin_pass.encode()).hexdigest()
    
    existing = crud.get_user_by_username(db_session, admin_user)
    if not existing:
        crud.create_user(db_session, admin_user, hashed_pw, role="admin")

def check_password(db_session, username, password):
    user = crud.get_user_by_username(db_session, username)
    if user and user.password == hashlib.sha256(password.encode()).hexdigest():
        return user
    return None

# =========================================================
# 4. CONEXIÓN A BASE DE DATOS
# =========================================================
database.Base.metadata.create_all(bind=database.engine)
db = database.SessionLocal()

# Aseguramos que el admin exista
init_admin_user(db)

# =========================================================
# 5. CONFIGURACIÓN DE PÁGINA Y SESSION STATE
# =========================================================
st.set_page_config(page_title="Print Head Monitor", layout="wide")

# =========================================================
# 5. CONFIGURACIÓN DE PÁGINA Y SESSION STATE (CORREGIDO)
# =========================================================
# =========================================================
# INICIALIZACIÓN DE SEGURIDAD (Debe ir AQUÍ)
# =========================================================
# Definimos los valores por defecto para que NUNCA den AttributeError
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

if 'user_role' not in st.session_state:
    st.session_state.user_role = None

if 'username' not in st.session_state:
    st.session_state.username = None

if 'estados_maquinas' not in st.session_state:
    st.session_state.estados_maquinas = {name: "Operativa" for name in MACHINE_CONFIGS.keys()}

if 'indice_carrusel' not in st.session_state:
    st.session_state.indice_carrusel = 0
    
# =========================================================
# INICIALIZACIÓN DE SESSION STATE (Cerca del inicio del script)
# =========================================================
if 'mapa_actual' not in st.session_state:
    st.session_state.mapa_actual = None

if 'img_resultado' not in st.session_state:
    st.session_state.img_resultado = None

# También asegúrate de que estas existan para que no te dé el siguiente error:
if 'recortes' not in st.session_state:
    st.session_state.recortes = {}    

# =========================================================
# FUNCIONES DE RENDERIZADO (PARA EVITAR DUPLICAR CÓDIGO)
# =========================================================

def render_machine_card(m_name, db_session, fecha_consulta):
    # Convertimos la fecha a string para comparar o la usamos en el query
    # Buscamos el último test realizado EN o ANTES de la fecha seleccionada
    last_test = crud.get_test_by_date(db_session, m_name, fecha_consulta)
    
    # El estado actual lo sacamos de la sesión si es hoy, 
    # o de la base de datos si es histórico (necesitarás guardar el estado en la DB)
    estado_actual = st.session_state.estados_maquinas.get(m_name, "Operativa")
    fecha_ultimo = "Sin registros"
    
    fecha_mostrar = last_test.timestamp.strftime("%d/%m/%y %H:%M") if last_test else "Sin registros"
    
    opciones_estilo = {
        "Operativa": {"color_b": "#28a745", "color_f": "rgba(40, 167, 69, 0.05)", "icon": "✅"},
        "Mantenimiento": {"color_b": "#6c757d", "color_f": "rgba(108, 117, 125, 0.1)", "icon": "🛠️"},
        "Falla Total": {"color_b": "#dc3545", "color_f": "rgba(220, 53, 69, 0.1)", "icon": "🚫"},
        "Falla de Slots": {"color_b": "#fd7e14", "color_f": "rgba(253, 126, 20, 0.1)", "icon": "🔌"},
        "Falla de Tarjetas": {"color_b": "#0dcaf0", "color_f": "rgba(13, 202, 240, 0.1)", "icon": "💾"}
    }
    
    estilo = opciones_estilo.get(estado_actual, opciones_estilo["Operativa"])
    
    # CSS para forzar la altura mínima y que los recuadros sean iguales
    # Ajusta '350px' según qué tan grandes sean tus gráficas
    card_height = "380px" 

    if estado_actual == "Operativa" and last_test:
        salud = last_test.health_score
        if salud < 75: estilo["color_b"] = "#fd7e14"
        if salud < 50: estilo["color_b"] = "#dc3545"
        
        # Contenedor para operativa
        with st.container(border=True):
            st.markdown(f"""
                <div style="height: 60px; border-bottom: 1px solid {estilo['color_b']}; margin-bottom: 10px;">
                    <h3 style="margin: 0; color: {estilo['color_b']};">{estilo['icon']} {m_name}</h3>
                    <p style="color: gray; font-size: 0.8em; margin: 0;">Último: {fecha_ultimo}</p>
                </div>
            """, unsafe_allow_html=True)
            
            st.metric("Salud", f"{salud:.1f}%", f"{last_test.missing_nodes} fallas", delta_color="inverse")
            
            history = crud.get_machine_history(db_session, m_name, limit=10)
            if not history.empty:
                st.area_chart(history.set_index('timestamp')['health_score'], height=150, color=[estilo["color_b"]])
    else:
        # Contenedor para Falla o Mantenimiento con altura fija
        st.markdown(f"""
            <div style="
                height: {card_height}; 
                border: 2px solid {estilo['color_b']}; 
                border-radius: 10px; 
                padding: 20px; 
                background-color: {estilo['color_f']}; 
                display: flex; 
                flex-direction: column; 
                justify-content: center; 
                align-items: center; 
                text-align: center;
                box-sizing: border-box;
            ">
                <h1 style="font-size: 3em; margin: 0;">{estilo['icon']}</h1>
                <h2 style="margin: 10px 0;">{m_name}</h2>
                <div style="
                    background-color: {estilo['color_b']}; 
                    color: white; 
                    padding: 5px 15px; 
                    border-radius: 20px; 
                    font-weight: bold;
                    text-transform: uppercase;
                ">
                    {estado_actual}
                </div>
                <p style="color: gray; font-size: 0.9em; margin-top: 20px;">
                    Modo restringido por estado de equipo.<br>
                    Último test: {fecha_ultimo}
                </p>
            </div>
        """, unsafe_allow_html=True)

# =========================================================
# 6. LÓGICA DE AUTENTICACIÓN (LOGIN)
# =========================================================
if not st.session_state.authenticated:
    st.title("🔐 Acceso al Sistema")
    with st.form("login_form"):
        user_input = st.text_input("Usuario")
        pass_input = st.text_input("Contraseña", type="password")
        submit = st.form_submit_button("Entrar")
        
        if submit:
            user = check_password(db, user_input, pass_input)
            if user:
                st.session_state.authenticated = True
                st.session_state.user_role = user.role
                st.session_state.username = user.username
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos")
    st.stop() 

# =========================================================
# --- CONFIGURACIÓN DE LOGO Y TÍTULO ---



def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

def render_header_with_logo(logo_path):
    if os.path.exists(logo_path):
        binary_string = get_base64_of_bin_file(logo_path)
        # Determinamos el tipo de imagen por la extensión
        ext = logo_path.split(".")[-1]
        
        st.markdown(
            f"""
            <div style="display: flex; align-items: center; gap: 5px; margin-bottom: 5px;">
                <img src="data:image/{ext};base64,{binary_string}" width="100">
                <h1 style="
                    font-size: 40px; 
                    color: #FFFFFF; 
                    margin: 0; 
                    font-family: sans-serif;
                    font-weight: 600;
                ">
                    🖨️Monitor Inteligente / Status Impresoras
                </h1>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        # Si no encuentra el logo, muestra solo el título para no romper la app
        st.title("Monitor Inteligente de Cabezales 🖨️ ")
        st.error(f"No se encontró el logo en: {logo_path}")

# --- USO EN LA INTERFAZ ---
# Ajusta la ruta exacta. Si tu carpeta es "assets" y el archivo "logo.png":
ruta_logo = os.path.join(BASE_DIR, "assets", "logo.png") 
render_header_with_logo(ruta_logo)
# =========================================================
# 7. INTERFAZ PRINCIPAL (POST-LOGIN)
# =========================================================

# --- 7.1 INICIALIZACIÓN DE VARIABLES (Evita errores de Pylance) ---
# Definimos valores por defecto para que siempre existan
run_camera = False
machine_selected = list(MACHINE_CONFIGS.keys())[0]
sensibilidad = 0.05

# --- 7.2 BARRA LATERAL (SIDEBAR) ---
if st.session_state.authenticated:
    with st.sidebar:
        st.write(f"👤 Usuario: **{st.session_state.username}**")
        st.write(f"🎖️ Rol: **{st.session_state.user_role.capitalize()}**")

        # --- SECCIÓN: EDITAR PERFIL ---
        with st.expander("⚙️ Editar Mi Perfil"):
            new_un = st.text_input("Nuevo Usuario", value=st.session_state.username)
            new_pw = st.text_input("Nueva Contraseña", type="password")
            confirm_pw = st.text_input("Confirmar Contraseña", type="password")
            st.divider()
            old_pw = st.text_input("Contraseña Actual", type="password", help="Obligatorio para guardar")
            
            if st.button("💾 Guardar Cambios"):
                user_db = crud.get_user_by_username(db, st.session_state.username)
                current_hash = hashlib.sha256(old_pw.encode()).hexdigest()
                
                if user_db and user_db.password == current_hash:
                    if new_pw == confirm_pw:
                        h_new = hashlib.sha256(new_pw.encode()).hexdigest() if new_pw else user_db.password
                        if crud.update_user_credentials(db, user_db.id, new_un, h_new):
                            st.session_state.username = new_un
                            st.success("✅ ¡Actualizado!")
                            st.rerun()
                    else:
                        st.error("❌ Las contraseñas no coinciden")
                else:
                    st.error("❌ Contraseña actual incorrecta")

        st.divider()
        st.subheader("🛠️ Configuración Global")
        # Definimos estas variables AQUÍ para que la cámara y la carga manual las vean
        machine_selected = st.selectbox("Máquina destino:", list(MACHINE_CONFIGS.keys()))
        sensibilidad = st.slider("Sensibilidad de Nozzles", 0.01, 0.20, 0.05)
        
        st.divider()
        st.subheader("📷 Control de Cámara")
        run_camera = st.checkbox("Activar Estación de Escaneo")

        if st.button("Cerrar Sesión"):
            st.session_state.authenticated = False
            st.rerun()



# --- SECCIÓN DE ACCESO RÁPIDO (QR) ---
    with st.sidebar:
        st.divider()
        st.subheader("📲 Acceso para Operadores")
        
        # 1. PEGA AQUÍ TU URL ACTUAL DE NGROK
        url_actual = "https://novelistically-unwakeful-jalen.ngrok-free.dev"
        
        # 2. Generar el QR con bordes para mejor lectura
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(url_actual)
        qr.make(fit=True)
        
        img_qr = qr.make_image(fill_color="black", back_color="white")
        
        # 3. Convertir para mostrar en Streamlit
        buf = BytesIO()
        img_qr.save(buf)
        st.image(buf, caption="Escanea para abrir en el celular", use_container_width=True)
        
        # Mostrar la URL en pequeño por si acaso
        st.caption(f"Enlace activo: {url_actual}")    
# --- 7.3 LÓGICA DE AUTO-CAPTURA (IA) ---


# --- CLASE PARA PROCESAR VIDEO DEL CELULAR ---
class VideoProcessor(VideoTransformerBase):
    def __init__(self):
        self.contador_estabilidad = 0
        self.ultimo_rect = None
        self.frame_capturado = None

    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        
        # --- IA DE DETECCIÓN (Igual que antes) ---
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edged = cv2.Canny(gray, 50, 150)
        cnts, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        if cnts:
            c = max(cnts, key=cv2.contourArea)
            if cv2.contourArea(c) > 40000:
                rect = cv2.minAreaRect(c)
                box = np.int0(cv2.boxPoints(rect))
                cv2.drawContours(img, [box], 0, (0, 255, 0), 3)
                
                # Estabilidad
                current_center = rect[0]
                if self.ultimo_rect is not None:
                    dist = np.linalg.norm(np.array(current_center) - np.array(self.ultimo_rect))
                    if dist < 8: self.contador_estabilidad += 1
                    else: self.contador_estabilidad = 0
                self.ultimo_rect = current_center

                # Si está estable, guardamos el frame para procesarlo
                if self.contador_estabilidad >= 30:
                    self.frame_capturado = img.copy()
        
        return img
    
    
# --- GESTIÓN DE ESTADOS EN EL SIDEBAR ---
with st.sidebar:
    st.header("🛠️ Gestión de Equipos")
    maquina_a_configurar = st.selectbox("Seleccionar Máquina:", list(MACHINE_CONFIGS.keys()))
    
    # Nuevo: Selector de estado con botón de confirmación
    nuevo_est = st.selectbox(
        f"Definir estado para {maquina_a_configurar}:",
        ["Operativa", "Mantenimiento", "Falla Total", "Falla de Slots", "Falla de Tarjetas"],
        index=["Operativa", "Mantenimiento", "Falla Total", "Falla de Slots", "Falla de Tarjetas"].index(
            st.session_state.estados_maquinas.get(maquina_a_configurar, "Operativa")
        )
    )
    
    if st.button("🔄 Actualizar Estado"):
        st.session_state.estados_maquinas[maquina_a_configurar] = nuevo_est
        st.success(f"{maquina_a_configurar} actualizada a {nuevo_est}")
        time.sleep(1)
        st.rerun()

    st.divider()


# --- INTERFAZ EN EL DASHBOARD ---
if run_camera:
    st.subheader("🤳 Escaneo desde Dispositivo Móvil")
    st.info("Apunta la cámara del celular al test de impresión. El sistema capturará la imagen automáticamente al detectar estabilidad.")

    # --- AJUSTE PARA CONEXIÓN REMOTA VÍA NGROK ---
    ctx = webrtc_streamer(
        key="escaneo-movil",
        mode=WebRtcMode.SENDRECV,
        # Este mensaje ayuda a que el usuario sepa que debe interactuar
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
        media_stream_constraints={
            "video": {
                "facingMode": "environment", # Cámara trasera
                "width": {"ideal": 1280},
                "height": {"ideal": 720}
            },
            "audio": False
        },
        # Mensaje personalizado si el permiso falla
        translations={
            "start": "🔴 Iniciar Cámara",
            "stop": "🛑 Detener Cámara",
            "select_device": "Seleccionar Cámara",
            "camera_action": "Cámara",
            "forbidden_message": "Permiso de cámara denegado. Por favor, actívalo en la configuración del navegador."
        }
    )

    if ctx.video_transformer and ctx.video_transformer.frame_capturado is not None:
        st.success("✅ ¡Test capturado con éxito!")
        temp_path = os.path.join(current_dir, "mobile_capture.jpg")
        cv2.imwrite(temp_path, ctx.video_transformer.frame_capturado)
        
        # Procesar con la configuración de la máquina y sensibilidad seleccionada
        config = MACHINE_CONFIGS[machine_selected]
        mapa, img_res, msg = image_processor.process_test_image_v2(temp_path, config, sensibilidad)
        
        if mapa is not None:
            st.session_state.mapa_actual = mapa
            st.session_state.img_resultado = img_res
            # Guardar en DB
            salud = (np.sum(mapa) / mapa.size) * 100
            fallas = int(np.count_nonzero(mapa == 0))
            crud.save_test_result(db, machine_selected, salud, fallas, mapa.tolist(), temp_path)
            
            st.balloons() # Efecto visual de éxito
            st.rerun()

# --- 7.4 TÍTULO Y MÉTRICAS ---

# --- FILTRO DE FECHA EN SIDEBAR ---
with st.sidebar:
    st.divider()
    st.subheader("📅 Historial Temporal")
    # Así queda perfecto
    fecha_consulta = st.date_input("Consultar estado al día:", datetime.now().date())
es_hoy = (fecha_consulta == datetime.now().date())
#==========================================================
# --- PANEL SUPERIOR: CARRUSEL DINÁMICO ---
#==========================================================

# --- SECCIÓN DEL MONITOR 
# --- MONITOR OPERATIVO (CORREGIDO) ---
# --- 1. PREPARACIÓN DE DATOS ---
lista_maquinas_nombres = list(MACHINE_CONFIGS.keys())
n_maquinas = len(lista_maquinas_nombres)

# --- 2. EL INTERRUPTOR ---
# --- 1. PREPARACIÓN DE DATOS ---
lista_maquinas_nombres = list(MACHINE_CONFIGS.keys())
n_maquinas = len(lista_maquinas_nombres)

# --- PANEL SUPERIOR: CONTROL DE MONITOREO ---
st.divider()

# Título dinámico que muestra la fecha seleccionada
fecha_formateada = fecha_consulta.strftime('%d/%m/%Y')

if es_hoy:
    st.subheader(f"📊 Monitoreo en Tiempo Real ({fecha_formateada})")
else:
    st.subheader(f"📅 Historial de Planta: {fecha_formateada}")

tab_carrusel, tab_planta = st.tabs(["🔄 Modo Carrusel", "🏬 Vista General"])

with tab_carrusel:
    idx = st.session_state.indice_carrusel
    maquinas_visibles = lista_maquinas_nombres[idx : idx + 2]
    cols_car = st.columns(2)
    for i, m_name in enumerate(maquinas_visibles):
        with cols_car[i]:
            # Pasamos la fecha_consulta aquí
            render_machine_card(m_name, db, fecha_consulta)

with tab_planta:
    for i in range(0, n_maquinas, 2):
        cols = st.columns(2)
        pareja = lista_maquinas_nombres[i : i + 2]
        for idx, m_name in enumerate(pareja):
            with cols[idx]:
                # Pasamos la fecha_consulta aquí también
                render_machine_card(m_name, db, fecha_consulta)

# --- 5. LÓGICA DE ROTACIÓN ---
# Para evitar que el rerun interrumpa la vista en "Tab Planta", 
# podrías usar un botón de "Pausa" o simplemente dejar que rote el índice.
# Solo rotar y refrescar si estamos viendo "Hoy" y la cámara está apagada
if es_hoy and not run_camera:
    time.sleep(10)
    st.session_state.indice_carrusel = (st.session_state.indice_carrusel + 2) % n_maquinas
    st.rerun()
else:
    st.info("💡 Autorefresco pausado durante consulta histórica.")

#función para guardar evidencias de los test de cabezales
def guardar_evidencia_fisica(imagen_pil, nombre_maquina):
    # 1. Definir la ruta base de evidencias
    base_path = os.path.join(project_root, "evidencias", nombre_maquina)
    
    # 2. Crear la carpeta si no existe
    if not os.path.exists(base_path):
        os.makedirs(base_path)
    
    # 3. Generar nombre de archivo con fecha y hora
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"test_{timestamp}.jpg"
    full_path = os.path.join(base_path, filename)
    
    # 4. Guardar la imagen
    imagen_pil.save(full_path, "JPEG")
    return full_path
# --- SECCIÓN DE CARGA Y ANÁLISIS ---
st.header("📸 Análisis de Test")
uploaded_file = st.file_uploader("Subir imagen del test", type=['jpg', 'png', 'jpeg'])

if uploaded_file:
    img_raw = Image.open(uploaded_file)
    col_edit, col_prev = st.columns([2, 1])
    
    with col_edit:
        st.subheader("✂️ 1. Ajustar y Recortar")
        # Girar imagen
        grados = st.slider("Girar imagen (grados)", -180, 180, 0)
        img_rotated = img_raw.rotate(grados, expand=True)
        
        # --- NUEVO: Selección de Cabezal a Recortar ---
        if 'recortes' not in st.session_state:
            st.session_state.recortes = {}
            
        num_cabezales = st.number_input("Número de cabezales en el test", min_value=1, value=2)
        cabezal_actual = st.selectbox("Selecciona cabezal para recortar:", range(1, num_cabezales + 1))
        
        st.info(f"Recorta el área del **Cabezal {cabezal_actual}** y presiona 'Guardar Recorte'.")
        
        # El Cropper estándar
        img_cropped = st_cropper(img_rotated, realtime_update=True, box_color='#FF0000', aspect_ratio=None, key=f"crop_h{cabezal_actual}")
        
        if st.button(f"💾 Guardar Recorte Cabezal {cabezal_actual}"):
            st.session_state.recortes[cabezal_actual] = img_cropped
            st.success(f"Recorte de Cabezal {cabezal_actual} guardado temporalmente.")

    with col_prev:
        st.subheader("🔍 2. Configuración")
        
        # Mostrar previsualizaciones guardadas
        if st.session_state.recortes:
            st.write("Recortes guardados:")
            cols_pre = st.columns(num_cabezales)
            for h_id, img in st.session_state.recortes.items():
                with cols_pre[h_id-1]:
                    st.image(img, caption=f"Head {h_id}", use_container_width=True)
        
        machine_selected = st.selectbox("Máquina destino:", list(MACHINE_CONFIGS.keys()))
        sensibilidad = st.slider("Sensibilidad", 0.01, 0.20, 0.05)
            
        # --- INICIALIZACIÓN DE VARIABLES DE PROCESAMIENTO ---
        all_maps = []
        total_missing_nodes = 0
        total_nodes = 0
        img_res_final = None  # <--- AGREGA ESTO AQUÍ
        mapas_completos = []

        if st.button("🚀 INICIAR PROCESAMIENTO TOTAL"):
            if not st.session_state.recortes:
                st.error("❌ No hay recortes guardados.")
            else:
                config = MACHINE_CONFIGS[machine_selected]
                for h_id, img_cropped in st.session_state.recortes.items():
                    img_cv = cv2.cvtColor(np.array(img_cropped), cv2.COLOR_RGB2BGR)
                    temp_path = os.path.join(current_dir, f"temp_h{h_id}.jpg")
                    cv2.imwrite(temp_path, img_cv)
                    
                    # PROCESAR
                    mapa, img_res, msg = image_processor.process_test_image_v2(temp_path, config, sensibilidad)
                    
                    if mapa is not None:
                        all_maps.append({"id": h_id, "mapa": mapa})
                        # IMPORTANTE: Asignamos img_res a img_res_final para que no sea None
                        img_res_final = img_res
                        total_missing_nodes += int(np.count_nonzero(mapa == 0))
                        total_nodes += mapa.size
                    else:
                        st.warning(f"⚠️ El Cabezal {h_id} no pudo ser procesado: {msg}")

                # --- LÓGICA DE UNIFICACIÓN VISUAL (SÓLO SI HAY RESULTADOS) ---
                if all_maps and img_res_final is not None:
                    salud_final = ((total_nodes - total_missing_nodes) / total_nodes) * 100
                    
                    # --- LA CORRECCIÓN AQUÍ ---
                    # Convertimos cada mapa de numpy a una lista de Python para que sea serializable
                    mapas_para_db = []
                    for item in all_maps:
                        mapas_para_db.append({
                            "id": item["id"],
                            "mapa": item["mapa"].tolist()  # .tolist() convierte el array de NumPy a lista estándar
                        })
                    # ---------------------------

                    img_evidencia_pil = Image.fromarray(cv2.cvtColor(img_res_final, cv2.COLOR_BGR2RGB))
                    ruta_final = guardar_evidencia_fisica(img_evidencia_pil, machine_selected)
                    
                    # Usamos 'mapas_para_db' en lugar de 'all_maps'
                    crud.save_test_result(db, machine_selected, salud_final, total_missing_nodes, mapas_para_db, ruta_final)
                    
                    st.session_state.mapa_actual = all_maps
                    st.session_state.img_resultado = img_res_final
                    st.success("✅ Datos guardados correctamente")
                    st.rerun()

# --- RESULTADOS DETALLADOS ACTUALIZADOS ---
if st.session_state.mapa_actual is not None:
    st.divider()
    mapas_data = st.session_state.mapa_actual
    
    col_res1, col_res2 = st.columns([1, 1])
    
    with col_res1:
        st.subheader("🖼️ Composición de Cabezales")
        if st.session_state.img_resultado is not None:
            st.image(st.session_state.img_resultado, use_container_width=True)
            
    with col_res2:
        st.subheader("📍 Detalle de Inyectores Fallidos")
        todas_las_fallas = []
        
        # Iteramos sobre la lista de mapas procesados
        for item in mapas_data:
            h_id = item["id"]
            mapa = item["mapa"]
            fallas = np.argwhere(mapa == 0)
            for f in fallas:
                todas_las_fallas.append({
                    "Cabezal": f"Head {h_id}",
                    "Fila": f[0] + 1,
                    "Columna": f[1] + 1
                })
        
        if todas_las_fallas:
            df_fallas = pd.DataFrame(todas_las_fallas)
            st.warning(f"Se detectaron {len(todas_las_fallas)} fallas totales.")
            st.dataframe(df_fallas, height=400, use_container_width=True)
        else:
            st.success("✅ ¡Todos los cabezales están en estado óptimo!")

    if st.button("🧹 Limpiar Resultados"):
        st.session_state.mapa_actual = None
        st.session_state.img_resultado = None
        st.rerun()

# --- PANEL ADMINISTRATIVO ---
if st.session_state.user_role == "admin":
    st.divider()
    st.header("⚙️ Panel de Administración")
    tab1, tab2 = st.tabs(["👥 Gestión de Usuarios", "📊 Reportes Maestros"])
    
    with tab1:
        with st.expander("➕ Crear nuevo usuario"):
            new_user = st.text_input("Nombre de usuario")
            new_pass = st.text_input("Contraseña", type="password")
            new_role = st.selectbox("Rol", ["operator", "admin"])
            if st.button("Registrar"):
                h_pw = hashlib.sha256(new_pass.encode()).hexdigest()
                crud.create_user(db, new_user, h_pw, new_role)
                st.success("Usuario creado")

        st.subheader("Usuarios actuales")
        for u in crud.get_all_users(db):
            c1, c2 = st.columns([3, 1])
            c1.write(f"{u.username} ({u.role})")
            if c2.button("Eliminar", key=f"d_{u.id}"):
                crud.delete_user(db, u.id)
                st.rerun()

    with tab2:
        st.subheader("📈 Tendencia de Salud de Cabezales")
        
        # Obtener datos para la gráfica
        df_history = crud.get_health_history(db)
        
        if not df_history.empty:
            # Pivotar los datos para que Streamlit los entienda: 
            # Una columna por cada máquina, filas por fecha
            chart_data = df_history.pivot(index='Fecha', columns='Máquina', values='Salud')
            
            # Mostrar la gráfica de líneas
            st.line_chart(chart_data)
            
            st.divider()
            st.subheader("📋 Registro Detallado")
            
            # Obtener el reporte semanal (la tabla que ya teníamos)
            df_rep = crud.get_weekly_data(db)
            st.dataframe(df_rep, use_container_width=True)
            
            st.download_button(
                label="📥 Descargar Reporte Completo (CSV)",
                data=df_rep.to_csv(index=False),
                file_name=f"reporte_impresoras_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
            
            
            pdf_bytes = crud.generate_pdf_report(df_rep)
        
            st.download_button(
                label="📄 Descargar Reporte Ejecutivo (PDF)",
                data=pdf_bytes,
                file_name=f"Reporte_Semanal_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf"
            )
        else:
            st.info("Aún no hay suficientes datos para generar gráficas de tendencia.")
            
    with tab2: # O donde tengas tu explorador
        st.subheader("📁 Explorador de Evidencias")
        m_ver = st.selectbox("Seleccionar Máquina:", list(MACHINE_CONFIGS.keys()))
        
        # Construimos la ruta exacta
        path_especifico = os.path.join(EVIDENCIAS_PATH, m_ver)
        
        if os.path.exists(path_especifico):
            # Listamos solo archivos .jpg
            fotos = [f for f in os.listdir(path_especifico) if f.lower().endswith(".jpg")]
            
            if fotos:
                # Ordenar por nombre (que tiene la fecha) para ver la más reciente primero
                fotos_ordenadas = sorted(fotos, reverse=True)
                foto_sel = st.select_slider("Historial de capturas", options=fotos_ordenadas)
                
                img_path = os.path.join(path_especifico, foto_sel)
                st.image(img_path, caption=f"Máquina: {m_ver} | Archivo: {foto_sel}")
            else:
                st.warning(f"No se encontraron imágenes en: {m_ver}")
        else:
            st.info("Aún no se han procesado tests para esta máquina.")        
            

db.close()