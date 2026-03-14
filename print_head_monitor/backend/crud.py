from sqlalchemy.orm import Session
import models
import datetime
import pandas as pd
from datetime import datetime, timedelta
from fpdf import FPDF
from sqlalchemy.orm import Session
# En backend/crud.py
import streamlit as st

# --- GESTIÓN DE USUARIOS ---

def get_user_by_username(db: Session, username: str):
    """Busca un usuario por su nombre de cuenta."""
    return db.query(models.User).filter(models.User.username == username).first()

def get_all_users(db: Session):
    """Retorna la lista completa de usuarios."""
    return db.query(models.User).all()

def create_user(db: Session, username: str, password_hash: str, role: str):
    """Crea un nuevo usuario en la base de datos."""
    db_user = models.User(username=username, password=password_hash, role=role)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: int):
    """Elimina un usuario por su ID."""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        db.delete(user)
        db.commit()
        return True
    return False

# --- REPORTES Y ESTADÍSTICAS ---

def get_weekly_data(db: Session):
    """
    Obtiene los tests de la última semana y los formatea 
    en un DataFrame de Pandas para el Administrador.
    """
    hace_una_semana = datetime.now() - timedelta(days=7)
    
    # Suponiendo que tu modelo TestResult tiene un campo 'timestamp'
    results = db.query(models.PrintTest).filter(
        models.PrintTest.timestamp >= hace_una_semana
    ).all()
    
    if not results:
        return pd.DataFrame() # Retorna vacío si no hay datos

    # Convertimos a lista de diccionarios para cargar en Pandas
    data = []
    for r in results:
        data.append({
            "Fecha": r.timestamp.strftime("%Y-%m-%d %H:%M"),
            "Máquina": r.machine_name,
            "Salud %": round(r.health_score, 2),
            "Nodos Caídos": r.missing_nodes,
            "ID Test": r.id
        })
    
    return pd.DataFrame(data)

def get_last_test(db: Session, machine_name: str):
    """Obtiene el último registro de una máquina específica"""
    return db.query(models.PrintTest)\
             .filter(models.PrintTest.machine_name == machine_name)\
             .order_by(models.PrintTest.timestamp.desc())\
             .first()

def save_test_result(db: Session, machine_name: str, health: float, missing: int, img_map: list, path: str):
    now = datetime.now() # Correcto: usa la clase directamente
    hour = now.hour
    
    # Determinar turno
    shift = 1 if 6 <= hour < 14 else 2 if 14 <= hour < 22 else 3
    
    db_test = models.PrintTest(
        machine_name=machine_name,
        health_score=health,
        missing_nodes=missing,
        injection_map=img_map,
        image_path=path,
        shift=shift,
        timestamp=now
    )
    db.add(db_test)
    db.commit()
    db.refresh(db_test)
    return db_test

def get_daily_report(db: Session):
    today = datetime.date.today()
    return db.query(models.PrintTest).filter(models.PrintTest.timestamp >= today).all()


def get_health_history(db: Session):
    """Obtiene el historial de salud para graficar."""
    # Cambia datetime.datetime.now() por solo datetime.now() 
    # y datetime.timedelta por solo timedelta
    hace_15_dias = datetime.now() - timedelta(days=15)
    
    results = db.query(models.PrintTest).filter(
        models.PrintTest.timestamp >= hace_15_dias
    ).order_by(models.PrintTest.timestamp.asc()).all()
    
    if not results:
        return pd.DataFrame()

    data = []
    for r in results:
        data.append({
            "Fecha": r.timestamp,
            "Máquina": r.machine_name,
            "Salud": r.health_score
        })
    
    return pd.DataFrame(data)



def get_status_by_date(db: Session, target_date: datetime.date):
    """Busca el último test de cada máquina en una fecha específica."""
    # Definimos el inicio y fin del día elegido
    start_day = datetime.combine(target_date, datetime.min.time())
    end_day = datetime.combine(target_date, datetime.max.time())
    
    # Obtenemos todos los tests de ese día
    return db.query(models.PrintTest).filter(
        models.PrintTest.timestamp >= start_day,
        models.PrintTest.timestamp <= end_day
    ).order_by(models.PrintTest.timestamp.desc()).all()
    


def generate_pdf_report(df):
    """Crea un objeto PDF a partir de un DataFrame de Pandas."""
    pdf = FPDF()
    pdf.add_page()
    
    # Título del Reporte
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, "Reporte de Salud - Print Head Monitor", 0, 1, 'C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(190, 10, f"Generado el: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 1, 'C')
    pdf.ln(10)
    
    # Encabezados de Tabla
    pdf.set_fill_color(200, 220, 255)
    pdf.set_font("Arial", 'B', 10)
    cols = ["Fecha", "Maquina", "Salud %", "Fallas"]
    widths = [45, 60, 45, 40]
    
    for i in range(len(cols)):
        pdf.cell(widths[i], 10, cols[i], 1, 0, 'C', True)
    pdf.ln()
    
    # Datos
    pdf.set_font("Arial", '', 10)
    for index, row in df.iterrows():
        pdf.cell(widths[0], 10, str(row['Fecha']), 1)
        pdf.cell(widths[1], 10, str(row['Máquina']), 1)
        pdf.cell(widths[2], 10, f"{row['Salud %']}%", 1, 0, 'C')
        pdf.cell(widths[3], 10, str(row['Nodos Caídos']), 1, 0, 'C')
        pdf.ln()
        
    return pdf.output(dest='S').encode('latin-1') # Retorna los bytes del PDF  


def get_machine_history(db: Session, machine_name: str, limit: int = 10):
    """
    Obtiene los últimos tests de una máquina específica.
    Retorna un DataFrame listo para graficar.
    """
    query = db.query(models.PrintTest).filter(
        models.PrintTest.machine_name == machine_name
    ).order_by(models.PrintTest.timestamp.desc()).limit(limit).all()
    
    if not query:
        return pd.DataFrame(columns=['timestamp', 'health_score'])

    # Creamos el DataFrame y lo invertimos para que el tiempo sea cronológico
    df = pd.DataFrame([{
        'timestamp': t.timestamp, 
        'health_score': t.health_score
    } for t in query])
    
    return df.sort_values('timestamp') 


def get_test_by_date(db, machine_name, date_to_search):
    """Busca el test más reciente de una máquina hasta una fecha específica."""
    from sqlalchemy import func
    # Cambiamos TestResult por PrintTest que es como se llama en tu models.py
    return db.query(models.PrintTest).filter(
        models.PrintTest.machine_name == machine_name,
        func.date(models.PrintTest.timestamp) <= date_to_search
    ).order_by(models.PrintTest.timestamp.desc()).first() # <--- Corregido de order_order_by a order_by
    
    
    
    
@st.cache_data(ttl=10) # Guarda los datos por 10 segundos
def get_machine_history_cached(_db, machine_name, limit=10):
    # Llamamos a tu función original (asumiendo que se llama get_machine_history)
    return get_machine_history(_db, machine_name, limit)

@st.cache_data(ttl=5) # El último test se refresca más seguido
def get_last_test_cached(_db, machine_name):
    return get_last_test(_db, machine_name)

