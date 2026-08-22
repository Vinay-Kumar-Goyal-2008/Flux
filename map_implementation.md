Anti Gravity — Map + Live Flood Detection Implementation Guide
For Claude Code / Developer Reference
WHAT THIS DOCUMENT COVERS

This document explains exactly how to implement the map search and live flood detection pipeline end to end. No hardcoding. Every result must come from the actual Sentinel Hub API and the actual trained SegFormer model. Every step the user sees on screen must be communicated as a live status message while processing happens in the background.

WHAT THE USER EXPERIENCE SHOULD LOOK LIKE

This is the exact flow a user sees:

User opens the app — sees a full-screen Leaflet map of India
User types a place name in the search bar (e.g. "Muzaffarpur, Bihar")
Map flies to that location
A status panel appears on screen — starts showing live text updates as each step runs
Steps run one by one in the background — each step updates the text on screen
Final result appears — flood mask overlaid on map, confidence percentage, impact numbers

The status panel is the most important UX decision. Since satellite fetch + model inference takes 15-30 seconds, the user must see exactly what is happening at every moment. Never show a blank loading spinner. Show real descriptive text for each step.

STEP BY STEP STATUS MESSAGES

These are the exact messages that should appear on screen one by one as each step completes. Each new message appends below the previous one so the user sees a growing log: example:

🛰️  Locating coordinates for Muzaffarpur, Bihar...
✅  Location found — 26.12°N, 85.39°E

🛰️  Requesting Sentinel-2 optical image from satellite...
✅  Optical image acquired — cloud cover: 22% [Panel 1 appears]

📡  Requesting Sentinel-1 SAR radar image...
✅  SAR image acquired — VV and VH bands loaded [Panel 2 appears]

🔧  Aligning SAR and optical images (ECC correction)...
✅  Images aligned — pixel shift corrected

🧠  Running flood detection model (SAR + Optical fusion)...
✅  Model inference complete — 87.3% average confidence

🎨  Generating segmentation image from model output...
✅  Flood mask painted over satellite image [Panel 3 appears]

💧  Filtering permanent water bodies (NDWI baseline)...
✅  Rivers and lakes removed from flood mask

🏔️  Validating with elevation data (DEM check)...
✅  False positives removed — high ground cleared

📊  Calculating flood type — flood or waterlogging...
✅  Classification: FLOOD detected

🏘️  Overlaying impact data (buildings, roads, hospitals)...
✅  Impact calculated — 847 buildings, 2 hospitals at risk

👥  Estimating affected population...
✅  Approx. 5,200 people in flood zone

⚠️  Severity scored: CRITICAL
✅  Flood zone mapped — displaying results on map

Every single one of these messages is triggered by the actual completion of that step in the backend. Not a timer. Not a fake animation. Real step completion.

FRONTEND REQUIREMENTS
Map Setup
Use Leaflet.js with Esri World Imagery tile layer (free, no API key needed)
Default view: India centered at lat 20.5, lon 78.9, zoom level 5
Map must be full screen height
Search bar sits at top center of the map
Search Bar
Use Nominatim (OpenStreetMap geocoding) to convert place name to coordinates
API: https://nominatim.openstreetmap.org/search?q={place}&format=json&limit=1
No API key needed
On result: fly map to coordinates with zoom level 10
Immediately trigger the flood detection pipeline for those coordinates
Status Panel
Fixed panel — appears on left side of map when detection starts
Dark background, white text, monospace or clean sans font
Each new status message fades in below the previous one
Show a subtle pulsing indicator next to the currently running step
Panel scrolls if messages overflow
When all steps complete, show a "RESULTS READY" banner at the bottom of the panel
Results Overlay

After all steps complete, show on the map:

Flood GeoJSON polygon filled with color based on severity (red=CRITICAL, orange=HIGH, yellow=MODERATE, green=LOW)
Confidence percentage as a large number floating above the flood zone on the map
Shelter markers as distinct icons (roof symbol) on the map
A separate results card below the status panel showing:
Flood area in sq km
Buildings affected
Population affected
Hospitals at risk
Severity level
S1 and S2 Image Preview Panel

On the LEFT side of the screen (separate from status panel), show three stacked image panels. Each panel has a label, the image, and a small caption:

Panel 1 — Sentinel-2 Optical

Label: "Sentinel-2 Optical (RGB)"
Image: the actual RGB satellite image returned from Sentinel Hub API for this location
Caption: "Cloud cover: X% — acquired [date]"
Appears: immediately when Step 3 (Sentinel-2 fetch) completes — do NOT wait for model

