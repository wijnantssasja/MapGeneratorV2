import os
import geopandas as gpd
from shapely.geometry import MultiPolygon
from sqlalchemy.orm import sessionmaker
from main import DepartmentShape, engine  # Importeert je datamodel en database-connectie

SHAPEFILE_PATH = "assets/Basiskaart.shp"

def safe_get(row, col_name, default=""):
    """Haalt veilig een waarde uit de rij, zelfs als de kolom ontbreekt of leeg is."""
    if col_name in row.index:
        val = row[col_name]
        if val is not None and str(val).strip() != "nan":
            # Converteer floats (zoals '783503.0') naar schone strings ('783503')
            return str(val).replace('.0', '').strip()
    return default

def run_import():
    if not os.path.exists(SHAPEFILE_PATH):
        print(f"[FOUT] Kan shapefile niet vinden op: {SHAPEFILE_PATH}")
        return
        
    print("[INFO] Shapefile inlezen... (Dit kan even duren)")
    gdf = gpd.read_file(SHAPEFILE_PATH)
    
    # 1. Zorg ervoor dat we EPSG:4326 (Standaard WGS84 GPS coördinaten) gebruiken
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        print(f"[INFO] Projectie omzetten van {gdf.crs} naar EPSG:4326...")
        gdf = gdf.to_crs(epsg=4326)

    Session = sessionmaker(bind=engine)
    session = Session()

    # Optioneel: Voorkom dubbele imports
    if session.query(DepartmentShape).count() > 0:
        print("[WAARSCHUWING] Er zitten al shapes in de database. Wis deze eerst als je een verse import wilt doen.")
        session.close()
        return

    print("[INFO] Data wegschrijven naar de PostgreSQL database...")
    added_count = 0
    
    for idx, row in gdf.iterrows():
        geom = row['geometry']
        
        # Sla lege polygonen over
        if geom is None or geom.is_empty:
            continue
            
        # PostGIS kolom is MULTIPOLYGON. Als de shape een enkele Polygon is, converteer deze dan.
        if geom.geom_type == 'Polygon':
            geom = MultiPolygon([geom])
            
        # Zet om naar de string-indeling die GeoAlchemy2 (PostGIS) verwacht
        wkt_geom = f"SRID=4326;{geom.wkt}"
        
        # Maak het nieuwe database-record aan
        new_shape = DepartmentShape(
            shape_id=safe_get(row, 'id'),
            name=safe_get(row, 'name'),
            postcode=safe_get(row, 'postcode'),
            parent_id=safe_get(row, 'parent_id'),
            hoofdgem=safe_get(row, 'hoofdgem'),
            geom=wkt_geom
        )
        
        session.add(new_shape)
        added_count += 1
        
    # Sla alles in één keer op voor de snelheid
    session.commit()
    session.close()
    
    print(f"[SUCCES] Klaar! {added_count} polygonen zijn succesvol geïmporteerd.")

if __name__ == "__main__":
    run_import()
