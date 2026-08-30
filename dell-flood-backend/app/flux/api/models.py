from pydantic import BaseModel, Field
from typing import List, Optional

class LatLng(BaseModel):
    lat: float
    lng: float

class FloodPolygon(BaseModel):
    place: str = ''
    coordinates: List[LatLng] = Field(default_factory=list)
