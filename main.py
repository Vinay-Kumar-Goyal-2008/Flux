"""
main.py
Entry point for the Mireye disaster response pipeline (Day 3-7).

Commands:
    python main.py run      --polygon houston_harvey       # Flood dossier (Day 3-4)
    python main.py evacuate --polygon houston_harvey       # Shelters + routes (Day 6-7)
    python main.py usage                                   # Check API credits
    python main.py catalog                                 # List all 250+ fields
    python main.py quote flood_risk terrain --points 10   # Cost estimate

Demo polygons:
    houston_harvey       -- Hurricane Harvey 2017, Houston TX
    new_orleans_katrina  -- Hurricane Katrina 2005, New Orleans LA
    baton_rouge_2016     -- August 2016 Louisiana floods
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# ── Validate token ─────────────────────────────────────────────────────────────
TOKEN = os.getenv("MIREYE_API_TOKEN", "")
if not TOKEN:
    print("\nNo API token found!")
    print("   Create a .env file with:  MIREYE_API_TOKEN=your_jwt_token_here")
    print("   See .env.example for reference.\n")
    sys.exit(1)

from api.client import MireyeClient, DISASTER_PRESETS
from pipeline.flood_polygon import get_demo_polygon, list_demo_polygons
from pipeline.extractor import extract_flood_dossier
from routing.evacuate import plan_evacuation
from routing.evacuation_engine import run_full_evacuation_pipeline


def cmd_run(args: argparse.Namespace) -> None:
    """Run the extraction pipeline for a flood polygon."""
    try:
        polygon = get_demo_polygon(args.polygon)
    except ValueError as e:
        print(f"\n✗ {e}\n")
        sys.exit(1)

    presets = args.presets if args.presets else DISASTER_PRESETS

    dossier = extract_flood_dossier(
        polygon=polygon,
        presets=presets,
        n_sample_points=args.points,
        use_cache=not args.no_cache,
        verbose=True,
    )

    # Pretty print summary
    print("\n" + "="*60)
    print("  FLOOD SITUATIONAL DOSSIER — SUMMARY")
    print("="*60)
    summary = dossier.summary
    if summary:
        print(json.dumps(summary.model_dump(), indent=2, default=str))

    print(f"\n  Full dossier saved to: output/flood_dossier_{dossier.polygon_hash}.json")


def cmd_check_usage(args: argparse.Namespace) -> None:
    """Check current API credit usage."""
    print("\n  Checking Mireye credit usage...\n")
    with MireyeClient() as client:
        try:
            usage = client.check_usage()
            print(json.dumps(usage, indent=2))
        except Exception as e:
            print(f"ERROR: {e}")


def cmd_catalog(args: argparse.Namespace) -> None:
    """Fetch and display the full field catalog."""
    print("\n  Fetching Mireye field catalog (no auth needed)...\n")
    with MireyeClient() as client:
        try:
            catalog = client.get_field_catalog()
            # Just print field names and units for readability
            fields = catalog.get("fields", {})
            print(f"  Total fields available: {len(fields)}\n")
            for name, meta in list(fields.items())[:30]:  # Show first 30
                unit = meta.get("unit", "—")
                source = meta.get("source", "—")
                print(f"  {name:<45} [{unit}]  — {source}")
            if len(fields) > 30:
                print(f"\n  ... and {len(fields) - 30} more fields.")
        except Exception as e:
            print(f"ERROR: {e}")


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mireye Disaster Response Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command")

    # run
    run_parser = subparsers.add_parser("run", help="Extract flood dossier (Day 3-4)")
    run_parser.add_argument(
        "--polygon", "-p",
        default="houston_harvey",
        choices=list_demo_polygons(),
        help="Demo polygon to use (default: houston_harvey)",
    )
    run_parser.add_argument(
        "--points", "-n",
        type=int,
        default=10,
        help="Number of sample points inside polygon (max 25, default: 10)",
    )
    run_parser.add_argument(
        "--presets",
        nargs="+",
        default=None,
        help="Mireye presets to fetch",
    )
    run_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip cache and always hit the API",
    )

    # evacuate  (Day 6-7)
    evac_parser = subparsers.add_parser("evacuate", help="Find shelters + evacuation routes (Day 6-7)")
    evac_parser.add_argument(
        "--polygon", "-p",
        default="houston_harvey",
        help="Demo or model county polygon (e.g., daviess_county_in, greene_county_in, knox_county_in, etc.)",
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

    # usage
    subparsers.add_parser("usage", help="Check API credit balance")

    # catalog
    subparsers.add_parser("catalog", help="List all available Mireye fields")

    # quote
    quote_parser = subparsers.add_parser("quote", help="Estimate API cost before calling")
    quote_parser.add_argument("presets", nargs="+", help="Presets to quote")
    quote_parser.add_argument("--points", "-n", type=int, default=10, help="Location count")

    args = parser.parse_args()

    # Default to 'run' if no subcommand given
    if args.command is None or args.command == "run":
        if args.command is None:
            args = parser.parse_args(["run"] + sys.argv[1:])
        cmd_run(args)
    elif args.command == "evacuate":
        cmd_evacuate(args)
    elif args.command == "usage":
        cmd_check_usage(args)
    elif args.command == "catalog":
        cmd_catalog(args)
    elif args.command == "quote":
        cmd_quote(args)


if __name__ == "__main__":
    main()
