"""
shelters/fallback.py
Loads local curated shelter GeoJSON dataset when Mireye or external APIs are unavailable.
"""
import json
from pathlib import Path
from shelters.models import ShelterCandidate

DATA_PATH = Path(__file__).parent / "data" / "local_shelters.geojson"


def load_local_shelter_dataset(
    bbox: tuple[float, float, float, float] | None = None
) -> list[ShelterCandidate]:
    """
    Load curated emergency shelters from local GeoJSON.
    Optionally filters by bounding box (min_lat, min_lon, max_lat, max_lon).
    """
    if not DATA_PATH.exists():
        return []
        
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error loading local shelter dataset: {e}")
        return []
        
    shelters = []
    features = data.get("features", [])
    
    for feat in features:
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        coords = geom.get("coordinates", [])
        
        if len(coords) < 2:
            continue
            
        lon, lat = coords[0], coords[1]
        
        if bbox:
            min_lat, min_lon, max_lat, max_lon = bbox
            if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
                continue
                
        shelter_type = props.get("type", "shelter")
        if "shelter" in shelter_type:
            stype = "shelter"
        elif "hospital" in shelter_type:
            stype = "hospital"
        elif "school" in shelter_type:
            stype = "school"
        else:
            stype = "assembly_point"
            
        shelters.append(
            ShelterCandidate(
                name=props.get("name", "Local Relief Center"),
                lat=lat,
                lng=lon,
                shelter_type=stype,
                straight_line_distance_m=0.0,
                source="local_fallback",
                osm_id=f"local/{props.get('name', 'shelter')}"
            )
        )
        
    return shelters
