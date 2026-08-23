import os
import json
import requests
from datetime import datetime

from shapely.geometry import Polygon, Point, MultiPolygon
from shapely.ops import transform
import pyproj
from dotenv import load_dotenv


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

MIREYE_URL = "https://api.mireye.com/v1/fetch"
MIREYE_TOKEN = os.environ["MIREYE_API_TOKEN"]

INPUT_FILE = "us_counties_flood_predictions.json"
OUTPUT_FILE = "mireye_flood_report.json"


# ============================================================
# MIREYE FIELDS
# ============================================================

MIREYE_FIELDS = [
    "elevation",
    "slope_degrees",
    "coast_distance_m",
    "within_floodplain_polygon",
    "intersects_nhd_area",
    "nearest_flowline_name",
    "nearest_waterbody_name",
    "primary_building_height_m",
    "primary_building_num_floors",
    "primary_building_footprint_sqm",
    "primary_building_overture_class",
]


# ============================================================
# LOAD INPUT JSON
# ============================================================

def load_flood_predictions(filename):
    """
    Load flood prediction data.

    Expected format:

    [
        {
            "place": "Bucks County, Pennsylvania",
            "flood_coordinates": [
                [longitude, latitude],
                ...
            ],
            "spacing_m": 1000,
            "classification": "Waterlogging",
            "area_sq_km": 0.23
        }
    ]
    """

    with open(filename, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(
            "Input JSON must contain a list of flood predictions."
        )

    return data


# ============================================================
# LOAD EXISTING OUTPUT / CHECKPOINT
# ============================================================

def load_existing_output(filename):
    """
    Load an existing Mireye output file.

    Returns:
        Existing output dictionary if available.
        None if the file does not exist or is invalid.

    IMPORTANT:
    We intentionally do not delete or overwrite the existing
    checkpoint before processing starts.
    """

    if not os.path.exists(filename):
        print("\nNo existing output file found.")
        print("Starting from the beginning.\n")
        return None

    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            print("\nExisting output is not a valid object.")
            print("Starting from the beginning.\n")
            return None

        regions = data.get("flood_regions", [])

        if not isinstance(regions, list):
            print("\nExisting output has invalid flood_regions.")
            print("Starting from the beginning.\n")
            return None

        print("\n" + "=" * 80)
        print("EXISTING CHECKPOINT FOUND")
        print("=" * 80)
        print(f"Previous regions saved: {len(regions)}")

        completed = sum(
            1
            for region in regions
            if region.get("status") == "completed"
        )

        processing = sum(
            1
            for region in regions
            if region.get("status") in {
                "processing",
                "interrupted",
                "failed"
            }
        )

        print(f"Completed regions      : {completed}")
        print(f"Incomplete regions     : {processing}")
        print("=" * 80)

        return data

    except json.JSONDecodeError as e:
        print("\nWARNING: Existing output JSON is corrupted.")
        print(f"JSON error: {e}")
        print("Starting from the beginning.\n")
        return None

    except Exception as e:
        print("\nWARNING: Could not load existing output.")
        print(f"Error: {e}")
        print("Starting from the beginning.\n")
        return None


# ============================================================
# POLYGON
# ============================================================

def polygon_from_coordinates(coordinates):
    """
    Convert [longitude, latitude] coordinates
    into a Shapely Polygon or MultiPolygon.
    """

    if len(coordinates) < 3:
        raise ValueError(
            "A polygon requires at least 3 coordinates."
        )

    coordinates = [
        list(coord)
        for coord in coordinates
    ]

    # Close polygon if necessary
    if coordinates[0] != coordinates[-1]:
        coordinates.append(coordinates[0])

    polygon = Polygon(coordinates)

    # Repair invalid geometry
    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    if polygon.is_empty:
        raise ValueError(
            "Invalid or empty polygon."
        )

    return polygon


# ============================================================
# CRS TRANSFORMERS
# ============================================================

TO_WEB_MERCATOR = pyproj.Transformer.from_crs(
    "EPSG:4326",
    "EPSG:3857",
    always_xy=True
).transform

TO_WGS84 = pyproj.Transformer.from_crs(
    "EPSG:3857",
    "EPSG:4326",
    always_xy=True
).transform


# ============================================================
# GET POLYGON PARTS
# ============================================================

def get_polygon_parts(polygon):
    """
    Return individual Polygon objects.
    Handles both Polygon and MultiPolygon.
    """

    if isinstance(polygon, Polygon):
        return [polygon]

    if isinstance(polygon, MultiPolygon):
        return list(polygon.geoms)

    raise ValueError(
        f"Unsupported geometry type: {polygon.geom_type}"
    )


# ============================================================
# INTERIOR SAMPLE POINTS
# ============================================================

def get_interior_sample_points(
    polygon,
    initial_spacing_m=1000,
    minimum_points=20,
    maximum_points=10000
):
    """
    Generate dense interior sampling points.

    The spacing automatically becomes smaller if the
    polygon is too small to produce enough points.

    Returns:
        List of (latitude, longitude)
    """

    polygon_m = transform(
        TO_WEB_MERCATOR,
        polygon
    )

    polygon_parts = get_polygon_parts(
        polygon_m
    )

    # --------------------------------------------------------
    # Start with requested spacing
    # --------------------------------------------------------

    spacing_m = initial_spacing_m

    while True:

        points = []

        # ----------------------------------------------------
        # Generate grid
        # ----------------------------------------------------

        for part in polygon_parts:

            minx, miny, maxx, maxy = part.bounds

            x = minx + spacing_m / 2

            while x < maxx:

                y = miny + spacing_m / 2

                while y < maxy:

                    point = Point(x, y)

                    if part.contains(point):

                        lon, lat = TO_WGS84(
                            point.x,
                            point.y
                        )

                        points.append(
                            (lat, lon)
                        )

                    y += spacing_m

                x += spacing_m

        # ----------------------------------------------------
        # Enough points?
        # ----------------------------------------------------

        if len(points) >= minimum_points:
            break

        # ----------------------------------------------------
        # Make grid 2x denser
        # ----------------------------------------------------

        spacing_m = spacing_m / 2

        # Prevent absurdly small spacing
        if spacing_m < 25:
            break

    # --------------------------------------------------------
    # Small polygon fallback
    # --------------------------------------------------------

    if not points:

        for part in polygon_parts:

            representative = part.representative_point()

            lon, lat = TO_WGS84(
                representative.x,
                representative.y
            )

            points.append(
                (lat, lon)
            )

    # --------------------------------------------------------
    # Maximum point safety limit
    # --------------------------------------------------------

    if len(points) > maximum_points:

        step = len(points) / maximum_points

        points = [
            points[
                min(
                    int(i * step),
                    len(points) - 1
                )
            ]
            for i in range(maximum_points)
        ]

    print(
        f"Adaptive spacing used: "
        f"{spacing_m:.1f} m"
    )

    return points


# ============================================================
# MIREYE API
# ============================================================

def fetch_mireye(
    lat,
    lon,
    fields
):
    """
    Fetch Mireye data for one coordinate.
    """

    payload = {
        "lat": lat,
        "lng": lon,
        "fields": fields
    }

    response = requests.post(
        MIREYE_URL,
        headers={
            "Authorization": f"Bearer {MIREYE_TOKEN}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=120
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# CLEAN MIREYE RESPONSE
# ============================================================

def extract_mireye_values(response):
    """
    Extract actual field values from Mireye response.
    """

    fields = response.get(
        "fields",
        {}
    )

    clean_data = {}

    for field_name, field_data in fields.items():

        if isinstance(field_data, dict):

            clean_data[field_name] = field_data.get(
                "value"
            )

        else:

            clean_data[field_name] = field_data

    return clean_data


# ============================================================
# QUERY ONE POINT
# ============================================================

def query_point(
    point_id,
    point_type,
    lat,
    lon
):
    """
    Query Mireye for one point.

    API failures are returned as a result instead of
    stopping the entire program.
    """

    print(
        f"[{point_id:05d}] "
        f"{point_type.upper():<8} "
        f"lat={lat:.6f}, "
        f"lng={lon:.6f}"
    )

    try:

        raw_response = fetch_mireye(
            lat,
            lon,
            MIREYE_FIELDS
        )

        clean_data = extract_mireye_values(
            raw_response
        )

        print("    SUCCESS")

        return {
            "point_id": point_id,
            "point_type": point_type,
            "latitude": lat,
            "longitude": lon,
            "data": clean_data,
            "raw_response": raw_response,
            "status": "success"
        }

    except requests.RequestException as e:

        print(
            f"    ERROR: {e}"
        )

        return {
            "point_id": point_id,
            "point_type": point_type,
            "latitude": lat,
            "longitude": lon,
            "data": None,
            "raw_response": None,
            "status": "failed",
            "error": str(e)
        }

    except Exception as e:

        print(
            f"    UNEXPECTED ERROR: {e}"
        )

        return {
            "point_id": point_id,
            "point_type": point_type,
            "latitude": lat,
            "longitude": lon,
            "data": None,
            "raw_response": None,
            "status": "failed",
            "error": str(e)
        }


# ============================================================
# UPDATE REGION COUNTS
# ============================================================

def update_region_counts(region):
    """
    Recalculate successful / failed points from
    the actual saved Mireye results.
    """

    results = region.get(
        "mireye_results",
        []
    )

    region["successful_points"] = sum(
        1
        for item in results
        if item.get("status") == "success"
    )

    region["failed_points"] = sum(
        1
        for item in results
        if item.get("status") == "failed"
    )


# ============================================================
# CHECKPOINT SAVE
# ============================================================

def save_checkpoint(
    output_file,
    flood_regions,
    input_file,
    total_flood_regions,
    default_spacing_m,
    max_points_per_region
):
    """
    Save current progress immediately to disk.

    Uses a temporary file and os.replace() so that the
    main JSON file is not left half-written.
    """

    total_api_calls = 0
    total_successful = 0
    total_failed = 0

    for region in flood_regions:

        mireye_results = region.get(
            "mireye_results",
            []
        )

        total_api_calls += len(
            mireye_results
        )

        total_successful += sum(
            1
            for item in mireye_results
            if item.get("status") == "success"
        )

        total_failed += sum(
            1
            for item in mireye_results
            if item.get("status") == "failed"
        )

    final_result = {
        "metadata": {
            "generated_at":
                datetime.now().isoformat(),

            "input_file":
                input_file,

            "total_flood_regions":
                total_flood_regions,

            "mireye_fields_requested":
                MIREYE_FIELDS,

            "default_spacing_m":
                default_spacing_m,

            "max_points_per_region":
                max_points_per_region
        },

        "summary": {
            "total_api_calls":
                total_api_calls,

            "successful_points":
                total_successful,

            "failed_points":
                total_failed
        },

        "flood_regions":
            flood_regions
    }

    # --------------------------------------------------------
    # Write temporary file
    # --------------------------------------------------------

    temp_file = output_file + ".tmp"

    with open(
        temp_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            final_result,
            f,
            indent=2,
            ensure_ascii=False
        )

        f.flush()

        os.fsync(
            f.fileno()
        )

    # --------------------------------------------------------
    # Atomically replace previous checkpoint
    # --------------------------------------------------------

    os.replace(
        temp_file,
        output_file
    )

    return final_result


# ============================================================
# BUILD REGION STRUCTURE
# ============================================================

def build_region_geometry(
    flood_data,
    default_spacing_m,
    max_points
):
    """
    Reconstruct the exact geometry and sampling points
    for a flood region.

    This is also used when RESUMING an interrupted region.
    """

    place = flood_data.get(
        "place",
        "Unknown"
    )

    coordinates = flood_data.get(
        "flood_coordinates"
    )

    classification = flood_data.get(
        "classification"
    )

    area_sq_km = flood_data.get(
        "area_sq_km"
    )

    if not coordinates:
        raise ValueError(
            f"No flood_coordinates found for {place}"
        )

    spacing_m = flood_data.get(
        "spacing_m",
        default_spacing_m
    )

    # --------------------------------------------------------
    # Create polygon
    # --------------------------------------------------------

    polygon = polygon_from_coordinates(
        coordinates
    )

    # --------------------------------------------------------
    # Boundary points
    # --------------------------------------------------------

    boundary_points = []

    for coord in coordinates:

        lon, lat = coord

        boundary_points.append(
            (lat, lon)
        )

    # --------------------------------------------------------
    # Interior points
    # --------------------------------------------------------

    interior_points = get_interior_sample_points(
        polygon,
        initial_spacing_m=spacing_m,
        minimum_points=30,
        maximum_points=max_points
    )

    # --------------------------------------------------------
    # Polygon coordinates
    # --------------------------------------------------------

    polygon_coordinates = []

    for part in get_polygon_parts(polygon):

        polygon_coordinates.append(
            [
                list(coord)
                for coord in part.exterior.coords
            ]
        )

    return {
        "place": place,

        "classification":
            classification,

        "area_sq_km":
            area_sq_km,

        "spacing_m":
            spacing_m,

        "polygon":
            polygon,

        "boundary_points":
            boundary_points,

        "interior_points":
            interior_points,

        "polygon_coordinates":
            polygon_coordinates
    }


# ============================================================
# CREATE / UPDATE REGION METADATA
# ============================================================

def prepare_region_structure(
    flood_data,
    existing_region,
    geometry
):
    """
    Make sure an existing or new region contains all
    necessary metadata while preserving existing results.
    """

    boundary_points = geometry["boundary_points"]
    interior_points = geometry["interior_points"]

    polygon_coordinates = geometry[
        "polygon_coordinates"
    ]

    # --------------------------------------------------------
    # If existing region exists, preserve it.
    # Otherwise create a new one.
    # --------------------------------------------------------

    if existing_region is not None:

        region = existing_region

        # Update basic metadata
        region["place"] = flood_data.get(
            "place",
            "Unknown"
        )

        region["classification"] = flood_data.get(
            "classification"
        )

        region["area_sq_km"] = flood_data.get(
            "area_sq_km"
        )

        # If these fields were missing because the program
        # stopped before geometry was written, add them.
        region["sampling"] = {
            "spacing_m":
                geometry["spacing_m"],

            "boundary_points":
                len(boundary_points),

            "interior_points":
                len(interior_points),

            "total_points":
                len(boundary_points)
                + len(interior_points)
        }

        region["flood_polygon"] = {
            "type":
                (
                    "Polygon"
                    if len(polygon_coordinates) == 1
                    else "MultiPolygon"
                ),

            "coordinates":
                polygon_coordinates
        }

        region["boundary_coordinates"] = [
            {
                "latitude": lat,
                "longitude": lon
            }
            for lat, lon in boundary_points
        ]

        region["interior_sample_points"] = [
            {
                "latitude": lat,
                "longitude": lon
            }
            for lat, lon in interior_points
        ]

        if "mireye_results" not in region:
            region["mireye_results"] = []

        update_region_counts(region)

        return region

    # --------------------------------------------------------
    # New region
    # --------------------------------------------------------

    region = {
        "place":
            flood_data.get(
                "place",
                "Unknown"
            ),

        "classification":
            flood_data.get(
                "classification"
            ),

        "area_sq_km":
            flood_data.get(
                "area_sq_km"
            ),

        "status":
            "processing",

        "sampling": {
            "spacing_m":
                geometry["spacing_m"],

            "boundary_points":
                len(boundary_points),

            "interior_points":
                len(interior_points),

            "total_points":
                len(boundary_points)
                + len(interior_points)
        },

        "flood_polygon": {
            "type":
                (
                    "Polygon"
                    if len(polygon_coordinates) == 1
                    else "MultiPolygon"
                ),

            "coordinates":
                polygon_coordinates
        },

        "boundary_coordinates": [
            {
                "latitude": lat,
                "longitude": lon
            }
            for lat, lon in boundary_points
        ],

        "interior_sample_points": [
            {
                "latitude": lat,
                "longitude": lon
            }
            for lat, lon in interior_points
        ],

        "mireye_results":
            [],

        "successful_points":
            0,

        "failed_points":
            0
    }

    return region


# ============================================================
# PROCESS / RESUME ONE REGION
# ============================================================

def process_flood_region(
    flood_data,
    existing_region=None,
    default_spacing_m=500,
    max_points=10000,
    progress_callback=None
):
    """
    Process one flood region.

    RESUME LOGIC:

    - Existing successful point IDs are skipped.
    - Existing failed point IDs are retried.
    - Completely missing point IDs are queried.
    """

    # --------------------------------------------------------
    # Reconstruct geometry
    # --------------------------------------------------------

    geometry = build_region_geometry(
        flood_data=flood_data,
        default_spacing_m=default_spacing_m,
        max_points=max_points
    )

    boundary_points = geometry[
        "boundary_points"
    ]

    interior_points = geometry[
        "interior_points"
    ]

    spacing_m = geometry[
        "spacing_m"
    ]

    place = flood_data.get(
        "place",
        "Unknown"
    )

    classification = flood_data.get(
        "classification"
    )

    area_sq_km = flood_data.get(
        "area_sq_km"
    )

    total_points = (
        len(boundary_points)
        +
        len(interior_points)
    )

    # --------------------------------------------------------
    # Prepare existing/new region
    # --------------------------------------------------------

    region = prepare_region_structure(
        flood_data=flood_data,
        existing_region=existing_region,
        geometry=geometry
    )

    # --------------------------------------------------------
    # Existing results
    # --------------------------------------------------------

    existing_results = region.get(
        "mireye_results",
        []
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Build dictionary indexed by point_id.
    #
    # If duplicate point IDs somehow exist in a damaged
    # checkpoint, the LAST one is retained.
    # --------------------------------------------------------

    results_by_id = {}

    for item in existing_results:

        point_id = item.get(
            "point_id"
        )

        if point_id is not None:

            results_by_id[
                int(point_id)
            ] = item

    # --------------------------------------------------------
    # Determine current progress
    # --------------------------------------------------------

    successful_ids = {
        point_id
        for point_id, item in results_by_id.items()
        if item.get("status") == "success"
    }

    failed_ids = {
        point_id
        for point_id, item in results_by_id.items()
        if item.get("status") == "failed"
    }

    print("\n")
    print("=" * 80)
    print(f"PROCESSING / RESUMING: {place}")
    print("=" * 80)

    print(
        f"Classification    : {classification}"
    )

    print(
        f"Flood area        : {area_sq_km} km²"
    )

    print(
        f"Grid spacing      : {spacing_m} m"
    )

    print(
        f"Boundary points   : {len(boundary_points)}"
    )

    print(
        f"Interior points   : {len(interior_points)}"
    )

    print(
        f"Total points      : {total_points}"
    )

    print(
        f"Already successful : {len(successful_ids)}"
    )

    print(
        f"Previously failed  : {len(failed_ids)}"
    )

    print(
        f"Points remaining   : "
        f"{total_points - len(successful_ids)}"
    )

    print("=" * 80)

    # --------------------------------------------------------
    # Query boundary + interior points
    # --------------------------------------------------------

    point_id = 1

    all_points = []

    # Boundary first
    for lat, lon in boundary_points:

        all_points.append(
            (
                point_id,
                "boundary",
                lat,
                lon
            )
        )

        point_id += 1

    # Interior next
    for lat, lon in interior_points:

        all_points.append(
            (
                point_id,
                "interior",
                lat,
                lon
            )
        )

        point_id += 1

    # --------------------------------------------------------
    # Process every expected point
    # --------------------------------------------------------

    for point_id, point_type, lat, lon in all_points:

        existing_item = results_by_id.get(
            point_id
        )

        # ====================================================
        # SUCCESS ALREADY SAVED
        # ====================================================

        if (
            existing_item is not None
            and existing_item.get("status") == "success"
        ):

            print(
                f"[{point_id:05d}] "
                f"{point_type.upper():<8} "
                f"SKIPPED - already successful"
            )

            continue

        # ====================================================
        # FAILED OR MISSING
        #
        # Both are queried again.
        # ====================================================

        if existing_item is not None:

            print(
                f"[{point_id:05d}] "
                f"{point_type.upper():<8} "
                f"RETRYING previous failure"
            )

        # ----------------------------------------------------
        # Query API
        # ----------------------------------------------------

        result = query_point(
            point_id=point_id,
            point_type=point_type,
            lat=lat,
            lon=lon
        )

        # ----------------------------------------------------
        # Replace previous failed result or add new result
        # ----------------------------------------------------

        results_by_id[point_id] = result

        # ----------------------------------------------------
        # Rebuild ordered results
        #
        # This ensures the output remains point_id ordered.
        # ----------------------------------------------------

        region["mireye_results"] = [
            results_by_id[pid]
            for pid in sorted(results_by_id)
        ]

        update_region_counts(
            region
        )

        region["status"] = "processing"

        # ----------------------------------------------------
        # SAVE IMMEDIATELY
        # ----------------------------------------------------

        if progress_callback:

            progress_callback(
                region
            )

    # ========================================================
    # REGION COMPLETE
    # ========================================================

    region["mireye_results"] = [
        results_by_id[pid]
        for pid in sorted(results_by_id)
    ]

    update_region_counts(
        region
    )

    # --------------------------------------------------------
    # Check if every expected point has succeeded
    # --------------------------------------------------------

    successful_count = sum(
        1
        for item in region["mireye_results"]
        if item.get("status") == "success"
    )

    failed_count = sum(
        1
        for item in region["mireye_results"]
        if item.get("status") == "failed"
    )

    if successful_count == total_points:

        region["status"] = "completed"

        # Remove old processing error if present
        region.pop("error", None)

        print("\n")
        print(
            f"COMPLETED: {place}"
        )

        print(
            f"Successful points: {successful_count}"
        )

        print(
            f"Failed points    : {failed_count}"
        )

    else:

        # This can happen if an API call failed.
        # We do NOT pretend that the region is completed.
        region["status"] = "processing"

        print("\n")
        print(
            f"REGION NOT FULLY COMPLETE: {place}"
        )

        print(
            f"Successful points: {successful_count}"
        )

        print(
            f"Failed points    : {failed_count}"
        )

    return region


# ============================================================
# FIND EXISTING REGION
# ============================================================

def find_existing_region(
    existing_regions,
    place
):
    """
    Find a previously saved region using its place name.
    """

    for region in existing_regions:

        if region.get("place") == place:
            return region

    return None


# ============================================================
# PROCESS ALL FLOOD REGIONS
# ============================================================

def process_all_flood_regions(
    input_file,
    output_file,
    default_spacing_m=500,
    max_points_per_region=10000
):
    """
    Process every flood region with full resume support.

    Existing completed regions are skipped.

    Existing incomplete regions are resumed from their
    successful point IDs.

    Progress is saved after EVERY API call.
    """

    # ========================================================
    # LOAD INPUT
    # ========================================================

    flood_predictions = load_flood_predictions(
        input_file
    )

    total_regions = len(
        flood_predictions
    )

    # ========================================================
    # LOAD EXISTING CHECKPOINT
    # ========================================================

    existing_output = load_existing_output(
        output_file
    )

    if existing_output is not None:

        existing_regions = existing_output.get(
            "flood_regions",
            []
        )

    else:

        existing_regions = []

    # ========================================================
    # INITIALIZE RESULTS
    # ========================================================

    all_results = []

    print("\n")
    print("=" * 80)
    print("FLOOD PREDICTION PROCESSING")
    print("=" * 80)

    print(
        f"Flood regions found: {total_regions}"
    )

    print(
        f"Resume file        : {output_file}"
    )

    print("=" * 80)

    # ========================================================
    # PROCESS EACH REGION
    # ========================================================

    for index, flood_data in enumerate(
        flood_predictions,
        start=1
    ):

        place = flood_data.get(
            "place",
            "Unknown"
        )

        print("\n")
        print("=" * 80)
        print(
            f"REGION {index} / {total_regions}: {place}"
        )
        print("=" * 80)

        # ----------------------------------------------------
        # Find existing checkpoint for this region
        # ----------------------------------------------------

        existing_region = find_existing_region(
            existing_regions=existing_regions,
            place=place
        )

        # ====================================================
        # COMPLETED REGION
        # ====================================================

        if (
            existing_region is not None
            and existing_region.get("status") == "completed"
        ):

            print(
                "STATUS: ALREADY COMPLETED"
            )

            print(
                "Skipping all Mireye API calls for this region."
            )

            # Keep existing completed result
            all_results.append(
                existing_region
            )

            continue

        # ====================================================
        # RESUME / NEW REGION
        # ====================================================

        if existing_region is not None:

            previous_results = existing_region.get(
                "mireye_results",
                []
            )

            successful = sum(
                1
                for item in previous_results
                if item.get("status") == "success"
            )

            failed = sum(
                1
                for item in previous_results
                if item.get("status") == "failed"
            )

            print(
                "STATUS: RESUMING"
            )

            print(
                f"Previously saved successful points: "
                f"{successful}"
            )

            print(
                f"Previously saved failed points: "
                f"{failed}"
            )

        else:

            print(
                "STATUS: NEW REGION"
            )

        # ----------------------------------------------------
        # Add existing region to all_results
        #
        # This is done BEFORE processing so that the
        # checkpoint always contains the region.
        # ----------------------------------------------------

        if existing_region is not None:

            region_index = len(
                all_results
            )

            all_results.append(
                existing_region
            )

        else:

            region_index = len(
                all_results
            )

            new_region = {
                "place":
                    place,

                "classification":
                    flood_data.get(
                        "classification"
                    ),

                "area_sq_km":
                    flood_data.get(
                        "area_sq_km"
                    ),

                "status":
                    "processing",

                "mireye_results":
                    [],

                "successful_points":
                    0,

                "failed_points":
                    0
            }

            all_results.append(
                new_region
            )

            existing_region = new_region

        # ====================================================
        # CALLBACK
        # ====================================================

        def save_region_progress(
            region,
            region_index=region_index
        ):
            """
            Save the current state of this region.
            """

            all_results[region_index] = region

            update_region_counts(
                region
            )

            save_checkpoint(
                output_file=output_file,

                flood_regions=all_results,

                input_file=input_file,

                total_flood_regions=
                    total_regions,

                default_spacing_m=
                    default_spacing_m,

                max_points_per_region=
                    max_points_per_region
            )

            successful = region.get(
                "successful_points",
                0
            )

            failed = region.get(
                "failed_points",
                0
            )

            print(
                f"    CHECKPOINT SAVED | "
                f"success={successful} "
                f"failed={failed}"
            )

        # ====================================================
        # PROCESS / RESUME REGION
        # ====================================================

        try:

            result = process_flood_region(
                flood_data=flood_data,

                existing_region=
                    existing_region,

                default_spacing_m=
                    default_spacing_m,

                max_points=
                    max_points_per_region,

                progress_callback=
                    save_region_progress
            )

            # ------------------------------------------------
            # Replace with latest region state
            # ------------------------------------------------

            all_results[
                region_index
            ] = result

            # ------------------------------------------------
            # Final save for this region
            # ------------------------------------------------

            save_checkpoint(
                output_file=output_file,

                flood_regions=all_results,

                input_file=input_file,

                total_flood_regions=
                    total_regions,

                default_spacing_m=
                    default_spacing_m,

                max_points_per_region=
                    max_points_per_region
            )

        except KeyboardInterrupt:

            print("\n")
            print("=" * 80)
            print(
                "PROCESS INTERRUPTED BY USER"
            )
            print("=" * 80)

            # Existing data has already been checkpointed
            # after the previous API call.

            current_region = all_results[
                region_index
            ]

            current_region["status"] = (
                "interrupted"
            )

            update_region_counts(
                current_region
            )

            save_checkpoint(
                output_file=output_file,

                flood_regions=all_results,

                input_file=input_file,

                total_flood_regions=
                    total_regions,

                default_spacing_m=
                    default_spacing_m,

                max_points_per_region=
                    max_points_per_region
            )

            print(
                "Checkpoint preserved."
            )

            print(
                "Restart the program to resume."
            )

            raise

        except Exception as e:

            print("\n")
            print(
                f"ERROR processing {place}: {e}"
            )

            # ------------------------------------------------
            # Preserve all collected data
            # ------------------------------------------------

            current_region = all_results[
                region_index
            ]

            current_region["status"] = (
                "failed"
            )

            current_region["error"] = str(e)

            update_region_counts(
                current_region
            )

            save_checkpoint(
                output_file=output_file,

                flood_regions=all_results,

                input_file=input_file,

                total_flood_regions=
                    total_regions,

                default_spacing_m=
                    default_spacing_m,

                max_points_per_region=
                    max_points_per_region
            )

            print(
                "Checkpoint preserved."
            )

            # Continue with the next region
            continue

    # ========================================================
    # FINAL SAVE
    # ========================================================

    final_result = save_checkpoint(
        output_file=output_file,

        flood_regions=all_results,

        input_file=input_file,

        total_flood_regions=
            total_regions,

        default_spacing_m=
            default_spacing_m,

        max_points_per_region=
            max_points_per_region
    )

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    total_api_calls = sum(
        len(
            region.get(
                "mireye_results",
                []
            )
        )
        for region in all_results
    )

    total_successful = sum(
        region.get(
            "successful_points",
            0
        )
        for region in all_results
    )

    total_failed = sum(
        region.get(
            "failed_points",
            0
        )
        for region in all_results
    )

    completed_regions = sum(
        1
        for region in all_results
        if region.get("status") == "completed"
    )

    incomplete_regions = (
        total_regions
        - completed_regions
    )

    print("\n")
    print("=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)

    print(
        f"Flood regions       : {total_regions}"
    )

    print(
        f"Completed regions   : {completed_regions}"
    )

    print(
        f"Incomplete regions  : {incomplete_regions}"
    )

    print(
        f"Total API calls     : {total_api_calls}"
    )

    print(
        f"Successful points   : {total_successful}"
    )

    print(
        f"Failed points       : {total_failed}"
    )

    print(
        f"\nSaved to: {output_file}"
    )

    print("=" * 80)

    return final_result


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    process_all_flood_regions(
        input_file=INPUT_FILE,

        output_file=OUTPUT_FILE,

        # 500 m grid instead of 1000 m
        # Gives substantially denser coverage.
        default_spacing_m=500,

        # Safety limit per flood region.
        max_points_per_region=10000
    )