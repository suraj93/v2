# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the main CLI application
python -m src.cli --data-dir data --out-dir outputs --horizon 7 --execute

# Run in demo mode (uses fixed date 2025-08-30 for testing)
python -m src.cli --data-dir data --out-dir outputs --horizon 7 --demo

# Run tests
pytest -q

# Run specific test files
pytest tests/test_core_loop.py -v
```

## Architecture Overview

This is a **treasury auto-sweep engine** that processes local CSV/JSON financial data to generate cash flow predictions and investment recommendations. The system is designed to be offline, explainable, and produce human-readable outputs.

### Core Data Pipeline

1. **Parse** (`src/core/parse.py`) - Load and validate CSV data files
2. **Predict** (`src/core/predict.py`) - Forecast AR/AP cash flows within horizon
3. **Prescribe** (`src/core/prescribe.py`) - Apply treasury policy and propose orders
4. **Perform** (`src/core/perform.py`) - Simulate order execution
5. **Present** (`src/core/present.py`) - Generate EOD markdown summaries

### Module Structure

- **`src/core/config.py`** - Loads policy.json and cutoff_calendar.json configuration
- **`src/core/parse.py`** - CSV loaders with balance calculations and data validation
- **`src/core/predict.py`** - Cash flow forecasting using payment probabilities
- **`src/core/reason_codes.py`** - Enumerated reason codes for all decision points
- **`src/cli.py`** - Main orchestration entry point

### Key Data Flows

The system expects these input files in the `data/` directory:
- `bank_txns.csv` - Bank transactions (date, description, amount, running_balance)
- `ar_invoices.csv` - Accounts receivable (invoice_id, amount, issue_date, due_date, status)
- `ap_bills.csv` - Accounts payable (bill_id, amount, issue_date, due_date, vendor_tier, status)
- `policy.json` - Treasury policy configuration including `ap_provision_days`
- `cutoff_calendar.json` - Market cutoffs and holidays
- `ar_ap_model_params.json` - Cash flow prediction probability models

### Cash Flow Prediction Methodology

**AR (Accounts Receivable):**
- Includes only **open** invoices (paid invoices excluded from forecasts)
- Covers invoices due within horizon OR already overdue
- Probability-weighted by days to due: overdue (85%), ≤7 days (70%), ≤14 days (50%), >14 days (30%)

**AP (Accounts Payable) - Four-Tier Model:**
- Includes only **open** bills (paid bills excluded from forecasts)
- **Overdue** (past due date): 100% probability - urgent payment required
- **Within horizon** (≤7 days): 100% probability - immediate obligations
- **Beyond horizon but within provision** (8-14 days): 90% probability - early payment buffer
- **Beyond provision** (>14 days): 0% probability - ignored for current decisions
- Provision period configurable via `policy.json` `ap_provision_days` parameter

### Implementation Status

The system is partially implemented with working file readers, configuration loading, and cash flow prediction. The prescription, performance, and presentation modules are still in development. Current CLI generates basic JSON summaries with cash flow forecasts.

### Demo Data

Test data is available showing ₹1.6M current balance with 56 AR invoices (₹6.1M) and 59 AP bills across vendor tiers. Demo mode uses fixed date 2025-08-30 for consistent testing.