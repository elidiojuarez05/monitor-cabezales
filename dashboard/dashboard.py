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
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase, WebRtcMode
import qrcode
from io import BytesIO
import base64


# --- CONFIGURACIÓN DE RUTAS PARA EL EJECUTABLE ---
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    # En el EXE, backend está en la raíz del paquete temporal
    backend_dir = os.path.join(sys._MEIPASS, "backend")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(BASE_DIR)
    backend_dir = os.path.join(project_root, "backend")

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Esto garantiza que la base de datos y evidencias NO se borren al cerrar
EVIDENCIAS_PATH = os.path.join(BASE_DIR, "evidencias")
REPORTES_PATH = os.path.join(BASE_DIR, "reportes")
# =========================================================
# 1. CONFIGURACIÓN DE PÁGINA (DEBE SER EL PRIMER COMANDO)
# =========================================================
st.set_page_config(page_title="Print Head Monitor", layout="wide")

st.markdown("""
    <style>
    /* Forzar que los iconos de la barra lateral sean visibles */
    [data-testid="stSidebarNav"] {
        background-color: rgba(100, 100, 100, 0.1);
    }
    /* Asegurar que el botón de cerrar/abrir sidebar se vea */
    .st-emotion-cache-1avcm0n {
        color: orange !important;
    }
    </style>
    """, unsafe_allow_html=True)
# =========================================================
# 2. CONFIGURACIÓN DE RUTAS Y PATHS
# =========================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
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
# 3. IMPORTS DE MÓDULOS PROPIOS
# =========================================================
try:
    import database
    import crud
    import image_processor
    from config import MACHINE_CONFIGS
except ImportError as e:
    st.error(f"Error crítico de importación: {e}")
    st.stop()

# =========================================================
# 4. INICIALIZACIÓN DE SESSION STATE Y VARIABLES GLOBALES
# =========================================================
# Seguridad y Autenticación
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'user_role' not in st.session_state: st.session_state.user_role = None
if 'username' not in st.session_state: st.session_state.username = None

# --- AGREGA ESTA LÍNEA AQUÍ ---
if 'machine_selected' not in st.session_state: 
    st.session_state.machine_selected = list(MACHINE_CONFIGS.keys())[0]
# Operación de Planta
if 'estados_maquinas' not in st.session_state: st.session_state.estados_maquinas = {name: "Operativa" for name in MACHINE_CONFIGS.keys()}
if 'indice_carrusel' not in st.session_state: st.session_state.indice_carrusel = 0

# Procesamiento de Imágenes
if 'mapa_actual' not in st.session_state: st.session_state.mapa_actual = None
if 'img_resultado' not in st.session_state: st.session_state.img_resultado = None
if 'recortes' not in st.session_state: st.session_state.recortes = {}

# Anti-Parpadeo y Reportes
if 'bloquear_refresco' not in st.session_state: st.session_state.bloquear_refresco = False
if 'mostrar_descarga_pdf' not in st.session_state: st.session_state.mostrar_descarga_pdf = False
if 'archivo_pdf_listo' not in st.session_state: st.session_state.archivo_pdf_listo = None


# Variables por defecto para evitar errores
run_camera = False

# =========================================================
# 5. FUNCIONES DE APOYO Y BASE DE DATOS
# =========================================================
database.Base.metadata.create_all(bind=database.engine)
db = database.SessionLocal()

def init_admin_user(db_session):
    admin_user = "admin"
    hashed_pw = hashlib.sha256("system123".encode()).hexdigest()
    if not crud.get_user_by_username(db_session, admin_user):
        crud.create_user(db_session, admin_user, hashed_pw, role="admin")

init_admin_user(db)

def check_password(db_session, username, password):
    user = crud.get_user_by_username(db_session, username)
    if user and user.password == hashlib.sha256(password.encode()).hexdigest():
        return user
    return None

