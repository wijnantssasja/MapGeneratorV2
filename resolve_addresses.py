import time
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from geopy.geocoders import Nominatim
from database import SessionLocal, Department, Vehicle, SitLocation, CoordinateCache


def update_coordinate_cache():
    db: Session = SessionLocal()
    geolocator = Nominatim(user_agent="rk_map_generator_backend", timeout=10)

    print("Start eenmalige/wekelijkse adres-resolutie (Cache Update)...")

    # 1. Verzamel alle unieke adressen uit de database
    addresses = set()

    for model in [Department, Vehicle, SitLocation]:
        items = db.query(model.address).filter(model.address != None).all()
        for item in items:
            if item.address and item.address.strip():
                addresses.add(item.address.strip())

    print(f"Totaal aantal unieke adressen gevonden: {len(addresses)}")

    # 2. Bepaal de grensdatum voor de wekelijkse refresh (7 dagen geleden)
    one_week_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    updated_count = 0

    # 3. Loop over de unieke adressen en controleer/update de cache
    for addr in addresses:
        # Zoek het adres in de cache
        cache_entry = db.query(CoordinateCache).filter(CoordinateCache.address == addr).first()

        # Skip als het adres al in de cache zit én recent is
        if cache_entry and cache_entry.last_checked and cache_entry.last_checked > one_week_ago:
            continue

        print(f"Resolven van adres: '{addr}'...")
        full_address = f"{addr}, België"

        try:
            time.sleep(1.1)  # Strikte rate-limiting
            location = geolocator.geocode(full_address)

            if location:
                if cache_entry:
                    cache_entry.lat = location.latitude
                    cache_entry.lon = location.longitude
                    cache_entry.last_checked = datetime.now(timezone.utc)
                    db.commit()  # Direct opslaan!
                    print(f"  -> [UPDATE] Cache wekelijks vernieuwd: {location.latitude}, {location.longitude}")
                else:
                    new_cache = CoordinateCache(
                        address=addr,
                        lat=location.latitude,
                        lon=location.longitude,
                        last_checked=datetime.now(timezone.utc)
                    )
                    db.add(new_cache)
                    try:
                        db.commit()  # Direct opslaan!
                        print(f"  -> [NIEUW] Toegevoegd aan cache: {location.latitude}, {location.longitude}")
                    except IntegrityError:
                        db.rollback()  # De applicatie was ons voor!
                        print(f"  -> [SKIP] Dit adres was ondertussen al toegevoegd door de live webapplicatie.")

                updated_count += 1
            else:
                print(f"  -> [FAIL] Adres niet gevonden door API.")
                if cache_entry:
                    cache_entry.last_checked = datetime.now(timezone.utc)
                    db.commit()

        except Exception as e:
            db.rollback()
            print(f"  -> [ERROR] API Fout bij '{addr}': {e}")
            time.sleep(1.1)

    db.close()
    print(f"\nKlaar! {updated_count} adressen (opnieuw) ge-resolved en opgeslagen in de CoordinateCache.")


if __name__ == "__main__":
    update_coordinate_cache()