"""
shelters/finder.py
Find shelter candidates for a flood polygon.

Strategy (in order):
  1. Mireye points_of_interest preset  → hospital, fire_station, school (nearest per sampled point)
  2. OSM Overpass API fallback          → amenity=shelter, emergency=assembly_point in bbox

Both sources are merged, deduplicated, and returned as ShelterCandidate list.
"""
from __future__ import annotations

import math
import time
import httpx

from api.client import MireyeClient, MireyeAPIError
from api.models import FloodPolygon
from shelters.models import ShelterCandidate

# Overpass API — free, no key needed
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# OSM tags that represent emergency shelters
SHELTER_QUERIES = [
    ('amenity', 'shelter'),
    ('emergency', 'assembly_point'),
    ('amenity', 'community_centre'),
    ('amenity', 'social_facility'),
]


# ── Geometry helpers ──────────────────────────────────────────────────────────

def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Straight-line distance in metres between two lat/lng points."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _centroid(polygon: FloodPolygon) -> tuple[float, float]:
    lats = [p.lat for p in polygon.coordinates]
    lngs = [p.lng for p in polygon.coordinates]
    return sum(lats) / len(lats), sum(lngs) / len(lngs)


def _bbox(polygon: FloodPolygon, buffer_deg: float = 0.15) -> tuple[float, float, float, float]:
    """(south, west, north, east) bounding box with a buffer in degrees (~15 km)."""
    lats = [p.lat for p in polygon.coordinates]
    lngs = [p.lng for p in polygon.coordinates]
    return (
        min(lats) - buffer_deg,
        min(lngs) - buffer_deg,
        max(lats) + buffer_deg,
        max(lngs) + buffer_deg,
    )


# ── Source 1: Mireye points_of_interest ──────────────────────────────────────

def _find_via_mireye(
    polygon: FloodPolygon,
    verbose: bool = True,
) -> list[ShelterCandidate]:
    """
    Use Mireye points_of_interest preset to find hospitals, fire stations, schools
    near the polygon centroid.

    Mireye returns the NEAREST of each type to a given coordinate.
    We use a few sampled points to get different candidates.
    """
    candidates: list[ShelterCandidate] = []
    seen: set[str] = set()

    centroid_lat, centroid_lng = _centroid(polygon)

    # Sample a few points around the centroid for variety
    sample_offsets = [
        (0, 0),           # centroid itself
        (0.01, 0.01),     # ~1.5 km NE
        (-0.01, 0.01),    # ~1.5 km SE
        (0.01, -0.01),    # ~1.5 km NW
    ]

    # Mireye POI fields we care about for shelters
    poi_fields = [
        "nearest_hospital_distance_m", "nearest_hospital_name",
        "nearest_fire_station_distance_m", "nearest_fire_station_name",
        "nearest_school_distance_m", "nearest_school_name",
    ]

    if verbose:
        print("  [Mireye] Fetching points_of_interest for shelter candidates...")

    with MireyeClient(timeout=30.0) as client:
        for dlat, dlng in sample_offsets:
            lat = round(centroid_lat + dlat, 6)
            lng = round(centroid_lng + dlng, 6)

            try:
                result = client.fetch(lat=lat, lng=lng, fields=poi_fields)
                fields = result.get("fields", {})

                # Hospital
                hosp_name = fields.get("nearest_hospital_name", {}).get("value")
                hosp_dist = fields.get("nearest_hospital_distance_m", {}).get("value")
                if hosp_name and hosp_dist is not None:
                    key = f"hospital:{hosp_name}"
                    if key not in seen:
                        seen.add(key)
                        # We don't get the shelter's lat/lng from Mireye directly —
                        # approximate from bearing/distance
                        s_lat, s_lng = _approximate_location(lat, lng, float(hosp_dist), bearing=0)
                        candidates.append(ShelterCandidate(
                            name=hosp_name,
                            lat=s_lat,
                            lng=s_lng,
                            shelter_type="hospital",
                            straight_line_distance_m=_haversine_m(centroid_lat, centroid_lng, s_lat, s_lng),
                            source="mireye",
                        ))

                # Fire station
                fire_name = fields.get("nearest_fire_station_name", {}).get("value")
                fire_dist = fields.get("nearest_fire_station_distance_m", {}).get("value")
                if fire_name and fire_dist is not None:
                    key = f"fire:{fire_name}"
                    if key not in seen:
                        seen.add(key)
                        s_lat, s_lng = _approximate_location(lat, lng, float(fire_dist), bearing=45)
                        candidates.append(ShelterCandidate(
                            name=fire_name,
                            lat=s_lat,
                            lng=s_lng,
                            shelter_type="fire_station",
                            straight_line_distance_m=_haversine_m(centroid_lat, centroid_lng, s_lat, s_lng),
                            source="mireye",
                        ))

                # School
                school_name = fields.get("nearest_school_name", {}).get("value")
                school_dist = fields.get("nearest_school_distance_m", {}).get("value")
                if school_name and school_dist is not None:
                    key = f"school:{school_name}"
                    if key not in seen:
                        seen.add(key)
                        s_lat, s_lng = _approximate_location(lat, lng, float(school_dist), bearing=90)
                        candidates.append(ShelterCandidate(
                            name=school_name,
                            lat=s_lat,
                            lng=s_lng,
                            shelter_type="school",
                            straight_line_distance_m=_haversine_m(centroid_lat, centroid_lng, s_lat, s_lng),
                            source="mireye",
                        ))

            except MireyeAPIError as e:
                if verbose:
                    print(f"  [Mireye] Warning: {e}")

            time.sleep(0.15)  # Rate limit gap

    if verbose:
        print(f"  [Mireye] Found {len(candidates)} candidates (hospital/fire/school)")

    return candidates


