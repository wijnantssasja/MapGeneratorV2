import sys
import os
import re
import warnings
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import mapping, Polygon, MultiPolygon, LineString, MultiLineString
import colorsys
import folium
from folium.plugins import StripePattern, GroupedLayerControl, Search
from branca.element import Element, MacroElement
import branca.colormap as cm
from shapely.geometry import Point
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import time
import yaml
import random
import base64
import json
import itertools
import copy
from datetime import datetime
from jinja2 import Template
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# -------------------------------
# Warning Filters
# -------------------------------
warnings.filterwarnings("ignore", message=".*Geometry is in a geographic CRS.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)


# -------------------------------
# Logging System
# -------------------------------
class OutputLogger:
    def __init__(self, filename="map_generator.log", stream="stdout"):
        self.terminal = sys.stdout if stream == "stdout" else sys.stderr
        self.log = open(filename, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()


def setup_logging():
    log_file = os.path.join(os.getcwd(), "map_generator.log")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"\n{'=' * 60}\n")
        f.write(f"--- Rode Kruis Kaart Generator Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        f.write(f"{'=' * 60}\n")

    sys.stdout = OutputLogger(log_file, stream="stdout")
    sys.stderr = OutputLogger(log_file, stream="stderr")
    print(f"[INFO] Logging geactiveerd. Output wordt opgeslagen in: {log_file}")


# -------------------------------
# PyInstaller Asset Helper
# -------------------------------
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# -------------------------------
# Global Configuration & Cache
# -------------------------------
CONFIG = {}
GEO_CACHE = None
GEO_CACHE_FILE = "geocode_cache.json"


# -------------------------------
# Caching & Location Helpers
# -------------------------------
def get_geocoded_address(address, geolocator):
    global GEO_CACHE
    if GEO_CACHE is None:
        if os.path.exists(GEO_CACHE_FILE):
            try:
                with open(GEO_CACHE_FILE, "r", encoding="utf-8") as f:
                    GEO_CACHE = json.load(f)
            except Exception as e:
                print(f"[WARN] Cache corrupter, start met schone cache: {e}")
                GEO_CACHE = {}
        else:
            GEO_CACHE = {}

    current_time = time.time()

    if address in GEO_CACHE:
        entry = GEO_CACHE[address]
        if current_time - entry.get("timestamp", 0) < 86400:
            return entry.get("lat"), entry.get("lon")

    print(f"[INFO] Resolving adres (Nieuw of >24u oud): {address}")
    try:
        location = geolocator.geocode(address, timeout=10)
        time.sleep(1.1)
        if location:
            GEO_CACHE[address] = {
                "lat": location.latitude,
                "lon": location.longitude,
                "timestamp": current_time
            }
            with open(GEO_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(GEO_CACHE, f, indent=4)
            return location.latitude, location.longitude
    except Exception as e:
        print(f"[WARN] Kon adres '{address}' niet resolven: {e}")

    return None, None


# -------------------------------
# Path, Naming & Image Helpers
# -------------------------------
def get_output_path(extension):
    folder = CONFIG['paths'].get('output_folder', 'output')
    if not os.path.exists(folder):
        os.makedirs(folder)

    base_name = CONFIG['paths'].get('base_filename', 'rodekruis_map')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{base_name}_{timestamp}.{extension}"
    return os.path.join(folder, filename)


def get_base64_image(image_path):
    abs_path = resource_path(image_path)
    try:
        if os.path.exists(abs_path):
            with open(abs_path, "rb") as img_file:
                encoded_string = base64.b64encode(img_file.read()).decode('utf-8')
                return f"data:image/png;base64,{encoded_string}"
    except Exception as e:
        print(f"[WARN] Kon icoon niet laden op pad {abs_path}: {e}")
    return None


# -------------------------------
# Custom Folium Plugins
# -------------------------------
class EasyPrint(MacroElement):
    def __init__(self, position='topleft', title='Exporteer Map', exportOnly=True, filename='rodekruis_map', **kwargs):
        super().__init__()
        self._name = 'EasyPrint'
        self.options = {
            'position': position,
            'title': title,
            'exportOnly': exportOnly,
            'filename': filename,
            'hideControlContainer': True,
            'sizeModes': ['Current', 'A4Landscape'],
            'tileWait': 1500,
            **kwargs
        }

    def render(self, **kwargs):
        super().render(**kwargs)
        figure = self.get_root()
        figure.header.add_child(
            folium.Element(
                '<script src="https://cdn.jsdelivr.net/npm/leaflet-easyprint@2.1.9/dist/bundle.js"></script>')
        )

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var easyPrint = L.easyPrint({{ this.options_json }}).addTo({{ this._parent.get_name() }});
        {% endmacro %}
        """
    )

    @property
    def options_json(self):
        return json.dumps(self.options)


class MapEnhancer(MacroElement):
    def __init__(self):
        super().__init__()
        self._name = 'MapEnhancer'

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        function enhanceMap(layer) {
            if (layer.setStyle && layer.options) {
                if (layer.options.className && layer.options.className.includes('kleurloos-shape')) {
                    if (!layer._clickTogglable) {
                        layer._clickTogglable = true;
                        layer.on('click', function(e) {
                            var currentOpacity = this.options.fillOpacity;
                            if (currentOpacity < 0.1) {
                                this.setStyle({fillColor: '#d32f2f', fillOpacity: 0.6});
                            } else {
                                this.setStyle({fillColor: '#ffffff', fillOpacity: 0.01});
                            }
                            L.DomEvent.stopPropagation(e);
                        });
                    }
                }
            }
            if (layer.eachLayer) {
                layer.eachLayer(enhanceMap);
            }
        }

        function enforceZOrder(map) {
            var inwonLayers = [];
            var afdLayers = [];
            var clusterLayers = [];
            var regioLayers = [];
            var provLayers = [];
            var debugLayers = [];

            function checkAndSort(l) {
                if (l.options && l.options.className) {
                    if (l.options.className.includes('layer-inwoners')) inwonLayers.push(l);
                    if (l.options.className.includes('layer-afdelingen')) afdLayers.push(l);
                    if (l.options.className.includes('layer-clusters')) clusterLayers.push(l);
                    if (l.options.className.includes('layer-regio')) regioLayers.push(l);
                    if (l.options.className.includes('layer-province')) provLayers.push(l);
                    if (l.options.className.includes('layer-debug-ref')) debugLayers.push(l);
                }
            }

            map.eachLayer(function(layer) {
                if (layer.eachLayer) {
                    layer.eachLayer(checkAndSort);
                } else {
                    checkAndSort(layer);
                }
            });

            inwonLayers.forEach(l => { if (l.bringToBack) l.bringToBack(); });
            afdLayers.forEach(l => { if (l.bringToFront) l.bringToFront(); });
            clusterLayers.forEach(l => { if (l.bringToFront) l.bringToFront(); });
            regioLayers.forEach(l => { if (l.bringToFront) l.bringToFront(); });
            provLayers.forEach(l => { if (l.bringToFront) l.bringToFront(); });
            debugLayers.forEach(l => { if (l.bringToFront) l.bringToFront(); });
        }

        function enforceCheckboxesAndRadios() {
            var groups = document.querySelectorAll('.leaflet-control-layers-group');
            groups.forEach(function(g) {
                var labelEl = g.querySelector('.leaflet-control-layers-group-name');
                if (!labelEl) return;
                var groupName = labelEl.innerText.trim();
                var inputs = g.querySelectorAll('input');

                if (groupName.includes('Vrijwilligers') || groupName.includes('Disciplines') || groupName.includes('Overlay') || groupName.includes('Data') || groupName.includes('Analyse')) {
                    inputs.forEach(function(i) { 
                        i.type = 'checkbox'; 
                        i.removeAttribute('name'); 
                    });
                }
                if (groupName.includes('Basiskaart') || groupName.includes('Afdelingen') || groupName.includes('Tekst Labels') || groupName.includes('Debug')) {
                    var safeName = groupName.replace(/\\s+/g, '');
                    inputs.forEach(function(i) { 
                        i.type = 'radio'; 
                        i.name = 'radioGroup_' + safeName; 
                    });
                }
            });
        }

        setTimeout(function() {
            var mapObjects = Object.values(window).filter(obj => obj instanceof L.Map);
            if (mapObjects.length > 0) {
                var map = mapObjects[0];
                map.eachLayer(enhanceMap);
                enforceZOrder(map);

                map.on('layeradd', function(e) {
                    enhanceMap(e.layer);
                    enforceZOrder(map);
                });
            }
            var layerControls = document.querySelectorAll('.leaflet-control-layers, .leaflet-control-layers-list');
            layerControls.forEach(function(ctrl) {
                ctrl.addEventListener('touchmove', function(e) { e.stopPropagation(); }, { passive: true });
            });
            enforceCheckboxesAndRadios();
        }, 500);
        setTimeout(enforceCheckboxesAndRadios, 1500);
        {% endmacro %}
        """
    )


def deduplicate_geojson_in_html(html_path):
    """
    Post-processor die de opgeslagen Folium HTML inleest, zoekt naar exact
    dezelfde GeoJSON datasets, en deze samenvoegt om bestandsgrootte te besparen.
    """
    print("[INFO] Post-processing HTML: Zoeken naar dubbele GeoJSON data...")
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Nieuwe Folium structuur: geo_json_123_add({"type": "FeatureCollection", ...});
        # re.MULTILINE zorgt dat we per regel scannen.
        # Groep 1: Inspringen, Groep 2: Variabelenaam, Groep 3: De gigantische JSON string
        pattern = re.compile(r'^(\s*)(geo_json_[a-f0-9]+)_add\((.+)\);$', re.MULTILINE)

        seen_geojsons = {}
        bytes_saved = 0
        replacements = 0
        shared_var_counter = 0

        def replacer(match):
            nonlocal bytes_saved, replacements, shared_var_counter
            indent = match.group(1)  # Spaties voor een nette code-opmaak
            var_name = match.group(2)  # Bijv: geo_json_abcd
            json_data = match.group(3)  # De ruwe data: {"type": ...}

            if json_data in seen_geojsons:
                # We hebben exact deze data al eerder gezien!
                replacements += 1
                bytes_saved += len(json_data)
                shared_var = seen_geojsons[json_data]

                # Vervang de gigantische lijn door een verwijzing naar de gedeelde data
                return f"{indent}{var_name}_add({shared_var}); /* Geoptimaliseerd: Duplicaat! */"
            else:
                # Eerste keer dat we deze specifieke coördinaten/data zien
                shared_var_counter += 1
                shared_var = f"shared_geojson_data_{shared_var_counter}"
                seen_geojsons[json_data] = shared_var

                # Sla de data EENMALIG op in een nieuwe JavaScript variabele, en gebruik hem
                return f"{indent}var {shared_var} = {json_data};\n{indent}{var_name}_add({shared_var});"

        # Voer de zoek-en-vervang actie uit over de hele HTML
        optimized_content = pattern.sub(replacer, content)

        if replacements > 0:
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(optimized_content)
            mb_saved = bytes_saved / (1024 * 1024)
            print(f"[SUCCES] Post-processing klaar! {replacements} dubbele lagen samengevoegd.")
            print(f"         Ruimtebesparing in HTML: ~{mb_saved:.2f} MB")
        else:
            print("[INFO] Geen exacte GeoJSON-duplicaten gevonden om te optimaliseren.")

    except Exception as e:
        print(f"[WARN] Fout tijdens post-processing van de HTML: {e}")


# -------------------------------
# Logic & Geometry Functions
# -------------------------------

def apply_manual_fusions(gdf, manual_fusions):
    """Overschrijft de parent_name direct o.b.v. Naam of ID."""
    if "parent_name" not in gdf.columns:
        return gdf

    updates = 0
    for new_parent_name, val_list in manual_fusions.items():
        for val in val_list:
            val_str = str(val).strip()
            val_clean = val_str.replace('.0', '')

            mask = pd.Series(False, index=gdf.index)

            if val_clean.isdigit():
                if "id" in gdf.columns: mask = mask | (gdf["id"] == val_clean)
                if "parent_id" in gdf.columns: mask = mask | (gdf["parent_id"] == val_clean)
            else:
                if "name" in gdf.columns:
                    name_match = gdf["name"].str.lower() == val_str.lower()
                    mask = mask | name_match

                    if name_match.any():
                        orig_parents = gdf.loc[name_match, "parent_name"].unique()
                        mask = mask | gdf["parent_name"].isin(orig_parents)

            if mask.sum() > 0:
                gdf.loc[mask, "parent_name"] = str(new_parent_name)
                updates += mask.sum()

    print(f"[INFO] Manual fusions: {updates} shapes samengevoegd onder nieuwe namen.")
    return gdf


def load_and_filter():
    print("[START] Laden van shapefile...")
    shape_path = resource_path(CONFIG['paths']['input_shapefile'])
    if not os.path.exists(shape_path):
        print(f"[ERROR] Kan shapefile niet vinden op: {shape_path}")
        return gpd.GeoDataFrame(), gpd.GeoDataFrame(), set()

    gdf_raw = gpd.read_file(shape_path)

    # Normaliseer naar 'parent_name'
    if "hoofdgem" in gdf_raw.columns and "parent_name" not in gdf_raw.columns:
        gdf_raw.rename(columns={"hoofdgem": "parent_name"}, inplace=True)

    if "parent_name" not in gdf_raw.columns:
        print("[WARN] Kolom 'parent_name' niet gevonden! Fallback naar parent_id of 'Onbekend'.")
        if "parent_id" in gdf_raw.columns:
            gdf_raw["parent_name"] = gdf_raw["parent_id"]
        else:
            gdf_raw["parent_name"] = "Onbekend"

    for col in ["id", "parent_id", "parent_name"]:
        if col in gdf_raw.columns:
            gdf_raw[col] = gdf_raw[col].astype(str).str.replace(r'\.0$', '', regex=True)

    gdf = gdf_raw.copy()

    if "id" in gdf.columns:
        exclude_list = [str(x).replace('.0', '') for x in CONFIG['settings'].get('exclude_ids', [])]
        if exclude_list:
            gdf = gdf[~gdf["id"].isin(exclude_list)].copy()

    configured_muns = set()
    for cluster_info in CONFIG.get('departments', {}).values():
        configured_muns.update([m.lower() for m in cluster_info.get("members", [])])

    manual_assignments = {str(k).lower(): str(v) for k, v in CONFIG.get('manual_shape_assignments', {}).items()}
    manual_assigned_keys = set(manual_assignments.keys())

    gdf["name_lower"] = gdf["name"].str.lower()
    gdf["pname_lower"] = gdf["parent_name"].str.lower()

    # Zoek match op deelgemeente OF op parent_name (hoofdgemeente)
    found_mask = (gdf["pname_lower"].isin(configured_muns)) | \
                 (gdf["name_lower"].isin(configured_muns)) | \
                 (gdf["name_lower"].isin(manual_assigned_keys))

    if "id" in gdf.columns:
        found_mask = found_mask | gdf["id"].isin(manual_assigned_keys)

    vb = gdf[found_mask].copy()

    found_muns = set(vb["name_lower"].unique()).union(set(vb["pname_lower"].unique()))
    missing_muns = configured_muns - found_muns

    if {"name", "id", "parent_name"}.issubset(vb.columns):
        vb = vb.dissolve(by=["name", "id", "parent_name"], as_index=False)

    return gdf_raw, vb, missing_muns


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255))


