"""
INR formatting and IST time utilities for treasury dashboard.
"""

from datetime import datetime
import pytz
from typing import Union


def fmt_inr_lakh_style(rupees: float) -> str:
    """
    Format rupees in Lakh/Crore style.
    
    Examples:
        1599081.36 -> "₹15.99L"
        12500000 -> "₹1.25Cr"
        50000 -> "₹50K"
        0 -> "₹0"
    """
    if rupees == 0:
        return "₹0"
    
    abs_rupees = abs(rupees)
    sign = "-" if rupees < 0 else ""
    
    if abs_rupees >= 10_000_000:  # 1 Crore or more
        crores = abs_rupees / 10_000_000
        if crores >= 100:
            return f"{sign}₹{crores:.0f}Cr"
        elif crores >= 10:
            return f"{sign}₹{crores:.1f}Cr"
        else:
            return f"{sign}₹{crores:.2f}Cr"
    
    elif abs_rupees >= 100_000:  # 1 Lakh or more
        lakhs = abs_rupees / 100_000
        if lakhs >= 100:
            return f"{sign}₹{lakhs:.0f}L"
        elif lakhs >= 10:
            return f"{sign}₹{lakhs:.1f}L"
        else:
            return f"{sign}₹{lakhs:.2f}L"
    
    elif abs_rupees >= 1_000:  # 1 Thousand or more
        thousands = abs_rupees / 1_000
        if thousands >= 100:
            return f"{sign}₹{thousands:.0f}K"
        elif thousands >= 10:
            return f"{sign}₹{thousands:.1f}K"
        else:
            return f"{sign}₹{thousands:.2f}K"
    
    else:  # Less than 1000
        return f"{sign}₹{abs_rupees:.0f}"


def to_ist(dt_input: Union[str, datetime, None] = None) -> str:
    """
    Convert datetime to IST formatted string.
    
    Args:
        dt_input: Datetime string, datetime object, or None (uses current time)
    
    Returns:
        IST formatted string like "30 Aug 2025, 10:05 IST"
    """
    ist_tz = pytz.timezone('Asia/Kolkata')
    
    if dt_input is None:
        # Use current time
        dt = datetime.now(ist_tz)
    elif isinstance(dt_input, str):
        # Parse string - handle ISO format from JSON
        if dt_input.endswith('Z'):
            dt_utc = datetime.fromisoformat(dt_input[:-1] + '+00:00')
        elif '+' in dt_input or dt_input.endswith(('Z', 'z')):
            dt_utc = datetime.fromisoformat(dt_input)
        else:
            # Assume it's a date string like "2025-08-30"
            dt_utc = datetime.fromisoformat(dt_input + 'T00:00:00+00:00')
        
        # Convert to IST
        dt = dt_utc.astimezone(ist_tz)
    else:
        # Assume datetime object
        if dt_input.tzinfo is None:
            # Assume UTC if no timezone
            dt_input = dt_input.replace(tzinfo=pytz.UTC)
        dt = dt_input.astimezone(ist_tz)
    
    return dt.strftime("%d %b %Y, %H:%M IST")


def format_refresh_time() -> str:
    """Get current IST time for 'Last refreshed' display."""
    ist_tz = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist_tz)
    return now.strftime("%H:%M IST")