from database import SessionLocal, User
import bcrypt
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey, Table, Text, Enum
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

SQLALCHEMY_DATABASE_URL = "postgresql://admin:secretpassword@192.168.2.10:5432/rodekruis_mapgen"

# Let op: GEEN connect_args={"check_same_thread": False} meer hier!
engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE departments ADD COLUMN \"group\" VARCHAR(50);"))
        conn.commit()
    print("Succes: Kolom \"group\" is veilig toegevoegd met behoud van alle data!")
except Exception as e:
    print(f"Er ging iets mis (misschien bestond de kolom al?): {e}")
