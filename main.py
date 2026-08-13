from fastapi import FastAPI, Depends, HTTPException, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
import bcrypt
from database import AuditLog, Municipality
from database import SessionLocal, engine, Base, User, Department, Vehicle, SitLocation, SitVehicle, Service
from types import SimpleNamespace
import os
import json
from sqlalchemy import func
from database import DepartmentShape, MatchMethodEnum  # <-- Voeg deze regel toe!
from sqlalchemy import text
from geopy.geocoders import Nominatim
import time
import os
import glob
from datetime import datetime
from urllib.parse import unquote
from fastapi import BackgroundTasks
from fastapi.responses import FileResponse

# Importeer de losse generator componenten
from generator import background_generate_map, OUTPUT_DIR

# Create database tables if not exist
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Rode Kruis Map Generator")

# SECURE SESSION MIDDLEWARE (Replace with a strong random secret key in production)
app.add_middleware(
    SessionMiddleware,
    secret_key="rk-map-generator-super-secret-key-change-me",
    max_age=14400  # 4 uur in seconden
)
templates = Jinja2Templates(directory="templates")

# Route om de statische kaart daadwerkelijk te kunnen bekijken
from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="/opt/MapGenerator/static"), name="static")


def verify_edit_permission(user: User, target_province: str):
    """
    Controleert of een gebruiker rechten heeft om een wijziging door te voeren.
    - Admin & Nationaal mogen alles.
    - Provinciaal mag alleen binnen de eigen provincie.
    """
    if user.role in ["admin", "nationaal"]:
        return True
    if user.role == "provinciaal" and user.province_access == target_province:
        return True
    raise HTTPException(
        status_code=403,
        detail=f"Toegang geweigerd: Je hebt geen rechten om wijzigingen te maken in provincie '{target_province}'."
    )


# Dependency: Get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def log_action(db: Session, username: str, action: str, table_name: str, row_name: str, details: str = ""):
    log = AuditLog(username=username, action=action, table_name=table_name, row_name=row_name, details=details)
    db.add(log)


# Helper: Get current logged-in user from session (Met 4-uur controle & Hard-Lock)
def get_current_user(request: Request, db: Session = Depends(get_db)):
    username = request.session.get("username")
    if not username:
        return None

    # Controleer of de sessie is verlopen (4 uur inactiviteit)
    login_time = request.session.get("login_time", 0)
    if time.time() - login_time > 14400:
        request.session.clear()
        return None

    user = db.query(User).filter(User.username == username).first()

    # HARD-LOCK: Mag deze gebruiker rondkijken, of MOET het wachtwoord gereset worden?
    if user and getattr(user, 'force_password_change', False):
        # Ze mogen enkel naar de reset pagina (om te wijzigen) of naar logout (om weg te gaan)
        allowed_paths = ["/profile/force-password-change", "/logout"]
        if request.url.path not in allowed_paths:
            # BAM! Teruggestuurd.
            raise ForcePasswordChangeException()

    return user


def has_permission(user: User, target_province: str) -> bool:
    """
    Controleert of een gebruiker rechten heeft in een bepaalde provincie.
    Retourneert True of False, zodat we de UI read-only kunnen maken.
    """
    if user.role in ["admin", "nationaal"]:
        return True
    if user.role == "provinciaal" and user.province_access == target_province:
        return True
    return False


def check_post_permission(user: User, target_province: str):
    """Gooit een nette HTML foutmelding als iemand via POST probeert in te breken."""
    if not has_permission(user, target_province):
        raise HTTPException(
            status_code=403,
            detail="Toegang geweigerd: Je hebt geen rechten om wijzigingen te maken in deze provincie."
        )


# =========================================================
# ADRES RESOLUTIE LOGICA
# =========================================================
geolocator = Nominatim(user_agent="rk_map_generator_backend", timeout=10)


def resolve_address(address_str):
    """Zoekt een adres op via API met verplichte delay en ', België' toevoeging."""
    if not address_str or not address_str.strip():
        return None, None
    full_address = f"{address_str.strip()}, België"
    try:
        time.sleep(1.1)  # Strikte rate-limiting voor de gratis API
        location = geolocator.geocode(full_address)
        if location:
            return location.latitude, location.longitude
    except Exception as e:
        print(f"Geocode Fout bij '{full_address}': {e}")
    return None, None


# ---------------------------------------------------------
# AUTHENTICATION ROUTES
# ---------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    request.session.clear()
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()

    if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Ongeldige gebruikersnaam of wachtwoord."}
        )

    # Zet de sessie variabelen en de starttijd
    request.session["username"] = user.username
    request.session["role"] = user.role
    request.session["province_access"] = user.province_access
    request.session["login_time"] = time.time()

    # Controleer of de admin een wachtwoord-reset heeft geforceerd
    if getattr(user, 'force_password_change', False):
        return RedirectResponse(url="/profile/force-password-change", status_code=status.HTTP_303_SEE_OTHER)

    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------
# PROTECTED APP ROUTES
# ---------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    # Check authentication
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    dept_count = db.query(Department).count()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": current_user,
            "dept_count": dept_count
        }
    )


