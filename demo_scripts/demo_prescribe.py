#!/usr/bin/env python3
"""
Demo script showcasing the prescribe module functionality.
Demonstrates treasury policy calculations with various scenarios.
"""

import json
from datetime import datetime
from src.core.prescribe import must_keep, deployable, propose_order
from src.core.config import load_settings


def format_currency(amount):
    """Format amount as currency string."""
    return f"Rs{amount:,.2f}"


def print_header(title):
    """Print formatted section header."""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")


def print_policy_summary(policy):
    """Print key policy parameters."""
    print("\n[POLICY] POLICY CONFIGURATION:")
    print(f"   * Min Operating Cash: {format_currency(policy['min_operating_cash'])}")
    print(f"   * Payroll Buffer: {format_currency(policy['payroll_buffer'])}")
    print(f"   * Tax Buffer: {format_currency(policy['tax_buffer'])}")
    print(f"   * Vendor Buffers: Critical={format_currency(policy['vendor_tier_buffers']['critical'])}, Regular={format_currency(policy['vendor_tier_buffers']['regular'])}")
    print(f"   * Outflow Shock Multiplier: {policy['outflow_shock_multiplier']}x")
    print(f"   * Recognition Ratio: 98% (hardcoded)")
    print(f"   * Approval Threshold: {format_currency(policy['approval_threshold'])}")
    print(f"   * Cutoff Enforcement: {'Enabled' if policy.get('enforce_cutoff') else 'Disabled'} at {policy.get('cutoff_hour_ist', 14)}:00 IST")


def print_calculation_breakdown(policy, expected_outflows, ap_rows, balance, expected_inflows):
    """Print detailed calculation breakdown."""
    print("\n[CALC] CALCULATION BREAKDOWN:")
    
    # Must Keep Components
    base_buffers = policy["min_operating_cash"] + policy["payroll_buffer"] + policy["tax_buffer"]
    
    from collections import Counter
    vendor_tiers = [row.get("vendor_tier", "regular") for row in ap_rows]
    tier_counts = Counter(vendor_tiers)
    vendor_buffer = (
        tier_counts.get("critical", 0) * policy["vendor_tier_buffers"]["critical"] +
        tier_counts.get("regular", 0) * policy["vendor_tier_buffers"]["regular"]
    )
    
    shock_buffer = policy["outflow_shock_multiplier"] * expected_outflows
    mk = base_buffers + vendor_buffer + shock_buffer
    
    print(f"   Must Keep Calculation:")
    print(f"     Base Buffers: {format_currency(base_buffers)}")
    print(f"     Vendor Buffers: {format_currency(vendor_buffer)} (Critical: {tier_counts.get('critical', 0)}, Regular: {tier_counts.get('regular', 0)})")
    print(f"     Shock Buffer: {format_currency(shock_buffer)} ({policy['outflow_shock_multiplier']}x * {format_currency(expected_outflows)})")
    print(f"     Total Must Keep: {format_currency(mk)}")
    
    # Deployable Calculation
    recognized_inflows = 0.98 * expected_inflows
    available = balance + recognized_inflows - mk
    dep = max(0.0, available)
    
    print(f"\n   Deployable Calculation:")
    print(f"     Current Balance: {format_currency(balance)}")
    print(f"     Recognized Inflows: {format_currency(recognized_inflows)} (98% of {format_currency(expected_inflows)})")
    print(f"     Available: {format_currency(available)} (Balance + Inflows - Must Keep)")
    print(f"     Deployable: {format_currency(dep)} (max(0, Available))")


def run_scenario(name, policy, expected_outflows, ap_rows, balance, expected_inflows):
    """Run a complete scenario and display results."""
    print_header(f"SCENARIO: {name}")
    
    print(f"\n[INPUT] INPUT PARAMETERS:")
    print(f"   * Current Balance: {format_currency(balance)}")
    print(f"   * Expected Inflows (7d): {format_currency(expected_inflows)}")
    print(f"   * Expected Outflows (7d): {format_currency(expected_outflows)}")
    print(f"   * AP Bills in Horizon: {len(ap_rows)} bills")
    if ap_rows:
        from collections import Counter
        tier_counts = Counter(row.get("vendor_tier", "regular") for row in ap_rows)
        print(f"     - Critical vendors: {tier_counts.get('critical', 0)}")
        print(f"     - Regular vendors: {tier_counts.get('regular', 0)}")
    
    # Calculate results
    mk = must_keep(policy, expected_outflows, ap_rows)
    dep = deployable(balance, expected_inflows, mk, policy)
    order, reasons = propose_order(dep, policy)
    
    print_calculation_breakdown(policy, expected_outflows, ap_rows, balance, expected_inflows)
    
    print(f"\n[RESULTS] RESULTS:")
    print(f"   * Must Keep: {format_currency(mk)}")
    print(f"   * Deployable: {format_currency(dep)}")
    
    if order:
        print(f"   * Proposed Order: {format_currency(order['proposed'])}")
        print(f"     - Instrument: {order['instrument']}")
        print(f"     - Issuer: {order['issuer']}")
        print(f"     - Needs Approval: {'Yes' if order['needs_maker_checker'] else 'No'}")
    else:
        print(f"   * Proposed Order: None")
    
    print(f"   * Reason Codes: {', '.join(reasons)}")
    
    # Explain reason codes
    from src.core.reason_codes import REASONS
    print(f"\n[REASON] REASON CODE EXPLANATIONS:")
    for code in reasons:
        if code in REASONS:
            print(f"   * {code}: {REASONS[code]}")


