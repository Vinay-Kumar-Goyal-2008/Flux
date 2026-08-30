"""
pipeline/flood_data.py
Loads the official flood model output dataset containing all county flood polygons.
"""
from __future__ import annotations
import json
from pathlib import Path
from api.models import FloodPolygon, LatLng

DATA_PATH = Path(__file__).parent.parent / "data" / "model_flood_polygons.json"


def load_all_flood_polygons() -> dict[str, FloodPolygon]:
    """Load all county flood polygons from JSON."""
    if not DATA_PATH.exists():
        return {}
    
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    polygons = {}
    for item in data:
        place = item["place"]
        # Standardize key (e.g., 'philadelphia_county_pa', 'volusia_county_fl')
        clean_key = (
            place.lower()
            .replace(", pennsylvania", "_pa")
            .replace(", south carolina", "_sc")
            .replace(", ohio", "_oh")
            .replace(", west virginia", "_wv")
            .replace(", north carolina", "_nc")
            .replace(", florida", "_fl")
            .replace(", indiana", "_in")
            .replace(" ", "_")
            .replace(",", "")
        )
        coords = item.get("flood_coordinates", [])
        if not coords:
            continue
            
        # Coordinates in json are [lng, lat]
        latlngs = [LatLng(lat=pt[1], lng=pt[0]) for pt in coords]
        if latlngs and (latlngs[0].lat != latlngs[-1].lat or latlngs[0].lng != latlngs[-1].lng):
            latlngs.append(latlngs[0])
            
        polygons[clean_key] = FloodPolygon(name=clean_key, coordinates=latlngs)
        
    return polygons


def get_polygon_by_name(name: str) -> FloodPolygon | None:
    polys = load_all_flood_polygons()
    return polys.get(name)
