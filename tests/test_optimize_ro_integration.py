"""
Integration tests for optimize_ro_configuration tool.

These tests verify the full end-to-end functionality of the MCP tool,
including input parsing, optimization, and response formatting.
"""

import pytest
import json
import sys
import os

# Add parent directory to path to import server
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.optimize_ro import optimize_vessel_array_configuration
from utils.validation import validate_optimize_ro_inputs
from utils.response_formatter import format_optimization_response, format_error_response


def optimize_ro_configuration_test(
    feed_flow_m3h: float,
    water_recovery_fraction: float,
    membrane_type: str = "brackish",
    allow_recycle: bool = True,
    max_recycle_ratio: float = 0.9,
    flux_targets_lmh: str = None,
    flux_tolerance: float = None
):
    """
    Test wrapper that mimics the MCP tool behavior for testing.
    """
    # Store request parameters
    request_params = {
        "feed_flow_m3h": feed_flow_m3h,
        "water_recovery_fraction": water_recovery_fraction,
        "membrane_type": membrane_type,
        "allow_recycle": allow_recycle,
        "max_recycle_ratio": max_recycle_ratio,
        "flux_targets_lmh": flux_targets_lmh,
        "flux_tolerance": flux_tolerance
    }
    
    try:
        # Validate inputs
        parsed_flux_targets, validated_flux_tolerance = validate_optimize_ro_inputs(
            feed_flow_m3h=feed_flow_m3h,
            water_recovery_fraction=water_recovery_fraction,
            membrane_type=membrane_type,
            allow_recycle=allow_recycle,
            max_recycle_ratio=max_recycle_ratio,
            flux_targets_lmh=flux_targets_lmh,
            flux_tolerance=flux_tolerance
        )
        
        # Use placeholder salinity
        placeholder_salinity = 5000 if membrane_type == "brackish" else 35000
        
        # Call optimization
        configurations = optimize_vessel_array_configuration(
            feed_flow_m3h=feed_flow_m3h,
            target_recovery=water_recovery_fraction,
            feed_salinity_ppm=placeholder_salinity,
            membrane_type=membrane_type,
            allow_recycle=allow_recycle,
            max_recycle_ratio=max_recycle_ratio,
            flux_targets_lmh=parsed_flux_targets,
            flux_tolerance=validated_flux_tolerance
        )
        
        # Format response
        response = format_optimization_response(
            configurations=configurations,
            feed_flow_m3h=feed_flow_m3h,
            target_recovery=water_recovery_fraction,
            membrane_type=membrane_type
        )
        
        # Add warnings if needed
        configs_meeting_target = [
            c for c in response["configurations"] 
            if c["recovery_achievement"]["met_target"]
        ]
        
        if not configs_meeting_target and response["configurations"]:
            best_recovery = max(
                c["achieved_recovery"] for c in response["configurations"]
            )
            response["warning"] = (
                f"No configuration achieved the target recovery of {water_recovery_fraction:.1%}. "
                f"Best achieved: {best_recovery:.1%}"
            )
            response["recommendation"] = (
                "Consider adjusting flux targets, allowing recycle, "
                "or accepting lower recovery."
            )
        
        return response
        
    except Exception as e:
        return format_error_response(e, request_params)