Panel 2 — Sentinel-1 SAR

Label: "Sentinel-1 SAR (VV band)"
Image: the VV channel from Sentinel Hub API visualized as grayscale
To render: take the VV numpy array, normalize to 0-255 range, convert to grayscale PNG, encode as base64
Caption: "Radar — sees through clouds"
Appears: immediately when Step 4 (Sentinel-1 fetch) completes — do NOT wait for model

Panel 3 — Model Segmentation Output

Label: "Flood Segmentation (Model Output)"
Image: a visual representation of what the model actually predicted — NOT a colored polygon, the actual pixel-level output
How to generate this image:
Take the 512×512 probability map output from the model (values 0.0 to 1.0)
Apply a colormap to it: pixels with probability > 0.7 = red, 0.4-0.7 = orange, 0.1-0.4 = yellow, < 0.1 = transparent or dark grey
Overlay this colormap image on top of the optical RGB image at 60% opacity so the satellite terrain is visible underneath the flood colors
The result is a composite image showing the actual satellite terrain with the model's flood prediction painted over it in color
Encode this composite as base64 PNG and send to frontend
Caption: "Model confidence: X% — [flood/waterlogging/no flood]"
Appears: after Step 8 (model inference) completes
This panel has a toggle button: "Show raw probability heatmap" — clicking it switches to showing the raw 0-1 probability map as a blue-to-red heatmap without the optical overlay

How to generate the raw probability heatmap (toggle view):

Take the 512×512 probability map
Apply matplotlib's 'RdYlBu_r' colormap (blue=low probability, red=high probability)
Encode as base64 PNG
This is the pure model output visualization with no satellite image underneath

Both the composite segmentation image and the raw heatmap must be generated from the actual model output. Never generate these from hardcoded values or placeholder images.

Important — these three panels update progressively:

Panel 1 appears when optical fetch done
Panel 2 appears when SAR fetch done
Panel 3 appears when model inference done
Each panel shows a skeleton placeholder (grey box with label) before its data arrives
This makes it visually clear that real data is loading in real time
BACKEND REQUIREMENTS
Technology
FastAPI (Python)
All heavy processing runs in background tasks
Frontend polls a /status/{job_id} endpoint every 1 second to get live status updates
When all steps complete, polling gets the final result
Job Flow

When the frontend sends a detection request:

Backend creates a unique job ID
Returns the job ID immediately to frontend
Frontend starts polling /status/{job_id} every second
Backend runs all steps in sequence, updating job status after each step
Frontend reads status updates and appends messages to the status panel
When job status is "complete", frontend reads the result and renders on map
Status Object Structure

The /status/{job_id} endpoint should return something like:

{
  "job_id": "abc123",
  "status": "running",
  "steps_completed": [
    {"step": "geocoding", "message": "Location found — 26.12°N, 85.39°E", "done": true},
    {"step": "rainfall", "message": "Cumulative rainfall: 187mm", "done": true},
    {"step": "sentinel2_fetch", "message": "Optical image acquired — cloud cover 22%", "done": true},
    {"step": "sentinel1_fetch", "message": "SAR image acquired", "done": false}
  ],
  "current_step": "sentinel1_fetch",
  "result": null
}

When complete, status becomes "complete" and result contains the full detection output.

Partial results must be available during processing: The frontend should not wait for all steps to finish before showing anything. The polling endpoint must return partial results as they become available:

{
  "job_id": "abc123",
  "status": "running",
  "steps_completed": [...],
  "current_step": "model_inference",
  "partial_result": {
    "optical_b64": "base64 string — available after Step 3",
    "sar_b64": "base64 string — available after Step 4",
    "segmentation_composite_b64": null,
    "probability_heatmap_b64": null
  }
}

Frontend logic:

When optical_b64 appears in partial_result → show Panel 1 immediately
When sar_b64 appears → show Panel 2 immediately
When segmentation_composite_b64 appears → show Panel 3 immediately
When status = "complete" → show map overlay and all impact numbers

This progressive loading is what makes the app feel fast and real even though the full pipeline takes 15-30 seconds.

SATELLITE IMAGE ACQUISITION — EXACT IMPLEMENTATION STEPS
Step 1 — OAuth token

Call Sentinel Hub token endpoint with CLIENT_ID and CLIENT_SECRET from .env file. Store the token in memory for the duration of this job. Do not re-fetch per request.

Endpoint: https://services.sentinel-hub.com/oauth/token Method: POST Body: grant_type=client_credentials, client_id, client_secret

