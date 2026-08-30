"""
visualization/map_plotter.py
Generates an interactive Folium map visualizing:
1. Flood inundation polygon
2. Building clusters (centroids + pop estimates)
3. Top candidate shelters
4. Safe evacuation route paths with elevation cost annotations
"""
from __future__ import annotations
import folium
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def plot_evacuation_map(
    polygon_coords: list[tuple[float, float]],
    clusters: list[dict],
    evacuation_results: list[dict],
    output_filename: str = "evacuation_map.html"
) -> Path:
    """
    Generate an interactive HTML map for visual inspection and demos.
    """
    if not polygon_coords:
        return OUTPUT_DIR / output_filename
        
    center_lat = sum(p[0] for p in polygon_coords) / len(polygon_coords)
    center_lng = sum(p[1] for p in polygon_coords) / len(polygon_coords)
    
    m = folium.Map(location=[center_lat, center_lng], zoom_start=14, tiles="CartoDB positron")
    
    # 1. Plot Flood Polygon
    folium.Polygon(
        locations=polygon_coords,
        color="#D32F2F",
        weight=2,
        fill=True,
        fill_color="#FF5252",
        fill_opacity=0.35,
        popup="Flood Inundation Zone"
    ).add_to(m)
    
    # 2. Plot Building Clusters
    for cluster in clusters:
        c_lat, c_lng = cluster["centroid"]
        pop = cluster.get("population_estimate", "N/A")
        b_count = cluster.get("building_count", "N/A")
        
        folium.CircleMarker(
            location=[c_lat, c_lng],
            radius=8,
            color="#FF9800",
            fill=True,
            fill_color="#FFA726",
            fill_opacity=0.9,
            popup=f"<b>{cluster['cluster_id']}</b><br>Buildings: {b_count}<br>Est. Population: {pop}"
        ).add_to(m)
        
    # 3. Plot Shelters and Routes
    route_colors = ["#2E7D32", "#1565C0", "#6A1B9A", "#00838F"]
    plotted_shelters = set()
    
    for plan in evacuation_results:
        cluster_id = plan["cluster_id"]
        for idx, option in enumerate(plan.get("shelter_options", [])):
            shelter = option["shelter"]
            route = option.get("route", {})
            s_lat = shelter.get("lat")
            s_lng = shelter.get("lon", shelter.get("lng"))
            s_name = shelter.get("name", "Shelter")
            
            # Add shelter icon if not already plotted
            if s_name not in plotted_shelters:
                folium.Marker(
                    location=[s_lat, s_lng],
                    icon=folium.Icon(color="green", icon="home", prefix="fa"),
                    popup=f"<b>{s_name}</b><br>Type: {shelter.get('shelter_type')}<br>Source: {shelter.get('source')}"
                ).add_to(m)
                plotted_shelters.add(s_name)
                
            # Draw Route LineString
            path = route.get("path", [])
            if path and len(path) > 1:
                color = route_colors[idx % len(route_colors)]
                dist_km = route.get("distance_km", 0.0)
                folium.PolyLine(
                    locations=path,
                    color=color,
                    weight=4,
                    opacity=0.8,
                    dash_array="5, 5" if not route.get("snapped", True) else None,
                    tooltip=f"Route from {cluster_id} to {s_name} ({dist_km} km)"
                ).add_to(m)
                
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / output_filename
    m.save(str(out_path))
    return out_path
