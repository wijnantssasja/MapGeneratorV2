import os
import time
from fastapi import FastAPI
from sqlalchemy import create_engine, Column, Integer, String, Enum, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError
from geoalchemy2 import Geometry
import enum

# --- Database Setup ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:secretpassword@db:5432/rodekruis_mapgen")

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Enums ---
class MatchMethodEnum(enum.Enum):
    NAAM_MATCH = "Naam_Match"
    HOOFDGEMEENTE_MATCH = "Hoofdgemeente_Match"
    RUIMTELIJKE_AFSTAND = "Ruimtelijke_Afstand_Dichtstbijzijnd"
    MANUELE_OVERRIDE = "Manuele_Override"

# --- Models ---
class Department(Base):
    __tablename__ = "departments"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    type = Column(String)

class DepartmentShape(Base):
    __tablename__ = "department_shapes"
    
    id = Column(Integer, primary_key=True, index=True)
    shape_id = Column(String, index=True) 
    name = Column(String, index=True)
    postcode = Column(String)
    parent_id = Column(String)
    hoofdgem = Column(String)
    
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    match_method = Column(Enum(MatchMethodEnum), nullable=True)
    
    geom = Column(Geometry(geometry_type='MULTIPOLYGON', srid=4326))

# --- Retry Logica voor Database Connectie ---
max_retries = 10
for i in range(max_retries):
    try:
        print(f"Poging {i+1} om tabellen aan te maken...")
        Base.metadata.create_all(bind=engine)
        print("Succes! Database is verbonden en tabellen zijn aangemaakt.")
        break
    except OperationalError:
        print("Database is nog niet klaar. 5 seconden wachten...")
        time.sleep(5)

# --- FastAPI Setup ---
app = FastAPI(title="MapGeneratorV2 API")

@app.get("/")
def read_root():
    return {"message": "MapGeneratorV2 Backend is draaiende! Tabellen zijn succesvol aangemaakt."}
