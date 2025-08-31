"""
Test cases for prescribe module.
"""

import pytest
from src.core.prescribe import must_keep, deployable, propose_order


class TestMustKeep:
    """Test cases for must_keep function."""
    
    def test_base_buffers_only(self):
        """Test must_keep with only base buffers (no AP rows)."""
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.15
        }
        
        result = must_keep(policy, 500000, [])
        expected = 1000000 + 400000 + 200000 + (1.15 * 500000)  # 2,175,000
        assert result == 2175000.0
    
    def test_with_vendor_tier_buffers(self):
        """Test must_keep with vendor tier buffers based on counts."""
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.15
        }
        
        ap_rows = [
            {"vendor_tier": "critical", "vendor_id": "V1"},
            {"vendor_tier": "critical", "vendor_id": "V2"},
            {"vendor_tier": "regular", "vendor_id": "V3"}
        ]
        
        result = must_keep(policy, 500000, ap_rows)
        # Base: 1,600,000 + Vendor: (2*300,000 + 1*100,000) + Shock: 575,000 = 2,875,000
        expected = 1600000 + 700000 + 575000
        assert result == 2875000.0
    
    def test_duplicate_vendor_tiers(self):
        """Test that duplicate vendor tiers are counted properly."""
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.0
        }
        
        ap_rows = [
            {"vendor_tier": "critical", "vendor_id": "V1"},
            {"vendor_tier": "critical", "vendor_id": "V1"},  # Same vendor, different bill
            {"vendor_tier": "regular", "vendor_id": "V2"}
        ]
        
        result = must_keep(policy, 0, ap_rows)
        # Base: 1,600,000 + Vendor: (2*300,000 + 1*100,000) = 2,300,000
        expected = 1600000 + 700000
        assert result == 2300000.0
    
    def test_missing_vendor_tier_defaults_to_regular(self):
        """Test that missing vendor_tier defaults to regular."""
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.0
        }
        
        ap_rows = [
            {"vendor_id": "V1"},  # No vendor_tier specified
        ]
        
        result = must_keep(policy, 0, ap_rows)
        # Base: 1,600,000 + Vendor: (1*100,000) = 1,700,000
        expected = 1600000 + 100000
        assert result == 1700000.0
    
    def test_rounding_to_two_decimals(self):
        """Test that result is rounded to 2 decimal places."""
        policy = {
            "min_operating_cash": 1000000,
            "payroll_buffer": 400000,
            "tax_buffer": 200000,
            "vendor_tier_buffers": {"critical": 300000, "regular": 100000},
            "outflow_shock_multiplier": 1.333  # Creates rounding scenario
        }
        
        result = must_keep(policy, 100000, [])
        # Base: 1,600,000 + Shock: 133,300 = 1,733,300.00
        expected = 1600000 + 133300
        assert result == 1733300.0


class TestDeployable:
    """Test cases for deployable function."""
    
    def test_positive_deployable(self):
        """Test deployable with positive surplus."""
        policy = {}  # Recognition ratio hardcoded to 0.98
        
        result = deployable(3000000, 1000000, 2000000, policy)
        # 3,000,000 + (0.98 * 1,000,000) - 2,000,000 = 1,980,000
        expected = 3000000 + 980000 - 2000000
        assert result == 1980000.0
    
    def test_zero_deployable(self):
        """Test deployable when exactly zero."""
        policy = {}
        
        result = deployable(2000000, 1000000, 2980000, policy)
        # 2,000,000 + (0.98 * 1,000,000) - 2,980,000 = 0
        expected = 2000000 + 980000 - 2980000
        assert result == 0.0
    
    def test_negative_clamped_to_zero(self):
        """Test that negative deployable is clamped to zero."""
        policy = {}
        
        result = deployable(1000000, 500000, 2000000, policy)
        # 1,000,000 + (0.98 * 500,000) - 2,000,000 = -510,000 -> 0
        assert result == 0.0
    
    def test_rounding_to_two_decimals(self):
        """Test that result is rounded to 2 decimal places."""
        policy = {}
        
        result = deployable(1000000, 1000000.333, 1000000, policy)
        # 1,000,000 + (0.98 * 1,000,000.333) - 1,000,000 = 980,000.326 -> 980,000.33
        expected = round(1000000 + (0.98 * 1000000.333) - 1000000, 2)
        assert result == expected


