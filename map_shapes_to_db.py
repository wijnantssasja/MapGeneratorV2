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

    # Haal afdelingen en leden op (Voor kandidaten-matching)
    departments = db.query(Department).all()
    dept_map = {d.name.strip().lower(): d.id for d in departments}

    mun_to_dept = {}
    for dept in departments:
        for member in dept.members:
            m_lower = member.name.strip().lower()
            if m_lower not in mun_to_dept:
                mun_to_dept[m_lower] = []
            mun_to_dept[m_lower].append(dept.id)

    def get_candidates(n_lower, p_lower):
        return list(set(mun_to_dept.get(n_lower, []) + mun_to_dept.get(p_lower, [])))

    unassigned_indices = list(gdf.index)
    updates = []
    dept_geometries = {d.id: [] for d in departments}

    print("Stap 1: Loop 0 - Manuele Assignments...")
    # ==========================================
    # LOOP 0: MANUELE ASSIGNMENTS
    # ==========================================
    for idx in unassigned_indices[:]:
        row = gdf.loc[idx]
        shape_id = str(row.get("shape_id", "")).replace(".0", "")
        n_lower = row.get("name_lower", "")

        target = MANUAL_ASSIGNMENTS.get(shape_id, MANUAL_ASSIGNMENTS.get(n_lower))
        if target and target.lower() in dept_map:
            d_id = dept_map[target.lower()]
            updates.append({"id": row['id'], "department_id": d_id, "match_method": MatchMethodEnum.MANUELE_OVERRIDE})
            dept_geometries[d_id].append(row['geom'])
            unassigned_indices.remove(idx)

    print("Stap 2: Loop 1 - Pure Matches (Unieke shapes zonder conflicten)...")
    # ==========================================
    # LOOP 1: PURE MATCHES
    # ==========================================
    # Tellen hoe vaak een deelgemeente voorkomt in de nog niet toegewezen dataset (om duplicaten zoals Hamme te spotten)
    name_counts = gdf.loc[unassigned_indices, "name_lower"].value_counts().to_dict()

    for idx in unassigned_indices[:]:
        row = gdf.loc[idx]
        n_lower = row.get("name_lower", "")
        p_lower = row.get("pname_lower", "")

        cands = get_candidates(n_lower, p_lower)

        # Een pure match is: exact 1 kandidaat afdeling, EN de naam van de shape is uniek in de resterende lijst.
        is_unique_shape = (name_counts.get(n_lower, 0) == 1)

        if len(cands) == 1 and is_unique_shape:
            d_id = cands[0]
            m_method = MatchMethodEnum.NAAM_MATCH if d_id in mun_to_dept.get(n_lower,
                                                                             []) else MatchMethodEnum.HOOFDGEMEENTE_MATCH
            updates.append({"id": row['id'], "department_id": d_id, "match_method": m_method})
            dept_geometries[d_id].append(row['geom'])
            unassigned_indices.remove(idx)

    # Voeg de verzamelde polygonen per afdeling samen voor snelle/zuivere afstandsmeting in Loop 2
    dept_combined_geom = {d_id: unary_union(geoms) if geoms else None for d_id, geoms in dept_geometries.items()}

    print(
        f" -> Loop 0 & 1 klaar. Nog {len(unassigned_indices)} onduidelijke/duplicaat polygonen te verwerken in Loop 2.")
    print("Stap 3: Loop 2 - Ruimtelijke analyse voor duplicaten...")

    # ==========================================
    # LOOP 2: DUPLICATEN (Ruimtelijke afstandsmeting)
    # ==========================================
    spatial_updates = 0

    # Groepeer de nog overgebleven shapes per naam
    unassigned_by_name = {}
    for idx in unassigned_indices:
        n = gdf.loc[idx, "name_lower"]
        if n not in unassigned_by_name:
            unassigned_by_name[n] = []
        unassigned_by_name[n].append(idx)

    for name, indices in unassigned_by_name.items():
        if not indices: continue

        # Bepaal alle afdelingen die één van de shapes in deze groep willen hebben
        all_wanting_depts = set()
        for idx in indices:
            row = gdf.loc[idx]
            all_wanting_depts.update(get_candidates(row.get("name_lower", ""), row.get("pname_lower", "")))

        # Zolang er shapes in deze groep over zijn EN afdelingen die ze willen en kunnen claimen
        while indices:
            # We kijken enkel naar afdelingen die effectief al polygonen (geometry) bezitten om van te meten
            active_depts = [d for d in all_wanting_depts if dept_combined_geom.get(d) is not None]
            if not active_depts:
                break  # Geen enkele eisende afdeling heeft geometrie. Berekenen is onmogelijk.

            # Bereken ALLE afstanden tussen de actieve afdelingen en de resterende shapes in deze naam-groep
            distances = []
            for d_id in active_depts:
                cand_geom = dept_combined_geom[d_id]
                for idx in indices:
                    dist = gdf.loc[idx, 'geom'].distance(cand_geom)
                    distances.append((dist, d_id, idx))

            if not distances:
                break

            # Sorteer en pak de absolute dichtstbijzijnde match (De afdeling claimt zijn specifieke stukje)
            distances.sort(key=lambda x: x[0])
            best_dist, best_d_id, best_idx = distances[0]

            # Toewijzen!
            row = gdf.loc[best_idx]
            updates.append(
                {"id": row['id'], "department_id": best_d_id, "match_method": MatchMethodEnum.RUIMTELIJKE_AFSTAND})
            spatial_updates += 1

            # Voeg direct toe aan de combined geometry van de winnende afdeling (voor evt. volgende berekeningen)
            dept_combined_geom[best_d_id] = dept_combined_geom[best_d_id].union(row['geom'])

            # Verwijder uit de werklijsten
            indices.remove(best_idx)
            unassigned_indices.remove(best_idx)

    # ==========================================
    # LOOP 3: RESTANT (Geen match = NULL)
    # ==========================================
    # Shapes die geen afdeling vonden (bijv. omdat de afdeling nog geen start-geometrie had) blijven leeg!
    for idx in unassigned_indices:
        updates.append({"id": gdf.loc[idx, 'id'], "department_id": None, "match_method": None})

    print("Resultaten bulksgewijs wegschrijven naar de database...")
    if updates:
        db.bulk_update_mappings(DepartmentShape, updates)
        db.commit()

    db.close()
    print(f"Succes! In totaal {len(updates)} polygonen behandeld.")
    print(f" -> {spatial_updates} duplicaten exact opgelost via minimale afstandsmeting.")
    print(f" -> {len(unassigned_indices)} polygonen blijven NULL (Geen match of referentie gevonden).")


if __name__ == "__main__":
    map_shapes_in_db()