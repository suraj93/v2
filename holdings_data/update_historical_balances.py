#!/usr/bin/env python3
"""
One-off script to update historical balances in interest_accruals table
and recalculate interest for specific dates.
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime, date, timedelta
import random

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def generate_historical_balances():
    """Generate realistic daily balances from Jan 1 to Aug 30, 2025."""
    start_date = date(2025, 1, 1)
    end_date = date(2025, 8, 30)
    
    # Base balance starts at 4M, grows to 6M by end
    base_start = 4000000  # 40 lakh
    base_end = 6000000    # 60 lakh
    total_days = (end_date - start_date).days + 1
    
    balances = {}
    current_date = start_date
    
    for i in range(total_days):
        # Linear growth with some realistic variation
        progress = i / (total_days - 1)
        base_balance = base_start + (base_end - base_start) * progress
        
        # Add monthly cyclical variation (cash flow patterns)
        monthly_cycle = 0.1 * base_balance * random.uniform(-0.5, 0.5)
        
        # Add weekly variation (smaller)
        weekly_cycle = 0.05 * base_balance * random.uniform(-0.5, 0.5)
        
        # Add daily noise
        daily_noise = 0.02 * base_balance * random.uniform(-0.5, 0.5)
        
        # Calculate final balance (rounded to nearest 100K)
        final_balance = base_balance + monthly_cycle + weekly_cycle + daily_noise
        final_balance = round(final_balance / 100000) * 100000  # Round to 1 lakh
        
        # Ensure minimum 2M, maximum 8M
        final_balance = max(2000000, min(8000000, final_balance))
        
        balances[current_date.isoformat()] = int(final_balance)
        current_date += timedelta(days=1)
    
    return balances

# Generate all historical balances
BALANCE_UPDATES = generate_historical_balances()

INSTRUMENT_NAME = "Liquid Fund - Direct Plan - Growth"
ISSUER = "HDFC Liquid FUnd"  # Note: matches the existing typo in data


def update_historical_balances(db_path: str):
    """Update historical balances and recalculate interest."""
    
    with sqlite3.connect(db_path) as conn:
        conn.execute("BEGIN TRANSACTION")
        
        try:
            # First, check what records exist
            cursor = conn.execute('''
                SELECT as_of_date, opening_amount_paise, expected_annual_rate_bps, 
                       accrual_basis_days, accrued_interest_paise
                FROM interest_accruals 
                WHERE instrument_name = ? AND issuer = ?
                ORDER BY as_of_date
            ''', (INSTRUMENT_NAME, ISSUER))
            
            existing_records = cursor.fetchall()
            print(f"Found {len(existing_records)} existing accrual records for {ISSUER}")
            
            updates_made = 0
            total_dates = len(BALANCE_UPDATES)
            
            print(f"Updating balances for {total_dates} dates...")
            
            for i, (date_str, new_balance_rupees) in enumerate(sorted(BALANCE_UPDATES.items()), 1):
                new_balance_paise = new_balance_rupees * 100
                
                # Check if record exists for this date
                cursor = conn.execute('''
                    SELECT opening_amount_paise, expected_annual_rate_bps, 
                           accrual_basis_days, accrued_interest_paise
                    FROM interest_accruals 
                    WHERE as_of_date = ? AND instrument_name = ? AND issuer = ?
                ''', (date_str, INSTRUMENT_NAME, ISSUER))
                
                record = cursor.fetchone()
                
                if record:
                    old_balance_paise, rate_bps, basis_days, old_interest_paise = record
                    old_balance_rupees = old_balance_paise / 100
                    old_interest_rupees = old_interest_paise / 100
                    
                    # Calculate new interest: floor(amount * rate / (10000 * basis))
                    new_interest_paise = int((new_balance_paise * rate_bps) // (10000 * basis_days))
                    new_interest_rupees = new_interest_paise / 100
                    
                    # Update the record
                    conn.execute('''
                        UPDATE interest_accruals 
                        SET opening_amount_paise = ?,
                            accrued_interest_paise = ?
                        WHERE as_of_date = ? AND instrument_name = ? AND issuer = ?
                    ''', (new_balance_paise, new_interest_paise, date_str, INSTRUMENT_NAME, ISSUER))
                    
                    # Show progress every 50 updates or for first/last few
                    if i <= 3 or i >= total_dates - 2 or i % 50 == 0:
                        print(f"{date_str}: Rs.{old_balance_rupees:,.0f} -> Rs.{new_balance_rupees:,.0f} | "
                              f"Interest: Rs.{old_interest_rupees:.4f} -> Rs.{new_interest_rupees:.4f}")
                    
                    updates_made += 1
                    
                else:
                    print(f"{date_str}: No existing accrual record found - skipping")
            
            if updates_made > 0:
                conn.execute("COMMIT")
                print(f"\nSuccessfully updated {updates_made} accrual records")
                
                # Show summary of changes
                print("\n--- Updated Records Summary ---")
                cursor = conn.execute('''
                    SELECT as_of_date, 
                           ROUND(opening_amount_paise / 100.0, 0) as balance_rupees,
                           ROUND(expected_annual_rate_bps / 100.0, 2) as rate_percent,
                           ROUND(accrued_interest_paise / 100.0, 4) as interest_rupees
                    FROM interest_accruals 
                    WHERE instrument_name = ? AND issuer = ?
                    ORDER BY as_of_date
                ''', (INSTRUMENT_NAME, ISSUER))
                
                for row in cursor.fetchall():
                    print(f"{row[0]}: Rs.{row[1]:,.0f} @ {row[2]:.2f}% = Rs.{row[3]:.4f}/day")
                    
            else:
                conn.execute("ROLLBACK")
                print("No updates made")
                
        except Exception as e:
            conn.execute("ROLLBACK")
            print(f"Error: {e}")
            raise


def create_all_accruals(db_path: str):
    """Create accrual records for all dates that don't exist yet."""
    from holdings.db import HoldingsDB
    
    db = HoldingsDB(db_path)
    created_count = 0
    skipped_count = 0
    
    print("Creating accrual records for all dates...")
    
    for date_str in sorted(BALANCE_UPDATES.keys()):
        try:
            result = db.post_daily_accrual(date_str)
            created_count += result.get('accruals_posted', 0)
            skipped_count += result.get('accruals_skipped', 0)
            
            if (created_count + skipped_count) % 50 == 0:  # Progress update every 50 days
                print(f"  Processed {created_count + skipped_count} days...")
                
        except Exception as e:
            print(f"  Warning: Failed to create accrual for {date_str}: {e}")
    
    print(f"Accrual creation complete: {created_count} created, {skipped_count} already existed")
    return created_count > 0


