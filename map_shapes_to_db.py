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

    # Pas Manual Fusions toe
    if MANUAL_FUSIONS:
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

    gdf["name_lower"] = gdf["deelgemeente"].fillna("").astype(str).str.strip().str.lower()
    gdf["pname_lower"] = gdf["hoofdgemeente"].fillna("").astype(str).str.strip().str.lower()

    # Database mapping opbouwen
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

    # HET TOKEN SYSTEEM: Houdt bij welke afdeling welke gemeentenaam al verbruikt heeft
    consumed_claims = set()

    def get_candidates(n_lower, p_lower):
        """Haalt enkel kandidaten op die hun recht op deze naam NOG NIET verbruikt hebben."""
        cands = []
        for d_id in mun_to_dept.get(n_lower, []):
            if (d_id, n_lower) not in consumed_claims:
                cands.append(d_id)
        for d_id in mun_to_dept.get(p_lower, []):
            if (d_id, p_lower) not in consumed_claims:
                cands.append(d_id)
        return list(set(cands))

    def assign_shape(idx, d_id, match_method):
        """Wijs toe, update geometrie én verbruik het ticket (token) voor die naam."""
        row = gdf.loc[idx]
        n_lower = row.get("name_lower", "")
        p_lower = row.get("pname_lower", "")

        # 1. Verbruik het token waardoor we matchten
        if d_id in mun_to_dept.get(n_lower, []) and (d_id, n_lower) not in consumed_claims:
            consumed_claims.add((d_id, n_lower))
        elif d_id in mun_to_dept.get(p_lower, []) and (d_id, p_lower) not in consumed_claims:
            consumed_claims.add((d_id, p_lower))

        # 2. Opslaan
        updates.append({"id": int(row['id']), "department_id": int(d_id), "match_method": match_method})

        # 3. Geometrie toevoegen
        geom = row['geom']
        if dept_combined_geom.get(d_id) is None:
            dept_combined_geom[d_id] = geom
        else:
            dept_combined_geom[d_id] = dept_combined_geom[d_id].union(geom)

        unassigned_indices.remove(idx)

        # Debug tracer voor "Hamme"
        if "landen" in n_lower or "landen" in p_lower:
            print(
                f"[DEBUG] '{n_lower}' (ID {row['id']}) toegewezen aan {dept_name_by_id.get(d_id)} via {match_method.name}")

    print("\n--- STAP 1: MANUELE ASSIGNMENTS ---")
    for idx in unassigned_indices[:]:
        row = gdf.loc[idx]
        shape_id = str(row.get("shape_id", "")).replace(".0", "")
        n_lower = row.get("name_lower", "")

        target = MANUAL_ASSIGNMENTS.get(shape_id, MANUAL_ASSIGNMENTS.get(n_lower))
        if target and target.lower() in dept_map:
            assign_shape(idx, dept_map[target.lower()], MatchMethodEnum.MANUELE_OVERRIDE)

    print("\n--- STAP 2: PURE MATCHES (Unieke shapes) ---")
    name_counts = gdf.loc[unassigned_indices, "name_lower"].value_counts().to_dict()

    for idx in unassigned_indices[:]:
        row = gdf.loc[idx]
        n_lower = row.get("name_lower", "")
        p_lower = row.get("pname_lower", "")

        cands = get_candidates(n_lower, p_lower)
        is_unique_shape = (name_counts.get(n_lower, 0) == 1)

        if len(cands) == 1 and is_unique_shape:
            d_id = cands[0]
            m_method = MatchMethodEnum.NAAM_MATCH if d_id in mun_to_dept.get(n_lower,
                                                                             []) else MatchMethodEnum.HOOFDGEMEENTE_MATCH
            assign_shape(idx, d_id, m_method)

    print("\n--- STAP 3: GLOBALE CONFLICT-RESOLUTIE (Afstand + Uitsluiting) ---")
    spatial_updates = 0

    while True:
        best_overall_dist = float('inf')
        best_match_info = None

        # 1. Zoek de absolute kortste afstand op de gehele kaart
        for idx in unassigned_indices:
            row = gdf.loc[idx]
            n_lower = row.get("name_lower", "")
            p_lower = row.get("pname_lower", "")

            cands = get_candidates(n_lower, p_lower)

            for d_id in cands:
                cand_geom = dept_combined_geom.get(d_id)
                if cand_geom is not None and not cand_geom.is_empty:
                    dist = row['geom'].distance(cand_geom)
                    if dist < best_overall_dist:
                        best_overall_dist = dist
                        best_match_info = (idx, d_id)

        # 2. Toewijzen
        if best_match_info:
            idx, d_id = best_match_info
            assign_shape(idx, d_id, MatchMethodEnum.RUIMTELIJKE_AFSTAND)
            spatial_updates += 1
        else:
            # 3. Fallback (Jouw regel): Als er niets gemeten kan worden, maar er is een kandidaat,
            # krijgt de enige overgebleven afdeling de polygoon zodat we kunnen starten met meten.
            fallback_made = False
            for idx in unassigned_indices:
                row = gdf.loc[idx]
                cands = get_candidates(row.get("name_lower", ""), row.get("pname_lower", ""))

                if len(cands) == 1:
                    d_id = cands[0]
                    m_method = MatchMethodEnum.NAAM_MATCH if d_id in mun_to_dept.get(row.get("name_lower", ""),
                                                                                     []) else MatchMethodEnum.HOOFDGEMEENTE_MATCH
                    assign_shape(idx, d_id, m_method)
                    fallback_made = True
                    break  # Breek uit de for-loop, zodat de while-loop opnieuw afstanden kan gaan meten!

            if not fallback_made:
                break  # Complete deadlock (Niemand wil de overgebleven shapes nog hebben)

    print("\n--- STAP 4: RESTANT (NULL) ---")
    for idx in unassigned_indices:
        row = gdf.loc[idx]
        updates.append({"id": int(row['id']), "department_id": None, "match_method": None})

    print("\nResultaten bulksgewijs wegschrijven naar de database...")
    if updates:
        db.bulk_update_mappings(DepartmentShape, updates)
        db.commit()

    db.close()
    print(f"Succes! {len(updates)} polygonen geëvalueerd.")
    print(f" -> {spatial_updates} dubbele polygonen organisch opgelost via competitie/afstand.")
    print(f" -> {len(unassigned_indices)} polygonen blijven NULL (Geen claimer, of claimrechten verbruikt).")


if __name__ == "__main__":
    map_shapes_in_db()