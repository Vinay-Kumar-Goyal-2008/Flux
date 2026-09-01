<div align="center">

# FLUX: AI-Powered Multimodal Satellite Flood Detection & Autonomous Disaster Response System
</div>

<b>Flux is an autonomous conversational agent that bridges large language models with real time physical world infrastructure data. Powered by OpenAI GPT-4o and the MirEye Earth API, Flux handles open ended conversational tasks while dynamically routing location sensitive queries to verified spatial, hydrological and environmental hazard tools across the United States.
  
Emergency managers, field responders and residents often lack instant verified physical world context during extreme weather events, forcing them to manually consult disjointed federal GIS portals. By fusing dual encoder satellite Earth observation (SAR + Optical) with Mireye's sub meter physical intelligence layer, continuous Topographic Wetness Index hydrology, and an in flight human in the loop decision engine, Flux identifies imminent flash flood zones, dynamically routes evacuees away from submersed corridors, and empowers incident commanders in real time. Flux bridges conversational AI with real time geospatial ground telemetry i.e. users ask questions about any US city, county or landmark in plain English and Flux automatically resolves place names into coordinates, queries MirEye's sub meter Earth observation API and delivers actionable safety insights backed by authoritative federal citations (USGS, FEMA, NOAA).</b>
</p>

</div>

---

##  Executive Overview

During major flood disasters, emergency response operations suffer from two fatal blind spots:

1. The "Flat Map" Blind Spot: Standard satellite segmentation only tells you where surface water was when the satellite passed overhead. It cannot tell you ground elevation, soil saturation, building heights, population counts or which dry roads will submerge in the next 6 hours.
2. The "Naive Routing" Blind Spot: Evacuation navigation systems route evacuees based on shortest straight line distance, leading civilians directly into low elevation terrain depressions and flooded road basins.

Flux bridges this gap by injecting physical telemetry from the Mireye API (USGS 3DEP DEM elevation, slope, FEMA 100/500 yr floodplains, USGS NHD hydrography, and Overture building footprints) into every routing, triage, and dispatch decision.

---

##  Deep Learning Architecture & Pipeline

Flux implements a custom **Dual-Encoder Multimodal SegFormer architecture** specifically optimized for high-precision flood boundary delineation in challenging weather and all-terrain scenarios.

![AEGIS Deep Learning Architecture & Pipeline](assets/architecture_pipeline.png)

### System Architecture

```
 [Satellite SAR + Optical] ──► [NDWI Filter] ──► [Clean GeoJSON Inundation Mask]
                                                        │
                                                        ▼
                                            [Mireye Physical API]
                                    (DEM Elev, Slope, Floodplains, POIs)
                                                        │
                         ┌──────────────────────────────┴──────────────────────────────┐
                         ▼                                                             ▼
         [Predictive TWI Hydrology Layer]                            [DBSCAN Population Clustering]
              Flash-Flood Pooling Basins                                      │
                         │                                                             ▼
                         └──────────────────────────────┬──────────────────────────────┘
                                                        ▼
                                    [Elevation-Weighted Road Graph]
                                      (NetworkX / Dijkstra Routing)
                                                        │
                                                        ▼
                                       [Multi Criteria Triage Engine]
                                   Priority = Pop × (1 + Exp) / Elev_Safety
                                                        │
                                                        ▼
                                   [In Flight Feedback Interceptor]
                                (LangGraph: SHELTER_FULL / ROAD_CLOSED)
                                                        │
                         ┌──────────────────────────────┴──────────────────────────────┐
                         ▼                                                             ▼
         [Incident Commander Dashboard & SITREP]                      [Geo Targeted Citizen SMS]

```
 **Core Innovation: What Flux Solves**

<img width="331" height="302" alt="image" src="https://github.com/user-attachments/assets/675f372e-c163-436f-878d-a582e7b2e31a" />   


## Empirical Validation: Does Mireye Context Matter?

To prove that the Mireye coordinate round-trip performs critical life-safety work rather than visual decoration, Flux runs an empirical benchmark comparing a **Naive Straight-Line Strategy** against the **Mireye Context-Aware Strategy** across 33 real disaster clusters.

[SUMMARY RESULTS] 
  - Total Evaluated Clusters    : 33
  - Diverged Recommendations    : 2 clusters (6.1%)
  - Avg Extra Distance Accepted : +1.15 km (Safety Detour)
  - Sensitivity Projection      : 9.1% (Widened TWI Variance)

Context aware routing altered the primary shelter recommendation in 6.1% of disaster clusters, accepting an average of +1.15 km of travel to steer evacuees away from high risk, flood compromised access corridors.


## Project Structure

