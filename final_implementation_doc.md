# Final Implementation Document: Floor Rescuer
## Complete Flood Detection & Response System

This document outlines the entire architecture, implementation details, technology stack, and directory structure of the Floor Rescuer Flood Detection and Response System.

---

## 1. System Architecture & Tech Stack

The system is built on a split architecture combining an offline-first React Native (Expo) client and a high-performance Python (FastAPI) machine learning backend.

### Tech Stack Breakdown
*   **Mobile App Client:**
    *   **Framework:** React Native / Expo SDK 57 (compiled for Web and mobile platforms).
    *   **Language:** TypeScript.
    *   **State Management:** React Query / React Context.
    *   **Mapping Interface:** `@rnmapbox/maps` (Mapbox GL Vector Tiles).
    *   **Local Data Store:** SQLite / WatermelonDB (Offline database).
    *   **Speech Output:** `expo-speech` (Text-To-Speech alert readouts).
*   **Backend Server:**
    *   **Framework:** FastAPI (Python).
    *   **Neural Network Core:** PyTorch (Loads weights from `best_model_focal.pth`).
    *   **GIS Processing:** `rasterio`, `geopandas`, `shapely`, `cv2` (OpenCV).
    *   **Elevation Pathfinding:** `pysheds` (Downslope flow modeling).
    *   **Generative AI & RAG:** ChromaDB (Vector database) + LangGraph / LangChain + Gemini & Groq APIs.
    *   **Alert Dispatchers:** Twilio (SMS/IVR voice triggers) and SMTP (Direct Email warnings).

---

## 2. Directory Structure

```
Dell_Project/
├── best_model_focal.pth            # Trained PyTorch SegFormer Weights (245MB)
├── features.md                     # Raw feature specifications
├── detailed_feature_design.md      # Master design document
├── final_implementation_doc.md     # [THIS FILE] Master feature reference
│
├── dell-flood-app/                 # React Native / Expo Client
│   ├── App.tsx                     # Entry Gate, Auth logic, Citizen & Official Dashboards, Shared Chatbot
│   ├── app.json                    # Permissions (GPS location, background alerts)
│   ├── package.json                # NPM Dependencies
│   └── src/
│       ├── components/
│       │   ├── MapView.tsx         # Side-by-side preview, choropleths, Dijkstra paths, Floating stats
│       │   ├── ReportForm.tsx      # Crowdsourced warning upload interface
│       │   ├── AgentPanel.tsx      # LangGraph Autonomous Agent logger
│       │   └── SettingsPanel.tsx   # Offline/Mock toggles and server URLs
│       ├── services/
│       │   └── api.ts              # API interfaces and local simulated DB, Voice call bindings
│       └── utils/
│           └── routing.ts          # Offline Dijkstra routing algorithm
│
└── dell-flood-backend/             # FastAPI / PyTorch Backend
    ├── main.py                     # API Bootstrapper
    ├── test_backend.py             # Validation script
    ├── mock_backend.py             # Offline verification script
    ├── corpus/                     # Folder for PDFs, txt, and md RAG documents
    └── app/
        ├── api/
        │   └── endpoints.py        # Auth routes, GIS endpoints, Twilio Voice calls, ranked queues
        ├── ml/
        │   ├── inference.py        # Custom dual-encoder SegFormer PyTorch loader
        │   └── postprocess.py      # NDWI baselines, relative heights, and classification
        ├── agent/
        │   └── flood_agent.py      # LangGraph autonomous cron loop
        └── RAG/
            ├── vector_store.py     # ChromaDB dynamic corpus indexing
            └── generator.py        # Gemini & Groq multi-LLM API routers
```

---

## 3. Database Schema

Stored locally in the FastAPI SQLite instance (`flood_database.db`):

```sql
-- Users and authentication roles
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password_hash TEXT,
    role TEXT, -- 'citizen' or 'official'
    phone TEXT
);

-- Crowdsourced complaints and alerts
CREATE TABLE complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    latitude FLOAT,
    longitude FLOAT,
    reported_severity TEXT, -- 'MINOR', 'MODERATE', 'SEVERE'
    description TEXT,
    status TEXT DEFAULT 'pending', -- 'pending', 'under review', 'resolved'
    model_confirmed INTEGER DEFAULT 0, -- 0 = Unconfirmed, 1 = Confirmed
    timestamp REAL
);

-- Pre-cached emergency shelters
CREATE TABLE shelters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    latitude FLOAT,
    longitude FLOAT,
    capacity TEXT, -- 'green', 'yellow', 'grey'
    slots_available INTEGER
);
```

---

## 4. Master Feature List & Implementations

### STAGE 1 — BACKGROUND MONITORING
1.  **Rainfall Accumulation Watch:** Periodically fetches OpenWeatherMap historical data. When rainfall sums over 100mm -> Yellow Watch; 200mm -> Orange Warning. Gives 3-5 days of warning before flooding commences.
2.  **River Gauge Monitoring (CWC):** Pulls Indian gauge heights from the CWC API. Crosses warning level -> Orange Alert; danger level -> Red Alert.
3.  **Progressive Alert Escalation:** Restricts alert statuses to progressive escalation (None -> Yellow -> Orange -> Red) to prevent public panic.
4.  **FloodAgent Autonomous Loop:** Built using LangGraph. Runs every 6 hours to perceive weather sensors, plan acquisitions, run models, write RAG reports, and update logs without human clicks.

