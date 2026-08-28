"""
pipeline/physical_data_hazard_engine.py
Day 8 & 9 Task Engine using physical_data.json as Direct Input.

Executes comprehensive Predictive Hydrology, Topographic Wetness Index (TWI),
and Flood Susceptibility Index (FSI) modeling on all 11 disaster regions
and 1,256 pre-extracted physical observation points in physical_data.json.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any
import numpy as np
import folium

# Base Paths
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

INPUT_PHYSICAL_DATA = ROOT_DIR / "physical_data.json"
OUTPUT_DIR = ROOT_DIR / "output"

RISK_COLOR_MAP = {
    "CRITICAL_RUNOFF_ZONE": {"color": "#311B92", "fill": "#D500F9", "opacity": 0.95, "radius": 12, "border": 3.0},
    "HIGH_SUSCEPTIBILITY": {"color": "#BF360C", "fill": "#FF6D00", "opacity": 0.90, "radius": 10, "border": 2.5},
    "MODERATE_WATCH": {"color": "#E65100", "fill": "#FFD600", "opacity": 0.85, "radius": 7, "border": 2.0},
    "LOW_RISK_HIGH_GROUND": {"color": "#1B5E20", "fill": "#00E676", "opacity": 0.70, "radius": 5, "border": 1.5},
}


def compute_point_twi_and_fsi(
    elevation: float,
    slope_deg: float,
    coast_dist_m: float,
    within_floodplain: bool,
    intersects_nhd: bool,
    building_sqm: float | None,
    avg_area_elevation: float,
    std_area_elevation: float
) -> tuple[float, float, str, list[str]]:
    """
    Computes TWI, FSI (0.0 to 1.0), and risk category for a single physical observation point.
    """
    notes = []
    
    # 1. Depression Deficit
    depression_deficit = max(0.0, avg_area_elevation - elevation)
    
    # 2. Contributing catchment area proxy (alpha)
    scale_factor = depression_deficit / max(1.0, std_area_elevation)
    coastal_factor = math.sqrt(10000.0 / max(500.0, min(10000.0, coast_dist_m)))
    eff_alpha = 150.0 * (1.0 + 2.5 * scale_factor) * coastal_factor
    
    # 3. Slope angle (beta)
    safe_slope = max(0.1, slope_deg)
    slope_rad = math.radians(safe_slope)
    tan_beta = max(0.001, math.tan(slope_rad))
    
    # 4. TWI = ln(alpha / tan(beta))
    twi_score = round(float(math.log(max(1.0, eff_alpha) / tan_beta)), 2)
    
    # 5. Multi-factor Flood Susceptibility Index (FSI)
    fsi_score = 0.0
    
    # TWI & Slope Contribution (up to 0.35)
    if twi_score >= 11.0 or safe_slope < 1.0:
        fsi_score += 0.35
        notes.append(f"Severe topographic wetness index (TWI={twi_score}) / flat pooling basin")
    elif twi_score >= 8.0 or safe_slope < 2.5:
        fsi_score += 0.22
        notes.append(f"Elevated wetness index (TWI={twi_score}) prone to runoff ponding")
    elif twi_score >= 6.0:
        fsi_score += 0.10
        
    # Elevation Depression Contribution (up to 0.25)
    if depression_deficit >= 15.0:
        fsi_score += 0.25
        notes.append(f"Deep topographic basin ({depression_deficit:.1f}m below regional mean)")
    elif depression_deficit > 3.0:
        fsi_score += 0.15
        notes.append(f"Localized depression ({depression_deficit:.1f}m below regional mean)")
    elif depression_deficit > 0.0:
        fsi_score += 0.08
        
    # FEMA Floodplain (0.20)
    if within_floodplain:
        fsi_score += 0.20
        notes.append("Inside FEMA regulatory 100/500-year floodplain")
        
    # USGS NHD Hydrography (0.10)
    if intersects_nhd:
        fsi_score += 0.10
        notes.append("Directly intersects USGS NHD active flowline / wetland area")
        
    # Coastal Proximity Risk (up to 0.10)
    if coast_dist_m < 5000.0:
        fsi_score += 0.10
        notes.append(f"High coastal surge vulnerability ({coast_dist_m/1000.0:.1f}km from coastline)")
    elif coast_dist_m < 20000.0:
        fsi_score += 0.05
        
    final_fsi = round(min(1.0, max(0.0, fsi_score)), 3)
    
    # Classification
    if final_fsi >= 0.70:
        category = "CRITICAL_RUNOFF_ZONE"
    elif final_fsi >= 0.45:
        category = "HIGH_SUSCEPTIBILITY"
    elif final_fsi >= 0.25:
        category = "MODERATE_WATCH"
    else:
        category = "LOW_RISK_HIGH_GROUND"
        if not notes:
            notes.append("Elevated well-drained positive slope terrain")
            
    return twi_score, final_fsi, category, notes


def extract_folium_polygons(poly_geom: dict[str, Any]) -> list[list[list[float]]]:
    """Returns a list of polygon rings, each being a list of [lat, lon] vertices."""
    gtype = poly_geom.get("type", "")
    coords = poly_geom.get("coordinates", [])
    polygons = []
    
    if gtype == "Polygon":
        for ring in coords:
            if ring and isinstance(ring[0], (list, tuple)):
                polygons.append([[p[1], p[0]] for p in ring if len(p) >= 2])
    elif gtype == "MultiPolygon":
        for poly in coords:
            if poly and isinstance(poly[0], (list, tuple)):
                if isinstance(poly[0][0], (list, tuple)):
                    for ring in poly:
                        polygons.append([[p[1], p[0]] for p in ring if len(p) >= 2])
                else:
                    # poly is directly a list of [lon, lat] points
                    polygons.append([[p[1], p[0]] for p in poly if len(p) >= 2])
    return polygons


def generate_tactical_hazard_map(
    region_data: dict[str, Any],
    analyzed_points: list[dict[str, Any]],
    output_path: Path
) -> None:
    """
    Renders clean, watermark-free high-contrast tactical Folium disaster map.
    """
    place_name = region_data.get("place", "Disaster Zone")
    centroid = region_data.get("event", {}).get("centroid", {})
    center_lat = centroid.get("latitude", 40.0)
    center_lon = centroid.get("longitude", -75.0)
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=14, tiles=None)
    
    # Basemaps
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Esri Light Gray Canvas",
        name="⚪ Clean Light Gray Canvas (Watermark-Free)",
        control=True,
        show=True
    ).add_to(m)
    
    folium.TileLayer(
        tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        attr="OpenStreetMap",
        name="🗺️ Standard Street Map",
        control=True,
        show=False
    ).add_to(m)
    
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri Satellite",
        name="🛰️ Satellite Imagery (Esri)",
        control=True,
        show=False
    ).add_to(m)
    
    # 1. Flood Inundation MultiPolygon
    poly_geom = region_data.get("event", {}).get("polygon", {})
    fg_poly = folium.FeatureGroup(name="🔴 Satellite Flood Inundation Polygon", show=True).add_to(m)
    
    for poly_pts in extract_folium_polygons(poly_geom):
        folium.Polygon(
            locations=poly_pts,
            color="#B71C1C",
            weight=3.5,
            dash_array="6, 5",
            fill=True,
            fill_color="#FF1744",
            fill_opacity=0.45,
            popup=f"<b>{place_name}</b><br>Classification: {region_data.get('classification')}<br>Area: {region_data.get('event', {}).get('flood_polygon_area_sq_km', 0):.2f} sq km"
        ).add_to(fg_poly)
            
    # 2. Predictive Hazard Points (TWI & FSI)
    fg_hazard = folium.FeatureGroup(name="⚠️ Predictive Flood-Prone Runoff Nodes (TWI)", show=True).add_to(m)
    for pt in analyzed_points:
        lat = pt["latitude"]
        lon = pt["longitude"]
        cat = pt["risk_category"]
        score = pt["susceptibility_score"]
        twi = pt["twi_score"]
        elev = pt["elevation_m"]
        slope = pt["slope_degrees"]
        fema = "YES" if pt["within_fema_floodplain"] else "No"
        nhd = "YES" if pt["intersects_nhd"] else "No"
        b_sqm = pt.get("building_footprint_sqm")
        b_sqm_str = f"{b_sqm:.0f} m²" if b_sqm is not None else "N/A"
        notes = "<br>• ".join(pt.get("threat_notes", []))
        
        style = RISK_COLOR_MAP.get(cat, RISK_COLOR_MAP["MODERATE_WATCH"])
        
        popup_html = f"""
        <div style="font-family: Arial, sans-serif; font-size: 12px; width: 260px; line-height: 1.4;">
            <div style="background:{style['fill']}; color:#fff; padding:6px 8px; border-radius:4px; font-weight:bold; font-size:13px; text-shadow:0 1px 2px #000;">
                {cat.replace('_', ' ')}
            </div>
            <div style="margin-top:6px;">
                <b>Susceptibility Score:</b> <span style="font-size:13px; font-weight:bold; color:#B71C1C;">{score:.3f}</span> / 1.000<br>
                <b>Topographic Wetness (TWI):</b> <b>{twi:.2f}</b><br>
                <b>DEM Elevation:</b> {elev:.1f} m | <b>Slope:</b> {slope:.1f}°<br>
                <b>FEMA Floodplain:</b> {fema} | <b>NHD Wetland:</b> {nhd}<br>
                <b>Building Footprint:</b> {b_sqm_str}<br>
                {f'<hr style="margin: 4px 0;"><span style="color:#C2185B; font-size:11px;">• {notes}</span>' if notes else ''}
            </div>
        </div>
        """
        
        folium.CircleMarker(
            location=[lat, lon],
            radius=style["radius"],
            color=style["color"],
            weight=style["border"],
            fill=True,
            fill_color=style["fill"],
            fill_opacity=style["opacity"],
            popup=popup_html,
            tooltip=f"{cat.replace('_', ' ')} (TWI: {twi:.1f} | Elev: {elev:.1f}m)"
        ).add_to(fg_hazard)
        
    # Floating HUD Legend
    legend_html = f"""
    <div style="position: fixed; bottom: 25px; left: 25px; width: 330px; z-index:9999;
                background-color: rgba(255, 255, 255, 0.96); border: 2px solid #263238;
                border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); font-family: Arial, sans-serif;">
        <div style="background:#263238; color:#fff; padding:8px 12px; font-weight:bold; font-size:13px;">
            🛡️ AEGIS DISASTER INTEL: {place_name}
        </div>
        <div style="padding:10px 12px; font-size:12px; line-height:1.5;">
            <div><span style="color:#D500F9; font-size:16px;">●</span> <b>Critical Runoff Zone</b> (TWI &gt; 11 / Flash Pooling)</div>
            <div><span style="color:#FF6D00; font-size:16px;">●</span> <b>High Susceptibility</b> (Watch-List Node)</div>
            <div><span style="color:#FFD600; font-size:16px;">●</span> <b>Moderate Watch</b> (Elevated Runoff)</div>
            <div><span style="color:#00E676; font-size:16px;">●</span> <b>Low Risk High Ground</b> (Well-Drained)</div>
            <div><span style="color:#FF1744; font-weight:bold;">---</span> <b>Active Flood Footprint</b> (Satellite SAR/Optical)</div>
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))
    folium.LayerControl(position="topright", collapsed=False).add_to(m)
    
    m.save(str(output_path))


