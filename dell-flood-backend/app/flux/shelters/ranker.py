"""
shelters/ranker.py
Rank shelter candidates using a cost function.

Cost function (lower = better):
  cost = distance_weight * distance_km
       + elevation_penalty  (shelter lower than flood zone = dangerous)
       + type_penalty        (hospital best, generic shelter worst)

Optionally enriches each shelter with elevation data from Mireye terrain preset.
"""
from __future__ import annotations

from api.client import MireyeClient, MireyeAPIError
from api.models import FloodPolygon
from shelters.models import ShelterCandidate, RankedShelter

# ── Weights ───────────────────────────────────────────────────────────────────
DISTANCE_WEIGHT = 1.0      # per km
ELEVATION_WEIGHT = 0.5     # penalty per metre below flood zone
TYPE_PRIORITY: dict[str, float] = {
    "hospital":         0.0,   # best — medical support
    "fire_station":     0.5,   # trained responders
    "assembly_point":   1.0,
    "school":           1.5,
    "shelter":          1.5,
    "unknown":          3.0,
}

MAX_DISTANCE_KM = 30.0     # ignore shelters further than this


# ── Elevation enrichment ──────────────────────────────────────────────────────

def _fetch_shelter_elevations(
    candidates: list[ShelterCandidate],
    verbose: bool = True,
) -> None:
    """
    Fetch elevation for each shelter candidate from Mireye terrain preset.
    Updates candidates in-place (mutates shelter.elevation_m).
    Batches up to 25 at a time.
    """
    to_fetch = [s for s in candidates if s.elevation_m is None]
    if not to_fetch:
        return

    if verbose:
        print(f"  [Ranker] Fetching elevation for {len(to_fetch)} shelters...")

    with MireyeClient(timeout=30.0) as client:
        # Process in batches of 25
        for i in range(0, len(to_fetch), 25):
            batch = to_fetch[i:i + 25]
            locs = [(s.lat, s.lng) for s in batch]
            try:
                results = client.fetch_batch(
                    locations=locs,
                    fields=["elevation"],
                    idempotency_key=f"shelter-elev-{i}-{len(batch)}"[:64],
                )
                for j, raw in enumerate(results):
                    if raw.get("ok", True) and "fields" in raw:
                        elev_field = raw["fields"].get("elevation", {})
                        val = elev_field.get("value")
                        if val is not None:
                            batch[j].elevation_m = float(val)
            except MireyeAPIError as e:
                if verbose:
                    print(f"  [Ranker] Elevation fetch failed: {e}")


# ── Cost function ─────────────────────────────────────────────────────────────

def _score(
    shelter: ShelterCandidate,
    flood_avg_elevation_m: float | None,
) -> float:
    """
    Calculate cost score for a shelter (lower = better).
    """
    dist_km = shelter.straight_line_distance_m / 1000.0

    # Distance component
    cost = DISTANCE_WEIGHT * dist_km

    # Elevation penalty: shelter should be HIGHER than flood zone
    if flood_avg_elevation_m is not None and shelter.elevation_m is not None:
        elev_diff = flood_avg_elevation_m - shelter.elevation_m
        if elev_diff > 0:
            # Shelter is LOWER than flood zone — bad
            cost += ELEVATION_WEIGHT * elev_diff
        # If shelter is higher, no penalty (bonus not needed; distance already rewards closer)

    # Type priority penalty
    cost += TYPE_PRIORITY.get(shelter.shelter_type, 3.0)

    return round(cost, 4)


# ── Public interface ───────────────────────────────────────────────────────────

def rank_shelters(
    candidates: list[ShelterCandidate],
    polygon: FloodPolygon | None = None,
    flood_avg_elevation_m: float | None = None,
    top_n: int = 5,
    enrich_elevation: bool = True,
    verbose: bool = True,
) -> list[RankedShelter]:
    """
    Rank shelter candidates and return top-N.

    Args:
        candidates: Raw shelter candidates from finder.
        polygon: Flood polygon (used to filter by distance).
        flood_avg_elevation_m: Average elevation of flood zone (metres).
        top_n: How many top shelters to return.
        enrich_elevation: Fetch shelter elevations from Mireye (costs credits).
        verbose: Print progress.

    Returns:
        List of RankedShelter sorted best-first.
    """
    # Filter to reasonable distance
    within_range = [
        c for c in candidates
        if c.straight_line_distance_m / 1000.0 <= MAX_DISTANCE_KM
    ]

    if not within_range:
        if verbose:
            print("  [Ranker] No candidates within range!")
        return []

    # Optionally enrich with elevation data
    if enrich_elevation:
        _fetch_shelter_elevations(within_range, verbose=verbose)

    # Score all
    scored = sorted(within_range, key=lambda s: _score(s, flood_avg_elevation_m))

    if verbose:
        print(f"\n  [Ranker] Top {min(top_n, len(scored))} shelters by cost score:")

    ranked: list[RankedShelter] = []
    for i, shelter in enumerate(scored[:top_n]):
        score = _score(shelter, flood_avg_elevation_m)
        ranked.append(RankedShelter(rank=i + 1, shelter=shelter, cost_score=score))
        if verbose:
            elev_str = f"{shelter.elevation_m:.1f}m" if shelter.elevation_m else "?"
            print(
                f"    #{i+1} {shelter.name} [{shelter.shelter_type}] "
                f"| dist={shelter.straight_line_distance_m/1000:.1f}km "
                f"| elev={elev_str} | score={score:.2f}"
            )

    return ranked
