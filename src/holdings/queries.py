"""Data query functions for holdings database operations."""

import json
from typing import Dict, Any
from .db import HoldingsDB


def get_setup_result(db_path: str) -> Dict[str, Any]:
    """Initialize database and return result."""
    db = HoldingsDB(db_path)
    return {
        "action": "setup_db",
        "status": "success", 
        "message": "Database initialized successfully",
        "db_path": db_path
    }


def get_seed_result(db_path: str, csv_file: str, overwrite: bool = True) -> Dict[str, Any]:
    """Seed holdings from CSV and return result."""
    db = HoldingsDB(db_path)
    result = db.seed_holdings_from_csv(csv_file, overwrite=overwrite)
    result["action"] = "seed"
    result["csv_file"] = csv_file
    return result


def get_clear_result(db_path: str) -> Dict[str, Any]:
    """Clear all holdings and accrual data and return result."""
    db = HoldingsDB(db_path)
    result = db.clear_all_data()
    result["action"] = "clear"
    return result


def get_holdings_list(db_path: str) -> Dict[str, Any]:
    """Get all holdings list."""
    db = HoldingsDB(db_path)
    holdings = db.list_holdings()
    return {
        "action": "list_holdings",
        "count": len(holdings),
        "holdings": holdings
    }


def get_holdings_totals(db_path: str) -> Dict[str, Any]:
    """Get holdings totals."""
    db = HoldingsDB(db_path)
    totals = db.get_holdings_totals()
    totals["action"] = "totals"
    return totals


def get_allocation_result(db_path: str, instrument: str, issuer: str, amount: float) -> Dict[str, Any]:
    """Apply allocation and return result."""
    db = HoldingsDB(db_path)
    result = db.apply_allocation(instrument, issuer, amount)
    result["action"] = "allocate"
    return result


def get_redemption_result(db_path: str, amount: float, selection: str = "most_recent_first") -> Dict[str, Any]:
    """Apply redemption and return result."""
    db = HoldingsDB(db_path)
    result = db.apply_redemption(amount, selection)
    result["action"] = "redeem"
    return result


def get_accrual_result(db_path: str, date: str) -> Dict[str, Any]:
    """Post daily accrual and return result."""
    db = HoldingsDB(db_path)
    result = db.post_daily_accrual(date)
    result["action"] = "post_accrual"
    return result


def get_daily_series(db_path: str, start_date: str, end_date: str) -> Dict[str, Any]:
    """Get daily interest series."""
    db = HoldingsDB(db_path)
    series = db.get_daily_interest_series(start_date, end_date)
    return {
        "action": "daily_series",
        "start_date": start_date,
        "end_date": end_date,
        "count": len(series),
        "series": series
    }


def get_ytd_totals(db_path: str, year: int) -> Dict[str, Any]:
    """Get YTD totals."""
    db = HoldingsDB(db_path)
    totals = db.get_ytd_totals(year)
    totals["action"] = "ytd_totals"
    return totals


def get_attribution(db_path: str, start_date: str, end_date: str) -> Dict[str, Any]:
    """Get interest attribution."""
    db = HoldingsDB(db_path)
    attribution = db.get_attribution(start_date, end_date)
    return {
        "action": "attribution",
        "start_date": start_date,
        "end_date": end_date,
        "count": len(attribution),
        "attribution": attribution
    }


def get_daily_detail(db_path: str, start_date: str, end_date: str) -> Dict[str, Any]:
    """Get detailed daily accruals per instrument."""
    db = HoldingsDB(db_path)
    details = db.get_daily_accruals_detail(start_date, end_date)
    return {
        "action": "daily_detail",
        "start_date": start_date,
        "end_date": end_date,
        "count": len(details),
        "daily_details": details
    }