import time
from sqlalchemy.orm import Session
from sqlalchemy import text
from geopy.geocoders import Nominatim
from database import SessionLocal, Department, Vehicle, SitLocation


def resolve_all_addresses():
    db: Session = SessionLocal()
    geolocator = Nominatim(user_agent="rk_map_generator_backend", timeout=10)

    print("Start eenmalige adres-resolutie...")

    # 1. AFDELINGEN
    print("\n--- Controleren van Afdelingen ---")
    departments = db.query(Department).all()
    for dept in departments:
        if dept.lat and dept.lon:
            continue  # Coördinaten bestaan al, overslaan

        print(f"Behandelen afdeling: {dept.name}")
        resolved = False

        # Probeer eerst op adres
        if dept.address:
            full_address = f"{dept.address.strip()}, België"
            try:
                location = geolocator.geocode(full_address)
                time.sleep(1.1)  # Rate limiting

                if location:
                    dept.lat = location.latitude
                    dept.lon = location.longitude
                    resolved = True
                    print(f"  -> Adres gevonden: {location.latitude}, {location.longitude}")
            except Exception as e:
                print(f"  -> API Fout bij {dept.name}: {e}")
                time.sleep(1.1)

        # Fallback: Bereken het ruimtelijke middelpunt (centroid) als API faalt of adres leeg is
        if not resolved:
            print("  -> Geen (geldig) adres. Berekenen van polygon-middelpunt...")
            sql = """
                SELECT ST_X(ST_Centroid(ST_Union(geom::geometry))) as lon, 
                       ST_Y(ST_Centroid(ST_Union(geom::geometry))) as lat 
                FROM department_shapes 
                WHERE department_id = :dept_id
            """
            result = db.execute(text(sql), {"dept_id": dept.id}).fetchone()

            if result and result.lat and result.lon:
                dept.lat = result.lat
                dept.lon = result.lon
                print(f"  -> Middelpunt berekend: {result.lat}, {result.lon}")
            else:
                print("  -> FOUT: Geen polygonen gekoppeld. Locatie blijft leeg.")

    # 2. VOERTUIGEN
    print("\n--- Controleren van Voertuigen ---")
    vehicles = db.query(Vehicle).all()
    for veh in vehicles:
        if veh.lat and veh.lon:
            continue

        print(f"Behandelen voertuig: {veh.name} (Afdeling ID: {veh.department_id})")
        resolved = False

        if veh.address:
            full_address = f"{veh.address.strip()}, België"
            try:
                location = geolocator.geocode(full_address)
                time.sleep(1.1)

                if location:
                    veh.lat = location.latitude
                    veh.lon = location.longitude
                    resolved = True
                    print(f"  -> Voertuig adres gevonden: {location.latitude}, {location.longitude}")
            except Exception as e:
                print(f"  -> API Fout bij voertuig {veh.name}: {e}")
                time.sleep(1.1)

        # Fallback voor voertuigen: Gebruik de coördinaten van de hoofdafdeling
        if not resolved and veh.department:
            print("  -> Terugvallen op coördinaten van de hoofdafdeling...")
            veh.lat = veh.department.lat
            veh.lon = veh.department.lon

    # 3. SIT-LOCATIES
    print("\n--- Controleren van SIT-Locaties ---")
    sit_locations = db.query(SitLocation).all()
    for sit in sit_locations:
        if sit.lat and sit.lon:
            continue

        print(f"Behandelen SIT: {sit.name}")
        if sit.address:
            full_address = f"{sit.address.strip()}, België"
            try:
                location = geolocator.geocode(full_address)
                time.sleep(1.1)

                if location:
                    sit.lat = location.latitude
                    sit.lon = location.longitude
                    print(f"  -> SIT adres gevonden: {location.latitude}, {location.longitude}")
                else:
                    print("  -> Adres niet gevonden door API.")
            except Exception as e:
                print(f"  -> API Fout bij SIT {sit.name}: {e}")
                time.sleep(1.1)
        else:
            print("  -> Geen adres ingevuld.")

    # Sla alles in één keer op
    db.commit()
    db.close()
    print("\nAdres-resolutie voltooid en opgeslagen in de database!")


if __name__ == "__main__":
    resolve_all_addresses()