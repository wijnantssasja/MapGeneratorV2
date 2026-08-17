import geopandas as gpd
from sqlalchemy.orm import Session
from shapely.ops import unary_union
from database import SessionLocal, engine, Department, DepartmentShape, MatchMethodEnum
import pandas as pd

# --- CONFIGURATIE ---
MANUAL_ASSIGNMENTS = {}
MANUAL_FUSIONS = {}


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

    gdf["name_lower"] = gdf["deelgemeente"].fillna("").astype(str).str.strip().str.lower()

    # Database mapping opbouwen uit municipalities
    departments = db.query(Department).all()
    dept_map = {d.name.strip().lower(): d.id for d in departments}
    dept_name_by_id = {d.id: d.name for d in departments}

    mun_to_dept = {}
    for dept in departments:
        for member in dept.members:
            m_lower = member.name.strip().lower()
            if m_lower not in mun_to_dept:
                mun_to_dept[m_lower] = []
            mun_to_dept[m_lower].append(dept.id)

    unassigned_indices = list(gdf.index)
    updates = []
    dept_combined_geom = {d.id: None for d in departments}
    consumed_claims = set()

    def get_candidates(n_lower):
        all_cands = mun_to_dept.get(n_lower, [])
        all_cands = list(set(all_cands))

        # SPECIAL GEACTIVEERDE DEBUGGER VOOR MOERZEKE
        if "moerzeke" in n_lower:
            cand_names = [dept_name_by_id.get(c) for c in all_cands]
            print(
                f"\n[MOERZEKE TRACE] Shape naam: '{n_lower}' | Gevonden afdelingen in DB (`mun_to_dept`): {cand_names}")

        if len(all_cands) <= 1:
            return all_cands

        valid_cands = []
        for d_id in all_cands:
            if (d_id, n_lower) not in consumed_claims:
                valid_cands.append(d_id)
        return valid_cands

    def assign_shape(idx, d_id, match_method):
        row = gdf.loc[idx]
        n_lower = row.get("name_lower", "")

        all_cands = mun_to_dept.get(n_lower, [])
        if len(set(all_cands)) > 1:
            if d_id in all_cands and (d_id, n_lower) not in consumed_claims:
                consumed_claims.add((d_id, n_lower))

        updates.append({"id": int(row['id']), "department_id": int(d_id), "match_method": match_method})

        geom = row['geom']
        if dept_combined_geom.get(d_id) is None:
            dept_combined_geom[d_id] = geom
        else:
            dept_combined_geom[d_id] = dept_combined_geom[d_id].union(geom)

        unassigned_indices.remove(idx)

        print(f"[DEBUG TOEGEWEZEN] '{n_lower}' (ID {row['id']}) -> {dept_name_by_id.get(d_id)} via {match_method.name}")

    print("\n--- STAP 1: MANUELE ASSIGNMENTS ---")
    for idx in unassigned_indices[:]:
        row = gdf.loc[idx]
        shape_id = str(row.get("shape_id", "")).replace(".0", "")
        n_lower = row.get("name_lower", "")

        target = MANUAL_ASSIGNMENTS.get(shape_id, MANUAL_ASSIGNMENTS.get(n_lower))
        if target and target.lower() in dept_map:
            assign_shape(idx, dept_map[target.lower()], MatchMethodEnum.MANUELE_OVERRIDE)

    print("\n--- STAP 2: PURE MATCHES (Unieke deelgemeente-namen) ---")
    name_counts = gdf.loc[unassigned_indices, "name_lower"].value_counts().to_dict()

    for idx in unassigned_indices[:]:
        row = gdf.loc[idx]
        n_lower = row.get("name_lower", "")

        cands = get_candidates(n_lower)
        is_unique_shape = (name_counts.get(n_lower, 0) == 1)

        if len(cands) == 1 and is_unique_shape:
            d_id = cands[0]
            assign_shape(idx, d_id, MatchMethodEnum.NAAM_MATCH)

    print("\n--- STAP 3: GLOBALE CONFLICT-RESOLUTIE ---")
    spatial_updates = 0

    while True:
        best_overall_dist = float('inf')
        best_match_info = None

        for idx in unassigned_indices:
            row = gdf.loc[idx]
            n_lower = row.get("name_lower", "")

            cands = get_candidates(n_lower)

            for d_id in cands:
                cand_geom = dept_combined_geom.get(d_id)
                if cand_geom is not None and not cand_geom.is_empty:
                    dist = row['geom'].distance(cand_geom)
                    if dist < best_overall_dist:
                        best_overall_dist = dist
                        best_match_info = (idx, d_id)

        if best_match_info:
            idx, d_id = best_match_info
            assign_shape(idx, d_id, MatchMethodEnum.RUIMTELIJKE_AFSTAND)
            spatial_updates += 1
        else:
            fallback_made = False
            for idx in unassigned_indices:
                row = gdf.loc[idx]
                n_lower = row.get("name_lower", "")
                cands = get_candidates(n_lower)

                if len(cands) == 1:
                    d_id = cands[0]
                    assign_shape(idx, d_id, MatchMethodEnum.NAAM_MATCH)
                    fallback_made = True
                    break

            if not fallback_made:
                break

    print("\n--- STAP 4: RESTANT (NULL) ---")
    for idx in unassigned_indices:
        row = gdf.loc[idx]
        updates.append({"id": int(row['id']), "department_id": None, "match_method": None})

    print("\nResultaten bulksgewijs wegschrijven naar de database...")
    if updates:
        db.bulk_update_mappings(DepartmentShape, updates)
        db.commit()

    db.close()
    print("Klaar!")


if __name__ == "__main__":
    map_shapes_in_db()