Step 2 — Calculate bounding box

From the clicked/searched lat and lon, calculate a bounding box:

bbox = [lon - 0.02, lat - 0.02, lon + 0.02, lat + 0.02]
This gives roughly a 4km × 4km square around the location
Use exact same bbox for BOTH Sentinel-1 and Sentinel-2 requests
Use exact same output size 512×512 for both
This guarantees both images are on the same pixel grid
Step 3 — Fetch Sentinel-2 optical

Request: POST to https://services.sentinel-hub.com/api/v1/process

Collection: sentinel-2-l2a
Bands: B04 (Red), B03 (Green), B02 (Blue)
Time range: last 30 days from today
Max cloud coverage: 30%
Output: 512×512 PNG
Evalscript multiplies each band by 2.5 for visual contrast
Parse response PNG bytes using PIL into a 512×512×3 numpy array
Also extract cloud coverage percentage from response metadata
Update status: "Optical image acquired — cloud cover X%"
Send this image to frontend immediately so it appears in the S2 preview panel
Step 4 — Fetch Sentinel-1 SAR

Request: POST to same process endpoint

Collection: sentinel-1-grd
Bands: VV, VH
Same bounding box and 512×512 output
Pack VV into Red channel, VH into Green channel, set Blue to 0
Parse response PNG bytes using PIL
Extract VV as arr[:,:,0] and VH as arr[:,:,1]
Update status: "SAR image acquired — VV and VH bands loaded"
Send visualized VV grayscale to frontend for the S1 preview panel
Step 5 — ECC Alignment

Convert both images to grayscale. Run OpenCV ECC algorithm to find pixel shift between SAR and optical. Apply correction to SAR image. Update status: "Images aligned."

If ECC fails (rare), skip silently and continue — same bbox already gives good alignment.

HOW SAR AND OPTICAL ARE DYNAMICALLY USED IN PREDICTION

This is critical to understand and implement correctly. The model does not use a fixed combination of SAR and optical. It dynamically adjusts based on what the actual images contain.

What dynamic means here

When the Sentinel-2 optical image is fetched, the cloud coverage percentage is extracted from the response metadata. This cloud percentage is passed into the model pipeline and changes how the two images are combined.

Low cloud cover (below 30%): Both SAR and optical are used with roughly equal weighting. The gated fusion modules in the model learn to trust optical more for fine boundary details (roads, building edges, vegetation boundaries) and SAR for open water detection.

High cloud cover (above 60%): The optical image is partially or fully blocked by clouds. In this case, pass a cloud_weight parameter to the model that increases the gating toward SAR channels. The SAR image was taken with radar which penetrates clouds completely, so it still contains accurate flood information even when optical is useless.

How to implement the dynamic weighting: The gated fusion in the model uses a sigmoid gate that is learned during training. To dynamically boost SAR at inference time when clouds are high, multiply the optical input tensor by (1 - cloud_fraction) before passing it to the encoder. If cloud cover is 80%, multiply optical by 0.2. This reduces the optical signal and forces the model to rely more on SAR. Do this BEFORE normalization so the scale is preserved correctly.

cloud_fraction = cloud_cover_pct / 100.0 optical_tensor = optical_tensor * (1.0 - cloud_fraction * 0.8)

The 0.8 factor prevents completely zeroing out optical even at 100% cloud cover, because partial information is still better than none.

When Sentinel-1 is unavailable: If the SAR fetch fails, run the model in optical-only mode. To do this, pass a zero tensor of shape (1, 2, 512, 512) as the SAR input. The model will still produce output but it will be less accurate. Add a status message: "SAR unavailable — running optical-only detection, accuracy reduced."

When Sentinel-2 is unavailable: If the optical fetch fails (extremely rare), pass a zero tensor of shape (1, 3, 512, 512) as the optical input and run SAR-only. Add status message: "Optical unavailable — running SAR-only detection."

The segmentation panel must show which mode was used: In the caption of Panel 3 (segmentation output), always show: "Mode: SAR + Optical fusion" or "Mode: Optical only" or "Mode: SAR only" so the user knows what data the prediction is based on.

MODEL INFERENCE — EXACT STEPS
Step 6 — Normalize inputs
SAR: Z-score normalize each channel independently (subtract mean, divide by std + 1e-8)
Optical: divide all values by 255.0 to get range 0-1
SAR becomes tensor shape (1, 2, 512, 512)
Optical becomes tensor shape (1, 3, 512, 512)
Step 7 — Cloud coverage check

