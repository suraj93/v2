"""
Cash flow prediction for treasury auto-sweep engine.
"""

import pandas as pd
from datetime import date, datetime
from typing import Tuple, Dict, Optional
from pathlib import Path


def invoice_pay_prob(days_to_due: int, status: str, collection_probs: Dict[str, float]) -> float:
    """
    Calculate probability of invoice payment based on days to due date.
    
    Args:
        days_to_due: Days until due date (negative = overdue)
        status: Invoice status ('open' or 'paid')
        collection_probs: Dictionary with collection probability thresholds
        
    Returns:
        Payment probability as float between 0 and 1
        
    Raises:
        ValueError: If status is invalid or collection_probs is malformed
    """
    # Validate status
    valid_statuses = ['open', 'paid']
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of {valid_statuses}")
    
    # Validate collection probabilities
    required_keys = ['overdue', 'within_7_days', 'within_14_days', 'beyond_14_days']
    missing_keys = [key for key in required_keys if key not in collection_probs]
    if missing_keys:
        raise ValueError(f"Missing collection probability keys: {missing_keys}")
    
    # Check probability values are valid (0-1)
    for key, prob in collection_probs.items():
        if not isinstance(prob, (int, float)) or prob < 0 or prob > 1:
            raise ValueError(f"Invalid probability for {key}: {prob}. Must be between 0 and 1")
    
    # Apply collection probability rules based on days to due
    # Note: Paid invoices should be filtered out before calling this function
    if days_to_due < 0:
        return collection_probs['overdue']
    elif days_to_due <= 7:
        return collection_probs['within_7_days']
    elif days_to_due <= 14:
        return collection_probs['within_14_days']
    else:
        return collection_probs['beyond_14_days']