def main():
    """Run prescribe module demonstration."""
    print_header("TREASURY PRESCRIBE MODULE DEMO")
    
    # Load policy configuration
    try:
        settings = load_settings('data')
        policy = settings.policy
    except Exception as e:
        print(f"Error loading settings: {e}")
        return
    
    print_policy_summary(policy)
    print(f"\n[TIME] Current Time: {datetime.now().strftime('%H:%M IST')} (Hour: {datetime.now().hour})")
    
    # Scenario 1: Surplus with successful order
    ap_rows_1 = [
        {"vendor_tier": "critical", "vendor_id": "VEND001"},
        {"vendor_tier": "regular", "vendor_id": "VEND002"}
    ]
    run_scenario(
        "Surplus Available - Order Generated",
        policy,
        expected_outflows=500000,
        ap_rows=ap_rows_1,
        balance=4000000,
        expected_inflows=1200000
    )
    
    # Scenario 2: No surplus
    ap_rows_2 = [
        {"vendor_tier": "critical", "vendor_id": "VEND001"},
        {"vendor_tier": "critical", "vendor_id": "VEND003"},
        {"vendor_tier": "regular", "vendor_id": "VEND002"}
    ]
    run_scenario(
        "No Surplus Available",
        policy,
        expected_outflows=800000,
        ap_rows=ap_rows_2,
        balance=2500000,
        expected_inflows=600000
    )
    
    # Scenario 3: Large order needing approval
    run_scenario(
        "Large Order - Needs Maker-Checker Approval",
        policy,
        expected_outflows=300000,
        ap_rows=[],
        balance=8000000,
        expected_inflows=2000000
    )
    
    # Scenario 4: Cutoff time passed
    policy_cutoff = policy.copy()
    policy_cutoff['enforce_cutoff'] = True
    policy_cutoff['cutoff_hour_ist'] = datetime.now().hour - 1  # Force cutoff
    
    run_scenario(
        "After Cutoff Time - Order Suppressed",
        policy_cutoff,
        expected_outflows=200000,
        ap_rows=[{"vendor_tier": "regular", "vendor_id": "VEND001"}],
        balance=5000000,
        expected_inflows=800000
    )
    
    # Scenario 5: Multiple vendor tiers
    ap_rows_3 = [
        {"vendor_tier": "critical", "vendor_id": "VEND001"},
        {"vendor_tier": "critical", "vendor_id": "VEND002"},
        {"vendor_tier": "critical", "vendor_id": "VEND003"},
        {"vendor_tier": "regular", "vendor_id": "VEND004"},
        {"vendor_tier": "regular", "vendor_id": "VEND005"},
    ]
    run_scenario(
        "Multiple Vendors - High Buffer Requirements",
        policy,
        expected_outflows=1000000,
        ap_rows=ap_rows_3,
        balance=6000000,
        expected_inflows=1500000
    )
    
    # Scenario 6: Successful order (cutoff disabled)
    policy_no_cutoff = policy.copy()
    policy_no_cutoff['enforce_cutoff'] = False
    
    run_scenario(
        "Order Generated Successfully (Cutoff Disabled)",
        policy_no_cutoff,
        expected_outflows=300000,
        ap_rows=[{"vendor_tier": "regular", "vendor_id": "VEND001"}],
        balance=3500000,
        expected_inflows=800000
    )
    
    print_header("DEMO COMPLETE")
    print("\n[SUCCESS] This demo showcased the prescribe module with various scenarios:")
    print("   * Policy-based must_keep calculations")
    print("   * Vendor tier buffer computations")
    print("   * Deployable surplus determination")  
    print("   * Order proposal with cutoff and approval logic")
    print("   * Waterfall allocation through whitelisted instruments")
    print("\n[NEXT] Next steps: Run 'pytest tests/test_prescribe.py -v' to see detailed test cases")


if __name__ == "__main__":
    main()