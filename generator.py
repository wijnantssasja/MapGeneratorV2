import os
import glob
import time
import json
import base64
import re
import warnings
from datetime import datetime
import itertools
import numpy as np
import pandas as pd
import geopandas as gpd
import topojson as tp
from shapely.wkt import loads, dumps
from shapely.geometry import Point

import folium
from folium.plugins import StripePattern, GroupedLayerControl, Search
from branca.element import Element, MacroElement
from jinja2 import Template

# Database imports
from database import SessionLocal, engine, Department, Vehicle, SitLocation, Service

# Onderdruk storende CRS waarschuwingen
warnings.filterwarnings("ignore", message=".*Geometry is in a geographic CRS.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)

OUTPUT_DIR = "/opt/MapGenerator/static"
MAX_STORAGE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB


# =========================================================
# HELPER CLASSES UIT DE ORIGINELE GENERATOR
# =========================================================
class EasyPrint(MacroElement):
    def __init__(self, position='topleft', title='Exporteer Map', exportOnly=True, filename='rodekruis_map', **kwargs):
        super().__init__()
        self._name = 'EasyPrint'
        self.options = {'position': position, 'title': title, 'exportOnly': exportOnly, 'filename': filename,
                        'hideControlContainer': True, 'sizeModes': ['Current', 'A4Landscape'], 'tileWait': 1500,
                        **kwargs}

    def render(self, **kwargs):
        super().render(**kwargs)
        figure = self.get_root()
        figure.header.add_child(folium.Element(
            '<script src="https://cdn.jsdelivr.net/npm/leaflet-easyprint@2.1.9/dist/bundle.js"></script>'))

    _template = Template(
        "{% macro script(this, kwargs) %}var easyPrint = L.easyPrint({{ this.options_json }}).addTo({{ this._parent.get_name() }});{% endmacro %}")

    @property
    def options_json(self):
        return json.dumps(self.options)


class MapEnhancer(MacroElement):
    def __init__(self):
        super().__init__()
        self._name = 'MapEnhancer'

    _template = Template("""
        {% macro script(this, kwargs) %}
        function enhanceMap(layer) {
            if (layer.setStyle && layer.options) {
                if (layer.options.className && layer.options.className.includes('kleurloos-shape')) {
                    if (!layer._clickTogglable) {
                        layer._clickTogglable = true;
                        layer.on('click', function(e) {
                            var currentOpacity = this.options.fillOpacity;
                            if (currentOpacity < 0.1) { this.setStyle({fillColor: '#d32f2f', fillOpacity: 0.6}); } 
                            else { this.setStyle({fillColor: '#ffffff', fillOpacity: 0.01}); }
                            L.DomEvent.stopPropagation(e);
                        });
                    }
                }
            }
            if (layer.eachLayer) { layer.eachLayer(enhanceMap); }
        }

        function enforceZOrder(map) {
            var inwonLayers = []; var afdLayers = []; var clusterLayers = []; var regioLayers = []; var provLayers = [];
            function checkAndSort(l) {
                if (l.options && l.options.className) {
                    if (l.options.className.includes('layer-inwoners')) inwonLayers.push(l);
                    if (l.options.className.includes('layer-afdelingen')) afdLayers.push(l);
                    if (l.options.className.includes('layer-clusters')) clusterLayers.push(l);
                    if (l.options.className.includes('layer-regio')) regioLayers.push(l);
                    if (l.options.className.includes('layer-province')) provLayers.push(l);
                }
            }
            map.eachLayer(function(layer) { if (layer.eachLayer) { layer.eachLayer(checkAndSort); } else { checkAndSort(layer); } });
            inwonLayers.forEach(l => { if (l.bringToBack) l.bringToBack(); });
            afdLayers.forEach(l => { if (l.bringToFront) l.bringToFront(); });
            clusterLayers.forEach(l => { if (l.bringToFront) l.bringToFront(); });
            regioLayers.forEach(l => { if (l.bringToFront) l.bringToFront(); });
            provLayers.forEach(l => { if (l.bringToFront) l.bringToFront(); });
        }

        function enforceCheckboxesAndRadios() {
            var groups = document.querySelectorAll('.leaflet-control-layers-group');
            groups.forEach(function(g) {
                var labelEl = g.querySelector('.leaflet-control-layers-group-name');
                if (!labelEl) return;
                var groupName = labelEl.innerText.trim();
                var inputs = g.querySelectorAll('input');
                if (groupName.includes('Vrijwilligers') || groupName.includes('Disciplines') || groupName.includes('Overlay')) {
                    inputs.forEach(function(i) { i.type = 'checkbox'; i.removeAttribute('name'); });
                }
                if (groupName.includes('Basiskaart') || groupName.includes('Afdelingen') || groupName.includes('Tekst Labels')) {
                    var safeName = groupName.replace(/\\s+/g, '');
                    inputs.forEach(function(i) { i.type = 'radio'; i.name = 'radioGroup_' + safeName; });
                }
            });
        }

        setTimeout(function() {
            var mapObjects = Object.values(window).filter(obj => obj instanceof L.Map);
            if (mapObjects.length > 0) {
                var map = mapObjects[0];
                map.eachLayer(enhanceMap);
                enforceZOrder(map);
                map.on('layeradd', function(e) { enhanceMap(e.layer); enforceZOrder(map); });
            }
            enforceCheckboxesAndRadios();
        }, 500);
        setTimeout(enforceCheckboxesAndRadios, 1500);
        {% endmacro %}
    """)


def deduplicate_geojson_in_html(html_path):
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
        pattern = re.compile(r'^(\s*)(geo_json_[a-f0-9]+)_add\((.+)\);$', re.MULTILINE)
        seen_geojsons = {}
        shared_var_counter = 0

        def replacer(match):
            nonlocal shared_var_counter
            indent, var_name, json_data = match.groups()
            if json_data in seen_geojsons:
                shared_var = seen_geojsons[json_data]
                return f"{indent}{var_name}_add({shared_var}); /* Geoptimaliseerd */"
            else:
                shared_var_counter += 1
                shared_var = f"shared_geojson_data_{shared_var_counter}"
                seen_geojsons[json_data] = shared_var
                return f"{indent}var {shared_var} = {json_data};\n{indent}{var_name}_add({shared_var});"

        optimized_content = pattern.sub(replacer, content)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(optimized_content)
    except Exception as e:
        print(f"[WARN] HTML Optimalisatie mislukt: {e}")


def enforce_fifo_storage(directory=OUTPUT_DIR, max_bytes=MAX_STORAGE_BYTES):
    os.makedirs(directory, exist_ok=True)
    files = glob.glob(os.path.join(directory, "*.html"))
    files.sort(key=os.path.getctime)
    while sum(os.path.getsize(f) for f in files) > max_bytes and len(files) > 0:
        os.remove(files.pop(0))


def get_base64_image(icon_name):
    path = os.path.join(OUTPUT_DIR, "assets", f"icon_{icon_name}.png")
    if os.path.exists(path):
        with open(path, "rb") as img_file:
            return f"data:image/png;base64,{base64.b64encode(img_file.read()).decode('utf-8')}"
    return None


# =========================================================
# DE HOOFD GENERATOR FUNCTIE
# =========================================================
def background_generate_map(province_filter: str, username: str):
    db = SessionLocal()
    enforce_fifo_storage()

    prov_name = "Vlaanderen" if province_filter.lower() == "vlaanderen" else province_filter
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"Kaart_{prov_name}_{timestamp}.html"
    output_path = os.path.join(OUTPUT_DIR, filename)

    print(f"[GENERATOR] Start generatie voor {prov_name} -> {filename}")

    try:
        # 1. Haal data op uit Database
        if prov_name == "Vlaanderen":
            depts = db.query(Department).all()
            sits = db.query(SitLocation).all()
        else:
            depts = db.query(Department).filter(Department.province == prov_name).all()
            sits = db.query(SitLocation).filter(SitLocation.province == prov_name).all()

        if not depts:
            print("[WARN] Geen afdelingen gevonden voor deze provincie.")
            return

        dept_ids = [str(d.id) for d in depts]

        # 2. Haal GeoJSON shapes op (Aangepast: 'name as hoofdgemeente' i.p.v. 'parent_name')
        sql = f"""
            SELECT id, shape_id, name as deelgemeente, name as hoofdgemeente, department_id, geom 
            FROM department_shapes 
            WHERE department_id IN ({','.join(dept_ids)})
        """
        gdf_shapes = gpd.read_postgis(sql, engine.connect(), geom_col='geom')
        gdf_shapes = gdf_shapes.rename(columns={'geom': 'geometry'}).set_geometry('geometry')
        gdf_shapes.crs = "EPSG:4326"

        # 3. Koppel data
        dept_data = []
        all_services = set()
        for d in depts:
            srvs = [s.name.lower() for s in d.services]
            all_services.update(srvs)
            dept_data.append({
                "department_id": d.id,
                "cluster_name": d.name,
                "group_name": d.group or "Geen Regio",
                "color": d.color or "#d32f2f",
                "type": d.type,
                "address": d.address or "Geen adres",
                "email": d.email or "",
                "lat": d.lat,
                "lon": d.lon,
                "is_transparent": d.transparent,
                "services": srvs,
                "website_url": f"https://www.rodekruis.be/afdeling/{d.name.lower().replace(' ', '-')}"
            })

        df_depts = pd.DataFrame(dept_data)

        if not gdf_shapes.empty:
            gdf_selected = gdf_shapes.merge(df_depts, on="department_id", how="inner")

            # Topologische Simplificatie
            print("[GENERATOR] Topologie vereenvoudigen...")
            gdf_selected = gdf_selected.to_crs(epsg=31370)
            try:
                topo = tp.Topology(gdf_selected, prequantize=False)
                gdf_selected = topo.toposimplify(5).to_gdf()
            except Exception:
                gdf_selected['geometry'] = gdf_selected.geometry.simplify(5)

            gdf_selected = gdf_selected.set_geometry('geometry')
            gdf_selected.crs = "EPSG:31370"
            gdf_selected = gdf_selected.to_crs(epsg=4326)
            gdf_selected['geometry'] = gdf_selected.geometry.apply(
                lambda geom: loads(dumps(geom, rounding_precision=5)) if geom else None)
            gdf_selected['geometry'] = gdf_selected.geometry.buffer(0).make_valid()

            default_lat = gdf_selected.geometry.centroid.y.mean()
            default_lon = gdf_selected.geometry.centroid.x.mean()
        else:
            gdf_selected = gpd.GeoDataFrame()
            default_lat, default_lon = 51.0, 4.5

        # 4. Folium Map Opbouwen
        m = folium.Map(location=[default_lat, default_lon], zoom_start=9, tiles=None)

        # 4A. Iconen inladen & CSS Genereren
        loaded_icons = set()
        icon_css_rules = ""
        for service in all_services:
            safe_name = service.replace(" ", "_").replace("-", "_")
            b64 = get_base64_image(safe_name)
            if b64:
                icon_css_rules += f".rk-icon-{safe_name} {{ background-image: url('{b64}'); }}\n"
                loaded_icons.add(service)

        icon_css_rules += """
        .rk-popup-container { font-family: sans-serif; min-width: 320px; padding: 5px; }
        .rk-popup-title { margin: 0 0 5px 0; color: #d32f2f; border-bottom: 2px solid #d32f2f; padding-bottom: 5px; }
        .rk-popup-body { font-size: 13px; line-height: 1.5; margin-bottom: 5px; }
        .rk-popup-link { color: #1976d2; }
        .rk-popup-btn { background-color: #d32f2f; color: white !important; padding: 10px 15px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 14px; display: inline-block; box-shadow: 2px 2px 5px rgba(0,0,0,0.2); }
        .rk-popup-btn-container { text-align: center; margin-top: 10px; margin-bottom: 10px; }
        .rk-popup-debug { margin-top: 8px; font-size: 11px; color: #888; }
        """
        custom_css = Element(f"""
        <style>
            .leaflet-container {{ background: #fff !important; }}
            .leaflet-control-layers-expanded {{ max-height: 80vh !important; max-width: 65vw !important; overflow-y: auto !important; overflow-x: hidden !important; -webkit-overflow-scrolling: touch !important; touch-action: pan-y !important; }}
            .leaflet-control-layers-list {{ overflow-y: auto !important; max-height: 75vh !important; -webkit-overflow-scrolling: touch !important; touch-action: pan-y !important; }}
            .rk-icon {{ display: inline-block; width: 24px; height: 24px; margin-right: 8px; vertical-align: middle; background-size: contain; background-repeat: no-repeat; background-position: center; cursor: help; }}
        </style>
        <style>{icon_css_rules}</style>
        """)
        m.get_root().header.add_child(custom_css)

        # Base Layers
        tl_licht = folium.TileLayer('cartodbpositron', name='Lichte kaart', control=False, show=True).add_to(m)
        tl_osm = folium.TileLayer(tiles='https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
                                  attr='&copy; OpenStreetMap contributors &copy; CARTO', name='Standaard kaart',
                                  control=False, show=False).add_to(m)
        tl_geen = folium.TileLayer(
            tiles="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
            attr='Geen Achtergrond', name='Geen kaart', control=False, show=False).add_to(m)

        # Feature Groups
        fg_afdelingen = folium.FeatureGroup(name="Afdelingen kleur", overlay=True, control=True)
        fg_basis = folium.FeatureGroup(name="Afdelingen kleurloos", overlay=True, control=True, show=False)
        fg_regio = folium.FeatureGroup(name="Regio", overlay=True, control=True, show=False)
        fg_locaties = folium.FeatureGroup(name="Afdelingslocaties", overlay=True, control=True, show=True)
        fg_vrijwilligerskorps = folium.FeatureGroup(name="Vrijwilligerskorpsen", overlay=True, control=True, show=False)
        fg_ziekenwagens = folium.FeatureGroup(name="Ziekenwagen", overlay=True, control=True, show=False)
        fg_sit = folium.FeatureGroup(name="SIT", overlay=True, control=True, show=False)
        fg_geen_labels = folium.FeatureGroup(name="Geen labels", overlay=True, control=True, show=True)
        fg_label_gem = folium.FeatureGroup(name="Gemeente Labels", overlay=True, control=True, show=False)
        fg_label_afd = folium.FeatureGroup(name="Afdeling Labels", overlay=True, control=True, show=False)
        fg_label_sam = folium.FeatureGroup(name="Cluster Labels", overlay=True, control=True, show=False)

        # Patterns (Disciplines)
        pat_jeugd = StripePattern(angle=45, color='#FFA500', weight=4, opacity=0.8, space_color='white',
                                  space_opacity=0).add_to(m)
        pat_zorgbib = StripePattern(angle=-45, color='#800080', weight=4, opacity=0.8, space_color='white',
                                    space_opacity=0).add_to(m)
        pat_brugfiguren = StripePattern(angle=90, color='#008080', weight=4, opacity=0.8, space_color='white',
                                        space_opacity=0).add_to(m)
        pat_internationaal = StripePattern(angle=0, color='#0000FF', weight=4, opacity=0.8, space_color='white',
                                           space_opacity=0).add_to(m)
        pat_uitleen = StripePattern(angle=135, color='#008000', weight=4, opacity=0.8, space_color='white',
                                    space_opacity=0).add_to(m)

        fg_jeugd = folium.FeatureGroup(name="Jeugd", overlay=True, control=True, show=False)
        fg_zorgbib = folium.FeatureGroup(name="Zorgbib", overlay=True, control=True, show=False)
        fg_brugfiguren = folium.FeatureGroup(name="Brugfiguren", overlay=True, control=True, show=False)
        fg_internationaal = folium.FeatureGroup(name="Internationale Samenwerking", overlay=True, control=True,
                                                show=False)
        fg_uitleen = folium.FeatureGroup(name="Uitleendienst", overlay=True, control=True, show=False)

        # 5. Voeg de Polygonen (Afdelingen) Toe
        if not gdf_selected.empty:
            for idx, row in gdf_selected.iterrows():
                is_zetel = (row["type"] == "provinciale_zetel")
                title_text = f"Provinciale Zetel {row['cluster_name']}" if is_zetel else f"Rode Kruis-{row['cluster_name']}"

                icons_html = ""
                if row['services']:
                    icons_html = "<div style='margin-top: 10px; margin-bottom: 10px;'>"
                    for service in row['services']:
                        safe_name = service.replace(" ", "_").replace("-", "_")
                        if service in loaded_icons:
                            icons_html += f"<div class='rk-icon rk-icon-{safe_name}' title='{service.capitalize()}'></div>"
                        else:
                            icons_html += f"<span title='{service.capitalize()}' style='background:#eee; padding:2px 5px; border-radius:3px; margin-right:5px; font-size:11px; cursor: help;'>{service.capitalize()}</span>"
                    icons_html += "</div>"

                volunteer_url = row['website_url'] + "/wat-kan-jij-doen/word-vrijwilliger/"
                website_line = "" if is_zetel else f"<b>Website:</b> <a href='{row['website_url']}' target='_blank' class='rk-popup-link'>{row['website_url']}</a><br>"
                volunteer_section = "" if is_zetel else f'<div class="rk-popup-btn-container"><a href="{volunteer_url}" target="_blank" class="rk-popup-btn">Word vrijwilliger</a></div>'

                html_content = f"""
                <div class="rk-popup-container">
                    <h4 class="rk-popup-title">{title_text}</h4>
                    {icons_html}
                    <div class="rk-popup-body">
                        <b>Gemeente:</b> {row['hoofdgemeente']}<br><b>Deelgemeente:</b> {row['deelgemeente']}
                    </div>
                    <div class="rk-popup-body">
                        <b>Adres:</b> {row['address']}<br><b>Email:</b> <a href="mailto:{row['email']}" class="rk-popup-link">{row['email']}</a><br>
                        {website_line}
                    </div>
                    {volunteer_section}
                </div>
                """

                folium.GeoJson(
                    row.geometry,
                    style_function=lambda x, trans=row['is_transparent'], col=row['color']: {
                        'fillColor': 'white' if trans else col,
                        'color': '#444444',
                        'weight': 1.2,
                        'dashArray': '5, 5',
                        'fillOpacity': 0.01 if trans else 0.7,
                        'className': 'layer-afdelingen'
                    },
                    highlight_function=lambda x: {'weight': 3, 'color': '#666', 'dashArray': ''},
                    tooltip=row['deelgemeente'],
                    popup=folium.Popup(html_content, max_width=350)
                ).add_to(fg_afdelingen)

            # Kleurloos
            cluster_dissolved = gdf_selected.dissolve(by='cluster_name')
            folium.GeoJson(cluster_dissolved,
                           style_function=lambda x: {'fillColor': 'none', 'color': 'black', 'weight': 2.5,
                                                     'fillOpacity': 0, 'className': 'layer-afdelingen'},
                           interactive=False).add_to(fg_basis)
            folium.GeoJson(cluster_dissolved,
                           style_function=lambda x: {'fillColor': '#ffffff', 'color': 'none', 'weight': 0,
                                                     'fillOpacity': 0.01, 'interactive': True,
                                                     'className': 'kleurloos-shape layer-afdelingen'}).add_to(fg_basis)

            # Regio (Gedeelde Bounding Box)
            regio_proj = gdf_selected.to_crs(epsg=31370).dissolve(by='group_name')
            solid_total = regio_proj.geometry.union_all()
            if not solid_total.is_empty:
                folium.GeoJson(
                    gpd.GeoDataFrame({'geometry': [solid_total.boundary]}, crs=31370).to_crs(epsg=4326),
                    style_function=lambda x: {'color': '#d32f2f', 'weight': 4.5, 'opacity': 0.8,
                                              'className': 'layer-regio'}, interactive=False
                ).add_to(fg_regio)

            for geom1, geom2 in itertools.combinations(regio_proj.geometry, 2):
                shared = geom1.intersection(geom2)
                if not shared.is_empty:
                    folium.GeoJson(
                        gpd.GeoDataFrame({'geometry': [shared]}, crs=31370).to_crs(epsg=4326),
                        style_function=lambda x: {'color': '#d32f2f', 'weight': 4.5, 'opacity': 0.8,
                                                  'className': 'layer-regio'}, interactive=False
                    ).add_to(fg_regio)

            # Regio Text Labels
            base_style = 'position: absolute; left: 0px; top: 0px; transform: translate(-50%, -50%); font-family: DejaVu Sans, sans-serif; white-space: nowrap; text-align: center; pointer-events: none;'
            for gname, row in regio_proj.to_crs(epsg=4326).iterrows():
                if pd.isna(gname) or str(gname).strip() == "Geen Regio": continue
                geom = row.geometry

                if prov_name == 'Vlaanderen':
                    pt = geom.representative_point()
                    label_lat, label_lon = pt.y, pt.x
                else:
                    bounds = geom.bounds
                    cent = geom.centroid
                    candidates = [
                        ("boven", bounds[3] + 0.015, cent.x),
                        ("links", cent.y, bounds[0] - 0.025),
                        ("rechts", cent.y, bounds[2] + 0.025),
                        ("onder", bounds[1] - 0.015, cent.x)
                    ]
                    other_regions = regio_proj[regio_proj.index != gname].to_crs(epsg=4326).geometry.union_all()
                    best_lat, best_lon = cent.y, cent.x
                    for _, cand_lat, cand_lon in candidates:
                        cand_pt = Point(cand_lon, cand_lat)
                        if other_regions.is_empty or not other_regions.contains(cand_pt):
                            best_lat, best_lon = cand_lat, cand_lon
                            break
                    label_lat, label_lon = best_lat, best_lon

                folium.Marker(
                    [label_lat, label_lon],
                    icon=folium.DivIcon(
                        html=f'<div style="{base_style} font-size: 22px; font-weight: bold; color: #333; text-shadow: 2px 2px 4px #fff, -1px -1px 0 #fff, 1px -1px 0 #fff, -1px 1px 0 #fff, 1px 1px 0 #fff;">{str(gname).upper()}</div>')
                ).add_to(fg_regio)

            # Text Labels Gemeente & Afdeling
            for name, row in gdf_selected.to_crs(epsg=31370).dissolve(by='hoofdgemeente').to_crs(epsg=4326).iterrows():
                folium.Marker([row.geometry.centroid.y, row.geometry.centroid.x], icon=folium.DivIcon(
                    html=f'<div style="{base_style} font-size: 11px; font-weight: bold; color: #333; text-shadow: 2px 2px 3px #fff;">{name}</div>')).add_to(
                    fg_label_gem)

            for name, row in cluster_dissolved.iterrows():
                folium.Marker([row.geometry.centroid.y, row.geometry.centroid.x], icon=folium.DivIcon(
                    html=f'<div style="{base_style} font-size: 12px; font-weight: bold; color: #d32f2f; text-shadow: 2px 2px 3px #fff;">{name}</div>')).add_to(
                    fg_label_afd)

        # 6. Locaties, Voertuigen & Patronen (Markers)
        for dept in depts:
            is_zetel = (dept.type == "provinciale_zetel")
            title_text = f"Provinciale Zetel {dept.name}" if is_zetel else f"Rode Kruis-{dept.name}"

            final_lat, final_lon = dept.lat, dept.lon
            if not final_lat and not gdf_selected.empty:
                mask = gdf_selected['cluster_name'] == dept.name
                if mask.any():
                    centroid = gdf_selected[mask].geometry.union_all().centroid
                    final_lat, final_lon = centroid.y, centroid.x

            if final_lat and final_lon:
                loc_html = f"<div style='font-family: sans-serif; min-width: 200px;'><h4 style='color: #d32f2f; border-bottom: 2px solid #d32f2f;'>{title_text}</h4><b>Adres:</b> {dept.address or 'Onbekend'}</div>"
                folium.Marker(
                    location=[final_lat, final_lon],
                    icon=folium.Icon(icon='star' if is_zetel else 'plus', prefix='fa',
                                     color='blue' if is_zetel else 'red'),
                    tooltip=title_text,
                    popup=folium.Popup(loc_html, max_width=300)
                ).add_to(fg_locaties)

            # Ziekenwagens
            for v in dept.vehicles:
                v_lat, v_lon = v.lat, v.lon
                if not v_lat: v_lat, v_lon = final_lat, final_lon
                if v_lat and v_lon:
                    v_html = f"<div style='position: relative; width: 30px; height: 42px; text-align: center; margin-left: -15px; margin-top: -42px;'><i class='fa fa-map-marker' style='font-size: 42px; color: #8B0000; text-shadow: 2px 2px 4px rgba(0,0,0,0.4);'></i><i class='fa fa-ambulance' style='font-size: 16px; color: white; position: absolute; top: 10px; left: 50%; transform: translateX(-50%);'></i></div>"
                    folium.Marker(
                        location=[v_lat, v_lon],
                        icon=folium.DivIcon(html=v_html, class_name="empty"),
                        tooltip=f"Voertuig: {v.name} ({dept.name})",
                        popup=f"<b>{title_text}</b><br>Voertuig: {v.name}<br>Vlootnr: {v.fleet_nr or 'Onbekend'}<br>Adres: {v.address or dept.address}"
                    ).add_to(fg_ziekenwagens)

            # Patronen (Jeugd / Zorgbib / etc)
            if not gdf_selected.empty:
                mask = gdf_selected['cluster_name'] == dept.name
                if mask.any():
                    c_gdf = gpd.GeoDataFrame({'geometry': [gdf_selected[mask].geometry.union_all()]}, crs=4326)
                    services = [s.name.lower() for s in dept.services]

                    if 'jeugd' in services:
                        folium.GeoJson(c_gdf,
                                       style_function=lambda x, p=pat_jeugd: {'fillPattern': p, 'fillOpacity': 1.0,
                                                                              'color': 'none', 'weight': 0},
                                       interactive=False).add_to(fg_jeugd)
                    if 'zorgbib' in services:
                        folium.GeoJson(c_gdf,
                                       style_function=lambda x, p=pat_zorgbib: {'fillPattern': p, 'fillOpacity': 1.0,
                                                                                'color': 'none', 'weight': 0},
                                       interactive=False).add_to(fg_zorgbib)
                    if 'brugfiguren' in services:
                        folium.GeoJson(c_gdf, style_function=lambda x, p=pat_brugfiguren: {'fillPattern': p,
                                                                                           'fillOpacity': 1.0,
                                                                                           'color': 'none',
                                                                                           'weight': 0},
                                       interactive=False).add_to(fg_brugfiguren)
                    if 'internationaal' in services or 'internationale samenwerking' in services:
                        folium.GeoJson(c_gdf, style_function=lambda x, p=pat_internationaal: {'fillPattern': p,
                                                                                              'fillOpacity': 1.0,
                                                                                              'color': 'none',
                                                                                              'weight': 0},
                                       interactive=False).add_to(fg_internationaal)
                    if 'uitleendienst' in services:
                        folium.GeoJson(c_gdf,
                                       style_function=lambda x, p=pat_uitleen: {'fillPattern': p, 'fillOpacity': 1.0,
                                                                                'color': 'none', 'weight': 0},
                                       interactive=False).add_to(fg_uitleen)
                    if 'vrijwilligerskorps' in services or 'vrijwilligerskorpsen' in services:
                        folium.GeoJson(c_gdf, style_function=lambda x: {'fillColor': '#4CAF50', 'fillOpacity': 0.4,
                                                                        'color': 'none', 'weight': 0},
                                       interactive=False, tooltip=f"Vrijwilligerskorps Actief: {dept.name}").add_to(
                            fg_vrijwilligerskorps)

        # 7. SIT Locaties
        for sit in sits:
            if sit.lat and sit.lon:
                header_color = "#800080" if 'med' in sit.type.lower() and 'log' in sit.type.lower() else (
                    "#d32f2f" if 'med' in sit.type.lower() else "#1976d2")
                bg_style = "background: linear-gradient(90deg, #d32f2f 50%, #1976d2 50%);" if 'med' in sit.type.lower() and 'log' in sit.type.lower() else f"background-color: {header_color};"
                sit_pin = f"<div style='position: absolute; transform: translate(-50%, -100%);'><div style='{bg_style} color: white; border: 2px solid white; border-radius: 4px; padding: 2px 4px; font-size: 11px; font-weight: bold; box-shadow: 1px 1px 4px rgba(0,0,0,0.4);'>SIT</div><div style='width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid {header_color}; margin: 0 auto;'></div></div>"
                folium.Marker(
                    location=[sit.lat, sit.lon],
                    icon=folium.DivIcon(html=sit_pin, class_name="empty"),
                    tooltip=f"{sit.type}: {sit.name}",
                    popup=f"<b>{sit.name}</b><br>Adres: {sit.address}"
                ).add_to(fg_sit)

        # 8. ZOEKFUNCTIE (Geïntegreerd)
        if not gdf_selected.empty:
            search_features = []
            for idx, row in gdf_selected.iterrows():
                display_name = f"{row['deelgemeente']} (Deelgemeente van {row['hoofdgemeente']})"
                search_features.append({"search_name": display_name, "geometry": row.geometry})
            for name, group in gdf_selected.groupby('hoofdgemeente'):
                search_features.append(
                    {"search_name": f"{name} (Hoofdgemeente)", "geometry": group.geometry.union_all()})
            for name, group in gdf_selected.groupby('cluster_name'):
                search_features.append({"search_name": f"{name} (Afdeling)", "geometry": group.geometry.union_all()})

            search_gdf = gpd.GeoDataFrame(search_features, crs=gdf_selected.crs).to_crs(epsg=4326)
            search_layer = folium.GeoJson(search_gdf, name="Verborgen Zoeklaag", show=True,
                                          style_function=lambda x: {'fillOpacity': 0, 'weight': 0,
                                                                    'color': 'transparent',
                                                                    'interactive': False}).add_to(m)

            search_control = Search(layer=search_layer, geom_type='Polygon',
                                    placeholder="Zoek op gemeente of afdeling...", collapsed=True,
                                    search_label='search_name', weight=4, color='#d32f2f', position='topleft',
                                    initial=False)
            search_control.add_to(m)

            search_var_name = f"{search_layer.get_name()}searchControl"
            custom_search_js = f"""
            <script>
            document.addEventListener("DOMContentLoaded", function() {{
                setTimeout(function() {{
                    var searchInstance = window["{search_var_name}"] || (typeof {search_var_name} !== 'undefined' ? {search_var_name} : null);
                    if (searchInstance) {{
                        var rk_search_timeout_id = null; var rk_found_layer = null;
                        searchInstance.options.initial = false;
                        function fullClear() {{
                            if (rk_found_layer) {{ if (typeof rk_found_layer.setStyle === 'function') {{ rk_found_layer.setStyle({{ fillOpacity: 0, opacity: 0, weight: 0, color: 'transparent' }}); }} rk_found_layer = null; }}
                            if (typeof searchInstance._clear === 'function') {{ searchInstance._clear(); }}
                        }}
                        searchInstance.on('search:locationfound', function(e) {{
                            if (rk_search_timeout_id !== null) {{ clearTimeout(rk_search_timeout_id); }}
                            if (rk_found_layer) {{ if (typeof rk_found_layer.setStyle === 'function') {{ rk_found_layer.setStyle({{ fillOpacity: 0, opacity: 0, weight: 0, color: 'transparent' }}); }} }}
                            rk_found_layer = e.layer;
                            rk_search_timeout_id = setTimeout(function() {{ fullClear(); }}, 30000);
                        }});
                        searchInstance.on('search:expanded', fullClear);
                        searchInstance.on('search:collapsed', fullClear);
                        searchInstance.on('search:cancel', fullClear);
                    }}
                }}, 800);
            }});
            </script>
            """
            m.get_root().html.add_child(Element(custom_search_js))

        # 9. Lagen Toevoegen & Menu genereren
        layers = [fg_afdelingen, fg_basis, fg_regio, fg_locaties, fg_vrijwilligerskorps, fg_ziekenwagens, fg_sit,
                  fg_jeugd, fg_zorgbib, fg_brugfiguren, fg_internationaal, fg_uitleen, fg_geen_labels, fg_label_gem,
                  fg_label_afd, fg_label_sam]
        [fg.add_to(m) for fg in layers]

        MapEnhancer().add_to(m)
        EasyPrint(filename=f"RodeKruis_{prov_name}_{timestamp}").add_to(m)

        groups_dict = {
            'Basiskaart': [tl_licht, tl_osm, tl_geen],
            'Afdelingen': [fg_afdelingen, fg_basis],
            'Vrijwilligerskorpsen': [fg_vrijwilligerskorps],
            'Overlay': [fg_locaties, fg_regio],
            'Disciplines': [fg_ziekenwagens, fg_sit, fg_jeugd, fg_zorgbib, fg_brugfiguren, fg_internationaal,
                            fg_uitleen],
            'Tekst Labels': [fg_geen_labels, fg_label_gem, fg_label_afd, fg_label_sam]
        }

        control = GroupedLayerControl(groups=groups_dict, collapsed=False)
        control.options = {'exclusiveGroups': ['Basiskaart', 'Afdelingen', 'Tekst Labels'], 'collapsed': False}
        control.add_to(m)

        # 10. Legende, Copyrights & Easter Eggs inladen
        author_info = "Sasja Wijnants - sasja.wijnants@vrijwilliger.rodekruis.be"
        m.get_root().header.add_child(Element(f'<meta name="author" content="{author_info}">'))

        protection_html = f"""
        <div style="display: none !important;" data-creator="{author_info}" aria-hidden="true">Ontwikkeld door {author_info}</div>
        <script>
            console.info("%c🚀 Interactieve Kaart Rode Kruis {prov_name}", "color: #d32f2f; font-size: 16px; font-weight: bold;");
            console.info("%c👨‍💻 Ontworpen & Ontwikkeld door: {author_info}", "color: #555; font-size: 12px; font-weight: bold;");
        </script>
        """
        m.get_root().html.add_child(Element(protection_html))

        current_year = datetime.now().year
        current_date_str = datetime.now().strftime('%d/%m/%Y')
        copyright_html = f"""
        <div style="position: absolute; bottom: 15px; left: 15px; width: auto; height: auto; background-color: rgba(255, 255, 255, 0.85); z-index: 9999; padding: 5px 10px; border: 1px solid rgba(0,0,0,0.1); border-radius: 4px; font-size: 11px; font-family: Arial, sans-serif; box-shadow: 0 1px 4px rgba(0,0,0,0.2); pointer-events: none;">
            <b>&copy; {current_year} Rode Kruis Vlaanderen</b> - Sasja Wijnants<br><span style="font-size: 10px; color: #555;">Interactieve Kaart {prov_name} - {current_date_str}</span>
        </div>
        """

        legend_html = """
        <div id="rk-legend-wrapper" style="position: absolute; bottom: 30px; right: 15px; z-index: 9999; background-color: rgba(255, 255, 255, 0.95); padding: 10px; border: 1px solid #ccc; border-radius: 5px; font-family: Arial, sans-serif; font-size: 12px; box-shadow: 2px 2px 5px rgba(0,0,0,0.2); pointer-events: auto; min-width: 170px;">
            <div id="rk-legend-header" style="display: flex; justify-content: space-between; align-items: center; cursor: pointer; border-bottom: 1px solid #ccc; padding-bottom: 3px;">
                <h4 style="margin: 0; font-size: 13px; color: #d32f2f;">Legende Disciplines</h4>
                <span id="rk-legend-toggle" style="font-weight: bold; font-size: 16px; margin-left: 15px; line-height: 1; color: #d32f2f;">−</span>
            </div>
            <div id="rk-legend-content" style="margin-top: 8px; display: block;">
                <div style="display: flex; align-items: center; margin-bottom: 4px;"><div style="width: 16px; height: 16px; margin-right: 8px; border: 1px solid #666; background: repeating-linear-gradient(45deg, #FFA500, #FFA500 3px, white 3px, white 6px);"></div> Jeugd</div>
                <div style="display: flex; align-items: center; margin-bottom: 4px;"><div style="width: 16px; height: 16px; margin-right: 8px; border: 1px solid #666; background: repeating-linear-gradient(-45deg, #800080, #800080 3px, white 3px, white 6px);"></div> Zorgbib</div>
                <div style="display: flex; align-items: center; margin-bottom: 4px;"><div style="width: 16px; height: 16px; margin-right: 8px; border: 1px solid #666; background: repeating-linear-gradient(90deg, #008080, #008080 3px, white 3px, white 6px);"></div> Brugfiguren</div>
                <div style="display: flex; align-items: center; margin-bottom: 4px;"><div style="width: 16px; height: 16px; margin-right: 8px; border: 1px solid #666; background: repeating-linear-gradient(0deg, #0000FF, #0000FF 3px, white 3px, white 6px);"></div> Internationaal</div>
                <div style="display: flex; align-items: center;"><div style="width: 16px; height: 16px; margin-right: 8px; border: 1px solid #666; background: repeating-linear-gradient(135deg, #008000, #008000 3px, white 3px, white 6px);"></div> Uitleendienst</div>
                <div style="display: flex; align-items: center; margin-top: 6px; border-top: 1px solid #eee; padding-top: 6px;"><div style="width: 16px; height: 16px; margin-right: 8px; border: 2px solid #388E3C; background-color: rgba(76, 175, 80, 0.4);"></div> Vrijwilligerskorpsen</div>
            </div>
        </div>
        """

        inject_js = f"""
        <script>
            setTimeout(function() {{
                var mapDiv = document.getElementById('{m.get_name()}');
                mapDiv.insertAdjacentHTML('beforeend', `{copyright_html}`);
                mapDiv.insertAdjacentHTML('beforeend', `{legend_html}`);
                var legendHeader = document.getElementById('rk-legend-header');
                if (legendHeader) {{
                    legendHeader.addEventListener('click', function() {{
                        var content = document.getElementById('rk-legend-content');
                        var toggle = document.getElementById('rk-legend-toggle');
                        if (content.style.display === 'none') {{ content.style.display = 'block'; toggle.innerText = '−'; }} 
                        else {{ content.style.display = 'none'; toggle.innerText = '+'; }}
                    }});
                }}
                var wrapper = document.getElementById('rk-legend-wrapper');
                if (wrapper) {{
                    L.DomEvent.disableClickPropagation(wrapper);
                    L.DomEvent.disableScrollPropagation(wrapper);
                }}
            }}, 500);
        </script>
        """
        m.get_root().html.add_child(folium.Element(inject_js))

        # 11. Opslaan en Optimaliseren
        m.save(output_path)
        db.close()

        print(f"[GENERATOR] Bestand opgeslagen. Post-processing start...")
        deduplicate_geojson_in_html(output_path)
        enforce_fifo_storage()
        print(f"[GENERATOR] Volledig Klaar!")

    except Exception as e:
        print(f"[GENERATOR FOUT] Fatale fout tijdens generatie: {e}")
        import traceback
        traceback.print_exc()
        db.close()