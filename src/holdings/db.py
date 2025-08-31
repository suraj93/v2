"""Core holdings database operations."""

import sqlite3
import json
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, date


class HoldingsDB:
    def __init__(self, db_path: str = "holdings_data/treasury.db"):
        self.db_path = db_path
        self._ensure_directory()
        self._init_db()
    
    def _ensure_directory(self):
        """Ensure the database directory exists."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
    
    def _init_db(self):
        """Initialize database with tables and triggers."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            
            # Create tables and triggers from spec
            ddl_script = '''
            CREATE TABLE IF NOT EXISTS holdings (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              instrument_name TEXT NOT NULL,
              issuer TEXT NOT NULL,
              amount_paise INTEGER NOT NULL,
              currency TEXT NOT NULL DEFAULT 'INR',
              expected_annual_rate_bps INTEGER NOT NULL DEFAULT 0,
              accrual_basis_days INTEGER NOT NULL DEFAULT 365,
              daily_interest_paise INTEGER NOT NULL DEFAULT 0,
              updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
              UNIQUE (instrument_name, issuer)
            );
            CREATE INDEX IF NOT EXISTS idx_holdings_issuer ON holdings(issuer);

            CREATE TRIGGER IF NOT EXISTS trg_holdings_recalc_interest
            AFTER INSERT ON holdings
            BEGIN
              UPDATE holdings
                SET daily_interest_paise =
                  (amount_paise * expected_annual_rate_bps) / (10000 * accrual_basis_days)
              WHERE id = NEW.id;
            END;
            
            CREATE TRIGGER IF NOT EXISTS trg_holdings_recalc_interest_update
            AFTER UPDATE OF amount_paise, expected_annual_rate_bps, accrual_basis_days ON holdings
            BEGIN
              UPDATE holdings
                SET daily_interest_paise =
                  (amount_paise * expected_annual_rate_bps) / (10000 * accrual_basis_days),
                  updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
              WHERE id = NEW.id;
            END;

            CREATE TABLE IF NOT EXISTS interest_accruals (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              as_of_date TEXT NOT NULL,
              instrument_name TEXT NOT NULL,
              issuer TEXT NOT NULL,
              opening_amount_paise INTEGER NOT NULL,
              expected_annual_rate_bps INTEGER NOT NULL,
              accrual_basis_days INTEGER NOT NULL DEFAULT 365,
              accrued_interest_paise INTEGER NOT NULL,
              method TEXT NOT NULL DEFAULT 'model',
              created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
              UNIQUE (as_of_date, instrument_name, issuer)
            );
            CREATE INDEX IF NOT EXISTS idx_accruals_date ON interest_accruals(as_of_date);
            CREATE INDEX IF NOT EXISTS idx_accruals_instr ON interest_accruals(instrument_name, issuer);
            '''
            
            conn.executescript(ddl_script)
            conn.commit()
    
    def clear_all_data(self) -> Dict[str, Any]:
        """Clear all holdings and accrual data."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                # Get counts before deletion
                cursor = conn.execute("SELECT COUNT(*) FROM holdings")
                holdings_count = cursor.fetchone()[0]
                
                cursor = conn.execute("SELECT COUNT(*) FROM interest_accruals")
                accruals_count = cursor.fetchone()[0]
                
                # Delete all data
                conn.execute("DELETE FROM interest_accruals")
                conn.execute("DELETE FROM holdings")
                
                conn.execute("COMMIT")
                return {
                    "status": "success",
                    "holdings_deleted": holdings_count,
                    "accruals_deleted": accruals_count
                }
            except Exception as e:
                conn.execute("ROLLBACK")
                raise Exception(f"Failed to clear data: {str(e)}")
    
    def seed_holdings_from_csv(self, csv_path: str, overwrite: bool = True) -> Dict[str, Any]:
        """Load holdings from CSV file."""
        rows_inserted = 0
        rows_skipped = 0
        clear_result = None
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                # Clear existing data if overwrite mode
                if overwrite:
                    cursor = conn.execute("SELECT COUNT(*) FROM holdings")
                    holdings_count = cursor.fetchone()[0]
                    
                    cursor = conn.execute("SELECT COUNT(*) FROM interest_accruals")
                    accruals_count = cursor.fetchone()[0]
                    
                    if holdings_count > 0 or accruals_count > 0:
                        conn.execute("DELETE FROM interest_accruals")
                        conn.execute("DELETE FROM holdings")
                        clear_result = {
                            "holdings_deleted": holdings_count,
                            "accruals_deleted": accruals_count
                        }
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Convert rupees to paise
                        amount_paise = int(float(row['amount_rupees']) * 100)
                        rate_bps = int(row['expected_annual_rate_bps'])
                        accrual_basis = int(row.get('accrual_basis_days', 365))
                        
                        try:
                            conn.execute('''
                                INSERT INTO holdings 
                                (instrument_name, issuer, amount_paise, expected_annual_rate_bps, accrual_basis_days)
                                VALUES (?, ?, ?, ?, ?)
                            ''', (row['instrument_name'], row['issuer'], amount_paise, rate_bps, accrual_basis))
                            rows_inserted += 1
                        except sqlite3.IntegrityError:
                            rows_skipped += 1  # Duplicate key, skip
                
                conn.execute("COMMIT")
                result = {
                    "status": "success",
                    "rows_inserted": rows_inserted,
                    "rows_skipped": rows_skipped,
                    "total_processed": rows_inserted + rows_skipped,
                    "overwrite_mode": bool(overwrite)
                }
                
                if clear_result:
                    result["cleared_data"] = clear_result
                
                return result
            except Exception as e:
                conn.execute("ROLLBACK")
                raise Exception(f"Failed to seed holdings: {str(e)}")
    
    def list_holdings(self) -> List[Dict[str, Any]]:
        """List all holdings with rupee conversions."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT 
                    instrument_name,
                    issuer,
                    ROUND(amount_paise / 100.0, 2) as amount_rupees,
                    ROUND(expected_annual_rate_bps / 100.0, 2) as expected_annual_rate_percent,
                    accrual_basis_days,
                    ROUND(daily_interest_paise / 100.0, 4) as daily_interest_rupees,
                    updated_at
                FROM holdings
                ORDER BY issuer, instrument_name
            ''')
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_holdings_totals(self) -> Dict[str, Any]:
        """Get total corpus and daily interest."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT 
                    COALESCE(SUM(amount_paise), 0) as total_corpus_paise,
                    COALESCE(SUM(daily_interest_paise), 0) as total_daily_interest_paise,
                    COUNT(*) as holdings_count
                FROM holdings
            ''')
            
            row = cursor.fetchone()
            return {
                "total_corpus_rupees": round(row[0] / 100.0, 2),
                "total_daily_interest_rupees": round(row[1] / 100.0, 4),
                "holdings_count": row[2]
            }
    
    def apply_allocation(self, instrument_name: str, issuer: str, amount_rupees: float) -> Dict[str, Any]:
        """Add allocation to existing holding or create new one."""
        amount_paise = int(amount_rupees * 100)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                # Try to update existing holding
                cursor = conn.execute('''
                    UPDATE holdings 
                    SET amount_paise = amount_paise + ?
                    WHERE instrument_name = ? AND issuer = ?
                ''', (amount_paise, instrument_name, issuer))
                
                if cursor.rowcount == 0:
                    # Create new holding with default rate
                    conn.execute('''
                        INSERT INTO holdings (instrument_name, issuer, amount_paise)
                        VALUES (?, ?, ?)
                    ''', (instrument_name, issuer, amount_paise))
                    action = "created"
                else:
                    action = "updated"
                
                conn.execute("COMMIT")
                return {
                    "status": "success",
                    "action": action,
                    "instrument_name": instrument_name,
                    "issuer": issuer,
                    "allocated_rupees": amount_rupees
                }
            except Exception as e:
                conn.execute("ROLLBACK")
                raise Exception(f"Failed to apply allocation: {str(e)}")
    
    def apply_redemption(self, amount_rupees: float, selection: str = "most_recent_first") -> Dict[str, Any]:
        """Redeem from holdings with hard failure on insufficient funds."""
        amount_paise_needed = int(amount_rupees * 100)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                # Check total available
                cursor = conn.execute('SELECT COALESCE(SUM(amount_paise), 0) FROM holdings')
                total_available = cursor.fetchone()[0]
                
                if total_available < amount_paise_needed:
                    conn.execute("ROLLBACK")
                    raise Exception(f"Insufficient funds: need ₹{amount_rupees:,.2f}, available ₹{total_available/100:,.2f}")
                
                # Get holdings ordered for redemption
                order_clause = "updated_at DESC" if selection == "most_recent_first" else "updated_at ASC"
                cursor = conn.execute(f'''
                    SELECT id, instrument_name, issuer, amount_paise, updated_at
                    FROM holdings 
                    WHERE amount_paise > 0
                    ORDER BY {order_clause}
                ''')
                
                holdings = cursor.fetchall()
                remaining_to_redeem = amount_paise_needed
                redemptions = []
                
                for holding_id, instr, issuer, current_amount, updated_at in holdings:
                    if remaining_to_redeem <= 0:
                        break
                    
                    redemption_amount = min(current_amount, remaining_to_redeem)
                    new_amount = current_amount - redemption_amount
                    
                    conn.execute('UPDATE holdings SET amount_paise = ? WHERE id = ?', 
                               (new_amount, holding_id))
                    
                    redemptions.append({
                        "instrument_name": instr,
                        "issuer": issuer,
                        "redeemed_rupees": round(redemption_amount / 100.0, 2),
                        "remaining_rupees": round(new_amount / 100.0, 2)
                    })
                    
                    remaining_to_redeem -= redemption_amount
                
                conn.execute("COMMIT")
                return {
                    "status": "success",
                    "total_redeemed_rupees": amount_rupees,
                    "redemptions": redemptions
                }
            except Exception as e:
                conn.execute("ROLLBACK")
                raise
    
    def post_daily_accrual(self, as_of_date: str) -> Dict[str, Any]:
        """Post daily interest accruals for given date (idempotent)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                # Get current holdings
                cursor = conn.execute('''
                    SELECT instrument_name, issuer, amount_paise, 
                           expected_annual_rate_bps, accrual_basis_days
                    FROM holdings
                    WHERE amount_paise > 0
                ''')
                
                holdings = cursor.fetchall()
                accruals_posted = 0
                accruals_skipped = 0
                
                for instr, issuer, amount_paise, rate_bps, basis_days in holdings:
                    # Calculate interest: floor(amount * rate / (10000 * basis))
                    accrued_interest = int((amount_paise * rate_bps) // (10000 * basis_days))
                    
                    try:
                        conn.execute('''
                            INSERT INTO interest_accruals 
                            (as_of_date, instrument_name, issuer, opening_amount_paise,
                             expected_annual_rate_bps, accrual_basis_days, accrued_interest_paise)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (as_of_date, instr, issuer, amount_paise, rate_bps, basis_days, accrued_interest))
                        accruals_posted += 1
                    except sqlite3.IntegrityError:
                        accruals_skipped += 1  # Already exists for this date
                
                conn.execute("COMMIT")
                return {
                    "status": "success",
                    "as_of_date": as_of_date,
                    "accruals_posted": accruals_posted,
                    "accruals_skipped": accruals_skipped,
                    "total_holdings": len(holdings)
                }
            except Exception as e:
                conn.execute("ROLLBACK")
                raise Exception(f"Failed to post daily accrual: {str(e)}")
    
    def get_daily_interest_series(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Get daily interest time series."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT 
                    as_of_date,
                    SUM(accrued_interest_paise) as total_accrued_paise,
                    ROUND(SUM(accrued_interest_paise) / 100.0, 4) as total_accrued_rupees,
                    COUNT(*) as instruments_count
                FROM interest_accruals
                WHERE as_of_date >= ? AND as_of_date <= ?
                GROUP BY as_of_date
                ORDER BY as_of_date
            ''', (start_date, end_date))
            
            return [{"date": row[0], "accrued_interest": row[2], "instruments": row[3]} 
                   for row in cursor.fetchall()]
    
    def get_ytd_totals(self, year: int) -> Dict[str, Any]:
        """Get year-to-date interest totals."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT 
                    COALESCE(SUM(accrued_interest_paise), 0) as ytd_accrued_paise,
                    COUNT(*) as total_accrual_records,
                    COUNT(DISTINCT as_of_date) as accrual_days,
                    COUNT(DISTINCT instrument_name || '|' || issuer) as unique_instruments
                FROM interest_accruals
                WHERE strftime('%Y', as_of_date) = ?
            ''', (str(year),))
            
            row = cursor.fetchone()
            return {
                "year": year,
                "ytd_accrued_interest": round(row[0] / 100.0, 2),
                "total_accrual_records": row[1],
                "accrual_days": row[2],
                "unique_instruments": row[3]
            }
    
    def get_attribution(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Get interest attribution by instrument/issuer."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT 
                    instrument_name,
                    issuer,
                    SUM(accrued_interest_paise) as sum_interest_paise,
                    ROUND(AVG(opening_amount_paise), 0) as avg_opening_balance_paise,
                    ROUND(SUM(expected_annual_rate_bps * opening_amount_paise) / 
                          NULLIF(SUM(opening_amount_paise), 0), 0) as avg_rate_bps,
                    COUNT(*) as days_count
                FROM interest_accruals
                WHERE as_of_date >= ? AND as_of_date <= ?
                GROUP BY instrument_name, issuer
                ORDER BY sum_interest_paise DESC
            ''', (start_date, end_date))
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "instrument_name": row[0],
                    "issuer": row[1],
                    "interest_earned": round(row[2] / 100.0, 2),
                    "avg_opening_balance_rupees": round((row[3] or 0) / 100.0, 2),
                    "avg_rate_percent": round((row[4] or 0) / 100.0, 2),
                    "days_count": row[5]
                })
            
            return results
    
    def get_daily_accruals_detail(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Get detailed daily accruals showing balances and interest per instrument."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT 
                    as_of_date,
                    instrument_name,
                    issuer,
                    ROUND(opening_amount_paise / 100.0, 2) as opening_balance_rupees,
                    ROUND(expected_annual_rate_bps / 100.0, 2) as rate_percent,
                    accrual_basis_days,
                    ROUND(accrued_interest_paise / 100.0, 4) as interest_earned,
                    created_at
                FROM interest_accruals
                WHERE as_of_date >= ? AND as_of_date <= ?
                ORDER BY as_of_date, instrument_name, issuer
            ''', (start_date, end_date))
            
            return [dict(row) for row in cursor.fetchall()]