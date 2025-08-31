#!/usr/bin/env python3
"""
Complete demo script for Holdings Database.

This script demonstrates:
1. Database initialization
2. CSV seeding 
3. Holdings operations (allocate/redeem)
4. Daily accrual posting
5. Query operations (totals, attribution, time series)
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from holdings.db import HoldingsDB


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def print_json(data, title: str = None):
    """Print JSON data with optional title."""
    if title:
        print(f"\n--- {title} ---")
    print(json.dumps(data, indent=2))


def main():
    print("Holdings Database - Complete Demo")
    print("=" * 60)
    
    # Use sample data file
    csv_file = Path(__file__).parent / "sample_holdings.csv"
    db_file = Path(__file__).parent / "demo_treasury.db"
    
    # Clean start - remove existing demo DB
    if db_file.exists():
        db_file.unlink()
        print(f"Removed existing demo database: {db_file}")
    
    # Initialize database
    print_section("1. DATABASE INITIALIZATION")
    db = HoldingsDB(str(db_file))
    print(f"Database initialized at: {db_file}")
    
    # Seed holdings from CSV
    print_section("2. CSV SEEDING")
    if not csv_file.exists():
        print(f"❌ Sample CSV not found: {csv_file}")
        return
    
    result = db.seed_holdings_from_csv(str(csv_file))
    print_json(result, "Seeding Result")
    
    # List initial holdings
    print_section("3. INITIAL HOLDINGS")
    holdings = db.list_holdings()
    print_json({"count": len(holdings), "holdings": holdings}, "All Holdings")
    
    totals = db.get_holdings_totals()
    print_json(totals, "Holdings Totals")
    
    # Apply some transactions
    print_section("4. HOLDINGS OPERATIONS")
    
    # Add allocation
    print("\nAdding Rs.500,000 allocation to Overnight Fund...")
    allocation_result = db.apply_allocation(
        "Overnight Fund - Direct Plan - Growth", 
        "Acme Mutual Fund", 
        500000
    )
    print_json(allocation_result, "Allocation Result")
    
    # Apply redemption
    print("\nRedeeming Rs.200,000...")
    try:
        redemption_result = db.apply_redemption(200000, "most_recent_first")
        print_json(redemption_result, "Redemption Result")
    except Exception as e:
        print_json({"error": str(e)}, "Redemption Error")
    
    # Show updated totals
    updated_totals = db.get_holdings_totals()
    print_json(updated_totals, "Updated Totals")
    
    # Post daily accruals for a week
    print_section("5. DAILY ACCRUAL POSTING")
    
    base_date = datetime(2025, 8, 26)  # Monday
    accrual_dates = []
    
    for i in range(7):  # Post for a week
        accrual_date = base_date + timedelta(days=i)
        date_str = accrual_date.strftime("%Y-%m-%d")
        accrual_dates.append(date_str)
        
        result = db.post_daily_accrual(date_str)
        print(f"{date_str}: {result['accruals_posted']} accruals posted")
    
    # Query daily interest series
    print_section("6. DAILY INTEREST SERIES")
    start_date = accrual_dates[0]
    end_date = accrual_dates[-1]
    
    series = db.get_daily_interest_series(start_date, end_date)
    print_json({
        "date_range": f"{start_date} to {end_date}",
        "count": len(series),
        "series": series
    }, "Daily Interest Series")
    
    # Calculate total for the week
    total_week_interest = sum(day["accrued_paise"] for day in series)
    print(f"\nTotal interest for the week: Rs.{total_week_interest/100:,.4f}")
    
    # YTD totals
    print_section("7. YTD TOTALS")
    ytd_totals = db.get_ytd_totals(2025)
    print_json(ytd_totals, "YTD 2025 Totals")
    
    # Attribution analysis
    print_section("8. INTEREST ATTRIBUTION")
    attribution = db.get_attribution(start_date, end_date)
    print_json({
        "date_range": f"{start_date} to {end_date}",
        "instruments": len(attribution),
        "attribution": attribution
    }, "Interest Attribution")
    
    # Test idempotency - repost same dates
    print_section("9. IDEMPOTENCY TEST")
    print("Re-posting accruals for same dates (should skip duplicates)...")
    
    for date_str in accrual_dates[:3]:  # Test first 3 dates
        result = db.post_daily_accrual(date_str)
        print(f"{date_str}: {result['accruals_posted']} new, {result['accruals_skipped']} skipped")
    
    # Final summary
    print_section("10. FINAL SUMMARY")
    final_holdings = db.list_holdings()
    final_totals = db.get_holdings_totals()
    final_ytd = db.get_ytd_totals(2025)
    
    print_json({
        "database_file": str(db_file),
        "total_holdings": len(final_holdings),
        "total_corpus_rupees": final_totals["total_corpus_rupees"],
        "daily_interest_rupees": final_totals["total_daily_interest_rupees"],
        "ytd_interest_rupees": final_ytd["ytd_accrued_rupees"],
        "accrual_days": final_ytd["accrual_days"]
    }, "Demo Summary")
    
    print("\nDemo completed successfully!")
    print(f"Database saved at: {db_file}")
    print("\nTry these CLI commands:")
    print(f"  python -m src.holdings.cli --db-path {db_file} list")
    print(f"  python -m src.holdings.cli --db-path {db_file} totals")
    print(f"  python -m src.holdings.cli --db-path {db_file} ytd 2025")


if __name__ == "__main__":
    main()