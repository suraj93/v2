# Core-Loop Treasury Auto-Sweep

An offline, explainable auto-sweep engine using local CSV/JSON inputs that produces a human-readable EOD summary and an optional simulated order.

## Project Structure

```
/core-loop
  /data/                         # INPUTS (CSV/JSON)
    bank_txns.csv
    ar_invoices.csv
    ap_bills.csv
    policy.json
    cutoff_calendar.json
  /src/
    __init__.py
    cli.py                       # orchestration (one-shot run)
    /core/
      __init__.py
      config.py                  # load_settings(data_dir) -> Settings
      reason_codes.py            # REASONS = {...}
      parse.py                   # loaders, balance computation
      predict.py                 # AR/AP horizon flows
      prescribe.py               # policy math, allocation
      perform.py                 # simulated order lifecycle
      present.py                 # EOD markdown builder
      models.py                  # (optional) pydantic models
  /outputs/                      # OUTPUTS
    summary.json
    EOD_Summary.md
    order_{uuid}.json            # if execute & order exists
  /tests/
    test_core_loop.py
```

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run CLI (default horizon=7)
python -m src.cli --data-dir data --out-dir outputs --horizon 7 --execute

# Run tests
pytest -q
```

## Data Format

The system expects CSV files in the `/data` folder:
- `bank_txns.csv` - Bank transactions with date, description, amount
- `ar_invoices.csv` - Accounts receivable invoices
- `ap_bills.csv` - Accounts payable bills
- `policy.json` - Treasury policy configuration
- `cutoff_calendar.json` - Market cutoff and holiday calendar