def generate_random_pastel():
    h = random.random()
    l = random.uniform(0.6, 0.85)
    s = random.uniform(0.3, 0.6)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return rgb_to_hex((r, g, b))


def determine_provinces(gdf_full, gdf_selected):
    print("[INFO] Provinciegrenzen berekenen via ruimtelijke analyse...")
    cluster_to_prov = {k.lower(): v.get('province', 'Onbekend') for k, v in CONFIG.get('departments', {}).items()}

    gdf_selected['temp_prov'] = gdf_selected['cluster_name'].fillna('').str.lower().map(cluster_to_prov).fillna(
        'Onbekend')

    prov_valid = gdf_selected[gdf_selected['temp_prov'] != 'Onbekend']
    if prov_valid.empty:
        print("[WARN] Geen afdelingen met een ingevulde provincie gevonden, ruimtelijke toewijzing overgeslagen.")
        gdf_full['calculated_province'] = 'Onbekend'
        return gdf_full

    prov_boundaries = prov_valid.dissolve(by='temp_prov')
    prov_dict = {prov: geom for prov, geom in zip(prov_boundaries.index, prov_boundaries.geometry)}

    def get_prov(geom):
        if geom is None or geom.is_empty: return "Buiten grens"
        centroid = geom.centroid
        for prov, p_geom in prov_dict.items():
            if centroid.within(p_geom): return prov

        max_area = 0
        best_prov = "Buiten grens"
        for prov, p_geom in prov_dict.items():
            if geom.intersects(p_geom):
                intersection_area = geom.intersection(p_geom).area
                if intersection_area > max_area:
                    max_area = intersection_area
                    best_prov = prov
        return best_prov

    gdf_full['calculated_province'] = gdf_full.geometry.apply(get_prov)
    return gdf_full


def assign_colors_and_groups(gdf):
    mun_to_clusters = {}
    for cluster_name, cluster_info in CONFIG['departments'].items():
        for mun in cluster_info.get("members", []):
            m_lower = mun.lower()
            if m_lower not in mun_to_clusters:
                mun_to_clusters[m_lower] = []
            mun_to_clusters[m_lower].append(cluster_name)

    gdf["cluster_name"] = None

    # PASS 1: Handmatige Toewijzingen
    manual_assignments = CONFIG.get('manual_shape_assignments', {})
    if manual_assignments:
        for shape_key, dept_name in manual_assignments.items():
            k_str = str(shape_key).strip().lower()
            if k_str.isdigit() and "id" in gdf.columns:
                mask = gdf["id"] == k_str
            else:
                mask = gdf["name_lower"] == k_str

            if mask.sum() > 0:
                gdf.loc[mask, "cluster_name"] = str(dept_name)

    # PASS 2: Veilige Toewijzingen (Zonder conflict)
    unassigned_mask = gdf["cluster_name"].isna()
    for idx, row in gdf[unassigned_mask].iterrows():
        p_lower = row.get("pname_lower", "")
        n_lower = row.get("name_lower", "")

        candidates_deel = mun_to_clusters.get(n_lower, [])
        candidates_hoofd = mun_to_clusters.get(p_lower, [])

        all_candidates = list(set(candidates_deel + candidates_hoofd))

        if len(all_candidates) == 1:
            gdf.at[idx, "cluster_name"] = all_candidates[0]

    # PASS 3: Conflictresolutie via Ruimtelijke Nabijheid
    still_unassigned = gdf[gdf["cluster_name"].isna()]
    for idx, row in still_unassigned.iterrows():
        p_lower = row.get("pname_lower", "")
        n_lower = row.get("name_lower", "")

        candidates_deel = mun_to_clusters.get(n_lower, [])
        candidates_hoofd = mun_to_clusters.get(p_lower, [])
        all_candidates = list(set(candidates_deel + candidates_hoofd))

        if not all_candidates:
            continue

        print(f"[INFO] Conflict gedetecteerd voor '{n_lower}' (Hoofd: '{p_lower}'). Opties: {all_candidates}")

        best_candidate = None
        min_dist = float('inf')

        for candidate in all_candidates:
            cand_shapes = gdf[(gdf["cluster_name"] == candidate) & (gdf.index != idx)]

            if not cand_shapes.empty:
                cand_geom = cand_shapes.geometry.union_all()
                dist = row.geometry.distance(cand_geom)
            else:
                dist = 999999

            if dist < min_dist:
                min_dist = dist
                best_candidate = candidate

        if best_candidate is None or min_dist == float('inf'):
            best_candidate = candidates_deel[0] if candidates_deel else candidates_hoofd[0]

        gdf.at[idx, "cluster_name"] = best_candidate
        print(f"       -> Toegewezen aan '{best_candidate}' o.b.v. kleinste afstand.")

        # ==========================================
        # Extra data (Kleuren, Regio's, etc.) invullen
        # ==========================================
        cluster_to_group = {}
        for cluster_name, cluster_info in CONFIG['departments'].items():
            if 'group' in cluster_info:
                cluster_to_group[cluster_name.lower()] = cluster_info['group']

        # 1. Standaard regio toewijzen op basis van de afdeling
        gdf["group_name"] = gdf["cluster_name"].str.lower().map(cluster_to_group)

        # 2. OVERRIDE: Manuele regio's forceren (Belangrijk voor provinciale zetels)
        manual_regions = CONFIG.get('manual_region_assignments', {})
        if manual_regions:
            # Maak alles lowercase voor een foutloze match
            mr_lower = {str(k).strip().lower(): str(v) for k, v in manual_regions.items()}

            for idx, row in gdf.iterrows():
                n_lower = str(row.get("name", "")).lower()
                p_lower = str(row.get("parent_name", "")).lower()

                # Deelgemeente krijgt voorrang op hoofdgemeente
                if n_lower in mr_lower:
                    gdf.at[idx, "group_name"] = mr_lower[n_lower]
                elif p_lower in mr_lower:
                    gdf.at[idx, "group_name"] = mr_lower[p_lower]

        gdf["color"] = ""

    working_cluster_map = {}
    for wc_name, clusters in CONFIG.get('clusters', {}).items():
        for c in clusters:
            working_cluster_map[c.lower()] = wc_name
    gdf["working_cluster_name"] = gdf["cluster_name"].str.lower().map(working_cluster_map)

    unique_clusters = gdf["cluster_name"].dropna().unique()

    for cluster in unique_clusters:
        cluster_config = CONFIG['departments'].get(cluster, {})
        mask = gdf["cluster_name"] == cluster

        is_zetel = (cluster_config.get("type", "") == "provinciale_zetel")

        if 'color' in cluster_config:
            final_color = cluster_config['color']
        elif is_zetel:
            final_color = ""
        else:
            final_color = generate_random_pastel()

        gdf.loc[mask, "color"] = final_color

    unclustered_mask = gdf["cluster_name"].isna()
    if unclustered_mask.any():
        for idx in gdf[unclustered_mask].index:
            gdf.at[idx, "color"] = generate_random_pastel()

    return gdf


def geocode_sit_locations():
    sit_list = CONFIG.get('sit_locations', [])
    if not sit_list: return []
    print("[INFO] Coördinaten berekenen voor SIT locaties...")
    geolocator = Nominatim(user_agent="rk_map_generator_v129", timeout=10)
    sit_data = []

    for sit in sit_list:
        lat_conf = sit.get("lat")
        lon_conf = sit.get("lon")

        if lat_conf is not None and lon_conf is not None:
            sit_entry = sit.copy()
            sit_entry['lat'] = float(lat_conf)
            sit_entry['lon'] = float(lon_conf)
            sit_data.append(sit_entry)
            continue

        address = sit.get("address", "")
        if not address: continue

        full_address = address + ", België"
        lat, lon = get_geocoded_address(full_address, geolocator)
        if lat is not None and lon is not None:
            sit_entry = sit.copy()
            sit_entry['lat'] = lat
            sit_entry['lon'] = lon
            sit_data.append(sit_entry)

    return sit_data