def guardar_evidencia_fisica(imagen_pil, nombre_maquina):
    base_path = os.path.join(EVIDENCIAS_PATH, nombre_maquina)
    if not os.path.exists(base_path): os.makedirs(base_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    full_path = os.path.join(base_path, f"test_{timestamp}.jpg")
    imagen_pil.save(full_path, "JPEG")
    return full_path

def render_machine_card(m_name, db_session, fecha_consulta, suffix=""):
    last_test = crud.get_test_by_date(db_session, m_name, fecha_consulta)
    estado_actual = st.session_state.estados_maquinas.get(m_name, "Operativa")
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
            history = crud.get_machine_history(db_session, m_name, limit=10)
            if not history.empty:
                st.area_chart(history.set_index('timestamp')['health_score'], height=150, color=[estilo["color_b"]])
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
# 6. LÓGICA DE AUTENTICACIÓN (LOGIN) - CORREGIDO DEFINITIVO
# =========================================================
if not st.session_state.authenticated:
    st.title("🔐 Acceso al Sistema")
    
    # Quitamos el st.form para evitar el bug del parpadeo con st.stop()
    user_input = st.text_input("Usuario")
    pass_input = st.text_input("Contraseña", type="password")
    
    if st.button("Entrar", type="primary"):
        user = check_password(db, user_input, pass_input)
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
                user_db = crud.get_user_by_username(db, st.session_state.username)
                if user_db and user_db.password == hashlib.sha256(old_pw.encode()).hexdigest():
                    if new_pass_val == confirm_pass_val:
                        h_new = hashlib.sha256(new_pass_val.encode()).hexdigest() if new_pass_val else user_db.password
                        if crud.update_user_credentials(db, user_db.id, new_user_val, h_new):
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
    nuevo_est = st.selectbox("Definir estado:", ["Operativa", "Mantenimiento", "Falla Total", "Falla de Slots", "Falla de Tarjetas"], 
                             index=["Operativa", "Mantenimiento", "Falla Total", "Falla de Slots", "Falla de Tarjetas"].index(st.session_state.estados_maquinas.get(maquina_a_configurar, "Operativa")))
    if st.button("🔄 Actualizar Estado"):
        st.session_state.estados_maquinas[maquina_a_configurar] = nuevo_est
        st.success(f"{maquina_a_configurar} -> {nuevo_est}")
        time.sleep(1)
        st.rerun()

    st.divider()
    fecha_consulta = st.date_input("📅 Consultar estado al día:", datetime.now().date())
    
    if st.button("Cerrar Sesión"):
        st.session_state.authenticated = False
        st.rerun()

# --- LÓGICA DE CÁMARA (MODO FOTO - CORREGIDO) ---
foto = None
if foto:
        st.session_state.bloquear_refresco = True
        
        with st.spinner("🔍 Optimizando imagen para análisis..."):
            img_bytes = foto.getvalue()
            res = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
            
            # --- ESCUDO DE SEGURIDAD TOTAL ---
            if res is not None:
                try:
                    # 1. Aplicamos el Zoom Digital
                    if zoom_level > 0:
                        h, w = res.shape[:2]
                        m_h, m_w = int(h * (zoom_level / 200)), int(w * (zoom_level / 200))
                        res = res[m_h:h-m_h, m_w:w-m_w]

                    # 2. Convertimos a grises
                    gray = cv2.cvtColor(res, cv2.COLOR_BGR2GRAY)
                    
                    # 3. TODO el procesamiento va AQUÍ ADENTRO del try
                    edged = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
                    cnts, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    
                    if cnts:
                        c = max(cnts, key=cv2.contourArea)
                        if cv2.contourArea(c) > 5000: # Filtro para evitar ruido
                            x, y, w, h = cv2.boundingRect(c)
                            res = res[y:y+h, x:x+w]
                            st.toast("🎯 Test detectado y centrado")

                    # 4. Guardar temporal y procesar el mapa de inyectores
                    temp_p = os.path.join(BASE_DIR, "temp_capture.jpg")
                    cv2.imwrite(temp_p, res)
                    
                    config = MACHINE_CONFIGS[machine_selected_global]
                    mapa, img_res, msg = image_processor.process_test_image_v2(temp_p, config, sensibilidad)
                    
                    if mapa is not None:
                        # 5. Calcular métricas y guardar
                        salud = (np.sum(mapa) / mapa.size) * 100
                        fallas = int(np.count_nonzero(mapa == 0))
                        img_pil = Image.fromarray(cv2.cvtColor(img_res, cv2.COLOR_BGR2RGB))
                        
                        ruta_evidencia = guardar_evidencia_fisica(img_pil, machine_selected_global)
                        
                        crud.save_test_result(db, machine_selected_global, salud, fallas, mapa.tolist(), ruta_evidencia)
                        db.commit() 
                        
                        contenedor_estado.success(f"✅ ¡{machine_selected_global} Actualizada! ({salud:.1f}%)")
                        st.balloons()
                        
                        st.session_state.bloquear_refresco = False
                        time.sleep(2)
                        st.rerun()
                        
                except Exception as e:
                    # Si cualquier cosa falla, lo atrapamos aquí sin que se caiga la app
                    st.error("❌ La imagen estaba borrosa o la cámara falló. Por favor, intenta tomar la foto de nuevo.")
                    st.session_state.bloquear_refresco = False
            else:
                st.warning("⚠️ Esperando señal de la cámara... Asegúrate de dar permisos en tu celular.")
                st.session_state.bloquear_refresco = False
            
            if cnts:
                c = max(cnts, key=cv2.contourArea)
                if cv2.contourArea(c) > 5000: # Filtro para evitar ruido
                    x, y, w, h = cv2.boundingRect(c)
                    res = res[y:y+h, x:x+w]
                    st.toast("🎯 Test detectado y centrado")

            # Guardar temporal para el procesador final
            temp_p = os.path.join(BASE_DIR, "temp_capture.jpg")
            cv2.imwrite(temp_p, res)
            
            # Procesar con la configuración de la máquina
            config = MACHINE_CONFIGS[machine_selected_global]
            mapa, img_res, msg = image_processor.process_test_image_v2(temp_p, config, sensibilidad)
            
            if mapa is not None:
                # 2. Calcular métricas
                salud = (np.sum(mapa) / mapa.size) * 100
                fallas = int(np.count_nonzero(mapa == 0))
                img_pil = Image.fromarray(cv2.cvtColor(img_res, cv2.COLOR_BGR2RGB))
                
                # CAMBIO: Usar 'machine_selected_global' para la ruta y base de datos
                ruta_evidencia = guardar_evidencia_fisica(img_pil, machine_selected_global)
                
                # Guardar y confirmar transacción
                crud.save_test_result(db, machine_selected_global, salud, fallas, mapa.tolist(), ruta_evidencia)
                db.commit() 
                
                # 3. Notificar éxito
                contenedor_estado.success(f"✅ ¡{machine_selected_global} Actualizada! ({salud:.1f}%)")
                st.balloons()
                
                st.session_state.bloquear_refresco = False
                time.sleep(2)
                st.rerun()
# --- TABS PRINCIPALES ---
st.divider()
es_hoy = (fecha_consulta == datetime.now().date())
st.subheader(f"📊 Monitoreo en Tiempo Real ({fecha_consulta.strftime('%d/%m/%Y')})" if es_hoy else f"📅 Historial de Planta: {fecha_consulta.strftime('%d/%m/%Y')}")

tab_carrusel, tab_planta, tab_analisis, tab_gestion, = st.tabs(["🔄 Modo Carrusel", "🏬 Vista General", "✂️ Análisis Manual", "⚙️ Gestión y Reportes"])

lista_maquinas = list(MACHINE_CONFIGS.keys())

# TAB 1: CARRUSEL
with tab_carrusel:
    idx = st.session_state.indice_carrusel
    cols_car = st.columns(2)
    for i, m_name in enumerate(lista_maquinas[idx : idx + 2]):
        with cols_car[i]: render_machine_card(m_name, db, fecha_consulta, suffix="car")

# TAB 2: VISTA GENERAL
with tab_planta:
    for i in range(0, len(lista_maquinas), 2):
        cols = st.columns(2)
        for j, m_name in enumerate(lista_maquinas[i : i + 2]):
            with cols[j]: render_machine_card(m_name, db, fecha_consulta, suffix="gral")

# TAB 3: ANÁLISIS MANUAL Y CROPPER
with tab_analisis:
    st.info("Sube una imagen y recorta los cabezales manualmente.")
    uploaded_file = st.file_uploader("Subir imagen del test", type=['jpg', 'png', 'jpeg'], key="up_manual")
    if uploaded_file:
        img_raw = Image.open(uploaded_file)
        col_edit, col_prev = st.columns([2, 1])
        with col_edit:
            grados = st.slider("Girar imagen", -180, 180, 0)
            img_rotated = img_raw.rotate(grados, expand=True)
            num_cabezales = st.number_input("Número de cabezales", min_value=1, value=2)
            cabezal_actual = st.selectbox("Selecciona cabezal:", range(1, num_cabezales + 1))
            img_cropped = st_cropper(img_rotated, realtime_update=False, box_color='#FF0000', aspect_ratio=None, key=f"crop_{cabezal_actual}")
            if st.button(f"💾 Guardar Recorte {cabezal_actual}"):
                st.session_state.recortes[cabezal_actual] = img_cropped
                st.success("Guardado temporalmente.")
        with col_prev:
            if st.session_state.recortes:
                st.write("Recortes guardados:")
                for h_id, img in st.session_state.recortes.items(): st.image(img, caption=f"Head {h_id}")
            if st.button("🚀 INICIAR PROCESAMIENTO TOTAL", use_container_width=True):
                if not st.session_state.recortes: st.error("Faltan recortes.")
                else:
                    config = MACHINE_CONFIGS[machine_selected_global]
                    all_maps, t_missing, t_nodes = [], 0, 0
                    img_res_final = None
                    for h_id, img_c in st.session_state.recortes.items():
                        temp_path = os.path.join(BASE_DIR, f"temp_h{h_id}.jpg")
                        cv2.imwrite(temp_path, cv2.cvtColor(np.array(img_c), cv2.COLOR_RGB2BGR))
                        mapa, img_res, msg = image_processor.process_test_image_v2(temp_path, config, sensibilidad)
                        if mapa is not None:
                            all_maps.append({"id": h_id, "mapa": mapa.tolist()})
                            img_res_final, t_missing, t_nodes = img_res, t_missing + int(np.count_nonzero(mapa == 0)), t_nodes + mapa.size
                    if all_maps and img_res_final is not None:
                        salud_final = ((t_nodes - t_missing) / t_nodes) * 100
                        ruta_final = guardar_evidencia_fisica(Image.fromarray(cv2.cvtColor(img_res_final, cv2.COLOR_BGR2RGB)), machine_selected_global)
                        crud.save_test_result(db, machine_selected_global, salud_final, t_missing, all_maps, ruta_final)
                        st.session_state.recortes = {} # Limpiamos
                        st.success("✅ Guardado en base de datos.")
                        time.sleep(1)
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
        
        # --- KPI GLOBAL: RENDIMIENTO SEMANAL ---
        st.subheader("📈 Rendimiento General (Últimos 7 días)")
        df_stats = crud.get_history_range(db, datetime.now() - timedelta(days=7), datetime.now())

        # Creamos una lista con todas las máquinas configuradas
        todas_las_maquinas = list(MACHINE_CONFIGS.keys())

        if not df_stats.empty:
            # Calculamos el promedio actual
            promedio_real = df_stats.groupby("Máquina")["Salud %"].mean()
            
            # Creamos una serie base con todas las máquinas en 0
            full_series = pd.Series(0, index=todas_las_maquinas)
            
            # Combinamos ambos: lo que no existe se queda en 0
            grafica_final = promedio_real.combine_first(full_series).sort_index()
            
            st.bar_chart(grafica_final, color="#28a745")
        else:
            # Si no hay nada, mostramos todas las máquinas en cero
            vacio = pd.Series(0, index=todas_las_maquinas)
            st.bar_chart(vacio, color="#6c757d")
            st.info("No hay datos recientes. Todas las máquinas se muestran en 0%.")

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
                            if crud.create_user(db, new_u, h_pw, role=new_r):
                                st.success("Usuario creado con éxito")
                                time.sleep(1); st.rerun()
                            else: st.error("El usuario ya existe")
        
        with col_u2:
            with st.expander("🗑️ Eliminar Acceso"):
                users = crud.get_all_users(db) # Asegúrate de crear esta función en crud.py
                lista_nombres = [u.username for u in users if u.username != st.session_state.username]
                u_eliminar = st.selectbox("Seleccionar usuario", lista_nombres)
                confirm = st.checkbox("Confirmo eliminación permanente")
                if st.button("Eliminar Usuario"):
                    if confirm and crud.delete_user(db, u_eliminar):
                        st.success(f"Usuario {u_eliminar} borrado")
                        time.sleep(1); st.rerun()

        st.divider()

        # --- REPORTES ---
        st.subheader("📄 Generación de Documentos Oficiales")
        c_r1, c_r2 = st.columns(2)
        f_i = c_r1.date_input("Desde", value=datetime.now()-timedelta(days=7), key="admin_f1")
        f_f = c_r2.date_input("Hasta", key="admin_f2")
        
        if st.button("📊 Preparar Archivos para Descarga", use_container_width=True):
            st.session_state.bloquear_refresco = True
            datos = crud.get_history_range(db, f_i, f_f)
            if not datos.empty:
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
# =========================================================
# MOTOR DE SINCRONIZACIÓN ÚNICO (VERSION ANTI-LOGOUT)
# =========================================================
# Solo activamos el refresco si el usuario está logueado
if st.session_state.authenticated:
    # Definimos qué actividades bloquean el refresco para no interrumpir al usuario
    interactuando = (
        st.session_state.get("bloquear_refresco", False) or 
        run_camera or 
        st.session_state.get("mostrar_descargas", False) or
        uploaded_file is not None # Si está subiendo un archivo manualmente
    )

    if not interactuando:
        # Tiempo de espera (12 segundos para la oficina es ideal)
        time.sleep(12) 
        
        # 1. Avanzar carrusel lógicamente
        num_maquinas = len(lista_maquinas)
        if num_maquinas > 0:
            st.session_state.indice_carrusel = (st.session_state.indice_carrusel + 2) % num_maquinas
        
        # 2. Forzar refresco manteniendo la sesión activa
        st.rerun()
    else:
        # Pequeño aviso visual opcional en el sidebar para saber que el refresco está en pausa
        st.sidebar.caption("⏸️ Actualización en pausa (Usuario activo)")   

db.close()
