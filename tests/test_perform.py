"""
Tests for the perform module (treasury order execution and output generation).
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import date
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from core.perform import submit_order_stub, _generate_description, _calculate_safety_buffers


class TestGenerateDescription:
    """Test the description generation logic."""
    
    def test_positive_deployable_strong_inflows(self):
        """Test description when deployable > 0 and inflows > outflows."""
        description = _generate_description(
            deployable_amt=500000.0,
            balance=2000000.0,
            expected_inflows=800000.0,
            expected_outflows=600000.0,
            must_keep_amt=1500000.0
        )
        
        lines = description.split('\n')
        assert len(lines) == 2
        assert "Deployable value: INR0.5M" in lines[0]
        assert "current balance INR2.0M" in lines[0]
        assert "expected AR INR0.8M" in lines[0]
        assert "AP INR0.6M" in lines[0]
        assert "buffer INR1.5M" in lines[0]
        assert "Strong inflow position enables surplus deployment" in lines[1]
    
    def test_positive_deployable_weak_inflows(self):
        """Test description when deployable > 0 but outflows > inflows."""
        description = _generate_description(
            deployable_amt=200000.0,
            balance=2000000.0,
            expected_inflows=500000.0,
            expected_outflows=700000.0,
            must_keep_amt=1600000.0
        )
        
        lines = description.split('\n')
        assert len(lines) == 2
        assert "Deployable value: INR0.2M" in lines[0]
        assert "Limited surplus available due to high outflow requirements" in lines[1]
    
    def test_zero_deployable_low_balance(self):
        """Test description when deployable = 0 due to low balance."""
        description = _generate_description(
            deployable_amt=0.0,
            balance=1000000.0,
            expected_inflows=300000.0,
            expected_outflows=400000.0,
            must_keep_amt=2000000.0
        )
        
        lines = description.split('\n')
        assert len(lines) == 2
        assert "Deployable value: INR0.0M" in lines[0]
        assert "No deployment possible - current balance below safety buffer requirements" in lines[1]
    
    def test_zero_deployable_adequate_balance(self):
        """Test description when deployable = 0 but balance is adequate."""
        description = _generate_description(
            deployable_amt=0.0,
            balance=1800000.0,
            expected_inflows=300000.0,
            expected_outflows=600000.0,
            must_keep_amt=2000000.0
        )
        
        lines = description.split('\n')
        assert len(lines) == 2
        assert "Deployable value: INR0.0M" in lines[0]
        assert "No surplus available after accounting for expected outflows" in lines[1]


class TestCalculateSafetyBuffers:
    """Test the safety buffer calculation logic."""
    
    def test_basic_buffers(self):
        """Test calculation with basic policy buffers."""
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.15
        }
        
        ap_rows = [
            {"vendor_id": "V001", "vendor_tier": "critical"},
            {"vendor_id": "V002", "vendor_tier": "regular"},
            {"vendor_id": "V003", "vendor_tier": "regular"},
        ]
        
        expected_outflows = 500000.0
        
        buffers = _calculate_safety_buffers(policy, ap_rows, expected_outflows)
        
        # Base: 1000000 + 400000 + 200000 = 1600000
        # Vendor: 1 critical (300000) + 2 regular (200000) = 500000  
        # Shock: 1.15 * 500000 = 575000
        # Total: 1600000 + 500000 + 575000 = 2675000
        expected_total = 1600000 + 500000 + 575000
        assert buffers == expected_total
    
    def test_duplicate_vendors(self):
        """Test that duplicate vendors are counted only once per tier."""
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.15
        }
        
        ap_rows = [
            {"vendor_id": "V001", "vendor_tier": "critical"},
            {"vendor_id": "V001", "vendor_tier": "critical"},  # Duplicate
            {"vendor_id": "V002", "vendor_tier": "regular"},
            {"vendor_id": "V002", "vendor_tier": "regular"},   # Duplicate
        ]
        
        expected_outflows = 500000.0
        
        buffers = _calculate_safety_buffers(policy, ap_rows, expected_outflows)
        
        # Should count V001 once and V002 once
        # Base: 1600000, Vendor: 300000 + 100000 = 400000, Shock: 575000
        expected_total = 1600000 + 400000 + 575000
        assert buffers == expected_total
    
    def test_empty_ap_rows(self):
        """Test calculation with no AP bills."""
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.15
        }
        
        ap_rows = []
        expected_outflows = 500000.0
        
        buffers = _calculate_safety_buffers(policy, ap_rows, expected_outflows)
        
        # Base: 1600000, Vendor: 0, Shock: 575000
        expected_total = 1600000 + 0 + 575000
        assert buffers == expected_total


class TestSubmitOrderStub:
    """Test the main perform module function."""
    
    def setUp(self):
        """Set up temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
    
    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_with_valid_order(self):
        """Test perform output with a valid deployment order."""
        self.setUp()
        
        order = {
            "proposed": 500000.0,
            "instrument": "Liquid_Fund_Overnight",
            "issuer": "ABC AMC",
            "needs_maker_checker": False
        }
        
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.15,
            "recognition_ratio_expected_inflows": 0.40,
            "whitelist": [
                {"instrument": "Liquid_Fund_Overnight", "issuer": "ABC AMC", "max_amount": 5000000, "max_tenor_days": 1}
            ]
        }
        
        ap_rows = [{"vendor_id": "V001", "vendor_tier": "critical"}]
        
        result = submit_order_stub(
            order=order,
            out_dir=self.temp_dir,
            balance=3000000.0,
            expected_inflows=800000.0,
            expected_outflows=600000.0,
            must_keep_amt=2000000.0,
            policy=policy,
            ap_rows=ap_rows
        )
        
        # Check return value
        assert result["status"] == "pass_through"
        assert "perform_output" in result
        
        # Check files were created
        summary_file = self.temp_path / "perform.json"
        dated_file = self.temp_path / f"perform_{date.today().isoformat()}.json"
        
        assert summary_file.exists()
        assert dated_file.exists()
        
        # Check file contents
        with open(summary_file, 'r') as f:
            data = json.load(f)
        
        assert data["date"] == date.today().isoformat()
        assert data["deployable_value"] > 0
        assert data["current_balance"] == 3000000.0
        assert data["must_keep_value"] == 2000000.0
        assert data["deploy_instrument"] == "Liquid_Fund_Overnight"
        assert data["deploy_issuer"] == "ABC AMC"
        assert data["max_tenor"] == 1
        assert data["approval_needed"] == True
        assert len(data["description"].split('\n')) == 2
        
        self.tearDown()
    
    def test_with_no_order(self):
        """Test perform output when no order is proposed."""
        self.setUp()
        
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.15,
            "recognition_ratio_expected_inflows": 0.40,
            "whitelist": []
        }
        
        ap_rows = []
        
        result = submit_order_stub(
            order=None,
            out_dir=self.temp_dir,
            balance=1500000.0,
            expected_inflows=400000.0,
            expected_outflows=600000.0,
            must_keep_amt=2000000.0,
            policy=policy,
            ap_rows=ap_rows
        )
        
        # Check return value
        assert result["status"] == "pass_through"
        
        # Check files were created
        summary_file = self.temp_path / "perform.json"
        assert summary_file.exists()
        
        # Check file contents
        with open(summary_file, 'r') as f:
            data = json.load(f)
        
        assert data["deployable_value"] == 0.0
        assert data["deploy_instrument"] is None
        assert data["deploy_issuer"] is None
        assert data["max_tenor"] is None
        assert data["approval_needed"] == True
        
        self.tearDown()
    
    def test_file_overwrite(self):
        """Test that files are properly overwritten on subsequent runs."""
        self.setUp()
        
        order = {
            "proposed": 300000.0,
            "instrument": "Liquid_Fund_Overnight",
            "issuer": "ABC AMC",
            "needs_maker_checker": False
        }
        
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.15,
            "recognition_ratio_expected_inflows": 0.40,
            "whitelist": [
                {"instrument": "Liquid_Fund_Overnight", "issuer": "ABC AMC", "max_amount": 5000000, "max_tenor_days": 1}
            ]
        }
        
        # First run
        submit_order_stub(
            order=order,
            out_dir=self.temp_dir,
            balance=2500000.0,
            expected_inflows=600000.0,
            expected_outflows=500000.0,
            must_keep_amt=1800000.0,
            policy=policy,
            ap_rows=[]
        )
        
        # Second run with different values
        submit_order_stub(
            order=order,
            out_dir=self.temp_dir,
            balance=3000000.0,  # Different balance
            expected_inflows=700000.0,
            expected_outflows=600000.0,
            must_keep_amt=2000000.0,
            policy=policy,
            ap_rows=[]
        )
        
        # Check that file contains latest values
        summary_file = self.temp_path / "perform.json"
        with open(summary_file, 'r') as f:
            data = json.load(f)
        
        assert data["current_balance"] == 3000000.0  # Should be updated value
        
        self.tearDown()


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def setUp(self):
        """Set up temporary directory for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
    
    def tearDown(self):
        """Clean up temporary directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_zero_balance(self):
        """Test with zero current balance."""
        self.setUp()
        
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.15,
            "recognition_ratio_expected_inflows": 0.40,
            "whitelist": []
        }
        
        result = submit_order_stub(
            order=None,
            out_dir=self.temp_dir,
            balance=0.0,  # Zero balance
            expected_inflows=500000.0,
            expected_outflows=300000.0,
            must_keep_amt=1800000.0,
            policy=policy,
            ap_rows=[]
        )
        
        summary_file = self.temp_path / "perform.json"
        with open(summary_file, 'r') as f:
            data = json.load(f)
        
        assert data["current_balance"] == 0.0
        assert data["deployable_value"] == 0.0
        assert "No deployment possible" in data["description"]
        
        self.tearDown()
    
    def test_extremely_high_deployable(self):
        """Test with very high deployable amount."""
        self.setUp()
        
        order = {
            "proposed": 10000000.0,  # 10M proposed
            "instrument": "Liquid_Fund_Overnight",
            "issuer": "ABC AMC",
            "needs_maker_checker": True
        }
        
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.15,
            "recognition_ratio_expected_inflows": 0.40,
            "whitelist": [
                {"instrument": "Liquid_Fund_Overnight", "issuer": "ABC AMC", "max_amount": 50000000, "max_tenor_days": 1}
            ]
        }
        
        result = submit_order_stub(
            order=order,
            out_dir=self.temp_dir,
            balance=20000000.0,  # 20M balance
            expected_inflows=3000000.0,
            expected_outflows=1000000.0,
            must_keep_amt=3000000.0,
            policy=policy,
            ap_rows=[]
        )
        
        summary_file = self.temp_path / "perform.json"
        with open(summary_file, 'r') as f:
            data = json.load(f)
        
        assert data["current_balance"] == 20000000.0
        assert data["deployable_value"] > 15000000.0  # Should be quite high
        assert data["deploy_instrument"] == "Liquid_Fund_Overnight"
        assert data["approval_needed"] == True  # Always true by default
        assert "Strong inflow position" in data["description"]
        
        self.tearDown()
    
    def test_negative_expected_inflows(self):
        """Test with negative expected inflows (edge case)."""
        self.setUp()
        
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.15,
            "recognition_ratio_expected_inflows": 0.40,
            "whitelist": []
        }
        
        result = submit_order_stub(
            order=None,
            out_dir=self.temp_dir,
            balance=2000000.0,
            expected_inflows=-100000.0,  # Negative inflows
            expected_outflows=500000.0,
            must_keep_amt=1800000.0,
            policy=policy,
            ap_rows=[]
        )
        
        summary_file = self.temp_path / "perform.json"
        with open(summary_file, 'r') as f:
            data = json.load(f)
        
        # Should handle gracefully
        assert data["deployable_value"] >= 0.0  # Should be clamped to zero
        
        self.tearDown()
    
    def test_missing_whitelist_fields(self):
        """Test with incomplete whitelist configuration."""
        self.setUp()
        
        order = {
            "proposed": 500000.0,
            "instrument": "Liquid_Fund_Overnight",
            "issuer": "ABC AMC",
            "needs_maker_checker": False
        }
        
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.15,
            "recognition_ratio_expected_inflows": 0.40,
            "whitelist": [
                {"instrument": "Liquid_Fund_Overnight", "issuer": "ABC AMC"}  # Missing max_tenor_days
            ]
        }
        
        result = submit_order_stub(
            order=order,
            out_dir=self.temp_dir,
            balance=3000000.0,
            expected_inflows=800000.0,
            expected_outflows=600000.0,
            must_keep_amt=2000000.0,
            policy=policy,
            ap_rows=[]
        )
        
        summary_file = self.temp_path / "perform.json"
        with open(summary_file, 'r') as f:
            data = json.load(f)
        
        # Should handle missing max_tenor_days gracefully
        assert data["deploy_instrument"] == "Liquid_Fund_Overnight"
        assert data["max_tenor"] is None  # Should be None when missing
        
        self.tearDown()
    
    def test_large_ap_vendor_list(self):
        """Test with many AP vendors to ensure buffer calculation works."""
        self.setUp()
        
        # Create many AP rows with different vendors
        ap_rows = []
        for i in range(20):
            ap_rows.append({
                "vendor_id": f"VENDOR_{i:03d}",
                "vendor_tier": "critical" if i % 3 == 0 else "regular"
            })
        
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.15,
            "recognition_ratio_expected_inflows": 0.40,
            "whitelist": []
        }
        
        result = submit_order_stub(
            order=None,
            out_dir=self.temp_dir,
            balance=10000000.0,  # High balance
            expected_inflows=1000000.0,
            expected_outflows=800000.0,
            must_keep_amt=5000000.0,  # High must keep due to many vendors
            policy=policy,
            ap_rows=ap_rows
        )
        
        summary_file = self.temp_path / "perform.json"
        with open(summary_file, 'r') as f:
            data = json.load(f)
        
        # Should have calculated high safety buffers due to many vendors
        assert data["safety_buffers"] > 3000000.0  # Should be quite high
        assert data["current_balance"] == 10000000.0
        
        self.tearDown()
    
    def test_rounding_precision(self):
        """Test that monetary values are properly rounded to 2 decimal places."""
        self.setUp()
        
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.15,
            "recognition_ratio_expected_inflows": 0.40,
            "whitelist": []
        }
        
        result = submit_order_stub(
            order=None,
            out_dir=self.temp_dir,
            balance=1599081.3658,  # Many decimal places
            expected_inflows=862625.1123,
            expected_outflows=1203878.1287,
            must_keep_amt=5284459.8456,
            policy=policy,
            ap_rows=[]
        )
        
        summary_file = self.temp_path / "perform.json"
        with open(summary_file, 'r') as f:
            data = json.load(f)
        
        # Check that all monetary values are properly rounded
        assert data["current_balance"] == round(1599081.3658, 2)
        assert data["must_keep_value"] == round(5284459.8456, 2)
        assert data["deployable_value"] == round(data["deployable_value"], 2)
        assert data["safety_buffers"] == round(data["safety_buffers"], 2)
        
        # Check decimal places (should be at most 2)
        for field in ["current_balance", "must_keep_value", "deployable_value", "safety_buffers"]:
            value_str = str(data[field])
            if '.' in value_str:
                decimal_places = len(value_str.split('.')[1])
                assert decimal_places <= 2, f"Field {field} has {decimal_places} decimal places"
        
        self.tearDown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])