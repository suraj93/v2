"""
Simulated order lifecycle for treasury auto-sweep engine.
"""

import json
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Optional, List


def _generate_description(deployable_amt: float, balance: float, expected_inflows: float, 
                         expected_outflows: float, must_keep_amt: float) -> str:
    """
    Generate a 2-line description explaining the deployable value.
    
    Args:
        deployable_amt: Deployable surplus amount
        balance: Current bank balance
        expected_inflows: Expected AR collections
        expected_outflows: Expected AP payments
        must_keep_amt: Total buffer amount to maintain
        
    Returns:
        Two-line description string
    """
    # Format amounts in millions for readability
    balance_m = balance / 1_000_000
    inflows_m = expected_inflows / 1_000_000
    outflows_m = expected_outflows / 1_000_000
    buffer_m = must_keep_amt / 1_000_000
    deployable_m = deployable_amt / 1_000_000
    
    line1 = f"Deployable value: INR{deployable_m:.1f}M from current balance INR{balance_m:.1f}M, expected AR INR{inflows_m:.1f}M, AP INR{outflows_m:.1f}M, buffer INR{buffer_m:.1f}M."
    
    if deployable_amt > 0:
        if expected_inflows > expected_outflows:
            line2 = "Strong inflow position enables surplus deployment after maintaining prudent safety buffers."
        else:
            line2 = "Limited surplus available due to high outflow requirements and conservative buffer maintenance."
    else:
        if balance < must_keep_amt * 0.8:
            line2 = "No deployment possible - current balance below safety buffer requirements."
        else:
            line2 = "No surplus available after accounting for expected outflows and mandatory buffers."
    
    return f"{line1}\n{line2}"


def _calculate_safety_buffers(policy: Dict, ap_rows: List[Dict], expected_outflows: float) -> float:
    """Calculate total safety buffers amount."""
    base_buffers = (
        policy["min_operating_cash"] + 
        policy["payroll_buffer"] + 
        policy["tax_buffer"]
    )
    
    # Vendor tier buffers
    unique_vendors_by_tier = {}
    for row in ap_rows:
        tier = row.get("vendor_tier", "regular")
        vendor_id = row.get("vendor_id", "")
        if tier not in unique_vendors_by_tier:
            unique_vendors_by_tier[tier] = set()
        unique_vendors_by_tier[tier].add(vendor_id)
    
    vendor_buffers = (
        len(unique_vendors_by_tier.get("critical", set())) * policy["vendor_tier_buffers"]["critical"] +
        len(unique_vendors_by_tier.get("regular", set())) * policy["vendor_tier_buffers"]["regular"]
    )
    
    # Outflow shock buffer
    shock_buffer = policy["outflow_shock_multiplier"] * expected_outflows
    
    return round(base_buffers + vendor_buffers + shock_buffer, 2)


def submit_order_stub(order: Optional[Dict], out_dir: str | Path, balance: float, 
                     expected_inflows: float, expected_outflows: float, must_keep_amt: float,
                     policy: Dict, ap_rows: List[Dict]) -> Dict:
    """
    Generate performance output JSON files and simulate order lifecycle.
    
    Args:
        order: Order dictionary with proposed amount, instrument, issuer (or None)
        out_dir: Output directory path
        balance: Current bank balance
        expected_inflows: Expected AR collections
        expected_outflows: Expected AP payments
        must_keep_amt: Minimum amount to maintain
        policy: Treasury policy configuration
        ap_rows: AP bills data for buffer calculations
        
    Returns:
        Final order state dictionary
    """
    out_path = Path(out_dir)
    out_path.mkdir(exist_ok=True)
    
    # Calculate deployable amount using same logic as prescribe module
    recognition_ratio = policy.get("recognition_ratio_expected_inflows", 0.40)
    deployable_amt = max(0.0, balance + (recognition_ratio * expected_inflows) - must_keep_amt)
    deployable_amt = round(deployable_amt, 2)
    
    # Calculate safety buffers total
    safety_buffers = _calculate_safety_buffers(policy, ap_rows, expected_outflows)
    
    # Generate description
    description = _generate_description(deployable_amt, balance, expected_inflows, expected_outflows, must_keep_amt)
    
    # Get current date for dating files
    current_date = date.today().isoformat()
    
    # Create perform output data
    perform_data = {
        "date": current_date,
        "deployable_value": deployable_amt,
        "current_balance": round(balance, 2),
        "must_keep_value": round(must_keep_amt, 2),
        "safety_buffers": safety_buffers,
        "description": description,
        "deploy_instrument": order["instrument"] if order else None,
        "deploy_issuer": order["issuer"] if order else None,
        "max_tenor": None,
        "approval_needed": True
    }
    
    # Add max_tenor if order exists and instrument is in whitelist
    if order and order.get("instrument"):
        whitelist = policy.get("whitelist", [])
        for instrument in whitelist:
            if instrument["instrument"] == order["instrument"]:
                perform_data["max_tenor"] = instrument.get("max_tenor_days")
                break
    
    # Write summary file (perform.json)
    summary_file = out_path / "perform.json"
    with open(summary_file, 'w') as f:
        json.dump(perform_data, f, indent=2)
    
    # Write dated file (perform_YYYY-MM-DD.json)
    dated_file = out_path / f"perform_{current_date}.json"
    with open(dated_file, 'w') as f:
        json.dump(perform_data, f, indent=2)
    
    # Legacy order simulation (pass-through for compatibility)
    order_state = {
        "status": "pass_through",
        "message": "Order processing deferred - performance output generated",
        "perform_output": perform_data
    }
    
    return order_state

