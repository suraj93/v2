"""
Data parsing and loading for treasury auto-sweep engine.
"""

import pandas as pd
from pathlib import Path
from typing import List


def load_bank(p: Path) -> pd.DataFrame:
    """
    Load bank transactions CSV file.
    
    Required columns: date, description, amount
    Optional columns: counterparty_id, running_balance
    
    Args:
        p: Path to bank_txns.csv file
        
    Returns:
        DataFrame with bank transactions
        
    Raises:
        ValueError: If required columns are missing
    """
    df = pd.read_csv(p)
    
    # Check required columns
    required_cols = ['date', 'description', 'amount']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
    
    # Convert date column to datetime
    df['date'] = pd.to_datetime(df['date'])
    
    # Convert amount to float
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    
    # Sort by date
    df = df.sort_values('date')
    
    return df


def load_ar(p: Path) -> pd.DataFrame:
    """
    Load accounts receivable invoices CSV file.
    
    Required columns: invoice_id, customer_id, invoice_date, due_date, amount, status
    Optional columns: paid_date
    
    Args:
        p: Path to ar_invoices.csv file
        
    Returns:
        DataFrame with AR invoices
        
    Raises:
        ValueError: If required columns are missing or invalid status values
    """
    df = pd.read_csv(p)
    
    # Check required columns
    required_cols = ['invoice_id', 'customer_id', 'invoice_date', 'due_date', 'amount', 'status']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
    
    # Validate status values
    valid_statuses = ['open', 'paid']
    invalid_statuses = df[~df['status'].isin(valid_statuses)]['status'].unique()
    if len(invalid_statuses) > 0:
        raise ValueError(f"Invalid status values: {invalid_statuses}")
    
    # Convert date columns to datetime
    df['invoice_date'] = pd.to_datetime(df['invoice_date'])
    df['due_date'] = pd.to_datetime(df['due_date'])
    if 'paid_date' in df.columns:
        df['paid_date'] = pd.to_datetime(df['paid_date'])
    
    # Convert amount to float
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    
    return df


def load_ap(p: Path) -> pd.DataFrame:
    """
    Load accounts payable bills CSV file.
    
    Required columns: bill_id, vendor_id, vendor_tier, bill_date, due_date, amount, status
    Optional columns: paid_date
    
    Args:
        p: Path to ap_bills.csv file
        
    Returns:
        DataFrame with AP bills
        
    Raises:
        ValueError: If required columns are missing or invalid values
    """
    df = pd.read_csv(p)
    
    # Check required columns
    required_cols = ['bill_id', 'vendor_id', 'vendor_tier', 'bill_date', 'due_date', 'amount', 'status']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
    
    # Validate status values
    valid_statuses = ['open', 'paid']
    invalid_statuses = df[~df['status'].isin(valid_statuses)]['status'].unique()
    if len(invalid_statuses) > 0:
        raise ValueError(f"Invalid status values: {invalid_statuses}")
    
    # Validate vendor_tier values
    valid_tiers = ['critical', 'regular']
    invalid_tiers = df[~df['vendor_tier'].isin(valid_tiers)]['vendor_tier'].unique()
    if len(invalid_tiers) > 0:
        raise ValueError(f"Invalid vendor_tier values: {invalid_tiers}")
    
    # Convert date columns to datetime
    df['bill_date'] = pd.to_datetime(df['bill_date'])
    df['due_date'] = pd.to_datetime(df['due_date'])
    if 'paid_date' in df.columns:
        df['paid_date'] = pd.to_datetime(df['paid_date'])
    
    # Convert amount to float
    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
    
    return df


def current_balance(bank_df: pd.DataFrame) -> float:
    """
    Calculate current bank balance.
    
    If 'running_balance' exists → last value after sorting by date ascending,
    else sum of 'amount'.
    
    Args:
        bank_df: DataFrame from load_bank()
        
    Returns:
        Current bank balance as float
    """
    if 'running_balance' in bank_df.columns:
        # Use the last running_balance value (already sorted by date in load_bank)
        return float(bank_df['running_balance'].iloc[-1])
    else:
        # Sum all amounts
        return float(bank_df['amount'].sum())

