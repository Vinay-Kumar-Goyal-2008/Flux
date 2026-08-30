"""
routing/osrm.py
Free OSRM public routing API wrapper.

OSRM (Open Source Routing Machine) uses OpenStreetMap road data.
Public demo server: router.project-osrm.org
  - No API key needed
  - Rate limit: ~1 req/sec (be polite)
  - Returns: distance, duration, GeoJSON route geometry

Endpoint used:
  GET /route/v1/driving/{lng,lat};{lng,lat}?overview=full&geometries=geojson
"""
from __future__ import annotations

import time
import httpx

from shelters.models import RouteResult

OSRM_BASE = "https://router.project-osrm.org"
OSRM_TIMEOUT = 20.0


def get_route(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    verbose: bool = False,
) -> RouteResult:
    """
    Get a driving route from origin to destination using OSRM.

    Args:
        origin_lat / origin_lng: Start point (flood zone / building cluster)
        dest_lat / dest_lng: Destination (shelter)
        verbose: Print debug info

    Returns:
        RouteResult with distance, duration, and waypoints list.
    """
    # OSRM coordinate format: lng,lat (note: longitude first!)
    coords = f"{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
    url = f"{OSRM_BASE}/route/v1/driving/{coords}"
    params = {
        "overview": "full",
        "geometries": "geojson",
        "steps": "false",
    }

    base = RouteResult(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
        distance_km=0.0,
        duration_min=0.0,
        route_found=False,
    )

    try:
        resp = httpx.get(
            url,
            params=params,
            timeout=OSRM_TIMEOUT,
            headers={"User-Agent": "Mireye-Disaster-Response/1.0"},
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            base.error = f"OSRM returned code: {data.get('code', 'unknown')}"
            return base

        route = data["routes"][0]
        distance_m = route["distance"]
        duration_s = route["duration"]

        # Extract waypoints from GeoJSON LineString
        # GeoJSON coordinates are [lng, lat] — flip to [lat, lng] for consistency
        coords_raw = route["geometry"]["coordinates"]
        waypoints = [[pt[1], pt[0]] for pt in coords_raw]  # flip lng,lat → lat,lng

        if verbose:
            print(f"    [OSRM] Route: {distance_m/1000:.1f} km, {duration_s/60:.0f} min, {len(waypoints)} waypoints")

        return RouteResult(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            dest_lat=dest_lat,
            dest_lng=dest_lng,
            distance_km=round(distance_m / 1000, 2),
            duration_min=round(duration_s / 60, 1),
            waypoints=waypoints,
            road_source="osrm",
            route_found=True,
        )

    except httpx.TimeoutException:
        base.error = "OSRM request timed out"
        return base
    except httpx.HTTPStatusError as e:
        base.error = f"OSRM HTTP {e.response.status_code}"
        return base
    except Exception as e:
        base.error = f"OSRM error: {e}"
        return base


def get_routes_batch(
    origin_lat: float,
    origin_lng: float,
    destinations: list[tuple[float, float]],
    delay_s: float = 0.8,
    verbose: bool = True,
) -> list[RouteResult]:
    """
    Get routes from one origin to multiple destinations sequentially.
    Adds a small delay between requests to respect OSRM rate limits.

    Args:
        origin_lat / origin_lng: The flood zone evacuation origin.
        destinations: List of (lat, lng) shelter locations.
        delay_s: Seconds to wait between requests (default 0.8s).
        verbose: Print progress.

    Returns:
        List of RouteResult, index-aligned with destinations.
    """
    results = []
    for i, (dlat, dlng) in enumerate(destinations):
        if verbose:
            print(f"  [OSRM] Routing to shelter {i+1}/{len(destinations)}...")
        route = get_route(origin_lat, origin_lng, dlat, dlng, verbose=verbose)
        results.append(route)
        if i < len(destinations) - 1:
            time.sleep(delay_s)
    return results
