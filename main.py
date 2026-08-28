"""
CLI entrypoint for the Mireye disaster intelligence pipeline.

Subcommands:
  run       — Fetch physical context for a flood polygon (Day 3-5)
  evacuate  — Nearest shelters + elevation-aware evacuation routes (Day 6-7)
  predict   — Predictive flood-prone hazard layer & TWI modeling (Day 8-9)
  usage     — Check remaining Mireye API credits
  catalog   — List available Mireye data fields
  quote     — Estimate credit cost for a query
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from api.client import MireyeClient, MireyeAPIError
from pipeline.extractor import extract_flood_dossier
from pipeline.flood_polygon import get_demo_polygon, DEMO_POLYGONS
from routing.evacuate import plan_evacuation
from routing.evacuation_engine import run_full_evacuation_pipeline
from pipeline.flood_prone import analyze_flood_prone_hazards
from visualization.map_plotter import plot_evacuation_map


def cmd_run(args: argparse.Namespace) -> None:
    """Fetch physical context for a flood polygon and print structured summary."""
    try:
        polygon = get_demo_polygon(args.polygon)
    except ValueError as e:
        print(f"\nERROR: {e}\n")
        sys.exit(1)

    print(f"\nRunning Mireye extraction for: {polygon.name}")
    print(f"Sampling mode: {args.sampling} ({args.num_points} points)")
    print(f"Presets: {args.presets}\n")

    try:
        dossier = extract_flood_dossier(
            polygon=polygon,
            sampling=args.sampling,
            num_interior_points=args.num_points,
            presets=args.presets,
            use_cache=not args.no_cache,
            verbose=True,
        )
    except MireyeAPIError as e:
        print(f"\nAPI ERROR [{e.status_code}]: {e.message}")
        if e.error_code:
            print(f"Error Code: {e.error_code}")
        print("\nTip: Check your MIREYE_API_TOKEN in .env or run: python main.py usage\n")
        sys.exit(1)

    dossier.print_summary()

    out_path = Path("output") / f"dossier_{polygon.name}.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(dossier.to_json_file(out_path), encoding="utf-8")
    print(f"\nFull dossier saved to: {out_path}\n")


def cmd_check_usage(_args: argparse.Namespace) -> None:
    """Check remaining Mireye API credits."""
    print("\n  Checking Mireye API credit balance...\n")
    with MireyeClient() as client:
        try:
            data = client.check_usage()
            plan_obj = data.get("plan", {})
            plan_name = plan_obj.get("name", "Build") if isinstance(plan_obj, dict) else str(plan_obj)
            credits_obj = data.get("credits", {})
            limit = credits_obj.get("included", 25000)
            used = credits_obj.get("used", 0)
            remaining = credits_obj.get("remaining", limit - used)
            period = data.get("period", {})
            start = period.get("start", "")
            end = period.get("end", "")

            print(f"  Plan:             {plan_name}")
            print(f"  Monthly Limit:    {limit:,} credits")
            print(f"  Credits Used:     {used:,} credits")
            print(f"  Remaining:        {remaining:,} credits")
            print(f"  Billing Period:   {start} -> {end}")
            pct = (used / limit * 100) if limit else 0
            print(f"  Utilization:      {pct:.1f}%\n")
        except MireyeAPIError as e:
            print(f"  ERROR [{e.status_code}]: {e.message}\n")


def cmd_catalog(_args: argparse.Namespace) -> None:
    """List all available fields in the Mireye catalog."""
    print("\n  Fetching Mireye field catalog (no auth needed)...\n")
    with MireyeClient() as client:
        try:
            catalog = client.get_field_catalog()
            fields = catalog.get("fields", []) if isinstance(catalog, dict) else catalog
            print(f"  Total fields available: {len(fields)}\n")
            if isinstance(fields, list) and fields and isinstance(fields[0], dict):
                for f in fields[:30]:
                    print(f"  - {f.get('name', 'N/A')}: {f.get('description', '')[:60]}...")
            elif isinstance(fields, dict):
                for name, info in list(fields.items())[:30]:
                    desc = info.get("description", "") if isinstance(info, dict) else str(info)
                    print(f"  - {name}: {desc[:60]}...")
            print(f"\n  (Showing first 30 of {len(fields)} fields)\n")
        except Exception as e:
            print(f"  ERROR: {e}\n")


def cmd_quote(args: argparse.Namespace) -> None:
    """Get a cost estimate for a preset + point count."""
    presets = args.presets if args.presets else ["flood_risk"]
    n = args.points

    print(f"\n  Quoting cost for presets={presets}, locations={n}...\n")
    with MireyeClient() as client:
        try:
            for preset in presets:
                quote = client.quote(preset=preset, num_locations=n)
                print(f"  [{preset}]  -> {json.dumps(quote, indent=2)}")
        except Exception as e:
            print(f"ERROR: {e}")


def cmd_evacuate(args: argparse.Namespace) -> None:
    """Plan evacuation: find top shelters + driving routes for flood building clusters."""
    try:
        polygon = get_demo_polygon(args.polygon)
    except ValueError as e:
        print(f"\nERROR: {e}\n")
        sys.exit(1)

    if args.multi_cluster:
        run_full_evacuation_pipeline(
            polygon=polygon,
            n_shelters_per_cluster=args.top,
            generate_html_map=True,
            verbose=True
        )
        return

    plan = plan_evacuation(
        polygon=polygon,
        top_n=args.top,
        radius_m=args.radius * 1000,
        enrich_elevation=not args.no_elevation,
        verbose=True,
    )

    print("\n" + "="*60)
    print("  EVACUATION PLAN SUMMARY")
    print("="*60)
    print(f"  Origin:     {plan.origin_lat:.5f}, {plan.origin_lng:.5f}")
    print(f"  Candidates: {plan.total_candidates_found}")
    print(f"  Top shelters found: {len(plan.top_shelters)}\n")

    for rs in plan.top_shelters:
        route_info = "no route"
        if rs.route and rs.route.route_found:
            route_info = f"{rs.route.distance_km} km | {rs.route.duration_min} min drive"
        print(f"  #{rs.rank}: {rs.shelter.name}")
        print(f"       Type:   {rs.shelter.shelter_type} [{rs.shelter.source}]")
        print(f"       Score:  {rs.cost_score:.2f}")
        print(f"       Route:  {route_info}")
        print()

    print(f"  Full plan: output/evacuation_{polygon.name}.json")


def cmd_predict(args: argparse.Namespace) -> None:
    """Day 8-9: Compute Topographic Wetness Index & Predictive Flood-Prone Hazard Model."""
    if getattr(args, "physical_data", None):
        from pipeline.physical_data_hazard_engine import process_physical_data_pipeline
        input_path = Path(args.physical_data)
        process_physical_data_pipeline(input_path)
        return

    try:
        polygon = get_demo_polygon(args.polygon)
    except ValueError as e:
        print(f"\nERROR: {e}\n")
        sys.exit(1)

    grid_dim = int(args.grid_points ** 0.5)
    hazard_data = analyze_flood_prone_hazards(
        polygon=polygon,
        buffer_km=args.buffer,
        grid_dimension=max(3, grid_dim),
        use_live_api=not args.no_live_api,
        verbose=True
    )

    # Render combined interactive HTML map
    poly_coords = [(p.lat, p.lng) for p in polygon.coordinates]
    
    # Load cluster & evacuation data if available
    evac_file = Path("output") / f"evacuation_clusters_{polygon.name}.json"
    clusters = []
    evac_results = []
    if evac_file.exists():
        try:
            evac_data = json.loads(evac_file.read_text(encoding="utf-8"))
            evac_results = evac_data.get("clusters_evacuation_plan", [])
            for res in evac_results:
                clusters.append({
                    "cluster_id": res.get("cluster_id"),
                    "centroid": [res.get("cluster_centroid", {}).get("lat", 0.0), res.get("cluster_centroid", {}).get("lon", 0.0)],
                    "population_estimate": res.get("population_estimate"),
                    "building_count": res.get("building_count")
                })
        except Exception:
            pass

    map_path = plot_evacuation_map(
        polygon_coords=poly_coords,
        clusters=clusters,
        evacuation_results=evac_results,
        hazard_cells=hazard_data.get("predictive_grid_cells", []),
        output_filename=f"predictive_hazard_map_{polygon.name}.html"
    )
    print(f"  [Visual Map] Interactive predictive hazard map saved to: {map_path}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mireye Disaster Intelligence Engine — Flood Inundation & Physical Context Extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # run (Day 3-5)
    run_parser = subparsers.add_parser("run", help="Fetch physical context for a polygon (Day 3-5)")
    run_parser.add_argument(
        "--polygon", "-p",
        default="houston_harvey",
        help="Polygon name to process",
    )
    run_parser.add_argument(
        "--sampling", "-s",
        choices=["centroid", "grid", "boundary", "all"],
        default="grid",
        help="Spatial sampling strategy (default: grid)",
    )
    run_parser.add_argument(
        "--num-points", "-n",
        type=int,
        default=5,
        help="Number of points to sample (default: 5)",
    )
    run_parser.add_argument(
        "--presets",
        nargs="+",
        default=["flood_risk", "natural_hazard", "terrain", "building_lookup"],
        help="Mireye presets to fetch",
    )
    run_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip cache and always hit the API",
    )

    # evacuate (Day 6-7)
    evac_parser = subparsers.add_parser("evacuate", help="Find shelters + evacuation routes (Day 6-7)")
    evac_parser.add_argument(
        "--polygon", "-p",
        default="houston_harvey",
        help="Demo or model county polygon (e.g., philadelphia_county_pa, charleston_county_sc, etc.)",
    )
    evac_parser.add_argument(
        "--top",
        type=int,
        default=2,
        help="Number of top shelters to return per cluster (default: 2)",
    )
    evac_parser.add_argument(
        "--radius",
        type=int,
        default=15,
        help="Search radius in km for OSM shelter lookup (default: 15)",
    )
    evac_parser.add_argument(
        "--no-elevation",
        action="store_true",
        help="Skip Mireye elevation enrichment for faster (cheaper) run",
    )
    evac_parser.add_argument(
        "--multi-cluster", "-m",
        action="store_true",
        default=True,
        help="Run DBSCAN clustering across flood zone buildings and route per cluster",
    )

    # predict (Day 8-9)
    predict_parser = subparsers.add_parser("predict", help="Predictive flood-prone hazard & TWI modeling (Day 8-9)")
    predict_parser.add_argument(
        "--physical-data", "-f",
        default=None,
        help="Path to pre-extracted physical_data.json file to process all regions",
    )
    predict_parser.add_argument(
        "--polygon", "-p",
        default="philadelphia_county_pa",
        help="Target county/polygon for predictive modeling",
    )
    predict_parser.add_argument(
        "--grid-points", "-n",
        type=int,
        default=25,
        help="Dense grid sample count (e.g., 25 or 36)",
    )
    predict_parser.add_argument(
        "--buffer", "-b",
        type=float,
        default=6.0,
        help="Buffer radius in km around flood boundary (default: 6.0km)",
    )
    predict_parser.add_argument(
        "--no-live-api",
        action="store_true",
        help="Use offline fallback without calling Mireye API",
    )

    # usage
    subparsers.add_parser("usage", help="Check API credit balance")

    # catalog
    subparsers.add_parser("catalog", help="List all available Mireye fields")

    # quote
    quote_parser = subparsers.add_parser("quote", help="Estimate API cost before calling")
    quote_parser.add_argument("presets", nargs="+", help="Presets to quote")
    quote_parser.add_argument("--points", "-n", type=int, default=10, help="Location count")

    args = parser.parse_args()

    # Dispatch commands
    if args.command is None or args.command == "run":
        if args.command is None:
            args = parser.parse_args(["run"] + sys.argv[1:])
        cmd_run(args)
    elif args.command == "evacuate":
        cmd_evacuate(args)
    elif args.command == "predict":
        cmd_predict(args)
    elif args.command == "usage":
        cmd_check_usage(args)
    elif args.command == "catalog":
        cmd_catalog(args)
    elif args.command == "quote":
        cmd_quote(args)


if __name__ == "__main__":
    main()
