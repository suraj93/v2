#!/usr/bin/env python3
"""
Demonstration script for the treasury auto-sweep file readers.
This script shows how to use the parse.py module to read CSV files.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, 'src')

from core.config import load_settings
from core.parse import load_bank, load_ar, load_ap, current_balance


def main():
    """Demonstrate the file readers."""
    print("=== Treasury Auto-Sweep File Readers Demo ===\n")
    
    try:
        # Load configuration
        print("1. Loading configuration...")
        settings = load_settings("data")
        print(f"   ✓ Currency: {settings.policy['currency']}")
        print(f"   ✓ Min operating cash: ₹{settings.policy['min_operating_cash']:,.2f}")
        print(f"   ✓ Cutoff hour: {settings.calendar['cutoff_hour_ist']}:00 IST\n")
        
        # Load bank transactions
        print("2. Loading bank transactions...")
        bank_df = load_bank(Path("data/bank_txns.csv"))
        print(f"   ✓ Loaded {len(bank_df)} transactions")
        print(f"   ✓ Date range: {bank_df['date'].min().date()} to {bank_df['date'].max().date()}")
        
        # Calculate current balance
        balance = current_balance(bank_df)
        print(f"   ✓ Current balance: ₹{balance:,.2f}")
        
        # Show sample transactions
        print("\n   Sample transactions:")
        sample_txns = bank_df.tail(3)[['date', 'description', 'amount']]
        for _, row in sample_txns.iterrows():
            print(f"     {row['date'].date()}: {row['description']} - ₹{row['amount']:,.2f}")
        
        # Load AR invoices
        print("\n3. Loading AR invoices...")
        ar_df = load_ar(Path("data/ar_invoices.csv"))
        print(f"   ✓ Loaded {len(ar_df)} invoices")
        
        # Show AR summary
        open_invoices = ar_df[ar_df['status'] == 'open']
        paid_invoices = ar_df[ar_df['status'] == 'paid']
        print(f"   ✓ Open invoices: {len(open_invoices)}")
        print(f"   ✓ Paid invoices: {len(paid_invoices)}")
        print(f"   ✓ Total AR amount: ₹{ar_df['amount'].sum():,.2f}")
        
        # Load AP bills
        print("\n4. Loading AP bills...")
        ap_df = load_ap(Path("data/ap_bills.csv"))
        print(f"   ✓ Loaded {len(ap_df)} bills")
        
        # Show AP summary
        open_bills = ap_df[ap_df['status'] == 'open']
        paid_bills = ap_df[ap_df['status'] == 'paid']
        print(f"   ✓ Open bills: {len(open_bills)}")
        print(f"   ✓ Paid bills: {len(paid_bills)}")
        print(f"   ✓ Total AP amount: ₹{ap_df['amount'].sum():,.2f}")
        
        # Show vendor tier breakdown
        if 'vendor_tier' in ap_df.columns:
            tier_counts = ap_df['vendor_tier'].value_counts()
            print(f"   ✓ Vendor tiers: {dict(tier_counts)}")
        
        print("\n=== Demo completed successfully! ===")
        print("\nNext steps:")
        print("1. Implement predict.py for cash flow forecasting")
        print("2. Implement prescribe.py for policy calculations")
        print("3. Implement present.py for EOD summaries")
        print("4. Run: python -m src.cli --data-dir data --out-dir outputs --horizon 7")
        
    except Exception as e:
        print(f"Error during demo: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
