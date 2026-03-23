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

# =========================================================
# 1. CONFIGURACIÓN DE PÁGINA Y TEMA INDUSTRIAL
# =========================================================
st.set_page_config(page_title="Print Head Monitor", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #e0e6ed; }
    div[data-testid="stMetricValue"] { color: #00ff41; font-family: 'Courier New', Courier, monospace; font-weight: bold; }
    .stButton>button {
        background-color: #1e3a8a; color: white; border-radius: 4px; border: 1px solid #3b82f6; font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton>button:hover { background-color: #3b82f6; border: 1px solid #60a5fa; box-shadow: 0 0 10px rgba(59, 130, 246, 0.5); }
    div[data-testid="stContainer"] { border-color: #334155 !important; background-color: #1e293b; border-radius: 8px; }
    section[data-testid="stSidebar"] { background-color: #111827; border-right: 1px solid #334155; }
    h1, h2, h3 { color: #f8fafc; font-family: 'Arial', sans-serif; }
    hr { border-color: #334155; }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. CONFIGURACIÓN DE RUTAS Y PATHS
# =========================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    backend_dir = os.path.join(sys._MEIPASS, "backend")
    assets_dir = os.path.join(sys._MEIPASS, "assets")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(BASE_DIR)
    backend_dir = os.path.join(project_root, "backend")
    assets_dir = os.path.join(project_root, "assets")

if backend_dir not in sys.path: sys.path.insert(0, backend_dir)

EVIDENCIAS_PATH = os.path.join(BASE_DIR, "evidencias")
REPORTES_PATH = os.path.join(BASE_DIR, "reportes")

for path in [EVIDENCIAS_PATH, REPORTES_PATH]:
    if not os.path.exists(path): os.makedirs(path)

# =========================================================
# 3. IMPORTS DE MÓDULOS PROPIOS (BACKEND)
# =========================================================
try:
    import image_processor
    from config import MACHINE_CONFIGS
    import crud
    import models
except ImportError as e:
    st.error(f"Error crítico de importación del backend: {e}")
    st.stop()

# =========================================================
# 4. CONEXIÓN A BASE DE DATOS Y UTILIDADES
# =========================================================
# Función helper para obtener la sesión de BD de forma segura
def get_db():
    return st.connection("postgresql", type="sql", pool_pre_ping=True).session

def hash_pw(password):
    return hashlib.sha256(str(password).strip().encode('utf-8')).hexdigest().lower()

def guardar_evidencia_fisica(imagen_pil, nombre_maquina):
    base_path = os.path.join(EVIDENCIAS_PATH, nombre_maquina)
    if not os.path.exists(base_path): os.makedirs(base_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    full_path = os.path.join(base_path, f"test_{timestamp}.jpg")
    imagen_pil.save(full_path, "JPEG")
    return full_path

# =========================================================
# 5. INICIALIZACIÓN DE SESSION STATE
# =========================================================
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'user_role' not in st.session_state: st.session_state.user_role = None
if 'username' not in st.session_state: st.session_state.username = None
if 'machine_selected' not in st.session_state: st.session_state.machine_selected = list(MACHINE_CONFIGS.keys())[0]
if 'estados_maquinas' not in st.session_state: st.session_state.estados_maquinas = {name: "Operativa" for name in MACHINE_CONFIGS.keys()}
if 'indice_carrusel' not in st.session_state: st.session_state.indice_carrusel = 0
if 'recortes' not in st.session_state: st.session_state.recortes = {}
if 'bloquear_refresco' not in st.session_state: st.session_state.bloquear_refresco = False

run_camera = False

# =========================================================
# 6. RENDERIZADO DE COMPONENTES
# =========================================================
def render_machine_card(m_name, fecha_consulta, suffix=""):
    with get_db() as db:
        last_test = crud.get_test_by_date(db, m_name, fecha_consulta)
        history = crud.get_machine_history(db, m_name, limit=10)

    estado_actual = st.session_state.estados_maquinas.get(m_name, "Operativa")
    fecha_ultimo = last_test.timestamp.strftime('%d/%m/%Y %H:%M') if last_test else "Sin registros"

    opciones_estilo = {
        "Operativa": {"color_b": "#10b981", "color_f": "rgba(16, 185, 129, 0.05)", "icon": "✅"},
        "Mantenimiento": {"color_b": "#64748b", "color_f": "rgba(100, 116, 139, 0.1)", "icon": "🛠️"},
        "Falla Total": {"color_b": "#ef4444", "color_f": "rgba(239, 68, 68, 0.1)", "icon": "🚫"},
        "Falla de Slots": {"color_b": "#f59e0b", "color_f": "rgba(245, 158, 11, 0.1)", "icon": "🔌"},
        "Falla de Tarjetas": {"color_b": "#06b6d4", "color_f": "rgba(6, 182, 212, 0.1)", "icon": "💾"}
    }
    estilo = opciones_estilo.get(estado_actual, opciones_estilo["Operativa"])
    
    if estado_actual == "Operativa" and last_test:
        salud = float(last_test.health_score)
        if salud < 75: estilo["color_b"] = "#f59e0b"
        if salud < 50: estilo["color_b"] = "#ef4444"
        
        with st.container(border=True):
            st.markdown(f"""
                <div style="height: 60px; border-bottom: 2px solid {estilo['color_b']}; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="margin: 0; color: #f8fafc; font-weight: 700;">{estilo['icon']} {m_name}</h3>
                    <span style="background-color: {estilo['color_b']}; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem;">{estado_actual}</span>
                </div>
            """, unsafe_allow_html=True)
            st.metric("Status de Salud", f"{salud:.1f}%", f"-{last_test.missing_nodes} Nodos", delta_color="inverse")
            st.caption(f"Último escaneo: {fecha_ultimo}")
            
            if not history.empty:
                st.line_chart(history.set_index('timestamp')['health_score'], height=120, color=estilo["color_b"])
    else:
        st.markdown(f"""
            <div style="height: 380px; border: 2px dashed {estilo['color_b']}; border-radius: 10px; padding: 20px; background-color: {estilo['color_f']}; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center;">
                <h1 style="font-size: 3.5em; margin: 0; text-shadow: 0 0 10px {estilo['color_b']};">{estilo['icon']}</h1>
                <h2 style="margin: 10px 0; color: #f8fafc;">{m_name}</h2>
                <div style="background-color: {estilo['color_b']}; color: white; padding: 5px 15px; border-radius: 4px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px;">
                    {estado_actual}
                </div>
                <p style="color: #94a3b8; font-size: 0.9em; margin-top: 20px;">
                    Modo restringido.<br>Último test: {fecha_ultimo}
                </p>
            </div>
        """, unsafe_allow_html=True)

# =========================================================
# 7. LÓGICA DE AUTENTICACIÓN (LOGIN)
# =========================================================
if not st.session_state.get('authenticated', False):
    st.markdown("<style>section[data-testid='stSidebar'] {display: none;}</style>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br><h2 style='text-align: center;'>🏭 Print Head Monitor</h2>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("### 🔐 Acceso al Sistema")
            u_ingreso = st.text_input("ID Operador", key="id_op")
            p_ingreso = st.text_input("Contraseña / PIN", type="password", key="pass_op")
            btn_entrar = st.button("🚀 Entrar al Monitor", use_container_width=True)

        if btn_entrar:
            if u_ingreso and p_ingreso:
                u_clean = u_ingreso.strip().lower()
                try:
                    with get_db() as db:
                        user = crud.get_user_by_username(db, u_clean)
                        if user:
                            stored_hash = str(user.password).strip().lower()
                            if hash_pw(p_ingreso) == stored_hash:
                                st.session_state.authenticated = True
                                st.session_state.username = u_clean
                                st.session_state.user_role = str(user.role).strip().lower()
                                st.success("✅ Acceso concedido.")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("❌ Contraseña incorrecta.")
                        else:
                            st.error("❌ El usuario no existe.")
                except Exception as e:
                    st.error(f"❌ Error conectando a la base de datos: {e}")
            else:
                st.warning("⚠️ Escribe tu usuario y contraseña.")
    st.stop()

# =========================================================
# 8. INTERFAZ PRINCIPAL (POST-LOGIN)
# =========================================================
# --- HEADER ---
st.markdown(f"""
    <div style="background: linear-gradient(90deg, #1e293b 0%, #0f172a 100%); padding: 15px; border-radius: 8px; border-left: 5px solid #3b82f6; margin-bottom: 20px;">
        <h1 style="font-size: 32px; color: #f8fafc; margin: 0; font-family: 'Arial', sans-serif;">
            🖨️ Monitor Industrial de Cabezales
        </h1>
        <p style="color: #94a3b8; margin: 5px 0 0 0;">Sistema de Monitoreo de Inyectores en Tiempo Real</p>
    </div>
""", unsafe_allow_html=True)

# --- SIDEBAR ---
with st.sidebar:
    # --- INTEGRACIÓN DEL LOGO EMPRESARIAL ---
    # Asegúrate de que tu archivo se llame logo.png o ajusta el nombre aquí
    logo_path = os.path.join(assets_dir, "logo.png")
    if os.path.exists(logo_path):
        st.image(logo_path, use_container_width=True)
    
    st.markdown(f"### 👤 {st.session_state.username}")
    st.caption(f"🎖️ {str(st.session_state.user_role).upper()}")

    with st.expander("⚙️ Editar Mi Perfil"):
        new_user_val = st.text_input("Nuevo usuario", value=st.session_state.username)
        new_pass_val = st.text_input("Nueva Contraseña", type="password")
        confirm_pass_val = st.text_input("Confirmar Nueva Contraseña", type="password")
        old_pw = st.text_input("Contraseña Actual", type="password")
        
        if st.button("💾 Guardar Cambios"):
            with get_db() as db:
                user = crud.get_user_by_username(db, st.session_state.username)
                if user and old_pw and hash_pw(old_pw) == str(user.password).strip().lower():
                    if new_pass_val == confirm_pass_val:
                        h_new = hash_pw(new_pass_val) if new_pass_val else hash_pw(old_pw)
                        if crud.update_user_credentials(db, user.id, new_user_val.lower(), h_new):
                            st.session_state.username = new_user_val.lower()
                            st.success("✅ Perfil actualizado")
                            time.sleep(1); st.rerun()
                        else: st.error("❌ Error al actualizar")
                    else: st.error("❌ Contraseñas no coinciden")
                else: st.error("❌ Credenciales inválidas")

    st.divider()
    st.subheader("🛠️ Parámetros de Escaneo")
    machine_selected_global = st.selectbox("Máquina en estación:", list(MACHINE_CONFIGS.keys()))
    sensibilidad = st.slider("Sensibilidad (Nozzles)", 0.01, 0.20, 0.05)
    zoom_level = st.slider("Zoom Digital (Bordes)", 0, 100, 0)
    
    st.divider()
    st.subheader("📷 Control de Estación")
    run_camera = st.toggle("Activar Lente de Inspección", value=False)

    st.divider()
    st.subheader("🛠️ Control de Planta")
    maquina_a_configurar = st.selectbox("Máquina a modificar:", list(MACHINE_CONFIGS.keys()))
    nuevo_est = st.selectbox("Asignar Estado:", ["Operativa", "Mantenimiento", "Falla Total", "Falla de Slots", "Falla de Tarjetas"])
    if st.button("🔄 Forzar Estado", use_container_width=True):
        st.session_state.estados_maquinas[maquina_a_configurar] = nuevo_est
        st.toast(f"{maquina_a_configurar} marcada como {nuevo_est}")

    st.divider()
    fecha_consulta = st.date_input("📅 Turno a consultar:", datetime.now().date())
    
    if st.button("🚪 Desconectar", type="primary", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# --- LÓGICA DE CÁMARA ---
if run_camera:
    st.info(f"Modo de inspección activo para: **{machine_selected_global}**")
    foto = st.camera_input("Capturar Evidencia de Test")
    
    if foto:
        st.session_state.bloquear_refresco = True
        contenedor_estado = st.empty()
        
        with st.spinner("🔍 Optimizando imagen mediante OpenCV..."):
            img_bytes = foto.getvalue()
            res = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
            
            if res is not None:
                try:
                    if zoom_level > 0:
                        h, w = res.shape[:2]
                        m_h, m_w = int(h * (zoom_level / 200)), int(w * (zoom_level / 200))
                        res = res[m_h:h-m_h, m_w:w-m_w]

                    gray = cv2.cvtColor(res, cv2.COLOR_BGR2GRAY)
                    edged = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
                    cnts, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    
                    if cnts:
                        c = max(cnts, key=cv2.contourArea)
                        if cv2.contourArea(c) > 5000:
                            x, y, w, h = cv2.boundingRect(c)
                            res = res[y:y+h, x:x+w]
                            st.toast("🎯 Test aislado y centrado")

                    temp_p = os.path.join(BASE_DIR, "temp_capture.jpg")
                    cv2.imwrite(temp_p, res)
                    
                    config = MACHINE_CONFIGS[machine_selected_global]
                    mapa, img_res, msg = image_processor.process_test_image_v2(temp_p, config, sensibilidad)
                    
                    if mapa is not None:
                        salud = (np.sum(mapa) / mapa.size) * 100
                        fallas = int(np.count_nonzero(mapa == 0))
                        img_pil = Image.fromarray(cv2.cvtColor(img_res, cv2.COLOR_BGR2RGB))
                        
                        ruta_evidencia = guardar_evidencia_fisica(img_pil, machine_selected_global)
                        
                        # Escribir usando CRUD
                        with get_db() as db:
                            crud.save_test_result(db, machine_selected_global, salud, fallas, str(mapa.tolist()), ruta_evidencia)
                        
                        contenedor_estado.success(f"✅ Telemetría guardada en la nube | Salud: {salud:.1f}%")
                        st.balloons()
                        
                        st.session_state.bloquear_refresco = False
                        time.sleep(2)
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"❌ Error en la lectura del test: {e}")
                    st.session_state.bloquear_refresco = False
            else:
                st.warning("⚠️ Fallo en el feed de la cámara.")
                st.session_state.bloquear_refresco = False

# --- TABS PRINCIPALES ---
st.divider()
es_hoy = (fecha_consulta == datetime.now().date())
st.subheader(f"📡 Monitor Global ({fecha_consulta.strftime('%d/%m/%Y')})" if es_hoy else f"🗃️ Registro de Planta ({fecha_consulta.strftime('%d/%m/%Y')})")

tab_carrusel, tab_planta, tab_analisis, tab_gestion = st.tabs(["🔄 Auto-Monitoreo", "🏭 Mapa de Planta", "✂️ Ingesta Manual", "⚙️ Hub Administrativo"])

lista_maquinas = list(MACHINE_CONFIGS.keys())

# TAB 1 & 2: VISTAS DE PLANTA
with tab_carrusel:
    idx = st.session_state.indice_carrusel
    cols_car = st.columns(2)
    for i, m_name in enumerate(lista_maquinas[idx : idx + 2]):
        with cols_car[i]: render_machine_card(m_name, fecha_consulta, suffix="car")

with tab_planta:
    for i in range(0, len(lista_maquinas), 2):
        cols = st.columns(2)
        for j, m_name in enumerate(lista_maquinas[i : i + 2]):
            with cols[j]: render_machine_card(m_name, fecha_consulta, suffix="gral")

# TAB 3: ANÁLISIS MANUAL
with tab_analisis:
    uploaded_file = st.file_uploader("Ingresar fotografía de test manual", type=['jpg', 'png', 'jpeg'], key="up_manual")
    if uploaded_file:
        img_raw = Image.open(uploaded_file)
        col_edit, col_prev = st.columns([2, 1])
        with col_edit:
            grados = st.slider("Calibración de ángulo", -180, 180, 0)
            img_rotated = img_raw.rotate(grados, expand=True)
            num_cabezales = st.number_input("Cantidad de módulos", min_value=1, value=2)
            cabezal_actual = st.selectbox("Módulo activo:", range(1, num_cabezales + 1))
            img_cropped = st_cropper(img_rotated, realtime_update=False, box_color='#00ff41', aspect_ratio=None, key=f"crop_{cabezal_actual}")
            if st.button(f"💾 Cargar Módulo {cabezal_actual}"):
                st.session_state.recortes[cabezal_actual] = img_cropped
                st.success("Módulo en memoria.")
        with col_prev:
            if st.session_state.recortes:
                for h_id, img in st.session_state.recortes.items(): st.image(img, caption=f"Módulo {h_id}")
            if st.button("🚀 PROCESAR LOTE", use_container_width=True, type="primary"):
                if not st.session_state.recortes: st.error("Lote vacío.")
                else:
                    config = MACHINE_CONFIGS[machine_selected_global]
                    t_missing, t_nodes = 0, 0
                    img_res_final = None
                    for h_id, img_c in st.session_state.recortes.items():
                        temp_path = os.path.join(BASE_DIR, f"temp_h{h_id}.jpg")
                        cv2.imwrite(temp_path, cv2.cvtColor(np.array(img_c), cv2.COLOR_RGB2BGR))
                        mapa, img_res, msg = image_processor.process_test_image_v2(temp_path, config, sensibilidad)
                        if mapa is not None:
                            img_res_final = img_res
                            t_missing += int(np.count_nonzero(mapa == 0))
                            t_nodes += mapa.size
                    if img_res_final is not None:
                        salud_final = ((t_nodes - t_missing) / t_nodes) * 100
                        ruta_final = guardar_evidencia_fisica(Image.fromarray(cv2.cvtColor(img_res_final, cv2.COLOR_BGR2RGB)), machine_selected_global)
                        
                        # Escribir usando CRUD
                        with get_db() as db:
                            crud.save_test_result(db, machine_selected_global, salud_final, t_missing, str(mapa.tolist()), ruta_final)
                        
                        st.session_state.recortes = {}
                        st.success("✅ Datos transferidos a la base de datos.")
                        time.sleep(1); st.rerun()

# TAB 4: GESTIÓN (ADMINISTRATIVA Y REPORTES)
with tab_gestion:
    if st.session_state.user_role != "admin":
        st.warning("⚠️ Nivel de acceso insuficiente. Solo Administradores de Planta.")
    else:
        tab_admin_users, tab_admin_reports = st.tabs(["👥 Gestión de Usuarios", "📊 Reportes y Telemetría"])
        
        # --- SECCIÓN: USUARIOS ---
        with tab_admin_users:
            st.subheader("📋 Directorio de Usuarios Activos")
            
            with get_db() as db:
                all_users = crud.get_all_users(db)
                # Formateamos los usuarios a un df rápido para visualizarlos
                if all_users:
                    df_users = pd.DataFrame([{"usuario": u.username, "rol": u.role} for u in all_users])
                    st.dataframe(df_users, use_container_width=True, hide_index=True)
                    
                    st.divider()
                    col_new, col_del = st.columns(2)
                    
                    with col_new:
                        with st.expander("➕ Registrar Nuevo Usuario", expanded=False):
                            st.markdown("### Datos de Acceso")
                            nu_user = st.text_input("ID de Usuario (Ej: op_01)", key="new_u_input")
                            nu_pass = st.text_input("Contraseña / PIN", type="password", key="new_p_input")
                            nu_rol = st.selectbox("Nivel de Permisos", ["operador", "admin"], key="new_r_input")
                            
                            if st.button("🚀 Confirmar Registro", use_container_width=True):
                                if nu_user and nu_pass:
                                    hashed_pass = hash_pw(nu_pass)
                                    crud.create_user(db, nu_user.lower(), hashed_pass, nu_rol)
                                    st.success(f"✅ '{nu_user}' añadido.")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("⚠️ Completa todos los campos.")
            
                    with col_del:
                        with st.expander("🗑️ Dar de Baja Usuario", expanded=False):
                            st.markdown("### Zona de Peligro")
                            user_list = df_users['usuario'].tolist()
                            user_to_delete = st.selectbox("Seleccione cuenta a borrar:", user_list, key="del_u_select")
                            
                            st.warning(f"Se eliminará permanentemente a: {user_to_delete}")
                            if st.button("❌ Ejecutar Baja", type="primary", use_container_width=True):
                                if user_to_delete == st.session_state.username:
                                    st.error("🚫 No puedes eliminar tu propia sesión activa.")
                                else:
                                    if crud.delete_user(db, user_to_delete):
                                        st.success(f"✅ Usuario '{user_to_delete}' removido.")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error("Error al eliminar usuario.")
                else:
                    st.error("❌ No hay usuarios en la base de datos o fallo de conexión.")

        # --- SECCIÓN: REPORTES ---
        with tab_admin_reports:
            st.subheader("📈 Rendimiento de Red (7 Días)")
            with get_db() as db:
                df_stats = crud.get_history_range(db, datetime.now().date() - timedelta(days=7), datetime.now().date())

            if not df_stats.empty:
                # Ajustamos los nombres de columnas a como las retorna tu crud.get_history_range
                # El DataFrame retorna: ["Fecha", "Máquina", "Salud %", "Nodos Caídos"]
                df_stats['Salud %'] = pd.to_numeric(df_stats['Salud %'])
                promedio_real = df_stats.groupby("Máquina")["Salud %"].mean()
                full_series = pd.Series(0, index=lista_maquinas)
                grafica_final = promedio_real.combine_first(full_series).sort_index()
                st.bar_chart(grafica_final, color="#3b82f6")
            else:
                st.info("No hay telemetría reciente para graficar.")

            st.divider()
            st.subheader("📄 Exportación de Datos en Lote")
            c_r1, c_r2 = st.columns(2)
            f_i = c_r1.date_input("Fecha Inicio", value=datetime.now()-timedelta(days=7))
            f_f = c_r2.date_input("Fecha Fin")
            
            if st.button("📊 Extraer Archivos CSV", use_container_width=True):
                with get_db() as db:
                    datos = crud.get_history_range(db, f_i, f_f)
                    
                if not datos.empty:
                    st.session_state.archivo_csv_listo = datos.to_csv(index=False).encode('utf-8')
                    st.session_state.mostrar_descargas = True
                    st.success("✅ Paquete de datos listo.")
                else:
                    st.warning("Sin registros en el intervalo seleccionado.")

            if st.session_state.get("mostrar_descargas") and hasattr(st.session_state, 'archivo_csv_listo'):
                st.download_button("📉 DESCARGAR MATRIZ CSV", st.session_state.archivo_csv_listo, "Telemetria_Planta.csv", "text/csv", use_container_width=True)

# =========================================================
# MOTOR DE SINCRONIZACIÓN AUTOMÁTICA
# =========================================================
if st.session_state.authenticated:
    interactuando = (
        st.session_state.get("bloquear_refresco", False) or 
        run_camera or 
        st.session_state.get("mostrar_descargas", False) or
        (uploaded_file is not None)
    )

    if not interactuando:
        time.sleep(15) 
        if len(lista_maquinas) > 0:
            st.session_state.indice_carrusel = (st.session_state.indice_carrusel + 2) % len(lista_maquinas)
        st.rerun()
    else:
        st.sidebar.caption("⏸️ Telemetría pausada por operación manual")
