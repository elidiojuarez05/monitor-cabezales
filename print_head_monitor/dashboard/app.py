from flask import Flask,render_template,request,redirect,session
from flask_socketio import SocketIO
import json

from datetime import datetime
# ... imports de flask ...
import sys
import os
import hashlib

# Configuración de rutas
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importar herramientas del backend
from backend import crud, database, models
from backend.image_processor import process_image

app = Flask(__name__)
app.secret_key = "industrial_monitor"

# Inicializar tablas de SQLAlchemy (esto crea la tabla 'users')
database.Base.metadata.create_all(bind=database.engine)

def init_admin_user():
    """Crea el usuario administrador usando SQLAlchemy."""
    # Abrimos una sesión temporal para la inicialización
    session_db = database.SessionLocal()
    try:
        admin_username = "admin"
        admin_password_raw = "system123"
        password_hash = hashlib.sha256(admin_password_raw.encode()).hexdigest()
        
        # Ahora 'crud' ya existe porque lo importamos arriba
        existing_admin = crud.get_user_by_username(session_db, admin_username)
        
        if not existing_admin:
            crud.create_user(session_db, admin_username, password_hash, role="admin")
            print("✅ Usuario administrador creado con éxito.")
    finally:
        session_db.close()

# Llamar a la función al arrancar
init_admin_user()

# ... resto de tus rutas ...

def init_admin_user(db):
    """Crea el usuario administrador por defecto si no existe."""
    admin_username = "admin"
    admin_password_raw = "system123"
    
    # Hashear la contraseña para seguridad
    password_hash = hashlib.sha256(admin_password_raw.encode()).hexdigest()
    
    # Verificar si ya existe
    existing_admin = crud.get_user_by_username(db, admin_username)
    
    if not existing_admin:
        crud.create_user(db, admin_username, password_hash, role="admin")
        # Opcional: st.info("Usuario administrador inicializado.")

# Añade la carpeta raíz del proyecto al path de Python
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Ahora ya puedes importar
from backend.image_processor import process_image

app = Flask(__name__)
app.secret_key="industrial_monitor"

socketio = SocketIO(app)

UPLOAD_FOLDER="../uploads"



# ------------------------
# DASHBOARD
# ------------------------
if __name__=="__main__":

    socketio.run(
        app,
        host="0.0.0.0",
        port=5000
    )