If cloud coverage from Step 3 is above 60%, log a note: "High cloud cover — SAR weighting increased." The model handles this inherently through its gated fusion — no manual intervention needed. Just pass the flag through for the status message.

Step 8 — Run model

Call model.forward(sar_tensor, optical_tensor). Model runs dual MiT-B2 encoders, gated fusion at stages 1-2, cross-attention at stages 3-4, FPN decoder, boundary refinement, sigmoid output. Output is a 512×512 probability map with values 0-1 per pixel. Update status: "Model inference complete."

Step 8b — Generate segmentation image immediately after inference

Do this right after model output is received, before post-processing. This step generates the three visual outputs:

Segmentation composite image:

Take the 512×512 probability map (values 0.0 to 1.0)
Create an RGBA overlay image, same size (512×512), fully transparent initially
For each pixel:
probability > 0.7 → paint red (255, 0, 0, 180)
probability 0.4-0.7 → paint orange (255, 140, 0, 160)
probability 0.1-0.4 → paint yellow (255, 220, 0, 120)
probability < 0.1 → leave transparent
Open the optical RGB image (already loaded in Step 3)
Paste the RGBA overlay on top of the optical image using alpha compositing
The result shows the actual satellite terrain with flood prediction colors overlaid
Encode as base64 PNG → this becomes segmentation_composite_b64

Raw probability heatmap:

Take the 512×512 probability map
Normalize to 0-255 range
Apply matplotlib colormap 'RdYlBu_r' → blue=safe, yellow=moderate, red=flooded
Encode as base64 PNG → this becomes probability_heatmap_b64

Update job status: "Segmentation image generated" and immediately add both images to the partial result so the frontend can show Panel 3 without waiting for post-processing to finish.

Step 9 — Apply threshold

Binary mask = probability map > 0.4. Every pixel above 0.4 is considered flooded.

Step 10 — Connected component filter

Label all connected regions in the binary mask. Remove any region smaller than 1000 pixels. This removes noise, shadows, and small false detections. Only large contiguous flood regions remain.

Step 11 — NDWI baseline subtraction

Fetch a second Sentinel-2 image from 30 days prior to the flood date. Compute NDWI = (Green - Red) / (Green + Red + 1e-8). Mark pixels with NDWI > 0.3 as permanent water. Subtract this permanent water mask from the current flood mask. What remains is only genuinely new flooding. Update status: "Rivers and lakes removed from flood mask."

Step 12 — DEM elevation check

Load SRTM DEM tile for the bounding box (pre-downloaded locally). For each pixel marked as flooded, check if it sits significantly higher than its surrounding neighborhood. If yes, remove it as a false positive — real flood water cannot exist on elevated terrain. Update status: "High ground cleared."

Step 13 — Flood vs waterlogging classification

Calculate total flood area in sq km (number of flood pixels × 0.0001). If area < 0.05 sq km, classify as noise and discard. If area < 0.1 sq km or average probability of flood pixels < 0.4, classify as waterlogging. Otherwise classify as flood. Update status accordingly.

Step 14 — Convert mask to GeoJSON

Use rasterio's shapes function with the geographic transform from the bounding box to convert the binary pixel mask into a geographic GeoJSON polygon. This polygon represents the actual flood boundary on the real map coordinates.

IMPACT CALCULATION — EXACT STEPS
Step 15 — OSM buildings and roads

Query Overpass API with the flood polygon bounding box. Count buildings, roads, hospitals, schools inside the polygon using GeoPandas spatial join. Update status: "Impact calculated."

Step 16 — Population

Load WorldPop raster for India (pre-downloaded). Mask with flood GeoJSON polygon. Sum all population values inside to get affected people count.

Step 17 — Severity score

Score = (population/10000 × 0.4) + (buildings/1000 × 0.3) + (hospitals/5 × 0.2) + (area/10 × 0.1). Capped at 1.0. Above 0.7 = CRITICAL, 0.4-0.7 = HIGH, 0.2-0.4 = MODERATE, below 0.2 = LOW.

FINAL RESULT OBJECT

When all steps complete, the job result should contain:

