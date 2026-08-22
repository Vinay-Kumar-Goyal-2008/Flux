# Detailed Feature Design & Implementation Blueprint
## Flood Detection & Response System (Anti Gravity)

This document provides a highly detailed technical blueprint for implementing every feature outlined in the updated [features.md](file:///C:/Users/SHAHZEB%20ALI/OneDrive/Desktop/Dell_Project/features.md). It serves as the master guide for the mobile client and backend development teams.

---

## 1. System Architecture & Tech Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    MOBILE CLIENT (Expo)                     │
│  - User Auth (JWT)       - Offline Map & Dijkstra Routing   │
│  - Citizen Form (GPS)    - Official GIS & Toggle overlays   │
│  - Local SQLite DB       - Speech Warnings (expo-speech)    │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP API / JSON
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   BACKEND SERVICE (FastAPI)                 │
│  - Router Controllers    - PySheds Flow Routing (DEM)       │
│  - PyTorch ML (ONNX)     - Vector store (ChromaDB + RAG)    │
│  - OSM Overpass client   - Telephony Gateways (Twilio)      │
└─────────────────────────────────────────────────────────────┘
```

*   **Mobile App Stack:** React Native (Expo SDK 57), TypeScript, `@rnmapbox/maps` (Mapbox GL), `expo-location` (GPS), `expo-speech` (TTS warnings), local SQLite / WatermelonDB (Offline storage).
*   **Backend Server Stack:** Python (FastAPI), PyTorch (Inference loader for `best_model_focal.pth`), `rasterio` & `geopandas` (Geospatial), `pysheds` (Flow routing/elevation pathing), LangGraph (Agent loop), ChromaDB (RAG Vector store), Twilio (SMS/IVR calls), SQLite (User Auth/Complaints DB).

---

## 2. Stage-by-Stage Feature Implementation Plan

### STAGE 1 — BACKGROUND MONITORING

#### 1. Rainfall Accumulation Watch
*   **Implementation:** A Celery background task runs every hour on the backend. It queries the OpenWeatherMap Historical API for the active grid. It sums the rainfall data for the past 120 hours (5 days).
*   **Threshold logic:** 
    *   Rain >= 100mm: Logs a **Yellow Watch** event in the database.
    *   Rain >= 200mm: Logs an **Orange Warning** event.
*   **Data flow:** `OpenWeather API` -> `Backend Parser` -> `SQLite (Alerts Table)` -> `Pushed to dashboard via WebSockets`.

#### 2. River Gauge Monitoring (CWC)
*   **Implementation:** Queries CWC (Central Water Commission) API for India gauge heights using the monitored location coordinates.
*   **Logic:**
    *   Current Water Level >= Warning Level: Triggers **Orange Alert**.
    *   Current Water Level >= Danger Level: Triggers **Red Alert**.
*   **Data schema:**
    ```sql
    CREATE TABLE river_gauges (
        station_id VARCHAR PRIMARY KEY,
        station_name VARCHAR,
        river_name VARCHAR,
        warning_level FLOAT,
        danger_level FLOAT,
        last_reading FLOAT,
        updated_at TIMESTAMP
    );
    ```

#### 3. Progressive Alert Escalation
*   **Implementation:** The alert dispatcher reads the last alert state from SQLite. It guarantees alerts escalate in sequence: `None` -> `Yellow` -> `Orange` -> `Red`. If a satellite confirms a flood (Red) but no rain alert (Yellow/Orange) has been sent, it sends a combined brief to avoid skipping warnings.

#### 4. FloodAgent Autonomous Loop
*   **Implementation:** A LangGraph state machine runs on a cron schedule (every 6 hours).
*   **State Graph Nodes:**
    *   `Perceive`: Reads weather, CWC readings, and crowdsourced clusters.
    *   `Plan`: Evaluates thresholds and chooses tools to invoke.
    *   `Act`: Executes Satellite fetch -> Model inference -> Post-process -> Alert dispatch -> RAG report.
    *   `Reflect`: Evaluates if status changed and updates memory.
*   **Framework:** `langgraph` state graphs with tool nodes.

---

### STAGE 2 — SATELLITE IMAGE ACQUISITION

#### 1. Sentinel-1 SAR Fetch
*   **Implementation:** Python backend queries Sentinel Hub Process API specifying the `Sentinel-1 (IW)` datasource, request bounds, and `VV` + `VH` output bands.
*   **Evaluation:** Returns a 16-bit GeoTIFF raster.

#### 2. Sentinel-2 Optical Fetch
*   **Implementation:** Same API request but queries `Sentinel-2 L2A` datasource, requesting RGB (B04, B03, B02) and Cloud QA (B11) bands.

#### 3. ECC Image Alignment
*   **Implementation:** Uses OpenCV's Enhanced Correlation Coefficient (`cv2.findTransformECC`) algorithm. Stacks SAR and Optical bands into a single multi-band array after applying the coordinate warp matrix.
*   **Code logic:**
    ```python
    # Find warp matrix from optical to SAR band template
    warp_matrix = np.eye(2, 3, dtype=np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 0.001)
    cc, warp_matrix = cv2.findTransformECC(optical_gray, sar_gray, warp_matrix, cv2.MOTION_TRANSLATION, criteria)
    aligned_optical = cv2.warpAffine(optical_rgb, warp_matrix, (512, 512), flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP)
    ```

#### 4. Pre-loaded Demo Events & Expert Image Upload
*   **Implementation:** Local file storage folder `/data/demo/` contains offline Bihar 2022 and Assam 2023 GeoTIFF tiles. An upload API `POST /api/upload-geotiff` accepts TIFF uploads, extracts metadata using `rasterio`, and feeds it directly to the model.

---

### STAGE 3 — AI DETECTION MODEL

#### 1. Loading Pre-trained Weights (`best_model_focal.pth`)
*   **Implementation:** Instantiates the SegFormer MiT-B2 architecture in PyTorch. Loads the `best_model_focal.pth` weights on the CPU/GPU server.
*   **Model input:** Multi-modal tensor `(Batch, Channels=5, Height=512, Width=512)`: [SAR_VV, SAR_VH, Opt_R, Opt_G, Opt_B].
*   **Loss configuration reference:** Trained using Dice + Focal Loss to counteract the ~5% active flood pixel sparsity.

#### 2. Cloud-Aware SAR Weighting & FPN Decoder
*   **Implementation:** Early stage Gated Fusion modules evaluate pixel intensities alongside the Cloud QA channel to attenuate the optical feature weights while propagating SAR features through the encoder block.
*   **FPN Decoder:** Merges channels from stages (S1, S2, S3, S4) through bilateral upsampling to output the 512x512 matrix.
*   **Boundary Refinement Block (BRB):** Sharpens edges using a 3x3 convolution layer with Sigmoid mapping.

#### 3. Heatmaps and Toggles
*   **Implementation:** Backend returns the raw probability map as an 8-bit single-channel grayscale PNG string, and a second binary GeoJSON mask. 
*   **Comparison Toggle:** Backend runs model twice (Optical-only vs Fusion) and returns both vector masks. Frontend switches Mapbox layer targets.

---

### STAGE 4 — POST-PROCESSING

#### 1. Dynamic NDWI Baseline Filter
*   **Implementation:** Backend computes `NDWI = (Green - NIR) / (Green + NIR)` on 30-day old pre-flood images. Pixels where `NDWI > 0.3` are grouped as permanent water.
*   **Logical operation:** `active_flood_mask[baseline_water_mask == 1] = 0`.

#### 2. DEM Elevation Validator & Low-Lying Warnings
*   **Implementation:** Downloads SRTM elevation arrays.
*   **Pre-flood warning:** Flow direction algorithm (PySheds) maps the drainage slope. Any coordinate adjacent to the current flood boundary that has a negative height gradient (downhill) is flagged as "At Risk", triggering SMS warnings to those specific addresses before water gets there.

#### 3. Connected Component Filter & Classification
*   **Implementation:** Run `cv2.connectedComponentsWithStats` on the binary mask. Remove components where size < 1000 pixels (approx. 0.1 sq km).
*   **Classification:**
    *   Area < 0.05 sq km: Noise.
    *   Area < 0.1 sq km or low backscatter: **Waterlogging**.
    *   Area >= 0.1 sq km: **Flood**.

---

### STAGE 5 — IMPACT ASSESSMENT

#### 1. Building, Road, and Critical Facility Counts
*   **Implementation:** Backend sends the flood boundary polygon to OSM Overpass API to query elements matching `building=*`, `highway=*`, `amenity=hospital`, or `amenity=school`. Spatial overlays filter features inside the polygon.

#### 2. Population Estimation (WorldPop)
*   **Implementation:** Projects the WorldPop India population density raster to EPSG:4326. Intersects it with the flood polygon and sums the grid cells.

#### 3. Severity Scoring & Priority Ranking
*   **Formula:** `Score = (pop/10000 * 0.4) + (bld/1000 * 0.3) + (fac/5 * 0.2) + (area/10 * 0.1)`.
*   **Rescue List:** Sorts active zones descending by score.

---

### STAGE 6 — ALERT & COMPLAINT SYSTEM

#### 1. SMS Dispatch & Crowdsource Trigger
*   **Implementation:** Twilio client dispatches messages to users inside the polygon.
*   **Crowdsourced Auto-Trigger:** When 3 user reports appear within 2km inside a 12-hour window, the background worker launches `run_detection` around the cluster centroid.

#### 2. Offline Complaint Queue
*   **Implementation:** If offline, the React Native app captures details and compresses the complaint image to a maximum of 150KB using `expo-image-manipulator`. The JSON payload is saved to local SQLite.
*   **Sync Logic:** App listens to network status using `@react-native-community/netinfo`. On reconnect, it fires `POST /api/report-flood` for all queued items in order.

---

### STAGE 7 — RAG REPORT GENERATION

#### 1. Dynamic ChromaDB Indexing
*   **Implementation:** Backend dynamically indexes documents placed in the `/corpus` directory.
    ```python
    # Dynamic loader
    for file in os.listdir("./corpus"):
        if file.endswith(".pdf"):
            # extract text via pypdf
            # chunk text to 500 words, 100 overlap
            # collection.add(documents, ids, metadatas)
    ```
*   **Generative pipeline:** Connects to **Gemini API** (`gemini-2.5-flash`) or **Groq API** (`llama-3.3-70b-versatile`) depending on configuration.

#### 2. Hallucination check
*   **Implementation:** A parser extracts all numbers from the LLM-generated report. It runs a value verification check against the inputs. If any number fails, it forces a regeneration with low temperature.

---

### STAGE 8 — DASHBOARD UI & MAP

*   **Choropleth severity map:** Colorizes flood polygons (Red = Critical, Orange = High, Yellow = Moderate, Green = Low).
*   **Shelter Icons:** Pre-cached shelter pins rendered on the map. Color reflects occupancy slots: Green (Available), Yellow (Near limit), Grey (Unknown). Clicking computes the shortest routing path.
*   **Before/After Slider:** Slide-over wrapper comparing dry historical base tiles with wet satellite imagery.

---

### STAGE 9 — AUTHENTICATION & USER MANAGEMENT

#### SQLite User & Complaint Schemas (Backend)
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR UNIQUE,
    password_hash VARCHAR,
    role VARCHAR, -- 'citizen' or 'official'
    phone VARCHAR
);

CREATE TABLE complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    latitude FLOAT,
    longitude FLOAT,
    reported_severity VARCHAR,
    description TEXT,
    status VARCHAR, -- 'pending', 'under review', 'resolved'
    model_confirmed BOOLEAN,
    created_at TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
```

---

### STAGE 10 — OFFLINE & ACCESSIBILITY

*   **Service Worker / PWA Caching:** Caches API coordinates, shelter information, and Mapbox map tiles (`.mbtiles` packages for the local district).
*   **Offline banner:** Renders "Offline mode — data last updated [timestamp]" using screen indicators.
