"""
Reason codes for treasury auto-sweep decisions.
"""

REASONS = {
    "FIXED_BUFFERS": "applied operating + payroll + tax + vendor tier buffers",
    "OUTFLOW_SHOCK": "applied outflow shock multiplier to horizon outflows", 
    "CONSERVATIVE_INFLOW": "recognized only a fraction of expected inflows pre-settlement",
    "WL_OK": "instrument/issuer within whitelist & caps",
    "CUTOFF_PASSED": "suppressed order due to market cutoff",
    "MAKER_CHECKER": "amount >= approval threshold",
    "NO_SURPLUS": "deployable <= 0"
}

