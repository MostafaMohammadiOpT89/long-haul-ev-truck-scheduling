import os
import csv
from typing import Dict, List, Tuple
import json
import time
import urllib.parse


def _script_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _project_root() -> str:
    # Assume this folder lives directly under the project root
    return os.path.dirname(_script_dir())


def _ensure_output_dir(out_dir: str) -> None:
    if not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)


def _cache_path() -> str:
    return os.path.join(_script_dir(), "geocode_cache.json")


def _load_cache() -> Dict[str, Tuple[float, float]]:
    path = _cache_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            # Ensure tuple casting
            return {k: (float(v[0]), float(v[1])) for k, v in raw.items()}
        except Exception:
            return {}
    return {}


def _save_cache(cache: Dict[str, Tuple[float, float]]) -> None:
    try:
        with open(_cache_path(), "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _read_test_instance(path: str) -> Tuple[str, List[str]]:
    """Return (depot_name, ordered_location_names_including_nodes).

    The route shown is the file order: depot -> node1 -> node2 -> ... -> last -> depot.
    """
    depot: str = None
    node_names: List[str] = []
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        section = None
        is_first_vehicle_row = True
        for row in reader:
            if not row:
                continue
            head = row[0].strip()
            if head.startswith("VehicleId"):
                section = "vehicles"
                continue
            if head.startswith("NodeId"):
                section = "nodes"
                continue
            if section == "vehicles" and is_first_vehicle_row:
                # VehicleId,VehicleLocation,VehicleLocationId
                _, vehicle_location, _ = row[:3]
                depot = vehicle_location.strip()
                is_first_vehicle_row = False
                continue
            if section == "nodes":
                # NodeId,Location,LocationId,TimeWindowStart,TimeWindowEnd,Weight,Volume,Revenue,ServiceTime
                if len(row) >= 2:
                    node_names.append(row[1].strip())
    if depot is None:
        raise ValueError(f"Could not find depot in {path}")
    return depot, node_names


def _normalize_location(name: str) -> str:
    """Normalize dataset-specific aliases to canonical place names for geocoding/lookup."""
    alias: Dict[str, str] = {
        "KristiansandS": "Kristiansand",
        "KristiansandN": "Kristiansand",
        "OsloS": "Oslo",
        "OsloO": "Oslo",
        "OsloN": "Oslo",
        "OsloV": "Oslo",
        "Lillestrom": "Lillestrøm",
        "Aas": "Ås",
        "Stjordal": "Stjørdal",
        "TrondheimO": "Trondheim",
        "TrondheimN": "Trondheim",
        "TrondheimS": "Trondheim",
        "TrondheimV": "Trondheim",
        "Aalesund": "Ålesund",
        "Forde": "Førde",
        "StavangerO": "Stavanger",
        "StavangerS": "Stavanger",
        "StavangerV": "Stavanger",
        "BergenS": "Bergen",
        "BergenN": "Bergen",
        "Gjovik": "Gjøvik",
        "Honefoss": "Hønefoss",
        "Flaam": "Flåm",
        "Risor": "Risør",
        "Bodo": "Bodø",
        "Tromso": "Tromsø",
        "Dombaas": "Dombås",
    }
    return alias.get(name, name)


def _get_known_coords() -> Dict[str, Tuple[float, float]]:
    """Hardcoded lat/lon for locations appearing in the test instances (WGS84)."""
    # lat, lon
    return {
        "Kristiansand": (58.1467, 7.9956),
        "Bergen": (60.3913, 5.3221),
        "Grimstad": (58.3405, 8.5934),
        "Sandefjord": (59.1312, 10.2167),
        "Horten": (59.4170, 10.4830),
        "Oslo": (59.9139, 10.7522),
        "Lillestrøm": (59.95597, 11.04918),
        "Ås": (59.6646, 10.7910),
        "Moss": (59.4340, 10.6577),
        "Fredrikstad": (59.2181, 10.9298),
        "Jessheim": (60.1419, 11.1711),
        "Hamar": (60.7945, 11.06798),
        "Drammen": (59.7439, 10.2045),
        "Kongsberg": (59.6699, 9.6502),
        "Geilo": (60.5330, 8.2060),
        "Gol": (60.7010, 8.9440),
        "Nesbyen": (60.5640, 9.1010),
        "Sarpsborg": (59.2839, 11.1096),
        "Kongsvinger": (60.1866, 12.1973),
        "Levanger": (63.7446, 11.2995),
        "Lillehammer": (61.1153, 10.4662),
        "Melhus": (63.2859, 10.2816),
        "Oppdal": (62.5921, 9.6910),
        "Stjørdal": (63.4689, 10.9260),
        "Trondheim": (63.4305, 10.3951),
        "Vinstra": (61.5954, 9.7564),
        "Ålesund": (62.4722, 6.1495),
        "Førde": (61.4522, 5.8573),
        "Kristiansund": (63.1104, 7.7281),
        "Molde": (62.7375, 7.1607),
        "Orkanger": (63.3060, 9.8466),
        "Ulsteinvik": (62.3438, 5.8487),
        "Volda": (62.1476, 6.0712),
        "Steinkjer": (64.0103, 11.4954),
        "Egersund": (58.4513, 6.0040),
        "Haugesund": (59.4138, 5.2680),
        "Mandal": (58.0277, 7.4534),
        "Stavanger": (58.9699, 5.7331),
        "Porsgrunn": (59.1400, 9.6561),
        "Gjøvik": (60.7957, 10.6916),
        "Dombås": (62.0740, 9.1240),
        "Rennebu": (62.8255, 10.0100),
        "Hommelvik": (63.4126, 10.7797),
        "Selbu": (63.2193, 11.0335),
        "Hønefoss": (60.1692, 10.2567),
        "Flåm": (60.8646, 7.1144),
        "Risør": (58.7215, 9.2308),
        "Vossevangen": (60.6256, 6.4110),
        "Sogndal": (61.2280, 7.1039),
        "Mo i Rana": (66.3128, 14.1428),
        "Fauske": (67.2588, 15.3918),
        "Bodø": (67.2804, 14.4049),
        "Narvik": (68.4385, 17.4272),
        "Tromsø": (69.6492, 18.9553),
        "Alta": (69.9689, 23.2716),
        "Hammerfest": (70.6634, 23.6821),
        "Kirkenes": (69.7271, 30.0457),
        "Bryne": (58.7351, 5.6471),
        "Flekkefjord": (58.2975, 6.6602),
    }


def _coords_for_locations(locations: List[str]) -> Tuple[List[Tuple[float, float]], List[str]]:
    """Map a list of location names to coordinates using the known mapping and a geocoding cache.

    Returns (coordinates, unresolved_names). Attempts to geocode any unknowns with geopy if available.
    """
    known = _get_known_coords()
    cache = _load_cache()
    coords: List[Tuple[float, float]] = []
    unresolved: List[str] = []

    # Optional geocoder
    geocoder = None
    try:
        from geopy.geocoders import Nominatim
        geocoder = Nominatim(user_agent="evtdsp_map_generator")
    except Exception:
        geocoder = None

    for name in locations:
        norm = _normalize_location(name)
        if norm in known:
            coords.append(known[norm])
            continue
        if norm in cache:
            coords.append(cache[norm])
            continue
        # Try geocoding if available
        if geocoder is not None:
            try:
                loc = geocoder.geocode(norm + ", Norway", timeout=10)
                if loc is None:
                    loc = geocoder.geocode(norm, timeout=10)
                if loc is not None:
                    lat_lon = (float(loc.latitude), float(loc.longitude))
                    cache[norm] = lat_lon
                    coords.append(lat_lon)
                    # Respect Nominatim usage policy with a small delay
                    time.sleep(1.0)
                    continue
            except Exception:
                pass
        # Still unresolved
        unresolved.append(name)

    # Persist any new cache entries
    _save_cache(cache)
    return coords, unresolved


def _fit_map_to_coords(m, coords: List[Tuple[float, float]]) -> None:
    if not coords:
        return
    min_lat = min(lat for lat, _ in coords)
    max_lat = max(lat for lat, _ in coords)
    min_lon = min(lon for _, lon in coords)
    max_lon = max(lon for _, lon in coords)
    # Add small padding
    lat_pad = (max(1e-6, (max_lat - min_lat))) * 0.05
    lon_pad = (max(1e-6, (max_lon - min_lon))) * 0.05
    m.fit_bounds([[min_lat - lat_pad, min_lon - lon_pad], [max_lat + lat_pad, max_lon + lon_pad]])


def _export_static_map(html_path: str, png_path: str, pdf_path: str) -> bool:
    """Export the saved HTML map to PNG and PDF if selenium/Pillow are available. Returns True if PNG saved."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager
    except Exception:
        return False
    try:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1400,900")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        try:
            url = "file:///" + urllib.parse.quote(os.path.abspath(html_path).replace("\\", "/"))
            driver.get(url)
            time.sleep(2.0)  # allow tiles to load
            driver.save_screenshot(png_path)
        finally:
            driver.quit()
        # Convert to PDF if Pillow available
        try:
            from PIL import Image
            img = Image.open(png_path).convert("RGB")
            img.save(pdf_path, "PDF", resolution=300)
        except Exception:
            pass
        return True
    except Exception:
        return False


def _make_map_html(route_names: List[str], route_coords: List[Tuple[float, float]], out_path: str, export_static: bool = True) -> None:
    try:
        import folium
        from folium.plugins import PolyLineTextPath
    except Exception as e:
        raise RuntimeError(
            "folium is required to render real maps. Install it via: pip install folium"
        ) from e

    # Center map on the mean coordinate
    lat_avg = sum(lat for lat, _ in route_coords) / len(route_coords)
    lon_avg = sum(lon for _, lon in route_coords) / len(route_coords)
    m = folium.Map(location=[lat_avg, lon_avg], zoom_start=8, tiles="OpenStreetMap")

    # Add depot (start) marker distinctly
    depot_lat, depot_lon = route_coords[0]
    depot_name = route_names[0]
    folium.Marker(
        location=[depot_lat, depot_lon],
        icon=folium.Icon(color='red', icon='home', prefix='fa'),
        tooltip=f"1. DEPOT: {depot_name}",
        popup=f"1. DEPOT: {depot_name}",
    ).add_to(m)

    # Add intermediate node markers (all nodes after depot)
    for idx in range(1, len(route_coords)):
        lat, lon = route_coords[idx]
        name = route_names[idx]
        folium.CircleMarker(
            location=[lat, lon],
            radius=6,
            color="#003f5c",
            fill=True,
            fill_color="#4c78a8",
            fill_opacity=0.95,
            popup=f"{idx+1}. {name}",
            tooltip=f"{idx+1}. {name}",
        ).add_to(m)

    # Draw directed segments with a single arrow per link
    for i in range(len(route_coords) - 1):
        seg = [route_coords[i], route_coords[i + 1]]
        pl = folium.PolyLine(seg, color="#555555", weight=4, opacity=0.9)
        pl.add_to(m)
        # Add one directional arrow along the segment (dark green)
        PolyLineTextPath(
            pl,
            '➤',
            repeat=False,
            center=True,
            offset=0,
            attributes={
                'fill': '#006400',
                'font-weight': 'bold',
                'font-size': '18px'
            }
        ).add_to(m)

    # Add legend with exact order
    ordered_items = []
    for idx, name in enumerate(route_names):
        if idx == 0:
            label = f"DEPOT: {name}"
        else:
            label = f"{name}"
        ordered_items.append(label)

    legend_html = (
        '<div style="position: fixed; bottom: 12px; left: 12px; z-index: 9999; '
        'background: rgba(255,255,255,0.95); padding: 10px 12px; border: 1px solid #ccc; '
        'box-shadow: 0 1px 3px rgba(0,0,0,0.25); max-height: 45%; overflow: auto; '
        'font-family: Arial, sans-serif; font-size: 12px; line-height: 1.25;">'
        '<div style="font-weight: 700; margin-bottom: 6px;">Route order</div>'
        '<ol style="margin: 0; padding-left: 18px;">'
        + ''.join(f'<li>{item}</li>' for item in ordered_items)
        + '</ol></div>'
    )
    m.get_root().html.add_child(folium.Element(legend_html))

    # Ensure a good zoom level around the path
    _fit_map_to_coords(m, route_coords)

    # Save HTML
    m.save(out_path)
    # Also export PNG/PDF if possible
    if export_static:
        png_path = out_path.replace('.html', '.png')
        pdf_path = out_path.replace('.html', '.pdf')
        _export_static_map(out_path, png_path, pdf_path)


def generate_maps(instances: List[int] = list(range(1, 13))) -> List[str]:
    """Generate folium HTML maps for the given instance IDs and return output paths."""
    root = _project_root()
    out_dir = os.path.join(root, "TestInstance_Map", "maps")
    _ensure_output_dir(out_dir)

    outputs: List[str] = []
    for i in instances:
        filename = os.path.join(root, f"testInstance{i}.txt")
        if not os.path.exists(filename):
            # Skip missing instances
            continue
        depot, nodes = _read_test_instance(filename)
        # Open-ended route: depot followed by nodes in file order (no return to depot)
        ordered_names = [depot] + nodes
        coords, unresolved = _coords_for_locations(ordered_names)
        if unresolved:
            print(f"[skip] Instance {i}: missing coordinates for {', '.join(sorted(set(unresolved)))}")
            print("       Add to _get_known_coords() or install geopy for auto-geocoding.")
            continue
        out_path = os.path.join(out_dir, f"testInstance_{i}.html")
        _make_map_html(ordered_names, coords, out_path)
        outputs.append(out_path)
    return outputs


def main() -> None:
    outputs = generate_maps()
    print("Saved instance maps:")
    for p in outputs:
        print(f"- {p}")
    if not outputs:
        print("No maps generated (no testInstance*.txt files found).")


if __name__ == "__main__":
    main()


