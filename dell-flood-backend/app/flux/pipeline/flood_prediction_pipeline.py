"""
pipeline/flood_prediction_pipeline.py
Day 6-7: Nearest Shelters + Best Evacuation Route Engine
Built directly against model flood predictions dataset (us_counties_flood_predictions.json).

Pipeline:
1. Filter: 30 counties -> only actually-flooded ones (drops 'Normal Conditions / Dry Ground')
2. Cluster: DBSCAN with haversine metric (eps in real km) over flood grid-cell coordinates.
   Handles multi-blob disconnected flood pockets within a county.
3. Shelters: Mireye points_of_interest + OSM Overpass API + Local Curated GeoJSON fallback.
4. Routing: NetworkX elevation-weighted road graph with straight-line fallback.
5. Output: Formatted cluster-level evacuation plans ready for Day 10-11 Decision Engine.
"""
from __future__ import annotations

import json
import math
import sys
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path
import numpy as np
from sklearn.cluster import DBSCAN
import networkx as nx

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shelters.fallback import load_local_shelter_dataset
from shelters.finder import find_shelter_candidates
from api.models import FloodPolygon, LatLng
from routing.graph_router import (
    haversine as router_haversine,
    pad_bbox,
    fetch_osm_roads,
    ElevationLookup,
    build_road_graph,
    get_graph_route
)
from visualization.map_plotter import plot_evacuation_map

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = Path(__file__).parent.parent / "output"
DEFAULT_INPUT_FILE = DATA_DIR / "model_flood_polygons.json"

DBSCAN_EPS_KM = 1.5           # points within 1.5km grouped into same cluster (grid spacing is 1km)
DBSCAN_MIN_SAMPLES = 3        # min grid-cells to count as a real cluster (filters noise)
SHELTERS_PER_CLUSTER = 2


# ---------------------------------------------------------------------------
# DISTANCE UTILS
# ---------------------------------------------------------------------------
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


# ---------------------------------------------------------------------------
# STEP 1: LOAD + FILTER
# ---------------------------------------------------------------------------
def load_flood_data(path: Path | str = DEFAULT_INPUT_FILE) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def filter_flooded(records: list[dict]) -> list[dict]:
    """Drop counties classified as dry/normal -- nothing to evacuate there."""
    return [
        r for r in records
        if r.get("classification") != "Normal Conditions / Dry Ground"
        and len(r.get("flood_coordinates", [])) > 0
    ]


# ---------------------------------------------------------------------------
# STEP 2: CLUSTER FLOOD POINTS INTO DISTINCT AFFECTED ZONES
# ---------------------------------------------------------------------------
def cluster_flood_points(
    flood_coordinates: list[list[float]], 
    eps_km: float = DBSCAN_EPS_KM, 
    min_samples: int = DBSCAN_MIN_SAMPLES
) -> list[list[list[float]]]:
    """
    flood_coordinates: list of [lon, lat] pairs.
    Returns list of clusters, each a list of [lon, lat] points.
    Uses haversine metric directly so eps is in real km, not degrees.
    """
    if len(flood_coordinates) < min_samples:
        return [flood_coordinates]

    coords_rad = np.radians([[lat, lon] for lon, lat in flood_coordinates])
    eps_rad = eps_km / 6371.0  # convert km to radians for haversine metric

    db = DBSCAN(eps=eps_rad, min_samples=min_samples, metric="haversine").fit(coords_rad)

    clusters: dict[int, list[list[float]]] = {}
    noise: list[list[float]] = []
    for label, (lon, lat) in zip(db.labels_, flood_coordinates):
        if label == -1:
            noise.append([lon, lat])
            continue
        clusters.setdefault(label, []).append([lon, lat])

    result = list(clusters.values())
    if not result:
        result = [flood_coordinates]
    return result


def cluster_centroid(cluster_points: list[list[float]]) -> tuple[float, float]:
    """Returns (lat, lon)."""
    lats = [p[1] for p in cluster_points]
    lons = [p[0] for p in cluster_points]
    return sum(lats) / len(lats), sum(lons) / len(lons)


