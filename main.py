from fastapi import FastAPI, Depends, HTTPException, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
import bcrypt

from database import SessionLocal, engine, Base, User, Department, Vehicle, SitLocation, SitVehicle, Service

# Create database tables if not exist
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Rode Kruis Map Generator")

# SECURE SESSION MIDDLEWARE (Replace with a strong random secret key in production)
app.add_middleware(SessionMiddleware, secret_key="rk-map-generator-super-secret-key-change-me")

templates = Jinja2Templates(directory="templates")

# Dependency: Get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper: Get current logged-in user from session
def get_current_user(request: Request, db: Session = Depends(get_db)):
    username = request.session.get("username")
    if not username:
        return None
    user = db.query(User).filter(User.username == username).first()
    return user

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
    return templates.TemplateResponse(request=request, name="departments.html", context={"user": current_user, "departments": departments})

@app.get("/provinciale-zetels", response_class=HTMLResponse)
async def list_provinciale_zetels(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    zetels = db.query(Department).filter(Department.type == "provinciale_zetel").order_by(Department.name).all()
    return templates.TemplateResponse(request=request, name="provinciale_zetels.html", context={"user": current_user, "zetels": zetels})

@app.get("/sit-locations", response_class=HTMLResponse)
async def list_sit_locations(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    sits = db.query(SitLocation).order_by(SitLocation.name).all()
    return templates.TemplateResponse(request=request, name="sit_locations.html", context={"user": current_user, "sits": sits})

@app.get("/regions", response_class=HTMLResponse)
async def manage_regions(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    regions = db.query(Region).all()
    departments = db.query(Department).filter(Department.type != "provinciale_zetel").all()
    return templates.TemplateResponse(request=request, name="regions.html", context={"user": current_user, "regions": regions, "departments": departments, "edit_region": None})

@app.get("/clusters", response_class=HTMLResponse)
async def manage_clusters(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    clusters = db.query(Cluster).all()
    regions = db.query(Region).all()
    departments = db.query(Department).filter(Department.type != "provinciale_zetel").all()
    return templates.TemplateResponse(request=request, name="clusters.html", context={"user": current_user, "clusters": clusters, "regions": regions, "departments": departments, "edit_cluster": None})

@app.get("/departments/edit/{dept_id}", response_class=HTMLResponse)
async def edit_department_page(request: Request, dept_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Afdeling niet gevonden")
        
    # Beveiliging: Mag deze gebruiker deze afdeling bewerken?
    if current_user.role == "provinciaal" and current_user.province_access != dept.province:
        raise HTTPException(status_code=403, detail="Geen toegang tot afdelingen buiten jouw provincie.")

    return templates.TemplateResponse(
        request=request,
        name="edit_department.html",
        context={"user": current_user, "dept": dept}
    )
@app.post("/departments/edit/{dept_id}")
async def update_department(
    request: Request,
    dept_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Afdeling niet gevonden")
        
    # VEILIGHEIDSCHECK
    verify_edit_permission(current_user, dept.province) # Check huidige provincie
    if new_province != dept.province:
        verify_edit_permission(current_user, new_province) # Check ook als ze de provincie zouden veranderen

    # Haal alle formulier data op
    form = await request.form()

    # Update basisvelden
    dept.name = form.get("name")
    dept.province = form.get("province")
    dept.group = form.get("group")
    dept.address = form.get("address")
    dept.email = form.get("email")
    dept.telephone = form.get("telephone")
    dept.entiteitnummer = form.get("entiteitnummer")
    dept.color = form.get("color")
    
    # Coördinaten converteren naar float indien ingevuld
    dept.lat = float(form.get("lat")) if form.get("lat") else None
    dept.lon = float(form.get("lon")) if form.get("lon") else None
    
    # Checkboxes verwerken
    dept.type = "provinciale_zetel" if form.get("is_provinciale_zetel") else "afdeling"
    dept.transparent = True if form.get("transparent") else False

    # --- ZIEKENWAGENS (VEHICLES) VERWERKEN ---
    # We verwijderen eerst de oude voertuigen van deze afdeling
    db.query(Vehicle).filter(Vehicle.department_id == dept.id).delete()
    
    # Lees de arrays uit de HTML input velden (vehicle_name[], vehicle_fleet[], etc.)
    v_names = form.getlist("vehicle_name[]")
    v_fleets = form.getlist("vehicle_fleet[]")
    v_addresses = form.getlist("vehicle_address[]")
    v_lats = form.getlist("vehicle_lat[]")
    v_lons = form.getlist("vehicle_lon[]")
    
    # Loop over de doorgegeven voertuigen en sla ze op
    for i in range(len(v_names)):
        if v_names[i].strip(): # Alleen toevoegen als er een naam is
            new_vehicle = Vehicle(
                name=v_names[i].strip(),
                fleet_nr=v_fleets[i].strip() if v_fleets[i] else None,
                address=v_addresses[i].strip() if v_addresses[i] else None,
                lat=float(v_lats[i]) if v_lats[i] else None,
                lon=float(v_lons[i]) if v_lons[i] else None,
                department_id=dept.id
            )
            db.add(new_vehicle)
    # --- SERVICES (DISCIPLINES) VERWERKEN ---
    # Haal de lijst met aangevinkte services op
    services_list = form.getlist("services[]")
    
    # Maak de huidige lijst leeg in de database relatie
    dept.services.clear()
    
    for srv_name in services_list:
        srv_name = srv_name.lower().strip()
        if srv_name:
            # Check of de service al bestaat in de globale services tabel
            service = db.query(Service).filter(Service.name == srv_name).first()
            if not service:
                service = Service(name=srv_name)
                db.add(service)
                db.flush() # Genereer direct een ID
            dept.services.append(service)
    db.commit()
    return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/sit-locations/edit/{sit_id}", response_class=HTMLResponse)
async def edit_sit_page(request: Request, sit_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    
    sit = db.query(SitLocation).filter(SitLocation.id == sit_id).first()
    if not sit:
        raise HTTPException(status_code=404, detail="SIT niet gevonden")
        
    if current_user.role == "provinciaal" and current_user.province_access != sit.province:
        raise HTTPException(status_code=403, detail="Geen toegang.")

    return templates.TemplateResponse(
        request=request,
        name="edit_sit.html",
        context={"user": current_user, "sit": sit}
    )

@app.post("/sit-locations/edit/{sit_id}")
async def update_sit(
    request: Request,
    sit_id: int,
    db: Session = Depends(get_db)
):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
    sit = db.query(SitLocation).filter(SitLocation.id == sit_id).first()
    if not sit:
        raise HTTPException(status_code=404, detail="SIT niet gevonden")

    verify_edit_permission(current_user, sit.province)
    if new_province != sit.province:
        verify_edit_permission(current_user, new_province)

    form = await request.form()

    sit.name = form.get("name")
    sit.province = form.get("province") # Opslaan van de provincie
    sit.type = form.get("type")
    sit.address = form.get("address")
    sit.lat = float(form.get("lat")) if form.get("lat") else None
    sit.lon = float(form.get("lon")) if form.get("lon") else None
    
    # Voertuigen verwerken
    db.query(SitVehicle).filter(SitVehicle.sit_location_id == sit.id).delete()
    
    v_names = form.getlist("vehicle_name[]")
    v_fleets = form.getlist("vehicle_fleet[]")
    
    for i in range(len(v_names)):
        if v_names[i].strip():
            db.add(SitVehicle(
                name=v_names[i].strip(),
                fleet_nr=v_fleets[i].strip() if v_fleets[i] else None,
                sit_location_id=sit.id
            ))
    
    db.commit()
    return RedirectResponse(url="/sit-locations", status_code=status.HTTP_303_SEE_OTHER)

from database import Region, Cluster, Municipality

# --- AFDELINGEN TOEVOEGEN & VERWIDEREN ---

@app.get("/departments/new", response_class=HTMLResponse)
async def new_department_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="edit_department.html", context={"user": current_user, "dept": None})

@app.post("/departments/new")
async def create_department(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
    form = await request.form()
    new_dept = Department(
        name=form.get("name"),
        province=form.get("province"),
        group=form.get("group"),
        address=form.get("address"),
        email=form.get("email"),
        telephone=form.get("telephone"),
        entiteitnummer=form.get("entiteitnummer"),
        color=form.get("color"),
        type="provinciale_zetel" if form.get("is_provinciale_zetel") else "afdeling",
        transparent=True if form.get("transparent") else False,
        lat=float(form.get("lat")) if form.get("lat") else None,
        lon=float(form.get("lon")) if form.get("lon") else None
    )
    db.add(new_dept)
    db.commit()
    return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/departments/delete/{dept_id}")
async def delete_department(dept_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
    dept = db.query(Department).filter(Department.id == dept_id).first()
    if dept:
        verify_edit_permission(current_user, dept.province)
        db.delete(dept)
        db.commit()
    return RedirectResponse(url="/departments", status_code=status.HTTP_303_SEE_OTHER)


# --- SIT LOCATIES TOEVOEGEN & VERWIDEREN ---

@app.get("/sit-locations/new", response_class=HTMLResponse)
async def new_sit_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request=request, name="edit_sit.html", context={"user": current_user, "sit": None})

@app.post("/sit-locations/new")
async def create_sit(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
    form = await request.form()
    new_sit = SitLocation(
        name=form.get("name"),
        province=form.get("province"),
        type=form.get("type"),
        address=form.get("address"),
        lat=float(form.get("lat")) if form.get("lat") else None,
        lon=float(form.get("lon")) if form.get("lon") else None
    )
    db.add(new_sit)
    db.commit()
    return RedirectResponse(url="/sit-locations", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/sit-locations/delete/{sit_id}")
async def delete_sit(sit_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
    sit = db.query(SitLocation).filter(SitLocation.id == sit_id).first()
    if sit:
        verify_edit_permission(current_user, sit.province)
        db.delete(sit)
        db.commit()
    return RedirectResponse(url="/sit-locations", status_code=status.HTTP_303_SEE_OTHER)


# --- REGIO'S & CLUSTERS BEHEER ---


@app.post("/regions/save")
async def save_region(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    reg_id = form.get("region_id")
    name = form.get("name")
    province = form.get("province")
    selected_depts = form.getlist("departments[]")

    verify_edit_permission(current_user, province)
    if reg_id:
        existing_reg = db.query(Region).filter(Region.id == int(reg_id)).first()
        if existing_reg:
            verify_edit_permission(current_user, existing_reg.province)
        region = db.query(Region).filter(Region.id == int(reg_id)).first()
        region.name = name
        region.province = province
    else:
        region = Region(name=name, province=province)
        db.add(region)
        db.flush()
        
    # Reset en koppel afdelingen
    db.query(Department).filter(Department.region_id == region.id).update({"region_id": None})
    if selected_depts:
        db.query(Department).filter(Department.id.in_([int(d) for d in selected_depts])).update({"region_id": region.id}, synchronize_session=False)
        
    db.commit()
    return RedirectResponse(url="/regions", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/clusters/save")
async def save_cluster(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    clus_id = form.get("cluster_id")
    name = form.get("name")
    province = form.get("province")
    region_id = form.get("region_id")
    selected_depts = form.getlist("departments[]")
    
    if clus_id:
        cluster = db.query(Cluster).filter(Cluster.id == int(clus_id)).first()
        cluster.name = name
        cluster.province = province
        cluster.region_id = int(region_id) if region_id else None
    else:
        cluster = Cluster(name=name, province=province, region_id=int(region_id) if region_id else None)
        db.add(cluster)
        db.flush()
    


    verify_edit_permission(current_user, province)
    if clus_id:
        existing_clus = db.query(Cluster).filter(Cluster.id == int(clus_id)).first()
        if existing_clus:
            verify_edit_permission(current_user, existing_clus.province)

    db.query(Department).filter(Department.cluster_id == cluster.id).update({"cluster_id": None})
    if selected_depts:
        db.query(Department).filter(Department.id.in_([int(d) for d in selected_depts])).update({"cluster_id": cluster.id}, synchronize_session=False)
        
    db.commit()
    return RedirectResponse(url="/clusters", status_code=status.HTTP_303_SEE_OTHER)

# --- REGIO'S BEHEER (BEWERKEN & VERWIJDEREN) ---

@app.get("/regions/edit/{reg_id}", response_class=HTMLResponse)
async def edit_region_page(request: Request, reg_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
    region = db.query(Region).filter(Region.id == reg_id).first()
    if not region:
        raise HTTPException(status_code=404, detail="Regio niet gevonden")
        
    regions = db.query(Region).all()
    departments = db.query(Department).filter(Department.type != "provinciale_zetel").all()
    
    return templates.TemplateResponse(
        request=request, 
        name="regions.html", 
        context={"user": current_user, "regions": regions, "departments": departments, "edit_region": region}
    )

@app.post("/regions/delete/{reg_id}")
async def delete_region(reg_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
    region = db.query(Region).filter(Region.id == reg_id).first()
    if region:
        verify_edit_permission(current_user, region.province)
        db.delete(region)
        db.commit()
    return RedirectResponse(url="/regions", status_code=status.HTTP_303_SEE_OTHER)


# --- CLUSTERS BEHEER (BEWERKEN & VERWIJDEREN) ---

@app.get("/clusters/edit/{clus_id}", response_class=HTMLResponse)
async def edit_cluster_page(request: Request, clus_id: int, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
    cluster = db.query(Cluster).filter(Cluster.id == clus_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster niet gevonden")
        
    clusters = db.query(Cluster).all()
    regions = db.query(Region).all()
    departments = db.query(Department).filter(Department.type != "provinciale_zetel").all()
    
    return templates.TemplateResponse(
        request=request, 
        name="clusters.html", 
        context={"user": current_user, "clusters": clusters, "regions": regions, "departments": departments, "edit_cluster": cluster}
    )

@app.post("/clusters/delete/{clus_id}")
async def delete_cluster(clus_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        
    cluster = db.query(Cluster).filter(Cluster.id == clus_id).first()
    if cluster:
        verify_edit_permission(current_user, region.province)
        db.delete(cluster)
        db.commit()
    return RedirectResponse(url="/clusters", status_code=status.HTTP_303_SEE_OTHER)

