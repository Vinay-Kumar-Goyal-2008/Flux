"""
pipeline/batch_predictive_hazard.py
Day 8 & 9: Complete Multi-County Batch Run for Predictive Hazard & TWI Modeling.

Runs full-scale physical hazard modeling across all flooded counties:
  1. Dense sampling grid per county (buffer 6.0 km).
  2. Live Mireye physical extraction across terrain and flood_risk presets.
  3. Topographic Wetness Index (TWI) & Flood Susceptibility Index (FSI) scoring.
  4. Day 6-7 Evacuation Route Compromise Analysis.
  5. Aggregated multi-county JSON dataset export.
  6. Interactive Folium disaster maps with predictive hazard overlays.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

# Ensure project root is in path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from api.models import FloodPolygon, LatLng
from pipeline.flood_prone import analyze_flood_prone_hazards
from visualization.map_plotter import plot_evacuation_map

OUTPUT_DIR = ROOT_DIR / "output"
DATA_DIR = ROOT_DIR / "data"
POLYGONS_FILE = DATA_DIR / "model_flood_polygons.json"


def load_all_flood_polygons() -> list[FloodPolygon]:
    """Loads all flood polygons from the benchmark dataset."""
    if not POLYGONS_FILE.exists():
        raise FileNotFoundError(f"Missing polygons file: {POLYGONS_FILE}")

    with open(POLYGONS_FILE, "r", encoding="utf-8") as f:
        raw_list = json.load(f)

    polygons = []
    for item in raw_list:
        place_name = item.get("place", "Unknown")
        coords = [LatLng(lat=c[1], lng=c[0]) for c in item.get("flood_coordinates", [])]
        if coords:
            polygons.append(FloodPolygon(
                name=place_name,
                coordinates=coords,
                confidence_score=0.92
            ))
    return polygons


def run_all_counties(
    grid_dimension: int = 5,
    buffer_km: float = 6.0,
    use_live_api: bool = True
) -> dict[str, Any]:
    """
    Executes Day 8 & 9 predictive flood-prone modeling across all counties.
    """
    polygons = load_all_flood_polygons()
    print(f"\n{'#'*80}")
    print(f"  AEGIS DISASTER INTELLIGENCE: DAY 8-9 MULTI-COUNTY HAZARD SUITE")
    print(f"  Total Disaster Zones to Analyze: {len(polygons)}")
    print(f"  Grid Density per County: {grid_dimension}x{grid_dimension} ({grid_dimension**2} sampling points)")
    print(f"  Live Mireye API: {'ENABLED (Direct Batch Querying)' if use_live_api else 'OFFLINE SYNTHETIC'}")
    print(f"{'#'*80}\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    all_county_summaries: list[dict[str, Any]] = []
    total_grid_points = 0
    total_critical_cells = 0
    total_compromised_corridors = 0

    start_time = time.time()

    for idx, poly in enumerate(polygons, 1):
        print(f"\n--- [{idx}/{len(polygons)}] Processing {poly.name} ---")
        try:
            result = analyze_flood_prone_hazards(
                polygon=poly,
                buffer_km=buffer_km,
                grid_dimension=grid_dimension,
                use_live_api=use_live_api,
                verbose=True
            )
            all_county_summaries.append(result)

            total_grid_points += result.get("grid_cells_evaluated", 0)
            cat_sum = result.get("category_summary", {})
            total_critical_cells += cat_sum.get("CRITICAL_RUNOFF_ZONE", 0)
            comp_routes = result.get("compromised_evacuation_corridors", [])
            total_compromised_corridors += len(comp_routes)

            # Generate interactive map
            poly_coords = [(p.lat, p.lng) for p in poly.coordinates]
            clusters = []
            evac_results = []
            
            plan_file = OUTPUT_DIR / f"evacuation_clusters_{poly.name}.json"
            if plan_file.exists():
                try:
                    plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
                    evac_results = plan_data.get("clusters_evacuation_plan", [])
                    for res in evac_results:
                        clusters.append({
                            "cluster_id": res.get("cluster_id"),
                            "centroid": [res.get("cluster_centroid", {}).get("lat", 0.0), res.get("cluster_centroid", {}).get("lon", 0.0)],
                            "population_estimate": res.get("population_estimate"),
                            "building_count": res.get("building_count")
                        })
                except Exception as ex:
                    print(f"  [DEBUG] Notice parsing clusters: {ex}")

            clean_name = poly.name.replace(" ", "_").replace(",", "")
            map_path = plot_evacuation_map(
                polygon_coords=poly_coords,
                clusters=clusters,
                evacuation_results=evac_results,
                hazard_cells=result.get("predictive_grid_cells", []),
                output_filename=f"predictive_hazard_map_{clean_name}.html"
            )
            print(f"  [MAP] Generated full tactical Folium map: {map_path}")

        except Exception as e:
            print(f"  [ERROR] Failed processing {poly.name}: {e}")

    elapsed = time.time() - start_time

    # Aggregate master output
    master_report = {
        "suite": "Day 8-9 Areas Prone to Flooding & TWI Predictive Watch-List",
        "total_counties_evaluated": len(all_county_summaries),
        "total_spatial_cells_analyzed": total_grid_points,
        "total_critical_runoff_cells": total_critical_cells,
        "total_compromised_evacuation_routes": total_compromised_corridors,
        "execution_time_seconds": round(elapsed, 2),
        "county_reports": all_county_summaries
    }

    master_path = OUTPUT_DIR / "all_counties_predictive_hazard.json"
    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(master_report, f, indent=2)

    print(f"\n{'='*80}")
    print(f"  DAY 8-9 BATCH EXECUTION COMPLETED")
    print(f"{'='*80}")
    print(f"  Counties Processed          : {len(all_county_summaries)}")
    print(f"  Total Sampling Points       : {total_grid_points}")
    print(f"  Critical Flash Flood Cells  : {total_critical_cells}")
    print(f"  Compromised Evac Corridors  : {total_compromised_corridors}")
    print(f"  Total Run Time              : {elapsed:.2f}s")
    print(f"  Master Report Saved To      : {master_path}")
    print(f"{'='*80}\n")

    return master_report


if __name__ == "__main__":
    run_all_counties(grid_dimension=5, buffer_km=6.0, use_live_api=True)
