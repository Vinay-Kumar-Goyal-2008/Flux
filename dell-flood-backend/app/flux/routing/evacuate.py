"""
routing/evacuate.py
Main orchestrator for the evacuation planning pipeline.

Flow:
  1. Load flood polygon + existing dossier (from Day 3-4 run)
  2. Find shelter candidates (Mireye POI + OSM fallback)
  3. Rank shelters by cost function (distance + elevation + type)
  4. Get OSRM driving routes for top-2 shelters
  5. Return EvacuationPlan, save to output/
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from api.models import FloodPolygon
from api.cache import polygon_hash
from shelters.finder import find_shelter_candidates
from shelters.ranker import rank_shelters
from shelters.models import EvacuationPlan, RankedShelter
from routing.osrm import get_routes_batch

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _centroid(polygon: FloodPolygon) -> tuple[float, float]:
    lats = [p.lat for p in polygon.coordinates]
    lngs = [p.lng for p in polygon.coordinates]
    return sum(lats) / len(lats), sum(lngs) / len(lngs)


def _load_cached_elevation(polygon: FloodPolygon) -> float | None:
    """
    Try to read average elevation from an existing dossier JSON (Day 3-4 output).
    Returns elevation in metres, or None if not found.
    """
    p_hash = polygon_hash(polygon.coordinates)
    dossier_path = OUTPUT_DIR / f"flood_dossier_{p_hash}.json"
    if not dossier_path.exists():
        return None
    try:
        data = json.loads(dossier_path.read_text(encoding="utf-8"))
        summary = data.get("summary", {})
        # avg_elevation_ft from dossier → convert to metres
        elev_ft = summary.get("avg_elevation_ft")
        if elev_ft is not None:
            return float(elev_ft) * 0.3048  # ft to metres
    except Exception:
        pass
    return None


def plan_evacuation(
    polygon: FloodPolygon,
    top_n: int = 2,
    radius_m: int = 15000,
    enrich_elevation: bool = True,
    verbose: bool = True,
) -> EvacuationPlan:
    """
    Full evacuation planning pipeline for a flood polygon.

    Args:
        polygon: The flood polygon from your model / demo set.
        top_n: Number of top shelters to return (default 2).
        radius_m: Search radius for OSM shelter lookup (metres).
        enrich_elevation: Fetch shelter elevations from Mireye for better ranking.
        verbose: Print step-by-step progress.

    Returns:
        EvacuationPlan with top-N shelters and driving routes.
    """
    centroid_lat, centroid_lng = _centroid(polygon)
    flood_elev_m = _load_cached_elevation(polygon)

    if verbose:
        print(f"\n{'='*60}")
        print(f"  EVACUATION PLANNER: {polygon.name}")
        print(f"  Origin (centroid): {centroid_lat:.5f}, {centroid_lng:.5f}")
        if flood_elev_m is not None:
            print(f"  Flood zone elevation: {flood_elev_m:.1f} m")
        print(f"  Looking for top-{top_n} shelters within {radius_m/1000:.0f} km")
        print(f"{'='*60}")

    # ── Step 1: Find candidates ───────────────────────────────────────────────
    candidates = find_shelter_candidates(
        polygon=polygon,
        radius_m=radius_m,
        use_mireye=True,
        use_osm=True,
        verbose=verbose,
    )

    if not candidates:
        if verbose:
            print("  [!] No shelter candidates found. Try increasing radius_m.")
        return EvacuationPlan(
            cluster_id=polygon.name,
            origin_lat=centroid_lat,
            origin_lng=centroid_lng,
            flood_avg_elevation_m=flood_elev_m,
            total_candidates_found=0,
            top_shelters=[],
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    # ── Step 2: Rank ─────────────────────────────────────────────────────────
    ranked = rank_shelters(
        candidates=candidates,
        polygon=polygon,
        flood_avg_elevation_m=flood_elev_m,
        top_n=top_n,
        enrich_elevation=enrich_elevation,
        verbose=verbose,
    )

    # ── Step 3: Get OSRM routes for top shelters ──────────────────────────────
    if ranked:
        if verbose:
            print(f"\n  [OSRM] Getting driving routes for top {len(ranked)} shelters...")

        destinations = [(rs.shelter.lat, rs.shelter.lng) for rs in ranked]
        routes = get_routes_batch(
            origin_lat=centroid_lat,
            origin_lng=centroid_lng,
            destinations=destinations,
            verbose=verbose,
        )

        for i, rs in enumerate(ranked):
            if i < len(routes):
                rs.route = routes[i]
                if verbose and routes[i].route_found:
                    print(
                        f"    #{rs.rank} {rs.shelter.name}: "
                        f"{routes[i].distance_km} km, "
                        f"{routes[i].duration_min} min drive"
                    )

    # ── Step 4: Assemble plan ─────────────────────────────────────────────────
    plan = EvacuationPlan(
        cluster_id=polygon.name,
        origin_lat=centroid_lat,
        origin_lng=centroid_lng,
        flood_avg_elevation_m=flood_elev_m,
        total_candidates_found=len(candidates),
        top_shelters=ranked,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    # ── Step 5: Save ──────────────────────────────────────────────────────────
    _save_plan(plan, polygon.name)

    if verbose:
        print(f"\n  [DONE] Evacuation plan saved!")
        print(f"    Candidates found: {len(candidates)}")
        print(f"    Top shelters:     {len(ranked)}")
        for rs in ranked:
            route_str = (
                f"{rs.route.distance_km} km / {rs.route.duration_min} min"
                if rs.route and rs.route.route_found
                else "route unavailable"
            )
            print(f"      #{rs.rank}: {rs.shelter.name} "
                  f"[{rs.shelter.shelter_type}] — {route_str}")
        print(f"    File: output/evacuation_{polygon.name}.json\n")

    return plan


def _save_plan(plan: EvacuationPlan, name: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"evacuation_{name}.json"
    path.write_text(
        json.dumps(plan.model_dump(), indent=2, default=str),
        encoding="utf-8",
    )
    return path
