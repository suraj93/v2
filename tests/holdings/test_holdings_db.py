"""Tests for holdings database operations."""

import pytest
import tempfile
import os
import sys
from pathlib import Path
import csv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.holdings.db import HoldingsDB


@pytest.fixture
def temp_csv():
    """Create a temporary CSV file with test data."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['instrument_name', 'issuer', 'amount_rupees', 'expected_annual_rate_bps', 'accrual_basis_days'])
        writer.writerow(['Test Fund - Growth', 'Test AMC', '1000000', '650', '365'])
        writer.writerow(['Another Fund - Direct', 'Another AMC', '500000', '600', '365'])
        temp_path = f.name
    
    yield temp_path
    os.unlink(temp_path)


@pytest.fixture
def temp_db():
    """Create a temporary database."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        temp_path = f.name
    
    yield temp_path
    if os.path.exists(temp_path):
        os.unlink(temp_path)


def test_db_initialization(temp_db):
    """Test database initialization."""
    db = HoldingsDB(temp_db)
    assert os.path.exists(temp_db)


def test_csv_seeding(temp_db, temp_csv):
    """Test CSV seeding functionality."""
    db = HoldingsDB(temp_db)
    result = db.seed_holdings_from_csv(temp_csv)
    
    assert result['status'] == 'success'
    assert result['rows_inserted'] == 2
    assert result['rows_skipped'] == 0
    
    # Test idempotency
    result2 = db.seed_holdings_from_csv(temp_csv)
    assert result2['rows_inserted'] == 0
    assert result2['rows_skipped'] == 2


def test_list_holdings(temp_db, temp_csv):
    """Test holdings listing."""
    db = HoldingsDB(temp_db)
    db.seed_holdings_from_csv(temp_csv)
    
    holdings = db.list_holdings()
    assert len(holdings) == 2
    assert holdings[0]['amount_rupees'] == 10000.0  # 1M rupees
    assert holdings[0]['expected_annual_rate_percent'] == 6.5  # 650 bps


def test_holdings_totals(temp_db, temp_csv):
    """Test holdings totals calculation."""
    db = HoldingsDB(temp_db)
    db.seed_holdings_from_csv(temp_csv)
    
    totals = db.get_holdings_totals()
    assert totals['total_corpus_rupees'] == 15000.0  # 1M + 0.5M
    assert totals['holdings_count'] == 2


def test_allocation(temp_db):
    """Test allocation operations."""
    db = HoldingsDB(temp_db)
    
    # Create new holding via allocation
    result = db.apply_allocation('New Fund', 'New AMC', 100000)
    assert result['status'] == 'success'
    assert result['action'] == 'created'
    
    # Update existing holding
    result2 = db.apply_allocation('New Fund', 'New AMC', 50000)
    assert result2['action'] == 'updated'
    
    # Check final amount
    holdings = db.list_holdings()
    assert holdings[0]['amount_rupees'] == 1500.0  # 150K total


def test_redemption_success(temp_db, temp_csv):
    """Test successful redemption."""
    db = HoldingsDB(temp_db)
    db.seed_holdings_from_csv(temp_csv)
    
    result = db.apply_redemption(5000)  # Redeem 5K from 15K total
    assert result['status'] == 'success'
    assert len(result['redemptions']) > 0
    
    # Check remaining balance
    totals = db.get_holdings_totals()
    assert totals['total_corpus_rupees'] == 10000.0


def test_redemption_insufficient_funds(temp_db, temp_csv):
    """Test redemption with insufficient funds."""
    db = HoldingsDB(temp_db)
    db.seed_holdings_from_csv(temp_csv)
    
    with pytest.raises(Exception) as exc_info:
        db.apply_redemption(20000)  # Try to redeem more than available
    
    assert "Insufficient funds" in str(exc_info.value)


def test_daily_accrual(temp_db, temp_csv):
    """Test daily accrual posting."""
    db = HoldingsDB(temp_db)
    db.seed_holdings_from_csv(temp_csv)
    
    result = db.post_daily_accrual('2025-08-30')
    assert result['status'] == 'success'
    assert result['accruals_posted'] == 2  # One per holding
    
    # Test idempotency
    result2 = db.post_daily_accrual('2025-08-30')
    assert result2['accruals_posted'] == 0
    assert result2['accruals_skipped'] == 2


def test_interest_calculations(temp_db):
    """Test interest calculation accuracy."""
    db = HoldingsDB(temp_db)
    
    # Add holding with known parameters
    db.apply_allocation('Test Fund', 'Test AMC', 100000)  # 1 lakh
    
    # Update rate to 7.3% (730 bps) 
    holdings = db.list_holdings()
    import sqlite3
    with sqlite3.connect(db.db_path) as conn:
        conn.execute('''
            UPDATE holdings 
            SET expected_annual_rate_bps = 730 
            WHERE instrument_name = ? AND issuer = ?
        ''', ('Test Fund', 'Test AMC'))
    
    # Post accrual
    db.post_daily_accrual('2025-08-30')
    
    # Check calculation: 100000 * 730 / (10000 * 365) = 20 paise per day
    series = db.get_daily_interest_series('2025-08-30', '2025-08-30')
    assert len(series) == 1
    assert series[0]['accrued_paise'] == 20  # Expected daily interest


def test_ytd_totals(temp_db, temp_csv):
    """Test YTD totals calculation."""
    db = HoldingsDB(temp_db)
    db.seed_holdings_from_csv(temp_csv)
    
    # Post accruals for multiple dates
    db.post_daily_accrual('2025-08-30')
    db.post_daily_accrual('2025-08-31')
    
    ytd = db.get_ytd_totals(2025)
    assert ytd['accrual_days'] == 2
    assert ytd['unique_instruments'] == 2


def test_attribution(temp_db, temp_csv):
    """Test interest attribution."""
    db = HoldingsDB(temp_db)
    db.seed_holdings_from_csv(temp_csv)
    
    # Post accruals
    db.post_daily_accrual('2025-08-30')
    db.post_daily_accrual('2025-08-31')
    
    attribution = db.get_attribution('2025-08-30', '2025-08-31')
    assert len(attribution) == 2
    assert attribution[0]['days_count'] == 2
    
    # Check that higher balance fund has higher interest
    fund1_interest = next(a for a in attribution if a['instrument_name'] == 'Test Fund - Growth')['interest_paise']
    fund2_interest = next(a for a in attribution if a['instrument_name'] == 'Another Fund - Direct')['interest_paise']
    assert fund1_interest > fund2_interest  # 1M fund should earn more than 0.5M fund


if __name__ == "__main__":
    pytest.main([__file__, "-v"])