{
  "confidence_score": 87.3,
  "flood_area_sqkm": 4.2,
  "flood_type": "flood",
  "severity": "CRITICAL",
  "severity_color": "red",
  "detection_mode": "SAR + Optical fusion",
  "cloud_cover_pct": 22,
  "flood_geojson": { GeoJSON polygon },

  "images": {
    "optical_b64": "base64 PNG — actual Sentinel-2 RGB image from API",
    "sar_b64": "base64 PNG — VV band grayscale from Sentinel-1 API",
    "segmentation_composite_b64": "base64 PNG — optical image with colormap flood overlay",
    "probability_heatmap_b64": "base64 PNG — raw 0-1 model output as RdYlBu_r colormap"
  },

  "image_metadata": {
    "optical_date": "2026-07-28",
    "sar_date": "2026-07-26",
    "optical_cloud_cover": 22,
    "bbox": [85.37, 26.10, 85.41, 26.14]
  },

  "impact": {
    "buildings": 847,
    "roads": 12,
    "hospitals": 2,
    "schools": 4,
    "population": 5200
  },
  "rainfall_mm": 187
}

The four images in the result must ALL be generated from real data:

optical_b64 → real Sentinel-2 API response for this exact location and date
sar_b64 → real Sentinel-1 API response for this exact location and date
segmentation_composite_b64 → actual model probability output painted over optical image
probability_heatmap_b64 → actual raw model probability map as colormap

None of these can be placeholders, stock images, or pre-generated files.

WHAT MUST NOT BE HARDCODED
Coordinates — must come from Nominatim geocoding of user search
Bounding box — must be calculated from actual search coordinates
Satellite images — must come from live Sentinel Hub API, not local files
Flood mask — must come from actual model inference on live images, not pre-computed
Impact numbers — must come from live OSM query and WorldPop calculation
Confidence score — must be actual average probability from model output
Severity — must be calculated from actual impact numbers

Pre-loaded demo events (Bihar 2022, Assam 2023) are allowed as FALLBACK ONLY if Sentinel Hub API fails. They must not be the default behavior.

ERROR HANDLING

Each step must have a fallback:

Nominatim fails → show "Could not find location — try a different search"
Sentinel Hub token fails → show "Satellite API unavailable — loading demo event" → fall back to pre-downloaded tiles
Sentinel-2 fetch fails (no image in date range) → widen date range to 60 days and retry once
Sentinel-1 fetch fails → show "SAR unavailable — using optical only" → run model in optical-only mode
Model inference crashes → show "Detection failed — please try again"
ECC alignment fails → skip silently, continue with unaligned images (same bbox is good enough)
OSM Overpass fails → show impact as "unavailable" without blocking the flood mask display
Never let one step failure crash the entire pipeline
SEGMENTATION IMAGE TOGGLE BEHAVIOR

Panel 3 has two views the user can switch between. Implement as a toggle button at the top of the panel:

View A — "Composite" (default) Shows the colormap overlay painted on top of the actual optical satellite image. User sees real terrain underneath the flood colors. This is the most visually informative view.

View B — "Probability Map" Shows only the raw model output as a blue-to-red heatmap. No satellite image underneath. Pure model confidence visualization. Useful for understanding where the model is certain vs uncertain.

The toggle button text changes: "Show probability map" ↔ "Show composite"

Both views use base64 images already generated in Step 8b. The toggle is purely a frontend image swap — no new API call needed. Just swap which base64 image is displayed in Panel 3.

IMPORTANT NOTES FOR DEVELOPER
The model weights file path comes from MODEL_WEIGHTS_PATH in .env — never hardcode the path
Load the model ONCE at server startup — not per request. Store in global memory
Run model inference on CPU if no GPU available — it will be slower (~10-15 seconds) but will work
The SRTM DEM and WorldPop rasters should be pre-downloaded and stored locally before deployment
All API keys come from .env file — SENTINEL_CLIENT_ID, SENTINEL_CLIENT_SECRET, OPENWEATHER_API_KEY
The frontend polls every 1 second — the backend must update job status after EVERY single step, not just at the end
Leaflet tiles are free — do not add Mapbox. Use Esri World Imagery: https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}
The segmentation composite image is generated from the actual optical image + actual model output — never from a placeholder or stock satellite image
The detection_mode field in the result must reflect what actually ran — check whether SAR tensor was zeros (optical-only mode) or optical was zeros (SAR-only mode) or both were real (fusion mode) and set the string accordingly
The cloud_cover_pct extracted from Sentinel Hub response metadata must be used to dynamically weight the optical input before passing to model — this is what makes fusion dynamic, not static
Both segmentation images (composite and heatmap) must be stored in the job result and returned in the partial result as soon as they are generated — do not wait for impact calculation to finish before sending them to frontend
PIL and numpy are sufficient for all image generation steps — no need for heavy GIS libraries like GDAL for the image visualization parts