"""
routing/graph_router.py
Part 2: Routable Road Network Graph & Elevation-Aware Pathfinding.

Supports:
1. Fetching local road network from OSM / Overpass or OSMnx
2. Mapping elevation from Mireye using KDTree nearest-neighbor lookup
3. Building NetworkX graph with edge costs penalizing low-elevation / flood-prone roads
4. Snapping cluster & shelter coordinates to nearest graph nodes
5. Computing shortest-paths with cost and distance metrics
"""
from __future__ import annotations
import math
import httpx
import networkx as nx
import numpy as np
from scipy.spatial import KDTree

from api.models import FloodPolygon
from api.cache import get as cache_get, set as cache_set

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
MIN_EXPECTED_SEGMENTS = 10


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in kilometers."""
    R = 6371.0  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def pad_bbox(bbox: tuple[float, float, float, float], buffer_km: float = 3.0) -> tuple[float, float, float, float]:
    """
    Pad (min_lat, min_lon, max_lat, max_lon) by buffer_km.
    1 deg latitude ~ 111 km, 1 deg longitude ~ 111 * cos(lat) km.
    """
    min_lat, min_lon, max_lat, max_lon = bbox
    avg_lat = (min_lat + max_lat) / 2.0
    lat_deg = buffer_km / 111.0
    lon_deg = buffer_km / (111.0 * max(0.1, math.cos(math.radians(avg_lat))))
    return (
        min_lat - lat_deg,
        min_lon - lon_deg,
        max_lat + lat_deg,
        max_lon + lon_deg,
    )


def fetch_osm_roads(bbox: tuple[float, float, float, float], timeout: float = 30.0) -> list[dict]:
    """
    Fetch drivable road ways and coordinates within bbox from Overpass API.
    Cached locally to avoid repeated requests.
    """
    min_lat, min_lon, max_lat, max_lon = bbox
    cache_key = f"osm_roads_{min_lat:.3f}_{min_lon:.3f}_{max_lat:.3f}_{max_lon:.3f}"
    
    cached = cache_get(cache_key)
    if cached and "roads" in cached:
        return cached["roads"]
        
    query = f"""
[out:json][timeout:{int(timeout)}];
(
  way["highway"~"motorway|trunk|primary|secondary|tertiary|residential|unclassified"]({min_lat},{min_lon},{max_lat},{max_lon});
);
out body;
>;
out skel qt;
"""
    try:
        resp = httpx.post(
            OVERPASS_URL,
            data={"data": query},
            timeout=timeout,
            headers={"User-Agent": "Mireye-Disaster-Route/1.0"}
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [Router] Overpass fetch road graph failed ({e}). Generating local connector grid.")
        return []

    # Map node id -> (lat, lon)
    nodes = {}
    for el in data.get("elements", []):
        if el["type"] == "node":
            nodes[el["id"]] = (el["lat"], el["lon"])
            
    roads = []
    for el in data.get("elements", []):
        if el["type"] == "way":
            way_nodes = el.get("nodes", [])
            coords = [nodes[nid] for nid in way_nodes if nid in nodes]
            if len(coords) >= 2:
                roads.append({
                    "id": el["id"],
                    "highway": el.get("tags", {}).get("highway", "residential"),
                    "name": el.get("tags", {}).get("name", "Road"),
                    "coords": coords
                })
                
    if roads:
        cache_set(cache_key, {"roads": roads})
        
    return roads


class ElevationLookup:
    """
    Nearest-Neighbor continuous elevation lookup using scipy KDTree.
    Uses sample elevation points from Mireye or defaults.
    """
    def __init__(self, elevation_points: list[tuple[float, float, float]] | None = None):
        """
        elevation_points: list of (lat, lon, elevation_meters)
        """
        if elevation_points and len(elevation_points) > 0:
            coords = np.array([[pt[0], pt[1]] for pt in elevation_points])
            self.elevations = [pt[2] for pt in elevation_points]
            self.kdtree = KDTree(coords)
        else:
            self.kdtree = None
            self.elevations = []
            
    def get(self, lat: float, lon: float, default_elev: float = 12.0) -> float:
        if self.kdtree is None or len(self.elevations) == 0:
            return default_elev
        dist, idx = self.kdtree.query([lat, lon])
        return float(self.elevations[idx])


def compute_edge_cost(distance_km: float, elev_a: float, elev_b: float, flood_threshold_m: float = 5.0) -> float:
    """
    Step 4: Basic cost function.
    Prefer higher ground: penalize low elevation as a proxy for flood risk.
    """
    avg_elev = (elev_a + elev_b) / 2.0
    elevation_penalty = max(0.0, (flood_threshold_m - avg_elev)) * 0.2
    return float(distance_km + elevation_penalty)


def build_road_graph(
    roads: list[dict], 
    elevation_lookup: ElevationLookup
) -> nx.Graph:
    """
    Step 3: Convert roads list to NetworkX Graph with weighted edges.
    """
    G = nx.Graph()
    for segment in roads:
        coords = segment["coords"]
        for i in range(len(coords) - 1):
            a = (round(coords[i][0], 6), round(coords[i][1], 6))
            b = (round(coords[i+1][0], 6), round(coords[i+1][1], 6))
            dist = haversine(a[0], a[1], b[0], b[1])
            elev_a = elevation_lookup.get(a[0], a[1])
            elev_b = elevation_lookup.get(b[0], b[1])
            cost = compute_edge_cost(dist, elev_a, elev_b)
            G.add_edge(a, b, weight=cost, distance=dist)
    return G


def nearest_node(G: nx.Graph, lat: float, lon: float) -> tuple[float, float]:
    """Snap coordinate to nearest node on the graph."""
    return min(G.nodes, key=lambda n: haversine(lat, lon, n[0], n[1]))


def get_graph_route(
    G: nx.Graph, 
    from_lat: float, 
    from_lon: float, 
    to_lat: float, 
    to_lon: float
) -> dict:
    """
    Step 5: Snap start & end nodes onto graph, compute shortest path.
    """
    if len(G.nodes) == 0:
        dist = haversine(from_lat, from_lon, to_lat, to_lon)
        return {
            "path": [[from_lat, from_lon], [to_lat, to_lon]],
            "distance_km": round(dist, 2),
            "snapped": False
        }
        
    start = nearest_node(G, from_lat, from_lon)
    end = nearest_node(G, to_lat, to_lon)
    
    try:
        path = nx.shortest_path(G, start, end, weight="weight")
        total_dist = sum(
            G[path[i]][path[i+1]]["distance"] for i in range(len(path) - 1)
        )
        return {
            "path": [[p[0], p[1]] for p in path],
            "distance_km": round(total_dist, 2),
            "snapped": True
        }
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        # Fallback straight path if disconnected component
        dist = haversine(from_lat, from_lon, to_lat, to_lon)
        return {
            "path": [[from_lat, from_lon], [to_lat, to_lon]],
            "distance_km": round(dist, 2),
            "snapped": False
        }
