import geopandas as gpd
from sqlalchemy.orm import Session
from shapely.ops import unary_union
from database import SessionLocal, engine, Department, DepartmentShape, MatchMethodEnum

# --- CONFIGURATIE ---
MANUAL_ASSIGNMENTS = {}


# --------------------

def map_shapes_in_db():
    db: Session = SessionLocal()

    print("Inladen van geometrieën direct vanuit PostgreSQL...")
    sql = "SELECT id, shape_id, name, hoofdgem, geom FROM department_shapes"

    try:
        with engine.connect() as conn:
            gdf = gpd.read_postgis(sql, con=conn, geom_col='geom')
    except Exception as e:
        print(f"Fout bij het ophalen van shapes: {e}")
        db.close()
        return

    # Zorg dat alles lowercase is én dat spaties zijn weggeknipt
    gdf["name_lower"] = gdf["name"].str.strip().str.lower()
    gdf["pname_lower"] = gdf["hoofdgem"].str.strip().str.lower()

    # 1. Haal alle afdelingen en hun geregistreerde deelgemeenten op uit de DB
    departments = db.query(Department).all()
    dept_map = {}
    mun_to_dept = {}

    # Dictionary om per afdeling de toegewezen geometrieën (van Pass 1 & 2) op te slaan
    dept_geometries = {d.id: [] for d in departments}

    for dept in departments:
        d_name_lower = dept.name.strip().lower()
        dept_map[d_name_lower] = dept.id
        for member in dept.members:
            m_lower = member.name.strip().lower()
            if m_lower not in mun_to_dept:
                mun_to_dept[m_lower] = []
            mun_to_dept[m_lower].append(dept.id)

    print("Stap 1: Start Pass 1 & 2 (Manueel & Unieke Namen)...")
    updates = []
    unmatched_shapes = []

    # LOOP 1: PASS 1 & PASS 2
    for idx, row in gdf.iterrows():
        db_id = row['id']
        shape_id = str(row.get("shape_id", ""))
        n_lower = row.get("name_lower", "")
        p_lower = row.get("pname_lower", "")

        matched_dept_id = None
        match_method = None

        # PASS 1: Handmatige toewijzingen
        if shape_id in MANUAL_ASSIGNMENTS or n_lower in MANUAL_ASSIGNMENTS:
            manual_target = MANUAL_ASSIGNMENTS.get(shape_id, MANUAL_ASSIGNMENTS.get(n_lower))
            if manual_target.lower() in dept_map:
                matched_dept_id = dept_map[manual_target.lower()]
                match_method = MatchMethodEnum.MANUELE_OVERRIDE

        # PASS 2: Veilige Toewijzingen op basis van naam (geen conflicten)
        if not matched_dept_id:
            candidates_deel = mun_to_dept.get(n_lower, [])
            candidates_hoofd = mun_to_dept.get(p_lower, [])
            all_candidates = list(set(candidates_deel + candidates_hoofd))

            if len(all_candidates) == 1:
                matched_dept_id = all_candidates[0]
                if matched_dept_id in candidates_deel:
                    match_method = MatchMethodEnum.NAAM_MATCH
                else:
                    match_method = MatchMethodEnum.HOOFDGEMEENTE_MATCH

        # Resultaat van Loop 1 wegschrijven
        if matched_dept_id:
            updates.append({
                "id": db_id,
                "department_id": matched_dept_id,
                "match_method": match_method
            })
            # Sla de polygon op zodat we die in Pass 3 kunnen gebruiken voor afstandsberekening!
            dept_geometries[matched_dept_id].append(row['geom'])
        else:
            # Deze doen we pas in de volgende ronde
            unmatched_shapes.append(row)

    print(f" -> {len(updates)} polygonen direct gekoppeld.")
    print(f"Stap 2: Start Pass 3 (Ruimtelijke Analyse) voor de {len(unmatched_shapes)} overgebleven conflicten...")

    # Combineer de polygonen per afdeling tot één groot blok voor snelle ruimtelijke metingen
    dept_combined_geom = {}
    for d_id, geoms in dept_geometries.items():
        if geoms:
            dept_combined_geom[d_id] = unary_union(geoms)
        else:
            dept_combined_geom[d_id] = None

    spatial_updates = 0

    # LOOP 2: PASS 3 (Ruimtelijke Afstand)
    for row in unmatched_shapes:
        db_id = row['id']
        n_lower = row.get("name_lower", "")
        p_lower = row.get("pname_lower", "")

        candidates_deel = mun_to_dept.get(n_lower, [])
        candidates_hoofd = mun_to_dept.get(p_lower, [])
        all_candidates = list(set(candidates_deel + candidates_hoofd))

        matched_dept_id = None
        match_method = None

        if len(all_candidates) > 1:
            best_candidate = None
            min_dist = float('inf')

            for cand_id in all_candidates:
                cand_geom = dept_combined_geom.get(cand_id)
                if cand_geom is not None:
                    dist = row['geom'].distance(cand_geom)
                else:
                    dist = 999999

                if dist < min_dist:
                    min_dist = dist
                    best_candidate = cand_id

            if best_candidate is not None:
                matched_dept_id = best_candidate
                match_method = MatchMethodEnum.RUIMTELIJKE_AFSTAND
                spatial_updates += 1

        # Toevoegen aan de lijst met updates (zelfs als matched_dept_id None is gebleven, zodat foute oude data gewist wordt)
        updates.append({
            "id": db_id,
            "department_id": matched_dept_id,
            "match_method": match_method
        })

    print("Resultaten bulksgewijs wegschrijven naar de database...")
    if updates:
        # Dit voert alle updates uit in één grote, efficiënte query
        db.bulk_update_mappings(DepartmentShape, updates)
        db.commit()

    db.close()
    print(
        f"Succes! In totaal {len(updates)} polygonen behandeld, waarvan {spatial_updates} via ruimtelijke nabijheid opgelost.")


if __name__ == "__main__":
    map_shapes_in_db()