def process_physical_data_pipeline(
    input_file: Path = INPUT_PHYSICAL_DATA
) -> dict[str, Any]:
    """
    Loads physical_data.json, runs Day 8 & 9 predictive modeling across all regions,
    and outputs datasets and maps.
    """
    if not input_file.exists():
        raise FileNotFoundError(f"Missing physical data file: {input_file}")
        
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    regions = data.get("regions", [])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*85}")
    print(f"  PROJECT AEGIS: DAY 8-9 PREDICTIVE TWI & HAZARD ENGINE (physical_data.json)")
    print(f"  Total Disaster Regions: {len(regions)}")
    print(f"  Total Enriched Observation Points: {data.get('global_summary', {}).get('total_query_points', 0)}")
    print(f"{'='*85}\n")
    
    all_region_reports: list[dict[str, Any]] = []
    total_critical_nodes = 0
    total_high_susceptibility_nodes = 0
    total_points_evaluated = 0
    
    for idx, reg in enumerate(regions, 1):
        place = reg.get("place", f"Region_{idx}")
        classification = reg.get("classification", "Flood Inundation")
        pts = reg.get("enriched_query_points", [])
        
        # Calculate regional elevation statistics
        elevs = [p.get("fields", {}).get("elevation", {}).get("value", 10.0) for p in pts if "fields" in p]
        avg_elev = float(np.mean(elevs)) if elevs else 10.0
        std_elev = float(np.std(elevs)) if elevs else 5.0
        min_elev = float(np.min(elevs)) if elevs else 0.0
        
        analyzed_points = []
        cat_counts = {
            "CRITICAL_RUNOFF_ZONE": 0,
            "HIGH_SUSCEPTIBILITY": 0,
            "MODERATE_WATCH": 0,
            "LOW_RISK_HIGH_GROUND": 0
        }
        
        twi_scores = []
        
        for p in pts:
            f = p.get("fields", {})
            elev = float(f.get("elevation", {}).get("value", avg_elev))
            slope = float(f.get("slope_degrees", {}).get("value", 1.5))
            coast_d = float(f.get("coast_distance_m", {}).get("value", 25000.0))
            fema = bool(f.get("within_floodplain_polygon", {}).get("value", False))
            nhd = bool(f.get("intersects_nhd_area", {}).get("value", False))
            b_sqm = f.get("primary_building_footprint_sqm", {}).get("value")
            b_height = f.get("primary_building_height_m", {}).get("value")
            
            twi, fsi, category, notes = compute_point_twi_and_fsi(
                elevation=elev,
                slope_deg=slope,
                coast_dist_m=coast_d,
                within_floodplain=fema,
                intersects_nhd=nhd,
                building_sqm=b_sqm,
                avg_area_elevation=avg_elev,
                std_area_elevation=std_elev
            )
            
            cat_counts[category] += 1
            twi_scores.append(twi)
            
            analyzed_points.append({
                "point_id": p.get("point_id"),
                "point_type": p.get("point_type"),
                "latitude": p.get("latitude"),
                "longitude": p.get("longitude"),
                "elevation_m": round(elev, 2),
                "slope_degrees": round(slope, 2),
                "coast_distance_m": round(coast_d, 1),
                "twi_score": twi,
                "susceptibility_score": fsi,
                "risk_category": category,
                "within_fema_floodplain": fema,
                "intersects_nhd": nhd,
                "building_footprint_sqm": round(b_sqm, 1) if b_sqm else None,
                "building_height_m": round(b_height, 1) if b_height else None,
                "threat_notes": notes
            })
            
        total_points_evaluated += len(analyzed_points)
        total_critical_nodes += cat_counts["CRITICAL_RUNOFF_ZONE"]
        total_high_susceptibility_nodes += cat_counts["HIGH_SUSCEPTIBILITY"]
        
        clean_name = place.replace(" ", "_").replace(",", "")
        
        # Build Region Summary
        region_summary = {
            "place": place,
            "classification": classification,
            "points_evaluated": len(analyzed_points),
            "average_elevation_m": round(avg_elev, 2),
            "min_elevation_m": round(min_elev, 2),
            "mean_twi": round(float(np.mean(twi_scores)), 2) if twi_scores else 0.0,
            "max_twi": round(float(np.max(twi_scores)), 2) if twi_scores else 0.0,
            "risk_category_breakdown": cat_counts,
            "population_proxy": reg.get("population", {}).get("estimated_population_proxy", 0),
            "total_building_footprint_sqm": reg.get("buildings", {}).get("estimated_building_footprint_sqm", 0),
            "analyzed_points": analyzed_points
        }
        
        all_region_reports.append(region_summary)
        
        # Save individual region JSON
        reg_json_path = OUTPUT_DIR / f"physical_data_hazard_{clean_name}.json"
        reg_json_path.write_text(json.dumps(region_summary, indent=2), encoding="utf-8")
        
        # Render tactical map
        map_out_path = OUTPUT_DIR / f"physical_data_map_{clean_name}.html"
        generate_tactical_hazard_map(
            region_data=reg,
            analyzed_points=analyzed_points,
            output_path=map_out_path
        )
        
        print(f"[{idx:02d}/11] {place:<36} | Points: {len(analyzed_points):<4} | "
              f"Mean TWI: {region_summary['mean_twi']:<5} | "
              f"Critical: {cat_counts['CRITICAL_RUNOFF_ZONE']:<3} | "
              f"High Watch: {cat_counts['HIGH_SUSCEPTIBILITY']:<3}")
              
    # Master Consolidated Report
    master_report = {
        "title": "Day 8-9 Full Physical Data Predictive TWI & Flood Hazard Dataset",
        "source_input": "physical_data.json",
        "total_regions": len(all_region_reports),
        "total_points_evaluated": total_points_evaluated,
        "total_critical_runoff_nodes": total_critical_nodes,
        "total_high_susceptibility_nodes": total_high_susceptibility_nodes,
        "regions": all_region_reports
    }
    
    master_output_path = OUTPUT_DIR / "physical_data_predictive_hazard.json"
    master_output_path.write_text(json.dumps(master_report, indent=2), encoding="utf-8")
    
    print(f"\n{'='*85}")
    print(f"  EXECUTION COMPLETED SUCCESSFULLY")
    print(f"{'='*85}")
    print(f"  Regions Analyzed                : {len(all_region_reports)}")
    print(f"  Total Ground Truth Points       : {total_points_evaluated}")
    print(f"  Critical Flash-Flood Nodes      : {total_critical_nodes}")
    print(f"  High Susceptibility Nodes       : {total_high_susceptibility_nodes}")
    print(f"  Master Report Saved To          : {master_output_path}")
    print(f"{'='*85}\n")
    
    return master_report


if __name__ == "__main__":
    process_physical_data_pipeline()