def _approximate_location(
    origin_lat: float,
    origin_lng: float,
    distance_m: float,
    bearing: float,
) -> tuple[float, float]:
    """
    Approximate a destination lat/lng given origin, distance, and bearing.
    Used because Mireye gives distance but not the shelter's coordinates.
    Bearing: 0=N, 45=NE, 90=E, 180=S, etc.
    """
    R = 6_371_000
    bearing_rad = math.radians(bearing)
    lat1 = math.radians(origin_lat)
    lng1 = math.radians(origin_lng)
    d = distance_m / R

    lat2 = math.asin(
        math.sin(lat1) * math.cos(d) +
        math.cos(lat1) * math.sin(d) * math.cos(bearing_rad)
    )
    lng2 = lng1 + math.atan2(
        math.sin(bearing_rad) * math.sin(d) * math.cos(lat1),
        math.cos(d) - math.sin(lat1) * math.sin(lat2),
    )
    return round(math.degrees(lat2), 6), round(math.degrees(lng2), 6)


# ── Source 2: OSM Overpass API fallback ───────────────────────────────────────

def _find_via_osm(
    polygon: FloodPolygon,
    radius_m: int = 15000,
    verbose: bool = True,
) -> list[ShelterCandidate]:
    """
    Query Overpass API (OSM) for emergency shelters within radius_m of centroid.
    Looks for: amenity=shelter, emergency=assembly_point,
               amenity=community_centre, amenity=social_facility
    """
    centroid_lat, centroid_lng = _centroid(polygon)
    candidates: list[ShelterCandidate] = []
    seen: set[str] = set()

    if verbose:
        print(f"  [OSM] Querying Overpass API for shelters within {radius_m/1000:.0f} km...")

    # Build Overpass QL query — around: radius, lat, lng
    around = f"(around:{radius_m},{centroid_lat},{centroid_lng})"
    query = f"""
[out:json][timeout:25];
(
  node["amenity"="shelter"]{around};
  node["emergency"="assembly_point"]{around};
  node["amenity"="community_centre"]{around};
  node["amenity"="social_facility"]["social_facility"="shelter"]{around};
  way["amenity"="shelter"]{around};
  way["emergency"="assembly_point"]{around};
);
out center 50;
"""

    try:
        resp = httpx.post(
            OVERPASS_URL,
            data={"data": query},
            timeout=30.0,
            headers={"User-Agent": "Mireye-Disaster-Response/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

        for el in data.get("elements", []):
            # Get coordinates
            if el["type"] == "node":
                lat, lng = el.get("lat"), el.get("lng") or el.get("lon")
            else:  # way
                center = el.get("center", {})
                lat, lng = center.get("lat"), center.get("lon")

            if lat is None or lng is None:
                continue

            tags = el.get("tags", {})
            name = (
                tags.get("name")
                or tags.get("name:en")
                or tags.get("amenity", "").replace("_", " ").title()
                or "Emergency Shelter"
            )

            # Determine type
            amenity = tags.get("amenity", "")
            emergency = tags.get("emergency", "")
            if emergency == "assembly_point":
                stype = "assembly_point"
            elif amenity == "shelter":
                stype = "shelter"
            else:
                stype = "shelter"

            osm_id = f"{el['type']}/{el['id']}"
            key = f"osm:{osm_id}"
            if key in seen:
                continue
            seen.add(key)

            dist = _haversine_m(centroid_lat, centroid_lng, lat, lng)
            candidates.append(ShelterCandidate(
                name=name,
                lat=lat,
                lng=lng,
                shelter_type=stype,
                straight_line_distance_m=dist,
                source="osm",
                osm_id=osm_id,
            ))

    except Exception as e:
        if verbose:
            print(f"  [OSM] Overpass query failed: {e}")

    if verbose:
        print(f"  [OSM] Found {len(candidates)} dedicated shelter/assembly-point tags")

    return candidates


# ── Public interface ───────────────────────────────────────────────────────────

def find_shelter_candidates(
    polygon: FloodPolygon,
    radius_m: int = 15000,
    use_mireye: bool = True,
    use_osm: bool = True,
    verbose: bool = True,
) -> list[ShelterCandidate]:
    """
    Find all shelter candidates near a flood polygon.

    Merges Mireye POI data (hospitals/fire stations/schools)
    with OSM Overpass (dedicated shelters, assembly points).

    Args:
        polygon: The flood polygon to find shelters for.
        radius_m: Search radius in metres (default 15 km).
        use_mireye: Query Mireye points_of_interest preset.
        use_osm: Query OSM Overpass API as fallback.
        verbose: Print progress.

    Returns:
        Combined, deduplicated list of ShelterCandidate sorted by distance.
    """
    all_candidates: list[ShelterCandidate] = []

    if use_mireye:
        all_candidates.extend(_find_via_mireye(polygon, verbose=verbose))

    if use_osm:
        all_candidates.extend(_find_via_osm(polygon, radius_m=radius_m, verbose=verbose))

    # Sort by straight-line distance from centroid
    all_candidates.sort(key=lambda s: s.straight_line_distance_m)

    if verbose:
        print(f"\n  [Finder] Total candidates: {len(all_candidates)}")
        for s in all_candidates[:5]:
            print(f"    - {s.name} ({s.shelter_type}) [{s.source}] "
                  f"~ {s.straight_line_distance_m/1000:.1f} km")

    return all_candidates
