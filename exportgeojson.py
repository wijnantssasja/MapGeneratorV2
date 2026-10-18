import geopandas as gpd
from main import engine

EXPORT_PATH = "assets/exported_sectors.geojson"


def run_export():
    print("[INFO] Data ophalen uit de database...")

    # SQL query to select everything from your table
    sql = "SELECT * FROM department_shapes where hoofdgem like 'Westerlo'"

    # Load data directly from PostgreSQL into GeoPandas
    # Specify 'geom' as the geometry column based on your SQLAlchemy model
    gdf = gpd.read_postgis(sql, con=engine, geom_col='geom')

    if gdf.empty:
        print("[WAARSCHUWING] Geen data gevonden om te exporteren.")
        return

    print(f"[INFO] {len(gdf)} polygonen gevonden. Exporteren naar GeoJSON...")

    # Export the GeoDataFrame to a GeoJSON file
    gdf.to_file(EXPORT_PATH, driver="GeoJSON")

    print(f"[SUCCES] Data geëxporteerd naar: {EXPORT_PATH}")


if __name__ == "__main__":
    run_export()