class TestProposeOrder:
    """Test cases for propose_order function."""
    
    def test_no_surplus(self):
        """Test when deployable amount is zero."""
        policy = {"whitelist": [{"instrument": "Test", "issuer": "Test", "max_amount": 1000000}]}
        
        order, reasons = propose_order(0, policy)
        
        assert order is None
        assert "NO_SURPLUS" in reasons
        assert "FIXED_BUFFERS" in reasons
        assert "OUTFLOW_SHOCK" in reasons
        assert "CONSERVATIVE_INFLOW" in reasons
    
    def test_cutoff_passed(self):
        """Test when cutoff time has passed."""
        from unittest.mock import patch, MagicMock
        from datetime import datetime
        
        policy = {
            "enforce_cutoff": True,
            "cutoff_hour_ist": 14,
            "whitelist": [{"instrument": "Test", "issuer": "Test", "max_amount": 1000000}]
        }
        
        # Mock current time to be after cutoff
        mock_now = MagicMock()
        mock_now.hour = 15
        
        with patch('src.core.prescribe.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_now
            
            order, reasons = propose_order(500000, policy)
        
        assert order is None
        assert "CUTOFF_PASSED" in reasons
    
    def test_successful_order_small_amount(self):
        """Test successful order below approval threshold."""
        policy = {
            "enforce_cutoff": False,
            "approval_threshold": 500000,
            "whitelist": [{"instrument": "Liquid_Fund", "issuer": "ABC AMC", "max_amount": 1000000}]
        }
        
        order, reasons = propose_order(300000, policy)
        
        assert order is not None
        assert order["proposed"] == 300000.0
        assert order["instrument"] == "Liquid_Fund"
        assert order["issuer"] == "ABC AMC"
        assert order["needs_maker_checker"] is False
        assert "WL_OK" in reasons
        assert "MAKER_CHECKER" not in reasons
    
    def test_successful_order_needs_maker_checker(self):
        """Test successful order above approval threshold."""
        policy = {
            "enforce_cutoff": False,
            "approval_threshold": 500000,
            "whitelist": [{"instrument": "Liquid_Fund", "issuer": "ABC AMC", "max_amount": 2000000}]
        }
        
        order, reasons = propose_order(1000000, policy)
        
        assert order is not None
        assert order["proposed"] == 1000000.0
        assert order["needs_maker_checker"] is True
        assert "WL_OK" in reasons
        assert "MAKER_CHECKER" in reasons
    
    def test_amount_limited_by_max_amount(self):
        """Test that order amount is limited by instrument max_amount."""
        policy = {
            "enforce_cutoff": False,
            "approval_threshold": 500000,
            "whitelist": [{"instrument": "Liquid_Fund", "issuer": "ABC AMC", "max_amount": 800000}]
        }
        
        order, reasons = propose_order(1200000, policy)
        
        assert order is not None
        assert order["proposed"] == 800000.0  # Limited by max_amount
        assert "WL_OK" in reasons
    
    def test_waterfall_allocation(self):
        """Test waterfall allocation selects first instrument."""
        policy = {
            "enforce_cutoff": False,
            "approval_threshold": 500000,
            "whitelist": [
                {"instrument": "First_Fund", "issuer": "ABC AMC", "max_amount": 500000},
                {"instrument": "Second_Fund", "issuer": "XYZ AMC", "max_amount": 1000000}
            ]
        }
        
        order, reasons = propose_order(300000, policy)
        
        assert order is not None
        assert order["instrument"] == "First_Fund"  # First in waterfall
        assert order["issuer"] == "ABC AMC"
    
    def test_empty_whitelist(self):
        """Test behavior with empty whitelist."""
        policy = {
            "enforce_cutoff": False,
            "whitelist": []
        }
        
        order, reasons = propose_order(500000, policy)
        
        assert order is None
        assert "WL_OK" not in reasons
    
    def test_missing_whitelist(self):
        """Test behavior with missing whitelist key."""
        policy = {
            "enforce_cutoff": False
        }
        
        order, reasons = propose_order(500000, policy)
        
        assert order is None
        assert "WL_OK" not in reasons
    
    def test_cutoff_disabled(self):
        """Test that cutoff is ignored when enforce_cutoff is False."""
        from unittest.mock import patch, MagicMock
        from datetime import datetime
        
        policy = {
            "enforce_cutoff": False,
            "cutoff_hour_ist": 14,
            "approval_threshold": 500000,
            "whitelist": [{"instrument": "Test", "issuer": "Test", "max_amount": 1000000}]
        }
        
        # Mock current time to be after cutoff
        mock_now = MagicMock()
        mock_now.hour = 15
        
        with patch('src.core.prescribe.datetime') as mock_datetime:
            mock_datetime.now.return_value = mock_now
            
            order, reasons = propose_order(300000, policy)
        
        assert order is not None
        assert "CUTOFF_PASSED" not in reasons
        assert "WL_OK" in reasons


if __name__ == "__main__":
    pytest.main([__file__, "-v"])