### STAGE 2 — SATELLITE IMAGE ACQUISITION
5.  **Sentinel-1 SAR Fetch:** Pulls VV and VH radar bands. Radar wavelengths penetrate cloud cover entirely.
6.  **Sentinel-2 Optical Fetch:** Pulls RGB bands. Active when skies are clear.
7.  **ECC Image Alignment:** Uses OpenCV's Enhanced Correlation Coefficient (`cv2.findTransformECC`) warped affine matrix to align Sentinel-1 and Sentinel-2 pixel grids.
8.  **Pre-loaded Demo Events:** Pre-caches Bihar 2022 and Assam 2023 GeoTIFF imagery for offline demonstration purposes.
9.  **Expert Image Upload:** Endpoint `POST /api/upload-geotiff` accepts custom drone or high-res satellite files, parses coordinates via rasterio, and triggers detection.

### STAGE 3 — AI DETECTION MODEL & MAP DISPLAY
10. **SAR + Optical Dual Encoder Fusion:** MIT-B2 encoders process SAR & Optical channels. Gated Fusion weights channels at early stages; Cross-Attention coordinates deep stages.
11. **Cloud-Aware SAR Weighting:** Quality Assessment (QA) bands attenuate optical feature weights if clouds exceed threshold bounds.
12. **Improved FPN Multi-Scale Decoder:** Combines spatial features (S1-S4) through bilateral upsampling.
13. **Boundary Refinement Block:** Convolutional layers sharpen flood boundary edges.
14. **Confidence Heatmap & Big % Number:** Maps 0-1 sigmoid pixel probabilities, averaging them across the active mask for the dashboard readout.
15. **Floating Probability Overlay:** Displays the model's average flood probability directly as a large percentage float value over each affected zone on the map.
16. **Classified Segmented Flood Image Map:** Classification logic categorizes flooded regions directly on the map popup overlays, showing whether a specific region represents localized **Waterlogging** or large-scale **Flooding**.
17. **Optical-Only vs Fusion Toggle:** Compares cloudy optical output and complete SAR fusion output on the map.

### STAGE 4 — POST-PROCESSING
18. **Dynamic NDWI Baseline Filter:** Computes NDWI from 30-day old imagery to mask and subtract permanent lakes, reservoirs, and rivers.
19. **DEM Elevation Validator & Downstream Warnings:** SRTM DEM arrays filter false positives (building shadows). Downhill warnings identify locations downhill and downhill-adjacent from the active flood zone using PySheds drainage path arrays to warn residents before water reaches them.
20. **Connected Component Filter:** Runs OpenCV components labeling; discards isolated patches smaller than 0.1 sq km.
21. **Flood vs Waterlogging Classification:** Allocates class types: <0.05 sq km is discarded, 0.05-0.1 sq km represents Waterlogging, and >=0.1 sq km represents a Flood.

### STAGE 5 — IMPACT ASSESSMENT & EXPORTS
22. **Building and Road Count:** Intersects the flood boundary polygon with OSM Overpass features and Microsoft Building Footprints.
23. **Population Estimation:** WorldPop gridded population density grids are masked and summed inside the polygon.
24. **Critical Infrastructure Flagging:** Pinpoints schools, hospitals, and power grids inside the zone, rendering distinct map marker tags.
25. **Severity Scoring & Rescue Priority:** Ranks areas based on population, buildings, and critical facilities.
26. **Flood Spread Prediction:** Predicts 24-hour (orange) and 48-hour (yellow) downstream spread using topography slope.
27. **PDF Report Export (Feature 18):** Compiles interactive satellite maps, elevation slope warnings, crowdsourced complaints, impact statistics, and shelter paths into a downloadable PDF document using the Python `ReportLab` library.

### STAGE 6 — ALERT & TELEPHONY SYSTEM
28. **SMS Alerts (Twilio):** Delivers location-specific coordinates, severity, and nearest shelter paths over 2G networks.
29. **Twilio Voice Call Warning (Stage 6 Call Feature):** Outbound voice calls dispatcher (`POST /api/alerts/voice`) placed by officials dials citizens inside low-lying danger zones to play automated alert messages using Text-to-Speech (TTS).
30. **In-App Slide-Down Notification Banner & TTS Warnings (Stage 6):** Displays premium, animated glassmorphic notification cards at the top of the screen on event triggers (detection confirmed, new community reports logged, or voice call status changes). Reads out the alert details dynamically in real-time using Text-to-Speech (`expo-speech` on mobile, browser SpeechSynthesis on Web).
31. **Crowdsource Auto-Trigger:** Automatically launches satellite detection sweeps if 3+ citizens report flooding within 2km inside 12 hours.
32. **Offline Complaint Queue:** Compresses report images to ~150KB and queues them in local SQLite storage, auto-syncing when internet returns.

### STAGE 7 — RAG REPORT GENERATION & CHATBOTS
33. **Dynamic ChromaDB Indexing:** Parses PDFs and documents placed in the `./corpus` folder, chunking and embedding them locally.
34. **RAG Situation Reports:** Injects stats into NDMA/UN-OCHA templates using Gemini or Groq API backends.
35. **Hallucination Prevention:** Verifies all numbers in generated reports against the SQL pipeline database.
36. **Shared RAG Chatbot Q&A (Citizen & Official):** Multi-role chatbot card available on both dashboards. Connects to ChromaDB safety guides, answering questions about survival rules, shelter capacities, or active flood widths.

### STAGE 8 & 9 — USER PORTAL & INTERACTIVE MAPS
37. **Side-by-Side preview:** Displays Sentinel-1 radar and Sentinel-2 optical views side-by-side.
38. **Choropleth Severity Map:** Colorizes flood regions on Mapbox (Red: Critical, Orange: High, Yellow: Moderate).
39. **Offline Dijkstra Routing:** Computes Dijkstra path routing locally on the phone's graph database, tracing safe road paths to the nearest shelter.
40. **Official Dashboard:** Displays aggregated complaints, location groupings, and the 60/40 composite ranking queues.
41. **Citizen Dashboard:** Tracks submitted reports and local SMS alert logs.
