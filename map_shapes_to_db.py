import geopandas as gpd
from sqlalchemy.orm import Session
from shapely.ops import unary_union
from database import SessionLocal, engine, Department, DepartmentShape, MatchMethodEnum
import pandas as pd

# --- CONFIGURATIE ---
MANUAL_ASSIGNMENTS = {
    # Voorbeeld: "shape_id_of_naam": "Naam van Afdeling"
}

MANUAL_FUSIONS = {
    # Voorbeeld: "Nieuwe Hoofdgemeente": ["Foute Deelgemeente", "12345"]
}


# --------------------

def map_shapes_in_db():
    db: Session = SessionLocal()

    print("Inladen van geometrieën direct vanuit PostgreSQL...")
    sql = "SELECT id, shape_id, name as deelgemeente, hoofdgem as hoofdgemeente, geom FROM department_shapes"

    try:
        with engine.connect() as conn:
            gdf = gpd.read_postgis(sql, con=conn, geom_col='geom')
    except Exception as e:
        print(f"Fout bij het ophalen van shapes: {e}")
        db.close()
        return

    # 0. Pas Manual Fusions toe VOORDAT we matchen
    if MANUAL_FUSIONS:
        updates_fusions = 0
        for new_parent_name, val_list in MANUAL_FUSIONS.items():
            for val in val_list:
                val_str = str(val).strip().lower()

                mask = pd.Series(False, index=gdf.index)
                if val_str.isdigit():
                    mask = mask | (gdf["id"].astype(str) == val_str)
                    mask = mask | (gdf["shape_id"].astype(str) == val_str)
                else:
                    mask = mask | (gdf["deelgemeente"].astype(str).str.lower() == val_str)

                if mask.sum() > 0:
                    gdf.loc[mask, "hoofdgemeente"] = str(new_parent_name)
                    updates_fusions += mask.sum()
        print(f"[INFO] Manual fusions toegepast: {updates_fusions} shapes kregen een nieuwe hoofdgemeente.")

    gdf["name_lower"] = gdf["deelgemeente"].fillna("").astype(str).str.strip().str.lower()
    gdf["pname_lower"] = gdf["hoofdgemeente"].fillna("").astype(str).str.strip().str.lower()

    # Haal afdelingen en mappings op
    departments = db.query(Department).all()
    dept_map = {d.name.strip().lower(): d.id for d in departments}

    mun_to_dept = {}
    dept_geometries = {d.id: [] for d in departments}

    for dept in departments:
        for member in dept.members:
            m_lower = member.name.strip().lower()
            if m_lower not in mun_to_dept:
                mun_to_dept[m_lower] = []
            mun_to_dept[m_lower].append(dept.id)

    updates = []
    shapes_met_duplicaten = []

    print("Stap 1: Loop 1 - Manuele assignments en Pure matches (Zekerheden)...")

    # ==========================================
    # LOOP 1: ZEKERHEDEN (Manueel + Unieke Match)
    # ==========================================
    for idx, row in gdf.iterrows():
        db_id = row['id']
        shape_id = str(row.get("shape_id", "")).replace(".0", "")
        n_lower = row.get("name_lower", "")
        p_lower = row.get("pname_lower", "")

        matched_dept_id = None
        match_method = None

        # A. Manuele toewijzingen primeren
        if shape_id in MANUAL_ASSIGNMENTS or n_lower in MANUAL_ASSIGNMENTS:
            manual_target = MANUAL_ASSIGNMENTS.get(shape_id, MANUAL_ASSIGNMENTS.get(n_lower))
            if manual_target and manual_target.lower() in dept_map:
                matched_dept_id = dept_map[manual_target.lower()]
                match_method = MatchMethodEnum.MANUELE_OVERRIDE

        # B. Pure matches zoeken (Geen duplicaten)
        if not matched_dept_id:
            candidates_deel = mun_to_dept.get(n_lower, [])
            candidates_hoofd = mun_to_dept.get(p_lower, [])
            all_candidates = list(set(candidates_deel + candidates_hoofd))

            if len(all_candidates) == 1:
                # Exact 1 kandidaat, dus 100% zekerheid
                matched_dept_id = all_candidates[0]
                match_method = MatchMethodEnum.NAAM_MATCH if matched_dept_id in candidates_deel else MatchMethodEnum.HOOFDGEMEENTE_MATCH
            elif len(all_candidates) > 1:
                # Duplicaat gedetecteerd! Toevoegen aan wachtlijst voor Loop 2.
                shapes_met_duplicaten.append((row, all_candidates, candidates_deel))
                continue
            else:
                # Helemaal geen kandidaat gevonden (blijft leeg)
                updates.append({"id": db_id, "department_id": None, "match_method": None})
                continue

        # Toewijzen en geometrie opslaan voor de afstandsmeting in Loop 2
        updates.append({
            "id": db_id,
            "department_id": matched_dept_id,
            "match_method": match_method
        })
        dept_geometries[matched_dept_id].append(row['geom'])

    print(f" -> {len(updates)} polygonen zonder conflict toegewezen.")

    # Bereid de geometrieën voor (samenvoegen per afdeling voor snellere/exactere afstandsberekening)
    dept_combined_geom = {}
    for d_id, geoms in dept_geometries.items():
        dept_combined_geom[d_id] = unary_union(geoms) if geoms else None

    print(f"Stap 2: Loop 2 - Ruimtelijke analyse voor {len(shapes_met_duplicaten)} duplicaten...")
    spatial_updates = 0

    # ==========================================
    # LOOP 2: DUPLICATEN (Ruimtelijke afstandsmeting)
    # ==========================================
    for row, all_candidates, candidates_deel in shapes_met_duplicaten:
        db_id = row['id']
        geom = row['geom']

        best_candidate = None
        min_dist = float('inf')

        # Meet afstand van dit conflictgebied tot de REEDS TOEGEWEZEN polygonen van elke kandidaat
        for cand_id in all_candidates:
            cand_geom = dept_combined_geom.get(cand_id)
            if cand_geom is not None and not cand_geom.is_empty:
                dist = geom.distance(cand_geom)
                if dist < min_dist:
                    min_dist = dist
                    best_candidate = cand_id

        if best_candidate is not None:
            # We hebben de dichtstbijzijnde afdeling gevonden
            matched_dept_id = best_candidate
            match_method = MatchMethodEnum.RUIMTELIJKE_AFSTAND
            spatial_updates += 1
        else:
            # Uitzonderlijke Fallback: Álle kandidaten hebben momenteel nog 0 toegewezen polygonen.
            # We wijzen hem toe aan de eerste de beste (prioriteit deelgemeente).
            matched_dept_id = all_candidates[0]
            match_method = MatchMethodEnum.NAAM_MATCH if matched_dept_id in candidates_deel else MatchMethodEnum.HOOFDGEMEENTE_MATCH

        updates.append({
            "id": db_id,
            "department_id": matched_dept_id,
            "match_method": match_method
        })

        # Zeer belangrijk: Voeg deze zojuist toegewezen shape onmiddellijk toe aan
        # dept_combined_geom, zodat volgende duplicaten hier óók hun afstand tegen kunnen meten.
        if dept_combined_geom.get(matched_dept_id) is None:
            dept_combined_geom[matched_dept_id] = geom
        else:
            dept_combined_geom[matched_dept_id] = dept_combined_geom[matched_dept_id].union(geom)

    print("Resultaten bulksgewijs wegschrijven naar de database...")
    if updates:
        db.bulk_update_mappings(DepartmentShape, updates)
        db.commit()

    db.close()
    print(f"Succes! In totaal {len(updates)} polygonen behandeld.")
    print(f" -> {spatial_updates} duplicaten/conflicten feilloos opgelost via ruimtelijke nabijheid.")


if __name__ == "__main__":
    map_shapes_in_db()