def main():
    # Set random seed for reproducible balances
    random.seed(42)
    
    # Use the main database path
    db_path = Path(__file__).parent / "treasury.db"
    
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        print("Run some accruals first with: python -m src.holdings.cli post-accrual 2025-08-30")
        return
    
    print(f"Historical Balance Generator")
    print(f"Database: {db_path}")
    print(f"Target: {INSTRUMENT_NAME} ({ISSUER})")
    print(f"Date Range: 2025-01-01 to 2025-08-30 ({len(BALANCE_UPDATES)} days)")
    print(f"Balance Range: Rs.2,000,000 to Rs.8,000,000")
    
    # Show sample of balances
    sample_dates = list(sorted(BALANCE_UPDATES.keys()))[::30]  # Every 30 days
    print("\nSample Balance Changes:")
    for date_str in sample_dates:
        balance = BALANCE_UPDATES[date_str]
        print(f"  {date_str}: Rs.{balance:,}")
    print("  ... (and similar for all 242 days)")
    
    confirm = input(f"\nThis will:\n1. Create accrual records for all {len(BALANCE_UPDATES)} dates\n2. Update HDFC fund balances with generated values\n\nProceed? (y/N): ")
    if confirm.lower() != 'y':
        print("Cancelled.")
        return
    
    # Step 1: Create accrual records for all dates
    accruals_created = create_all_accruals(str(db_path))
    
    if not accruals_created:
        print("No new accruals created. Existing records will be updated.")
    
    # Step 2: Update historical balances
    print(f"\nUpdating {len(BALANCE_UPDATES)} historical balances...")
    update_historical_balances(str(db_path))


if __name__ == "__main__":
    main()