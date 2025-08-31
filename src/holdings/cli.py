"""CLI for holdings database operations."""

import argparse
import json
import sys
from pathlib import Path

from .queries import (
    get_setup_result, get_seed_result, get_clear_result,
    get_holdings_list, get_holdings_totals, get_allocation_result, 
    get_redemption_result, get_accrual_result, get_daily_series,
    get_ytd_totals, get_attribution, get_daily_detail
)


def cmd_setup_db(args):
    """Initialize database and seed with CSV data."""
    result = get_setup_result(args.db_path)
    print(json.dumps(result, indent=2))


def cmd_seed(args):
    """Seed holdings from CSV file."""
    if not Path(args.csv_file).exists():
        print(json.dumps({
            "action": "seed",
            "status": "error",
            "message": f"CSV file not found: {args.csv_file}"
        }), file=sys.stderr)
        sys.exit(1)
    
    result = get_seed_result(args.db_path, args.csv_file, args.overwrite)
    print(json.dumps(result, indent=2))


def cmd_clear(args):
    """Clear all holdings and accrual data."""
    result = get_clear_result(args.db_path)
    print(json.dumps(result, indent=2))


def cmd_list_holdings(args):
    """List all holdings."""
    result = get_holdings_list(args.db_path)
    print(json.dumps(result, indent=2))


def cmd_totals(args):
    """Get holdings totals."""
    result = get_holdings_totals(args.db_path)
    print(json.dumps(result, indent=2))


def cmd_allocate(args):
    """Apply allocation to holding."""
    result = get_allocation_result(args.db_path, args.instrument, args.issuer, args.amount)
    print(json.dumps(result, indent=2))


def cmd_redeem(args):
    """Apply redemption from holdings."""
    try:
        result = get_redemption_result(args.db_path, args.amount, args.selection)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({
            "action": "redeem",
            "status": "error", 
            "message": str(e)
        }), file=sys.stderr)
        sys.exit(1)


def cmd_post_accrual(args):
    """Post daily interest accrual."""
    result = get_accrual_result(args.db_path, args.date)
    print(json.dumps(result, indent=2))


def cmd_daily_series(args):
    """Get daily interest series."""
    result = get_daily_series(args.db_path, args.start_date, args.end_date)
    print(json.dumps(result, indent=2))


def cmd_ytd_totals(args):
    """Get YTD totals."""
    result = get_ytd_totals(args.db_path, args.year)
    print(json.dumps(result, indent=2))


def cmd_attribution(args):
    """Get interest attribution."""
    result = get_attribution(args.db_path, args.start_date, args.end_date)
    print(json.dumps(result, indent=2))


def cmd_daily_detail(args):
    """Get detailed daily accruals showing balances and interest per instrument."""
    result = get_daily_detail(args.db_path, args.start_date, args.end_date)
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Holdings Database CLI")
    parser.add_argument("--db-path", default="holdings_data/treasury.db", 
                       help="Path to SQLite database file")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Setup command
    setup_parser = subparsers.add_parser("setup", help="Initialize database")
    setup_parser.set_defaults(func=cmd_setup_db)
    
    # Seed command
    seed_parser = subparsers.add_parser("seed", help="Seed holdings from CSV")
    seed_parser.add_argument("csv_file", help="Path to CSV file")
    seed_parser.add_argument("--update", dest="overwrite", action="store_false",
                            help="Update mode: add to existing holdings (default is overwrite)")
    seed_parser.add_argument("--overwrite", dest="overwrite", action="store_true", 
                            default=True, help="Overwrite mode: clear DB first (default)")
    seed_parser.set_defaults(func=cmd_seed)
    
    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear all holdings and accrual data")
    clear_parser.set_defaults(func=cmd_clear)
    
    # List command
    list_parser = subparsers.add_parser("list", help="List all holdings")
    list_parser.set_defaults(func=cmd_list_holdings)
    
    # Totals command
    totals_parser = subparsers.add_parser("totals", help="Get holdings totals")
    totals_parser.set_defaults(func=cmd_totals)
    
    # Allocate command
    allocate_parser = subparsers.add_parser("allocate", help="Apply allocation")
    allocate_parser.add_argument("instrument", help="Instrument name")
    allocate_parser.add_argument("issuer", help="Issuer name")
    allocate_parser.add_argument("amount", type=float, help="Amount in rupees")
    allocate_parser.set_defaults(func=cmd_allocate)
    
    # Redeem command
    redeem_parser = subparsers.add_parser("redeem", help="Apply redemption")
    redeem_parser.add_argument("amount", type=float, help="Amount in rupees")
    redeem_parser.add_argument("--selection", default="most_recent_first",
                              choices=["most_recent_first", "oldest_first"],
                              help="Redemption selection strategy")
    redeem_parser.set_defaults(func=cmd_redeem)
    
    # Post accrual command  
    accrual_parser = subparsers.add_parser("post-accrual", help="Post daily interest accrual")
    accrual_parser.add_argument("date", help="Date in YYYY-MM-DD format")
    accrual_parser.set_defaults(func=cmd_post_accrual)
    
    # Daily series command
    series_parser = subparsers.add_parser("daily-series", help="Get daily interest series")
    series_parser.add_argument("start_date", help="Start date in YYYY-MM-DD format")
    series_parser.add_argument("end_date", help="End date in YYYY-MM-DD format")
    series_parser.set_defaults(func=cmd_daily_series)
    
    # YTD totals command
    ytd_parser = subparsers.add_parser("ytd", help="Get YTD totals")
    ytd_parser.add_argument("year", type=int, help="Year (e.g., 2025)")
    ytd_parser.set_defaults(func=cmd_ytd_totals)
    
    # Attribution command
    attr_parser = subparsers.add_parser("attribution", help="Get interest attribution")
    attr_parser.add_argument("start_date", help="Start date in YYYY-MM-DD format")
    attr_parser.add_argument("end_date", help="End date in YYYY-MM-DD format")
    attr_parser.set_defaults(func=cmd_attribution)
    
    # Daily detail command
    detail_parser = subparsers.add_parser("daily-detail", help="Get detailed daily accruals per instrument")
    detail_parser.add_argument("start_date", help="Start date in YYYY-MM-DD format")
    detail_parser.add_argument("end_date", help="End date in YYYY-MM-DD format")
    detail_parser.set_defaults(func=cmd_daily_detail)
    
    args = parser.parse_args()
    
    if not hasattr(args, 'func'):
        parser.print_help()
        sys.exit(1)
    
    try:
        args.func(args)
    except Exception as e:
        print(json.dumps({
            "status": "error",
            "message": str(e)
        }), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()