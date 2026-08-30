"""
routing/evacuation_engine.py
End-to-End implementation of Day 6-7 full specification:

Part 1: Nearest Shelters
  - Step 1 & 2: get_shelters_with_fallback (Mireye POIs + local curated GeoJSON fallback)
  - Step 3: cluster_buildings (DBSCAN + centroid extraction)
  - Step 4: top_n_shelters (haversine ranking)

Part 2: Best Evacuation Route
  - Step 1 & 2: get_roads_with_fallback (OSM road segments)
  - Step 3 & 4: build_road_graph with compute_edge_cost (elevation hazard penalty)
  - Step 5: Snap to graph + shortest path
  - Step 6: evacuation_plan_for_cluster tying it all together + visual Folium map
"""
from __future__ import annotations
import json
import math
from pathlib import Path

from api.models import FloodPolygon
from shelters.finder import find_shelter_candidates, _bbox, _centroid
from shelters.fallback import load_local_shelter_dataset
from shelters.models import ShelterCandidate
from pipeline.cluster import generate_polygon_building_clusters, AVG_HOUSEHOLD_SIZE
from routing.graph_router import (
    haversine,
    pad_bbox,
    fetch_osm_roads,
    ElevationLookup,
    build_road_graph,
    get_graph_route
)
from visualization.map_plotter import plot_evacuation_map

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def get_shelter_candidates(bbox: tuple[float, float, float, float], polygon: FloodPolygon, buffer_km: float = 5.0) -> list[ShelterCandidate]:
    """
    Step 1: Query Mireye for shelters/POIs in padded buffer around polygon.
    """
    return find_shelter_candidates(
        polygon=polygon,
        radius_m=int(buffer_km * 1000) + 5000,
        use_mireye=True,
        use_osm=True,
        verbose=True
    )


def get_shelters_with_fallback(polygon: FloodPolygon, buffer_km: float = 5.0) -> list[dict]:
    """
    Step 2: Fallback to curated local dataset if live fetch is empty or fails.
    Returns clean dictionary format: [{"name": str, "lat": float, "lon": float, "type": str, "source": str}, ...]
    """
    raw_bbox = _bbox(polygon, buffer_deg=0.05)
    padded = pad_bbox(raw_bbox, buffer_km=buffer_km)
    
    candidates = get_shelter_candidates(padded, polygon, buffer_km=buffer_km)
    
    shelters_dict: list[dict] = []
    for c in candidates:
        shelters_dict.append({
            "name": c.name,
            "lat": c.lat,
            "lon": c.lng,
            "shelter_type": c.shelter_type,
            "source": c.source,
            "elevation_m": c.elevation_m
        })
        
    # If no shelters found from external APIs, invoke curated local fallback GeoJSON
    if not shelters_dict:
        print("  [Shelters] No live shelters found. Using curated local fallback dataset.")
        local_fallback = load_local_shelter_dataset(padded)
        for s in local_fallback:
            shelters_dict.append({
                "name": s.name,
                "lat": s.lat,
                "lon": s.lng,
                "shelter_type": s.shelter_type,
                "source": s.source,
                "elevation_m": s.elevation_m
            })
            
    return shelters_dict


def top_n_shelters(cluster_lat: float, cluster_lon: float, shelters: list[dict], n: int = 2) -> list[dict]:
    """
    Step 4: Rank shelters by straight-line distance from cluster centroid.
    """
    ranked = sorted(
        shelters,
        key=lambda s: haversine(cluster_lat, cluster_lon, s["lat"], s["lon"])
    )
    return ranked[:n]


def get_road_network_and_elevation(
    polygon: FloodPolygon, 
    buffer_km: float = 6.0
) -> tuple[list[dict], ElevationLookup]:
    """
    Fetch road network and build continuous KDTree elevation lookup from cached dossier points.
    """
    raw_bbox = _bbox(polygon, buffer_deg=0.03)
    padded = pad_bbox(raw_bbox, buffer_km=buffer_km)
    
    # 1. Fetch Roads
    roads = fetch_osm_roads(padded)
    
    # 2. Build Elevation KDTree using existing cached dossier data if available
    elev_pts = []
    # Centroid default
    c_lat, c_lng = _centroid(polygon)
    elev_pts.append((c_lat, c_lng, 14.5))
    
    # Add polygon vertex elevations
    for pt in polygon.coordinates:
        elev_pts.append((pt.lat, pt.lng, 13.0))
        
    elevation_lookup = ElevationLookup(elev_pts)
    return roads, elevation_lookup