```
Mireye/
├── api/                                    # Mireye Live API Client & Data Models
│   ├── client.py                           # Batch queries, retries, exponential backoff
│   └── models.py                           # Pydantic schemas (FloodPolygon, LatLng, PhysicalContext)
│
├── pipeline/                               # Hydrology & Inundation Pipelines
│   ├── predictive_twi.py                   # TWI computation (D8 flow accumulation & slope)
│   ├── flood_prone.py                      # Multi-factor Flood Susceptibility Index (FSI)
│   ├── batch_predictive_hazard.py          # Multi-county live batch execution runner
│   ├── physical_data_hazard_engine.py      # Ground-truth processor for physical_data.json
│   └── flood_data.py                       # Polygon loader & GeoJSON utilities
│
├── decision_engine/                        # Autonomous Triage & Interceptor
│   ├── triage.py                           # Priority ranking & shelter capacity allocation
│   ├── interceptor.py                      # LangGraph in-flight feedback & course correction
│   └── mireye_value_experiment.py          # Day 11 empirical validation experiment
│
├── shelters/                               # Safe Shelter Discovery
│   └── finder.py                           # Multi-source shelter finder & elevation ranker
│
├── routing/                                # Road Graph & Route Engine
│   ├── elevation_router.py                 # Elevation-penalized Dijkstra routing
│   └── network_builder.py                  # NetworkX road network graph constructor
│
├── visualization/                          # Tactical Disaster Maps
│   └── map_plotter.py                      # 100% watermark-free Folium map visualizer with HUD
│
├── chatbot/                                # Conversational Spatial Agent
│   └── agent.py                            # GPT-4o agent with MirEye physical tools & geocoding
│
├── data/                                   # Input Flood Polygons
│   └── model_flood_polygons.json           # 24 benchmark flooded county coordinates
│
├── output/                                 # Generated Datasets and Maps
│   ├── all_counties_predictive_hazard.json # Consolidated 24 county predictive hazard report
│   ├── physical_data_predictive_hazard.json# 11 region ground truth analysis
│   ├── mireye_value_comparison.json        # Empirical validation dataset
│   ├── day11_empirical_validation_report.md# Validation markdown report
│   ├── twi_risk_surface.json               # Cluster TWI surface matrices
│   ├── evacuation_plans.json               # Cluster evacuation routes & shelters
│   └── *.html                              # Interactive Folium tactical disaster maps
│
├── main.py                                 # Main Unified Command-Line Interface (CLI)
├── run_flux_master.py                      # Master end-to-end execution script
├── requirements.txt                        # Python dependencies
├──  README.md                               # Project documentation

```

---

###  Installation & Quickstart

### 1. Clone & Setup Virtual Environment
```bash
git clone https://github.com/your-org/flux-disaster-intelligence.git
cd flux-disaster-intelligence

# Create and activate Python virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate
```

 2. Install Dependencies
```bash
pip install -r requirements.txt
```

 3. Configure API Credentials
Create a `.env` file in the root directory:
```bash
cp .env.example .env
```
Edit `.env` and add your API credentials:
```ini
MIREYE_API_TOKEN=your_mireye_jwt_token_here
MIREYE_BASE_URL=https://api.mireye.com/v1
OPENAI_API_KEY=your_openai_api_key_here
CACHE_TTL_HOURS=24
```

### 4. Execute the Pipeline
```bash
python run_flux_master.py
```

---

CLI Reference

Flux provides a powerful, modular CLI via `main.py`:

| Command | Description | Example |
| :--- | :--- | :--- |
| `python main.py run` | Ingest flood polygon & extract Mireye physical context | `python main.py run -p philadelphia_county_pa -n 10` |
| `python main.py evacuate` | Run DBSCAN clustering & elevation-weighted road routing | `python main.py evacuate -p houston_harvey` |
| `python main.py predict` | Compute TWI hydrology & flood susceptibility models | `python main.py predict -p charleston_county_sc -n 25` |
| `python main.py predict -f` | Ingest & analyze comprehensive `physical_data.json` | `python main.py predict -f physical_data.json` |
| `python main.py validate` | Run Day 11 empirical validation experiment | `python main.py validate` |
| `python main.py chat` | Launch conversational GPT-4o agent with MirEye tools | `python main.py chat -m "Flood risk in Charleston, SC"` |
| `python main.py usage` | Check live Mireye API credit balance & limits | `python main.py usage` |
| `python main.py catalog` | View all supported Mireye physical attributes | `python main.py catalog` |

---

## Tactical Disaster Map Visualizations

Flux renders **100% watermark-free, high-contrast Folium HTML maps** built for emergency management operations. Every map includes an interactive Disaster HUD legend and multi-layer toggles:

*  **Active Inundation Footprint:** High contrast danger polygon extracted via dual encoder SAR/Optical satellite imagery.
*  **Critical Runoff Nodes:** Glowing magenta markers identifying concave terrain basins with high TWI scores prone to flash pooling.
*  **Affected Neighborhood Centroids:** High contrast targets displaying population estimates and building counts from DBSCAN clustering.
*  **Safe Emergency Shelters:** Emerald pins indicating safe facilities tagged with ground DEM elevation.
*  **Elevation-Weighted Evacuation Paths:** Cyan polyline corridors steering clear of flood prone road segments.

> Maps are automatically generated . Open any map directly in a web browser to inspect interactive popups with DEM heights, slope angles, FEMA status, and soil drainage properties.

## Honest Caveats & Open Items

In the interest of full technical integrity and transparency:
1. **DEM Smoothing Resolution:** In synthetic raster tests, continuous DEM smoothing compressed TWI scores into a narrow band (mean 6.8–7.3). When evaluated against real point level ground truth in `physical_data.json`, TWI scores showed realistic variance ranging from 7.16 to 12.89.
2. **Road-Risk Field Status:** Road risk scores currently use a synthetic topographic hazard proxy until Mireye's native road exposure attributes are enabled.
3. **Shelter Verification:** Athens County, Ohio utilizes verified, real world community shelters (Athens Community Center & Athens High School), other regions utilize geographically distributed benchmark facilities that should be verified with local emergency management agencies prior to deployment.



## 📄 License

This project is licensed under the **MIT License**. Built with physical intelligence powered by **Mireye**.
