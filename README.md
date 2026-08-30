# Flux - Flood Inundation & Waterlogging Polygon Predictions + Intelligent Chatbot

This repository contains:
1. **SegFormer MiT-B2 deep learning model inference predictions** for 30 US Counties across Pennsylvania, Ohio, South Carolina, West Virginia, North Carolina, Florida, and Indiana.
2. **MirEye & OpenAI Intelligent Chatbot** for interactive physical-world geospatial intelligence and general Q&A.

---

## Dataset Structure
- `us_counties_flood_predictions.json`: Master dataset containing all 30 US counties.
- `us_flood_polygons/`: Individual county JSON files.

### Coordinate Format
Coordinates are formatted as `[longitude, latitude]`:
```json
{
  "place": "Charleston County, South Carolina",
  "flood_coordinates": [
    [-79.93285, 32.77942],
    [-79.93347, 32.77918],
    [-79.93386, 32.77965]
  ],
  "spacing_m": 1000
}
```

---

## MirEye & OpenAI Intelligent Chatbot

An AI-powered chatbot that uses **OpenAI GPT-4o** for general conversation and seamlessly integrates the **MirEye Earth API** for physical-world geospatial intelligence across US locations.

### Features

- **Dynamic Tool Routing (OpenAI Function Calling)**: OpenAI answers general questions directly and selectively calls MirEye API tools only when physical-world or location intelligence is needed.
- **Automatic Location Resolution**: Users do not need to provide GPS coordinates. Place names, landmarks, cities, or addresses (e.g. *Times Square*, *Aspen, CO*, *Galveston, TX*) are automatically resolved into coordinates.
- **Cited Geospatial Intelligence**: Location queries return structured responses backed by official federal and scientific sources (USGS 3DEP, NOAA, FEMA NFHL, USFS, CAL FIRE, Copernicus Sentinel-2).
- **Multiple MirEye Tools**:
  - `mireye_geocode`: Converts place names / landmarks into latitude and longitude.
  - `mireye_ask`: Natural language Q&A for complex location inquiries with full citation provenance.
  - `mireye_fetch`: Deterministic structured data and preset bundles (`terrain`, `flood_risk`, `wildfire_underwrite`, `solar_siting`, `utilities`, `data_center_siting`, etc.).

---

### Setup & Installation

#### 1. Clone the repository
```bash
git clone https://github.com/Vinay-Kumar-Goyal-2008/Flux.git
cd Flux
```

#### 2. Install dependencies
```bash
pip install -r requirements.txt
```

#### 3. Configure Environment Variables
Create a `.env` file in the root directory (refer to `.env.example`):
```env
OPENAI_API_KEY=your_openai_api_key_here
MIREYE_API_TOKEN=your_mireye_api_token_here
```

> **Note**: The `.env` file is gitignored to protect your API keys.

---

### Running the Chatbot

Start the interactive terminal chatbot:
```bash
python chatbot.py
```

#### Example Questions to Try:
- **General Q&A**: *"What is the difference between synchronous and asynchronous programming?"*
- **Flood Risk**: *"What is the flood risk around Galveston, Texas?"*
- **Terrain & Elevation**: *"What is the elevation and slope in Aspen, Colorado?"*
- **Wildfire Risk**: *"What is the wildfire risk around South Lake Tahoe, California?"*
- **Energy / Siting**: *"Check solar potential and terrain for Phoenix, Arizona."*
