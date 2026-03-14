from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from database import Base
import datetime
from sqlalchemy import Column, Integer, String
# ... otros imports

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)  # Se recomienda guardar el hash, no texto plano
    role = Column(String)      # "admin" o "operator"
    
class PrintTest(Base):
    __tablename__ = "print_tests"
    
    id = Column(Integer, primary_key=True, index=True)
    machine_name = Column(String, index=True)
    machine_id = Column(String) 
    timestamp = Column(DateTime, default=datetime.datetime.now)
    shift = Column(Integer)
    health_score = Column(Float)
    missing_nodes = Column(Integer)
    injection_map = Column(JSON) 
    image_path = Column(String)