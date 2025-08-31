#!/usr/bin/env python3
"""
Demonstration script for the cash flow prediction module.
This script shows how the prediction module works with real data.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, 'src')

from core.config import load_settings
from core.parse import load_bank, load_ar, load_ap, current_balance
from core.predict import horizon_flows, get_demo_as_of_date


def main():
    """Demonstrate the cash flow prediction module."""
    print("=== Cash Flow Prediction Module Demo ===\n")
    
    try:
        # Load configuration
        print("1. Loading configuration...")
        settings = load_settings("data")
        print(f"   ✓ Currency: {settings.policy['currency']}")
        print(f"   ✓ AR Collection probabilities: {settings.model_params['ar_collection_probabilities']}")
        print(f"   ✓ AP Payment probabilities: {settings.model_params['ap_payment_probabilities']}\n")
        
        # Load data files
        print("2. Loading data files...")
        bank_df = load_bank(Path("data/bank_txns.csv"))
        ar_df = load_ar(Path("data/ar_invoices.csv"))
        ap_df = load_ap(Path("data/ap_bills.csv"))
        print(f"   ✓ Bank transactions: {len(bank_df)} rows")
        print(f"   ✓ AR invoices: {len(ar_df)} rows")
        print(f"   ✓ AP bills: {len(ap_df)} rows")
        
        # Calculate current balance
        balance = current_balance(bank_df)
        print(f"   ✓ Current balance: ₹{balance:,.2f}\n")
        
        # Demo mode with fixed date
        demo_date = get_demo_as_of_date()
        print(f"3. Demo Mode - Using as-of date: {demo_date}")
        print(f"   This simulates running the system on August 30, 2025\n")
        
        # Test different horizons
        horizons = [3, 7, 14]
        
        for horizon in horizons:
            print(f"4. Testing {horizon}-day horizon...")
            
            inflows, outflows, ar_h_df, ap_h_df = horizon_flows(
                ar_df, ap_df, horizon_days=horizon,
                as_of_date=demo_date,
                collection_probs=settings.model_params['ar_collection_probabilities'],
                ap_probs=settings.model_params['ap_payment_probabilities']
            )
            
            print(f"   ✓ Expected inflows: ₹{inflows:,.2f}")
            print(f"   ✓ Expected outflows: ₹{outflows:,.2f}")
            print(f"   ✓ AR invoices in horizon: {len(ar_h_df)}")
            print(f"   ✓ AP bills in horizon: {len(ap_h_df)}")
            
            # Show sample AR invoices with probabilities
            if len(ar_h_df) > 0:
                print(f"   Sample AR invoices in {horizon}-day horizon:")
                sample_ar = ar_h_df.head(3)[['invoice_id', 'due_date', 'amount', 'days_to_due', 'payment_probability', 'expected_amount']]
                for _, row in sample_ar.iterrows():
                    print(f"     {row['invoice_id']}: Due {row['due_date'].date()} "
                          f"({row['days_to_due']:+d} days), Amount: ₹{row['amount']:,.2f}, "
                          f"Prob: {row['payment_probability']:.2f}, Expected: ₹{row['expected_amount']:,.2f}")
            
            # Show sample AP bills
            if len(ap_h_df) > 0:
                print(f"   Sample AP bills in {horizon}-day horizon:")
                sample_ap = ap_h_df.head(3)[['bill_id', 'due_date', 'amount']]
                for _, row in sample_ap.iterrows():
                    print(f"     {row['bill_id']}: Due {row['due_date'].date()}, Amount: ₹{row['amount']:,.2f}")
            
            print()
        
        # Show detailed analysis for 7-day horizon
        print("5. Detailed 7-day horizon analysis...")
        inflows, outflows, ar_h_df, ap_h_df = horizon_flows(
            ar_df, ap_df, horizon_days=7,
            as_of_date=demo_date,
            collection_probs=settings.model_params['ar_collection_probabilities'],
            ap_probs=settings.model_params['ap_payment_probabilities']
        )
        
        print(f"   Expected inflows breakdown:")
        if len(ar_h_df) > 0:
            # Group by days to due and show totals
            ar_h_df['days_category'] = ar_h_df['days_to_due'].apply(lambda x: 
                'Overdue' if x < 0 else 
                'Due today' if x == 0 else 
                f'Due in {x} days')
            
            category_totals = ar_h_df.groupby('days_category').agg({
                'amount': 'sum',
                'expected_amount': 'sum',
                'invoice_id': 'count'
            }).round(2)
            
            for category, row in category_totals.iterrows():
                print(f"     {category}: {row['invoice_id']} invoices, "
                      f"Total: ₹{row['amount']:,.2f}, Expected: ₹{row['expected_amount']:,.2f}")
        
        print(f"   Expected outflows breakdown:")
        if len(ap_h_df) > 0:
            ap_total = ap_h_df['amount'].sum()
            print(f"     {len(ap_h_df)} bills due within 7 days: ₹{ap_total:,.2f}")
        
        print(f"\n   Net cash flow: ₹{inflows - outflows:+,.2f}")
        
        print("\n=== Demo completed successfully! ===")
        print("\nNext steps:")
        print("1. Implement prescribe.py for policy calculations")
        print("2. Implement present.py for EOD summaries")
        print("3. Run CLI: python -m src.cli --data-dir data --out-dir outputs --horizon 7 --demo")
        
    except Exception as e:
        print(f"Error during demo: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
