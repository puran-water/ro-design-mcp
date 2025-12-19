#!/usr/bin/env python3
"""
Test that salt_passage parameter is required in all TDS calculations.

This ensures the fix for unrealistic TDS values is properly enforced.
"""

import pytest
import sys
sys.path.insert(0, '.')

from utils.ro_initialization import (
    calculate_concentrate_tds,
    calculate_required_pressure
)


class TestSaltPassageRequired:
    """Test that salt_passage is mandatory."""
    
    def test_calculate_concentrate_tds_requires_salt_passage(self):
        """Test that calculate_concentrate_tds requires salt_passage parameter."""
        # This should raise TypeError due to missing required parameter
        with pytest.raises(TypeError) as excinfo:
            calculate_concentrate_tds(2000, 0.75)
        
        assert "missing 1 required positional argument: 'salt_passage'" in str(excinfo.value)
    
    def test_calculate_concentrate_tds_with_salt_passage(self):
        """Test that calculate_concentrate_tds works correctly with salt_passage."""
        # Test with typical brackish water values
        feed_tds = 2000  # ppm
        recovery = 0.75
        salt_passage = 0.015  # 1.5%
        
        result = calculate_concentrate_tds(feed_tds, recovery, salt_passage)
        
        # Expected: 2000 * (1 - 0.015*0.75) / (1 - 0.75) = 7910 ppm
        expected = feed_tds * (1 - salt_passage * recovery) / (1 - recovery)
        assert abs(result - expected) < 0.1
        assert 7000 < result < 8000  # Realistic range
    
    def test_calculate_required_pressure_requires_salt_passage(self):
        """Test that calculate_required_pressure requires salt_passage parameter."""
        # Should raise ValueError when salt_passage is None (default)
        with pytest.raises(ValueError) as excinfo:
            calculate_required_pressure(2000, 0.75)
        
        assert "salt_passage parameter is required" in str(excinfo.value)
    
    def test_calculate_required_pressure_with_salt_passage(self):
        """Test that calculate_required_pressure works correctly with salt_passage."""
        # Test with typical values
        feed_tds = 2000  # ppm
        recovery = 0.75
        salt_passage = 0.015  # 1.5%
        
        pressure = calculate_required_pressure(
            feed_tds,
            recovery,
            salt_passage=salt_passage
        )
        
        # Pressure should be reasonable (10-30 bar for brackish water)
        assert 10e5 < pressure < 30e5
    
    def test_old_formula_vs_new_formula(self):
        """Compare old formula (perfect rejection) vs new formula with salt passage."""
        feed_tds = 2000
        recovery = 0.75
        salt_passage = 0.015
        
        # Old formula (perfect rejection)
        old_result = feed_tds / (1 - recovery)  # 8000 ppm
        
        # New formula (with salt passage)
        new_result = calculate_concentrate_tds(feed_tds, recovery, salt_passage)
        
        # New result should be lower due to salt passage
        assert new_result < old_result
        assert abs(old_result - 8000) < 0.1
        assert abs(new_result - 7910) < 1  # ~7910 ppm
    
    def test_multistage_tds_calculation(self):
        """Test TDS calculation through multiple stages."""
        feed_tds = 2000
        stage1_recovery = 0.5518
        stage2_recovery = 0.4128
        salt_passage = 0.015
        
        # Stage 1
        stage1_conc = calculate_concentrate_tds(feed_tds, stage1_recovery, salt_passage)
        assert 4000 < stage1_conc < 5000  # Reasonable range
        
        # Stage 2 (using stage 1 concentrate as feed)
        stage2_conc = calculate_concentrate_tds(stage1_conc, stage2_recovery, salt_passage)
        assert 7000 < stage2_conc < 9000  # Reasonable range
        
        # Should not be the unrealistic 666,667 ppm from old formula
        assert stage2_conc < 10000
    
    def test_salt_passage_validation_range(self):
        """Test that salt_passage values are in reasonable range."""
        feed_tds = 2000
        recovery = 0.5
        
        # Test with various salt passage values
        test_cases = [
            (0.001, "High rejection"),   # 0.1%
            (0.015, "Brackish water"),   # 1.5%
            (0.05, "Seawater/brine"),    # 5%
        ]
        
        for salt_passage, description in test_cases:
            result = calculate_concentrate_tds(feed_tds, recovery, salt_passage)
            # All should produce reasonable values
            assert result < 50000, f"{description} produced unrealistic TDS: {result}"
            assert result > feed_tds, f"{description} concentrate should be higher than feed"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])