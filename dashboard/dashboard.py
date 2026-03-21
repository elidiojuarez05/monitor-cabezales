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
import base64

# Base de datos
import psycopg2

# =========================================================
# 1. CONFIGURACIÓN DE PÁGINA Y TEMA INDUSTRIAL (VA PRIMERO)
# =========================================================
st.set_page_config(page_title="Print Head Monitor", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #e0e6ed; }
    div[data-testid="stMetricValue"] { color: #00ff41; font-family: 'Courier New', Courier, monospace; font-weight: bold; }
    .stButton>button { background-color: #1e3a8a; color: white; border-radius: 4px; border: 1px solid #3b82f6; font-weight: bold; transition: all 0.3s ease; }
    .stButton>button:hover { background-color: #3b82f6; border: 1px solid #60a5fa; box-shadow: 0 0 10px rgba(59, 130, 246, 0.5); }
    div[data-testid="stContainer"] { border-color: #334155 !important; background-color: #1e293b; border-radius: 8px; }
    section[data-testid="stSidebar"] { background-color: #111827; border-right: 1px solid #334155; }
    h1, h2, h3 { color: #f8fafc; font-family: 'Arial', sans-serif; }
    hr { border-color: #334155; }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 2. DEFINICIÓN DE LA BASE DE DATOS (SUPABASE)
# =========================================================
class PostgresDB:
    def __init__(self):
        self.conn = st.connection("postgresql", type="sql", pool_pre_ping=True)

    def safe_read(self, table_name):
        try:
            query = f'SELECT * FROM "{table_name}"'
            return self.conn.query(query, ttl=0)
        except Exception as e:
            return pd.DataFrame() # Retorna tabla vacía si hay error para no tronar la app

    # --- PUENTES TEMPORALES (Reemplazan a GSheetsCRUD para evitar errores) ---
    def get_test_by_date(self, m_name, fecha_consulta):
        # TODO: Implementar búsqueda real en Supabase de la tabla 'tests'
        return None 

    def get_machine_history(self, m_name, limit=10):
        # TODO: Implementar búsqueda real en Supabase
        return pd.DataFrame(columns=['timestamp', 'health_score'])

    def save_test_result(self, machine_name, health, missing, mapa, ruta):
        # TODO: Implementar Insert en Supabase
        st.toast(f"✅ Datos calculados (Salud: {health:.1f}%) - Pendiente guardar en Nube")
        pass

    def get_history_range(self, start, end):
        return pd.DataFrame()

# Iniciamos la conexión de DB una sola vez
db = PostgresDB()

# =========================================================
# 3. CONFIGURACIÓN DE RUTAS Y PATHS
# =========================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    backend_dir = os.path.join(sys._MEIPASS, "backend")
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(BASE_DIR)
    backend_dir = os.path.join(project_root, "backend")

if backend_dir not in sys.path: sys.path.insert(0, backend_dir)

EVIDENCIAS_PATH = os.path.join(BASE_DIR, "evidencias")
REPORTES_PATH = os.path.join(BASE_DIR, "reportes")

for path in [EVIDENCIAS_PATH, REPORTES_PATH]:
    if not os.path.exists(path): os.makedirs(path)

# =========================================================
# 4. IMPORTS DE MÓDULOS PROPIOS
# =========================================================
try:
    import image_processor
    from config import MACHINE_CONFIGS
except ImportError as e:
    st.error(f"Error crítico de importación: {e}")
    st.stop()

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
# 6. FUNCIONES DE APOYO
# =========================================================
def guardar_evidencia_fisica(imagen_pil, nombre_maquina):
    base_path = os.path.join(EVIDENCIAS_PATH, nombre_maquina)
    if not os.path.exists(base_path): os.makedirs(base_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    full_path = os.path.join(base_path, f"test_{timestamp}.jpg")
    imagen_pil.save(full_path, "JPEG")
    return full_path

def render_machine_card(m_name, fecha_consulta, suffix=""):
    last_test = db.get_test_by_date(m_name, fecha_consulta) # Ahora usa PostgresDB
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
            
            history = db.get_machine_history(m_name, limit=10)
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
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("<h2 style='text-align: center;'>🏭 Print Head Monitor</h2>", unsafe_allow_html=True)
        
        with st.container(border=True):
            st.markdown("### 🔐 Acceso al Sistema")
            u_ingreso = st.text_input("ID Operador", key="id_op")
            p_ingreso = st.text_input("Contraseña / PIN", type="password", key="pass_op")
            btn_entrar = st.button("🚀 Entrar al Monitor", use_container_width=True)

        if btn_entrar:
            if u_ingreso and p_ingreso:
                res_usuarios = db.safe_read("usuarios")
                
                if not res_usuarios.empty:
                    res_usuarios.columns = [str(c).lower().strip() for c in res_usuarios.columns]
                    if 'usuario' in res_usuarios.columns:
                        u_clean = u_ingreso.strip().lower()
                        match = res_usuarios[res_usuarios['usuario'].astype(str).str.strip().lower() == u_clean]
                        
                        if not match.empty:
                            stored_pass = str(match.iloc[0]['contrasena'])
                            if p_ingreso == stored_pass:
                                st.session_state.authenticated = True
                                st.session_state.username = u_clean
                                st.session_state.user_role = str(match.iloc[0].get('rol', 'operador'))
                                st.success("✅ Acceso concedido.")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("❌ Contraseña incorrecta.")
                        else:
                            st.error("❌ El usuario no existe.")
                    else:
                        st.error("Error: La columna 'usuario' no existe en la BD.")
                else:
                    st.error("❌ No se pudo conectar con la base de datos (Tabla vacía).")
            else:
                st.warning("⚠️ Escribe tu usuario y contraseña.")
    
    # ¡ESTA LÍNEA ES LA MÁS IMPORTANTE PARA QUE NO TRUENE EL CÓDIGO!
    st.stop() 

# =========================================================
# 8. INTERFAZ PRINCIPAL (POST-LOGIN)
# =========================================================
st.markdown(f"""
    <div style="background: linear-gradient(90deg, #1e293b 0%, #0f172a 100%); padding: 15px; border-radius: 8px; border-left: 5px solid #3b82f6; margin-bottom: 20px;">
        <h1 style="font-size: 32px; color: #f8fafc; margin: 0; font-family: 'Arial', sans-serif;">
            🖨️ Monitor Industrial de Cabezales
        </h1>
        <p style="color: #94a3b8; margin: 5px 0 0 0;">Sistema de Monitoreo de Inyectores en Tiempo Real</p>
    </div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown(f"### 👤 {st.session_state.username}")
    st.caption(f"🎖️ {st.session_state.user_role.upper()}")

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

if run_camera:
    st.info(f"Modo de inspección activo para: **{machine_selected_global}**")
    foto = st.camera_input("Capturar Evidencia de Test")
    
    if foto:
        st.session_state.bloquear_refresco = True
        contenedor_estado = st.empty()
        
        with st.spinner("🔍 Optimizando imagen..."):
            img_bytes = foto.getvalue()
            res = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
            
            if res is not None:
                try:
                    if zoom_level > 0:
                        h, w = res.shape[:2]
                        m_h, m_w = int(h * (zoom_level / 200)), int(w * (zoom_level / 200))
                        res = res[m_h:h-m_h, m_w:w-m_w]

                    temp_p = os.path.join(BASE_DIR, "temp_capture.jpg")
                    cv2.imwrite(temp_p, res)
                    
                    config = MACHINE_CONFIGS[machine_selected_global]
                    mapa, img_res, msg = image_processor.process_test_image_v2(temp_p, config, sensibilidad)
                    
                    if mapa is not None:
                        salud = (np.sum(mapa) / mapa.size) * 100
                        fallas = int(np.count_nonzero(mapa == 0))
                        img_pil = Image.fromarray(cv2.cvtColor(img_res, cv2.COLOR_BGR2RGB))
                        ruta_evidencia = guardar_evidencia_fisica(img_pil, machine_selected_global)
                        
                        # Guardar usando PostgresDB
                        db.save_test_result(machine_selected_global, salud, fallas, mapa.tolist(), ruta_evidencia)
                        
                        contenedor_estado.success(f"✅ Telemetría procesada | Salud: {salud:.1f}%")
                        st.balloons()
                        st.session_state.bloquear_refresco = False
                        time.sleep(2)
                        st.rerun()
                except Exception as e:
                    st.error("❌ Error en la lectura del test.")
                    st.session_state.bloquear_refresco = False

st.divider()
es_hoy = (fecha_consulta == datetime.now().date())
st.subheader(f"📡 Monitor Global ({fecha_consulta.strftime('%d/%m/%Y')})" if es_hoy else f"🗃️ Registro de Planta ({fecha_consulta.strftime('%d/%m/%Y')})")

tab_carrusel, tab_planta, tab_analisis, tab_gestion = st.tabs(["🔄 Auto-Monitoreo", "🏭 Mapa de Planta", "✂️ Ingesta Manual", "⚙️ Hub Administrativo"])

lista_maquinas = list(MACHINE_CONFIGS.keys())

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
                        
                        db.save_test_result(machine_selected_global, salud_final, t_missing, [], ruta_final)
                        
                        st.session_state.recortes = {}
                        st.success("✅ Datos transferidos.")
                        time.sleep(1); st.rerun()

with tab_gestion:
    if st.session_state.user_role != "admin":
        st.warning("⚠️ Nivel de acceso insuficiente. Solo Administradores de Planta.")
    else:
        st.subheader("📈 Rendimiento de Red (7 Días)")
        df_stats = db.get_history_range(datetime.now() - timedelta(days=7), datetime.now())

        if not df_stats.empty:
            df_stats['health_score'] = pd.to_numeric(df_stats['health_score'])
            promedio_real = df_stats.groupby("machine_name")["health_score"].mean()
            full_series = pd.Series(0, index=lista_maquinas)
            grafica_final = promedio_real.combine_first(full_series).sort_index()
            st.bar_chart(grafica_final, color="#3b82f6")
        else:
            st.info("No hay telemetría reciente para graficar (Aún no hay datos en Supabase).")

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