def write_debug_files(gdf_full, gdf_selected, missing_muns):
    print("[INFO] Bezig met wegschrijven van debug-bestanden...")
    try:
        used_ids = gdf_selected['id'].dropna().unique()
        unused_shapes = gdf_full[~gdf_full['id'].isin(used_ids)]
        if not unused_shapes.empty:
            cols = [c for c in ['id', 'name', 'parent_name'] if c in unused_shapes.columns]
            unused_shapes[cols].to_csv("debug_unused_shapes.csv", index=False)
        else:
            pd.DataFrame(columns=['id', 'name', 'parent_name']).to_csv("debug_unused_shapes.csv", index=False)

        missing_log = []
        for dept, info in CONFIG.get('departments', {}).items():
            for member in info.get('members', []):
                if member.lower() in missing_muns:
                    missing_log.append(f"Afdeling: {dept} | Member niet gevonden in shapefile: {member}")

        with open("debug_missing_members.log", "w", encoding="utf-8") as f:
            f.write("\n".join(missing_log) if missing_log else "Alle members zijn succesvol gevonden in de shapefile.")

        fragmented = []
        cluster_groups = gdf_selected.groupby('cluster_name')
        for name, group in cluster_groups:
            if pd.notna(name):
                u_geom = group.geometry.union_all()
                if u_geom.geom_type == 'MultiPolygon' and len(u_geom.geoms) > 1:
                    poly_details = []
                    for _, row in group.iterrows():
                        p_id = str(row.get('id', 'Onbekend'))
                        p_name = str(row.get('name', 'Onbekend'))
                        poly_details.append(f"{p_name} (ID: {p_id})")

                    details_str = ", ".join(poly_details)
                    fragmented.append(
                        f"Afdeling '{name}' bestaat uit {len(u_geom.geoms)} losse, niet-aangrenzende gebieden.\nBetrokken polygonen: {details_str}")

        with open("debug_fragmented_departments.log", "w", encoding="utf-8") as f:
            f.write("\n\n".join(fragmented) if fragmented else "Geen fysiek gefragmenteerde afdelingen gevonden.")

        # ==========================================
        # Export van Gedeelde/Conflicterende gebieden (Zoals op de kaart!)
        # ==========================================
        print("[INFO] Genereren van 'debug_gedeelde_gebieden.csv'...")
        hoofdgem_to_clusters = {}
        for idx, row in gdf_selected.iterrows():
            p_name = row.get("parent_name", "Onbekend")
            c_name = row.get("cluster_name", "Onbekend")
            if pd.notna(c_name) and c_name != "Onbekend":
                if p_name not in hoofdgem_to_clusters:
                    hoofdgem_to_clusters[p_name] = set()
                hoofdgem_to_clusters[p_name].add(c_name)

        shared_list = []
        for idx, row in gdf_selected.iterrows():
            p_name = row.get("parent_name", "Onbekend")
            c_name = row.get("cluster_name", "Onbekend")

            alle_clusters_in_hoofdgem = hoofdgem_to_clusters.get(p_name, set())

            if len(alle_clusters_in_hoofdgem) > 1:
                andere_afdelingen = sorted(list(alle_clusters_in_hoofdgem - {c_name}))

                shared_list.append({
                    'shape_id': row.get('id', 'Onbekend'),
                    'deelgemeente': row.get('name', 'Onbekend'),
                    'hoofdgemeente': p_name,
                    'toegewezen_aan_afdeling': c_name,
                    'hoofdgemeente_gedeeld_met': ", ".join(andere_afdelingen)
                })

        if shared_list:
            pd.DataFrame(shared_list).to_csv("debug_gedeelde_gebieden.csv", index=False, sep=";", encoding="utf-8-sig")
            print(f"       -> Er zijn {len(shared_list)} shapes geëxporteerd die in een gedeelde hoofdgemeente liggen.")
        else:
            print("       -> Geen gedeelde hoofdgemeenten gevonden.")

        print("[INFO] Genereren van 'export_alle_deelgemeenten.csv' voor analyse...")
        export_df = gdf_full.copy()
        export_df['hoofdgemeente'] = export_df.get('parent_name', 'Onbekend')

        id_to_cluster = dict(zip(gdf_selected['id'], gdf_selected['cluster_name']))
        export_df['huidige_afdeling'] = export_df['id'].map(id_to_cluster).fillna("Niet Toegewezen")

        cols_to_export = ['id', 'name', 'parent_name', 'calculated_province', 'huidige_afdeling']
        available_cols = [c for c in cols_to_export if c in export_df.columns]

        export_csv = export_df[available_cols].rename(columns={
            'id': 'shape_id',
            'name': 'deelgemeente',
            'parent_name': 'hoofdgemeente_naam',
            'calculated_province': 'provincie'
        })

        export_csv.to_csv("export_alle_deelgemeenten.csv", index=False, sep=";", encoding="utf-8-sig")

        print("[INFO] Standaard debug bestanden succesvol gegenereerd.")
    except Exception as e:
        print(f"[WARN] Fout bij wegschrijven debug bestanden: {e}")


def add_search_auto_clear_to_html(html_path):
    """
    Zorgt ervoor dat de rode highlight-rand van de zoekbalk na 30 seconden
    of bij een volgende zoekopdracht automatisch verdwijnt.
    Perfect afgestemd op de addControl structuur in de gegenereerde HTML.
    """
    print("[INFO] Post-processing HTML: Gecorrigeerde clear-logica voor zoekbalk injecteren...")
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Zoek naar de unieke variabele van de Search Control en de addControl regel
        # Dit matcht exact met jouw HTML: var search_control_xxx = new L.Control.Search(...);
        pattern = re.compile(
            r'(var\s+(search_control_[a-f0-9]+)\s*=\s*new\s+L\.Control\.Search\(.*?\.addControl\(\s*\2\s*\);)',
            re.DOTALL)

        search_match = pattern.search(content)
        if search_match:
            full_block = search_match.group(1)
            var_name = search_match.group(2)  # Dit haalt bijv. 'search_control_fa5e019...' op

            # JavaScript-code die we injecteren, specifiek gekoppeld aan de variabele
            search_js_events = f"""
        // ==========================================
        // AUTO-CLEAR HIGHLIGHT LOGICA (V2.5)
        // ==========================================
        var rk_search_timeout_id = null;

        {var_name}.on('search:locationfound', function(e) {{
            if (rk_search_timeout_id !== null) {{
                clearTimeout(rk_search_timeout_id);
            }}

            var self = this;
            rk_search_timeout_id = setTimeout(function() {{
                if (typeof self._clear === 'function') {{
                    self._clear(); 
                }}
                if (self._geocodeMarker) {{
                    if (typeof self._geocodeMarker.setStyle === 'function') {{
                        self._geocodeMarker.setStyle({{ fillOpacity: 0, opacity: 0, weight: 0 }});
                    }}
                    self._map.removeLayer(self._geocodeMarker);
                }}
                rk_search_timeout_id = null;
            }}, 30000); // 30 seconden
        }});

        {var_name}.on('search:expanded', function(e) {{
            if (rk_search_timeout_id !== null) {{
                clearTimeout(rk_search_timeout_id);
                rk_search_timeout_id = null;
            }}
            if (typeof this._clear === 'function') {{
                this._clear();
            }}
            if (this._geocodeMarker) {{
                if (typeof this._geocodeMarker.setStyle === 'function') {{
                    this._geocodeMarker.setStyle({{ fillOpacity: 0, opacity: 0, weight: 0 }});
                }}
                this._map.removeLayer(this._geocodeMarker);
            }}
        }});
        // ==========================================
        """
            # Plak de JavaScript code direct onder het initialisatieblok van de zoekbalk
            optimized_content = content.replace(full_block, full_block + "\n" + search_js_events)

            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(optimized_content)
            print("[SUCCES] Automatische clear-logica succesvol gekoppeld aan de zoekbalk!")
        else:
            print("[WARN] Kon L.Control.Search initialisatie niet vinden in de HTML via addControl patroon.")

    except Exception as e:
        print(f"[WARN] Fout tijdens injecteren van zoekbalk-clear: {e}")