@app.get("/departments", response_class=HTMLResponse)
async def list_departments(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    # Iedereen ziet alle afdelingen (behalve zetels)
    departments = db.query(Department).filter(Department.type != "provinciale_zetel").order_by(Department.name).all()
    return templates.TemplateResponse(request=request, name="departments.html",
                                      context={"user": current_user, "departments": departments})


@app.get("/provinciale-zetels", response_class=HTMLResponse)
async def list_provinciale_zetels(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    zetels = db.query(Department).filter(Department.type == "provinciale_zetel").order_by(Department.name).all()
    return templates.TemplateResponse(request=request, name="provinciale_zetels.html",
                                      context={"user": current_user, "zetels": zetels})


@app.get("/sit-locations", response_class=HTMLResponse)
async def list_sit_locations(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    sits = db.query(SitLocation).order_by(SitLocation.name).all()
    return templates.TemplateResponse(request=request, name="sit_locations.html",
                                      context={"user": current_user, "sits": sits})


@app.get("/regions", response_class=HTMLResponse)
async def manage_regions(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    regions = db.query(Region).all()
    departments = db.query(Department).filter(Department.type != "provinciale_zetel").all()
    return templates.TemplateResponse(request=request, name="regions.html",
                                      context={"user": current_user, "regions": regions, "departments": departments,
                                               "edit_region": None})


@app.get("/clusters", response_class=HTMLResponse)
async def manage_clusters(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    clusters = db.query(Cluster).all()
    regions = db.query(Region).all()
    departments = db.query(Department).filter(Department.type != "provinciale_zetel").all()
    return templates.TemplateResponse(request=request, name="clusters.html",
                                      context={"user": current_user, "clusters": clusters, "regions": regions,
                                               "departments": departments, "edit_cluster": None})


from database import Region, Cluster, Municipality


# --- AFDELINGEN TOEVOEGEN & VERWIDEREN ---

@app.get("/departments/new", response_class=HTMLResponse)
async def new_department_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    is_zetel = request.query_params.get("type") == "zetel"
    return templates.TemplateResponse(request=request, name="edit_department.html",
                                      context={"user": current_user, "dept": None, "is_zetel": is_zetel})


# --- SIT LOCATIES TOEVOEGEN & VERWIDEREN ---

@app.get("/sit-locations/new", response_class=HTMLResponse)
async def new_sit_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="edit_sit.html",
                                      context={"user": current_user, "sit": None})


# --- REGIO'S & CLUSTERS BEHEER ---


# --- REGIO'S BEHEER (BEWERKEN & VERWIJDEREN) ---

# --- CLUSTERS BEHEER (BEWERKEN & VERWIJDEREN) ---


@app.get("/audit-logs", response_class=HTMLResponse)
async def view_audit_logs(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(200).all()
    return templates.TemplateResponse(request=request, name="audit_logs.html",
                                      context={"user": current_user, "logs": logs})


# =========================================================
# HELPER: LOGBOEK
# =========================================================
def log_action(db: Session, username: str, action: str, table_name: str, row_name: str, details: str = ""):
    try:
        log = AuditLog(username=username, action=action, table_name=table_name, row_name=row_name, details=details)
        db.add(log)
    except Exception as e:
        print(f"Kon log niet wegschrijven: {e}")


# =========================================================
# HARD-LOCK EXCEPTION VOOR WACHTWOORD RESET
# =========================================================
class ForcePasswordChangeException(Exception):
    pass


@app.exception_handler(ForcePasswordChangeException)
async def force_password_handler(request: Request, exc: ForcePasswordChangeException):
    # Als deze error wordt opgeworpen, stuur de gebruiker ALTIJD terug naar de reset pagina
    return RedirectResponse(url="/profile/force-password-change", status_code=status.HTTP_303_SEE_OTHER)


# =========================================================
# AFDELINGEN: BEWERKEN, TOEVOEGEN, FUSIE & VERWIJDEREN
# =========================================================
@app.post("/departments/new")
async def create_department(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    form = await request.form()
    province = form.get("province")
    verify_edit_permission(current_user, province)

    new_dept = Department(
        name=form.get("name"), province=province, group=form.get("group"),
        address=form.get("address"), email=form.get("email"), telephone=form.get("telephone"),
        entiteitnummer=form.get("entiteitnummer"), color=form.get("color"),
        type="provinciale_zetel" if form.get("is_provinciale_zetel") else "afdeling",
        transparent=True if form.get("transparent") else False,
    )
    db.add(new_dept)
    db.flush()

    # 2. Bepaal Coördinaten Voertuigen
    v_names = form.getlist("vehicle_name[]")
    v_fleets = form.getlist("vehicle_fleet[]")
    v_addresses = form.getlist("vehicle_address[]")
    v_lats = form.getlist("vehicle_lat[]")
    v_lons = form.getlist("vehicle_lon[]")
    for i in range(len(v_names)):
        if v_names[i].strip():
            v_lat = float(v_lats[i]) if i < len(v_lats) and v_lats[i] else None
            v_lon = float(v_lons[i]) if i < len(v_lons) and v_lons[i] else None
            db.add(Vehicle(
                name=v_names[i].strip(), fleet_nr=v_fleets[i].strip() if v_fleets[i] else None,
                address=v_addresses[i].strip() if v_addresses[i] else None,
                lat=v_lat, lon=v_lon, department_id=new_dept.id
            ))

    for srv_name in form.getlist("services[]"):
        srv_name = srv_name.lower().strip()
        if srv_name:
            service = db.query(Service).filter(Service.name == srv_name).first()
            if not service:
                service = Service(name=srv_name)
                db.add(service)
                db.flush()
            new_dept.services.append(service)

    log_action(db, current_user.username, "CREATE", "Afdeling", new_dept.name, "Nieuwe afdeling/fusie aangemaakt.")
    db.commit()
    return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/departments/edit/{dept_id}")
async def update_department(request: Request, dept_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user: return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept: raise HTTPException(status_code=404, detail="Afdeling niet gevonden")

    form = await request.form()
    new_province = form.get("province")

    if not has_permission(current_user, dept.province) or (
            new_province and not has_permission(current_user, new_province)):
        return HTMLResponse("<h2>Actie geweigerd</h2><p>Je hebt geen rechten.</p><a href='/departments'>Ga terug</a>",
                            status_code=403)

    changes = []

    # 1. ENKEL OPSLAAN WAT DE GEBRUIKER HEEFT INGEVULD
    # (Geen API aanroepen of fallbacks berekenen hier!)
    form_lat = float(form.get("lat")) if form.get("lat") else None
    form_lon = float(form.get("lon")) if form.get("lon") else None
    new_address = form.get("address")

    dept.lat = form_lat
    dept.lon = form_lon
    dept.address = new_address

    if str(dept.name) != str(form.get("name")): changes.append("naam")
    if str(dept.province) != str(form.get("province")): changes.append("provincie")

    dept.name = form.get("name")
    dept.province = new_province
    dept.group = form.get("group")
    dept.email = form.get("email")
    dept.telephone = form.get("telephone")
    dept.entiteitnummer = form.get("entiteitnummer")
    dept.color = form.get("color")
    dept.type = "provinciale_zetel" if form.get("is_provinciale_zetel") else "afdeling"
    dept.transparent = True if form.get("transparent") else False

    # 2. Voertuigen (Enkel opslaan wat is getypt)
    db.query(Vehicle).filter(Vehicle.department_id == dept.id).delete()
    v_names = form.getlist("vehicle_name[]")
    v_fleets = form.getlist("vehicle_fleet[]")
    v_addresses = form.getlist("vehicle_address[]")
    v_lats = form.getlist("vehicle_lat[]")
    v_lons = form.getlist("vehicle_lon[]")

    for i in range(len(v_names)):
        if v_names[i].strip():
            v_lat = float(v_lats[i]) if v_lats[i] else None
            v_lon = float(v_lons[i]) if v_lons[i] else None

            db.add(Vehicle(name=v_names[i].strip(), fleet_nr=v_fleets[i].strip() if v_fleets[i] else None,
                           address=v_addresses[i].strip() if v_addresses[i] else None,
                           lat=v_lat, lon=v_lon, department_id=dept.id))

    dept.services.clear()
    for srv_name in form.getlist("services[]"):
        srv_name = srv_name.lower().strip()
        if srv_name:
            service = db.query(Service).filter(Service.name == srv_name).first()
            if not service:
                service = Service(name=srv_name)
                db.add(service)
                db.flush()
            dept.services.append(service)

    log_action(db, current_user.username, "UPDATE", "Afdeling", dept.name,
               f"Gewijzigd: {', '.join(changes) if changes else 'Subdata'}")
    db.commit()
    return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)


# =========================================================
# SIT LOCATIES: BEWERKEN, TOEVOEGEN & VERWIJDEREN
# =========================================================
@app.post("/sit-locations/new")
async def create_sit(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user: return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    form = await request.form()
    province = form.get("province")
    verify_edit_permission(current_user, province)

    # Simpelweg uitlezen wat ingevuld is
    sit_lat = float(form.get("lat")) if form.get("lat") else None
    sit_lon = float(form.get("lon")) if form.get("lon") else None

    new_sit = SitLocation(
        name=form.get("name"), province=province, type=form.get("type"), address=form.get("address"),
        lat=sit_lat, lon=sit_lon
    )
    db.add(new_sit)
    db.flush()

    v_names = form.getlist("vehicle_name[]")
    v_fleets = form.getlist("vehicle_fleet[]")
    for i in range(len(v_names)):
        if v_names[i].strip():
            db.add(SitVehicle(name=v_names[i].strip(),
                              fleet_nr=v_fleets[i].strip() if i < len(v_fleets) and v_fleets[i] else None,
                              sit_location_id=new_sit.id))

    log_action(db, current_user.username, "CREATE", "SIT-Locatie", new_sit.name, "Nieuwe SIT aangemaakt.")
    db.commit()
    return RedirectResponse(url="/sit-locations", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/sit-locations/edit/{sit_id}")
async def update_sit(request: Request, sit_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user: return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    sit = db.query(SitLocation).filter(SitLocation.id == sit_id).first()
    if not sit: raise HTTPException(status_code=404, detail="SIT niet gevonden")

    form = await request.form()
    new_province = form.get("province")

    if not has_permission(current_user, sit.province) or (
            new_province and not has_permission(current_user, new_province)):
        return HTMLResponse(
            "<h2>Actie geweigerd</h2><p>Geen rechten in deze provincie.</p><a href='/sit-locations'>Ga terug</a>",
            status_code=403)

    # Overschrijf exact met wat de gebruiker heeft ingevuld
    sit.lat = float(form.get("lat")) if form.get("lat") else None
    sit.lon = float(form.get("lon")) if form.get("lon") else None
    sit.name = form.get("name")
    sit.province = new_province
    sit.type = form.get("type")
    sit.address = form.get("address")

    db.query(SitVehicle).filter(SitVehicle.sit_location_id == sit.id).delete()
    v_names = form.getlist("vehicle_name[]")
    v_fleets = form.getlist("vehicle_fleet[]")
    for i in range(len(v_names)):
        if v_names[i].strip():
            db.add(SitVehicle(name=v_names[i].strip(),
                              fleet_nr=v_fleets[i].strip() if i < len(v_fleets) and v_fleets[i] else None,
                              sit_location_id=sit.id))

    log_action(db, current_user.username, "UPDATE", "SIT-Locatie", sit.name, "SIT Gewijzigd")
    db.commit()
    return RedirectResponse(url="/sit-locations", status_code=status.HTTP_303_SEE_OTHER)


# --- FUSIE / MERGE (MET BEIDE ROUTES) ---
@app.get("/departments/merge", response_class=HTMLResponse)
async def merge_select_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    if current_user.role in ["admin", "nationaal"]:
        departments = db.query(Department).filter(Department.type != "provinciale_zetel").order_by(
            Department.name).all()
    else:
        departments = db.query(Department).filter(Department.province == current_user.province_access,
                                                  Department.type != "provinciale_zetel").order_by(
            Department.name).all()
    is_zetel = (Department.type == "provinciale_zetel")
    return templates.TemplateResponse(request=request, name="merge_departments.html",
                                      context={"user": current_user, "departments": departments, "is_zetel": is_zetel})


@app.post("/departments/merge", response_class=HTMLResponse)
async def execute_merge(request: Request, dept_a_id: int = Form(...), dept_b_id: int = Form(...),
                        db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    dept_a = db.query(Department).filter(Department.id == dept_a_id).first()
    dept_b = db.query(Department).filter(Department.id == dept_b_id).first()

    if not dept_a or not dept_b:
        raise HTTPException(status_code=400, detail="Eén of beide afdelingen werden niet gevonden.")

    # Leden verzamelen zonder dubbelingen
    merged_members_names = []
    for m in dept_a.members:
        if m.name and m.name not in merged_members_names:
            merged_members_names.append(m.name)
    for m in dept_b.members:
        if m.name and m.name not in merged_members_names:
            merged_members_names.append(m.name)

    # Voertuigen verzamelen
    merged_vehicles = []
    for v in (dept_a.vehicles + dept_b.vehicles):
        merged_vehicles.append(
            SimpleNamespace(name=v.name, fleet_nr=v.fleet_nr, address=v.address, lat=v.lat, lon=v.lon))

    # Services verzamelen (Unieke namen)
    service_names = list(set([s.name for s in dept_a.services] + [s.name for s in dept_b.services]))

    # Maak een dummy object aan met SimpleNamespace dat exact reageert als een model instance
    merged_dept = SimpleNamespace(
        id=None,
        name=f"{dept_a.name} - {dept_b.name}",
        province=dept_a.province,
        group=dept_a.group or dept_b.group,
        address=dept_a.address,
        email=dept_a.email,
        telephone=dept_a.telephone,
        entiteitnummer=dept_a.entiteitnummer or dept_b.entiteitnummer,
        color=dept_a.color,
        type="afdeling",
        transparent=False,
        lat=dept_a.lat,
        lon=dept_a.lon,
        members=[SimpleNamespace(name=m_name) for m_name in merged_members_names],
        vehicles=merged_vehicles,
        services=[SimpleNamespace(name=s_name) for s_name in service_names]
    )

    return templates.TemplateResponse(request=request, name="edit_department.html",
                                      context={"user": current_user, "dept": merged_dept})


# --- REGIO'S BEWERKEN & VERWIJDEREN ---
@app.get("/regions/edit/{reg_id}", response_class=HTMLResponse)
async def edit_region_page(request: Request, reg_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user: return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    region = db.query(Region).filter(Region.id == reg_id).first()
    if not region: raise HTTPException(status_code=404, detail="Regio niet gevonden")

    regions = db.query(Region).all()
    departments = db.query(Department).filter(Department.type != "provinciale_zetel").all()
    return templates.TemplateResponse(request=request, name="regions.html",
                                      context={"user": current_user, "regions": regions, "departments": departments,
                                               "edit_region": region})


# --- CLUSTERS BEWERKEN & VERWIJDEREN ---
@app.get("/clusters/edit/{clus_id}", response_class=HTMLResponse)
async def edit_cluster_page(request: Request, clus_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user: return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    cluster = db.query(Cluster).filter(Cluster.id == clus_id).first()
    if not cluster: raise HTTPException(status_code=404, detail="Cluster niet gevonden")

    clusters = db.query(Cluster).all()
    regions = db.query(Region).all()
    departments = db.query(Department).filter(Department.type != "provinciale_zetel").all()
    return templates.TemplateResponse(request=request, name="clusters.html",
                                      context={"user": current_user, "clusters": clusters, "regions": regions,
                                               "departments": departments, "edit_cluster": cluster})


@app.post("/regions/save")
async def save_region(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user: return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    form = await request.form()
    reg_id = form.get("region_id")
    name = form.get("name")
    province = form.get("province")
    selected_depts = form.getlist("departments[]")

    if not has_permission(current_user, province):
        return HTMLResponse(
            f"<h2>Actie geweigerd</h2><p>Je hebt geen rechten om in provincie {province} te werken.</p><a href='/regions'>Ga terug</a>",
            status_code=403)

    if reg_id:
        region = db.query(Region).filter(Region.id == int(reg_id)).first()
        if region and not has_permission(current_user, region.province):
            return HTMLResponse(
                "<h2>Actie geweigerd</h2><p>Je kunt een regio buiten je provincie niet aanpassen.</p><a href='/regions'>Ga terug</a>",
                status_code=403)
        region.name = name
        region.province = province
        log_action(db, current_user.username, "UPDATE", "Regio", region.name, "Regio gewijzigd")
    else:
        region = Region(name=name, province=province)
        db.add(region)
        db.flush()
        log_action(db, current_user.username, "CREATE", "Regio", region.name, "Nieuwe regio")

    db.query(Department).filter(Department.region_id == region.id).update({"region_id": None})
    if selected_depts:
        db.query(Department).filter(Department.id.in_([int(d) for d in selected_depts])).update(
            {"region_id": region.id}, synchronize_session=False)

    db.commit()
    return RedirectResponse(url="/regions", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/regions/delete/{reg_id}")
async def delete_region(reg_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user: return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    region = db.query(Region).filter(Region.id == reg_id).first()
    if region:
        if not has_permission(current_user, region.province):
            return HTMLResponse(
                "<h2>Actie geweigerd</h2><p>Je mag deze regio niet verwijderen.</p><a href='/regions'>Ga terug</a>",
                status_code=403)
        log_action(db, current_user.username, "DELETE", "Regio", region.name, "Regio verwijderd")
        db.query(Department).filter(Department.region_id == reg_id).update({"region_id": None})
        db.query(Cluster).filter(Cluster.region_id == reg_id).update({"region_id": None})
        db.delete(region)
        db.commit()
    return RedirectResponse(url="/regions", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/clusters/save")
async def save_cluster(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user: return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    form = await request.form()
    clus_id = form.get("cluster_id")
    name = form.get("name")
    province = form.get("province")
    region_id = form.get("region_id")
    selected_depts = form.getlist("departments[]")

    if not has_permission(current_user, province):
        return HTMLResponse(
            f"<h2>Actie geweigerd</h2><p>Je hebt geen rechten om in provincie {province} te werken.</p><a href='/clusters'>Ga terug</a>",
            status_code=403)

    if clus_id:
        cluster = db.query(Cluster).filter(Cluster.id == int(clus_id)).first()
        if cluster and not has_permission(current_user, cluster.province):
            return HTMLResponse(
                "<h2>Actie geweigerd</h2><p>Je kunt een cluster buiten je provincie niet aanpassen.</p><a href='/clusters'>Ga terug</a>",
                status_code=403)
        cluster.name = name
        cluster.province = province
        cluster.region_id = int(region_id) if region_id else None
        log_action(db, current_user.username, "UPDATE", "Cluster", cluster.name, "Cluster gewijzigd")
    else:
        cluster = Cluster(name=name, province=province, region_id=int(region_id) if region_id else None)
        db.add(cluster)
        db.flush()
        log_action(db, current_user.username, "CREATE", "Cluster", cluster.name, "Nieuwe cluster")

    db.query(Department).filter(Department.cluster_id == cluster.id).update({"cluster_id": None})
    if selected_depts:
        db.query(Department).filter(Department.id.in_([int(d) for d in selected_depts])).update(
            {"cluster_id": cluster.id}, synchronize_session=False)

    db.commit()
    return RedirectResponse(url="/clusters", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/clusters/delete/{clus_id}")
async def delete_cluster(clus_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user: return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    cluster = db.query(Cluster).filter(Cluster.id == clus_id).first()
    if cluster:
        if not has_permission(current_user, cluster.province):
            return HTMLResponse(
                "<h2>Actie geweigerd</h2><p>Je mag deze cluster niet verwijderen.</p><a href='/clusters'>Ga terug</a>",
                status_code=403)
        log_action(db, current_user.username, "DELETE", "Cluster", cluster.name, "Cluster verwijderd")
        db.query(Department).filter(Department.cluster_id == clus_id).update({"cluster_id": None})
        db.delete(cluster)
        db.commit()
    return RedirectResponse(url="/clusters", status_code=status.HTTP_303_SEE_OTHER)


# =========================================================
# GEBRUIKERSBEHEER (USER MANAGEMENT - ADMIN ONLY)
# =========================================================
@app.get("/users", response_class=HTMLResponse)
async def list_users(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user or current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Toegang geweigerd.")
    users = db.query(User).order_by(User.username).all()
    return templates.TemplateResponse(request=request, name="users.html",
                                      context={"user": current_user, "users": users})


@app.get("/users/new", response_class=HTMLResponse)
async def new_user_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user or current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Toegang geweigerd.")
    return templates.TemplateResponse(request=request, name="edit_user.html",
                                      context={"user": current_user, "edit_user": None})


@app.post("/users/new")
async def create_user_route(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        role: str = Form(...),
        province_access: str = Form("All"),
        force_password_change: bool = Form(False),
        db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user or current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Toegang geweigerd.")

    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Gebruikersnaam bestaat al.")

    hashed_pwd = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    new_user = User(
        username=username,
        password_hash=hashed_pwd,
        role=role,
        province_access=province_access,
        force_password_change=force_password_change
    )

    db.add(new_user)
    log_action(db, current_user.username, "CREATE", "Gebruiker", username,
               f"Rol: {role}, Reset geforceerd: {force_password_change}")
    db.commit()
    return RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/users/edit/{user_id}")
async def update_user(
        user_id: int,
        request: Request,
        username: str = Form(...),
        password: str = Form(None),
        role: str = Form(...),
        province_access: str = Form("All"),
        force_password_change: bool = Form(False),
        db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user or current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Toegang geweigerd.")

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Gebruiker niet gevonden.")

    target_user.username = username
    target_user.role = role
    target_user.province_access = province_access
    target_user.force_password_change = force_password_change

    if password and password.strip():
        target_user.password_hash = bcrypt.hashpw(password.strip().encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    log_action(db, current_user.username, "UPDATE", "Gebruiker", username,
               f"Rol: {role}, Reset geforceerd: {force_password_change}")
    db.commit()
    return RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/users/edit/{user_id}", response_class=HTMLResponse)
async def edit_user_page(user_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user or current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Toegang geweigerd.")
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Gebruiker niet gevonden.")
    return templates.TemplateResponse(request=request, name="edit_user.html",
                                      context={"user": current_user, "edit_user": target_user})


@app.post("/users/delete/{user_id}")
async def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user or current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Toegang geweigerd.")

    target_user = db.query(User).filter(User.id == user_id).first()
    if target_user:
        if target_user.id == current_user.id:
            raise HTTPException(status_code=400, detail="Je kunt je eigen account niet verwijderen!")
        log_action(db, current_user.username, "DELETE", "Gebruiker", target_user.username, "Gebruiker verwijderd")
        db.delete(target_user)
        db.commit()
    return RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/departments/edit/{dept_id}", response_class=HTMLResponse)
async def edit_department_page(request: Request, dept_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user: return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept: raise HTTPException(status_code=404, detail="Afdeling niet gevonden")

    # READONLY CHECK
    readonly = not has_permission(current_user, dept.province)
    is_zetel = (dept.type == "provinciale_zetel")
    return templates.TemplateResponse(request=request, name="edit_department.html",
                                      context={"user": current_user, "dept": dept, "readonly": readonly,
                                               "is_zetel": is_zetel})


@app.post("/departments/delete/{dept_id}")
async def delete_department(dept_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user: return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    dept = db.query(Department).filter(Department.id == dept_id).first()
    is_zetel = False
    if dept:
        if not has_permission(current_user, dept.province or ""):
            return HTMLResponse(
                "<h2>Actie geweigerd</h2><p>Je hebt geen rechten om deze afdeling te wissen.</p><a href='/departments'>Ga terug</a>",
                status_code=403)
        is_zetel = (dept.type == "provinciale_zetel")
        log_action(db, current_user.username, "DELETE", "Afdeling", dept.name, "Afdeling verwijderd")
        dept.services.clear()
        db.delete(dept)
        db.commit()
    target_url = "/provinciale-zetels" if is_zetel else "/departments"
    return RedirectResponse(url=target_url, status_code=status.HTTP_303_SEE_OTHER)


# --- SIT LOCATIES ---
@app.get("/sit-locations/edit/{sit_id}", response_class=HTMLResponse)
async def edit_sit_page(request: Request, sit_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user: return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    sit = db.query(SitLocation).filter(SitLocation.id == sit_id).first()
    if not sit: raise HTTPException(status_code=404, detail="SIT niet gevonden")

    readonly = not has_permission(current_user, sit.province)
    return templates.TemplateResponse(request=request, name="edit_sit.html",
                                      context={"user": current_user, "sit": sit, "readonly": readonly})


@app.post("/sit-locations/delete/{sit_id}")
async def delete_sit(sit_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user: return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    sit = db.query(SitLocation).filter(SitLocation.id == sit_id).first()
    if sit:
        if not has_permission(current_user, sit.province or ""):
            return HTMLResponse("<h2>Actie geweigerd</h2><p>Geen rechten.</p><a href='/sit-locations'>Ga terug</a>",
                                status_code=403)
        log_action(db, current_user.username, "DELETE", "SIT-Locatie", sit.name, "SIT verwijderd")
        db.query(SitVehicle).filter(SitVehicle.sit_location_id == sit.id).delete()
        db.delete(sit)
        db.commit()
    return RedirectResponse(url="/sit-locations", status_code=status.HTTP_303_SEE_OTHER)


# =========================================================
# API ROUTES VOOR DE INTERACTIEVE WERKINGSGEBIEDEN KAART
# =========================================================

@app.get("/api/departments/{dept_id}/shapes")
async def get_department_shapes(dept_id: int, db: Session = Depends(get_db)):
    """
    Haalt polygonen op met een strikte provinciegrens (op basis van postcodes):
    - Lokale afdeling: Eigen polygonen + Vrije polygonen binnen 10km (enkele binnen eigen provincie).
    - Provinciale zetel: Eigen polygonen + Vrije polygonen binnen de hele eigen provincie.
    Polygonen van andere afdelingen worden altijd genegeerd.
    """
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Afdeling niet gevonden")

    params = {"dept_id": dept_id}

    # 1. Bepaal de postcoderange afhankelijk van de provincie
    postcode_filter = "1=1"  # Fallback: toon alles als de provincie onbekend is
    prov = dept.province.lower() if dept.province else ""

    # Gebruik dubbele backslash (\\D) in Python string voor de regex in PostgreSQL
    safe_pc = "CAST(NULLIF(regexp_replace(postcode, '\\D', '', 'g'), '') AS INTEGER)"

    if prov == "antwerpen":
        postcode_filter = f"{safe_pc} BETWEEN 2000 AND 2999"
    elif prov == "limburg":
        postcode_filter = f"{safe_pc} BETWEEN 3500 AND 3999"
    elif prov == "oost-vlaanderen":
        postcode_filter = f"{safe_pc} BETWEEN 9000 AND 9999"
    elif prov == "west-vlaanderen":
        postcode_filter = f"{safe_pc} BETWEEN 8000 AND 8999"
    elif prov == "vlaams-brabant":
        postcode_filter = f"({safe_pc} BETWEEN 1500 AND 1999 OR {safe_pc} BETWEEN 3000 AND 3499)"
    elif prov == "brussel":
        postcode_filter = f"{safe_pc} BETWEEN 1000 AND 1299"

    # 2. Bouw de SQL op
    if dept.type == "provinciale_zetel":
        sql = f"""
        SELECT 
            id, shape_id, name, department_id, match_method,
            ST_AsGeoJSON(geom) as geojson
        FROM department_shapes
        WHERE department_id = :dept_id 
           OR (department_id IS NULL AND {postcode_filter})
        """
    else:
        # Lokale afdeling (10km restrictie + postcode restrictie)
        sql = f"""
        WITH core_shapes AS (
            SELECT ST_Union(geom) as combined_geom
            FROM department_shapes
            WHERE department_id = :dept_id
        )
        SELECT 
            id, shape_id, name, department_id, match_method,
            ST_AsGeoJSON(geom) as geojson
        FROM department_shapes
        WHERE department_id = :dept_id
        """

        if dept.lat and dept.lon:
            sql += f"""
            OR (
                department_id IS NULL 
                AND {postcode_filter}
                AND (
                    ((SELECT combined_geom FROM core_shapes) IS NOT NULL AND ST_DWithin(geom::geography, (SELECT combined_geom FROM core_shapes)::geography, 10000))
                    OR 
                    ((SELECT combined_geom FROM core_shapes) IS NULL AND ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, 10000))
                )
            )
            """
            params["lon"] = dept.lon
            params["lat"] = dept.lat
        else:
            sql += f"""
            OR (
                department_id IS NULL 
                AND {postcode_filter}
                AND (
                    ((SELECT combined_geom FROM core_shapes) IS NOT NULL AND ST_DWithin(geom::geography, (SELECT combined_geom FROM core_shapes)::geography, 10000))
                    OR 
                    ((SELECT combined_geom FROM core_shapes) IS NULL)
                )
            )
            """

    result = db.execute(text(sql), params).mappings().fetchall()

    features = []
    for r in result:
        geom_str = r["geojson"]
        if not geom_str:
            continue

        status = "empty"
        if r["department_id"] == dept_id:
            status = "current"

        method_str = r["match_method"] if r["match_method"] else "Geen"

        features.append({
            "type": "Feature",
            "geometry": json.loads(geom_str),
            "properties": {
                "shape_id": r["shape_id"],
                "name": r["name"],
                "status": status,
                "current_department_id": r["department_id"],
                "match_method": method_str
            }
        })

    return {"type": "FeatureCollection", "features": features}


@app.post("/api/departments/{dept_id}/shapes/{shape_id}/toggle")
async def toggle_department_shape(dept_id: int, shape_id: str, request: Request, db: Session = Depends(get_db)):
    """Koppelt of ontkoppelt een polygoon wanneer je erop klikt in de kaart."""
    current_user = get_current_user(request, db)
    if not current_user:
        raise HTTPException(status_code=401, detail="Niet ingelogd")

    shape = db.query(DepartmentShape).filter(DepartmentShape.shape_id == shape_id).first()
    if not shape:
        raise HTTPException(status_code=404, detail="Shape niet gevonden")

    # Toggle logica
    if shape.department_id == dept_id:
        shape.department_id = None
        shape.match_method = None
        action = "unassigned"
        log_action(db, current_user.username, "UPDATE", "Werkingsgebied", shape.name,
                   f"Ontkoppeld van afdeling {dept_id}")
    else:
        shape.department_id = dept_id
        shape.match_method = MatchMethodEnum.MANUELE_OVERRIDE
        action = "assigned"
        log_action(db, current_user.username, "UPDATE", "Werkingsgebied", shape.name,
                   f"Manueel gekoppeld aan afdeling {dept_id}")

    db.commit()
    return {"action": action}


@app.post("/generate-map")
async def trigger_map_generation(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    if current_user.role not in ["admin", "nationaal"]:
        raise HTTPException(status_code=403, detail="Alleen beheerders kunnen de hoofdkaart genereren.")

    # Voorlopige paden bepalen
    output_dir = "/opt/MapGenerator/static"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "RodeKruis_Kaart.html")

    try:
        # Hier roepen we straks jouw script aan:
        # generate_master_map(db, output_file)

        # Tijdelijke dummy file voor test
        with open(output_file, "w") as f:
            f.write("<h1>Kaart wordt gegenereerd...</h1><p>Dit is een tijdelijke test.</p>")

        # Log de actie
        log_action(db, current_user.username, "CREATE", "Kaart", "Master Map", "Nieuwe kaart gegenereerd")

        # Redirect naar het dashboard met een success-parameter
        return RedirectResponse(url="/?map_generated=true", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        print(f"Fout bij genereren: {e}")
        raise HTTPException(status_code=500, detail="Fout bij het genereren van de kaart.")


@app.get("/api/departments/{dept_id}/markers")
async def get_department_markers(dept_id: int, db: Session = Depends(get_db)):
    """Haalt de opgeslagen coördinaten op van de hoofdlocatie en voertuigen."""
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Afdeling niet gevonden")

    markers = []

    # 1. Hoofdlocatie van de afdeling
    if dept.lat and dept.lon:
        markers.append({
            "type": "main",
            "name": dept.name,
            "address": dept.address or "Geen adres",
            "lat": dept.lat,
            "lon": dept.lon
        })

    # 2. Ziekenwagens en voertuigen
    for vehicle in dept.vehicles:
        if vehicle.lat and vehicle.lon:
            markers.append({
                "type": "vehicle",
                "name": vehicle.name,
                "fleet_nr": vehicle.fleet_nr or "Onbekend",
                "address": vehicle.address or "Geen adres",
                "lat": vehicle.lat,
                "lon": vehicle.lon
            })

    return {"markers": markers}


# --- VRIJWILLIGE WACHTWOORD WIJZIGING ---
@app.get("/profile/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="change_password.html",
                                      context={"user": current_user, "error": None})


@app.post("/profile/change-password")
async def change_password(
        request: Request,
        current_password: str = Form(...),
        new_password: str = Form(...),
        db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    # Verifieer het huidige wachtwoord
    if not bcrypt.checkpw(current_password.encode('utf-8'), current_user.password_hash.encode('utf-8')):
        return templates.TemplateResponse(
            request=request, name="change_password.html",
            context={"user": current_user, "error": "Huidig wachtwoord is onjuist."}
        )

    # Sla het nieuwe wachtwoord op
    current_user.password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Eventuele force-vlag weghalen
    if getattr(current_user, 'force_password_change', False):
        current_user.force_password_change = False

    log_action(db, current_user.username, "UPDATE", "Gebruiker", current_user.username, "Wachtwoord zelf gewijzigd.")
    db.commit()

    return RedirectResponse(url="/?password_changed=true", status_code=status.HTTP_303_SEE_OTHER)


# --- GEFORCEERDE WACHTWOORD WIJZIGING (BIJ EERSTE LOGIN) ---
@app.get("/profile/force-password-change", response_class=HTMLResponse)
async def force_password_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="force_password.html", context={"user": current_user})


@app.post("/profile/force-password-change")
async def process_force_password(request: Request, new_password: str = Form(...), db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    current_user.password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    current_user.force_password_change = False

    log_action(db, current_user.username, "UPDATE", "Gebruiker", current_user.username,
               "Geforceerde wachtwoord-reset uitgevoerd.")
    db.commit()

    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


# =========================================================
# KAART GENERATOR ROUTES
# =========================================================

@app.get("/maps", response_class=HTMLResponse)
async def map_management_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    files = glob.glob(os.path.join(OUTPUT_DIR, "*.html"))

    # Maak een nette lijst met bestandsinformatie (nieuwste bovenaan)
    map_files = []
    for f in files:
        stat = os.stat(f)
        map_files.append({
            "name": os.path.basename(f),
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "created": datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
            "timestamp": stat.st_ctime
        })
    map_files.sort(key=lambda x: x["timestamp"], reverse=True)

    # Bepaal welke provincies de gebruiker mag genereren
    if current_user.role in ["admin", "nationaal"]:
        provinces = ["Vlaanderen", "Antwerpen", "Limburg", "Oost-Vlaanderen", "West-Vlaanderen", "Vlaams-Brabant",
                     "Brussel"]
    else:
        provinces = [current_user.province_access]

    return templates.TemplateResponse(request=request, name="maps.html", context={
        "user": current_user,
        "map_files": map_files,
        "provinces": provinces
    })


@app.get("/maps/preview/{filename}", response_class=HTMLResponse)
async def preview_map(request: Request, filename: str, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    safe_filename = unquote(filename)
    file_path = os.path.join(OUTPUT_DIR, safe_filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Kaart niet gevonden.")

    return templates.TemplateResponse(request=request, name="preview_map.html", context={
        "user": current_user,
        "filename": safe_filename
    })


@app.get("/maps/download/{filename}")
async def download_map(filename: str):
    safe_filename = unquote(filename)
    file_path = os.path.join(OUTPUT_DIR, safe_filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Kaart niet gevonden.")

    return FileResponse(path=file_path, filename=safe_filename, media_type='text/html')


@app.post("/maps/generate")
async def trigger_map_generation(
        request: Request,
        background_tasks: BackgroundTasks,
        province: str = Form(...),
        db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    if province != "Vlaanderen" and current_user.role == "provinciaal" and current_user.province_access != province:
        return HTMLResponse("<h2>Geen rechten voor deze provincie.</h2>", status_code=403)

    # Log de actie
    log_action(db, current_user.username, "CREATE", "Kaart", f"Kaart {province}", "Generatie gestart op de achtergrond")
    db.commit()

    # Roep de externe generator.py functie aan via de background_tasks
    background_tasks.add_task(background_generate_map, province, current_user.username)

    return RedirectResponse(url="/maps?status=generating", status_code=status.HTTP_303_SEE_OTHER)
