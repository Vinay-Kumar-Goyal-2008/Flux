"""
shelters/models.py
Data models for shelter candidates and evacuation plans.
"""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class ShelterCandidate(BaseModel):
    """A potential evacuation shelter."""
    name: str
    lat: float
    lng: float
    shelter_type: Literal["hospital", "fire_station", "school", "shelter", "assembly_point", "unknown"]
    straight_line_distance_m: float        # from flood polygon centroid
    elevation_m: float | None = None       # fetched from Mireye terrain if available
    source: Literal["mireye", "osm"]
    osm_id: str | None = None


class RouteResult(BaseModel):
    """A driving route from origin to a shelter."""
    origin_lat: float
    origin_lng: float
    dest_lat: float
    dest_lng: float
    distance_km: float
    duration_min: float
    waypoints: list[list[float]] = Field(default_factory=list)  # [[lat, lng], ...]
    road_source: str = "osrm"
    route_found: bool = True
    error: str | None = None


class RankedShelter(BaseModel):
    """A shelter with ranking score and route."""
    rank: int
    shelter: ShelterCandidate
    cost_score: float                     # lower = better
    route: RouteResult | None = None


class EvacuationPlan(BaseModel):
    """Full evacuation plan for one building cluster / polygon centroid."""
    cluster_id: str
    origin_lat: float
    origin_lng: float
    flood_avg_elevation_m: float | None = None
    total_candidates_found: int
    top_shelters: list[RankedShelter] = Field(default_factory=list)
    generated_at: str | None = None
