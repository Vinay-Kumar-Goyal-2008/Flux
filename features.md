# ANTI GRAVITY — Final Features
## Flood Detection & Response System

---

## SYSTEM ARCHITECTURE (Full Flow)

```
┌──────────────────────────────────────────────────────────────────────┐
│                     BACKGROUND MONITORING                            │
│  OpenWeatherMap (rainfall) + CWC API (river gauge) → escalation     │
└────────────────────────────┬─────────────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────────────┐
│                   SATELLITE IMAGE ACQUISITION                        │
│  Sentinel Hub API → Sentinel-1 SAR (VV,VH) + Sentinel-2 Optical     │
│  ECC alignment → same 512×512 pixel grid guaranteed                 │
└────────────────────────────┬─────────────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────────────┐
│                       AI DETECTION MODEL                             │
│  MiT-B2 Dual Encoder → Gated Fusion (S1,S2) + CrossAttn (S3,S4)    │
│  → Improved FPN Decoder → Boundary Refinement → Flood Probability   │
└────────────────────────────┬─────────────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────────────┐
│                      POST-PROCESSING                                 │
│  NDWI Baseline Filter → DEM Elevation Validator →                   │
│  Connected Component Filter → Flood vs Waterlogging Classifier       │
└────────────────────────────┬─────────────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────────────┐
│                      IMPACT ASSESSMENT                               │
│  OSM + Microsoft Building Footprints + WorldPop + Severity Scoring   │
└────────────────────────────┬─────────────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────────────┐
│               ALERT + REPORT + COMPLAINT PIPELINE                    │
│  SMS alerts (Twilio) + RAG report + Complaint management            │
└────────────────────────────┬─────────────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────────────┐
│                    DASHBOARD + OFFLINE LAYER                         │
│  Mapbox map + PWA offline caching + shelter markers                  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## STAGE 1 — BACKGROUND MONITORING

### Rainfall Accumulation Watch
Tracks cumulative 5-day rainfall every hour using OpenWeatherMap API. When rainfall crosses 100mm → Yellow watch alert issued. When it crosses 200mm → Orange warning issued. This gives a 3-5 day advance warning before flooding actually starts, purely from rainfall data without needing any satellite image.

**API used:** OpenWeatherMap Current + Historical API (free tier, 1000 calls/day)

### River Gauge Monitoring (CWC)
CWC (Central Water Commission) is India's government body that monitors river water levels at hundreds of gauging stations across the country. The CWC API gives real-time river height data. When a river crosses its "warning level" → Orange alert. When it crosses "danger level" → Red alert. This confirms a flood is imminent even before satellite detection. CWC covers all major Indian rivers — Ganga, Brahmaputra, Mahanadi, Godavari — so for any Indian flood event, there will be a nearby gauge.

**Why CWC specifically:** Optical satellites are blind under clouds. Rainfall data tells you rain is falling. River gauge tells you water is actually rising and about to overflow. Together they give early warning days before satellite can confirm.

**API used:** CWC Flood Forecasting API (government, free)

### Progressive Alert Escalation
Alerts escalate automatically as more evidence accumulates. Yellow (rainfall threshold crossed) → Orange (river gauge warning level) → Red (satellite flood confirmed). Each stage sends a different message with different urgency. System never skips a level — a resident gets a watch first, then a warning, then a confirmed alert. This avoids panic from premature full alerts.

### FloodAgent Autonomous Loop
LangGraph-based AI agent runs every 6 hours without any human trigger. It perceives incoming monitoring data, plans what action to take, chains tool calls automatically (fetch satellite → run model → assess impact → send alert → generate report), and updates its memory so it never sends duplicate alerts and escalates correctly when flooding worsens across multiple cycles.

**Framework:** LangGraph (LangChain), Claude API for agent reasoning

---

## STAGE 2 — SATELLITE IMAGE ACQUISITION

### Sentinel Hub API — Sentinel-1 SAR Fetch
Pulls VV (vertical transmit, vertical receive) and VH (vertical transmit, horizontal receive) radar polarization bands from Sentinel-1 satellite. Radar penetrates clouds completely — no weather interference. VV band is better for open water detection. VH band is better for flooded vegetation detection. Both are pulled together for the same bounding box.

**API used:** Sentinel Hub Process API (30-day free trial)

### Sentinel Hub API — Sentinel-2 Optical Fetch
Pulls RGB (B04, B03, B02) optical bands from Sentinel-2 satellite for the same bounding box and same 512×512 output dimensions. When skies are clear, optical imagery is much richer in detail than SAR alone. When cloudy, SAR takes over — but optical still provides context at cloud edges.

**API used:** Sentinel Hub Process API (same account as SAR)

### ECC Image Alignment
Sentinel-1 and Sentinel-2 are different satellites with different orbital cycles. They cannot capture the same location at the same time — images may be 2-5 days apart. Even with same bounding box and output size requested from the API, a small pixel shift remains due to different angles and positions. ECC (Enhanced Correlation Coefficient) algorithm in OpenCV automatically detects and corrects this shift before the images are stacked and fed to the model. Takes under 1 second.

### Pre-loaded Demo Events
Bihar 2022 and Assam 2023 Sentinel image pairs pre-downloaded and stored locally before the hackathon. Used as stable fallback if Sentinel Hub API is slow or fails on venue internet. Judges see the full pipeline running — they cannot tell the difference between a pre-loaded tile and a live API call.

### Expert Image Upload
Officials and NGOs who already have their own drone or satellite imagery can upload a GeoTIFF directly to the system. The full pipeline runs on it — no Sentinel API call needed. Useful for agencies that use higher-resolution commercial satellites like Planet or Maxar.

---

## STAGE 3 — AI DETECTION MODEL

### SAR + Optical Dual Encoder Fusion
Two separate MiT-B2 encoders process SAR and optical images independently. At Stage 1 (64 channels) and Stage 2 (128 channels), a Gated Fusion module learns how much to trust SAR vs optical per pixel — it outputs a learned gate value between 0 and 1 that weights each modality. At Stage 3 (320 channels) and Stage 4 (512 channels), Cross-Attention Fusion lets SAR features attend to optical features and vice versa — detecting which parts of the image each modality should guide the other on.

### Cloud-Aware SAR Weighting
QA (Quality Assessment) band from Sentinel-2 provides per-pixel cloud probability. When cloud coverage in a patch exceeds a threshold, the fusion weights automatically shift toward SAR. The gating is learned from training data — the model inherently learns to rely on SAR when optical signal is degraded by clouds.

### Improved FPN Multi-Scale Decoder
Feature Pyramid Network decoder combines feature maps from all four encoder stages simultaneously. Early stages capture fine spatial details (exact flood boundaries, narrow urban streets). Deep stages capture global context (large-scale flood extent, regional water patterns). FPN merges all scales — output segmentation is sharp at boundaries and globally accurate at the same time.

### Boundary Refinement Block
Dedicated convolutional block after FPN specifically designed to sharpen flood boundary edges. Without this, flood masks have blurry uncertain edges at land-water boundaries. The BRB detects edge gradients and refines them — output masks have clean, crisp flood boundaries suitable for precise building overlay calculations.

### Confidence Heatmap and Big % Number
Model outputs a continuous probability map (0-1 per pixel) not just a binary mask. Pixels classified as flooded have their probabilities averaged — this average is displayed as a large percentage number prominently on the dashboard (e.g. "87%"). Color coded — green below 50%, orange 50-75%, red above 75%. The full heatmap is also available as a map layer showing per-pixel confidence across the whole image.

### Optical-Only vs Fusion Comparison Toggle
Model runs twice on the same input — once with only the optical channels and once with full SAR+optical fusion. Both masks are stored. A toggle button on the dashboard switches between them. Where clouds exist, the optical-only mask shows empty gaps. The fusion mask fills those gaps correctly using SAR data. This single visual makes the core novelty immediately obvious to judges in 5 seconds.

**Loss function:** Dice + Focal (handles class imbalance — flood pixels are ~5% of any image)
**Evaluation:** IoU and F1 score per flood class (not raw accuracy)

---

## STAGE 4 — POST-PROCESSING

### Dynamic NDWI Baseline Filter
Rivers and lakes are always wet — we must never flag them as floods. Instead of using a static historical water map (JRC Global Surface Water which can be outdated), we compute a fresh baseline from a Sentinel-2 image taken 30 days before the flood event. NDWI (Normalized Difference Water Index) = (Green - NIR) / (Green + NIR). Pixels with NDWI above 0.3 are marked as permanent water. After model detection, this baseline mask is subtracted from the flood mask — only genuinely new flooding remains.

### DEM Elevation Validator — Pre-Flood Warning for Low-Lying Areas
SRTM Digital Elevation Model gives elevation for every pixel in the bounding box. This is used in two ways. First, it removes false detections — SAR sometimes falsely marks flat dry surfaces (airport runways, building shadows) as water. Any detected flood pixel sitting significantly higher than its surrounding neighborhood is removed as a false positive. Second, it enables pre-flood warnings — once a flood zone is confirmed, DEM flow direction analysis (using pysheds library) identifies which adjacent low-elevation areas are hydrologically connected and downhill from the flood. These areas get flagged as "at risk of flooding next" even before water reaches them, so residents there receive early warnings via SMS before the flood arrives.

**This is how DEM is specifically used:** Not just for removing false positives — actively used to predict which nearby low-lying neighborhoods will flood next based on terrain flow, and alerting those residents in advance.

### Connected Component Filter
Real flood water is spatially continuous — it forms a large connected region. SAR shadows and dry flat surfaces create small isolated dark pixels scattered randomly. Connected component analysis labels each group of connected flood pixels. Groups smaller than 1000 pixels (0.1 sq km) are removed as noise. What remains are only large contiguous flood regions consistent with real flooding.

### Flood vs Waterlogging Classification
Three checks combined: area below 0.05 sq km → noise. Area 0.05-0.1 sq km or low SAR backscatter → waterlogging. Area above 0.1 sq km + strong SAR signal → flood. Waterlogging triggers a lower severity yellow municipal alert. Flood triggers the full red emergency pipeline.

---

## STAGE 5 — IMPACT ASSESSMENT

### Building and Road Count
Flood polygon is used to query OpenStreetMap Overpass API for all buildings, roads, hospitals, schools within the bounding box. GeoPandas spatial join checks which features actually fall inside the polygon (not just the bounding box). Microsoft Global ML Building Footprints supplements OSM for rural India where OSM is sparse.

**APIs used:** OSM Overpass API (free), Microsoft Building Footprints (free download)

### Population Estimation
WorldPop gridded population raster is masked with the flood polygon. All population values inside the polygon are summed to estimate affected people. WorldPop is derived from satellite imagery and census data — it covers unmapped rural areas that OSM misses.

**Data:** WorldPop India raster (free download from worldpop.org)

### Critical Infrastructure Flagging
Hospitals, schools, power stations, and bridges are specifically identified from OSM tags and shown as distinct markers on the map (different icon/color per type). These are highlighted separately from regular buildings because their loss creates a second disaster inside the first.

### Severity Scoring
Weighted formula: (population/10000 × 0.4) + (buildings/1000 × 0.3) + (hospitals/5 × 0.2) + (area/10 × 0.1). Score above 0.7 = CRITICAL, 0.4-0.7 = HIGH, 0.2-0.4 = MODERATE, below 0.2 = LOW. Each detected zone gets a score and a color.

### Rescue Priority Ranking
All flood zones scored and sorted into a numbered list — Zone 1 most urgent, Zone N least urgent. Rescue teams see this list on the dashboard and know exactly where to go first without any manual analysis.

### Flood Spread Prediction (24-48 hours)
DEM flow direction algorithm (pysheds) computes which adjacent low-elevation areas are hydrologically connected to the current flood boundary. OpenWeatherMap 48-hour rainfall forecast adds rainfall intensity weighting — more rain means more aggressive spread. Output is two additional GeoJSON polygons shown on the map as orange (24h predicted) and yellow (48h predicted) zones alongside the current red flood zone.

**APIs used:** OpenWeatherMap Forecast API (free tier), SRTM DEM (NASA Earthdata, free)

---

## STAGE 6 — ALERT SYSTEM

### SMS Alerts via Twilio
Sent to all registered users whose GPS coordinates fall inside the confirmed flood polygon. Works on 2G — no internet needed by recipient. Message includes flood severity, distance from their location, and nearest shelter coordinates. Only zone-specific — a person 5km away from the flood gets nothing.

**API used:** Twilio SMS API (free trial credits)

### Crowdsource Auto-Trigger
When 3 or more ground reports cluster within a 2km radius, the system automatically triggers the full detection pipeline for that location without waiting for the next satellite pass. Priority score: each report weighted by severity (severe=5, moderate=3, minor=1) + recency bonus for reports under 2 hours old.

### Complaint Queue (Offline Store and Forward)
If a user raises a complaint with zero internet connectivity, the complaint (location, description, severity, compressed photo) is saved to device local storage. App shows "Saved offline — will submit when connected." When internet returns, all pending complaints sync automatically in order. Photos are compressed to ~150KB before local storage to prevent hitting device storage limits.

---

## STAGE 7 — RAG REPORT GENERATION

### RAG Situation Report
ChromaDB vector database preloaded with real past flood situation reports from NDMA India, UN-OCHA, and state SDMAs. When a flood event is detected, current event metadata (location, severity, flood area, season) is used to retrieve the 3-5 most similar past reports. These are injected into the LLM prompt as style and structure templates alongside current verified statistics. LLM writes a report that structurally matches official flood bulletins.

**Stack:** ChromaDB (local, free), all-MiniLM-L6-v2 embeddings (HuggingFace, free), Claude API for generation

### RAG Chatbot — What To Do Suggestions
A chatbot interface powered by the same RAG system. Users and officials can ask questions like "what should I do if flood water is entering my house?" or "which areas have the highest risk?" The chatbot retrieves relevant sections from NDMA flood safety guidelines and past response documents and answers in plain language. All factual data about the current flood (affected buildings, shelter locations, severity) comes from the live database — not from LLM memory.

### Hallucination Prevention
All numbers in the generated report come from our verified pipeline — never from LLM memory. An automated validator extracts every number from the generated text and checks it against pipeline output. Any unverified number triggers a regeneration request. Raw verified numbers are always shown alongside the report in a separate panel so officials can cross-check instantly.

### Official Report Format Selection
NDMA India bulletin format, UN-OCHA situation report format, state government advisory format, and field team operational brief — user selects which style before generating. RAG retrieves documents matching the selected format style.

---

## STAGE 8 — DASHBOARD AND MAP

### Map 1 — Normal Map with Live Satellite Preview
Standard Mapbox satellite base map. User can search any place by name — map flies to that location. User clicks anywhere on the map — a side panel appears showing the latest Sentinel-2 optical satellite image of that exact location fetched live from Sentinel Hub API. A "Run Flood Detection" button triggers the full pipeline on that location.

**Left panel shows:**
- Sentinel-1 SAR image of the clicked location
- Sentinel-2 optical image of the clicked location
- Side by side, same area, same date range

**APIs used:** Mapbox GL JS, Mapbox Geocoding API, Sentinel Hub Process API

### Map 2 — Colour Severity Map (Most Important)
Choropleth-style colored map showing flood severity level for every affected zone. Colour scale:
- Deep red — CRITICAL (score above 0.7)
- Orange — HIGH (0.4-0.7)
- Yellow — MODERATE (0.2-0.4)
- Light green — LOW (below 0.2)
- Grey — no flood detected

This is the primary operational view for disaster response officials. At a glance they see which zones are most affected without reading any numbers. Each colored zone is clickable — clicking shows the detailed impact numbers for that zone.

### Flood Probability Overlay
On top of either map, a toggle shows the model's average flood probability for each zone as a large number displayed directly over that area on the map. For example, a zone colored red might show "91%" floating over it — meaning the model is 91% confident this area is flooded. This is the average of all flood-pixel probabilities predicted by the model for that zone.

### Segmentation Mask Toggle
Button overlays the raw pixel-level flood segmentation mask on the satellite image. Exact flooded pixels are highlighted. Users can see precisely which streets, fields, and buildings are under water at pixel resolution. Can be toggled on and off without re-running the model.

### Historical Comparison — Days Before vs Now
A date picker or slider lets users select any past date for which satellite data is available. The segmented flood mask for that date is shown alongside today's mask. Users can visually compare how the flood has grown or receded over multiple days. Numbers show flood area on each date — "Day 1: 0.3 sq km → Day 3: 2.1 sq km → Day 7: 4.8 sq km." This builds a timeline of the flood event.

### Offline Shelter Markers
All NDMA and state SDMA registered shelters are shown on the map as distinct icons (a roof/house symbol, clearly different from any other map marker, large enough to be visible at moderate zoom). Shelters are color-coded by capacity — green (space available), yellow (filling up), grey (unknown capacity). The nearest shelter to the user's current GPS location is highlighted and distance shown. Shelter data is pre-cached on device — visible even with zero internet connectivity.

### Before/After Flood Timeline Slider
Side-by-side or overlapping view of the satellite image before the flood (30 days prior) and during the flood. A draggable divider reveals before on one side and after on the other. Flood area growth shown as a number below — "flood area grew from 0.2 sq km to 4.8 sq km in 3 days."

---

## STAGE 9 — AUTHENTICATION AND USER MANAGEMENT

### Login and Sign Up — Two User Types
Two separate login flows on the same auth screen. Normal user (resident) and Official (disaster management / government). Each sees a completely different dashboard after login.

**Auth stack:** JWT tokens, bcrypt password hashing, SQLite user table

### Normal User Dashboard
- Map with flood overlay for their registered area
- Personal alert history (all SMS alerts they received with timestamps)
- Report flooding button (crowdsource complaint submission)
- Personal complaint log — list of all complaints they have submitted, status of each (pending / under review / resolved), and whether the model confirmed flooding at their reported location

### Official Dashboard
- Full severity color map for all active flood zones
- Complaint management panel:
  - Total complaints count
  - Complaints grouped by location — "25 from Muzaffarpur, 18 from Darbhanga, 11 from Sitamarhi"
  - Active vs resolved complaints count
  - Complaints ranked by combined severity score: 60% weight to user-reported severity + 40% weight to model prediction confidence for that location
  - Filter by status (active / resolved), by location, by severity level
- Rescue priority ranked zone list
- RAG situation report generation button
- PDF export button
- Agent activity log (every autonomous action with timestamp and reason)

---

## STAGE 10 — OFFLINE AND ACCESSIBILITY

### Progressive Web App Offline Mode
Service worker pre-caches flood map, shelter locations, evacuation routes, and emergency contacts for user's registered area when app is opened on good internet. When internet dies, everything cached is still accessible. App shows "Offline mode — data last updated [timestamp]" banner so user knows how fresh the cached data is.

### Offline Complaint Queue
Complaints filled with zero connectivity saved to device local storage with photo (compressed to ~150KB). Auto-sync on reconnect. Complaint log on user dashboard updates to show "pending sync" status for offline complaints until they are submitted.

---

## COMPLETE API LIST

| API | What it does in our system | Free? |
|---|---|---|
| Sentinel Hub Process API | Fetch Sentinel-1 SAR (VV, VH) and Sentinel-2 optical images for any bounding box | 30-day free trial |
| Copernicus Open Access Hub | Manual Sentinel tile downloads for demo backup | Free forever |
| OpenWeatherMap API | 5-day cumulative rainfall monitoring + 48h forecast for flood spread prediction | Free tier (1000/day) |
| CWC Flood Forecasting API | Real-time India river gauge levels — warning and danger thresholds | Free (government) |
| OSM Overpass API | Building, road, hospital, school footprints for impact assessment | Free forever |
| Microsoft Building Footprints | AI-detected buildings in rural India where OSM is sparse | Free download |
| WorldPop | Gridded population density raster for people-affected estimation | Free download |
| SRTM DEM (NASA Earthdata) | Elevation data for false positive removal and flood spread flow direction | Free download |
| Twilio SMS API | Send SMS alerts to registered users in flood zones | Free trial credits |
| Mapbox GL JS | Interactive map rendering — satellite base, GeoJSON overlays, marker layers | Free tier (50k loads/month) |
| Mapbox Geocoding API | Place name search — user types location, map flies there | Free tier |
| OSM Nominatim API | Reverse geocode — coordinates to place name for complaint location labels | Free forever |
| Claude API | Agent reasoning, RAG report generation, chatbot responses | Pay per use |
| ChromaDB | Local vector database for RAG — stores past NDMA and UN-OCHA flood reports | Free, runs locally |
| HuggingFace Sentence Transformers | Embed flood report documents for ChromaDB retrieval | Free, runs locally |
| LangGraph (LangChain) | FloodAgent orchestration — perceive, plan, act, reflect loop | Free, open source |
| Browser Geolocation API | Capture user GPS for complaint location and shelter distance calculation | Free, built into browser |
| Browser Service Worker + Cache API | PWA offline caching of flood map, shelters, evacuation routes | Free, built into browser |

---

## WHERE AI IS USED — ALL TOUCHPOINTS

| Layer | AI Type | What it does |
|---|---|---|
| Core detection | SegFormer MiT-B2 (deep learning) | Pixel-level flood segmentation from fused SAR + optical |
| Gated Fusion | Learned gate network | Weights SAR vs optical trust per pixel based on cloud coverage |
| Cross-Attention Fusion | Transformer attention | SAR and optical features attend to each other at deep stages |
| FPN Decoder | Multi-scale CNN | Combines features from all 4 encoder stages for sharp output |
| Boundary Refinement | Convolutional block | Sharpens flood boundaries post-decoding |
| Severity scoring | Weighted ML formula | Ranks flood zones by urgency for rescue prioritization |
| Flood spread prediction | DEM flow algorithm + API | Predicts where flood moves next using terrain and rainfall |
| FloodAgent | LLM agent (LangGraph) | Autonomous monitoring, planning, tool chaining every 6 hours |
| RAG retrieval | Sentence Transformer embeddings | Finds similar past flood reports from vector DB |
| Report generation | LLM (Claude) | Writes official-style situation report from verified data only |
| RAG chatbot | LLM + RAG pipeline | Answers what-to-do questions using NDMA safety guidelines |
| Complaint scoring | Weighted formula (60:40) | Ranks complaints by user severity + model prediction confidence |

---

## ENVIRONMENT VARIABLES (All API keys — never hardcoded)

```
SENTINEL_CLIENT_ID
SENTINEL_CLIENT_SECRET
OPENWEATHER_API_KEY
CWC_API_KEY
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_PHONE_NUMBER
ANTHROPIC_API_KEY
MAPBOX_TOKEN
MODEL_WEIGHTS_PATH
MODEL_CONFIDENCE_THRESHOLD
DATABASE_URL
CHROMA_DB_PATH
JWT_SECRET_KEY
```
