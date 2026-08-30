import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import time
import base64
import math
import random

app = FastAPI(
    title="Lightweight Mock Backend - Flood Detection & Response",
    description="Minimal endpoint server using zero heavy dependencies for instant mobile client testing."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-Memory stores
CROWD_REPORTS = []
ACTIVE_ALERTS = {}
AGENT_TRACES = {}

class CrowdReportRequest(BaseModel):
    lat: float
    lon: float
    severity: str
    description: str
    phone: str = ""

class AgentCycleRequest(BaseModel):
    location: str
    lat: float
    lon: float
    phones: list = []

# Distance calculator using pure math
def calculate_distance(lat1, lon1, lat2, lon2):
    x = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2.0)) * 111.32
    y = (lat2 - lat1) * 110.57
    return math.sqrt(x*x + y*y)

@app.get("/")
def read_root():
    return {"status": "ONLINE", "mode": "LIGHTWEIGHT_MOCK_SERVER"}

@app.get("/api/preview")
def get_satellite_preview(lat: float, lon: float):
    # Standard base64 blue/green pixel representation
    mock_pixel = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    return {
        "image": mock_pixel,
        "lat": lat,
        "lon": lon,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

@app.post("/api/run-detection")
def run_detection(lat: float, lon: float, cloud_cover: float = 10.0):
    rainfall_5day = 0.0
    try:
        import requests
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=precipitation_sum&past_days=5&forecast_days=1&timezone=auto"
        res = requests.get(url, timeout=2.5)
        if res.status_code == 200:
            precip_list = res.json().get("daily", {}).get("precipitation_sum", [])
            rainfall_5day = sum(p for p in precip_list if p is not None)
    except Exception:
        pass

    is_delhi_rajasthan = (24.0 <= lat <= 29.0 and 70.0 <= lon <= 77.5)
    is_assam = (24.0 <= lat <= 28.5 and 89.5 <= lon <= 96.5)
    is_bihar = (24.5 <= lat <= 27.5 and 83.5 <= lon <= 88.5)

    if (is_delhi_rajasthan and rainfall_5day < 45.0) or rainfall_5day < 35.0:
        return {
            "confidence_score": 0.0,
            "classification": "Normal Conditions / Dry Ground",
            "area_sq_km": 0.0,
            "severity": "NONE",
            "severity_score": 0,
            "impact": { "population": 0, "buildings": 0, "facilities": 0 },
            "mask_geojson": { "type": "FeatureCollection", "features": [] }
        }

    rain_excess = max(0.0, rainfall_5day - 35.0)
    area = round(min(8.5, max(0.4, (rain_excess / 40.0) * 2.5 + (0.5 if is_assam else 0.0))), 2)
    conf = round(75.0 + min(22.0, rain_excess / 2.0), 1)
    
    pop = int(area * 1200)
    bld = int(area * 40)
    fac = max(1, int(area * 0.5))
    
    score = min(1.0, (pop / 10000 * 0.4) + (bld / 1000 * 0.3) + (fac / 5 * 0.2) + (area / 10 * 0.1))
    
    if score >= 0.7 or area >= 3.0:
        severity = "CRITICAL"
    elif score >= 0.4 or area >= 1.5:
        severity = "HIGH"
    elif score >= 0.2:
        severity = "MODERATE"
    else:
        severity = "LOW"
        
    mask_geojson = {
        "type": "FeatureCollection",
        "features": [{
          "type": "Feature",
          "properties": { "severity": severity, "area_sq_km": area },
          "geometry": {
            "type": "Polygon",
            "coordinates": [[
              [lon - 0.015, lat - 0.015],
              [lon + 0.015, lat - 0.015],
              [lon + 0.015, lat + 0.015],
              [lon - 0.015, lat + 0.015],
              [lon - 0.015, lat - 0.015]
            ]]
          }
        }]
    }
    
    return {
        "confidence_score": conf,
        "classification": "Flood Inundation" if area >= 0.35 else "Waterlogging",
        "area_sq_km": area,
        "severity": severity,
        "severity_score": int(score * 100),
        "impact": {
            "population": pop,
            "buildings": bld,
            "facilities": fac
        },
        "mask_geojson": mask_geojson
    }

@app.post("/api/report-flood")
def report_flood(payload: CrowdReportRequest):
    new_report = {
        "lat": payload.lat,
        "lon": payload.lon,
        "severity": payload.severity,
        "description": payload.description,
        "phone": payload.phone,
        "timestamp": time.time()
    }
    CROWD_REPORTS.append(new_report)
    
    # Clustering logic: 3 reports in 2km
    nearby = [r for r in CROWD_REPORTS if calculate_distance(payload.lat, payload.lon, r["lat"], r["lon"]) <= 2.0]
    if len(nearby) >= 3:
        zone_id = f"zone_{round(payload.lat, 2)}_{round(payload.lon, 2)}"
        ACTIVE_ALERTS[zone_id] = {
            "lat": payload.lat,
            "lon": payload.lon,
            "severity": "CRITICAL",
            "type": "Crowd Cluster Alert",
            "message": f"CRITICAL: 3+ independent citizens reported severe flooding near coordinates {payload.lat}, {payload.lon}.",
            "timestamp": time.time()
        }
    return {"status": "SUCCESS", "message": "Report logged."}

@app.get("/api/alerts")
def get_alerts():
    return {
        "active_alerts": list(ACTIVE_ALERTS.values()),
        "crowd_pins": CROWD_REPORTS
    }

@app.post("/api/agent-cycle")
def run_agent_cycle(payload: AgentCycleRequest, background_tasks: BackgroundTasks):
    def run_agent_async():
        # Generate simulation logs
        logs = [
            f"[{time.strftime('%H:%M:%S')}] Starting autonomous monitoring cycle for: {payload.location}",
            f"[{time.strftime('%H:%M:%S')}] Perceiving environmental sensors...",
            f"[{time.strftime('%H:%M:%S')}] Perceived River Gauge Level: 16.5m (WARNING limit crossed)",
            f"[{time.strftime('%H:%M:%S')}] Plan calculated: Fetch latest Sentinel-1 passes",
            f"[{time.strftime('%H:%M:%S')}] Executing Action: SegFormer satellite fusion evaluation",
            f"[{time.strftime('%H:%M:%S')}] Output: Inundation detected spanning 2.8 sq km",
            f"[{time.strftime('%H:%M:%S')}] Running RAG situation brief generator...",
            f"[{time.strftime('%H:%M:%S')}] Dispatched warnings to {len(payload.phones)} users via Twilio",
            f"[{time.strftime('%H:%M:%S')}] Cycle finished successfully."
        ]
        
        report = f"""
============================================================
OFFICIAL EMERGENCY FLOOD BULLETIN: {payload.location.upper()}
============================================================
ALERT STATUS: WARNING

1. METRICS OVERVIEW
   Satellite analysis validates inundations of 2.80 sq km 
   affecting approximately 3,360 citizens.

2. LOGISTICS DIRECTIVES
   Relief camps opened at local secondary educational facilities.
============================================================
"""
        
        AGENT_TRACES[payload.location] = {
            "location": payload.location,
            "severity": "HIGH",
            "area_sq_km": 2.8,
            "gauge_status": "WARNING",
            "logs": logs,
            "report": report
        }
        
    background_tasks.add_task(run_agent_async)
    return {"status": "QUEUED", "message": f"Agent cycle triggered."}

@app.get("/api/agent-trace")
def get_agent_trace(location: str):
    if location in AGENT_TRACES:
        return AGENT_TRACES[location]
    return {"status": "NO_TRACE", "message": "No active agent trace."}
