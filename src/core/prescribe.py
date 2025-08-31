"""
Policy math and allocation for treasury auto-sweep engine.
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime
from collections import Counter
from src.core.reason_codes import REASONS


def must_keep(policy: Dict, expected_outflows: float, ap_rows: List[Dict]) -> float:
    """
    Calculate the minimum amount that must be kept in the bank account.
    
    Args:
        policy: Treasury policy configuration
        expected_outflows: Expected outflows within horizon
        ap_rows: AP bills within horizon as list of dicts
        
    Returns:
        Minimum amount to keep as float
    """
    # Base buffers
    base_amount = (
        policy["min_operating_cash"] + 
        policy["payroll_buffer"] + 
        policy["tax_buffer"]
    )
    
    # Vendor tier buffers based on unique vendor count per tier
    unique_vendors_by_tier = {}
    for row in ap_rows:
        tier = row.get("vendor_tier", "regular")
        vendor_id = row.get("vendor_id", "")
        if tier not in unique_vendors_by_tier:
            unique_vendors_by_tier[tier] = set()
        unique_vendors_by_tier[tier].add(vendor_id)
    
    vendor_buffer = (
        len(unique_vendors_by_tier.get("critical", set())) * policy["vendor_tier_buffers"]["critical"] +
        len(unique_vendors_by_tier.get("regular", set())) * policy["vendor_tier_buffers"]["regular"]
    )
    
    # Outflow shock buffer
    shock_buffer = policy["outflow_shock_multiplier"] * expected_outflows
    
    total = base_amount + vendor_buffer + shock_buffer
    return round(total, 2)


def deployable(balance: float, expected_inflows: float, must_keep_amt: float, policy: Dict) -> float:
    """
    Calculate deployable surplus amount.
    
    Args:
        balance: Current bank balance
        expected_inflows: Expected inflows within horizon
        must_keep_amt: Minimum amount that must be kept
        policy: Treasury policy configuration
        
    Returns:
        Deployable amount as float (clamped to ≥ 0, rounded to 2dp)
    """
    # Use policy-defined recognition ratio
    recognition_ratio = policy.get("recognition_ratio_expected_inflows", 0.40)
    recognized_inflows = recognition_ratio * expected_inflows
    
    available = balance + recognized_inflows - must_keep_amt
    deployable_amt = max(0.0, available)
    
    return round(deployable_amt, 2)


def propose_order(deployable_amt: float, policy: Dict) -> Tuple[Optional[Dict], List[str]]:
    """
    Propose an investment order based on deployable amount and policy.
    
    Args:
        deployable_amt: Deployable surplus amount
        policy: Treasury policy configuration
        
    Returns:
        Tuple of (order_dict_or_none, reason_codes)
    """
    reason_codes = []
    
    # Always add these base reason codes
    reason_codes.extend(["FIXED_BUFFERS", "OUTFLOW_SHOCK", "CONSERVATIVE_INFLOW"])
    
    # Check if no surplus available
    if deployable_amt <= 0:
        reason_codes.append("NO_SURPLUS")
        return None, reason_codes
    
    # Check cutoff time (all in IST as specified)
    if policy.get("enforce_cutoff", False):
        current_hour_ist = datetime.now().hour  # Assuming system time is IST
        cutoff_hour = policy.get("cutoff_hour_ist", 14)
        
        if current_hour_ist >= cutoff_hour:
            reason_codes.append("CUTOFF_PASSED")
            return None, reason_codes
    
    # Waterfall allocation through whitelist instruments
    whitelist = policy.get("whitelist", [])
    if not whitelist:
        return None, reason_codes
    
    remaining_amount = deployable_amt
    orders = []
    
    for instrument in whitelist:
        if remaining_amount <= 0:
            break
            
        max_for_instrument = instrument.get("max_amount", float('inf'))
        proposed_for_instrument = min(remaining_amount, max_for_instrument)
        
        if proposed_for_instrument > 0:
            orders.append({
                "proposed": round(proposed_for_instrument, 2),
                "instrument": instrument["instrument"],
                "issuer": instrument["issuer"],
                "needs_maker_checker": proposed_for_instrument >= policy.get("approval_threshold", 500000)
            })
            
            remaining_amount -= proposed_for_instrument
    
    reason_codes.append("WL_OK")
    
    # For now, return the first order (primary allocation)
    if orders:
        primary_order = orders[0]
        if primary_order["needs_maker_checker"]:
            reason_codes.append("MAKER_CHECKER")
        return primary_order, reason_codes
    
    return None, reason_codes


def create_deployable_attribution(
    policy: Dict,
    balance: float,
    expected_inflows: float, 
    expected_outflows: float,
    total_open_ar: float,
    total_open_ap: float,
    ap_rows: List[Dict],
    deployable_amt: float
) -> Dict:
    """
    Create comprehensive attribution breakdown for deployable calculation.
    
    Args:
        policy: Treasury policy configuration
        balance: Current bank balance
        expected_inflows: Probability-weighted AR collections
        expected_outflows: Probability-weighted AP payments
        total_open_ar: Face value of AR invoices in scope
        total_open_ap: Face value of AP bills in scope
        ap_rows: AP bills data for vendor analysis
        deployable_amt: Final deployable amount
        
    Returns:
        Detailed attribution dictionary
    """
    # Cash flow components
    ar_prob_effect = total_open_ar - expected_inflows
    ap_prob_effect = total_open_ap - expected_outflows
    net_expected_flow = expected_inflows - expected_outflows
    
    # Safety buffer components
    base_buffers = (
        policy["min_operating_cash"] + 
        policy["payroll_buffer"] + 
        policy["tax_buffer"]
    )
    
    # Vendor buffer breakdown
    unique_vendors_by_tier = {}
    for row in ap_rows:
        tier = row.get("vendor_tier", "regular")
        vendor_id = row.get("vendor_id", "")
        if tier not in unique_vendors_by_tier:
            unique_vendors_by_tier[tier] = set()
        unique_vendors_by_tier[tier].add(vendor_id)
    
    critical_vendor_count = len(unique_vendors_by_tier.get("critical", set()))
    regular_vendor_count = len(unique_vendors_by_tier.get("regular", set()))
    
    vendor_buffer = (
        critical_vendor_count * policy["vendor_tier_buffers"]["critical"] +
        regular_vendor_count * policy["vendor_tier_buffers"]["regular"]
    )
    
    shock_buffer = policy["outflow_shock_multiplier"] * expected_outflows
    total_must_keep = base_buffers + vendor_buffer + shock_buffer
    
    # Recognition calculation
    recognition_ratio = policy.get("recognition_ratio_expected_inflows", 0.40)
    recognized_inflows = recognition_ratio * expected_inflows
    
    return {
        "cash_flows": {
            "current_balance": round(balance, 2),
            "raw_ar_receivables": round(total_open_ar, 2),
            "raw_ap_payables": round(total_open_ap, 2),
            "raw_net_position": round(total_open_ar - total_open_ap, 2),
            "expected_inflows": round(expected_inflows, 2),
            "expected_outflows": round(expected_outflows, 2),
            "net_expected_flow": round(net_expected_flow, 2),
            "ar_probability_effect": round(ar_prob_effect, 2),
            "ap_probability_effect": round(ap_prob_effect, 2),
            "net_probability_effect": round(ar_prob_effect - ap_prob_effect, 2)
        },
        "safety_buffers": {
            "total_must_keep": round(total_must_keep, 2),
            "base_buffers": {
                "operating_cash": policy["min_operating_cash"],
                "payroll_buffer": policy["payroll_buffer"], 
                "tax_buffer": policy["tax_buffer"],
                "subtotal": round(base_buffers, 2)
            },
            "vendor_buffers": {
                "critical_vendors": critical_vendor_count,
                "regular_vendors": regular_vendor_count,
                "critical_buffer": critical_vendor_count * policy["vendor_tier_buffers"]["critical"],
                "regular_buffer": regular_vendor_count * policy["vendor_tier_buffers"]["regular"],
                "subtotal": round(vendor_buffer, 2)
            },
            "shock_buffer": {
                "multiplier": policy["outflow_shock_multiplier"],
                "expected_outflows": round(expected_outflows, 2),
                "buffer_amount": round(shock_buffer, 2)
            }
        },
        "deployable_calculation": {
            "available_balance": round(balance, 2),
            "recognition_ratio": recognition_ratio,
            "recognized_inflows": round(recognized_inflows, 2),
            "total_available": round(balance + recognized_inflows, 2),
            "less_must_keep": round(total_must_keep, 2),
            "deployable_amount": round(deployable_amt, 2)
        }
    }