def horizon_flows(
    ar_df: pd.DataFrame,
    ap_df: pd.DataFrame,
    horizon_days: int = 7,
    as_of_date: Optional[date] = None,
    collection_probs: Optional[Dict[str, float]] = None,
    ap_probs: Optional[Dict[str, float]] = None,
    ap_provision_days: int = 14
) -> Tuple[float, float, float, float, pd.DataFrame, pd.DataFrame]:
    """
    Calculate expected cash flows within the specified horizon.
    
    Methodology:
    - AR: Includes open invoices due within horizon OR overdue. Paid invoices excluded.
    - AP: Uses four-tier model with configurable provision period. Paid bills excluded.
      * Overdue: 100% probability (urgent payment required)
      * Within horizon: 100% probability
      * Beyond horizon but within provision: 90% probability  
      * Beyond provision: 0% probability (filtered out)
    
    Args:
        ar_df: Accounts receivable DataFrame with columns: due_date, amount, status
        ap_df: Accounts payable DataFrame with columns: due_date, amount, status
        horizon_days: Number of days to look ahead (default: 7)
        as_of_date: Reference date for horizon calculation (default: today)
        collection_probs: AR collection probability configuration (default: from policy)
        ap_probs: AP payment probability configuration (default: from policy)
        ap_provision_days: Number of days beyond horizon to provision for AP (default: 14)
        
    Returns:
        Tuple of (expected_inflows, expected_outflows, total_open_receivables, total_open_payables, ar_h_df, ap_h_df)
        - expected_inflows: Probability-weighted AR expected collections
        - expected_outflows: Probability-weighted AP expected payments  
        - total_open_receivables: Face value of open AR within horizon
        - total_open_payables: Face value of open AP within horizon
        - ar_h_df: Open AR invoices within horizon (with probability columns)
        - ap_h_df: Open AP bills within horizon (with probability columns)
        
    Raises:
        ValueError: If required columns are missing or data is invalid
        TypeError: If horizon_days is not an integer
        ValueError: If horizon_days is not in valid range (1-365)
    """
    # Input validation
    if not isinstance(horizon_days, int):
        raise TypeError(f"horizon_days must be an integer, got {type(horizon_days)}")
    
    if not 1 <= horizon_days <= 365:
        raise ValueError(f"horizon_days must be between 1 and 365, got {horizon_days}")
    
    # Set default as_of_date to today if not provided
    if as_of_date is None:
        as_of_date = date.today()
    
    # Convert as_of_date to pandas datetime for comparison
    as_of_datetime = pd.Timestamp(as_of_date)
    
    # Validate AR DataFrame
    required_ar_cols = ['due_date', 'amount', 'status']
    missing_ar_cols = [col for col in required_ar_cols if col not in ar_df.columns]
    if missing_ar_cols:
        raise ValueError(f"AR DataFrame missing required columns: {missing_ar_cols}")
    
    # Validate AP DataFrame
    required_ap_cols = ['due_date', 'amount', 'status']
    missing_ap_cols = [col for col in required_ap_cols if col not in ap_df.columns]
    if missing_ap_cols:
        raise ValueError(f"AP DataFrame missing required columns: {missing_ap_cols}")
    
    # Validate date columns are datetime
    if not pd.api.types.is_datetime64_any_dtype(ar_df['due_date']):
        raise ValueError("AR DataFrame 'due_date' column must be datetime type")
    
    if not pd.api.types.is_datetime64_any_dtype(ap_df['due_date']):
        raise ValueError("AP DataFrame 'due_date' column must be datetime type")
    
    # Validate amount columns are numeric
    if not pd.api.types.is_numeric_dtype(ar_df['amount']):
        raise ValueError("AR DataFrame 'amount' column must be numeric type")
    
    if not pd.api.types.is_numeric_dtype(ap_df['amount']):
        raise ValueError("AP DataFrame 'amount' column must be numeric type")
    
    # Validate status columns
    valid_statuses = ['open', 'paid']
    invalid_ar_statuses = ar_df[~ar_df['status'].isin(valid_statuses)]['status'].unique()
    if len(invalid_ar_statuses) > 0:
        raise ValueError(f"AR DataFrame contains invalid status values: {invalid_ar_statuses}")
    
    invalid_ap_statuses = ap_df[~ap_df['status'].isin(valid_statuses)]['status'].unique()
    if len(invalid_ap_statuses) > 0:
        raise ValueError(f"AP DataFrame contains invalid status values: {invalid_ap_statuses}")
    
    # Calculate horizon end date
    horizon_end = as_of_datetime + pd.Timedelta(days=horizon_days)
    
    # Filter AR invoices within horizon (include overdue invoices, exclude paid)
    # For AR: include invoices due within horizon OR overdue (due_date < as_of_date)
    # Exclude paid invoices as they don't contribute to future inflows
    ar_horizon_mask = (ar_df['due_date'] <= horizon_end) & (ar_df['status'] == 'open')
    ar_h_df = ar_df[ar_horizon_mask].copy()
    
    # Filter AP bills within provision period (include overdue bills, exclude paid bills)
    # Include overdue bills as they need immediate payment
    # Exclude paid bills as they don't contribute to future outflows
    provision_end = as_of_datetime + pd.Timedelta(days=ap_provision_days)
    ap_provision_mask = (ap_df['due_date'] <= provision_end) & (ap_df['status'] == 'open')
    ap_provision_df = ap_df[ap_provision_mask].copy()
    
    # Initialize ap_h_df for return value (bills within horizon + overdue, exclude paid)
    # Include overdue bills in horizon totals as they need immediate attention
    ap_horizon_mask = (ap_df['due_date'] <= horizon_end) & (ap_df['status'] == 'open')
    ap_h_df = ap_df[ap_horizon_mask].copy()
    
    # Calculate expected inflows from AR
    expected_inflows = 0.0
    if len(ar_h_df) > 0:
        # Calculate days to due for each invoice
        ar_h_df['days_to_due'] = (ar_h_df['due_date'] - as_of_datetime).dt.days
        
        # Calculate payment probability for each invoice
        # Use default collection probabilities if none provided
        if collection_probs is None:
            collection_probs = {
                'overdue': 0.85,
                'within_7_days': 0.70,
                'within_14_days': 0.50,
                'beyond_14_days': 0.30
            }
        
        ar_h_df['payment_probability'] = ar_h_df.apply(
            lambda row: invoice_pay_prob(
                row['days_to_due'], 
                row['status'], 
                collection_probs
            ), 
            axis=1
        )
        
        # Calculate expected inflow: amount × probability
        ar_h_df['expected_amount'] = ar_h_df['amount'] * ar_h_df['payment_probability']
        expected_inflows = ar_h_df['expected_amount'].sum()
    
    # Calculate expected outflows from AP with three-tier probability model
    expected_outflows = 0.0
    if len(ap_provision_df) > 0:
        # Calculate days to due for each bill
        ap_provision_df['days_to_due'] = (ap_provision_df['due_date'] - as_of_datetime).dt.days
        
        # Use default AP probabilities if none provided
        if ap_probs is None:
            ap_probs = {
                'overdue': 1.00,
                'within_horizon': 1.00,
                'beyond_horizon_within_provision': 0.90,
                'beyond_provision': 0.00
            }
        
        # Apply four-tier AP probability model:
        # 1. Overdue: 100% probability (urgent payment required)
        # 2. Within horizon: 100% probability
        # 3. Beyond horizon but within provision: 90% probability
        # 4. Beyond provision: 0% probability (not included)
        def get_ap_probability(days_to_due):
            if days_to_due < 0:  # Overdue bills
                return ap_probs.get('overdue', 1.0)
            elif days_to_due <= horizon_days:
                return ap_probs['within_horizon']
            elif days_to_due <= ap_provision_days:
                return ap_probs.get('beyond_horizon_within_provision', ap_probs.get('beyond_horizon', 0.90))
            else:
                return ap_probs.get('beyond_provision', 0.0)
        
        ap_provision_df['payment_probability'] = ap_provision_df['days_to_due'].apply(get_ap_probability)
        
        # Calculate expected outflow: amount × probability
        ap_provision_df['expected_amount'] = ap_provision_df['amount'] * ap_provision_df['payment_probability']
        expected_outflows = ap_provision_df['expected_amount'].sum()
    
    # Round to 2 decimal places for monetary values
    expected_inflows = round(expected_inflows, 2)
    expected_outflows = round(expected_outflows, 2)
    
    # Calculate total open amounts within horizon (face value, not probability-weighted)
    total_open_receivables = ar_h_df['amount'].sum() if len(ar_h_df) > 0 else 0.0
    total_open_payables = ap_h_df['amount'].sum() if len(ap_h_df) > 0 else 0.0
    
    # Round totals to 2 decimal places
    total_open_receivables = round(total_open_receivables, 2)
    total_open_payables = round(total_open_payables, 2)
    
    return expected_inflows, expected_outflows, total_open_receivables, total_open_payables, ar_h_df, ap_h_df


def get_demo_as_of_date() -> date:
    """
    Get the demo reference date for testing purposes.
    
    Returns:
        Demo date: August 30, 2025
    """
    return date(2025, 8, 30)
