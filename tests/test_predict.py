"""
Tests for the cash flow prediction module.
"""

import pytest
import pandas as pd
from datetime import date, datetime
from pathlib import Path
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.predict import invoice_pay_prob, horizon_flows, get_demo_as_of_date


class TestInvoicePayProb:
    """Test the invoice_pay_prob function."""
    
    def test_paid_invoices_are_filtered_out_not_probabilities(self):
        """Test that paid invoices are filtered out in horizon_flows, not handled by invoice_pay_prob."""
        collection_probs = {
            'overdue': 0.85,
            'within_7_days': 0.70,
            'within_14_days': 0.50,
            'beyond_14_days': 0.30
        }
        
        # invoice_pay_prob should only be called with open invoices
        # Test that it still works correctly for open invoices
        assert invoice_pay_prob(-5, 'open', collection_probs) == 0.85
        assert invoice_pay_prob(0, 'open', collection_probs) == 0.70
        assert invoice_pay_prob(10, 'open', collection_probs) == 0.50
        assert invoice_pay_prob(20, 'open', collection_probs) == 0.30
    
    def test_open_invoice_probabilities(self):
        """Test that open invoices return correct probabilities based on days to due."""
        collection_probs = {
            'overdue': 0.85,
            'within_7_days': 0.70,
            'within_14_days': 0.50,
            'beyond_14_days': 0.30
        }
        
        # Test overdue invoices
        assert invoice_pay_prob(-1, 'open', collection_probs) == 0.85
        assert invoice_pay_prob(-10, 'open', collection_probs) == 0.85
        
        # Test within 7 days
        assert invoice_pay_prob(0, 'open', collection_probs) == 0.70
        assert invoice_pay_prob(5, 'open', collection_probs) == 0.70
        assert invoice_pay_prob(7, 'open', collection_probs) == 0.70
        
        # Test within 14 days
        assert invoice_pay_prob(8, 'open', collection_probs) == 0.50
        assert invoice_pay_prob(14, 'open', collection_probs) == 0.50
        
        # Test beyond 14 days
        assert invoice_pay_prob(15, 'open', collection_probs) == 0.30
        assert invoice_pay_prob(30, 'open', collection_probs) == 0.30
    
    def test_invalid_status_raises_error(self):
        """Test that invalid status values raise ValueError."""
        collection_probs = {
            'overdue': 0.85,
            'within_7_days': 0.70,
            'within_14_days': 0.50,
            'beyond_14_days': 0.30
        }
        
        with pytest.raises(ValueError, match="Invalid status 'invalid_status'"):
            invoice_pay_prob(0, 'invalid_status', collection_probs)
    
    def test_missing_collection_prob_keys_raises_error(self):
        """Test that missing collection probability keys raise ValueError."""
        incomplete_probs = {
            'overdue': 0.85,
            'within_7_days': 0.70
            # Missing within_14_days and beyond_14_days
        }
        
        with pytest.raises(ValueError, match="Missing collection probability keys"):
            invoice_pay_prob(0, 'open', incomplete_probs)
    
    def test_invalid_probability_values_raise_error(self):
        """Test that invalid probability values raise ValueError."""
        invalid_probs = {
            'overdue': 1.5,  # > 1.0
            'within_7_days': 0.70,
            'within_14_days': 0.50,
            'beyond_14_days': 0.30
        }
        
        with pytest.raises(ValueError, match="Invalid probability for overdue: 1.5"):
            invoice_pay_prob(0, 'open', invalid_probs)
        
        invalid_probs2 = {
            'overdue': -0.1,  # < 0.0
            'within_7_days': 0.70,
            'within_14_days': 0.50,
            'beyond_14_days': 0.30
        }
        
        with pytest.raises(ValueError, match="Invalid probability for overdue: -0.1"):
            invoice_pay_prob(0, 'open', invalid_probs2)