# -------------------------------
# Visualization Functions
# -------------------------------
def export_interactive_map(gdf_full, gdf_selected, sit_data):
    if gdf_selected.empty:
        print("[WARN] Geen afdelingen gevonden om te tekenen!")
        return

    output_html = get_output_path("html")
    settings = CONFIG.get('settings', {})

    print("[INFO] HTML Optimalisatie: Topologische simplificatie en coördinaten afronden...")
    import topojson as tp
    from shapely.wkt import loads, dumps

    # 1. Topologische Simplificatie in meters (Lambert 72)
    gdf_selected = gdf_selected.to_crs(epsg=31370)
    topo = tp.Topology(gdf_selected, prequantize=False)
    gdf_selected = topo.toposimplify(5).to_gdf()
    gdf_selected.crs = "EPSG:31370"
    gdf_selected = gdf_selected.to_crs(epsg=4326)

    # 2. EERST afronden op 5 decimalen
    gdf_selected['geometry'] = gdf_selected['geometry'].apply(
        lambda geom: loads(dumps(geom, rounding_precision=5)) if geom else None
    )

    # 3. DAARNA pas de topologie repareren (Lost knopen op ontstaan door het afronden)
    # buffer(0) is de ultieme reddingsboei voor "side location conflicts"
    gdf_selected['geometry'] = gdf_selected.geometry.buffer(0).make_valid()

    # 4. Opschonen tot zuivere polygonen
    gdf_selected = gdf_selected.explode(index_parts=False)
    gdf_selected = gdf_selected[gdf_selected.geometry.type.isin(['Polygon', 'MultiPolygon'])]

    debug_mode = settings.get('debug_id_print', False)
    debug_show_all_shapes = settings.get('debug_show_all_shapes', False)

    public_version = settings.get('public_version', False)
    productie_versie = settings.get('productie_versie', False)
    # Nieuwe instelling

    prov_filter = settings.get('province_filter', 'All')
    display_region = prov_filter.title() if prov_filter.lower() != 'all' else 'Vlaanderen'

    gdf_selected['mun_label'] = gdf_selected.get('parent_name', 'Onbekend')

    mun_to_depts = {}
    for idx, row in gdf_selected.iterrows():
        m = row['mun_label']
        c = row.get('cluster_name')
        if pd.notna(c) and c != "Onbekend":
            if m not in mun_to_depts:
                mun_to_depts[m] = set()
            mun_to_depts[m].add(c)

    geometries = gdf_selected.geometry.values
    contained_mask = np.zeros(len(gdf_selected), dtype=bool)
    for i, geom_i in enumerate(geometries):
        for j, geom_j in enumerate(geometries):
            if i != j and geom_j.contains(geom_i):
                contained_mask[i] = True
                break
    gdf_selected["is_contained"] = contained_mask

    default_lat = gdf_selected.geometry.centroid.y.mean()
    default_lon = gdf_selected.geometry.centroid.x.mean()

    m = folium.Map(location=[default_lat, default_lon], zoom_start=10, tiles=None)

    print(f"[INFO] Iconen verzamelen (Publieke modus: {'AAN' if public_version else 'UIT'})...")
    all_services = set()
    for cluster_info in CONFIG.get('departments', {}).values():
        for s in cluster_info.get("services", []):
            all_services.add(s.lower())

    loaded_icons = set()
    icon_css_rules = ""
    for service in all_services:
        safe_name = service.replace(" ", "_").replace("-", "_")
        icon_path = f"assets/icon_{service}.png"
        b64 = get_base64_image(icon_path)
        if b64:
            icon_css_rules += f".rk-icon-{safe_name} {{ background-image: url('{b64}'); }}\n"
            loaded_icons.add(service)

    # Injecteer de global popup classes als optimalisatie aan staat
    icon_css_rules += """
    .rk-popup-container { font-family: sans-serif; min-width: 320px; padding: 5px; }
    .rk-popup-title { margin: 0 0 5px 0; color: #d32f2f; border-bottom: 2px solid #d32f2f; padding-bottom: 5px; }
    .rk-popup-body { font-size: 13px; line-height: 1.5; margin-bottom: 5px; }
    .rk-popup-link { color: #1976d2; }
.rk-popup-btn { background-color: #d32f2f; color: white !important; padding: 10px 15px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 14px; display: inline-block; box-shadow: 2px 2px 5px rgba(0,0,0,0.2); }        .rk-popup-btn-container { text-align: center; margin-top: 10px; margin-bottom: 10px; }
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

    tl_licht = folium.TileLayer('cartodbpositron', name='Lichte kaart', control=False, show=True).add_to(m)
    tl_osm = folium.TileLayer(tiles='https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
                              attr='&copy; OpenStreetMap contributors &copy; CARTO', name='Standaard kaart',
                              control=False, show=False).add_to(m)
    transparent_tile = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    tl_geen = folium.TileLayer(tiles=transparent_tile, attr='Geen Achtergrond', name='Geen kaart', control=False,
                               show=False).add_to(m)

    fg_afdelingen = folium.FeatureGroup(name="Afdelingen kleur", overlay=True, control=True)
    fg_basis = folium.FeatureGroup(name="Afdelingen kleurloos", overlay=True, control=True, show=False)
    fg_geen_afd = folium.FeatureGroup(name="Geen afdelingen", overlay=True, control=True, show=False)

    fg_werkingsgebieden = folium.FeatureGroup(name="Clusters", overlay=True, control=True, show=False)
    fg_regio = folium.FeatureGroup(name="Regio", overlay=True, control=True, show=False)
    fg_provincies = folium.FeatureGroup(name="Provinciegrenzen", overlay=True, control=True, show=True)

    fg_locaties = folium.FeatureGroup(name="Afdelingslocaties", overlay=True, control=True, show=False)
    fg_vrijwilligerskorps = folium.FeatureGroup(name="Vrijwilligerskorpsen", overlay=True, control=True, show=False)
    fg_ziekenwagens = folium.FeatureGroup(name="Ziekenwagen", overlay=True, control=True, show=False)
    fg_jeugd = folium.FeatureGroup(name="Jeugd", overlay=True, control=True, show=False)
    fg_zorgbib = folium.FeatureGroup(name="Zorgbib", overlay=True, control=True, show=False)
    fg_brugfiguren = folium.FeatureGroup(name="Brugfiguren", overlay=True, control=True, show=False)
    fg_internationaal = folium.FeatureGroup(name="Internationale Samenwerking", overlay=True, control=True, show=False)
    fg_uitleen = folium.FeatureGroup(name="Uitleendienst", overlay=True, control=True, show=False)
    fg_sit = folium.FeatureGroup(name="SIT", overlay=True, control=True, show=False)

    if not public_version:
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

    fg_geen_labels = folium.FeatureGroup(name="Geen labels", overlay=True, control=True, show=True)
    fg_label_gem = folium.FeatureGroup(name="Gemeente Labels", overlay=True, control=True, show=False)
    fg_label_afd = folium.FeatureGroup(name="Afdeling Labels", overlay=True, control=True, show=False)
    fg_label_sam = folium.FeatureGroup(name="Cluster Labels", overlay=True, control=True, show=False)

    all_departments = list(CONFIG.get('departments', {}).keys())

    if prov_filter.lower() == 'all':
        gdf_selected['province'] = gdf_selected['cluster_name'].map(
            lambda x: CONFIG['departments'].get(x, {}).get('province', 'Onbekend'))
        prov_valid = gdf_selected[gdf_selected['province'] != 'Onbekend']

        if not prov_valid.empty:
            prov_dissolved = prov_valid.dissolve(by='province')
            folium.GeoJson(
                prov_dissolved,
                style_function=lambda x: {
                    'fillColor': 'none',
                    'color': '#2F4F4F',
                    'weight': 5.5,
                    'opacity': 0.9,
                    'className': 'layer-province'
                },
                interactive=False
            ).add_to(fg_provincies)

    print("[INFO] Locaties en ambulances berekenen...")
    geolocator = Nominatim(user_agent="rk_map_generator_v129", timeout=10)

    cluster_coords = {}
    ambulance_data = []

    for cluster_name in all_departments:
        cluster_info = CONFIG['departments'].get(cluster_name, {})
        address = cluster_info.get("address", "")
        services = sorted([s.lower() for s in cluster_info.get("services", [])])

        final_lat, final_lon = None, None
        lat_conf = cluster_info.get("lat")
        lon_conf = cluster_info.get("lon")

        if lat_conf is not None and lon_conf is not None:
            final_lat, final_lon = float(lat_conf), float(lon_conf)

        if final_lat is None and address:
            full_address = address + ", België"
            lat, lon = get_geocoded_address(full_address, geolocator)
            if lat is not None and lon is not None:
                final_lat, final_lon = lat, lon

        if final_lat is None:
            mask = gdf_selected['cluster_name'] == cluster_name
            if mask.any():
                centroid = gdf_selected[mask].geometry.union_all().centroid
                final_lat, final_lon = centroid.y, centroid.x

        if final_lat is None:
            print(f"[WARN] Geen coördinaten gevonden voor {cluster_name}. Wordt in kaartmidden geplaatst.")
            final_lat, final_lon = default_lat, default_lon

        cluster_coords[cluster_name] = {'lat': final_lat, 'lon': final_lon}

        if not public_version:
            zws = cluster_info.get('ziekenwagens', [])
            if zws:
                grouped_zws = {}
                for zw in zws:
                    zw_addr = zw.get('address', address)
                    zw_lat_conf, zw_lon_conf = zw.get('lat'), zw.get('lon')

                    group_key = (zw_addr, zw_lat_conf, zw_lon_conf)
                    if group_key not in grouped_zws: grouped_zws[group_key] = []
                    grouped_zws[group_key].append(zw)

                for (zw_addr, zw_lat_conf, zw_lon_conf), vehicles in grouped_zws.items():
                    z_lat, z_lon = final_lat, final_lon
                    if zw_lat_conf is not None and zw_lon_conf is not None:
                        z_lat, z_lon = float(zw_lat_conf), float(zw_lon_conf)
                    elif zw_addr != address and zw_addr:
                        zw_full_addr = zw_addr + ", België"
                        lat, lon = get_geocoded_address(zw_full_addr, geolocator)
                        if lat is not None and lon is not None:
                            z_lat, z_lon = lat, lon

                    ambulance_data.append({
                        'cluster_name': cluster_name, 'address': zw_addr, 'lat': z_lat, 'lon': z_lon,
                        'is_main_location': (z_lat == final_lat and z_lon == final_lon), 'vehicles': vehicles
                    })
            elif 'ziekenwagen' in services:
                ambulance_data.append({
                    'cluster_name': cluster_name, 'address': address, 'lat': final_lat, 'lon': final_lon,
                    'is_main_location': True, 'vehicles': [{'name': 'Ziekenwagen', 'fleet_nr': 'Onbekend'}]
                })

    for idx, row in gdf_selected.iterrows():
        cluster_name = row.get("cluster_name") or "Onbekend"
        cluster_info = CONFIG['departments'].get(cluster_name, {})

        gemeente = row['mun_label']
        deelgemeente = row.get("name")
        shape_id = row.get("id", "Onbekend")
        email = cluster_info.get("email", "")
        address = cluster_info.get("address", "")
        services = sorted([s.lower() for s in cluster_info.get("services", [])])

        is_zetel = (cluster_info.get("type", "afdeling") == "provinciale_zetel")
        title_text = f"Provinciale Zetel {cluster_name}" if is_zetel else f"Rode Kruis-{cluster_name}"

        website_base = CONFIG['settings'].get('base_url', '#') + cluster_name
        volunteer_url = website_base + "/wat-kan-jij-doen/word-vrijwilliger/"

        gemeente_display = gemeente

        color = row.get("color", "")
        tooltip_text = deelgemeente
        is_transparent = pd.isna(color) or color == "" or row["is_contained"]
        pop_info_html = "<br>"

        icons_html = ""
        if services and not public_version:
            icons_html = "<div style='margin-top: 10px; margin-bottom: 10px;'>"
            for service in services:
                safe_name = service.replace(" ", "_").replace("-", "_")
                if service in loaded_icons:
                    icons_html += f"<div class='rk-icon rk-icon-{safe_name}' title='{service.capitalize()}'></div>"
                else:
                    icons_html += f"<span title='{service.capitalize()}' style='background:#eee; padding:2px 5px; border-radius:3px; margin-right:5px; font-size:11px; cursor: help;'>{service.capitalize()}</span>"
            icons_html += "</div>"

        website_line = "" if is_zetel else f"<b>Website:</b> <a href='{website_base}' target='_blank' class='rk-popup-link'>{website_base}</a><br>"
        volunteer_section = "" if is_zetel else f'<div class="rk-popup-btn-container"><a href="{volunteer_url}" target="_blank" class="rk-popup-btn">Word vrijwilliger</a></div>'
        debug_html = f"<div class='rk-popup-debug'><b>Shape ID:</b> {shape_id}</div>" if debug_mode else ""

        html_content = f"""
            <div class="rk-popup-container">
                <h4 class="rk-popup-title">{title_text}</h4>
                {icons_html}
                <div class="rk-popup-body">
                    <b>Gemeente:</b> {gemeente_display}<br><b>Deelgemeente:</b> {deelgemeente}
                </div>
                {pop_info_html}
                <div class="rk-popup-body">
                    <b>Adres:</b> {address}<br><b>Email:</b> <a href="mailto:{email}" class="rk-popup-link">{email}</a><br>
                    {website_line}
                </div>
                {volunteer_section}
                {debug_html}
            </div>
            """

        popup_color = folium.Popup(html_content, max_width=350)

        folium.GeoJson(
            row.geometry,
            style_function=lambda x, transparent=is_transparent, col=color: {
                'fillColor': 'white' if transparent else col,
                'color': '#444444',
                'weight': 1.2,
                'dashArray': '5, 5',
                'fillOpacity': 0.01 if transparent else 0.7,
                'className': 'layer-afdelingen'
            },
            highlight_function=lambda x: {'weight': 3, 'color': '#666', 'dashArray': ''},
            tooltip=tooltip_text, popup=popup_color
        ).add_to(fg_afdelingen)

    if not gdf_selected.empty:
        mun_dissolved = gdf_selected.dissolve(by='mun_label')

        if not public_version:
            vk_muns = [str(m).lower().strip() for m in CONFIG.get('vrijwilligerskorpsen', [])]
            for mun_name, row in mun_dissolved.iterrows():
                if str(mun_name).lower().strip() in vk_muns:
                    folium.GeoJson(
                        gpd.GeoDataFrame({'geometry': [row.geometry]}, crs=gdf_selected.crs),
                        style_function=lambda x: {'fillColor': '#4CAF50', 'fillOpacity': 0.4, 'color': 'none',
                                                  'weight': 0},
                        interactive=False, tooltip=f"Vrijwilligerskorps Actief: {mun_name}"
                    ).add_to(fg_vrijwilligerskorps)

        folium.GeoJson(mun_dissolved,
                       style_function=lambda x: {'fillColor': 'none', 'color': 'black', 'weight': 2.0, 'fillOpacity': 0,
                                                 'className': 'layer-afdelingen'}, interactive=False).add_to(
            fg_afdelingen)

        cluster_dissolved = gdf_selected.dissolve(by='cluster_name')
        folium.GeoJson(cluster_dissolved,
                       style_function=lambda x: {'fillColor': 'none', 'color': 'black', 'weight': 2.5, 'fillOpacity': 0,
                                                 'className': 'layer-afdelingen'}, interactive=False).add_to(fg_basis)
        folium.GeoJson(cluster_dissolved,
                       style_function=lambda x: {'fillColor': '#ffffff', 'color': 'none', 'weight': 0,
                                                 'fillOpacity': 0.01, 'interactive': True,
                                                 'className': 'kleurloos-shape layer-afdelingen'}).add_to(fg_basis)

        configured_clusters = CONFIG.get('clusters', {})
        for wc_name, clustered_muns in configured_clusters.items():
            mask = gdf_selected['cluster_name'].fillna('').str.lower().isin([c.lower() for c in clustered_muns])
            if mask.any():
                wc_geom = gdf_selected[mask].geometry.union_all()
                folium.GeoJson(gpd.GeoDataFrame({'geometry': [wc_geom]}, crs=gdf_selected.crs),
                               style_function=lambda x: {'fillOpacity': 0, 'color': '#0066FF', 'weight': 4,
                                                         'opacity': 0.9, 'className': 'layer-clusters'},
                               interactive=False, name=wc_name).add_to(fg_werkingsgebieden)

    # De afdelingslocaties (markers) moeten OOK op de publieke kaart komen
    # ==============================================================
    # START VAN DE LOCATIES (Geen 'if not public_version:' hierboven!)
    # ==============================================================
    for cluster_name in all_departments:
        coords = cluster_coords[cluster_name]
        cluster_info = CONFIG['departments'].get(cluster_name, {})
        services = sorted([s.lower() for s in cluster_info.get("services", [])])
        address = cluster_info.get("address", "Adres onbekend")
        email = cluster_info.get("email", "")

        is_zetel = (cluster_info.get("type", "afdeling") == "provinciale_zetel")
        title_text = f"Provinciale Zetel {cluster_name}" if is_zetel else f"Rode Kruis-{cluster_name}"
        icon_name, icon_color = ('star', 'blue') if is_zetel else ('plus', 'red')

        website_base = CONFIG['settings'].get('base_url', '#') + cluster_name
        website_line = "" if is_zetel else f"<b>Website:</b> <a href='{website_base}' target='_blank' style='color: #1976d2;'>{website_base}</a><br>"

        marker_icons_html = ""
        # Verberg de service-iconen in de popup als het een publieke kaart is
        if services and not public_version:
            marker_icons_html = "<div style='margin-top: 10px; margin-bottom: 10px;'>"
            for service in services:
                safe_name = service.replace(" ", "_").replace("-", "_")
                if service in loaded_icons:
                    marker_icons_html += f"<div class='rk-icon rk-icon-{safe_name}' title='{service.capitalize()}'></div>"
                else:
                    marker_icons_html += f"<span title='{service.capitalize()}' style='background:#eee; padding:2px 5px; border-radius:3px; margin-right:5px; font-size:11px; cursor: help;'>{service.capitalize()}</span>"
            marker_icons_html += "</div>"

        marker_debug_html = ""
        if debug_mode and not gdf_selected.empty:
            shapes = gdf_selected[gdf_selected['cluster_name'] == cluster_name]
            shape_ids = ", ".join([str(x) for x in shapes['id'].tolist() if pd.notna(x)])
            marker_debug_html = f"<br><div style='margin-top: 8px; font-size: 11px; color: #888;'><b>Shape IDs in Afdeling:</b> {shape_ids}</div>"

        loc_popup_html = f"""
            <div style="font-family: sans-serif; min-width: 320px; padding: 5px;">
                <h4 style="margin: 0 0 5px 0; color: #d32f2f; border-bottom: 2px solid #d32f2f; padding-bottom: 5px;">{title_text}</h4>
                {marker_icons_html}
                <div style="font-size: 13px;">
                    <b>Adres:</b> {address}<br><b>Email:</b> <a href="mailto:{email}" style="color: #1976d2;">{email}</a><br>
                    {website_line}
                </div>
                {marker_debug_html}
            </div>
            """

        folium.Marker(location=[coords['lat'], coords['lon']],
                      icon=folium.Icon(icon=icon_name, prefix='fa', color=icon_color), tooltip=title_text,
                      popup=folium.Popup(loc_popup_html, max_width=350)).add_to(fg_locaties)

        # Extra patroon-lagen op de kaart ENKEL voor intern gebruik
        if not gdf_selected.empty and not public_version:
            mask = gdf_selected['cluster_name'] == cluster_name
            if mask.any():
                c_gdf = gpd.GeoDataFrame({'geometry': [gdf_selected[mask].geometry.union_all()]},
                                         crs=gdf_selected.crs)

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

        # Ambulances en SIT enkel voor interne kaart
        if not public_version:
            for ambu in ambulance_data:
                info = CONFIG['departments'].get(ambu['cluster_name'], {})
                is_zetel = (info.get("type") == "provinciale_zetel")
                title_text = f"Provinciale Zetel {ambu['cluster_name']}" if is_zetel else f"Rode Kruis-{ambu['cluster_name']}"

                vehicles_html = "".join([
                    f"<li style='margin-bottom: 3px;'><b>{v.get('name', 'Ziekenwagen')}</b> <span style='color: #666; font-size: 11px;'>(Vlootnr: {v.get('fleet_nr', 'Onbekend')})</span></li>"
                    for v in ambu['vehicles']])
                zw_popup_html = f"<div style='font-family: sans-serif; min-width: 200px;'><h4 style='margin: 0 0 5px 0; color: darkred; border-bottom: 1px solid darkred;'>{title_text}</h4><div style='font-size: 13px;'><b>Locatie:</b> {ambu['address']}<ul style='margin-top: 5px; padding-left: 20px;'>{vehicles_html}</ul></div></div>"

                count = len(ambu['vehicles'])
                badge_html = f"<div style='position: absolute; bottom: 8px; right: -5px; background-color: #1976d2; color: white; border-radius: 50%; width: 18px; height: 18px; line-height: 18px; text-align: center; font-size: 11px; font-weight: bold; border: 2px solid white; box-shadow: 1px 1px 2px rgba(0,0,0,0.3);'>{count}</div>" if count > 1 else ""
                html_icon = f"<div style='position: relative; width: 30px; height: 42px; text-align: center; margin-left: -15px; margin-top: -42px;'><i class='fa fa-map-marker' style='font-size: 42px; color: #8B0000; text-shadow: 2px 2px 4px rgba(0,0,0,0.4);'></i><i class='fa fa-ambulance' style='font-size: 16px; color: white; position: absolute; top: 10px; left: 50%; transform: translateX(-50%);'></i>{badge_html}</div>"

                folium.Marker(location=[ambu['lat'], ambu['lon'] + (0.0005 if ambu['is_main_location'] else 0)],
                              icon=folium.DivIcon(html=html_icon, class_name="empty"),
                              tooltip=f"Ziekenwagen(s): {title_text}",
                              popup=folium.Popup(zw_popup_html, max_width=300)).add_to(fg_ziekenwagens)

        for sit in sit_data:
            sit_type = sit.get('type', 'SIT-Med')
            header_color = "#800080" if 'med' in sit_type.lower() and 'log' in sit_type.lower() else (
                "#d32f2f" if 'med' in sit_type.lower() else "#1976d2")
            bg_style = "background: linear-gradient(90deg, #d32f2f 50%, #1976d2 50%); color: white;" if 'med' in sit_type.lower() and 'log' in sit_type.lower() else (
                f"background-color: {header_color}; color: white;")
            html_pin = f"<div style='position: absolute; transform: translate(-50%, -100%);'><div style='{bg_style} border: 2px solid white; border-radius: 4px; padding: 2px 4px; font-size: 11px; font-weight: bold; box-shadow: 1px 1px 4px rgba(0,0,0,0.4);'>SIT</div><div style='width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid {header_color}; margin: 0 auto;'></div></div>"

            vehicles = sit.get('vehicles', [])
            vehicles_html = ""
            if vehicles:
                vehicles_html = "<ul style='margin-top: 5px; padding-left: 20px;'>"
                for v in vehicles:
                    v_name = v.get('name', 'Voertuig')
                    v_fleet = v.get('fleet_nr', 'Onbekend')
                    vehicles_html += f"<li style='margin-bottom: 3px;'><b>{v_name}</b> <span style='color: #666; font-size: 11px;'>(Vlootnr: {v_fleet})</span></li>"
                vehicles_html += "</ul>"

            sit_popup_html = f"""
            <div style='font-family: sans-serif; min-width: 200px;'>
                <h4 style='margin: 0 0 5px 0; color: {header_color}; border-bottom: 1px solid {header_color}; padding-bottom: 5px;'>{sit.get('name', 'SIT Locatie')}</h4>
                <div style='font-size: 13px;'>
                    <b>Type:</b> {sit_type}<br><b>Adres:</b> {sit.get('address', '')}<br>
                    {vehicles_html}
                </div>
            </div>
            """
            folium.Marker(location=[sit['lat'], sit['lon']], icon=folium.DivIcon(html=html_pin, class_name="empty"),
                          tooltip=f"{sit_type}: {sit.get('name', '')}",
                          popup=folium.Popup(sit_popup_html, max_width=300)).add_to(fg_sit)

    if not gdf_selected.empty:
        gdf_proj = gdf_selected.to_crs(epsg=31370)
        base_style = 'position: absolute; left: 0px; top: 0px; transform: translate(-50%, -50%); font-family: DejaVu Sans, sans-serif; white-space: nowrap; text-align: center; pointer-events: none;'

        for name, row in gdf_proj.dissolve(by='mun_label').to_crs(epsg=4326).iterrows():
            folium.Marker([row.geometry.centroid.y, row.geometry.centroid.x], icon=folium.DivIcon(
                html=f'<div style="{base_style} font-size: 11px; font-weight: bold; color: #333; text-shadow: 2px 2px 3px #fff;">{name}</div>')).add_to(
                fg_label_gem)

        for name, row in gdf_proj.dissolve(by='cluster_name').to_crs(epsg=4326).iterrows():
            folium.Marker([row.geometry.centroid.y, row.geometry.centroid.x], icon=folium.DivIcon(
                html=f'<div style="{base_style} font-size: 12px; font-weight: bold; color: #d32f2f; text-shadow: 2px 2px 3px #fff;">{name}</div>')).add_to(
                fg_label_afd)

        if 'working_cluster_name' in gdf_proj.columns and not gdf_proj['working_cluster_name'].dropna().empty:
            for name, row in gdf_proj.dissolve(by='working_cluster_name').to_crs(epsg=4326).iterrows():
                if pd.notna(name):
                    folium.Marker([row.geometry.centroid.y, row.geometry.centroid.x], icon=folium.DivIcon(
                        html=f'<div style="{base_style} font-size: 14px; font-weight: bold; color: #0066FF; text-shadow: 2px 2px 4px #fff;">{name}</div>')).add_to(
                        fg_label_sam)

        regio_proj = gdf_proj.dissolve(by='group_name')

        solid_total = gdf_proj.geometry.union_all()

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

        for gname, row in regio_proj.to_crs(epsg=4326).iterrows():
            if pd.isna(gname) or str(gname).strip() == "":
                continue

            geom = row.geometry
            gname_str = str(gname).upper()

            if prov_filter.lower() == 'all':
                # Bij 'All' (heel Vlaanderen) zetten we de labels netjes in het geografische midden
                pt = geom.representative_point()
                label_lat, label_lon = pt.y, pt.x
            else:
                # Provincie filter: Plaats ze aan de buitenkant
                bounds = geom.bounds  # [minx, miny, maxx, maxy] -> [West, Zuid, Oost, Noord]
                cent = geom.centroid

                # We bepalen 4 ankerpunten net buiten de rand van de regio
                # offset zorgt ervoor dat de tekst niet exact op de grenslijn kleeft
                y_offset = 0.015
                x_offset = 0.025

                # Prioriteit: Boven > Links > Rechts > Onder
                candidates = [
                    ("boven", bounds[3] + y_offset, cent.x),
                    ("links", cent.y, bounds[0] - x_offset),
                    ("rechts", cent.y, bounds[2] + x_offset),
                    ("onder", bounds[1] - y_offset, cent.x)
                ]

                # Verzamel alle ándere regio's in deze provincie om overlap te vermijden
                other_regions = regio_proj[regio_proj.index != gname].to_crs(epsg=4326).geometry.union_all()

                best_lat, best_lon = cent.y, cent.x  # Fallback = in het midden als alles volzet is

                for pos_name, cand_lat, cand_lon in candidates:
                    cand_pt = Point(cand_lon, cand_lat)
                    # Check of dit nieuwe punt niet in een andere regio valt
                    if other_regions.is_empty or not other_regions.contains(cand_pt):
                        best_lat, best_lon = cand_lat, cand_lon
                        break  # Perfecte positie gevonden!

                label_lat, label_lon = best_lat, best_lon

            # Een stevigere text-shadow (stroke) zodat het altijd leesbaar is, ongeacht de achtergrond
            folium.Marker(
                [label_lat, label_lon],
                icon=folium.DivIcon(
                    html=f'<div style="{base_style} font-size: 22px; font-weight: bold; color: #333; text-shadow: 2px 2px 4px #fff, -1px -1px 0 #fff, 1px -1px 0 #fff, -1px 1px 0 #fff, 1px 1px 0 #fff;">{gname_str}</div>'
                )
            ).add_to(fg_regio)

        # ==========================================
        # EXPERIMENTEEL: UNIVERSELE ZOEKFUNCTIE (Geoptimaliseerd!)
        # ==========================================
        print("[INFO] Universele zoekindex opbouwen (Geoptimaliseerd voor bestandsgrootte)...")
        search_features = []

        # 1. Deelgemeenten toevoegen
        for idx, row in gdf_selected.iterrows():
            name = row.get("name", "Onbekend")
            parent = row.get("mun_label", "Onbekend")

            display_name = f"{name} (Deelgemeente)" if str(name).lower() == str(
                parent).lower() else f"{name} (Deelgemeente van {parent})"

            search_features.append({
                "search_name": display_name,
                "geometry": row.geometry
            })

        # 2. Hoofdgemeenten toevoegen
        for name, group in gdf_selected.groupby('mun_label'):
            if pd.notna(name):
                geom = group.geometry.union_all()
                search_features.append({
                    "search_name": f"{name} (Hoofdgemeente)",
                    "geometry": geom
                })

        # 3. Afdelingen toevoegen
        for name, group in gdf_selected.groupby('cluster_name'):
            if pd.notna(name) and name != "Onbekend":
                geom = group.geometry.union_all()

                # Haal de configuratie van deze specifieke afdeling op
                cluster_info = CONFIG.get('departments', {}).get(name, {})
                entiteit_nr = cluster_info.get('entiteitnummer')

                # Als er een entiteitnummer in de yaml staat, plakken we het in de zoekstring
                if entiteit_nr:
                    search_string = f"{name} (Afdeling - {entiteit_nr})"
                else:
                    search_string = f"{name} (Afdeling)"

                search_features.append({
                    "search_name": search_string,
                    "geometry": geom
                })

        # 4. Postcodes toevoegen (Samenvoegen per postcode!)
        if 'postcode' in gdf_selected.columns:
            for pc, group in gdf_selected.groupby('postcode'):
                pc_str = str(pc).strip()
                if pc_str and pc_str != "nan":
                    muns = ", ".join(sorted(group['mun_label'].dropna().unique()))
                    geom = group.geometry.union_all()
                    search_features.append({
                        "search_name": f"{pc_str} (Postcode - {muns})",
                        "geometry": geom
                    })

        # Maak de GeoDataFrame voor de zoeklaag
        search_gdf = gpd.GeoDataFrame(search_features, crs=gdf_selected.crs).to_crs(epsg=4326)

        # Voeg de onzichtbare zoeklaag toe
        search_layer = folium.GeoJson(
            search_gdf,
            name="Verborgen Zoeklaag",
            show=True,
            style_function=lambda x: {'fillOpacity': 0, 'weight': 0, 'color': 'transparent', 'interactive': False}
        ).add_to(m)

        # Activeer de Search Plugin (Opgevangen in een stabiele variabele)
        search_control = Search(
            layer=search_layer,
            geom_type='Polygon',
            placeholder="Zoek op postcode, gemeente of afdeling...",
            collapsed=True,
            search_label='search_name',
            weight=4,
            color='#d32f2f',
            position='topleft',
            initial=False  # <--- DEZE REGEL ACTIVEERT SUBSTRING ZOEKEN
        )
        search_control.add_to(m)

        # ==============================================================================
        # INJECTIE: Auto-clear logica (Wist de rode highlight gegarandeerd na 30 seconden)
        # ==============================================================================
        search_var_name = f"{search_layer.get_name()}searchControl"

        custom_search_js = f"""
                <script>
                document.addEventListener("DOMContentLoaded", function() {{
                    var rk_search_timeout_id = null;
                    var rk_found_layer = null;

                    setTimeout(function() {{
                        var searchInstance = window["{search_var_name}"] || (typeof {search_var_name} !== 'undefined' ? {search_var_name} : null);

                        if (searchInstance) {{
                            searchInstance.options.initial = false;
                            // Functie 1: Wist ENKEL de rode rand van de vorige polygoon
                            function resetOldLayer() {{
                                if (rk_found_layer) {{
                                    if (typeof rk_found_layer.setStyle === 'function') {{
                                        rk_found_layer.setStyle({{ fillOpacity: 0, opacity: 0, weight: 0, color: 'transparent' }});
                                    }}
                                    rk_found_layer = null;
                                }}
                            }}

                            // Functie 2: Volledige reset (wist de rand én de tekst/marker in de zoekbalk)
                            function fullClear() {{
                                resetOldLayer();
                                if (typeof searchInstance._clear === 'function') {{
                                    searchInstance._clear();
                                }}
                            }}

                            // Event 1: Nieuwe locatie gevonden
                            searchInstance.on('search:locationfound', function(e) {{
                                // Stop de timer van de vorige zoekopdracht
                                if (rk_search_timeout_id !== null) {{
                                    clearTimeout(rk_search_timeout_id);
                                    rk_search_timeout_id = null;
                                }}

                                // *** DE FIX: Wis de VORIGE rode rand voordat we de nieuwe opslaan! ***
                                resetOldLayer();

                                // Sla de nieuwe, roodgekleurde polygoon op
                                rk_found_layer = e.layer;

                                // Start de nieuwe timer van 30 seconden
                                rk_search_timeout_id = setTimeout(function() {{
                                    fullClear();
                                    rk_search_timeout_id = null;
                                }}, 30000);
                            }});

                            // Event 2: Zoekbalk wordt (opnieuw) geopend
                            searchInstance.on('search:expanded', function(e) {{
                                if (rk_search_timeout_id !== null) {{
                                    clearTimeout(rk_search_timeout_id);
                                    rk_search_timeout_id = null;
                                }}
                                fullClear();
                            }});

                            // Event 3: Zoekbalk ingeklapt of actie geannuleerd (kruisje geklikt)
                            searchInstance.on('search:collapsed', function(e) {{
                                if (rk_search_timeout_id !== null) {{
                                    clearTimeout(rk_search_timeout_id);
                                    rk_search_timeout_id = null;
                                }}
                                fullClear();
                            }});

                            searchInstance.on('search:cancel', function(e) {{
                                if (rk_search_timeout_id !== null) {{
                                    clearTimeout(rk_search_timeout_id);
                                    rk_search_timeout_id = null;
                                }}
                                fullClear();
                            }});
                        }}
                    }}, 800);
                }});
                </script>
                """
        m.get_root().html.add_child(Element(custom_search_js))

    # Locaties worden hier nu standaard aan toegevoegd
    layers_to_add = [fg_afdelingen, fg_basis, fg_geen_afd, fg_geen_labels, fg_label_gem, fg_label_afd, fg_label_sam,
                     fg_locaties]

    # Clusters en Regio uitsluiten voor het publiek
    if not public_version:
        layers_to_add.extend([fg_werkingsgebieden, fg_regio])

    if prov_filter.lower() == 'all':
        layers_to_add.append(fg_provincies)

    if not public_version:
        layers_to_add.extend([fg_vrijwilligerskorps, fg_ziekenwagens, fg_jeugd, fg_zorgbib, fg_brugfiguren,
                              fg_internationaal, fg_uitleen, fg_sit])
    # Debug Shapes
    if debug_show_all_shapes and not gdf_full.empty:
        fg_debug = folium.FeatureGroup(name="DEBUG: Alle Shapes", overlay=True, control=True, show=False)
        fg_debug_frag = folium.FeatureGroup(name="DEBUG: Gefragmenteerde Afd.", overlay=True, control=True, show=False)

        avail_cols = [c for c in ['id', 'name', 'parent_name'] if c in gdf_full.columns]
        gdf_debug = gdf_full[avail_cols + ['geometry']].copy()

        for col in avail_cols: gdf_debug[col] = gdf_debug[col].astype(str)

        aliases = []
        for c in avail_cols:
            if c == 'parent_name':
                aliases.append("GEMEENTE (Resolved)")
            else:
                aliases.append(c.upper())

        popup = folium.GeoJsonPopup(fields=avail_cols, aliases=aliases, labels=True,
                                    style="background-color: white; color: #333; font-family: arial; font-size: 12px; padding: 5px;")
        tooltip = folium.GeoJsonTooltip(fields=['name']) if 'name' in avail_cols else None

        folium.GeoJson(
            gdf_debug,
            style_function=lambda x: {'fillColor': 'transparent', 'color': 'red', 'weight': 1, 'fillOpacity': 0.1,
                                      'dashArray': '4, 4'},
            highlight_function=lambda x: {'weight': 3, 'fillOpacity': 0.3, 'color': 'red'},
            popup=popup, tooltip=tooltip
        ).add_to(fg_debug)

        fragmented_clusters = []
        for c_name, group in gdf_selected.groupby('cluster_name'):
            if pd.notna(c_name):
                u_geom = group.geometry.union_all()
                if u_geom.geom_type == 'MultiPolygon' and len(u_geom.geoms) > 1:
                    fragmented_clusters.append(c_name)

        if fragmented_clusters:
            gdf_frag = gdf_selected[gdf_selected['cluster_name'].isin(fragmented_clusters)]
            for idx, row in gdf_frag.iterrows():
                c_name = row.get("cluster_name", "Onbekend")
                s_id = row.get("id", "Onbekend")
                s_name = row.get("name", "Onbekend")
                c_col = row.get("color", "#ff0000")
                if pd.isna(c_col) or c_col == "": c_col = "#ff0000"

                frag_popup = f"""
                <div style="font-family: sans-serif; min-width: 250px; padding: 5px;">
                    <h4 style="margin: 0 0 5px 0; color: #d32f2f; border-bottom: 2px solid #d32f2f; padding-bottom: 5px;">Losliggend Grondgebied: {c_name}</h4>
                    <div style="font-size: 13px; line-height: 1.5;">
                        <b>Naam Polygoon:</b> {s_name}<br>
                        <b>Shape ID:</b> {s_id}
                    </div>
                </div>
                """
                folium.GeoJson(
                    row.geometry,
                    style_function=lambda x, col=c_col: {'fillColor': col, 'color': '#000000', 'weight': 2,
                                                         'fillOpacity': 0.6, 'dashArray': '3, 3'},
                    highlight_function=lambda x: {'weight': 4, 'color': 'yellow', 'dashArray': ''},
                    tooltip=f"Deel van {c_name}: {s_name}",
                    popup=folium.Popup(frag_popup, max_width=300)
                ).add_to(fg_debug_frag)

        layers_to_add.append(fg_debug)
        layers_to_add.append(fg_debug_frag)

    [fg.add_to(m) for fg in layers_to_add]
    MapEnhancer().add_to(m)

    groups_dict = {
        'Basiskaart': [tl_licht, tl_osm, tl_geen],
        'Afdelingen': [fg_afdelingen, fg_basis, fg_geen_afd],
    }

    if not public_version:
        groups_dict['Vrijwilligerskorpsen'] = [fg_vrijwilligerskorps]

    # Overlay: Locaties altijd tonen. Werkingsgebieden en Regio enkel indien niet-publiek.
    groups_dict['Overlay'] = [fg_locaties]
    if not public_version:
        groups_dict['Overlay'].extend([fg_werkingsgebieden, fg_regio])

    if prov_filter.lower() == 'all':
        groups_dict['Overlay'].append(fg_provincies)

    if not public_version:
        groups_dict['Disciplines'] = [fg_jeugd, fg_zorgbib, fg_brugfiguren, fg_internationaal, fg_uitleen,
                                      fg_ziekenwagens, fg_sit]
    if not public_version:
        groups_dict['Tekst Labels'] = [fg_geen_labels, fg_label_gem, fg_label_afd, fg_label_sam]
    else:
        groups_dict['Tekst Labels'] = [fg_geen_labels, fg_label_gem, fg_label_afd]

    exclusive_list = ['Basiskaart', 'Afdelingen', 'Tekst Labels']
    if debug_show_all_shapes:
        debug_list = [fg_debug, fg_debug_frag]
        groups_dict['Debug Lagen'] = debug_list
        exclusive_list.append('Debug Lagen')

    control = GroupedLayerControl(groups=groups_dict, collapsed=False)
    control.options = {'exclusiveGroups': exclusive_list, 'collapsed': False}
    control.add_to(m)

    author_info = "Sasja Wijnants - sasja.wijnants@vrijwilliger.rodekruis.be"
    m.get_root().header.add_child(Element(f'<meta name="author" content="{author_info}">'))
    m.get_root().header.add_child(Element(f''))

    protection_html = f"""
    <div style="display: none !important;" data-creator="{author_info}" aria-hidden="true">Ontwikkeld door {author_info}</div>
    <script>
        console.info("%c🚀 Interactieve Kaart Rode Kruis {display_region}", "color: #d32f2f; font-size: 16px; font-weight: bold;");
        console.info("%c👨‍💻 Ontworpen & Ontwikkeld door: {author_info}", "color: #555; font-size: 12px; font-weight: bold;");
    </script>
    """
    m.get_root().html.add_child(Element(protection_html))

    filename_for_export = CONFIG['paths'].get('base_filename',
                                              'rodekruis_map') + f"_{datetime.now().strftime('%Y%m%d')}"
    EasyPrint(filename=filename_for_export).add_to(m)

    current_year = datetime.now().year
    current_date_str = datetime.now().strftime('%d/%m/%Y')
    copyright_html = f"""
    <div style="position: absolute; bottom: 15px; left: 15px; width: auto; height: auto; background-color: rgba(255, 255, 255, 0.85); z-index: 9999; padding: 5px 10px; border: 1px solid rgba(0,0,0,0.1); border-radius: 4px; font-size: 11px; font-family: Arial, sans-serif; box-shadow: 0 1px 4px rgba(0,0,0,0.2); pointer-events: none;">
        <b>&copy; {current_year} Rode Kruis Vlaanderen</b> - Sasja Wijnants<br><span style="font-size: 10px; color: #555;">Interactieve Kaart {display_region} - {current_date_str}</span>
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
            """ + (f"mapDiv.insertAdjacentHTML('beforeend', `{legend_html}`);" if not public_version else "") + f"""

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

            if (window.innerWidth < 850 || window.innerHeight < 600) {{
                var legendContent = document.getElementById('rk-legend-content');
                if (legendContent) {{
                    legendContent.style.display = 'none';
                    document.getElementById('rk-legend-toggle').innerText = '+';
                }}
            }}
        }}, 500);
    </script>
    """
    m.get_root().html.add_child(folium.Element(inject_js))

    m.save(output_html)

    # Run de post-processor direct na het opslaan!
    deduplicate_geojson_in_html(output_html)

    print(f"[DONE] Interactieve kaart klaar! Bestand: {output_html}")


# -------------------------------
# GUI Editor & Hoofdmenu
# -------------------------------
class ConfigEditor:
    def __init__(self, parent, config_data):
        self.viewer = tk.Toplevel(parent)
        self.viewer.title("Configuratie Bekijken & Aanpassen (Actieve Sessie)")
        self.viewer.geometry("900x750")
        self.config = config_data

        self.notebook = ttk.Notebook(self.viewer)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        self.setup_afdelingen_tab()
        self.setup_tree_tab("Clusters (Werkingsgebieden)", "clusters", ["Cluster", "Gemeentes"])
        self.setup_tree_tab("SIT-Locaties", "sit_locations", ["Naam", "Type", "Adres"])
        self.setup_list_tab("Vrijwilligerskorpsen", "vrijwilligerskorpsen")

        self.setup_dict_tab("Globale Parent Namen", "global_parent_names", ["ID", "Nieuwe Naam"])
        self.setup_dict_tab("Handmatige Toewijzingen", "manual_shape_assignments", ["Shape ID", "Afdeling"])

        action_frame = ttk.Frame(self.viewer)
        action_frame.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(action_frame, text="Exporteer Config (Sla op als .yaml)", command=self.save_config_to_file).pack(
            side="right")

    def save_config_to_file(self):
        default_name = f"config_{datetime.now().strftime('%Y%m%d')}.yaml"
        path = filedialog.asksaveasfilename(
            title="Sla configuratie op",
            initialfile=default_name,
            defaultextension=".yaml",
            filetypes=[("YAML bestanden", "*.yaml"), ("Alle bestanden", "*.*")]
        )
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
                messagebox.showinfo("Succes", f"Configuratie opgeslagen als:\n{path}", parent=self.viewer)
            except Exception as e:
                messagebox.showerror("Fout", f"Kon bestand niet opslaan:\n{e}", parent=self.viewer)

    def setup_afdelingen_tab(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Afdelingen")

        self.zw_fields = {}
        self.service_vars = {}
        self.zw_active = tk.BooleanVar()

        top_frame = ttk.Frame(tab, padding=10)
        top_frame.pack(fill="x")
        ttk.Label(top_frame, text="Kies Afdeling:", font=("Arial", 10, "bold")).pack(side="left")

        self.dept_names = sorted(list(self.config.get('departments', {}).keys()))
        self.dept_var = tk.StringVar()
        self.combo = ttk.Combobox(top_frame, textvariable=self.dept_var, values=self.dept_names, state="readonly",
                                  width=40)
        self.combo.pack(side="left", padx=10)
        self.combo.bind("<<ComboboxSelected>>", self.load_dept_details)

        self.detail_canvas = tk.Canvas(tab, highlightthickness=0, bg="#f0f0f0")
        self.scrollbar = ttk.Scrollbar(tab, orient="vertical", command=self.detail_canvas.yview)
        self.scroll_frame = ttk.Frame(self.detail_canvas)

        self.scroll_frame.bind("<Configure>",
                               lambda e: self.detail_canvas.configure(scrollregion=self.detail_canvas.bbox("all")))
        self.detail_canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.detail_canvas.configure(yscrollcommand=self.scrollbar.set)

        self.detail_canvas.pack(side="left", fill="both", expand=True, padx=10)
        self.scrollbar.pack(side="right", fill="y")

        self.fields = {}
        standard_fields = [
            ("type", "Type (bijv. afdeling, provinciale_zetel)"),
            ("group", "Regio (bijv. West, Oost)"),
            ("address", "Adres"),
            ("email", "E-mail"),
            ("color", "Kleur (Hex, bijv. #FF0000)"),
            ("lat", "Breedtegraad (Optioneel)"),
            ("lon", "Lengtegraad (Optioneel)")
        ]

        for key, label in standard_fields:
            f = ttk.Frame(self.scroll_frame, padding=2)
            f.pack(fill="x")
            ttk.Label(f, text=label, width=35).pack(side="left")
            ent = ttk.Entry(f, width=50)
            ent.pack(side="left", padx=5)
            self.fields[key] = ent

        ttk.Separator(self.scroll_frame, orient="horizontal").pack(fill="x", pady=15)
        ttk.Label(self.scroll_frame, text="Services / Disciplines:", font=("Arial", 10, "bold")).pack(anchor="w")

        all_possible_services = ["jeugd", "zorgbib", "brugfiguren", "internationaal", "uitleendienst", "hulpdienst",
                                 "vorming", "bloed"]

        s_grid = ttk.Frame(self.scroll_frame)
        s_grid.pack(fill="x", pady=5)
        for i, s in enumerate(all_possible_services):
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(s_grid, text=s.capitalize(), variable=var)
            cb.grid(row=i // 3, column=i % 3, sticky="w", padx=10, pady=2)
            self.service_vars[s] = var

        ttk.Separator(self.scroll_frame, orient="horizontal").pack(fill="x", pady=15)

        zw_header = ttk.Frame(self.scroll_frame)
        zw_header.pack(fill="x")
        ttk.Label(zw_header, text="Ziekenwagen aanwezig?", font=("Arial", 10, "bold")).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(zw_header, variable=self.zw_active, command=self.toggle_zw_fields).pack(side="left")

        self.zw_frame = ttk.LabelFrame(self.scroll_frame, text="Details Ziekenwagen", padding=10)
        self.zw_frame.pack(fill="x", pady=5)

        for k, l in [("name", "Roepnaam"), ("fleet_nr", "Vlootnummer"), ("address", "Standplaats Adres")]:
            f = ttk.Frame(self.zw_frame)
            f.pack(fill="x", pady=2)
            ttk.Label(f, text=l, width=20).pack(side="left")
            ent = ttk.Entry(f)
            ent.pack(side="left", fill="x", expand=True)
            self.zw_fields[k] = ent

        ttk.Button(tab, text="Sla Afdeling op (Voor deze sessie)", command=self.save_dept_to_session).pack(pady=20)

        if self.dept_names:
            self.combo.current(0)
            self.load_dept_details()

    def toggle_zw_fields(self):
        state = "normal" if self.zw_active.get() else "disabled"
        for ent in self.zw_fields.values():
            ent.config(state=state)

    def load_dept_details(self, event=None):
        dept = self.dept_var.get()
        if not dept: return
        data = self.config['departments'].get(dept, {})

        for k, ent in self.fields.items():
            ent.delete(0, tk.END)
            ent.insert(0, str(data.get(k, "")))

        services = [s.lower() for s in data.get("services", [])]
        for s, var in self.service_vars.items():
            var.set(s in services)

        zws = data.get("ziekenwagens", [])
        self.zw_active.set(len(zws) > 0)
        self.toggle_zw_fields()

        for k, ent in self.zw_fields.items():
            ent.delete(0, tk.END)
            if zws:
                ent.insert(0, str(zws[0].get(k, "")))

    def save_dept_to_session(self):
        dept = self.dept_var.get()
        if not dept: return
        d = self.config['departments'][dept]

        for k, ent in self.fields.items():
            val = ent.get().strip()
            if val:
                d[k] = val
            elif k in d:
                del d[k]

        d["services"] = [s for s, v in self.service_vars.items() if v.get()]
        if self.zw_active.get():
            d["ziekenwagens"] = [{k: ent.get() for k, ent in self.zw_fields.items()}]
        else:
            d["ziekenwagens"] = []

        messagebox.showinfo("Opgeslagen", f"De wijzigingen voor {dept} zijn bewaard voor deze sessie!",
                            parent=self.viewer)

    def setup_tree_tab(self, title, key, columns):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=title)

        ttk.Label(tab, text=f"Weergave van {title} (Alleen-lezen in GUI)", font=("Arial", 10, "italic"),
                  foreground="#666").pack(anchor="w", padx=10, pady=(10, 0))

        if key == "sit_locations":
            tree = ttk.Treeview(tab, columns=columns, show="headings")
            for col in columns:
                tree.heading(col, text=col)
                tree.column(col, width=150)
            tree.pack(fill="both", expand=True, padx=10, pady=10)

            for item in self.config.get(key, []):
                tree.insert("", "end",
                            values=(item.get("name", "Onbekend"), item.get("type", ""), item.get("address", "")))
        else:
            tree = ttk.Treeview(tab, columns=columns[1:], show="tree headings")
            tree.heading("#0", text=columns[0])
            tree.column("#0", width=150)
            for col in columns[1:]:
                tree.heading(col, text=col)
                tree.column(col, width=150)
            tree.pack(fill="both", expand=True, padx=10, pady=10)

            for c, muns in self.config.get(key, {}).items():
                node = tree.insert("", "end", text=c, open=True)
                for m in muns: tree.insert(node, "end", values=(m,))

    def setup_list_tab(self, title, key):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=title)

        ttk.Label(tab, text=f"Weergave van {title} (Alleen-lezen in GUI)", font=("Arial", 10, "italic"),
                  foreground="#666").pack(anchor="w", padx=10, pady=(10, 0))

        listbox = tk.Listbox(tab, font=("Arial", 10))
        listbox.pack(fill="both", expand=True, padx=10, pady=10)
        for item in self.config.get(key, []):
            listbox.insert("end", item)

    def setup_dict_tab(self, title, key, columns):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=title)

        ttk.Label(tab, text=f"Weergave van {title} (Alleen-lezen in GUI)", font=("Arial", 10, "italic"),
                  foreground="#666").pack(anchor="w", padx=10, pady=(10, 0))

        tree = ttk.Treeview(tab, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=200)
        tree.pack(fill="both", expand=True, padx=10, pady=10)

        data_dict = self.config.get(key, {})
        for k, v in data_dict.items():
            tree.insert("", "end", values=(k, v))


def run_gui():
    root = tk.Tk()
    root.title("Rode Kruis Kaart Generator")
    root.geometry("780x680")
    root.configure(bg="#f0f0f0")

    style = ttk.Style()
    if 'clam' in style.theme_names():
        style.theme_use('clam')

    # Variabelen
    config_path_var = tk.StringVar()
    output_dir_var = tk.StringVar()
    filename_var = tk.StringVar(value="rodekruis_map")
    prov_filter_var = tk.StringVar(value="All")

    public_map_var = tk.BooleanVar(value=False)
    productie_versie_var = tk.BooleanVar(value=False)

    debug_id_var = tk.BooleanVar(value=False)
    debug_shapes_var = tk.BooleanVar(value=False)
    debug_logs_var = tk.BooleanVar(value=False)

    def select_file():
        path = filedialog.askopenfilename(title="Selecteer config.yaml", filetypes=[("YAML bestanden", "*.yaml")])
        if path:
            config_path_var.set(path)
            if not output_dir_var.get():
                output_dir_var.set(os.path.dirname(os.path.abspath(path)))
            try:
                global CONFIG
                with open(path, "r", encoding="utf-8") as f:
                    CONFIG = yaml.safe_load(f)

                    if CONFIG and 'paths' in CONFIG and 'base_filename' in CONFIG['paths']:
                        filename_var.set(CONFIG['paths']['base_filename'])

                    provinces = sorted(list(set(
                        str(v.get('province', '')) for v in CONFIG.get('departments', {}).values() if
                        v.get('province'))))
                    if not provinces:
                        prov_combo.config(values=["All"], state="disabled")
                        prov_filter_var.set("All")
                    else:
                        options = ["All"] + provinces if len(provinces) > 1 else provinces
                        prov_combo.config(values=options, state="readonly")
                        prov_filter_var.set(options[0])

                view_btn.config(state="normal")
            except Exception as e:
                messagebox.showerror("Fout bij inladen", f"Kon YAML niet lezen:\n{e}")

    def select_output_dir():
        path = filedialog.askdirectory(title="Kies de Output Map")
        if path: output_dir_var.set(path)

    def generate_map():
        file_path = config_path_var.get()
        if not file_path:
            messagebox.showwarning("Waarschuwing", "Selecteer eerst een config.yaml bestand!")
            return

        try:
            os.chdir(os.path.dirname(os.path.abspath(file_path)))

            if 'settings' not in CONFIG: CONFIG['settings'] = {}
            if 'paths' not in CONFIG: CONFIG['paths'] = {}

            # Hardcoded defaults (worden altijd toegepast)
            CONFIG['settings']['optimize_html'] = True

            # Basis tab
            CONFIG['settings']['public_version'] = public_map_var.get()
            CONFIG['settings']['productie_versie'] = productie_versie_var.get()

            # Geavanceerd tab
            CONFIG['settings']['debug_id_print'] = debug_id_var.get()
            CONFIG['settings']['debug_show_all_shapes'] = debug_shapes_var.get()
            CONFIG['settings']['generate_debug_logs'] = debug_logs_var.get()
            CONFIG['settings']['province_filter'] = prov_filter_var.get()

            if output_dir_var.get(): CONFIG['paths']['output_folder'] = output_dir_var.get()
            if filename_var.get().strip(): CONFIG['paths']['base_filename'] = filename_var.get().strip()

            generate_btn.config(state="disabled", text="Bezig met genereren...")
            status_label.config(text="⚠️ Even geduld, de kaart wordt gebouwd... (Zie log file voor details)",
                                fg="#d32f2f")
            root.update()

            main()

            generate_btn.config(state="normal", text="Genereer Kaart")
            status_label.config(text="Klaar! Bekijk de gekozen output map.", fg="green")
            messagebox.showinfo("Succes!", "De interactieve kaart is succesvol gegenereerd!")

        except Exception as e:
            generate_btn.config(state="normal", text="Genereer Kaart")
            status_label.config(text="Fout opgetreden. Controleer de logs.", fg="red")
            print(f"[CRITICAL ERROR] Tijdens genereren: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Er ging iets mis",
                                 f"Kijk in 'map_generator.log' voor details.\n\nFoutmelding:\n{str(e)}")

    header_frame = tk.Frame(root, bg="#d32f2f", pady=15)
    header_frame.pack(fill="x")
    tk.Label(header_frame, text="Rode Kruis Kaart Generator", font=("Arial", 16, "bold"), bg="#d32f2f",
             fg="white").pack()

    # Tabbladen container
    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=10, pady=(10, 5))

    tab_basis = ttk.Frame(notebook)
    notebook.add(tab_basis, text="Basisscherm")

    tab_geavanceerd = ttk.Frame(notebook)
    notebook.add(tab_geavanceerd, text="Geavanceerd")

    # ================= TAB BASIS =================
    file_frame = tk.Frame(tab_basis, bg="#f0f0f0", pady=10, padx=20)
    file_frame.pack(fill="x")
    tk.Label(file_frame, text="1. Configuratie (YAML)", font=("Arial", 10, "bold"), bg="#f0f0f0").grid(row=0, column=0,
                                                                                                       sticky="w",
                                                                                                       pady=5)
    ttk.Entry(file_frame, textvariable=config_path_var, width=38, state="readonly").grid(row=0, column=1, padx=(10, 5))
    ttk.Button(file_frame, text="Bladeren...", command=select_file).grid(row=0, column=2, padx=(0, 5))
    view_btn = ttk.Button(file_frame, text="Bekijk / Pas aan...", state="disabled",
                          command=lambda: ConfigEditor(root, CONFIG))
    view_btn.grid(row=0, column=3)

    prov_frame = tk.Frame(tab_basis, bg="#f0f0f0", pady=5, padx=20)
    prov_frame.pack(fill="x")
    tk.Label(prov_frame, text="2. Provincie Filter", font=("Arial", 10, "bold"), bg="#f0f0f0").grid(row=0, column=0,
                                                                                                    sticky="w", pady=5)
    prov_combo = ttk.Combobox(prov_frame, textvariable=prov_filter_var, state="disabled", width=36)
    prov_combo.grid(row=0, column=1, padx=(10, 5))

    map_frame = tk.Frame(tab_basis, bg="#f0f0f0", pady=5, padx=20)
    map_frame.pack(fill="x")
    tk.Label(map_frame, text="3. Output Map (Optioneel)", font=("Arial", 10, "bold"), bg="#f0f0f0").grid(row=0,
                                                                                                         column=0,
                                                                                                         sticky="w",
                                                                                                         pady=5)
    ttk.Entry(map_frame, textvariable=output_dir_var, width=38, state="readonly").grid(row=0, column=1, padx=(10, 5))
    ttk.Button(map_frame, text="Kiezen...", command=select_output_dir).grid(row=0, column=2, padx=(0, 5))

    tk.Label(map_frame, text="4. Output Naam (Prefix)", font=("Arial", 10, "bold"), bg="#f0f0f0").grid(row=1, column=0,
                                                                                                       sticky="w",
                                                                                                       pady=5)
    ttk.Entry(map_frame, textvariable=filename_var, width=38).grid(row=1, column=1, padx=(10, 5))
    tk.Label(map_frame, text="(_datum.html wordt toegevoegd)", font=("Arial", 8, "italic"), bg="#f0f0f0",
             fg="#666").grid(row=1, column=2, columnspan=2, sticky="w")

    settings_basis = ttk.LabelFrame(tab_basis, text="5. Kaart Instellingen", padding=15)
    settings_basis.pack(fill="x", padx=20, pady=10)

    ttk.Checkbutton(settings_basis, text="Publieke Kaart (Geen disciplines/interne info)",
                    variable=public_map_var).grid(row=0, column=0, sticky="w", pady=5)
    tk.Label(settings_basis, text="- Exporteert een schone versie met enkel afdelingen en tekstlabels.",
             font=("Arial", 9, "italic"), fg="#666").grid(row=0, column=1, sticky="w", padx=15)

    ttk.Checkbutton(settings_basis, text="Productieversie (Asynchroon / Kleine HTML)",
                    variable=productie_versie_var).grid(row=1, column=0, sticky="w", pady=5)
    tk.Label(settings_basis, text="- Exporteert de zware GeoJSON code naar externe data-bestanden.",
             font=("Arial", 9, "italic"), fg="#666").grid(row=1, column=1, sticky="w", padx=15)

    # ================= TAB GEAVANCEERD =================
    settings_adv = ttk.LabelFrame(tab_geavanceerd, text="Debug & Ontwikkelaarsopties", padding=15)
    settings_adv.pack(fill="x", padx=20, pady=10)

    ttk.Checkbutton(settings_adv, text="Toon Shape ID's", variable=debug_id_var).grid(row=0, column=0, sticky="w",
                                                                                      pady=5)
    tk.Label(settings_adv, text="- Print interne ID's in popups (handig voor 'exclude_ids').",
             font=("Arial", 9, "italic"), fg="#666").grid(row=0, column=1, sticky="w", padx=15)

    ttk.Checkbutton(settings_adv, text="Toon Alle Basis Shapes", variable=debug_shapes_var).grid(row=1, column=0,
                                                                                                 sticky="w", pady=5)
    tk.Label(settings_adv, text="- Maakt een extra laag aan met alle ruwe gemeentegrenzen.",
             font=("Arial", 9, "italic"), fg="#666").grid(row=1, column=1, sticky="w", padx=15)

    ttk.Checkbutton(settings_adv, text="Genereer extra Debug Bestanden", variable=debug_logs_var).grid(row=2, column=0,
                                                                                                       sticky="w",
                                                                                                       pady=5)
    tk.Label(settings_adv, text="- Schrijft logs/csv uit van o.a. ongebruikte polygonen en missende shapes.",
             font=("Arial", 9, "italic"), fg="#666").grid(row=2, column=1, sticky="w", padx=15)

    # ================= ACTIE & STATUS =================
    action_frame = tk.Frame(root, bg="#f0f0f0", pady=10)
    action_frame.pack(fill="x")

    generate_btn = tk.Button(action_frame, text="Genereer Kaart", command=generate_map, bg="#1976d2", fg="white",
                             font=("Arial", 12, "bold"), padx=20, pady=10)
    generate_btn.pack()

    status_label = tk.Label(root, text="Klaar voor actie.", font=("Arial", 10), bg="#f0f0f0", fg="#555")
    status_label.pack(side="bottom", pady=5)

    root.mainloop()


def main():
    original_departments = copy.deepcopy(CONFIG.get('departments', {}))
    prov_filter = CONFIG.get('settings', {}).get('province_filter', 'All')

    try:
        # 1. We laden EERST alles globaal in, ongeacht de provincie filter.
        gdf_full, gdf, missing_muns = load_and_filter()
        if gdf.empty:
            raise ValueError("Geen data gevonden in de shapefile!")

        gdf = apply_manual_fusions(gdf, CONFIG.get('manual_fusions', {}))
        gdf = assign_colors_and_groups(gdf)

        # 2. PAS HIER gaan we filteren op de gekozen provincie.
        if prov_filter.lower() != 'all':
            print(f"[INFO] Provincie-filter toepassen: '{prov_filter}' (na globale toewijzing)...")
            valid_clusters = [k for k, v in original_departments.items() if
                              str(v.get('province', '')).lower() == prov_filter.lower()]

            gdf = gdf[gdf['cluster_name'].isin(valid_clusters)].copy()

            CONFIG['departments'] = {k: v for k, v in original_departments.items() if k in valid_clusters}

            if gdf.empty:
                raise ValueError(f"Geen afdelingen overgebleven na filteren op provincie '{prov_filter}'!")

            configured_muns = set()
            for cluster_info in CONFIG['departments'].values():
                configured_muns.update([m.lower() for m in cluster_info.get("members", [])])
            found_muns = set(gdf["name_lower"].unique()).union(set(gdf["pname_lower"].unique()))
            missing_muns = configured_muns - found_muns

        # 3. Rest van de flow
        gdf_full = determine_provinces(gdf_full, gdf)

        if CONFIG.get('settings', {}).get('generate_debug_logs', False):
            write_debug_files(gdf_full, gdf, missing_muns)

        sit_data = geocode_sit_locations()
        export_interactive_map(gdf_full, gdf, sit_data)

    finally:
        # Zorg dat de originele config hersteld wordt als de GUI open blijft staan
        CONFIG['departments'] = original_departments


if __name__ == "__main__":
    setup_logging()

    if "--local" in sys.argv:
        print("[INFO] Draait in lokale development modus (--local). GUI overgeslagen.")
        if os.path.exists("config.yaml"):
            try:
                with open("config.yaml", "r", encoding="utf-8") as f:
                    CONFIG = yaml.safe_load(f)
                main()
                print("[INFO] Lokaal runnen succesvol afgerond. Controleer de output map.")
            except Exception as e:
                print(f"[ERROR] Fout tijdens genereren: {e}")
                import traceback

                traceback.print_exc()
        else:
            print("[ERROR] 'config.yaml' niet gevonden in de huidge map. Voeg een config toe om --local te gebruiken.")
    else:
        run_gui()