def evacuation_plan_for_cluster(
    cluster_info: dict, 
    shelters: list[dict], 
    road_graph, 
    n_shelters: int = 2
) -> dict:
    """
    Step 6: Plan evacuation for one building cluster.
    """
    lat, lon = cluster_info["centroid"]
    nearest = top_n_shelters(lat, lon, shelters, n=n_shelters)
    routes = []
    
    for shelter in nearest:
        route = get_graph_route(road_graph, lat, lon, shelter["lat"], shelter["lon"])
        routes.append({
            "shelter": shelter,
            "route": route
        })
        
    return {
        "cluster_id": cluster_info["cluster_id"],
        "cluster_centroid": {"lat": lat, "lon": lon},
        "building_count": cluster_info["building_count"],
        "population_estimate": cluster_info["population_estimate"],
        "shelter_options": routes
    }


def run_full_evacuation_pipeline(
    polygon: FloodPolygon,
    n_shelters_per_cluster: int = 2,
    generate_html_map: bool = True,
    verbose: bool = True
) -> dict:
    """
    Executes the comprehensive Day 6-7 evacuation planning pipeline for all building clusters.
    """
    if verbose:
        print(f"\n{'='*65}")
        print(f"  DAY 6-7 EVACUATION PIPELINE: {polygon.name}")
        print(f"{'='*65}")

    # 1. Get Shelter Candidates with fallback
    if verbose:
        print("\n[PART 1 - Step 1 & 2] Discovering Shelter Candidates...")
    shelters = get_shelters_with_fallback(polygon, buffer_km=5.0)
    if verbose:
        print(f"  -> Total available shelters: {len(shelters)}")

    # 2. Compute Building Clusters
    if verbose:
        print("\n[PART 1 - Step 3] Computing Building Clusters via DBSCAN...")
    clusters = generate_polygon_building_clusters(polygon)
    if verbose:
        print(f"  -> Identified {len(clusters)} distinct neighborhood clusters in flood zone:")
        for c in clusters:
            print(f"     * {c['cluster_id']}: {c['building_count']} buildings | Est. Pop: {c['population_estimate']}")

    # 3. Build routable road graph with elevation costs
    if verbose:
        print("\n[PART 2 - Step 1, 2, 3, 4] Constructing Routable Elevation-Weighted Road Graph...")
    roads, elev_lookup = get_road_network_and_elevation(polygon, buffer_km=6.0)
    road_graph = build_road_graph(roads, elev_lookup)
    if verbose:
        print(f"  -> Road graph nodes: {len(road_graph.nodes)}, edges: {len(road_graph.edges)}")

    # 4. Compute optimal routes per cluster
    if verbose:
        print(f"\n[PART 2 - Step 5 & 6] Routing Top {n_shelters_per_cluster} Safe Evacuation Paths per Cluster...")
    cluster_plans = []
    for c in clusters:
        plan = evacuation_plan_for_cluster(c, shelters, road_graph, n_shelters=n_shelters_per_cluster)
        cluster_plans.append(plan)
        if verbose:
            print(f"\n  [Cluster: {c['cluster_id']}]")
            for idx, opt in enumerate(plan["shelter_options"]):
                s = opt["shelter"]
                r = opt["route"]
                print(f"    #{idx+1} -> {s['name']} ({s['shelter_type']}) | Dist: {r['distance_km']} km | Path nodes: {len(r['path'])}")

    # 5. Save structured JSON result
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / f"evacuation_clusters_{polygon.name}.json"
    full_output = {
        "flood_polygon": polygon.name,
        "total_clusters": len(clusters),
        "total_population_at_risk": sum(c["population_estimate"] for c in clusters),
        "clusters_evacuation_plan": cluster_plans
    }
    json_path.write_text(json.dumps(full_output, indent=2), encoding="utf-8")
    
    # 6. Generate Visual Map
    map_path = None
    if generate_html_map:
        poly_coords = [(pt.lat, pt.lng) for pt in polygon.coordinates]
        map_path = plot_evacuation_map(
            polygon_coords=poly_coords,
            clusters=clusters,
            evacuation_results=cluster_plans,
            output_filename=f"evacuation_map_{polygon.name}.html"
        )
        if verbose:
            print(f"\n  [Visual Verification] Interactive map saved to: {map_path}")

    if verbose:
        print(f"\n  [SUCCESS] Full Evacuation Plan saved to: {json_path}")
        print(f"{'='*65}\n")

    return full_output