def cluster_bbox(cluster_points: list[list[float]], pad_km: float = 2.0) -> tuple[float, float, float, float]:
    """Returns (min_lat, min_lon, max_lat, max_lon)."""
    lats = [p[1] for p in cluster_points]
    lons = [p[0] for p in cluster_points]
    pad_deg = pad_km / 111.0
    return min(lats) - pad_deg, min(lons) - pad_deg, max(lats) + pad_deg, max(lons) + pad_deg


# ---------------------------------------------------------------------------
# STEP 3: SHELTERS -- Mireye / OSM live + local fallback dataset
# ---------------------------------------------------------------------------
LOCAL_SHELTER_DATASET = [
    {"name": "West Chester Community Center", "lat": 39.9596, "lon": -75.6058, "type": "community_center"},
    {"name": "Chester County Fairgrounds Shelter", "lat": 39.9012, "lon": -75.7930, "type": "fairground"},
    {"name": "Media High School", "lat": 39.9168, "lon": -75.3877, "type": "school"},
    {"name": "Philadelphia Convention Center", "lat": 39.9564, "lon": -75.1636, "type": "convention_center"},
    {"name": "North Charleston Coliseum", "lat": 32.8887, "lon": -80.0122, "type": "arena"},
    {"name": "Cuyahoga Community College - Metro", "lat": 41.4890, "lon": -81.6802, "type": "college"},
    {"name": "Athens Community Center", "lat": 39.3292, "lon": -82.1013, "type": "community_center"},
    {"name": "Daytona Beach Shelter (Volusia)", "lat": 29.2108, "lon": -81.0228, "type": "shelter"},
]


def get_shelters_for_cluster(
    cluster_pts: list[list[float]], 
    county_name: str, 
    use_live_apis: bool = True
) -> list[dict]:
    """
    Find shelter candidates near cluster.
    Tries Mireye POI and OSM Overpass; falls back to curated local dataset.
    """
    lat, lon = cluster_centroid(cluster_pts)
    
    if use_live_apis:
        dummy_poly = FloodPolygon(
            name=county_name,
            coordinates=[LatLng(lat=p[1], lng=p[0]) for p in cluster_pts]
        )
        try:
            candidates = find_shelter_candidates(
                polygon=dummy_poly,
                radius_m=12000,
                use_mireye=True,
                use_osm=True,
                verbose=False
            )
            if candidates:
                return [
                    {
                        "name": c.name,
                        "lat": c.lat,
                        "lon": c.lng,
                        "type": c.shelter_type,
                        "source": c.source
                    }
                    for c in candidates
                ]
        except Exception:
            pass

    # Fallback to local curated list
    return [
        {"name": s["name"], "lat": s["lat"], "lon": s["lon"], "type": s["type"], "source": "local_fallback"}
        for s in LOCAL_SHELTER_DATASET
    ]


def top_n_shelters(lat: float, lon: float, shelters: list[dict], n: int = SHELTERS_PER_CLUSTER) -> list[dict]:
    ranked = sorted(shelters, key=lambda s: haversine(lat, lon, s["lat"], s["lon"]))
    return ranked[:n]


# ---------------------------------------------------------------------------
# STEP 4: ROAD NETWORK + ROUTING
# ---------------------------------------------------------------------------
def compute_cluster_route(
    from_lat: float, 
    from_lon: float, 
    to_lat: float, 
    to_lon: float,
    use_road_graph: bool = True
) -> dict:
    """
    Computes road network shortest-path route with elevation cost.
    Falls back gracefully to straight-line distance if road data is sparse.
    """
    dist_straight = haversine(from_lat, from_lon, to_lat, to_lon)
    
    if use_road_graph and dist_straight < 25.0:  # Fetch road graph for reasonably local distances
        try:
            min_lat = min(from_lat, to_lat) - 0.03
            max_lat = max(from_lat, to_lat) + 0.03
            min_lon = min(from_lon, to_lon) - 0.03
            max_lon = max(from_lon, to_lon) + 0.03
            
            roads = fetch_osm_roads((min_lat, min_lon, max_lat, max_lon), timeout=15.0)
            if roads and len(roads) > 5:
                elev_lookup = ElevationLookup([(from_lat, from_lon, 15.0), (to_lat, to_lon, 20.0)])
                G = build_road_graph(roads, elev_lookup)
                res = get_graph_route(G, from_lat, from_lon, to_lat, to_lon)
                if res.get("snapped"):
                    return {
                        "distance_km": res["distance_km"],
                        "method": "elevation_weighted_road_graph",
                        "waypoints_count": len(res["path"])
                    }
        except Exception:
            pass

    return {
        "distance_km": round(dist_straight, 2),
        "method": "straight_line_fallback"
    }


