import json
import math
from collections import Counter
from statistics import mean

from shapely.geometry import Polygon, MultiPolygon, shape
from shapely.ops import transform
from pyproj import Transformer


INPUT_FILE = "mireye_flood_report.json"

OUTPUT_JSON = "affected_object.json"
OUTPUT_TXT = "affected_report.txt"

IDW_POWER = 2.0
IDW_EPSILON_M = 1.0

DEFAULT_PERSONS_PER_RESIDENTIAL_BUILDING = 3.0


EXPECTED_FIELDS = [
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


NUMERIC_FIELDS = [
    "elevation",
    "slope_degrees",
    "coast_distance_m",
    "primary_building_height_m",
    "primary_building_num_floors",
    "primary_building_footprint_sqm",
]


BOOLEAN_FIELDS = [
    "within_floodplain_polygon",
    "intersects_nhd_area",
]


CATEGORICAL_FIELDS = [
    "nearest_flowline_name",
    "nearest_waterbody_name",
    "primary_building_overture_class",
]


def load_input_json(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_boundary_coordinates(region):
    boundary = region.get("boundary_coordinates")

    if boundary:
        coordinates = []

        for item in boundary:
            if isinstance(item, dict):
                lat = item.get("latitude")
                lon = item.get("longitude")

                if lat is not None and lon is not None:
                    coordinates.append(
                        [float(lon), float(lat)]
                    )

            elif isinstance(item, (list, tuple)):
                if len(item) >= 2:
                    coordinates.append(
                        [
                            float(item[0]),
                            float(item[1])
                        ]
                    )

        if len(coordinates) >= 3:
            return coordinates

    polygon_data = region.get("flood_polygon")

    if polygon_data:
        polygon_type = polygon_data.get("type")
        coords = polygon_data.get("coordinates")

        if polygon_type == "Polygon":
            if (
                isinstance(coords, list)
                and len(coords) > 0
                and len(coords[0]) >= 3
            ):
                return [
                    [
                        float(point[0]),
                        float(point[1])
                    ]
                    for point in coords[0]
                ]

        if polygon_type == "MultiPolygon":
            polygons = []

            for polygon_coords in coords or []:
                if (
                    isinstance(polygon_coords, list)
                    and len(polygon_coords) > 0
                    and len(polygon_coords[0]) >= 3
                ):
                    polygons.append(
                        [
                            [
                                float(point[0]),
                                float(point[1])
                            ]
                            for point in polygon_coords[0]
                        ]
                    )

            if polygons:
                return polygons

    raise ValueError(
        "Could not find flood polygon boundary."
    )


def build_polygon(region):
    polygon_data = region.get("flood_polygon")

    if polygon_data:
        try:
            polygon = shape(polygon_data)

            if not polygon.is_valid:
                polygon = polygon.buffer(0)

            if not polygon.is_empty:
                return polygon

        except Exception:
            pass

    boundary = extract_boundary_coordinates(region)

    if (
        boundary
        and isinstance(boundary[0], list)
        and len(boundary[0]) > 0
        and isinstance(boundary[0][0], list)
    ):
        polygons = []

        for ring in boundary:
            polygons.append(
                Polygon(ring)
            )

        polygon = MultiPolygon(
            polygons
        )

    else:
        polygon = Polygon(boundary)

    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    if polygon.is_empty:
        raise ValueError(
            "Flood polygon is invalid or empty."
        )

    return polygon


def calculate_polygon_area_sqkm(region):
    polygon = build_polygon(region)

    transformer = Transformer.from_crs(
        "EPSG:4326",
        "EPSG:3857",
        always_xy=True
    )

    polygon_m = transform(
        transformer.transform,
        polygon
    )

    return polygon_m.area / 1_000_000


def calculate_centroid(region):
    polygon = build_polygon(region)

    centroid = polygon.centroid

    return {
        "latitude": centroid.y,
        "longitude": centroid.x
    }


def extract_interior_points(region):
    points = []

    for item in region.get(
        "interior_sample_points",
        []
    ):
        if isinstance(item, dict):
            lat = item.get("latitude")
            lon = item.get("longitude")

            if lat is not None and lon is not None:
                points.append(
                    (
                        float(lat),
                        float(lon)
                    )
                )

        elif isinstance(item, (list, tuple)):
            if len(item) >= 2:
                points.append(
                    (
                        float(item[1]),
                        float(item[0])
                    )
                )

    return points


def haversine_distance_m(
    lat1,
    lon1,
    lat2,
    lon2
):
    R = 6_371_000.0

    lat1 = float(lat1)
    lon1 = float(lon1)
    lat2 = float(lat2)
    lon2 = float(lon2)

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    dphi = math.radians(
        lat2 - lat1
    )

    dlambda = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(dphi / 2.0) ** 2
        +
        math.cos(phi1)
        *
        math.cos(phi2)
        *
        math.sin(dlambda / 2.0) ** 2
    )

    a = max(
        0.0,
        min(1.0, a)
    )

    c = 2.0 * math.asin(
        math.sqrt(a)
    )

    return R * c


def get_query_points(region):
    points = []

    for item in region.get(
        "mireye_results",
        []
    ):
        lat = item.get("latitude")
        lon = item.get("longitude")

        if lat is None or lon is None:
            continue

        data = item.get("data")

        if not isinstance(data, dict):
            data = {}

        raw_response = item.get(
            "raw_response"
        )

        successful = (
            isinstance(data, dict)
            and len(data) > 0
        )

        if item.get("status") == "success":
            successful = True

        points.append(
            {
                "point_id": item.get(
                    "point_id"
                ),
                "point_type": item.get(
                    "point_type",
                    "unknown"
                ),
                "latitude": float(lat),
                "longitude": float(lon),
                "status": (
                    "success"
                    if successful
                    else "failed"
                ),
                "data": data,
                "raw_response": raw_response
            }
        )

    return points


def to_float(value):
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:
        value = float(value)

        if math.isfinite(value):
            return value

    except (
        TypeError,
        ValueError
    ):
        pass

    return None


def safe_mean(values):
    clean = [
        float(v)
        for v in values
        if to_float(v) is not None
    ]

    if not clean:
        return None

    return round(
        mean(clean),
        4
    )


def safe_min(values):
    clean = [
        float(v)
        for v in values
        if to_float(v) is not None
    ]

    if not clean:
        return None

    return round(
        min(clean),
        4
    )


def safe_max(values):
    clean = [
        float(v)
        for v in values
        if to_float(v) is not None
    ]

    if not clean:
        return None

    return round(
        max(clean),
        4
    )


def idw_estimate(
    target_lat,
    target_lon,
    observations
):
    weighted_sum = 0.0
    weight_sum = 0.0

    for obs in observations:

        value = to_float(
            obs.get("value")
        )

        if value is None:
            continue

        lat = to_float(
            obs.get("latitude")
        )

        lon = to_float(
            obs.get("longitude")
        )

        if lat is None or lon is None:
            continue

        distance = haversine_distance_m(
            target_lat,
            target_lon,
            lat,
            lon
        )

        if distance <= IDW_EPSILON_M:
            return value

        weight = 1.0 / (
            distance ** IDW_POWER
        )

        weighted_sum += (
            weight * value
        )

        weight_sum += weight

    if weight_sum == 0:
        return None

    return weighted_sum / weight_sum


def collect_field_observations(
    points,
    field
):
    observations = []

    for point in points:

        if point.get("status") != "success":
            continue

        value = point.get(
            "data",
            {}
        ).get(field)

        if value is None:
            continue

        observations.append(
            {
                "point_id": point["point_id"],
                "latitude": point["latitude"],
                "longitude": point["longitude"],
                "value": value
            }
        )

    return observations


def interpolate_numeric_field(
    points,
    field
):
    observations = (
        collect_field_observations(
            points,
            field
        )
    )

    estimated_points = []

    for point in points:

        actual = point.get(
            "data",
            {}
        ).get(field)

        actual_value = to_float(
            actual
        )

        if actual_value is not None:

            estimated_points.append(
                {
                    "point_id": point["point_id"],
                    "point_type": point["point_type"],
                    "latitude": point["latitude"],
                    "longitude": point["longitude"],
                    "value": actual_value,
                    "source": "mireye_api"
                }
            )

            continue

        estimate = idw_estimate(
            point["latitude"],
            point["longitude"],
            observations
        )

        if estimate is not None:

            estimated_points.append(
                {
                    "point_id": point["point_id"],
                    "point_type": point["point_type"],
                    "latitude": point["latitude"],
                    "longitude": point["longitude"],
                    "value": round(
                        estimate,
                        6
                    ),
                    "source": "idw_estimate"
                }
            )

    return {
        "field": field,
        "api_observation_count": len(
            observations
        ),
        "estimated_point_count": sum(
            1
            for p in estimated_points
            if p["source"] == "idw_estimate"
        ),
        "coverage_percentage": round(
            100.0
            *
            len(estimated_points)
            /
            max(len(points), 1),
            2
        ),
        "points": estimated_points
    }


def aggregate_numeric_field(
    field_result
):
    values = [
        p["value"]
        for p in field_result["points"]
        if to_float(p["value"]) is not None
    ]

    if not values:
        return {
            "available": False,
            "count": 0,
            "average": None,
            "minimum": None,
            "maximum": None,
            "sum": None
        }

    return {
        "available": True,
        "count": len(values),
        "average": safe_mean(values),
        "minimum": safe_min(values),
        "maximum": safe_max(values),
        "sum": round(
            sum(values),
            4
        )
    }


def analyze_numeric_fields(points):
    result = {}

    for field in NUMERIC_FIELDS:

        field_result = (
            interpolate_numeric_field(
                points,
                field
            )
        )

        field_result[
            "polygon_aggregate"
        ] = aggregate_numeric_field(
            field_result
        )

        result[field] = field_result

    return result


def analyze_boolean_field(
    points,
    field
):
    observed = []

    for point in points:

        if point.get("status") != "success":
            continue

        value = point.get(
            "data",
            {}
        ).get(field)

        if isinstance(
            value,
            bool
        ):
            observed.append(
                {
                    "point_id": point["point_id"],
                    "latitude": point["latitude"],
                    "longitude": point["longitude"],
                    "value": value
                }
            )

    true_count = sum(
        1
        for x in observed
        if x["value"] is True
    )

    false_count = sum(
        1
        for x in observed
        if x["value"] is False
    )

    estimated_probabilities = []

    for point in points:

        exact = point.get(
            "data",
            {}
        ).get(field)

        if isinstance(
            exact,
            bool
        ):

            probability = (
                1.0
                if exact
                else 0.0
            )

            source = "mireye_api"

        else:

            weighted_sum = 0.0
            weight_sum = 0.0

            for obs in observed:

                distance = haversine_distance_m(
                    point["latitude"],
                    point["longitude"],
                    obs["latitude"],
                    obs["longitude"]
                )

                if distance <= IDW_EPSILON_M:

                    weighted_sum = (
                        1.0
                        if obs["value"]
                        else 0.0
                    )

                    weight_sum = 1.0
                    break

                weight = 1.0 / (
                    distance ** IDW_POWER
                )

                weighted_sum += (
                    weight
                    *
                    (
                        1.0
                        if obs["value"]
                        else 0.0
                    )
                )

                weight_sum += weight

            if weight_sum == 0:
                continue

            probability = (
                weighted_sum
                /
                weight_sum
            )

            source = "idw_estimate"

        estimated_probabilities.append(
            {
                "point_id": point["point_id"],
                "probability_true": round(
                    probability,
                    6
                ),
                "estimated_boolean":
                    probability >= 0.5,
                "source": source
            }
        )

    polygon_probability = None

    if estimated_probabilities:
        polygon_probability = (
            sum(
                x["probability_true"]
                for x in estimated_probabilities
            )
            /
            len(estimated_probabilities)
        )

    total_observed = (
        true_count
        +
        false_count
    )

    return {
        "api_true_count": true_count,
        "api_false_count": false_count,
        "api_observation_count": total_observed,
        "api_true_percentage": round(
            100.0
            *
            true_count
            /
            max(total_observed, 1),
            2
        ),
        "polygon_estimated_true_percentage":
            round(
                100.0
                *
                polygon_probability,
                2
            )
            if polygon_probability is not None
            else None,
        "estimated_points":
            estimated_probabilities
    }


def analyze_categorical_field(
    points,
    field
):
    observations = []

    for point in points:

        if point.get("status") != "success":
            continue

        value = point.get(
            "data",
            {}
        ).get(field)

        if value is None:
            continue

        value = str(value).strip()

        if not value:
            continue

        observations.append(
            {
                "point_id": point["point_id"],
                "latitude": point["latitude"],
                "longitude": point["longitude"],
                "value": value
            }
        )

    counts = Counter(
        x["value"]
        for x in observations
    )

    return {
        "api_observation_count":
            len(observations),

        "unique_value_count":
            len(counts),

        "distribution":
            dict(counts),

        "most_common":
            (
                counts.most_common(1)[0][0]
                if counts
                else None
            ),

        "observations":
            observations
    }


def analyze_buildings(
    points,
    numeric_analysis,
    categorical_analysis
):
    footprint = numeric_analysis[
        "primary_building_footprint_sqm"
    ]["polygon_aggregate"]

    height = numeric_analysis[
        "primary_building_height_m"
    ]["polygon_aggregate"]

    floors = numeric_analysis[
        "primary_building_num_floors"
    ]["polygon_aggregate"]

    building_classes = categorical_analysis[
        "primary_building_overture_class"
    ]

    api_building_observations = 0

    for point in points:

        if point.get("status") != "success":
            continue

        footprint_value = (
            point.get("data", {})
            .get(
                "primary_building_footprint_sqm"
            )
        )

        if to_float(
            footprint_value
        ) is not None:
            api_building_observations += 1

    estimated_building_points = sum(
        1
        for x in numeric_analysis[
            "primary_building_footprint_sqm"
        ]["points"]
        if to_float(x["value"]) is not None
        and x["value"] > 0
    )

    return {
        "api_building_observation_count":
            api_building_observations,

        "estimated_building_observation_count":
            estimated_building_points,

        "total_estimated_building_footprint_sqm":
            footprint["sum"],

        "average_building_footprint_sqm":
            footprint["average"],

        "minimum_building_footprint_sqm":
            footprint["minimum"],

        "maximum_building_footprint_sqm":
            footprint["maximum"],

        "average_building_height_m":
            height["average"],

        "maximum_building_height_m":
            height["maximum"],

        "average_building_floors":
            floors["average"],

        "maximum_building_floors":
            floors["maximum"],

        "building_class_distribution":
            building_classes["distribution"],

        "most_common_building_class":
            building_classes["most_common"],

        "note":
            (
                "Building observations represent sampled "
                "Mireye query locations and are not guaranteed "
                "to represent unique physical buildings."
            )
    }


def calculate_building_density(
    polygon_area_sqkm,
    building_count,
    footprint_sqm
):
    if (
        polygon_area_sqkm is None
        or polygon_area_sqkm <= 0
    ):
        return {
            "buildings_per_sq_km": None,
            "footprint_coverage_percentage": None
        }

    buildings_per_sqkm = (
        building_count
        /
        polygon_area_sqkm
    )

    polygon_area_sqm = (
        polygon_area_sqkm
        *
        1_000_000
    )

    footprint_percentage = (
        100.0
        *
        footprint_sqm
        /
        polygon_area_sqm
        if footprint_sqm is not None
        else None
    )

    return {
        "buildings_per_sq_km":
            round(
                buildings_per_sqkm,
                4
            ),

        "footprint_coverage_percentage":
            round(
                footprint_percentage,
                4
            )
            if footprint_percentage is not None
            else None
    }


def estimate_population(
    building_analysis
):
    building_count = (
        building_analysis[
            "estimated_building_observation_count"
        ]
    )

    residential_keywords = [
        "residential",
        "house",
        "apartments",
        "apartment",
        "multi-family",
        "multifamily",
        "dwelling"
    ]

    distribution = (
        building_analysis[
            "building_class_distribution"
        ]
    )

    residential_count = 0

    for class_name, count in distribution.items():

        name = str(
            class_name
        ).lower()

        if any(
            keyword in name
            for keyword in residential_keywords
        ):
            residential_count += count

    if residential_count == 0:
        residential_count = building_count

    estimated_population = (
        residential_count
        *
        DEFAULT_PERSONS_PER_RESIDENTIAL_BUILDING
    )

    return {
        "available": False,

        "estimate_type":
            "building_based_proxy",

        "estimated_affected_population":
            round(
                estimated_population
            ),

        "residential_building_observations":
            residential_count,

        "persons_per_building_assumption":
            DEFAULT_PERSONS_PER_RESIDENTIAL_BUILDING,

        "warning":
            (
                "This is a rough exposure proxy and not "
                "an official population estimate."
            )
    }


def estimate_critical_facilities(
    categorical_analysis
):
    distribution = (
        categorical_analysis[
            "primary_building_overture_class"
        ]["distribution"]
    )

    facilities = {
        "hospital_like": 0,
        "school_like": 0,
        "police_like": 0,
        "fire_station_like": 0,
        "civic_like": 0
    }

    for class_name, count in distribution.items():

        name = str(
            class_name
        ).lower()

        if "hospital" in name:
            facilities[
                "hospital_like"
            ] += count

        if "school" in name:
            facilities[
                "school_like"
            ] += count

        if "police" in name:
            facilities[
                "police_like"
            ] += count

        if "fire" in name:
            facilities[
                "fire_station_like"
            ] += count

        if (
            "civic" in name
            or "government" in name
            or "public" in name
        ):
            facilities[
                "civic_like"
            ] += count

    return {
        "available": True,

        "observed_class_based_proxies":
            facilities,

        "warning":
            (
                "These are building-class proxies only "
                "and are not verified facility inventories."
            )
    }


def analyze_hydrography(
    boolean_analysis,
    categorical_analysis
):
    nhd = boolean_analysis[
        "intersects_nhd_area"
    ]

    flowlines = categorical_analysis[
        "nearest_flowline_name"
    ]

    waterbodies = categorical_analysis[
        "nearest_waterbody_name"
    ]

    return {
        "nhd_area": nhd,

        "flowlines": flowlines,

        "waterbodies": waterbodies,

        "hydrography_exposure_percentage":
            nhd[
                "polygon_estimated_true_percentage"
            ]
    }


def analyze_terrain(
    numeric_analysis
):
    return {
        "elevation":
            numeric_analysis[
                "elevation"
            ]["polygon_aggregate"],

        "slope":
            numeric_analysis[
                "slope_degrees"
            ]["polygon_aggregate"],

        "coast_distance":
            numeric_analysis[
                "coast_distance_m"
            ]["polygon_aggregate"]
    }


def calculate_risk_indicators(
    terrain,
    floodplain,
    hydrography,
    buildings
):
    floodplain_pct = (
        floodplain[
            "polygon_estimated_true_percentage"
        ]
    )

    hydro_pct = (
        hydrography[
            "hydrography_exposure_percentage"
        ]
    )

    avg_elevation = terrain[
        "elevation"
    ]["average"]

    min_coast = terrain[
        "coast_distance"
    ]["minimum"]

    avg_coast = terrain[
        "coast_distance"
    ]["average"]

    avg_slope = terrain[
        "slope"
    ]["average"]

    building_density = buildings[
        "estimated_building_observation_count"
    ]

    score_components = []

    if floodplain_pct is not None:
        score_components.append(
            min(
                floodplain_pct,
                100
            )
        )

    if hydro_pct is not None:
        score_components.append(
            min(
                hydro_pct,
                100
            )
        )

    if avg_elevation is not None:
        elevation_score = max(
            0,
            min(
                100,
                100 - (
                    avg_elevation * 10
                )
            )
        )

        score_components.append(
            elevation_score
        )

    if min_coast is not None:
        coast_score = max(
            0,
            min(
                100,
                100 - (
                    min_coast / 10
                )
            )
        )

        score_components.append(
            coast_score
        )

    if score_components:
        composite = (
            sum(score_components)
            /
            len(score_components)
        )
    else:
        composite = None

    if composite is None:
        category = "unknown"
    elif composite >= 75:
        category = "very_high"
    elif composite >= 50:
        category = "high"
    elif composite >= 25:
        category = "moderate"
    else:
        category = "low"

    return {
        "composite_exposure_score":
            round(
                composite,
                2
            )
            if composite is not None
            else None,

        "category":
            category,

        "components": {
            "floodplain_percentage":
                floodplain_pct,

            "hydrography_percentage":
                hydro_pct,

            "average_elevation_m":
                avg_elevation,

            "minimum_coast_distance_m":
                min_coast,

            "average_coast_distance_m":
                avg_coast,

            "average_slope_degrees":
                avg_slope,

            "estimated_building_observations":
                building_density
        },

        "methodology":
            (
                "Heuristic exposure index combining "
                "floodplain, hydrography, elevation and "
                "coastal proximity."
            )
    }


def calculate_data_quality(
    points,
    numeric_analysis,
    boolean_analysis,
    categorical_analysis
):
    total = len(points)

    successful = sum(
        1
        for p in points
        if p.get("status") == "success"
    )

    failed = (
        total
        -
        successful
    )

    field_coverage = {}

    for field, result in numeric_analysis.items():

        field_coverage[field] = {
            "api_observations":
                result[
                    "api_observation_count"
                ],

            "final_points":
                len(
                    result["points"]
                ),

            "coverage_percentage":
                result[
                    "coverage_percentage"
                ]
        }

    for field, result in boolean_analysis.items():

        field_coverage[field] = {
            "api_observations":
                result[
                    "api_observation_count"
                ],

            "coverage_percentage":
                round(
                    100.0
                    *
                    result[
                        "api_observation_count"
                    ]
                    /
                    max(total, 1),
                    2
                )
        }

    for field, result in categorical_analysis.items():

        field_coverage[field] = {
            "api_observations":
                result[
                    "api_observation_count"
                ],

            "coverage_percentage":
                round(
                    100.0
                    *
                    result[
                        "api_observation_count"
                    ]
                    /
                    max(total, 1),
                    2
                )
        }

    return {
        "total_query_points":
            total,

        "successful_queries":
            successful,

        "failed_queries":
            failed,

        "overall_query_success_percentage":
            round(
                100.0
                *
                successful
                /
                max(total, 1),
                2
            ),

        "field_coverage":
            field_coverage
    }


def create_enriched_points(
    points,
    numeric_analysis,
    boolean_analysis
):
    enriched = []

    numeric_maps = {}

    for field, result in numeric_analysis.items():

        numeric_maps[field] = {
            x["point_id"]: x
            for x in result["points"]
        }

    boolean_maps = {}

    for field, result in boolean_analysis.items():

        boolean_maps[field] = {
            x["point_id"]: x
            for x in result[
                "estimated_points"
            ]
        }

    for point in points:

        enriched_point = {
            "point_id":
                point["point_id"],

            "point_type":
                point["point_type"],

            "latitude":
                point["latitude"],

            "longitude":
                point["longitude"],

            "api_status":
                point["status"],

            "fields": {}
        }

        for field in NUMERIC_FIELDS:

            item = numeric_maps[
                field
            ].get(
                point["point_id"]
            )

            if item:

                enriched_point[
                    "fields"
                ][field] = {
                    "value":
                        item["value"],

                    "source":
                        item["source"]
                }

        for field in BOOLEAN_FIELDS:

            item = boolean_maps[
                field
            ].get(
                point["point_id"]
            )

            if item:

                enriched_point[
                    "fields"
                ][field] = {
                    "value":
                        item[
                            "estimated_boolean"
                        ],

                    "probability_true":
                        item[
                            "probability_true"
                        ],

                    "source":
                        item["source"]
                }

        for field in CATEGORICAL_FIELDS:

            value = point.get(
                "data",
                {}
            ).get(field)

            if value is not None:

                enriched_point[
                    "fields"
                ][field] = {
                    "value":
                        value,

                    "source":
                        "mireye_api"
                }

        enriched.append(
            enriched_point
        )

    return enriched


def analyze_region(region):
    boundary = extract_boundary_coordinates(
        region
    )

    interior = extract_interior_points(
        region
    )

    points = get_query_points(
        region
    )

    area_sqkm = (
        calculate_polygon_area_sqkm(
            region
        )
    )

    centroid = (
        calculate_centroid(
            region
        )
    )

    numeric_analysis = (
        analyze_numeric_fields(
            points
        )
    )

    boolean_analysis = {}

    for field in BOOLEAN_FIELDS:
        boolean_analysis[field] = (
            analyze_boolean_field(
                points,
                field
            )
        )

    categorical_analysis = {}

    for field in CATEGORICAL_FIELDS:
        categorical_analysis[field] = (
            analyze_categorical_field(
                points,
                field
            )
        )

    terrain = analyze_terrain(
        numeric_analysis
    )

    floodplain = boolean_analysis[
        "within_floodplain_polygon"
    ]

    hydrography = analyze_hydrography(
        boolean_analysis,
        categorical_analysis
    )

    buildings = analyze_buildings(
        points,
        numeric_analysis,
        categorical_analysis
    )

    building_density = (
        calculate_building_density(
            area_sqkm,
            buildings[
                "estimated_building_observation_count"
            ],
            buildings[
                "total_estimated_building_footprint_sqm"
            ]
        )
    )

    population = estimate_population(
        buildings
    )

    facilities = estimate_critical_facilities(
        categorical_analysis
    )

    risk = calculate_risk_indicators(
        terrain,
        floodplain,
        hydrography,
        buildings
    )

    quality = calculate_data_quality(
        points,
        numeric_analysis,
        boolean_analysis,
        categorical_analysis
    )

    enriched_points = create_enriched_points(
        points,
        numeric_analysis,
        boolean_analysis
    )

    boundary_queries = sum(
        1
        for p in points
        if p.get("point_type") == "boundary"
    )

    interior_queries = sum(
        1
        for p in points
        if p.get("point_type") == "interior"
    )

    return {
        "place":
            region.get(
                "place"
            ),

        "classification":
            region.get(
                "classification"
            ),

        "status":
            region.get(
                "status"
            ),

        "event": {
            "flood_polygon_area_sq_km":
                round(
                    area_sqkm,
                    6
                ),

            "centroid":
                centroid,

            "boundary_point_count":
                len(boundary)
                if boundary
                and not isinstance(
                    boundary[0][0]
                    if boundary
                    else None,
                    list
                )
                else sum(
                    len(x)
                    for x in boundary
                ),

            "interior_sample_point_count":
                len(interior),

            "total_query_points":
                len(points),

            "boundary_queries":
                boundary_queries,

            "interior_queries":
                interior_queries,

            "polygon":
                region.get(
                    "flood_polygon"
                )
        },

        "numeric_field_estimates":
            numeric_analysis,

        "boolean_field_estimates":
            boolean_analysis,

        "categorical_field_analysis":
            categorical_analysis,

        "buildings": {
            **buildings,
            "density":
                building_density
        },

        "population":
            population,

        "critical_facilities":
            facilities,

        "terrain":
            terrain,

        "floodplain":
            floodplain,

        "hydrography":
            hydrography,

        "risk_assessment":
            risk,

        "data_quality":
            quality,

        "enriched_query_points":
            enriched_points,

        "raw_mireye_results":
            region.get(
                "mireye_results",
                []
            )
    }


def build_global_summary(regions):
    total_area = sum(
        r["event"][
            "flood_polygon_area_sq_km"
        ]
        or 0
        for r in regions
    )

    total_queries = sum(
        r["data_quality"][
            "total_query_points"
        ]
        for r in regions
    )

    successful_queries = sum(
        r["data_quality"][
            "successful_queries"
        ]
        for r in regions
    )

    failed_queries = sum(
        r["data_quality"][
            "failed_queries"
        ]
        for r in regions
    )

    total_buildings = sum(
        r["buildings"][
            "estimated_building_observation_count"
        ]
        for r in regions
    )

    total_footprint = sum(
        (
            r["buildings"][
                "total_estimated_building_footprint_sqm"
            ]
            or 0
        )
        for r in regions
    )

    total_population = sum(
        r["population"][
            "estimated_affected_population"
        ]
        for r in regions
    )

    risk_scores = [
        r["risk_assessment"][
            "composite_exposure_score"
        ]
        for r in regions
        if r["risk_assessment"][
            "composite_exposure_score"
        ] is not None
    ]

    average_risk = (
        sum(risk_scores)
        /
        len(risk_scores)
        if risk_scores
        else None
    )

    return {
        "region_count":
            len(regions),

        "total_flood_area_sq_km":
            round(
                total_area,
                6
            ),

        "total_query_points":
            total_queries,

        "successful_queries":
            successful_queries,

        "failed_queries":
            failed_queries,

        "overall_success_percentage":
            round(
                100.0
                *
                successful_queries
                /
                max(total_queries, 1),
                2
            ),

        "estimated_building_observations":
            total_buildings,

        "estimated_building_footprint_sqm":
            round(
                total_footprint,
                4
            ),

        "estimated_population_proxy":
            total_population,

        "average_region_exposure_score":
            round(
                average_risk,
                2
            )
            if average_risk is not None
            else None
    }


def build_final_object(input_data):
    regions = input_data.get(
        "flood_regions",
        []
    )

    if not regions:
        raise ValueError(
            "No flood_regions found in input JSON."
        )

    analyzed_regions = []

    for index, region in enumerate(
        regions,
        start=1
    ):
        print(
            f"\nProcessing region "
            f"{index}/{len(regions)}: "
            f"{region.get('place', 'Unknown')}"
        )

        try:
            result = analyze_region(
                region
            )

            analyzed_regions.append(
                result
            )

            print(
                f"  Area: "
                f"{result['event']['flood_polygon_area_sq_km']} km²"
            )

            print(
                f"  Queries: "
                f"{result['data_quality']['total_query_points']}"
            )

            print(
                f"  Successful: "
                f"{result['data_quality']['successful_queries']}"
            )

            print(
                f"  Buildings: "
                f"{result['buildings']['estimated_building_observation_count']}"
            )

            print(
                f"  Risk: "
                f"{result['risk_assessment']['composite_exposure_score']}"
            )

        except Exception as e:
            print(
                f"  ERROR: {e}"
            )

            analyzed_regions.append(
                {
                    "place":
                        region.get(
                            "place"
                        ),

                    "classification":
                        region.get(
                            "classification"
                        ),

                    "status":
                        "analysis_failed",

                    "error":
                        str(e)
                }
            )

    valid_regions = [
        r
        for r in analyzed_regions
        if "event" in r
    ]

    return {
        "metadata": {
            "analysis_type":
                "whole_polygon_affected_area_analysis",

            "source_file":
                INPUT_FILE,

            "mireye_fields_used":
                EXPECTED_FIELDS,

            "idw_power":
                IDW_POWER,

            "region_count":
                len(regions),

            "successfully_analyzed_regions":
                len(valid_regions),

            "failed_analysis_regions":
                len(regions)
                -
                len(valid_regions),

            "analysis_note":
                (
                    "Missing numeric Mireye observations "
                    "are estimated using IDW from available "
                    "observations within the same flood region."
                )
        },

        "global_summary":
            build_global_summary(
                valid_regions
            ),

        "regions":
            analyzed_regions
    }


def save_json(
    affected,
    filename
):
    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            affected,
            f,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"\nSaved JSON: {filename}"
    )


