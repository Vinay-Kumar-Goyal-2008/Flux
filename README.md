# Flux - Flood Inundation & Waterlogging Polygon Predictions

This repository contains SegFormer MiT-B2 deep learning model inference predictions for 30 US Counties across Pennsylvania, Ohio, South Carolina, West Virginia, North Carolina, Florida, and Indiana.

## Structure
- `us_counties_flood_predictions.json`: Master dataset containing all 30 US counties.
- `us_flood_polygons/`: Individual county JSON files.

## Coordinate Format
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

