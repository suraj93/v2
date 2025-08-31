"""
Tests for the core treasury auto-sweep engine.
"""

import pytest
import pandas as pd
from pathlib import Path
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.config import load_settings
from core.parse import load_bank, load_ar, load_ap, current_balance


def test_load_settings():
    """Test loading configuration files."""
    settings = load_settings("data")
    
    assert settings.data_dir == Path("data")
    assert "currency" in settings.policy
    assert "timezone" in settings.calendar
    assert settings.policy["currency"] == "INR"
    assert settings.calendar["timezone"] == "Asia/Kolkata"


def test_load_bank():
    """Test loading bank transactions."""
    bank_df = load_bank(Path("data/bank_txns.csv"))
    
    # Check required columns exist
    assert "date" in bank_df.columns
    assert "description" in bank_df.columns
    assert "amount" in bank_df.columns
    
    # Check data types
    assert pd.api.types.is_datetime64_any_dtype(bank_df['date'])
    assert pd.api.types.is_numeric_dtype(bank_df['amount'])
    
    # Check data is sorted by date
    assert bank_df['date'].is_monotonic_increasing


def test_load_ar():
    """Test loading AR invoices."""
    ar_df = load_ar(Path("data/ar_invoices.csv"))
    
    # Check required columns exist
    required_cols = ['invoice_id', 'customer_id', 'invoice_date', 'due_date', 'amount', 'status']
    for col in required_cols:
        assert col in ar_df.columns
    
    # Check status values are valid
    valid_statuses = ['open', 'paid']
    assert ar_df['status'].isin(valid_statuses).all()
    
    # Check data types
    assert pd.api.types.is_datetime64_any_dtype(ar_df['invoice_date'])
    assert pd.api.types.is_datetime64_any_dtype(ar_df['due_date'])
    assert pd.api.types.is_numeric_dtype(ar_df['amount'])


def test_load_ap():
    """Test loading AP bills."""
    ap_df = load_ap(Path("data/ap_bills.csv"))
    
    # Check required columns exist
    required_cols = ['bill_id', 'vendor_id', 'vendor_tier', 'bill_date', 'due_date', 'amount', 'status']
    for col in required_cols:
        assert col in ap_df.columns
    
    # Check status values are valid
    valid_statuses = ['open', 'paid']
    assert ap_df['status'].isin(valid_statuses).all()
    
    # Check vendor_tier values are valid
    valid_tiers = ['critical', 'regular']
    assert ap_df['vendor_tier'].isin(valid_tiers).all()
    
    # Check data types
    assert pd.api.types.is_datetime64_any_dtype(ap_df['bill_date'])
    assert pd.api.types.is_datetime64_any_dtype(ap_df['due_date'])
    assert pd.api.types.is_numeric_dtype(ap_df['amount'])


def test_current_balance():
    """Test current balance calculation."""
    bank_df = load_bank(Path("data/bank_txns.csv"))
    balance = current_balance(bank_df)
    
    assert isinstance(balance, float)
    assert balance >= 0  # Balance should be non-negative


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

