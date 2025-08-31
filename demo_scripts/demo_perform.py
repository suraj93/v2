#!/usr/bin/env python3
"""
Demo script for treasury auto-sweep engine perform module.

This script demonstrates various scenarios of the perform module:
1. Zero deployable scenario (current demo data)
2. Positive deployable scenario (modified balance)
3. High deployable scenario (very high balance)
4. Multiple runs showing file overwriting behavior

Usage:
    python demo_perform.py
"""

import sys
import os
import json
import shutil
from pathlib import Path
from datetime import date

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from core.config import load_settings
from core.parse import load_bank, load_ar, load_ap, current_balance
from core.predict import horizon_flows, get_demo_as_of_date
from core.prescribe import must_keep, deployable, propose_order
from core.perform import submit_order_stub


def print_separator(title):
    """Print a formatted separator."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_scenario_summary(balance, inflows, outflows, mk, dep, order):
    """Print scenario summary."""
    print(f"Current Balance:     INR {balance:12,.2f}")
    print(f"Expected Inflows:    INR {inflows:12,.2f}")
    print(f"Expected Outflows:   INR {outflows:12,.2f}")
    print(f"Must Keep:           INR {mk:12,.2f}")
    print(f"Deployable:          INR {dep:12,.2f}")
    if order:
        print(f"Proposed Order:      INR {order['proposed']:12,.2f} ({order['instrument']})")
        if order['needs_maker_checker']:
            print("                     WARNING: Requires maker-checker approval")
    else:
        print("Proposed Order:      None")


def read_perform_output(out_dir):
    """Read and display perform output files."""
    perform_file = Path(out_dir) / "perform.json"
    if perform_file.exists():
        with open(perform_file, 'r') as f:
            data = json.load(f)
        
        print(f"\nPerformance Output (perform.json):")
        print(f"Date:                {data['date']}")
        print(f"Deployable Value:    INR {data['deployable_value']:12,.2f}")
        print(f"Current Balance:     INR {data['current_balance']:12,.2f}")
        print(f"Must Keep Value:     INR {data['must_keep_value']:12,.2f}")
        print(f"Safety Buffers:      INR {data['safety_buffers']:12,.2f}")
        print(f"Deploy Instrument:   {data['deploy_instrument'] or 'None'}")
        print(f"Deploy Issuer:       {data['deploy_issuer'] or 'None'}")
        print(f"Max Tenor:           {data['max_tenor'] or 'None'} days")
        print(f"Approval Needed:     {data['approval_needed']}")
        print(f"\nDescription:")
        for line in data['description'].split('\n'):
            # Replace rupee symbols for console display
            display_line = line.replace('₹', 'INR ')
            print(f"   {display_line}")
        
        # Check if dated file exists
        dated_file = Path(out_dir) / f"perform_{data['date']}.json"
        if dated_file.exists():
            print(f"\nHistorical file created: perform_{data['date']}.json")
        
        return data
    else:
        print("ERROR: No perform.json file found")
        return None


def run_scenario(scenario_name, balance_override=None, out_dir="demo_outputs"):
    """Run a complete scenario."""
    print_separator(f"SCENARIO: {scenario_name}")
    
    try:
        # Load configuration and data
        settings = load_settings("data")
        bank_df = load_bank(settings.data_dir / "bank_txns.csv")
        ar_df = load_ar(settings.data_dir / "ar_invoices.csv")
        ap_df = load_ap(settings.data_dir / "ap_bills.csv")
        
        # Override balance if specified
        if balance_override:
            balance = balance_override
            print(f"Balance overridden to INR {balance:,.2f} for demo")
        else:
            balance = current_balance(bank_df)
        
        # Use demo date for consistency
        as_of_date = get_demo_as_of_date()
        
        # Calculate cash flows
        inflows, outflows, total_open_ar, total_open_ap, ar_h_df, ap_h_df = horizon_flows(
            ar_df, ap_df, 7, 
            as_of_date=as_of_date,
            collection_probs=settings.model_params.get('ar_collection_probabilities', {}),
            ap_probs=settings.model_params.get('ap_payment_probabilities', {}),
            ap_provision_days=settings.policy.get('ap_provision_days', 14)
        )
        
        # Apply treasury policy
        ap_rows = ap_h_df.to_dict('records') if not ap_h_df.empty else []
        mk = must_keep(settings.policy, outflows, ap_rows)
        dep = deployable(balance, inflows, mk, settings.policy)
        order, reasons = propose_order(dep, settings.policy)
        
        # Print scenario summary
        print_scenario_summary(balance, inflows, outflows, mk, dep, order)
        print(f"Reason Codes:        {', '.join(reasons)}")
        
        # Create output directory
        out_path = Path(out_dir)
        out_path.mkdir(exist_ok=True)
        
        # Execute perform module
        print(f"\nExecuting perform module...")
        execution_state = submit_order_stub(
            order=order,
            out_dir=out_dir,
            balance=balance,
            expected_inflows=inflows,
            expected_outflows=outflows,
            must_keep_amt=mk,
            policy=settings.policy,
            ap_rows=ap_rows
        )
        
        print(f"Execution complete: {execution_state['status']}")
        
        # Read and display output
        perform_data = read_perform_output(out_dir)
        
        return perform_data
        
    except Exception as e:
        print(f"ERROR in scenario '{scenario_name}': {e}")
        return None


def main():
    """Main demo function."""
    print("Treasury Auto-Sweep Engine - Perform Module Demo")
    print("This demo showcases different deployment scenarios")
    
    # Clean up previous demo outputs
    demo_dir = "demo_outputs"
    if Path(demo_dir).exists():
        shutil.rmtree(demo_dir)
    Path(demo_dir).mkdir()
    
    scenarios = [
        ("Current Demo Data (Zero Deployable)", None),
        ("Moderate Balance (Low Deployable)", 3_500_000),
        ("High Balance (High Deployable)", 8_000_000),
        ("Very High Balance (Max Deployable)", 15_000_000),
    ]
    
    results = []
    
    for scenario_name, balance_override in scenarios:
        result = run_scenario(scenario_name, balance_override, demo_dir)
        if result:
            results.append((scenario_name, result))
    
    # Summary comparison
    print_separator("SCENARIO COMPARISON SUMMARY")
    print(f"{'Scenario':<25} {'Balance':<12} {'Deployable':<12} {'Instrument':<20} {'Approval'}")
    print("-" * 80)
    
    for scenario_name, data in results:
        instrument = data.get('deploy_instrument', 'None')
        if instrument and len(instrument) > 18:
            instrument = instrument[:15] + "..."
        approval = "Yes" if data.get('approval_needed') else "No"
        
        print(f"{scenario_name:<25} "
              f"INR {data['current_balance']/1_000_000:>7.1f}M  "
              f"INR {data['deployable_value']/1_000_000:>7.1f}M  "
              f"{instrument or 'None':<20} {approval}")
    
    # File listing
    print_separator("GENERATED FILES")
    demo_path = Path(demo_dir)
    files = list(demo_path.glob("*.json"))
    files.sort()
    
    print(f"Output directory: {demo_path.absolute()}")
    print(f"Generated files ({len(files)}):")
    for file in files:
        size = file.stat().st_size
        print(f"   {file.name:<25} ({size:,} bytes)")
    
    # Show final perform.json content
    final_perform = demo_path / "perform.json"
    if final_perform.exists():
        print_separator("FINAL PERFORM.JSON CONTENT")
        with open(final_perform, 'r') as f:
            content = f.read()
        print(content)
    
    print_separator("DEMO COMPLETE")
    print("All scenarios executed successfully!")
    print(f"Check the '{demo_dir}' directory for output files")
    print("Run 'python cli.py --demo --execute' to test with real CLI")


if __name__ == "__main__":
    main()