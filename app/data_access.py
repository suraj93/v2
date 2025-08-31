"""
Data access layer for treasury dashboard.
Reads from existing JSON outputs and holdings database.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime, date, timedelta

# Add src to path for holdings imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from holdings.queries import (
        get_holdings_totals, get_ytd_totals, get_attribution, 
        get_daily_series, get_holdings_list
    )
    from core.config import load_settings
    from core.parse import load_ar, load_ap
    from core.predict import horizon_flows
except ImportError as e:
    print(f"Warning: Holdings integration unavailable: {e}")
    # Mock functions for development
    def get_holdings_totals(*args, **kwargs): 
        return {"total_corpus_rupees": 0, "total_daily_interest_rupees": 0}
    def get_ytd_totals(*args, **kwargs): 
        return {"ytd_accrued_interest": 0}
    def get_attribution(*args, **kwargs): 
        return {"attribution": []}
    def get_daily_series(*args, **kwargs): 
        return {"series": []}
    def get_holdings_list(*args, **kwargs): 
        return {"holdings": []}
    def load_settings(*args): 
        return {"policy": {}}

# Configuration
HOLDINGS_DB_PATH = "holdings_data/treasury.db"


def get_compute_today() -> Dict:
    """
    Read existing treasury summary JSON and return data for UI.
    
    Returns:
        Dict with keys: asOf, bankBalance_rupees, rawAP_7d_rupees, 
        rawAR_7d_rupees, deployable_rupees, reasons
    """
    # Path to summary JSON (relative to project root)
    summary_path = Path(__file__).parent.parent / "outputs" / "summary.json"
    
    try:
        if not summary_path.exists():
            return _get_fallback_data("Summary file not found")
        
        with open(summary_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract required fields and validate
        result = {
            "asOf": data.get("as_of_date", datetime.now().strftime("%Y-%m-%d")),
            "bankBalance_rupees": float(data.get("balance", 0)),
            "rawAP_7d_rupees": float(data.get("total_open_payables", 0)),
            "rawAR_7d_rupees": float(data.get("total_open_receivables", 0)),
            "deployable_rupees": float(data.get("deployable", 0)),
            "reasons": data.get("reasons", []),
            "horizon_days": data.get("horizon_days", 7)
        }
        
        # Add file timestamp for freshness
        file_stat = summary_path.stat()
        result["file_updated_at"] = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
        
        return result
        
    except json.JSONDecodeError as e:
        return _get_fallback_data(f"Invalid JSON format: {str(e)}")
    except Exception as e:
        return _get_fallback_data(f"Error reading data: {str(e)}")


def _get_fallback_data(error_msg: str) -> Dict:
    """Return fallback data structure when primary data unavailable."""
    return {
        "asOf": datetime.now().strftime("%Y-%m-%d"),
        "bankBalance_rupees": 0.0,
        "rawAP_7d_rupees": 0.0,
        "rawAR_7d_rupees": 0.0,
        "deployable_rupees": 0.0,
        "reasons": ["DATA_UNAVAILABLE"],
        "horizon_days": 7,
        "file_updated_at": None,
        "error": error_msg
    }


def get_data_freshness_info() -> Dict:
    """
    Get information about data freshness for display.
    
    Returns:
        Dict with file_age_hours, last_updated, is_stale flags
    """
    summary_path = Path(__file__).parent.parent / "outputs" / "summary.json"
    
    if not summary_path.exists():
        return {
            "file_exists": False,
            "file_age_hours": None,
            "last_updated": None,
            "is_stale": True
        }
    
    try:
        file_stat = summary_path.stat()
        file_modified = datetime.fromtimestamp(file_stat.st_mtime)
        age_hours = (datetime.now() - file_modified).total_seconds() / 3600
        
        return {
            "file_exists": True,
            "file_age_hours": age_hours,
            "last_updated": file_modified.isoformat(),
            "is_stale": age_hours > 24  # Consider stale if older than 24 hours
        }
        
    except Exception as e:
        return {
            "file_exists": True,
            "file_age_hours": None,
            "last_updated": None,
            "is_stale": True,
            "error": str(e)
        }


# ===== PHASE 2: HOLDINGS & INVESTMENT DATA =====

def get_investment_totals(db_path: str = HOLDINGS_DB_PATH) -> Dict:
    """Get investment totals: current balance, YTD interest, 30d average."""
    try:
        # Current investment balance
        holdings_totals = get_holdings_totals(db_path)
        current_investment = holdings_totals.get("total_corpus_rupees", 0)
        
        # YTD interest earned
        current_year = datetime.now().year
        ytd_data = get_ytd_totals(db_path, current_year)
        ytd_interest = ytd_data.get("ytd_accrued_interest", 0)
        
        # 30-day average balance (custom aggregation)
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        daily_data = get_daily_series(db_path, start_date, end_date)
        series = daily_data.get("series", [])
        
        if series:
            # Calculate average from opening balances (would need custom query)
            # For now, approximate from daily interest
            avg_30d = sum(day.get("accrued_interest", 0) for day in series) * 365 / (len(series) * 0.065)  # Rough inverse calc
        else:
            avg_30d = current_investment  # Fallback to current if no history
        
        return {
            "current_investment_rupees": float(current_investment),
            "ytd_interest_rupees": float(ytd_interest),
            "avg_30d_investment_rupees": float(avg_30d),
            "data_available": True
        }
    except Exception as e:
        return {
            "current_investment_rupees": 0.0,
            "ytd_interest_rupees": 0.0,
            "avg_30d_investment_rupees": 0.0,
            "data_available": False,
            "error": str(e)
        }


def load_holdings_df(db_path: str = HOLDINGS_DB_PATH) -> List[Dict]:
    """Load holdings table data."""
    try:
        result = get_holdings_list(db_path)
        return result.get("holdings", [])
    except Exception as e:
        return []


def load_attribution(start_date: str, end_date: str, db_path: str = HOLDINGS_DB_PATH) -> List[Dict]:
    """Load interest attribution data for date range."""
    try:
        result = get_attribution(db_path, start_date, end_date)
        return result.get("attribution", [])
    except Exception as e:
        return []


def load_daily_interest_series(days: int = 60, db_path: str = HOLDINGS_DB_PATH) -> List[Dict]:
    """Load daily interest series for charts."""
    try:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        result = get_daily_series(db_path, start_date, end_date)
        return result.get("series", [])
    except Exception as e:
        return []


def load_policy_limits() -> Dict:
    """Load policy limits from policy.json."""
    try:
        data_dir = Path(__file__).parent.parent / "data"
        settings = load_settings(str(data_dir))
        policy = settings.policy
        
        return {
            "min_operating_cash": policy.get("min_operating_cash", 1000000),
            "payroll_buffer": policy.get("payroll_buffer", 400000),
            "tax_buffer": policy.get("tax_buffer", 200000),
            "vendor_tier_critical": policy.get("vendor_tier_buffers", {}).get("critical", 300000),
            "vendor_tier_regular": policy.get("vendor_tier_buffers", {}).get("regular", 100000),
            "approval_threshold": policy.get("approval_threshold", 500000),
            "recognition_ratio": policy.get("recognition_ratio_expected_inflows", 0.98),
            "shock_multiplier": policy.get("outflow_shock_multiplier", 1.15),
            "data_available": True
        }
    except Exception as e:
        return {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_critical": 300000,
            "vendor_tier_regular": 100000,
            "approval_threshold": 500000,
            "recognition_ratio": 0.98,
            "shock_multiplier": 1.15,
            "data_available": False,
            "error": str(e)
        }


def get_ap_ar_forecast_14d() -> Dict:
    """Get 14-day AP/AR forecast using existing treasury system."""
    try:
        # Load treasury data
        data_dir = Path(__file__).parent.parent / "data"
        settings = load_settings(str(data_dir))
        
        ar_df = load_ar(data_dir / "ar_invoices.csv")
        ap_df = load_ap(data_dir / "ap_bills.csv")
        
        # Generate 14-day forecast
        inflows, outflows, total_open_ar, total_open_ap, ar_h_df, ap_h_df = horizon_flows(
            ar_df, ap_df, horizon_days=14,
            as_of_date=None,  # Current date
            collection_probs=settings.model_params.get('ar_collection_probabilities', {}),
            ap_probs=settings.model_params.get('ap_payment_probabilities', {}),
            ap_provision_days=settings.policy.get('ap_provision_days', 14)
        )
        
        # Create daily forecast data (simplified - would need day-by-day breakdown)
        forecast_data = []
        for i in range(14):
            forecast_date = datetime.now() + timedelta(days=i+1)
            forecast_data.append({
                "date": forecast_date.strftime("%Y-%m-%d"),
                "expected_inflows": inflows / 14,  # Simplified: distribute evenly
                "expected_outflows": outflows / 14,
                "net_flow": (inflows - outflows) / 14
            })
        
        return {
            "forecast": forecast_data,
            "total_inflows_14d": inflows,
            "total_outflows_14d": outflows,
            "net_flow_14d": inflows - outflows,
            "data_available": True
        }
    except Exception as e:
        return {
            "forecast": [],
            "total_inflows_14d": 0,
            "total_outflows_14d": 0,
            "net_flow_14d": 0,
            "data_available": False,
            "error": str(e)
        }


def load_perform_data() -> Dict:
    """Load perform.json data for deployment approvals."""
    perform_path = Path(__file__).parent.parent / "outputs" / "perform.json"
    
    try:
        if not perform_path.exists():
            return {"data_available": False, "error": "perform.json not found"}
        
        with open(perform_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return {
            "data_available": True,
            "date": data.get("date"),
            "deployable_value": float(data.get("deployable_value", 0)),
            "current_balance": float(data.get("current_balance", 0)),
            "must_keep_value": float(data.get("must_keep_value", 0)),
            "deploy_instrument": data.get("deploy_instrument", ""),
            "deploy_issuer": data.get("deploy_issuer", ""),
            "max_tenor": data.get("max_tenor", 1),
            "approval_needed": data.get("approval_needed", False),
            "description": data.get("description", "")
        }
    except Exception as e:
        return {
            "data_available": False,
            "error": str(e)
        }