class TestOptimizeROIntegration:
    """Integration tests for the optimize_ro_configuration MCP tool."""
    
    @pytest.mark.integration
    
    def test_basic_configuration(self):
        """Test basic RO configuration with default parameters."""
        result = optimize_ro_configuration_test(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.75,
            membrane_type="brackish"
        )
        
        assert result["status"] == "success"
        assert "configurations" in result
        assert len(result["configurations"]) >= 1
        
        # Check summary
        assert result["summary"]["feed_flow_m3h"] == 100.0
        assert result["summary"]["target_recovery_percent"] == 75.0
        assert result["summary"]["membrane_type"] == "brackish"
        
        # Check configurations have required fields
        for config in result["configurations"]:
            assert "stage_count" in config
            assert "array_notation" in config
            assert "total_vessels" in config
            assert "achieved_recovery" in config
            assert "stages" in config
            assert "recycle_info" in config
            assert "recovery_achievement" in config
    
    @pytest.mark.integration
    
    def test_with_custom_flux_targets(self):
        """Test configuration with custom flux targets."""
        # Test with single flux target
        result = optimize_ro_configuration_test(
            feed_flow_m3h=150.0,
            water_recovery_fraction=0.70,
            membrane_type="brackish",
            flux_targets_lmh="20.0",
            flux_tolerance=0.15
        )
        
        assert result["status"] == "success"
        configs = result["configurations"]
        
        # Check flux is within tolerance
        for config in configs:
            for stage in config["stages"]:
                assert 17.0 <= stage["design_flux_lmh"] <= 23.0  # 20 ± 15%
        
        # Test with per-stage flux targets
        result = optimize_ro_configuration_test(
            feed_flow_m3h=150.0,
            water_recovery_fraction=0.70,
            membrane_type="brackish",
            flux_targets_lmh="[22, 18, 15]",
            flux_tolerance=0.10
        )
        
        assert result["status"] == "success"
    
    @pytest.mark.integration
    
    def test_high_recovery_with_recycle(self):
        """Test high recovery configuration requiring recycle."""
        result = optimize_ro_configuration_test(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.85,
            membrane_type="brackish",
            allow_recycle=True,
            max_recycle_ratio=0.9
        )
        
        assert result["status"] == "success"
        
        # Should have at least one configuration with recycle
        recycle_configs = [
            c for c in result["configurations"] 
            if c["recycle_info"]["uses_recycle"]
        ]
        assert len(recycle_configs) > 0
        
        # Check recycle parameters
        for config in recycle_configs:
            recycle_info = config["recycle_info"]
            assert 0 < recycle_info["recycle_ratio"] <= 0.9
            assert recycle_info["recycle_flow_m3h"] > 0
            assert recycle_info["effective_feed_flow_m3h"] > 100.0
    
    @pytest.mark.integration
    
    def test_seawater_configuration(self):
        """Test configuration for seawater desalination."""
        result = optimize_ro_configuration_test(
            feed_flow_m3h=200.0,
            water_recovery_fraction=0.45,
            membrane_type="seawater"
        )
        
        assert result["status"] == "success"
        assert result["summary"]["membrane_type"] == "seawater"
        
        # Seawater typically has lower recovery
        for config in result["configurations"]:
            assert config["achieved_recovery"] <= 0.50
    
    @pytest.mark.integration
    
    def test_no_recycle_constraint(self):
        """Test configuration with recycle disabled."""
        result = optimize_ro_configuration_test(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.75,
            membrane_type="brackish",
            allow_recycle=False
        )
        
        assert result["status"] == "success"
        
        # No configuration should use recycle
        for config in result["configurations"]:
            assert not config["recycle_info"]["uses_recycle"]
    
    @pytest.mark.integration
    
    def test_configuration_diversity(self):
        """Test that multiple stage configurations are returned."""
        result = optimize_ro_configuration_test(
            feed_flow_m3h=150.0,
            water_recovery_fraction=0.70,
            membrane_type="brackish"
        )
        
        assert result["status"] == "success"
        
        # Extract stage counts
        stage_counts = set(c["stage_count"] for c in result["configurations"])
        
        # Should have multiple stage options
        assert len(stage_counts) >= 2
        assert 1 in stage_counts or 2 in stage_counts or 3 in stage_counts
    
    @pytest.mark.integration
    
    def test_flux_target_validation(self):
        """Test flux target input validation."""
        # Test invalid flux format
        result = optimize_ro_configuration_test(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.75,
            flux_targets_lmh="invalid"
        )
        
        assert result["status"] == "error"
        assert "Invalid flux_targets_lmh format" in result["error"]["message"]
        
        # Test negative flux
        result = optimize_ro_configuration_test(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.75,
            flux_targets_lmh="-20"
        )
        
        assert result["status"] == "error"
        assert "positive" in result["error"]["message"].lower()
    
    @pytest.mark.integration
    
    def test_recovery_validation(self):
        """Test recovery target validation."""
        # Test invalid recovery
        result = optimize_ro_configuration_test(
            feed_flow_m3h=100.0,
            water_recovery_fraction=1.5
        )
        
        assert result["status"] == "error"
        assert "Recovery" in result["error"]["message"]
        
        # Test recovery too low
        result = optimize_ro_configuration_test(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.05
        )
        
        assert result["status"] == "error"
        assert "Recovery" in result["error"]["message"]
    
    @pytest.mark.integration
    
    def test_flow_rate_validation(self):
        """Test flow rate validation."""
        # Test negative flow
        result = optimize_ro_configuration_test(
            feed_flow_m3h=-100.0,
            water_recovery_fraction=0.75
        )
        
        assert result["status"] == "error"
        assert "feed_flow_m3h" in result["error"]["message"]
        
        # Test zero flow
        result = optimize_ro_configuration_test(
            feed_flow_m3h=0.0,
            water_recovery_fraction=0.75
        )
        
        assert result["status"] == "error"
        assert "feed_flow_m3h" in result["error"]["message"]
    
    @pytest.mark.integration
    
    def test_recovery_achievement_reporting(self):
        """Test recovery achievement status reporting."""
        result = optimize_ro_configuration_test(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.60,  # Easy target
            membrane_type="brackish"
        )
        
        assert result["status"] == "success"
        
        # Should have configurations that meet the target
        met_target = [
            c for c in result["configurations"]
            if c["recovery_achievement"]["met_target"]
        ]
        assert len(met_target) > 0
        
        # Check recovery achievement details
        for config in met_target:
            achievement = config["recovery_achievement"]
            assert achievement["target_recovery_percent"] == 60.0
            assert abs(achievement["achieved_recovery_percent"] - 60.0) <= 2.0
            assert achievement["recovery_error_percent"] <= 2.0
    
    @pytest.mark.integration
    
    def test_flux_summary_reporting(self):
        """Test flux summary in response."""
        result = optimize_ro_configuration_test(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.75,
            flux_targets_lmh="[20, 17, 14]"
        )
        
        assert result["status"] == "success"
        
        for config in result["configurations"]:
            flux_summary = config["flux_summary"]
            assert "min_flux_ratio" in flux_summary
            assert "max_flux_ratio" in flux_summary
            assert "average_flux_lmh" in flux_summary
            
            # Check bounds
            assert 0.7 <= flux_summary["min_flux_ratio"] <= 1.1
            assert 0.7 <= flux_summary["max_flux_ratio"] <= 1.1
            assert flux_summary["min_flux_ratio"] <= flux_summary["max_flux_ratio"]
    
    @pytest.mark.integration
    
    def test_concentrate_flow_margins(self):
        """Test concentrate flow margin reporting."""
        result = optimize_ro_configuration_test(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.75
        )
        
        assert result["status"] == "success"
        
        for config in result["configurations"]:
            for stage in config["stages"]:
                # Check concentrate margin fields
                assert "concentrate_per_vessel_m3h" in stage
                assert "min_concentrate_required_m3h" in stage
                assert "concentrate_margin_m3h" in stage
                assert "concentrate_margin_percent" in stage
                
                # Verify calculations
                if stage["min_concentrate_required_m3h"]:
                    assert stage["concentrate_per_vessel_m3h"] >= stage["min_concentrate_required_m3h"]
                    assert stage["concentrate_margin_m3h"] >= 0
    
    @pytest.mark.integration
    
    def test_error_response_format(self):
        """Test error response formatting."""
        result = optimize_ro_configuration_test(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.75,
            membrane_type="invalid_type"
        )
        
        assert result["status"] == "error"
        assert "error" in result
        assert "type" in result["error"]
        assert "message" in result["error"]
        assert "request_parameters" in result["error"]
        assert result["configurations"] == []
        
        # Check request parameters are captured
        params = result["error"]["request_parameters"]
        assert params["feed_flow_m3h"] == 100.0
        assert params["water_recovery_fraction"] == 0.75
        assert params["membrane_type"] == "invalid_type"
    
    @pytest.mark.integration
    
    def test_configuration_type_summary(self):
        """Test configuration type summary in response."""
        result = optimize_ro_configuration_test(
            feed_flow_m3h=150.0,
            water_recovery_fraction=0.80,
            allow_recycle=True
        )
        
        assert result["status"] == "success"
        
        if result["configurations"]:
            config_types = result["summary"]["configuration_types"]
            assert "stage_counts" in config_types
            assert "includes_recycle_options" in config_types
            assert "includes_non_recycle_options" in config_types
            
            # Stage counts should be sorted
            assert config_types["stage_counts"] == sorted(config_types["stage_counts"])
    
    @pytest.mark.integration
    @pytest.mark.slow
    
    def test_large_flow_rate(self):
        """Test configuration for large industrial flow rates."""
        result = optimize_ro_configuration_test(
            feed_flow_m3h=1000.0,
            water_recovery_fraction=0.70,
            membrane_type="brackish"
        )
        
        assert result["status"] == "success"
        
        # Should handle large flows
        for config in result["configurations"]:
            assert config["total_vessels"] > 10
            assert config["total_membrane_area_m2"] > 10000
    
    @pytest.mark.integration
    
    def test_warning_for_unachievable_recovery(self):
        """Test warning message for unachievable recovery targets."""
        result = optimize_ro_configuration_test(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.95,  # Very high
            membrane_type="brackish",
            allow_recycle=False  # Make it harder
        )
        
        # Should either succeed with warning or fail gracefully
        if result["status"] == "success" and result["configurations"]:
            # Check if warning is present
            if "warning" in result:
                assert "No configuration achieved" in result["warning"]
                assert "recommendation" in result
        else:
            # Or it should fail with appropriate error
            assert result["status"] == "error"
            assert "No feasible configuration" in str(result["error"]["message"])