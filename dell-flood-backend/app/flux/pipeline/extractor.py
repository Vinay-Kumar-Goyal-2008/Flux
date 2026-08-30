"""
pipeline/extractor.py
Core pipeline: FloodPolygon → sample points → Mireye API → FloodDossier

Flow:
  1. Sample N representative lat/lng points inside the flood polygon
  2. Check local cache for each batch of points
  3. Call Mireye API /v1/fetch/batch for uncached batches
  4. Parse responses into PointDossier objects
  5. Aggregate into a FloodDossier with summary statistics
  6. Save structured JSON to output/
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

from api.cache import get as cache_get, set as cache_set, make_batch_cache_key, polygon_hash
from api.client import MireyeClient, MireyeAPIError, DISASTER_PRESETS
from api.models import (
    FloodPolygon,
    FloodDossier,
    PointDossier,
    FieldValue,
    DossierSummary,
)

OUTPUT_DIR = Path(__file__).parent.parent / "output"
BATCH_SIZE = 25  # Mireye batch endpoint max


# ── Point sampling ────────────────────────────────────────────────────────────

def _bbox(polygon: FloodPolygon) -> tuple[float, float, float, float]:
    """Return (min_lat, max_lat, min_lng, max_lng) bounding box."""
    lats = [pt.lat for pt in polygon.coordinates]
    lngs = [pt.lng for pt in polygon.coordinates]
    return min(lats), max(lats), min(lngs), max(lngs)


def _centroid(polygon: FloodPolygon) -> tuple[float, float]:
    """Return (lat, lng) centroid of the polygon."""
    lats = [pt.lat for pt in polygon.coordinates]
    lngs = [pt.lng for pt in polygon.coordinates]
    return sum(lats) / len(lats), sum(lngs) / len(lngs)


def sample_points(polygon: FloodPolygon, n_points: int = 10) -> list[tuple[float, float]]:
    """
    Sample representative lat/lng points from inside the flood polygon.

    Strategy:
    - Always include the centroid (most representative single point)
    - Add equally spaced grid points within the bounding box
    - Filter to only points reasonably inside the bbox

    Args:
        polygon: FloodPolygon to sample from
        n_points: Total number of sample points (capped at 25 for API batch)

    Returns:
        List of (lat, lng) tuples.
    """
    n_points = min(n_points, BATCH_SIZE)
    min_lat, max_lat, min_lng, max_lng = _bbox(polygon)
    centroid_lat, centroid_lng = _centroid(polygon)

    points: list[tuple[float, float]] = [(centroid_lat, centroid_lng)]

    if n_points == 1:
        return points

    # Grid sampling across the bbox
    remaining = n_points - 1
    grid_side = math.ceil(math.sqrt(remaining))
    lat_step = (max_lat - min_lat) / max(grid_side, 1)
    lng_step = (max_lng - min_lng) / max(grid_side, 1)

    for i in range(grid_side):
        for j in range(grid_side):
            lat = min_lat + (i + 0.5) * lat_step
            lng = min_lng + (j + 0.5) * lng_step
            pt = (round(lat, 6), round(lng, 6))
            if pt not in points:
                points.append(pt)
            if len(points) >= n_points:
                break
        if len(points) >= n_points:
            break

    return points[:n_points]


# ── Response parsing ──────────────────────────────────────────────────────────

def _parse_field_value(raw: dict) -> FieldValue:
    """Parse a single field entry from the Mireye API response."""
    return FieldValue(
        value=raw.get("value"),
        unit=raw.get("unit"),
        source=raw.get("source"),
        source_url=raw.get("source_url"),
        confidence=raw.get("confidence"),
        dataset_vintage=raw.get("dataset_vintage"),
        status=raw.get("status"),
    )


def _parse_point_result(lat: float, lng: float, raw: dict) -> PointDossier:
    """Convert a raw Mireye API response into a PointDossier."""
    if not raw.get("ok", True):
        return PointDossier(
            lat=lat,
            lng=lng,
            ok=False,
            error=str(raw.get("error", "unknown error")),
        )

    fields: dict[str, FieldValue] = {}
    raw_fields = raw.get("fields", {})
    for field_name, field_data in raw_fields.items():
        if isinstance(field_data, dict):
            fields[field_name] = _parse_field_value(field_data)
        else:
            # Scalar value — wrap it
            fields[field_name] = FieldValue(value=field_data)

    return PointDossier(lat=lat, lng=lng, fields=fields, ok=True)


# ── Summary aggregation ───────────────────────────────────────────────────────

def _build_summary(points: list[PointDossier]) -> DossierSummary:
    """Aggregate point-level data into a high-level summary."""
    ok_points = [p for p in points if p.ok]
    failed_points = [p for p in points if not p.ok]

    flood_zones: list[str] = []
    flood_factors: list[float] = []
    elevations: list[float] = []
    hazard_scores: list[float] = []
    hospitals: list[str] = []
    shelters: list[str] = []

    for pt in ok_points:
        # Flood risk fields
        if fz := pt.fields.get("flood_zone"):
            if fz.value and str(fz.value) not in flood_zones:
                flood_zones.append(str(fz.value))

        if ff := pt.fields.get("flood_factor"):
            try:
                flood_factors.append(float(ff.value))
            except (TypeError, ValueError):
                pass

        # Terrain
        for elev_field in ("elevation_ft", "elevation", "dem_elevation_ft"):
            if elev := pt.fields.get(elev_field):
                try:
                    elevations.append(float(elev.value))
                    break
                except (TypeError, ValueError):
                    pass

        # Hazard
        for hz_field in ("natural_hazard_score", "hazard_score", "composite_hazard_score"):
            if hz := pt.fields.get(hz_field):
                try:
                    hazard_scores.append(float(hz.value))
                    break
                except (TypeError, ValueError):
                    pass

        # POI — hospitals and shelters
        for poi_field in ("nearest_hospital", "hospital_name"):
            if h := pt.fields.get(poi_field):
                if h.value and str(h.value) not in hospitals:
                    hospitals.append(str(h.value))

        for shelter_field in ("nearest_shelter", "emergency_shelter"):
            if s := pt.fields.get(shelter_field):
                if s.value and str(s.value) not in shelters:
                    shelters.append(str(s.value))

    return DossierSummary(
        fema_flood_zones=list(set(flood_zones)),
        max_flood_factor=max(flood_factors) if flood_factors else None,
        avg_flood_factor=sum(flood_factors) / len(flood_factors) if flood_factors else None,
        avg_elevation_ft=sum(elevations) / len(elevations) if elevations else None,
        min_elevation_ft=min(elevations) if elevations else None,
        avg_hazard_score=sum(hazard_scores) / len(hazard_scores) if hazard_scores else None,
        building_count_estimate=None,  # Would come from building_lookup preset
        nearby_hospitals=hospitals[:5],
        nearby_shelters=shelters[:5],
        total_points_ok=len(ok_points),
        total_points_failed=len(failed_points),
    )


# ── Main extraction pipeline ──────────────────────────────────────────────────

def extract_flood_dossier(
    polygon: FloodPolygon,
    presets: list[str] | None = None,
    n_sample_points: int = 10,
    use_cache: bool = True,
    verbose: bool = True,
) -> FloodDossier:
    """
    Main pipeline: given a flood polygon, return a complete situational dossier.

    Args:
        polygon: FloodPolygon with lat/lng boundary coordinates
        presets: Mireye presets to fetch. Defaults to DISASTER_PRESETS.
        n_sample_points: How many points to sample inside the polygon (max 25).
        use_cache: Whether to check/write the local cache.
        verbose: Print progress to stdout.

    Returns:
        FloodDossier with structured situational data for the flood zone.
    """
    presets = presets or DISASTER_PRESETS
    p_hash = polygon_hash(polygon.coordinates)

    if verbose:
        print(f"\n{'='*60}")
        print(f"  Flood Dossier Extraction: {polygon.name}")
        print(f"  Polygon hash: {p_hash}")
        print(f"  Presets: {presets}")
        print(f"{'='*60}")

    # 1. Sample points from polygon
    sample_pts = sample_points(polygon, n_points=n_sample_points)
    if verbose:
        print(f"  [OK] Sampled {len(sample_pts)} points from polygon")

    all_point_dossiers: list[PointDossier] = []

    # 2. For each preset, fetch batch results
    with MireyeClient(timeout=45.0) as client:
        for preset in presets:
            if verbose:
                print(f"\n  --> Fetching preset: [{preset}] for {len(sample_pts)} points...")

            # Build cache key for this (locations, preset) combo
            cache_key = make_batch_cache_key(sample_pts, [preset])

            # 2a. Check cache
            if use_cache:
                cached = cache_get(cache_key)
                if cached:
                    if verbose:
                        print(f"    [CACHE] Cache hit - skipping API call")
                    raw_results = cached.get("results", [])
                    _merge_preset_results(all_point_dossiers, sample_pts, raw_results, preset)
                    continue

            # 2b. Call API in batches of 25
            try:
                # Check cost first (free, unmetered)
                if verbose:
                    quote = client.quote(preset=preset, num_locations=len(sample_pts))
                    cost = quote.get("total_credits", "?")
                    print(f"    [INFO] Estimated cost: {cost} credits")

                raw_results = client.fetch_batch(
                    locations=sample_pts,
                    preset=preset,
                    idempotency_key=f"mireye-{p_hash}-{preset}-{len(sample_pts)}"[:64],
                )

                # Store in cache
                if use_cache:
                    cache_set(cache_key, {"results": raw_results, "preset": preset})
                    if verbose:
                        print(f"    [OK] Cached {len(raw_results)} results")

                _merge_preset_results(all_point_dossiers, sample_pts, raw_results, preset)

            except MireyeAPIError as e:
                if verbose:
                    print(f"    [ERROR] API error [{preset}]: {e}")
                # Add failed entries for all points in this preset
                for lat, lng in sample_pts:
                    _ensure_point(all_point_dossiers, lat, lng).ok = False
                    _ensure_point(all_point_dossiers, lat, lng).error = str(e)

            time.sleep(0.2)  # Polite rate limit gap between preset calls

    # 3. Build summary
    summary = _build_summary(all_point_dossiers)

    # 4. Assemble dossier
    dossier = FloodDossier(
        polygon_name=polygon.name,
        polygon_hash=p_hash,
        sampled_points=len(sample_pts),
        presets_fetched=presets,
        points=all_point_dossiers,
        summary=summary,
        cached=False,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )

    # 5. Save to output/
    _save_dossier(dossier)

    if verbose:
        print(f"\n  [DONE] Dossier complete!")
        print(f"    Points OK:     {summary.total_points_ok}")
        print(f"    Points failed: {summary.total_points_failed}")
        if summary.fema_flood_zones:
            print(f"    FEMA zones:    {summary.fema_flood_zones}")
        if summary.avg_elevation_ft is not None:
            print(f"    Avg elevation: {summary.avg_elevation_ft:.1f} ft")
        print(f"    Saved to: output/flood_dossier_{p_hash}.json\n")

    return dossier


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_point(
    point_list: list[PointDossier], lat: float, lng: float
) -> PointDossier:
    """Find or create a PointDossier for a given coordinate."""
    for pt in point_list:
        if abs(pt.lat - lat) < 1e-7 and abs(pt.lng - lng) < 1e-7:
            return pt
    new_pt = PointDossier(lat=lat, lng=lng)
    point_list.append(new_pt)
    return new_pt


def _merge_preset_results(
    point_list: list[PointDossier],
    sample_pts: list[tuple[float, float]],
    raw_results: list[dict],
    preset: str,
) -> None:
    """Merge API results (index-aligned with sample_pts) into point_list."""
    for i, (lat, lng) in enumerate(sample_pts):
        pt = _ensure_point(point_list, lat, lng)
        if i >= len(raw_results):
            pt.ok = False
            pt.error = f"No result returned for index {i} [{preset}]"
            continue

        raw = raw_results[i]
        if not raw.get("ok", True):
            pt.ok = False
            pt.error = str(raw.get("error", f"failed [{preset}]"))
            continue

        # Merge fields from this preset into the point's fields dict
        for field_name, field_data in raw.get("fields", {}).items():
            if isinstance(field_data, dict):
                pt.fields[field_name] = _parse_field_value(field_data)
            else:
                pt.fields[field_name] = FieldValue(value=field_data)


def _save_dossier(dossier: FloodDossier) -> Path:
    """Save the dossier as JSON in the output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"flood_dossier_{dossier.polygon_hash}.json"
    out_path.write_text(
        json.dumps(dossier.model_dump(), indent=2, default=str),
        encoding="utf-8",
    )
    return out_path
