"""
pipeline/flood_prone.py
Day 8 & 9: Areas Prone to Flooding & Forward-Looking Hazard Watch-List Generator.

Orchestrates:
  1. Dense spatial buffer grid generation around flood polygon / county bounding box.
  2. Batch physical query via Mireye Live API (fetching terrain & flood_risk presets).
  3. Continuous Topographic Wetness Index (TWI) & Flood Susceptibility Index (FSI) calculation.
  4. Corridor Hazard Intersect: Checks Day 6-7 evacuation routes against high-susceptibility zones.
  5. Structured JSON dataset & Watch-List generation.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root is in path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from api.client import MireyeClient, MireyeAPIError
from api.models import FloodPolygon, LatLng
from pipeline.predictive_twi import (
    PredictiveHazardCell,
    compute_twi,
    compute_flood_susceptibility
)
from shelters.finder import _bbox, _centroid

OUTPUT_DIR = ROOT_DIR / "output"


def generate_buffered_grid_points(
    polygon: FloodPolygon,
    buffer_km: float = 6.0,
    grid_dimension: int = 5  # 5x5 = 25 points, or 6x6 = 36 points
) -> list[tuple[float, float]]:
    """
    Generates a uniform dense rectangular grid covering the flood zone plus a buffer area.
    """
    lats = [p.lat for p in polygon.coordinates]
    lngs = [p.lng for p in polygon.coordinates]
    
    pad_deg = buffer_km / 111.0
    min_lat, max_lat = min(lats) - pad_deg, max(lats) + pad_deg
    min_lng, max_lng = min(lngs) - pad_deg, max(lngs) + pad_deg
    
    lat_step = (max_lat - min_lat) / max(1, grid_dimension - 1)
    lng_step = (max_lng - min_lng) / max(1, grid_dimension - 1)
    
    grid = []
    for i in range(grid_dimension):
        for j in range(grid_dimension):
            glat = round(min_lat + i * lat_step, 6)
            glon = round(min_lng + j * lng_step, 6)
            grid.append((glat, glon))
            
    return grid


def analyze_flood_prone_hazards(
    polygon: FloodPolygon,
    buffer_km: float = 6.0,
    grid_dimension: int = 5,
    use_live_api: bool = True,
    verbose: bool = True
) -> dict[str, Any]:
    """
    Executes dense Mireye physical extraction and computes forward-looking flood hazard models.
    """
    grid_points = generate_buffered_grid_points(polygon, buffer_km=buffer_km, grid_dimension=grid_dimension)
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"  DAY 8-9 PREDICTIVE HAZARD & FLOOD-PRONE ANALYSIS: {polygon.name}")
        print(f"  Generated {len(grid_points)} dense grid sampling locations (buffer: {buffer_km}km)")
        print(f"{'='*70}")

    fields_to_fetch = [
        # Terrain preset fields
        "elevation", "slope_degrees", "aspect_cardinal", "soil_drainage_class", "bedrock_depth_cm", "coast_distance_m",
        # Flood Risk preset fields
        "within_floodplain_polygon", "intersects_nhd_area", "nearest_waterbody_name",
        "nearest_wetland_distance_m", "wetlands_within_500m_count", "surface_water_permanence_pct"
    ]

    raw_results_map: dict[tuple[float, float], dict] = {}
    
    if use_live_api:
        if verbose:
            print(f"  [Mireye Live API] Querying {len(grid_points)} locations across 'terrain' & 'flood_risk' presets...")
        
        with MireyeClient(timeout=45.0) as client:
            # Process in batches of up to 25 (Mireye batch limit)
            for b_idx in range(0, len(grid_points), 25):
                batch = grid_points[b_idx:b_idx + 25]
                clean_id = f"prone_grid_{int(abs(batch[0][0])*10000)}_{b_idx}_{int(time.time()*10)%1000000}"[:64]
                try:
                    results = client.fetch_batch(
                        locations=batch,
                        fields=fields_to_fetch,
                        idempotency_key=clean_id
                    )
                    for pt, res in zip(batch, results):
                        if res.get("ok", True) and "fields" in res:
                            raw_results_map[pt] = res["fields"]
                except Exception as e:
                    if verbose:
                        print(f"  [Mireye Live API] Warning during batch {b_idx}: {e}")

    # Fallback / baseline values if API calls returned empty for any coordinates
    analyzed_cells: list[PredictiveHazardCell] = []
    
    # Calculate local reference elevation
    all_elevs = []
    for pt in grid_points:
        fields = raw_results_map.get(pt, {})
        elev_val = fields.get("elevation", {}).get("value")
        if elev_val is not None:
            all_elevs.append(float(elev_val))
            
    avg_area_elevation = sum(all_elevs) / len(all_elevs) if all_elevs else 12.0
    min_area_elevation = min(all_elevs) if all_elevs else (avg_area_elevation - 2.0)

    for pt in grid_points:
        fields = raw_results_map.get(pt, {})
        
        # Extract physical metrics
        elev_raw = fields.get("elevation", {}).get("value")
        elev = float(elev_raw) if elev_raw is not None else avg_area_elevation
        slope_raw = fields.get("slope_degrees", {}).get("value")
        slope = float(slope_raw) if slope_raw is not None else 1.5
        wetland_dist = fields.get("nearest_wetland_distance_m", {}).get("value")
        flowline_dist_m = float(wetland_dist) if wetland_dist is not None else 500.0
        
        fema_floodplain = bool(fields.get("within_floodplain_polygon", {}).get("value", False))
        nhd_waterbody = bool(fields.get("intersects_nhd_area", {}).get("value", False))
        soil_class = fields.get("soil_drainage_class", {}).get("value")
        bedrock = fields.get("bedrock_depth_cm", {}).get("value")
        bedrock_cm = float(bedrock) if bedrock is not None else None
        wetlands_cnt = int(fields.get("wetlands_within_500m_count", {}).get("value", 0))

        # Compute TWI & Susceptibility
        twi = compute_twi(slope, elev, min_area_elevation, nearest_flowline_dist_m=flowline_dist_m)
        fsi, category, notes = compute_flood_susceptibility(
            elevation_m=elev,
            slope_degrees=slope,
            twi_score=twi,
            within_fema_floodplain=fema_floodplain,
            intersects_nhd=nhd_waterbody,
            soil_drainage_class=soil_class,
            bedrock_depth_cm=bedrock_cm,
            wetlands_nearby=wetlands_cnt,
            avg_area_elevation_m=avg_area_elevation
        )

        analyzed_cells.append(PredictiveHazardCell(
            lat=pt[0],
            lon=pt[1],
            elevation_m=round(elev, 2),
            slope_degrees=round(slope, 2),
            twi_score=twi,
            within_fema_floodplain=fema_floodplain,
            intersects_nhd_waterbody=nhd_waterbody,
            soil_drainage_class=str(soil_class or "moderately_well_drained"),
            bedrock_depth_cm=bedrock_cm,
            wetlands_nearby_count=wetlands_cnt,
            susceptibility_score=fsi,
            risk_category=category,
            imminent_threat_notes=notes
        ))

    # Cross-check with Day 6-7 Evacuation Routes to identify compromised segments
    compromised_routes = check_evacuation_route_compromises(polygon.name, analyzed_cells)

    # Statistics & Watch-List Breakdown
    category_counts = {
        "CRITICAL_RUNOFF_ZONE": sum(1 for c in analyzed_cells if c.risk_category == "CRITICAL_RUNOFF_ZONE"),
        "HIGH_SUSCEPTIBILITY": sum(1 for c in analyzed_cells if c.risk_category == "HIGH_SUSCEPTIBILITY"),
        "MODERATE_WATCH": sum(1 for c in analyzed_cells if c.risk_category == "MODERATE_WATCH"),
        "LOW_RISK_HIGH_GROUND": sum(1 for c in analyzed_cells if c.risk_category == "LOW_RISK_HIGH_GROUND"),
    }

    if verbose:
        print(f"\n[Predictive Modeling Results]")
        print(f"  - Average Elevation: {avg_area_elevation:.2f} m (Min: {min_area_elevation:.2f} m)")
        print(f"  - Critical Runoff Zones : {category_counts['CRITICAL_RUNOFF_ZONE']} cells (IMMINENT SUBMERSION RISK)")
        print(f"  - High Susceptibility   : {category_counts['HIGH_SUSCEPTIBILITY']} cells (WATCH LIST)")
        print(f"  - Moderate Watch        : {category_counts['MODERATE_WATCH']} cells")
        print(f"  - Low Risk High Ground  : {category_counts['LOW_RISK_HIGH_GROUND']} cells")
        if compromised_routes:
            print(f"\n  [WARNING] Found {len(compromised_routes)} evacuation corridor(s) passing through critical runoff zones!")
            for cr in compromised_routes:
                print(f"    * Route '{cr['route_id']}' -> {cr['compromised_waypoints_count']} waypoint(s) at risk of flash flooding!")

    # Format output payload
    output_data = {
        "polygon_name": polygon.name,
        "grid_cells_evaluated": len(analyzed_cells),
        "buffer_radius_km": buffer_km,
        "average_elevation_m": round(avg_area_elevation, 2),
        "category_summary": category_counts,
        "compromised_evacuation_corridors": compromised_routes,
        "predictive_grid_cells": [c.model_dump() for c in analyzed_cells]
    }

    # Save to output file
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUTPUT_DIR / f"predictive_hazard_{polygon.name}.json"
    out_json.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    
    if verbose:
        print(f"\n  [SUCCESS] Saved predictive hazard model to: {out_json}")
        print(f"{'='*70}\n")

    return output_data


def check_evacuation_route_compromises(
    polygon_name: str, 
    hazard_cells: list[PredictiveHazardCell],
    threshold_distance_km: float = 0.8
) -> list[dict[str, Any]]:
    """
    Checks whether previously computed evacuation paths cross any CRITICAL_RUNOFF_ZONE or HIGH_SUSCEPTIBILITY cells.
    """
    plan_file = OUTPUT_DIR / f"evacuation_clusters_{polygon_name}.json"
    if not plan_file.exists():
        return []

    try:
        data = json.loads(plan_file.read_text(encoding="utf-8"))
    except Exception:
        return []

    critical_cells = [c for c in hazard_cells if c.risk_category in ("CRITICAL_RUNOFF_ZONE", "HIGH_SUSCEPTIBILITY")]
    if not critical_cells:
        return []

    compromised = []
    for plan in data.get("clusters_evacuation_plan", []):
        cid = plan.get("cluster_id", "cluster")
        for idx, opt in enumerate(plan.get("shelter_options", [])):
            shelter_name = opt.get("shelter", {}).get("name", f"Shelter {idx+1}")
            route = opt.get("route", {})
            path = route.get("path", [])
            
            threatened_pts = []
            for wp in path:
                # Check proximity to any critical hazard cell
                for hc in critical_cells:
                    dlat = (wp[0] - hc.lat) * 111.0
                    dlon = (wp[1] - hc.lon) * 111.0 * math.cos(math.radians(hc.lat))
                    dist = math.sqrt(dlat**2 + dlon**2)
                    if dist <= threshold_distance_km:
                        threatened_pts.append({
                            "lat": wp[0],
                            "lon": wp[1],
                            "hazard_category": hc.risk_category,
                            "twi_score": hc.twi_score,
                            "elevation_m": hc.elevation_m
                        })
                        break

            if len(threatened_pts) >= 2:
                compromised.append({
                    "cluster_id": cid,
                    "shelter_name": shelter_name,
                    "route_id": f"{cid}_to_{shelter_name.replace(' ', '_')}",
                    "compromised_waypoints_count": len(threatened_pts),
                    "compromise_ratio": round(len(threatened_pts) / max(1, len(path)), 2),
                    "highest_threat": threatened_pts[0]["hazard_category"],
                    "threat_sample_coords": threatened_pts[:3]
                })

    return compromised
