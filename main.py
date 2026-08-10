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
# Create database tables if not exist
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Rode Kruis Map Generator")

# SECURE SESSION MIDDLEWARE (Replace with a strong random secret key in production)
app.add_middleware(SessionMiddleware, secret_key="rk-map-generator-super-secret-key-change-me")

templates = Jinja2Templates(directory="templates")


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


# Helper: Get current logged-in user from session
def get_current_user(request: Request, db: Session = Depends(get_db)):
    username = request.session.get("username")
    if not username:
        return None
    user = db.query(User).filter(User.username == username).first()
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


# ---------------------------------------------------------
# AUTHENTICATION ROUTES
# ---------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # If already logged in, redirect to dashboard
    if request.session.get("username"):
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()

    # Verify user exists and password matches
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Ongeldige gebruikersnaam of wachtwoord."}
        )

    # Set session data
    request.session["username"] = user.username
    request.session["role"] = user.role
    request.session["province_access"] = user.province_access

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
        lat=float(form.get("lat")) if form.get("lat") else None,
        lon=float(form.get("lon")) if form.get("lon") else None
    )
    db.add(new_dept)
    db.flush()  # Genereer ID

    # Leden (Deelgemeenten) opslaan
    for m_name in form.getlist("members[]"):
        if m_name.strip(): db.add(Municipality(name=m_name.strip(), department_id=new_dept.id))

    # Voertuigen opslaan
    v_names = form.getlist("vehicle_name[]")
    v_fleets = form.getlist("vehicle_fleet[]")
    v_addresses = form.getlist("vehicle_address[]")
    v_lats = form.getlist("vehicle_lat[]")
    v_lons = form.getlist("vehicle_lon[]")
    for i in range(len(v_names)):
        if v_names[i].strip():
            db.add(Vehicle(
                name=v_names[i].strip(), fleet_nr=v_fleets[i].strip() if v_fleets[i] else None,
                address=v_addresses[i].strip() if v_addresses[i] else None,
                lat=float(v_lats[i]) if v_lats[i] else None, lon=float(v_lons[i]) if v_lons[i] else None,
                department_id=new_dept.id
            ))

    # Services (Disciplines) opslaan
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

    new_sit = SitLocation(
        name=form.get("name"), province=province, type=form.get("type"), address=form.get("address"),
        lat=float(form.get("lat")) if form.get("lat") else None, lon=float(form.get("lon")) if form.get("lon") else None
    )
    db.add(new_sit)
    db.flush()

    v_names = form.getlist("vehicle_name[]")
    v_fleets = form.getlist("vehicle_fleet[]")
    for i in range(len(v_names)):
        if v_names[i].strip():
            db.add(SitVehicle(name=v_names[i].strip(), fleet_nr=v_fleets[i].strip() if v_fleets[i] else None,
                              sit_location_id=new_sit.id))

    log_action(db, current_user.username, "CREATE", "SIT-Locatie", new_sit.name, "Nieuwe SIT aangemaakt.")
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
        db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user or current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Toegang geweigerd.")

    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="Gebruikersnaam bestaat al.")

    hashed_pwd = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    new_user = User(username=username, password_hash=hashed_pwd, role=role, province_access=province_access)
    db.add(new_user)
    log_action(db, current_user.username, "CREATE", "Gebruiker", username, f"Rol: {role}, Provincie: {province_access}")
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


@app.post("/users/edit/{user_id}")
async def update_user(
        user_id: int,
        request: Request,
        username: str = Form(...),
        password: str = Form(None),
        role: str = Form(...),
        province_access: str = Form("All"),
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

    if password and password.strip():
        target_user.password_hash = bcrypt.hashpw(password.strip().encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    log_action(db, current_user.username, "UPDATE", "Gebruiker", username, f"Rol: {role}, Provincie: {province_access}")
    db.commit()
    return RedirectResponse(url="/users", status_code=status.HTTP_303_SEE_OTHER)


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
        return HTMLResponse(
            "<h2>Actie geweigerd</h2><p>Je hebt geen rechten om deze afdeling te bewerken.</p><a href='/departments'>Ga terug</a>",
            status_code=403)

    changes = []
    if str(dept.name) != str(form.get("name")): changes.append("naam")
    if str(dept.province) != str(form.get("province")): changes.append("provincie")

    dept.name = form.get("name")
    dept.province = new_province
    dept.group = form.get("group")
    dept.address = form.get("address")
    dept.email = form.get("email")
    dept.telephone = form.get("telephone")
    dept.entiteitnummer = form.get("entiteitnummer")
    dept.color = form.get("color")
    dept.lat = float(form.get("lat")) if form.get("lat") else None
    dept.lon = float(form.get("lon")) if form.get("lon") else None
    dept.type = "provinciale_zetel" if form.get("is_provinciale_zetel") else "afdeling"
    dept.transparent = True if form.get("transparent") else False

    db.query(Municipality).filter(Municipality.department_id == dept.id).delete()
    for m_name in form.getlist("members[]"):
        if m_name.strip(): db.add(Municipality(name=m_name.strip(), department_id=dept.id))

    db.query(Vehicle).filter(Vehicle.department_id == dept.id).delete()
    v_names = form.getlist("vehicle_name[]")
    v_fleets = form.getlist("vehicle_fleet[]")
    v_addresses = form.getlist("vehicle_address[]")
    v_lats = form.getlist("vehicle_lat[]")
    v_lons = form.getlist("vehicle_lon[]")
    for i in range(len(v_names)):
        if v_names[i].strip():
            db.add(Vehicle(name=v_names[i].strip(), fleet_nr=v_fleets[i].strip() if v_fleets[i] else None,
                           address=v_addresses[i].strip() if v_addresses[i] else None,
                           lat=float(v_lats[i]) if v_lats[i] else None, lon=float(v_lons[i]) if v_lons[i] else None,
                           department_id=dept.id))

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

    sit.name = form.get("name")
    sit.province = new_province
    sit.type = form.get("type")
    sit.address = form.get("address")
    sit.lat = float(form.get("lat")) if form.get("lat") else None
    sit.lon = float(form.get("lon")) if form.get("lon") else None

    db.query(SitVehicle).filter(SitVehicle.sit_location_id == sit.id).delete()
    v_names = form.getlist("vehicle_name[]")
    v_fleets = form.getlist("vehicle_fleet[]")
    for i in range(len(v_names)):
        if v_names[i].strip():
            db.add(SitVehicle(name=v_names[i].strip(), fleet_nr=v_fleets[i].strip() if v_fleets[i] else None,
                              sit_location_id=sit.id))

    log_action(db, current_user.username, "UPDATE", "SIT-Locatie", sit.name, "SIT Gewijzigd")
    db.commit()
    return RedirectResponse(url="/sit-locations", status_code=status.HTTP_303_SEE_OTHER)


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


# Route om de statische kaart daadwerkelijk te kunnen bekijken
from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="/opt/MapGenerator/static"), name="static")