from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey, Table, Text, Enum
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Float, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime
import enum
from geoalchemy2 import Geometry  # <-- Deze moet bovenaan staan!
from datetime import datetime, timezone

SQLALCHEMY_DATABASE_URL = "postgresql://admin:secretpassword@192.168.2.10:5432/rodekruis_mapgen"
# SQLACLHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:secretpassword@db:5432/rodekruis_mapgen")


engine = create_engine(
    SQLALCHEMY_DATABASE_URL, echo=False
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

department_services = Table(
    'department_services',
    Base.metadata,
    Column('department_id', Integer, ForeignKey('departments.id'), primary_key=True),
    Column('service_id', Integer, ForeignKey('services.id'), primary_key=True)
)


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)
    province_access = Column(String(50), nullable=True)

class Service(Base):
    __tablename__ = 'services'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)


class Region(Base):
    __tablename__ = 'regions'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    province = Column(String(50), nullable=False)
    clusters = relationship('Cluster', back_populates='region', cascade="all, delete-orphan")
    departments = relationship('Department', back_populates='region_rel')


class Cluster(Base):
    __tablename__ = 'clusters'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    province = Column(String(50), nullable=False)
    region_id = Column(Integer, ForeignKey('regions.id'), nullable=True)
    region = relationship('Region', back_populates='clusters')
    departments = relationship('Department', back_populates='cluster_rel')


class Department(Base):
    __tablename__ = 'departments'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    group = Column(String(50), nullable=True)  # Legacy / text group
    province = Column(String(50), nullable=False, index=True)
    type = Column(String(50), default="afdeling")
    email = Column(String(100), nullable=True)
    telephone = Column(String(50), nullable=True)
    address = Column(String(255), nullable=True)
    entiteitnummer = Column(String(20), nullable=True)
    color = Column(String(20), nullable=True)
    transparent = Column(Boolean, default=False)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)

    # Hiërarchie relaties
    region_id = Column(Integer, ForeignKey('regions.id'), nullable=True)
    cluster_id = Column(Integer, ForeignKey('clusters.id'), nullable=True)
    region_rel = relationship('Region', back_populates='departments')
    cluster_rel = relationship('Cluster', back_populates='departments')

    services = relationship('Service', secondary=department_services, backref='departments')
    vehicles = relationship('Vehicle', back_populates='department', cascade="all, delete-orphan")
    members = relationship('Municipality', back_populates='department', cascade="all, delete-orphan")


class Municipality(Base):
    __tablename__ = 'municipalities'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    department_id = Column(Integer, ForeignKey('departments.id'))
    department = relationship('Department', back_populates='members')


class Vehicle(Base):
    __tablename__ = 'vehicles'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    fleet_nr = Column(String(50), nullable=True)
    address = Column(String(255), nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    department_id = Column(Integer, ForeignKey('departments.id'))
    department = relationship('Department', back_populates='vehicles')


class SitLocation(Base):
    __tablename__ = 'sit_locations'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    province = Column(String(50), nullable=True, default="Onbekend")
    type = Column(String(50), nullable=True)
    address = Column(String(255), nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    sit_vehicles = relationship('SitVehicle', back_populates='sit_location', cascade="all, delete-orphan")


class SitVehicle(Base):
    __tablename__ = 'sit_vehicles'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    fleet_nr = Column(String(50), nullable=True)
    sit_location_id = Column(Integer, ForeignKey('sit_locations.id'))
    sit_location = relationship('SitLocation', back_populates='sit_vehicles')


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(String(50), default=lambda: datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    username = Column(String(50), nullable=False)
    action = Column(String(20), nullable=False)  # CREATE, UPDATE of DELETE
    table_name = Column(String(50), nullable=False)
    row_name = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)


class MatchMethodEnum(enum.Enum):
    NAAM_MATCH = "Naam_Match"
    HOOFDGEMEENTE_MATCH = "Hoofdgemeente_Match"
    RUIMTELIJKE_AFSTAND = "Ruimtelijke_Afstand_Dichtstbijzijnd"
    MANUELE_OVERRIDE = "Manuele_Override"


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


class CoordinateCache(Base):
    __tablename__ = "coordinate_cache"

    id = Column(Integer, primary_key=True, index=True)
    address = Column(String, unique=True, index=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    last_checked = Column(DateTime, default=lambda: datetime.now(timezone.utc))