class TestHorizonFlows:
    """Test the horizon_flows function."""
    
    def setup_method(self):
        """Set up test data for each test method."""
        # Create sample AR data
        self.ar_data = {
            'invoice_id': ['INV001', 'INV002', 'INV003', 'INV004'],
            'customer_id': ['CUST1', 'CUST2', 'CUST3', 'CUST4'],
            'due_date': [
                pd.Timestamp('2025-08-25'),  # Overdue (5 days)
                pd.Timestamp('2025-08-30'),  # Due today
                pd.Timestamp('2025-09-02'),  # Due in 3 days
                pd.Timestamp('2025-09-05')   # Due in 6 days (within 7-day horizon)
            ],
            'amount': [100000, 200000, 150000, 300000],
            'status': ['open', 'open', 'open', 'open']
        }
        
        # Create sample AP data
        self.ap_data = {
            'bill_id': ['BILL001', 'BILL002', 'BILL003'],
            'vendor_id': ['VEND1', 'VEND2', 'VEND3'],
            'due_date': [
                pd.Timestamp('2025-08-30'),  # Due today
                pd.Timestamp('2025-09-01'),  # Due in 1 day
                pd.Timestamp('2025-09-05')   # Due in 5 days
            ],
            'amount': [50000, 75000, 125000],
            'status': ['open', 'open', 'open']
        }
        
        self.collection_probs = {
            'overdue': 0.85,
            'within_7_days': 0.70,
            'within_14_days': 0.50,
            'beyond_14_days': 0.30
        }
        
        self.as_of_date = date(2025, 8, 30)  # August 30, 2025
    
    def test_basic_horizon_flows_calculation(self):
        """Test basic horizon flows calculation with 7-day horizon."""
        ar_df = pd.DataFrame(self.ar_data)
        ap_df = pd.DataFrame(self.ap_data)
        
        inflows, outflows, total_open_ar, total_open_ap, ar_h_df, ap_h_df = horizon_flows(
            ar_df, ap_df, horizon_days=7, 
            as_of_date=self.as_of_date,
            collection_probs=self.collection_probs
        )
        
        # Expected calculations:
        # AR: INV001 (overdue, 100k * 0.85) + INV002 (due today, 200k * 0.70) + INV003 (due in 3 days, 150k * 0.70) + INV004 (due in 6 days, 300k * 0.70)
        # = 85,000 + 140,000 + 105,000 + 210,000 = 540,000
        expected_inflows = 540000.0
        
        # AP: BILL001 (50k) + BILL002 (75k) + BILL003 (125k) = 250,000
        expected_outflows = 250000.0
        
        assert inflows == expected_inflows
        assert outflows == expected_outflows
        assert len(ar_h_df) == 4  # 4 AR invoices within 7-day horizon
        assert len(ap_h_df) == 3  # 3 AP bills within 7-day horizon
    
    def test_horizon_flows_with_different_horizon(self):
        """Test horizon flows with different horizon periods."""
        ar_df = pd.DataFrame(self.ar_data)
        ap_df = pd.DataFrame(self.ap_data)
        
        # Test with 3-day horizon
        inflows, outflows, total_open_ar, total_open_ap, ar_h_df, ap_h_df = horizon_flows(
            ar_df, ap_df, horizon_days=3,
            as_of_date=self.as_of_date,
            collection_probs=self.collection_probs
        )
        
        # Only invoices/bills due within 3 days should be included
        assert len(ar_h_df) == 3  # INV001 (overdue) + INV002 (due today) + INV003 (due in 3 days)
        assert len(ap_h_df) == 2  # BILL001 (due today) + BILL002 (due in 1 day)
    
    def test_horizon_flows_with_paid_invoices(self):
        """Test that paid invoices are handled correctly."""
        ar_data_with_paid = self.ar_data.copy()
        ar_data_with_paid['status'] = ['paid', 'open', 'open', 'open']
        
        ar_df = pd.DataFrame(ar_data_with_paid)
        ap_df = pd.DataFrame(self.ap_data)
        
        inflows, outflows, total_open_ar, total_open_ap, ar_h_df, ap_h_df = horizon_flows(
            ar_df, ap_df, horizon_days=7,
            as_of_date=self.as_of_date,
            collection_probs=self.collection_probs
        )
        
        # INV001 is paid, so it's FILTERED OUT (no longer contributes to inflows)
        # Only open invoices contribute:
        # INV002: 200k * 0.70 = 140,000
        # INV003: 150k * 0.70 = 105,000
        # INV004: 300k * 0.70 = 210,000
        # Total: 455,000
        expected_inflows = 455000.0
        
        assert inflows == expected_inflows
    
    def test_empty_dataframes(self):
        """Test handling of empty DataFrames."""
        # Create empty DataFrames with proper column types
        empty_ar = pd.DataFrame({
            'due_date': pd.Series(dtype='datetime64[ns]'),
            'amount': pd.Series(dtype='float64'),
            'status': pd.Series(dtype='object')
        })
        empty_ap = pd.DataFrame({
            'due_date': pd.Series(dtype='datetime64[ns]'),
            'amount': pd.Series(dtype='float64'),
            'status': pd.Series(dtype='object')
        })
        
        inflows, outflows, total_open_ar, total_open_ap, ar_h_df, ap_h_df = horizon_flows(
            empty_ar, empty_ap, horizon_days=7,
            as_of_date=self.as_of_date,
            collection_probs=self.collection_probs
        )
        
        assert inflows == 0.0
        assert outflows == 0.0
        assert len(ar_h_df) == 0
        assert len(ap_h_df) == 0
    
    def test_missing_columns_raises_error(self):
        """Test that missing required columns raise ValueError."""
        ar_df_missing_col = pd.DataFrame({
            'invoice_id': ['INV001'],
            'due_date': [pd.Timestamp('2025-08-30')],
            # Missing 'amount' and 'status' columns
        })
        
        ap_df = pd.DataFrame(self.ap_data)
        
        with pytest.raises(ValueError, match="AR DataFrame missing required columns"):
            horizon_flows(ar_df_missing_col, ap_df, horizon_days=7)
    
    def test_invalid_horizon_days_raises_error(self):
        """Test that invalid horizon_days values raise appropriate errors."""
        ar_df = pd.DataFrame(self.ar_data)
        ap_df = pd.DataFrame(self.ap_data)
        
        # Test non-integer
        with pytest.raises(TypeError, match="horizon_days must be an integer"):
            horizon_flows(ar_df, ap_df, horizon_days="7")
        
        # Test out of range
        with pytest.raises(ValueError, match="horizon_days must be between 1 and 365"):
            horizon_flows(ar_df, ap_df, horizon_days=0)
        
        with pytest.raises(ValueError, match="horizon_days must be between 1 and 365"):
            horizon_flows(ar_df, ap_df, horizon_days=366)
    
    def test_invalid_status_values_raise_error(self):
        """Test that invalid status values raise ValueError."""
        ar_data_invalid_status = self.ar_data.copy()
        ar_data_invalid_status['status'] = ['open', 'invalid', 'open', 'open']
        
        ar_df = pd.DataFrame(ar_data_invalid_status)
        ap_df = pd.DataFrame(self.ap_data)
        
        with pytest.raises(ValueError, match="AR DataFrame contains invalid status values"):
            horizon_flows(ar_df, ap_df, horizon_days=7)
    
    def test_output_dataframe_structure(self):
        """Test that output DataFrames have the expected structure."""
        ar_df = pd.DataFrame(self.ar_data)
        ap_df = pd.DataFrame(self.ap_data)
        
        inflows, outflows, total_open_ar, total_open_ap, ar_h_df, ap_h_df = horizon_flows(
            ar_df, ap_df, horizon_days=7,
            as_of_date=self.as_of_date,
            collection_probs=self.collection_probs
        )
        
        # Check AR horizon DataFrame structure
        expected_ar_cols = ['invoice_id', 'customer_id', 'due_date', 'amount', 'status', 'days_to_due', 'payment_probability', 'expected_amount']
        for col in expected_ar_cols:
            assert col in ar_h_df.columns
        
        # Check AP horizon DataFrame structure (should be unchanged)
        expected_ap_cols = ['bill_id', 'vendor_id', 'due_date', 'amount', 'status']
        for col in expected_ap_cols:
            assert col in ap_h_df.columns
        
        # Verify calculated columns
        assert 'days_to_due' in ar_h_df.columns
        assert 'payment_probability' in ar_h_df.columns
        assert 'expected_amount' in ar_h_df.columns
        
        # Verify days_to_due calculation
        inv001_row = ar_h_df[ar_h_df['invoice_id'] == 'INV001']
        inv002_row = ar_h_df[ar_h_df['invoice_id'] == 'INV002']
        
        assert len(inv001_row) > 0, "INV001 should be in horizon DataFrame"
        assert len(inv002_row) > 0, "INV002 should be in horizon DataFrame"
        
        assert inv001_row['days_to_due'].iloc[0] == -5  # Overdue
        assert inv002_row['days_to_due'].iloc[0] == 0   # Due today
    
    def test_ap_beyond_horizon_probabilities(self):
        """Test that AP bills beyond horizon are included in probability calculations."""
        ar_df = pd.DataFrame(self.ar_data)
        
        # Create AP data with bills beyond horizon
        ap_data_beyond_horizon = {
            'bill_id': ['BILL001', 'BILL002', 'BILL003', 'BILL004'],
            'vendor_id': ['VEND1', 'VEND2', 'VEND3', 'VEND4'],
            'due_date': [
                pd.Timestamp('2025-08-30'),  # Due today (within 7-day horizon)
                pd.Timestamp('2025-09-01'),  # Due in 1 day (within 7-day horizon)
                pd.Timestamp('2025-09-10'),  # Due in 10 days (beyond 7-day horizon)
                pd.Timestamp('2025-09-15')   # Due in 15 days (beyond 7-day horizon)
            ],
            'amount': [50000, 75000, 100000, 125000],
            'status': ['open', 'open', 'open', 'open']
        }
        ap_df = pd.DataFrame(ap_data_beyond_horizon)
        
        # Test with 7-day horizon
        inflows, outflows, total_open_ar, total_open_ap, ar_h_df, ap_h_df = horizon_flows(
            ar_df, ap_df, horizon_days=7,
            as_of_date=self.as_of_date,
            collection_probs=self.collection_probs
        )
        
        # Expected calculations:
        # AR: Same as before = 540,000
        expected_inflows = 540000.0
        
        # AP with new three-tier model (horizon=7, default provision=14):
        # BILL001 (day 0, within horizon): 50k * 1.0 = 50,000
        # BILL002 (day 2, within horizon): 75k * 1.0 = 75,000  
        # BILL003 (day 11, beyond horizon but within provision): 100k * 0.9 = 90,000
        # BILL004 (day 16, beyond provision): 125k * 0.0 = 0 (filtered out)
        # Total: 215,000
        expected_outflows = 215000.0
        
        assert inflows == expected_inflows
        assert outflows == expected_outflows
        
        # Verify that AP horizon DataFrame only contains bills within horizon
        assert len(ap_h_df) == 2  # Only BILL001 and BILL002 within 7-day horizon
        
        # Verify that all AP bills were considered for probability calculation
        # (This is handled internally in horizon_flows function)
        
        # Test with custom AP probabilities (four-tier model)
        custom_ap_probs = {
            'overdue': 1.00,
            'within_horizon': 0.95,
            'beyond_horizon_within_provision': 0.80,
            'beyond_provision': 0.00
        }
        
        inflows2, outflows2, total_open_ar2, total_open_ap2, ar_h_df2, ap_h_df2 = horizon_flows(
            ar_df, ap_df, horizon_days=7,
            as_of_date=self.as_of_date,
            collection_probs=self.collection_probs,
            ap_probs=custom_ap_probs
        )
        
        # Expected with custom probabilities (three-tier model):
        # BILL001 (day 0, within horizon): 50k * 0.95 = 47,500
        # BILL002 (day 2, within horizon): 75k * 0.95 = 71,250
        # BILL003 (day 11, beyond horizon but within provision): 100k * 0.80 = 80,000
        # BILL004 (day 16, beyond provision): 125k * 0.00 = 0 (filtered out)
        # Total: 198,750
        expected_outflows2 = 198750.0
        
        assert outflows2 == expected_outflows2

    def test_integration_with_model_params_file(self):
        """Test that the prediction module works correctly with the new model parameters file."""
        from core.config import load_settings
        
        # Load settings to get model parameters
        settings = load_settings("data")
        
        # Verify model parameters are loaded correctly
        assert 'ar_collection_probabilities' in settings.model_params
        assert 'ap_payment_probabilities' in settings.model_params
        
        ar_probs = settings.model_params['ar_collection_probabilities']
        ap_probs = settings.model_params['ap_payment_probabilities']
        
        # Verify AR probabilities structure
        expected_ar_keys = ['overdue', 'within_7_days', 'within_14_days', 'beyond_14_days']
        for key in expected_ar_keys:
            assert key in ar_probs
            assert 0 <= ar_probs[key] <= 1
        
        # Verify AP probabilities structure (new four-tier model)
        expected_ap_keys = ['overdue', 'within_horizon', 'beyond_horizon_within_provision', 'beyond_provision']
        for key in expected_ap_keys:
            assert key in ap_probs
            assert 0 <= ap_probs[key] <= 1
        
        # Test that the probabilities are used correctly in horizon_flows
        ar_df = pd.DataFrame(self.ar_data)
        ap_df = pd.DataFrame(self.ap_data)
        
        inflows, outflows, total_open_ar, total_open_ap, ar_h_df, ap_h_df = horizon_flows(
            ar_df, ap_df, horizon_days=7,
            as_of_date=self.as_of_date,
            collection_probs=ar_probs,
            ap_probs=ap_probs
        )
        
        # Verify that the function works with the loaded parameters
        assert isinstance(inflows, float)
        assert isinstance(outflows, float)
        assert inflows >= 0
        assert outflows >= 0
        
        # Verify that AR probabilities are applied correctly
        if len(ar_h_df) > 0:
            assert 'payment_probability' in ar_h_df.columns
            assert 'expected_amount' in ar_h_df.columns
            
            # Check that probabilities match the loaded values
            overdue_mask = ar_h_df['days_to_due'] < 0
            if overdue_mask.any():
                assert ar_h_df.loc[overdue_mask, 'payment_probability'].iloc[0] == ar_probs['overdue']
            
            within_7_mask = (ar_h_df['days_to_due'] >= 0) & (ar_h_df['days_to_due'] <= 7)
            if within_7_mask.any():
                assert ar_h_df.loc[within_7_mask, 'payment_probability'].iloc[0] == ar_probs['within_7_days']


class TestDemoAsOfDate:
    """Test the get_demo_as_of_date function."""
    
    def test_demo_date_is_correct(self):
        """Test that demo date returns August 30, 2025."""
        demo_date = get_demo_as_of_date()
        assert demo_date == date(2025, 8, 30)
        assert demo_date.year == 2025
        assert demo_date.month == 8
        assert demo_date.day == 30


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