def save_txt(
    affected,
    filename
):
    summary = affected[
        "global_summary"
    ]

    regions = affected[
        "regions"
    ]

    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "=" * 100
            + "\n"
        )

        f.write(
            "MIREYE WHOLE-POLYGON AFFECTED AREA ANALYSIS\n"
        )

        f.write(
            "=" * 100
            + "\n\n"
        )

        f.write(
            "GLOBAL SUMMARY\n"
        )

        f.write(
            "-" * 100
            + "\n"
        )

        f.write(
            f"Flood regions                  : "
            f"{summary['region_count']}\n"
        )

        f.write(
            f"Total flood area               : "
            f"{summary['total_flood_area_sq_km']} km²\n"
        )

        f.write(
            f"Total query points             : "
            f"{summary['total_query_points']}\n"
        )

        f.write(
            f"Successful queries             : "
            f"{summary['successful_queries']}\n"
        )

        f.write(
            f"Failed queries                 : "
            f"{summary['failed_queries']}\n"
        )

        f.write(
            f"Overall success                : "
            f"{summary['overall_success_percentage']}%\n"
        )

        f.write(
            f"Estimated building observations: "
            f"{summary['estimated_building_observations']}\n"
        )

        f.write(
            f"Estimated building footprint   : "
            f"{summary['estimated_building_footprint_sqm']} m²\n"
        )

        f.write(
            f"Estimated population proxy     : "
            f"{summary['estimated_population_proxy']}\n"
        )

        f.write(
            f"Average exposure score         : "
            f"{summary['average_region_exposure_score']}\n"
        )

        f.write(
            "\n"
            + "=" * 100
            + "\n"
        )

        f.write(
            "REGION ANALYSIS\n"
        )

        f.write(
            "=" * 100
            + "\n"
        )

        for index, region in enumerate(
            regions,
            start=1
        ):

            f.write(
                f"\n[{index}] "
                f"{region.get('place', 'Unknown')}\n"
            )

            f.write(
                "-" * 100
                + "\n"
            )

            if "event" not in region:

                f.write(
                    f"Analysis failed: "
                    f"{region.get('error')}\n"
                )

                continue

            event = region[
                "event"
            ]

            terrain = region[
                "terrain"
            ]

            buildings = region[
                "buildings"
            ]

            population = region[
                "population"
            ]

            risk = region[
                "risk_assessment"
            ]

            quality = region[
                "data_quality"
            ]

            floodplain = region[
                "floodplain"
            ]

            hydrography = region[
                "hydrography"
            ]

            f.write(
                f"Classification                : "
                f"{region.get('classification')}\n"
            )

            f.write(
                f"Flood area                    : "
                f"{event['flood_polygon_area_sq_km']} km²\n"
            )

            f.write(
                f"Boundary query points         : "
                f"{event['boundary_queries']}\n"
            )

            f.write(
                f"Interior query points         : "
                f"{event['interior_queries']}\n"
            )

            f.write(
                f"Total query points            : "
                f"{event['total_query_points']}\n"
            )

            f.write(
                "\nTERRAIN\n"
            )

            f.write(
                f"Elevation average             : "
                f"{terrain['elevation']['average']} m\n"
            )

            f.write(
                f"Elevation minimum             : "
                f"{terrain['elevation']['minimum']} m\n"
            )

            f.write(
                f"Elevation maximum             : "
                f"{terrain['elevation']['maximum']} m\n"
            )

            f.write(
                f"Slope average                 : "
                f"{terrain['slope']['average']}°\n"
            )

            f.write(
                f"Slope maximum                 : "
                f"{terrain['slope']['maximum']}°\n"
            )

            f.write(
                f"Coast distance average        : "
                f"{terrain['coast_distance']['average']} m\n"
            )

            f.write(
                f"Coast distance minimum        : "
                f"{terrain['coast_distance']['minimum']} m\n"
            )

            f.write(
                "\nFLOODPLAIN\n"
            )

            f.write(
                f"API true points               : "
                f"{floodplain['api_true_count']}\n"
            )

            f.write(
                f"API false points              : "
                f"{floodplain['api_false_count']}\n"
            )

            f.write(
                f"Estimated true percentage     : "
                f"{floodplain['polygon_estimated_true_percentage']}%\n"
            )

            f.write(
                "\nHYDROGRAPHY\n"
            )

            f.write(
                f"NHD exposure                  : "
                f"{hydrography['hydrography_exposure_percentage']}%\n"
            )

            f.write(
                "\nBUILDINGS\n"
            )

            f.write(
                f"Building observations         : "
                f"{buildings['estimated_building_observation_count']}\n"
            )

            f.write(
                f"Total footprint               : "
                f"{buildings['total_estimated_building_footprint_sqm']} m²\n"
            )

            f.write(
                f"Average footprint             : "
                f"{buildings['average_building_footprint_sqm']} m²\n"
            )

            f.write(
                f"Maximum footprint             : "
                f"{buildings['maximum_building_footprint_sqm']} m²\n"
            )

            f.write(
                f"Average height                : "
                f"{buildings['average_building_height_m']} m\n"
            )

            f.write(
                f"Maximum height                : "
                f"{buildings['maximum_building_height_m']} m\n"
            )

            f.write(
                f"Average floors                : "
                f"{buildings['average_building_floors']}\n"
            )

            f.write(
                f"Maximum floors                : "
                f"{buildings['maximum_building_floors']}\n"
            )

            f.write(
                f"Building density              : "
                f"{buildings['density']['buildings_per_sq_km']} / km²\n"
            )

            f.write(
                f"Footprint coverage            : "
                f"{buildings['density']['footprint_coverage_percentage']}%\n"
            )

            f.write(
                "\nPOPULATION PROXY\n"
            )

            f.write(
                f"Estimated population          : "
                f"{population['estimated_affected_population']}\n"
            )

            f.write(
                f"Residential observations      : "
                f"{population['residential_building_observations']}\n"
            )

            f.write(
                "\nEXPOSURE ASSESSMENT\n"
            )

            f.write(
                f"Composite exposure score      : "
                f"{risk['composite_exposure_score']}\n"
            )

            f.write(
                f"Category                      : "
                f"{risk['category']}\n"
            )

            f.write(
                "\nDATA QUALITY\n"
            )

            f.write(
                f"Total queries                 : "
                f"{quality['total_query_points']}\n"
            )

            f.write(
                f"Successful queries            : "
                f"{quality['successful_queries']}\n"
            )

            f.write(
                f"Failed queries                : "
                f"{quality['failed_queries']}\n"
            )

            f.write(
                f"Success percentage            : "
                f"{quality['overall_query_success_percentage']}%\n"
            )

            f.write(
                "\n"
                + "-" * 100
                + "\n"
            )

        f.write(
            "\n"
            + "=" * 100
            + "\n"
        )

        f.write(
            "END OF REPORT\n"
        )

        f.write(
            "=" * 100
            + "\n"
        )

    print(
        f"Saved report: {filename}"
    )


