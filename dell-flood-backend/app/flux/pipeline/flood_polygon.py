"""
pipeline/flood_polygon.py
Demo flood polygons simulating what a flood segmentation model would output.

In production this module would:
  1. Receive the model's binary flood mask (image array)
  2. Convert flood pixels → geographic coordinates using the image's geo-transform
  3. Trace polygon contours (e.g. with OpenCV or rasterio)
  4. Return a list of lat/lng points forming the polygon

For Day 3–4 we use hardcoded real US flood zone polygons so we can test
the Mireye API integration end-to-end. Note: Mireye Earth is US-only.
"""
from __future__ import annotations

from api.models import FloodPolygon, LatLng


# ── Demo flood polygons ───────────────────────────────────────────────────────
# These represent historically flooded areas in the US.
# Coordinates are approximate bounding polygons of flood inundation zones.

DEMO_POLYGONS: dict[str, FloodPolygon] = {

    "houston_harvey": FloodPolygon(
        name="houston_harvey",
        coordinates=[
            # Hurricane Harvey 2017 — Houston, TX flood zone (simplified)
            LatLng(lat=29.7604, lng=-95.3698),
            LatLng(lat=29.7700, lng=-95.3500),
            LatLng(lat=29.7800, lng=-95.3600),
            LatLng(lat=29.7750, lng=-95.3900),
            LatLng(lat=29.7650, lng=-95.3950),
            LatLng(lat=29.7550, lng=-95.3800),
            LatLng(lat=29.7604, lng=-95.3698),  # close the ring
        ],
    ),

    "new_orleans_katrina": FloodPolygon(
        name="new_orleans_katrina",
        coordinates=[
            # Hurricane Katrina 2005 — Lower Ninth Ward, New Orleans, LA
            LatLng(lat=29.9697, lng=-90.0292),
            LatLng(lat=29.9750, lng=-90.0200),
            LatLng(lat=29.9800, lng=-90.0250),
            LatLng(lat=29.9780, lng=-90.0380),
            LatLng(lat=29.9710, lng=-90.0400),
            LatLng(lat=29.9660, lng=-90.0340),
            LatLng(lat=29.9697, lng=-90.0292),
        ],
    ),

    "baton_rouge_2016": FloodPolygon(
        name="baton_rouge_2016",
        coordinates=[
            # August 2016 Louisiana floods — Baton Rouge area
            LatLng(lat=30.4515, lng=-91.1871),
            LatLng(lat=30.4600, lng=-91.1750),
            LatLng(lat=30.4700, lng=-91.1800),
            LatLng(lat=30.4680, lng=-91.2000),
            LatLng(lat=30.4580, lng=-91.2050),
            LatLng(lat=30.4490, lng=-91.1980),
            LatLng(lat=30.4515, lng=-91.1871),
        ],
    ),
}


from pipeline.flood_data import load_all_flood_polygons

def get_demo_polygon(name: str = "houston_harvey") -> FloodPolygon:
    """
    Return a demo polygon by name.
    Checks DEMO_POLYGONS first, then the loaded model flood polygons.
    """
    if name in DEMO_POLYGONS:
        return DEMO_POLYGONS[name]
        
    model_polys = load_all_flood_polygons()
    if name in model_polys:
        return model_polys[name]

    # Try matching without prefix/suffix
    for k, v in model_polys.items():
        if name.lower() in k or k in name.lower():
            return v

    available = list(DEMO_POLYGONS.keys()) + list(model_polys.keys())
    raise ValueError(f"Unknown demo polygon '{name}'. Available: {available}")


def polygon_from_model_output(flood_mask_coords: list[tuple[float, float]], name: str = "model_output") -> FloodPolygon:
    """
    Convert raw (lat, lng) tuples from a segmentation model into a FloodPolygon.
    """
    coords = [LatLng(lat=lat, lng=lng) for lat, lng in flood_mask_coords]

    # Ensure the polygon ring is closed
    if coords and (coords[0].lat != coords[-1].lat or coords[0].lng != coords[-1].lng):
        coords.append(coords[0])

    return FloodPolygon(name=name, coordinates=coords)


def list_demo_polygons() -> list[str]:
    """Return names of all available demo and model polygons."""
    model_polys = load_all_flood_polygons()
    return list(DEMO_POLYGONS.keys()) + list(model_polys.keys())
