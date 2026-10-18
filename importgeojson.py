import os
import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon
from sqlalchemy.orm import sessionmaker
from main import DepartmentShape, engine

# Update this path to wherever you save the complete GeoJSON file
GEOJSON_PATH = "assets/sectors.geojson"


def safe_get(row, col_name, default=""):
    if col_name in row.index:
        val = row[col_name]
        if pd.notna(val) and str(val).strip() != "nan":
            return str(val).replace('.0', '').strip()
    return default


def run_import():
    if not os.path.exists(GEOJSON_PATH):
        print(f"[FOUT] Kan GeoJSON niet vinden op: {GEOJSON_PATH}")
        return

    print("[INFO] GeoJSON inlezen... (Dit kan even duren)")
    # GeoPandas reads GeoJSON using the exact same function as shapefiles
    gdf = gpd.read_file(GEOJSON_PATH)

    # Reproject from EPSG:3812 to EPSG:4326 to match your SQLAlchemy model
    if gdf.crs and gdf.crs.to_epsg() != 4326:
        print(f"[INFO] Projectie omzetten van {gdf.crs} naar EPSG:4326...")
        gdf = gdf.to_crs(epsg=4326)

    Session = sessionmaker(bind=engine)
    session = Session()

    print("[INFO] Data wegschrijven naar de PostgreSQL database...")
    added_count = 0

    for idx, row in gdf.iterrows():
        geom = row['geometry']

        if geom is None or geom.is_empty:
            continue

        if geom.geom_type == 'Polygon':
            geom = MultiPolygon([geom])

        wkt_geom = f"SRID=4326;{geom.wkt}"

        # Get the ID first to check for existing records
        # (Make sure 'cs012026' matches the actual ID key in your GeoJSON)
        current_shape_id = safe_get(row, 'shape_id', default="MANUAL_ID")

        # Query the database for an existing shape with this shape_id
        existing_shape = session.query(DepartmentShape).filter_by(shape_id=current_shape_id).first()

        if existing_shape:
            # UPDATE: The record exists, so we update its properties
            existing_shape.name = safe_get(row, '"name"', default="MANUAL_NAME")
            existing_shape.postcode = safe_get(row, 'postcode', default="0000")
            existing_shape.parent_id = safe_get(row, 'parent_id', default="")
            existing_shape.hoofdgem = safe_get(row, 'hoofdgem', default="Westerlo")
            existing_shape.geom = wkt_geom
            # We don't increment added_count here, but you could create an updated_count variable if you want
        else:
            # INSERT: The record does not exist, create a new one
            new_shape = DepartmentShape(
                shape_id=current_shape_id,
                name=safe_get(row, '"name"', default="MANUAL_NAME"),
                postcode=safe_get(row, 'postcode', default="0000"),
                parent_id=safe_get(row, 'parent_id', default=""),
                hoofdgem=safe_get(row, 'hoofdgem', default="Westerlo"),
                geom=wkt_geom
            )
            session.add(new_shape)
            added_count += 1

    session.commit()
    session.close()

    print(f"[SUCCES] Klaar! {added_count} polygonen zijn succesvol geïmporteerd.")


if __name__ == "__main__":
    run_import()