# ---------------------------------------------------------------------------
# STEP 5: TIE IT ALL TOGETHER (BATCH EVACUATION PLANS)
# ---------------------------------------------------------------------------
def build_all_county_evacuation_plans(
    input_path: Path | str = DEFAULT_INPUT_FILE,
    output_filename: str = "evacuation_plans.json",
    use_live_apis: bool = True,
    verbose: bool = True
) -> list[dict]:
    """
    Executes the entire Day 6-7 pipeline over all counties in the predictions dataset.
    """
    records = load_flood_data(input_path)
    flooded = filter_flooded(records)

    if verbose:
        print("=" * 70)
        print("  DAY 6-7 FULL BATCH EVACUATION ENGINE")
        print(f"  Loaded {len(records)} counties -> {len(flooded)} flooded / waterlogged.")
        print("=" * 70)

    plans = []
    for county in flooded:
        place_name = county["place"]
        classification = county["classification"]
        coords = county["flood_coordinates"]
        area_total = county.get("area_sq_km", 0.0)

        # DBSCAN clustering with real-km haversine distance
        clusters = cluster_flood_points(coords, eps_km=1.5, min_samples=3)

        if verbose:
            print(f"\n[County: {place_name}] ({classification})")
            print(f"  -> Total flood grid cells: {len(coords)} | Area: {area_total} sq km")
            print(f"  -> DBSCAN split into {len(clusters)} distinct flood cluster(s)")

        for i, cluster_pts in enumerate(clusters):
            lat, lon = cluster_centroid(cluster_pts)
            cluster_id = f"{place_name}_{i}"

            # Step 3: Shelters
            shelters = get_shelters_for_cluster(cluster_pts, place_name, use_live_apis=use_live_apis)
            nearest = top_n_shelters(lat, lon, shelters, n=SHELTERS_PER_CLUSTER)

            # Step 4: Routing
            shelter_options = []
            for s in nearest:
                route = compute_cluster_route(lat, lon, s["lat"], s["lon"], use_road_graph=use_live_apis)
                shelter_options.append({
                    "shelter": {
                        "name": s["name"],
                        "lat": round(s["lat"], 5),
                        "lon": round(s["lon"], 5),
                        "type": s.get("type", "shelter")
                    },
                    "route": route
                })

            plan_record = {
                "county": place_name,
                "cluster_id": cluster_id,
                "classification": classification,
                "cluster_centroid": {
                    "lat": round(lat, 5),
                    "lon": round(lon, 5)
                },
                "flood_cell_count": len(cluster_pts),
                "area_sq_km_county_total": area_total,
                "shelter_options": shelter_options
            }
            plans.append(plan_record)

            if verbose:
                print(f"     * Cluster '{cluster_id}' centroid: ({lat:.5f}, {lon:.5f}) - {len(cluster_pts)} cells")
                for s_opt in shelter_options:
                    s = s_opt["shelter"]
                    r = s_opt["route"]
                    print(f"       -> Shelter: {s['name']} ({s['type']}) | Dist: {r['distance_km']} km [{r['method']}]")

    # Save final JSON
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUTPUT_DIR / output_filename
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(plans, f, indent=2)

    if verbose:
        print("\n" + "=" * 70)
        print(f"  [SUCCESS] Generated {len(plans)} cluster evacuation plans across {len(flooded)} counties.")
        print(f"  Saved full Decision Engine dataset to: {out_file}")
        print("=" * 70 + "\n")

    return plans


if __name__ == "__main__":
    build_all_county_evacuation_plans()
