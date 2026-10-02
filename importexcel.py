import pandas as pd
import math
from sqlalchemy.orm import Session
# Pas de import hieronder aan naar de naam van jouw bestand met DB-modellen (bijv. 'database' of 'models')
from database import SessionLocal, Department, Region, Service, Vehicle, Municipality


def run_import():
    db: Session = SessionLocal()

    # 1. Lees het Excel-bestand
    excel_file = "Configuratie_West-Vlaanderen.xlsx"
    print(f"Start met inlezen van {excel_file}...")
    df = pd.read_excel(excel_file)

    # Vervang NaN (Not a Number) waardes in tekstvelden door lege strings of None
    df = df.where(pd.notnull(df), None)

    for index, row in df.iterrows():
        dept_name = row.get('Department_ID')
        if not dept_name:
            continue

        print(f"Verwerken: {dept_name}...")

        # --- REGIO BEHEREN ---
        region_name = row.get('regio')
        province = row.get('province') or "Antwerpen"
        db_region = None

        if region_name:
            region_name = str(region_name).strip()
            db_region = db.query(Region).filter(Region.name == region_name, Region.province == province).first()
            if not db_region:
                db_region = Region(name=region_name, province=province)
                db.add(db_region)
                db.flush()  # Zorg dat db_region een ID krijgt

        # --- AFDELING BEHEREN ---
        dept = db.query(Department).filter(Department.name == dept_name).first()
        if not dept:
            dept = Department(name=dept_name)
            db.add(dept)

        # Update attributen
        dept.type = row.get('Type') if row.get('Type') else "afdeling"
        dept.entiteitnummer = str(row.get('entiteitnummer')) if row.get('entiteitnummer') else None
        dept.province = province
        dept.email = str(row.get('email')) if row.get('email') else None
        dept.telephone = str(row.get('telephone')) if row.get('telephone') else None
        dept.address = str(row.get('address')) if row.get('address') else None

        if db_region:
            dept.region_id = db_region.id

        # --- SERVICES (DISCIPLINES) KOPPELEN ---
        dept.services.clear()  # Wis oude koppelingen
        service_cols = [c for c in df.columns if c.startswith('Service:')]
        for col in service_cols:
            val = row.get(col)
            if val and str(val).strip().lower() == 'x':
                srv_name = col.replace('Service:', '').strip().lower()
                # Haal service op of maak aan
                service_obj = db.query(Service).filter(Service.name == srv_name).first()
                if not service_obj:
                    service_obj = Service(name=srv_name)
                    db.add(service_obj)
                    db.flush()
                dept.services.append(service_obj)

        # --- VOERTUIGEN (ZIEKENWAGENS) BEHEREN ---
        # Verwijder oude voertuigen zodat we ze netjes kunnen heraanmaken vanuit de Excel
        db.query(Vehicle).filter(Vehicle.department_id == dept.id).delete()

        # Voertuig 1
        if row.get('ZW_1_Naam'):
            db.add(Vehicle(
                name=str(row.get('ZW_1_Naam')).strip(),
                fleet_nr=str(row.get('ZW_1_roepnaam')).strip() if row.get('ZW_1_roepnaam') else None,
                address=str(row.get('ZW_1_Adres')).strip() if row.get('ZW_1_Adres') else None,
                department_id=dept.id
            ))

        # Voertuig 2
        if row.get('ZW_2_Naam'):
            db.add(Vehicle(
                name=str(row.get('ZW_2_Naam')).strip(),
                fleet_nr=str(row.get('ZW_2_Vlootnummer')).strip() if row.get('ZW_2_Vlootnummer') else None,
                address=str(row.get('ZW_2_Adres')).strip() if row.get('ZW_2_Adres') else None,
                department_id=dept.id
            ))

        # Voertuig 3
        if row.get('ZW_3_Naam'):
            db.add(Vehicle(
                name=str(row.get('ZW_3_Naam')).strip(),
                fleet_nr=str(row.get('ZW_3_Vlootnummer')).strip() if row.get('ZW_3_Vlootnummer') else None,
                address=str(row.get('ZW_3_Adres')).strip() if row.get('ZW_3_Adres') else None,
                department_id=dept.id
            ))

        # --- GEMEENTEN (MEMBERS) BEHEREN ---
        # Verwijder oude members zodat we niet dubbelen
        db.query(Municipality).filter(Municipality.department_id == dept.id).delete()
        members_str = row.get('members')
        if members_str:
            # We splitsen op de komma
            municipalities = [m.strip() for m in str(members_str).split(',')]
            for mun in municipalities:
                if mun:
                    db.add(Municipality(name=mun, department_id=dept.id))

    # Commit alles in 1 keer naar de database
    db.commit()
    db.close()
    print("Klaar! De database is succesvol bijgewerkt.")


if __name__ == "__main__":
    # Voer importeer-script uit
    # Zorg dat de pandas openpyxl library is geïnstalleerd: pip install pandas openpyxl
    run_import()