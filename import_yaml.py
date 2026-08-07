import yaml
from database import SessionLocal, Department, Service, Municipality, Vehicle, SitLocation, SitVehicle, Region, Cluster

def import_data():
    db = SessionLocal()
    
    print("Lezen van config_ALL_gesorteerd.yaml...")
    try:
        with open("/opt/MapGenerator/config_ALL_gesorteerd.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print("Fout: config_ALL_gesorteerd.yaml niet gevonden in /opt/MapGenerator/")
        return

    print("Database wordt leeggemaakt voor een schone import...")
    db.query(Municipality).delete()
    db.query(Vehicle).delete()
    db.query(SitVehicle).delete()
    db.query(SitLocation).delete()
    db.query(Cluster).delete()
    db.query(Region).delete()
    db.query(Department).delete()
    db.commit()

    departments_data = config.get("departments", {})
    
    # 1. Eerst Regio's verzamelen op basis van 'group' en 'province' in afdelingen
    print("Regio's analyseren en importeren...")
    regions_map = {} # Key: (province, region_name) -> Region object
    
    for dept_name, dept_info in departments_data.items():
        province = dept_info.get("province")
        group_name = dept_info.get("group")
        if province and group_name and group_name.strip():
            key = (province, group_name.strip())
            if key not in regions_map:
                reg = Region(name=group_name.strip(), province=province)
                db.add(reg)
                db.flush()
                regions_map[key] = reg

    # 2. Afdelingen importeren en koppelen aan regio's
    print("Afdelingen importeren...")
    dept_objects = {}
    for dept_name, dept_info in departments_data.items():
        province = dept_info.get("province", "Onbekend")
        group_name = dept_info.get("group")
        
        region_id = None
        if province and group_name:
            reg_obj = regions_map.get((province, group_name.strip()))
            if reg_obj:
                region_id = reg_obj.id

        dept = Department(
            name=dept_name,
            group=group_name,
            province=province,
            type=dept_info.get("type", "afdeling"),
            email=dept_info.get("email"),
            telephone=dept_info.get("telephone"),
            address=dept_info.get("address"),
            entiteitnummer=dept_info.get("entiteitnummer"),
            color=dept_info.get("color"),
            transparent=dept_info.get("transparent", False),
            lat=dept_info.get("lat"),
            lon=dept_info.get("lon"),
            region_id=region_id
        )
        
        # Services
        for srv_name in dept_info.get("services", []):
            srv_name = srv_name.lower().strip()
            service = db.query(Service).filter(Service.name == srv_name).first()
            if not service:
                service = Service(name=srv_name)
                db.add(service)
                db.flush()
            dept.services.append(service)

        # Members
        for member_name in dept_info.get("members", []):
            dept.members.append(Municipality(name=member_name))

        # Ziekenwagens
        for zw in dept_info.get("ziekenwagens", []):
            dept.vehicles.append(Vehicle(
                name=zw.get("name"),
                fleet_nr=zw.get("fleet_nr"),
                address=zw.get("address"),
                lat=zw.get("lat"),
                lon=zw.get("lon")
            ))
            
        db.add(dept)
        db.flush()
        dept_objects[dept_name.lower()] = dept

    # 3. Clusters importeren uit de top-level 'clusters' sectie[cite: 1]
    print("Clusters importeren...")
    clusters_data = config.get("clusters", {})
    for cluster_name, member_muns in clusters_data.items():
        # Bepaal de provincie op basis van de eerste afdeling die deze gemeentes bevat
        provincie = "Vlaams-Brabant" # Default fallback
        matched_region_id = None
        
        # Zoek welke provincie bij deze cluster hoort via de afdelingen die deze members bevatten
        for mun in member_muns:
            for d_name, d_info in departments_data.items():
                if any(m.lower() == mun.lower() for m in d_info.get("members", [])):
                    provincie = d_info.get("province", provincie)
                    if d_info.get("group"):
                        reg = regions_map.get((provincie, d_info.get("group").strip()))
                        if reg:
                            matched_region_id = reg.id
                    break
            if provincie:
                break

        cluster_obj = Cluster(
            name=cluster_name,
            province=provincie,
            region_id=matched_region_id
        )
        db.add(cluster_obj)
        db.flush()

        # Koppel eventueel afdelingen wiens naam overeenkomt met de clusterleden
        for mun in member_muns:
            mun_lower = mun.lower()
            if mun_lower in dept_objects:
                dept_objects[mun_lower].cluster_id = cluster_obj.id

    # 4. SIT-locaties importeren
    print("SIT-Locaties importeren...")
    sit_locations_data = config.get("sit_locations", [])
    for sit_data in sit_locations_data:
        sit = SitLocation(
            name=sit_data.get("name"),
            province=sit_data.get("province", "Vlaams-Brabant"), # Fallback indien niet gespecificeerd
            type=sit_data.get("type"),
            address=sit_data.get("address"),
            lat=sit_data.get("lat"),
            lon=sit_data.get("lon")
        )
        for v_data in sit_data.get("vehicles", []):
            sit.sit_vehicles.append(SitVehicle(
                name=v_data.get("name"),
                fleet_nr=v_data.get("fleet_nr")
            ))
        db.add(sit)

    db.commit()
    db.close()
    print("Import van afdelingen, regio's en clusters succesvol afgerond!")

if __name__ == "__main__":
    import_data()
