#!/usr/bin/env python3
"""
Test the MCP server API endpoints.

This ensures the server functions work correctly after refactoring.
"""

import pytest
import json
import sys
sys.path.insert(0, '.')

# Import the server functions
from server import optimize_ro_configuration, simulate_ro_system


class TestAPIEndpoints:
    """Test MCP server API functions."""
    
    @pytest.mark.asyncio
    async def test_optimize_ro_configuration_basic(self):
        """Test basic RO configuration optimization."""
        result = await optimize_ro_configuration(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.75,
            membrane_type="brackish",
            allow_recycle=True
        )
        
        assert result["status"] == "success"
        assert "configurations" in result
        assert len(result["configurations"]) > 0
        
        # Check that we get multiple stage options
        stage_counts = {c["n_stages"] for c in result["configurations"]}
        assert len(stage_counts) >= 2  # Should have at least 2 different stage counts
    
    @pytest.mark.asyncio
    async def test_optimize_ro_configuration_with_flux_targets(self):
        """Test RO configuration with custom flux targets."""
        result = await optimize_ro_configuration(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.75,
            membrane_type="brackish",
            flux_targets_lmh="[20, 17, 14]",
            flux_tolerance=0.15
        )
        
        assert result["status"] == "success"
        assert "configurations" in result
        
        # Check flux values are within tolerance
        for config in result["configurations"]:
            for stage in config["stages"]:
                flux = stage["design_flux_lmh"]
                target = stage["flux_target_lmh"]
                ratio = flux / target
                assert 0.85 <= ratio <= 1.15  # Within 15% tolerance
    
    @pytest.mark.asyncio
    async def test_optimize_ro_configuration_high_recovery(self):
        """Test RO configuration for high recovery requiring recycle."""
        result = await optimize_ro_configuration(
            feed_flow_m3h=50.0,
            water_recovery_fraction=0.85,
            membrane_type="brackish",
            allow_recycle=True,
            max_recycle_ratio=0.5
        )
        
        assert result["status"] == "success"
        assert "configurations" in result
        
        # Should have at least one configuration with recycle
        recycle_configs = [c for c in result["configurations"] if c.get("recycle_info", {}).get("uses_recycle")]
        assert len(recycle_configs) > 0
    
    @pytest.mark.asyncio
    async def test_optimize_ro_configuration_error_handling(self):
        """Test error handling in optimization."""
        # Invalid recovery
        result = await optimize_ro_configuration(
            feed_flow_m3h=100.0,
            water_recovery_fraction=1.5,  # Invalid >100%
            membrane_type="brackish"
        )
        
        assert result["status"] == "error"
        assert "error" in result
    
    @pytest.mark.asyncio
    async def test_simulate_ro_system_basic(self):
        """Test basic RO system simulation."""
        # First get a configuration
        config_result = await optimize_ro_configuration(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.75,
            membrane_type="brackish"
        )
        
        assert config_result["status"] == "success"
        configuration = config_result["configurations"][0]
        
        # Now simulate it
        ion_composition = json.dumps({
            "Na+": 1200.0,
            "Ca2+": 120.0,
            "Mg2+": 60.0,
            "Cl-": 2100.0,
            "SO4-2": 200.0,
            "HCO3-": 150.0
        })
        
        sim_result = await simulate_ro_system(
            configuration=configuration,
            feed_salinity_ppm=5000,
            feed_ion_composition=ion_composition,
            feed_temperature_c=25.0,
            membrane_type="brackish",
            optimize_pumps=False
        )
        
        # Note: This might fail if WaterTAP is not installed
        if sim_result.get("status") == "error" and "WaterTAP dependencies" in sim_result.get("message", ""):
            pytest.skip("WaterTAP not installed")
        
        assert sim_result["status"] == "success"
        assert "performance" in sim_result
        assert "economics" in sim_result
        assert "stage_results" in sim_result
    
    @pytest.mark.asyncio
    async def test_simulate_ro_system_validation(self):
        """Test input validation in simulation."""
        # Invalid configuration
        result = await simulate_ro_system(
            configuration="not a dict",
            feed_salinity_ppm=5000,
            feed_ion_composition='{"Na+": 1200}',
            feed_temperature_c=25.0
        )
        
        assert result["status"] == "error"
        assert "configuration must be a dictionary" in result["error"]
        
        # Invalid ion composition JSON
        result = await simulate_ro_system(
            configuration={"stages": []},
            feed_salinity_ppm=5000,
            feed_ion_composition='invalid json',
            feed_temperature_c=25.0
        )
        
        assert result["status"] == "error"
        assert "Invalid JSON format" in result["error"]


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])