if __name__ == "__main__":

    print(
        "=" * 80
    )

    print(
        "DAY 5 - WHOLE POLYGON AFFECTED AREA ANALYSIS"
    )

    print(
        "=" * 80
    )

    input_data = load_input_json(
        INPUT_FILE
    )

    regions = input_data.get(
        "flood_regions",
        []
    )

    print(
        f"\nLoaded: {INPUT_FILE}"
    )

    print(
        f"Flood regions: {len(regions)}"
    )

    if not regions:
        raise ValueError(
            "No flood_regions found in mireye_flood_report.json"
        )

    affected = build_final_object(
        input_data
    )

    summary = affected[
        "global_summary"
    ]

    print(
        "\n"
        + "=" * 80
    )

    print(
        "GLOBAL SUMMARY"
    )

    print(
        "=" * 80
    )

    print(
        f"Flood regions: "
        f"{summary['region_count']}"
    )

    print(
        f"Total flood area: "
        f"{summary['total_flood_area_sq_km']} km²"
    )

    print(
        f"Total query points: "
        f"{summary['total_query_points']}"
    )

    print(
        f"Successful queries: "
        f"{summary['successful_queries']}"
    )

    print(
        f"Failed queries: "
        f"{summary['failed_queries']}"
    )

    print(
        f"Overall success: "
        f"{summary['overall_success_percentage']}%"
    )

    print(
        f"Estimated building observations: "
        f"{summary['estimated_building_observations']}"
    )

    print(
        f"Estimated building footprint: "
        f"{summary['estimated_building_footprint_sqm']} m²"
    )

    print(
        f"Estimated population proxy: "
        f"{summary['estimated_population_proxy']}"
    )

    print(
        f"Average exposure score: "
        f"{summary['average_region_exposure_score']}"
    )

    save_json(
        affected,
        OUTPUT_JSON
    )

    save_txt(
        affected,
        OUTPUT_TXT
    )

    print(
        "\n"
        + "=" * 80
    )

    print(
        "DAY 5 ANALYSIS COMPLETE"
    )

    print(
        "=" * 80
    )