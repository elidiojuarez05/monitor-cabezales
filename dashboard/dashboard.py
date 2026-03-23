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

# =========================================================
# 1. CONFIGURACIÓN DE RUTAS (BACKEND Y ASSETS)
# =========================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    backend_dir = os.path.join(sys._MEIPASS, "backend")
else:
    # Si dashboard.py está dentro de una carpeta /dashboard/
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(BASE_DIR)
    backend_dir = os.path.join(project_root, "backend")

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Directorios de datos
EVIDENCIAS_PATH = os.path.join(BASE_DIR, "evidencias")
REPORTES_PATH = os.path.join(BASE_DIR, "reportes")
for path in [EVIDENCIAS_PATH, REPORTES_PATH]:
    if not os.path.exists(path): os.makedirs(path)

# =========================================================
# 2. CONFIGURACIÓN DE PÁGINA E IMPORTS
# =========================================================
st.set_page_config(page_title="Print Head Monitor", layout="wide", initial_sidebar_state="expanded")

try:
    import database
    import crud
    import image_processor
    from config import MACHINE_CONFIGS
except ImportError as e:
    st.error(f"Error al conectar con backend: {e}")
    st.stop()

# =========================================================
# 3. INICIALIZACIÓN DE ESTADOS
# =========================================================
if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'user_role' not in st.session_state: st.session_state.user_role = None
if 'username' not in st.session_state: st.session_state.username = None
if 'recortes' not in st.session_state: st.session_state.recortes = {}
if 'estados_maquinas' not in st.session_state: 
    st.session_state.estados_maquinas = {name: "Operativa" for name in MACHINE_CONFIGS.keys()}
if 'indice_carrusel' not in st.session_state: st.session_state.indice_carrusel = 0

# Conexión DB
database.Base.metadata.create_all(bind=database.engine)
db = database.SessionLocal()

