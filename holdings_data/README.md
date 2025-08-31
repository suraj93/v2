# Holdings Database

A simple SQLite-based treasury holdings database for liquid fund tracking and interest accrual.

## Quick Start

```bash
# Run the complete demo
cd holdings_data
python demo.py

# Use the CLI
python -m src.holdings.cli seed holdings_data/sample_holdings.csv
python -m src.holdings.cli list
python -m src.holdings.cli totals
python -m src.holdings.cli post-accrual 2025-08-30
python -m src.holdings.cli ytd 2025
```

## Files

- **`sample_holdings.csv`** - Example CSV with 5 liquid funds (₹15M total)
- **`input_data.csv`** - Your actual holdings data (upload here)
- **`demo.py`** - Complete demonstration script
- **`treasury.db`** - Default SQLite database location

## Database Schema

### Holdings Table
Current withdrawable corpus per instrument/issuer with expected rates.

### Interest Accruals Table  
Daily interest calculations with attribution data.

## Module Structure

The holdings system consists of:
- **`src/holdings/db.py`** - Core SQLite database operations and data models
- **`src/holdings/queries.py`** - High-level query functions for all data operations
- **`src/holdings/cli.py`** - Command-line interface (uses queries module)

## Usage Options

### Option 1: CLI Commands (Recommended)

```bash
# Database operations
python -m src.holdings.cli setup                           # Initialize empty DB
python -m src.holdings.cli seed <csv_file>                 # Load holdings from CSV (overwrite mode - default)
python -m src.holdings.cli seed <csv_file> --update        # Load holdings from CSV (update mode)
python -m src.holdings.cli clear                           # Clear all holdings and accrual data

# Holdings management
python -m src.holdings.cli list                            # List all holdings
python -m src.holdings.cli totals                          # Show corpus totals
python -m src.holdings.cli allocate <instrument> <issuer> <amount>  # Add allocation
python -m src.holdings.cli redeem <amount>                 # Redeem funds

# Interest accruals
python -m src.holdings.cli post-accrual <YYYY-MM-DD>       # Post daily interest
python -m src.holdings.cli daily-series <start> <end>     # Interest time series
python -m src.holdings.cli ytd <year>                     # Year-to-date totals
python -m src.holdings.cli attribution <start> <end>      # Performance attribution
python -m src.holdings.cli daily-detail <start> <end>       # Detailed daily accruals per instrument
```

### Option 2: Direct Python API

```python
from src.holdings import queries

# Get all data operations as JSON-ready dictionaries
result = queries.get_holdings_totals("holdings_data/treasury.db")
print(f"Total: Rs.{result['total_corpus_rupees']:,.2f}")

# All query functions available:
# get_setup_result, get_seed_result, get_clear_result
# get_holdings_list, get_holdings_totals
# get_allocation_result, get_redemption_result  
# get_accrual_result, get_daily_series
# get_ytd_totals, get_attribution, get_daily_detail
```

## CSV Format

Your `input_data.csv` should have these columns:

```csv
instrument_name,issuer,amount_rupees,expected_annual_rate_bps,accrual_basis_days
Overnight Fund - Direct Plan - Growth,Acme Mutual Fund,6000000,630,365
Liquid Fund - Direct Plan - Growth,Bravo Mutual Fund,2500000,645,365
```

Where:
- `amount_rupees` - Holdings value in rupees (float)
- `expected_annual_rate_bps` - Annual rate in basis points (int, e.g., 630 = 6.30%)
- `accrual_basis_days` - Usually 365 (int)

## Interest Calculation

Daily interest = `floor(amount_paise × rate_bps / (10000 × accrual_basis_days))`

Example: ₹1,00,000 at 6.30% = `floor(10000000 × 630 / (10000 × 365))` = ₹1.72/day

*Note: Calculations are done in paise internally for precision, but all outputs show only rupees.*

## Seeding Modes

- **Overwrite Mode (Default)**: `seed <file>` - Clears all existing holdings and accruals, then loads new data
- **Update Mode**: `seed <file> --update` - Adds new holdings without clearing existing data (skips duplicates)
- **Clear**: `clear` - Removes all holdings and accrual data

## Key Features

- **Precision**: All calculations done in paise internally to avoid floating-point errors
- **Clean Output**: All JSON responses show amounts in rupees only 
- **Flexible Seeding**: Overwrite mode for fresh starts, update mode for additions
- **Idempotency**: Re-running operations won't create duplicates  
- **Attribution**: Track which instruments earn how much interest over time periods
- **Hard Limits**: Redemptions fail if insufficient funds (no partial redemptions)
- **JSON Output**: All CLI commands return structured JSON data