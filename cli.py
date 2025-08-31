"""
Command-line interface for treasury auto-sweep engine.
"""

import argparse
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date
from src.core.config import load_settings
from src.core.parse import load_bank, load_ar, load_ap, current_balance
from src.core.predict import horizon_flows, get_demo_as_of_date
from src.core.prescribe import must_keep, deployable, propose_order, create_deployable_attribution
from src.core.perform import submit_order_stub


class NumpyEncoder(json.JSONEncoder):
    """Custom JSON encoder for numpy data types and other problematic objects."""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        elif isinstance(obj, pd.Series):
            return obj.tolist()
        elif isinstance(obj, pd.DataFrame):
            return obj.to_dict('records')
        elif hasattr(obj, 'item'):  # numpy scalars
            return obj.item()
        return super().default(obj)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Treasury Auto-Sweep Engine")
    parser.add_argument("--data-dir", default="data", help="Input data directory")
    parser.add_argument("--out-dir", default="outputs", help="Output directory")
    parser.add_argument("--horizon", type=int, default=7, help="Horizon in days (3-14)")
    parser.add_argument("--execute", action="store_true", help="Execute simulated orders")
    parser.add_argument("--demo", action="store_true", help="Use demo mode with fixed date (2025-08-30)")
    
    args = parser.parse_args()
    
    # Validate horizon
    
    if not 3 <= args.horizon <= 14:
        print("Error: horizon must be between 3 and 14 days")
        return 1
    
    try:
        # Load configuration
        print(f"Loading configuration from {args.data_dir}...")
        settings = load_settings(args.data_dir)
        print(f"OK Configuration loaded: {settings.policy['currency']} currency")
        
        # Load data files
        print("Loading data files...")
        bank_df = load_bank(settings.data_dir / "bank_txns.csv")
        ar_df = load_ar(settings.data_dir / "ar_invoices.csv")
        ap_df = load_ap(settings.data_dir / "ap_bills.csv")
        print(f"OK Bank transactions: {len(bank_df)} rows")
        print(f"OK AR invoices: {len(ar_df)} rows")
        print(f"OK AP bills: {len(ap_df)} rows")
        
        # Calculate current balance
        balance = current_balance(bank_df)
        print(f"OK Current balance: INR {balance:,.2f}")
        
        # Set as-of date (demo mode or current date)
        if args.demo:
            as_of_date = get_demo_as_of_date()
            print(f"OK Demo mode: Using as-of date {as_of_date}")
        else:
            as_of_date = None
            print(f"OK Using current date as reference")
        
        # Calculate expected cash flows
        print("Calculating expected cash flows...")
        inflows, outflows, total_open_ar, total_open_ap, ar_h_df, ap_h_df = horizon_flows(
            ar_df, ap_df, args.horizon, 
            as_of_date=as_of_date,
            collection_probs=settings.model_params.get('ar_collection_probabilities', {}),
            ap_probs=settings.model_params.get('ap_payment_probabilities', {}),
            ap_provision_days=settings.policy.get('ap_provision_days', 14)
        )
        print(f"OK Expected inflows ({args.horizon}d): INR {inflows:,.2f}")
        print(f"OK Expected outflows ({args.horizon}d): INR {outflows:,.2f}")
        print(f"OK Total open AR in horizon: INR {total_open_ar:,.2f} ({len(ar_h_df)} invoices)")
        print(f"OK Total open AP in horizon: INR {total_open_ap:,.2f} ({len(ap_h_df)} bills)")
        
        # Calculate provision-period AP face value for attribution table
        as_of_datetime = pd.to_datetime(as_of_date) if as_of_date else pd.to_datetime('today')
        provision_end = as_of_datetime + pd.Timedelta(days=settings.policy.get('ap_provision_days', 14))
        ap_provision_mask = (ap_df['due_date'] <= provision_end) & (ap_df['status'] == 'open')
        total_open_ap_provision = ap_df[ap_provision_mask]['amount'].sum() if ap_provision_mask.any() else 0.0
        
        # Cash flow attribution table (provision-consistent)
        print("\nCash Flow Attribution:")
        ar_prob_effect = total_open_ar - inflows
        ap_prob_effect = total_open_ap_provision - outflows  
        net_face_value = total_open_ar - total_open_ap_provision
        net_prob_effect = ar_prob_effect - ap_prob_effect
        net_expected = inflows - outflows
        
        print("+-------------+-------------+-------------+-------------+")
        print("| Component   | Face Value  | Prob Effect | Expected    |")
        print("+-------------+-------------+-------------+-------------+")
        print(f"| AR Inflows  | {total_open_ar:>10,.0f} | {-ar_prob_effect:>10,.0f} | {inflows:>10,.0f} |")
        print(f"| AP Outflows | {total_open_ap_provision:>10,.0f} | {-ap_prob_effect:>10,.0f} | {outflows:>10,.0f} |")
        print("+-------------+-------------+-------------+-------------+")
        print(f"| Net Flow    | {net_face_value:>10,.0f} | {-net_prob_effect:>10,.0f} | {net_expected:>10,.0f} |")
        print("+-------------+-------------+-------------+-------------+")
        print("Note: AR conservative collection (30-85%), AP complete payment (90-100%)")
        
        # Apply treasury policy (prescription)
        print("Applying treasury policy...")
        ap_rows = ap_h_df.to_dict('records') if not ap_h_df.empty else []
        mk = must_keep(settings.policy, outflows, ap_rows)
        dep = deployable(balance, inflows, mk, settings.policy)
        order, reasons = propose_order(dep, settings.policy)
        
        print(f"OK Must keep: INR {mk:,.2f}")
        print(f"OK Deployable: INR {dep:,.2f}")
        if order:
            print(f"OK Proposed order: INR {order['proposed']:,.2f} ({order['instrument']})")
            if order['needs_maker_checker']:
                print("   WARNING: Order requires maker-checker approval")
        else:
            print("OK No order proposed")
        print(f"OK Reason codes: {', '.join(reasons)}")
        
        # Create outputs directory
        out_path = Path(args.out_dir)
        out_path.mkdir(exist_ok=True)
        
        # Calculate cash flow attribution metrics (provision-consistent)
        ar_prob_effect = total_open_ar - inflows
        ap_prob_effect = total_open_ap_provision - outflows  
        net_prob_effect = ar_prob_effect - ap_prob_effect
        net_expected_flow = inflows - outflows
        
        # Create detailed deployable attribution
        deployable_attribution = create_deployable_attribution(
            policy=settings.policy,
            balance=balance,
            expected_inflows=inflows,
            expected_outflows=outflows,
            total_open_ar=total_open_ar,
            total_open_ap=total_open_ap_provision,
            ap_rows=ap_rows,
            deployable_amt=dep
        )
        
        # Generate summary
        summary = {
            "balance": balance,
            "expected_inflows": inflows,
            "expected_outflows": outflows,
            "total_open_receivables": total_open_ar,
            "total_open_payables": total_open_ap,
            "ar_probability_effect": round(ar_prob_effect, 2),
            "ap_probability_effect": round(ap_prob_effect, 2),
            "net_probability_effect": round(net_prob_effect, 2),
            "net_expected_flow": round(net_expected_flow, 2),
            "must_keep": mk,
            "deployable": dep,
            "deployable_attribution": deployable_attribution,
            "order": order,
            "reasons": reasons,
            "horizon_days": args.horizon,
            "as_of_date": as_of_date.isoformat() if as_of_date else None
        }
        
        # Write summary
        summary_file = out_path / "summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, cls=NumpyEncoder)
        print(f"OK Summary written to {summary_file}")
        
        # Write field interpretation guide
        guide_file = out_path / "SUMMARY_FIELD_GUIDE.md"
        guide_content = """# Treasury Summary Field Interpretation Guide

This guide explains how to interpret the `summary.json` fields generated by the treasury auto-sweep engine.

## Core Cash Position Fields

### `balance`
- **Definition**: Current bank account balance at time of analysis
- **Usage**: Starting point for all treasury calculations
- **Example**: `1599081.36` = ₹1.59M current cash

### `horizon_days` 
- **Definition**: Forecast horizon in days (typically 3-14 days)
- **Usage**: Defines scope of AR cash flow predictions (AP uses provision period)
- **Example**: `7` = analyzing AR collections in next 7 business days

### `as_of_date`
- **Definition**: Analysis date (demo mode uses fixed date for testing)
- **Usage**: Reference point for due date calculations
- **Example**: `"2025-08-30"` = analysis performed as of this date

## Cash Flow Forecast Fields (Top-Level)

### Raw Amounts (Face Value)
- **`total_open_receivables`**: Face value of AR invoices due within horizon period
- **`total_open_payables`**: Face value of AP bills due within horizon period (NOT provision)
- **Usage**: Shows horizon-scoped amounts on the books before probability adjustments
- **Note**: For complete AP analysis, see `deployable_attribution.cash_flows.raw_ap_payables`

### Expected Amounts (Probability-Adjusted)
- **`expected_inflows`**: Probability-weighted AR collections within horizon
- **`expected_outflows`**: Probability-weighted AP payments within provision period (14d)
- **Usage**: Realistic cash flow forecasts for treasury planning
- **Note**: Outflows use provision period (14d) for comprehensive policy analysis

### Probability Effects (Top-Level Summary)
- **`ar_probability_effect`**: AR collection discount due to aging-based probabilities
- **`ap_probability_effect`**: AP payment discount (provision vs horizon scope difference)
- **`net_probability_effect`**: Combined modeling conservatism impact
- **`net_expected_flow`**: Net cash impact (`expected_inflows - expected_outflows`)

## Treasury Policy Fields

### Buffer Calculations
- **`must_keep`**: Minimum cash that must remain in account
  - **Components**: See `deployable_attribution.safety_buffers` for detailed breakdown
  - **Usage**: Safety threshold below which no investments are made

### Investment Decision
- **`deployable`**: Surplus cash available for investment after all policy requirements
- **`order`**: Investment proposal (null if no deployment possible)
- **`reasons`**: Array of reason codes explaining the treasury decision

## Detailed Attribution Structure: `deployable_attribution`

### `deployable_attribution.cash_flows`
Complete cash flow analysis with consistent scope (provision period for AP):

- **`current_balance`**: Starting cash position
- **`raw_ar_receivables`**: Face value AR within horizon period
- **`raw_ap_payables`**: Face value AP within provision period (comprehensive view)
- **`raw_net_position`**: Book position before probability adjustments
- **`expected_inflows`**: Probability-weighted AR collections  
- **`expected_outflows`**: Probability-weighted AP payments
- **`net_expected_flow`**: Expected net cash impact
- **`ar_probability_effect`**: AR collection risk discount
- **`ap_probability_effect`**: AP payment timing discount  
- **`net_probability_effect`**: Total conservatism from probability modeling

### `deployable_attribution.safety_buffers`
Detailed breakdown of `must_keep` requirement:

#### `base_buffers`
- **`operating_cash`**: Policy-defined minimum operating balance
- **`payroll_buffer`**: Employment obligation reserve
- **`tax_buffer`**: Compliance and tax payment reserve
- **`subtotal`**: Sum of base operational buffers

#### `vendor_buffers`  
- **`critical_vendors`**: Count of unique critical-tier vendors in AP horizon
- **`regular_vendors`**: Count of unique regular-tier vendors in AP horizon
- **`critical_buffer`**: `critical_vendors × critical_buffer_amount`
- **`regular_buffer`**: `regular_vendors × regular_buffer_amount`
- **`subtotal`**: Total vendor-based buffer requirement

#### `shock_buffer`
- **`multiplier`**: Policy shock factor (typically 1.15 = 15% additional buffer)
- **`expected_outflows`**: Base amount for shock calculation
- **`buffer_amount`**: Additional buffer for outflow volatility

### `deployable_attribution.deployable_calculation`
Step-by-step deployable amount calculation:

- **`available_balance`**: Starting cash position
- **`recognition_ratio`**: Policy-defined inflow recognition percentage
- **`recognized_inflows`**: Conservative portion of expected inflows counted
- **`total_available`**: Available cash + recognized inflows
- **`less_must_keep`**: Required safety buffer deduction
- **`deployable_amount`**: Final surplus available for investment

## Analytical Usage Patterns

### 1. Comprehensive Cash Flow Analysis
```python
# Access detailed cash flows
cash_flows = summary["deployable_attribution"]["cash_flows"]
raw_position = cash_flows["raw_net_position"]
expected_position = cash_flows["net_expected_flow"]
probability_impact = cash_flows["net_probability_effect"]

# Analysis: probability_impact = expected_position - raw_position
```

### 2. Buffer Requirement Analysis
```python
# Analyze buffer composition
buffers = summary["deployable_attribution"]["safety_buffers"]
base_pct = buffers["base_buffers"]["subtotal"] / buffers["total_must_keep"]
vendor_pct = buffers["vendor_buffers"]["subtotal"] / buffers["total_must_keep"] 
shock_pct = buffers["shock_buffer"]["buffer_amount"] / buffers["total_must_keep"]

# Identify dominant buffer component
```

### 3. Liquidity Stress Testing
```python
# Calculate liquidity ratios
calc = summary["deployable_attribution"]["deployable_calculation"]
liquidity_ratio = calc["total_available"] / calc["less_must_keep"]
recognition_impact = calc["recognized_inflows"] / summary["expected_inflows"]

# Assess conservatism level
```

### 4. Vendor Risk Assessment
```python
# Analyze vendor concentration
vendor_buf = summary["deployable_attribution"]["safety_buffers"]["vendor_buffers"]
total_vendors = vendor_buf["critical_vendors"] + vendor_buf["regular_vendors"]
critical_concentration = vendor_buf["critical_vendors"] / total_vendors
vendor_buffer_intensity = vendor_buf["subtotal"] / summary["expected_outflows"]
```

## Decision Tree for Analysis

### Liquidity Assessment
1. **Check `deployable > 0`**: Investment opportunity exists
2. **Review `cash_flows.net_expected_flow`**: Underlying cash generation/consumption
3. **Analyze `safety_buffers` composition**: Buffer requirement drivers
4. **Evaluate `deployable_calculation.recognition_ratio`**: Inflow conservatism level

### Risk Evaluation  
1. **AR Collection Risk**: `ar_probability_effect / raw_ar_receivables`
2. **AP Payment Certainty**: `1 - (ap_probability_effect / raw_ap_payables)`
3. **Buffer Coverage**: `total_available / total_must_keep`
4. **Vendor Concentration**: Critical vs regular vendor split

### Policy Optimization Opportunities
1. **High vendor buffers**: Consider vendor tier reclassification
2. **High shock buffer**: Review outflow shock multiplier appropriateness  
3. **Low recognition ratio**: Assess inflow forecasting confidence
4. **Large probability effects**: Review collection/payment probability models

## Integration with External Systems

### For Risk Management Systems
- Monitor `net_probability_effect` trends
- Alert on `vendor_buffers.subtotal` increases  
- Track `deployable_calculation.recognition_ratio` changes

### For Cash Management Systems
- Use `expected_inflows/outflows` for liquidity forecasting
- Apply `deployable_amount` for investment sizing
- Reference `order` details for execution

### For Treasury Reporting
- Present `cash_flows` section for CFO dashboards
- Use `safety_buffers` breakdown for policy discussions
- Reference `reasons` for decision audit trails

This comprehensive structure enables sophisticated treasury analysis while maintaining clear interpretability for both human users and automated systems."""
        
        with open(guide_file, 'w', encoding='utf-8') as f:
            f.write(guide_content)
        print(f"OK Field guide written to {guide_file}")
        
        # Execute performance module if --execute flag is set
        if args.execute:
            print("Executing performance module...")
            execution_state = submit_order_stub(
                order=order,
                out_dir=args.out_dir,
                balance=balance,
                expected_inflows=inflows,
                expected_outflows=outflows,
                must_keep_amt=mk,
                policy=settings.policy,
                ap_rows=ap_rows
            )
            
            # Update summary with execution state
            summary["execution_state"] = execution_state
            
            # Rewrite summary with execution state
            with open(summary_file, 'w') as f:
                json.dump(summary, f, indent=2, cls=NumpyEncoder)
            
            # Enhanced performance output logging
            perform_file = Path(args.out_dir) / "perform.json"
            dated_file = Path(args.out_dir) / f"perform_{summary.get('as_of_date', date.today().isoformat())}.json"
            
            print(f"OK Performance files generated:")
            print(f"   - Summary: {perform_file}")
            print(f"   - Historical: {dated_file}")
            
            # Show key performance metrics
            if perform_file.exists():
                try:
                    with open(perform_file, 'r') as f:
                        perf_data = json.load(f)
                    
                    print(f"OK Performance Summary:")
                    print(f"   - Date: {perf_data.get('date')}")
                    print(f"   - Deployable Value: INR {perf_data.get('deployable_value', 0):,.2f}")
                    print(f"   - Safety Buffers: INR {perf_data.get('safety_buffers', 0):,.2f}")
                    
                    if perf_data.get('deploy_instrument'):
                        print(f"   - Deployment Target: {perf_data.get('deploy_instrument')} ({perf_data.get('deploy_issuer')})")
                        print(f"   - Max Tenor: {perf_data.get('max_tenor')} days")
                        print(f"   - Approval Required: {'Yes' if perf_data.get('approval_needed') else 'No'}")
                    else:
                        print(f"   - Deployment Target: None (insufficient deployable surplus)")
                    
                    # Show description if available
                    desc = perf_data.get('description', '')
                    if desc:
                        print(f"OK Deployment Rationale:")
                        for i, line in enumerate(desc.split('\n'), 1):
                            # Handle rupee symbol encoding for console display
                            display_line = line.replace('₹', 'INR ')
                            print(f"   {i}. {display_line}")
                            
                except (json.JSONDecodeError, IOError) as e:
                    print(f"   Warning: Could not read performance data: {e}")
        
        # Enhanced output summary
        print(f"\n{'='*60}")
        print(f"TREASURY AUTO-SWEEP EXECUTION SUMMARY")
        print(f"{'='*60}")
        print(f"Horizon:             {args.horizon} days")
        print(f"Mode:                {'Demo (2025-08-30)' if args.demo else 'Live'}")
        print(f"Current Balance:     INR {balance:,.2f}")
        print(f"Expected Inflows:    INR {inflows:,.2f}")
        print(f"Expected Outflows:   INR {outflows:,.2f}")
        print(f"Must Keep Amount:    INR {mk:,.2f}")
        print(f"Deployable Surplus:  INR {dep:,.2f}")
        
        if order:
            print(f"Investment Proposal: INR {order['proposed']:,.2f}")
            print(f"Target Instrument:   {order['instrument']} ({order['issuer']})")
            print(f"Maker-Checker:       {'Required' if order['needs_maker_checker'] else 'Not required'}")
        else:
            print(f"Investment Proposal: None")
        
        print(f"Decision Rationale:  {', '.join(reasons)}")
        print(f"Execution Mode:      {'Performance Output Generated' if args.execute else 'Analysis Only'}")
        print(f"Output Directory:    {Path(args.out_dir).absolute()}")
        
        if args.execute:
            print(f"\nStatus: Performance module executed successfully")
            print(f"Next:   Run presentation module to generate EOD summary")
        else:
            print(f"\nStatus: Analysis completed")
            print(f"Next:   Add --execute flag to generate performance outputs")
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