# =========================================================
# 4. FUNCIONES DE APOYO
# =========================================================
def guardar_evidencia_fisica(imagen_pil, nombre_maquina):
    base_path = os.path.join(EVIDENCIAS_PATH, nombre_maquina)
    if not os.path.exists(base_path): os.makedirs(base_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    full_path = os.path.join(base_path, f"test_{timestamp}.jpg")
    imagen_pil.save(full_path, "JPEG")
    return full_path

# =========================================================
# 5. LOGIN
# =========================================================
if not st.session_state.authenticated:
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.title("🔐 Acceso al Sistema")
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.button("Entrar", type="primary", use_container_width=True):
            user = crud.get_user_by_username(db, u)
            if user and user.password == hashlib.sha256(p.encode()).hexdigest():
                st.session_state.update({"authenticated": True, "user_role": user.role, "username": user.username})
                st.rerun()
            else: st.error("Credenciales incorrectas")
    st.stop()

# =========================================================
# 6. SIDEBAR Y CABECERA
# =========================================================
# Logo desde assets
ruta_logo = os.path.join(project_root, "assets", "logo.png") if not getattr(sys, 'frozen', False) else os.path.join(BASE_DIR, "assets", "logo.png")

with st.sidebar:
    if os.path.exists(ruta_logo):
        st.image(ruta_logo, width=150)
    st.title("Monitor de Cabezales")
    st.write(f"👤 **{st.session_state.username}** ({st.session_state.user_role})")
    
    st.divider()
    machine_selected_global = st.selectbox("Máquina destino:", list(MACHINE_CONFIGS.keys()))
    sensibilidad = st.slider("Sensibilidad (Umbral)", 0.01, 0.20, 0.05)
    
    st.divider()
    run_camera = st.checkbox("📷 Activar Cámara de Escaneo")
    fecha_consulta = st.date_input("📅 Ver historial al:", datetime.now().date())
    
    if st.button("🚪 Cerrar Sesión"):
        st.session_state.authenticated = False
        st.rerun()

# =========================================================
# 7. ESTACIÓN DE ESCANEO (CÁMARA)
# =========================================================
if run_camera:
    st.subheader(f"📸 Escaneando para: {machine_selected_global}")
    foto = st.camera_input("Toma la foto del test")
    if foto:
        with st.spinner("Procesando..."):
            temp_p = os.path.join(BASE_DIR, "temp_capture.jpg")
            with open(temp_p, "wb") as f: f.write(foto.getbuffer())
            
            config = MACHINE_CONFIGS[machine_selected_global]
            mapa, img_res, msg = image_processor.process_test_image_v2(temp_p, config, sensibilidad)
            
            if mapa is not None:
                salud = (np.sum(mapa) / mapa.size) * 100
                fallas = int(np.count_nonzero(mapa == 0))
                img_pil = Image.fromarray(cv2.cvtColor(img_res, cv2.COLOR_BGR2RGB))
                ruta_ev = guardar_evidencia_fisica(img_pil, machine_selected_global)
                
                crud.save_test_result(db, machine_selected_global, salud, fallas, mapa.tolist(), ruta_ev)
                st.success(f"✅ ¡Actualizado! Salud: {salud:.1f}%")
                st.balloons()
                time.sleep(2)
                st.rerun()

# =========================================================
# 8. TABS PRINCIPALES
# ========================================================

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
# --- TAB ANÁLISIS MANUAL (CORREGIDO ROTACIÓN) ---
with tab_manual:
    st.info("Sube una imagen y usa el recuadro para seleccionar el área de inyectores.")
    up = st.file_uploader("Imagen del test", type=['jpg', 'png'], key="manual_up")
    
    if up:
        img_raw = Image.open(up)
        c1, c2 = st.columns([2, 1])
        
        with c1:
            grados = st.select_slider("Girar imagen (°)", options=[0, 90, 180, 270], value=0)
            img_rotated = img_raw.rotate(grados, expand=True)
            
            # CLAVE: Añadir 'grados' al key para forzar el refresco al rotar
            img_cropped = st_cropper(img_rotated, realtime_update=True, box_color='#FF0000', key=f"cropper_{grados}")
            
            if st.button("💾 Guardar este recorte"):
                idx_recorte = len(st.session_state.recortes) + 1
                st.session_state.recortes[idx_recorte] = img_cropped
                st.toast(f"Recorte {idx_recorte} guardado")

        with c2:
            st.write("### Recortes Listos")
            if st.session_state.recortes:
                for id_r, im in st.session_state.recortes.items():
                    st.image(im, caption=f"Parte {id_r}", width=150)
                
                if st.button("🚀 PROCESAR TODO", use_container_width=True):
                    # Aquí llamarías a la lógica de procesamiento por lotes que ya tenías
                    st.success("Enviando a image_processor...")
                    # (Lógica de procesado similar a la de tu código original)

# TAB 4: GESTIÓN (ADMINISTRATIVA Y REPORTES)
with tab_gestion:
    if st.session_state.user_role != "admin":
        st.warning("⚠️ Nivel de acceso insuficiente. Solo Administradores de Planta.")
    else:
        # Sub-pestañas internas para mantener el diseño limpio
        tab_admin_users, tab_admin_reports = st.tabs(["👥 Gestión de Usuarios", "📊 Reportes y Telemetría"])
        
        # --- SECCIÓN: USUARIOS ---
        # --- SECCIÓN: USUARIOS (DENTRO DEL TAB DE GESTIÓN) ---
        with tab_admin_users:
            # Mostramos siempre el directorio para tener visibilidad rápida
            st.subheader("📋 Directorio de Usuarios Activos")
            df_users = db.safe_read("usuarios")
            
            if not df_users.empty:
                # Tabla limpia de usuarios actuales
                st.dataframe(df_users[['usuario', 'rol']], use_container_width=True, hide_index=True)
                
                st.divider()
                
                # --- COLUMNAS PARA HIDE/SHOW (EXPANDERS) ---
                col_new, col_del = st.columns(2)
                
                with col_new:
                    # EXPANDER PARA AGREGAR
                    with st.expander("➕ Registrar Nuevo Usuario", expanded=False):
                        st.markdown("### Datos de Acceso")
                        nu_user = st.text_input("ID de Usuario (Ej: op_01)", key="new_u_input")
                        nu_pass = st.text_input("Contraseña / PIN", type="password", key="new_p_input")
                        nu_rol = st.selectbox("Nivel de Permisos", ["operador", "admin"], key="new_r_input")
                        
                        if st.button("🚀 Confirmar Registro", use_container_width=True):
                            if nu_user and nu_pass:
                                hashed_pass = hash_pw(nu_pass)
                                q_insert = "INSERT INTO usuarios (usuario, contrasena, rol) VALUES (:u, :h, :r)"
                                if db.execute_query(q_insert, {"u": nu_user.lower(), "h": hashed_pass, "r": nu_rol}):
                                    st.success(f"✅ '{nu_user}' añadido.")
                                    time.sleep(1)
                                    st.rerun()
                            else:
                                st.error("⚠️ Completa todos los campos.")
        
                with col_del:
                    # EXPANDER PARA ELIMINAR
                    with st.expander("🗑️ Dar de Baja Usuario", expanded=False):
                        st.markdown("### Zona de Peligro")
                        user_list = df_users['usuario'].tolist()
                        user_to_delete = st.selectbox("Seleccione cuenta a borrar:", user_list, key="del_u_select")
                        
                        st.warning(f"Se eliminará permanentemente a: {user_to_delete}")
                        if st.button("❌ Ejecutar Baja", type="primary", use_container_width=True):
                            if user_to_delete == st.session_state.username:
                                st.error("🚫 No puedes eliminar tu propia sesión activa.")
                            else:
                                q_delete = "DELETE FROM usuarios WHERE usuario = :u"
                                if db.execute_query(q_delete, {"u": user_to_delete}):
                                    st.success(f"✅ Usuario '{user_to_delete}' removido.")
                                    time.sleep(1)
                                    st.rerun()
            else:
                st.error("❌ Error al cargar la tabla de usuarios en Supabase.")

        # --- SECCIÓN: REPORTES ---
        with tab_admin_reports:
            st.subheader("📈 Rendimiento de Red (7 Días)")
            df_stats = db.get_history_range(datetime.now() - timedelta(days=7), datetime.now())

            if not df_stats.empty:
                df_stats['health_score'] = pd.to_numeric(df_stats['health_score'])
                promedio_real = df_stats.groupby("machine_name")["health_score"].mean()
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
                datos = db.get_history_range(f_i, f_f)
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
