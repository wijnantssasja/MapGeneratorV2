import json
from shapely.geometry import shape, mapping, GeometryCollection, Polygon, MultiPolygon

# Laad je GeoJSON bestand
with open('output.geojson', 'r') as f:
    data = json.load(f)

new_features = []

for feature in data['features']:
    geom = feature.get('geometry')
    if not geom:
        continue

    # Als het een GeometryCollection is, splitsen we de polygonen/linestrings op of converteren we ze
    if geom['type'] == 'GeometryCollection':
        for sub_geom in geom['geometries']:
            # Maak een kopie van de properties voor elk sub-element
            new_feature = feature.copy()
            new_feature['geometry'] = sub_geom
            new_features.append(new_feature)
    else:
        new_features.append(feature)

data['features'] = new_features

# Sla de aangepaste GeoJSON op
with open('output_gekorrigeerd.geojson', 'w') as f:
    json.dump(data, f)

print("Klaar! Het bestand is opgeschoond en klaar voor import.")