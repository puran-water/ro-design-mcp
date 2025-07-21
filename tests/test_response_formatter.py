"""
Tests for response formatting utilities.
"""

import pytest
from utils.response_formatter import (
    format_stage_info,
    format_recycle_info,
    format_recovery_achievement,
    format_configuration_response,
    format_optimization_response,
    format_error_response
)


class TestFormatStageInfo:
    """Tests for stage info formatting."""
    
    @pytest.mark.unit
    def test_format_basic_stage_info(self):
        """Test formatting basic stage information."""
        stage = {
            "stage_number": 1,
            "n_vessels": 10,
            "feed_flow_m3h": 100.0,
            "permeate_flow_m3h": 40.0,
            "concentrate_flow_m3h": 60.0,
            "stage_recovery": 0.4,
            "design_flux_lmh": 18.0,
            "flux_ratio": 1.0,
            "membrane_area_m2": 2602.0
        }
        
        formatted = format_stage_info(stage)
        
        assert formatted["stage_number"] == 1
        assert formatted["vessel_count"] == 10
        assert formatted["feed_flow_m3h"] == 100.0
        assert formatted["permeate_flow_m3h"] == 40.0
        assert formatted["concentrate_flow_m3h"] == 60.0
        assert formatted["stage_recovery"] == 0.4
        assert formatted["design_flux_lmh"] == 18.0
        assert formatted["flux_ratio"] == 1.0
        assert formatted["membrane_area_m2"] == 2602.0
        assert formatted["concentrate_per_vessel_m3h"] == 6.0  # 60/10
    
    @pytest.mark.unit
    def test_format_stage_with_concentrate_margins(self):
        """Test formatting stage with concentrate margin info."""
        stage = {
            "stage_number": 2,
            "n_vessels": 5,
            "feed_flow_m3h": 60.0,
            "permeate_flow_m3h": 25.0,
            "concentrate_flow_m3h": 35.0,
            "stage_recovery": 0.417,
            "design_flux_lmh": 15.0,
            "flux_ratio": 0.9,
            "membrane_area_m2": 1301.0,
            "concentrate_per_vessel_m3h": 7.0,
            "min_concentrate_required": 3.8
        }
        
        formatted = format_stage_info(stage)
        
        assert formatted["concentrate_per_vessel_m3h"] == 7.0
        assert formatted["min_concentrate_required_m3h"] == 3.8
        assert formatted["concentrate_margin_m3h"] == pytest.approx(3.2, rel=0.01)
        assert formatted["concentrate_margin_percent"] == pytest.approx(84.2, rel=0.1)


class TestFormatRecycleInfo:
    """Tests for recycle info formatting."""
    
    @pytest.mark.unit
    def test_format_no_recycle(self):
        """Test formatting when no recycle is used."""
        config = {"recycle_ratio": 0}
        formatted = format_recycle_info(config)
        
        assert formatted == {"uses_recycle": False}
    
    @pytest.mark.unit
    def test_format_with_recycle(self):
        """Test formatting with recycle."""
        config = {
            "recycle_ratio": 0.5,
            "recycle_flow_m3h": 25.0,
            "recycle_split_ratio": 0.8,
            "effective_feed_flow_m3h": 125.0,
            "disposal_flow_m3h": 5.0
        }
        
        formatted = format_recycle_info(config)
        
        assert formatted["uses_recycle"] is True
        assert formatted["recycle_ratio"] == 0.5
        assert formatted["recycle_flow_m3h"] == 25.0
        assert formatted["recycle_split_ratio"] == 0.8
        assert formatted["effective_feed_flow_m3h"] == 125.0
        assert formatted["disposal_flow_m3h"] == 5.0


class TestFormatRecoveryAchievement:
    """Tests for recovery achievement formatting."""
    
    @pytest.mark.unit
    def test_recovery_met(self):
        """Test formatting when recovery target is met."""
        config = {
            "recovery_error": 0.01,
            "target_recovery": 0.75,
            "total_recovery": 0.7575
        }
        
        formatted = format_recovery_achievement(config)
        
        assert formatted["met_target"] is True
        assert formatted["target_recovery_percent"] == 75.0
        assert formatted["achieved_recovery_percent"] == 75.75
        assert formatted["recovery_error_percent"] == 1.0
    
    @pytest.mark.unit
    def test_recovery_not_met(self):
        """Test formatting when recovery target is not met."""
        config = {
            "recovery_error": 0.05,
            "target_recovery": 0.80,
            "total_recovery": 0.76
        }
        
        formatted = format_recovery_achievement(config)
        
        assert formatted["met_target"] is False
        assert formatted["target_recovery_percent"] == 80.0
        assert formatted["achieved_recovery_percent"] == 76.0
        assert formatted["recovery_error_percent"] == 5.0


class TestFormatConfigurationResponse:
    """Tests for configuration response formatting."""
    
    @pytest.mark.unit
    def test_format_simple_configuration(self):
        """Test formatting a simple configuration."""
        config = {
            "n_stages": 2,
            "array_notation": "10:5",
            "total_vessels": 15,
            "total_membrane_area_m2": 3903.0,
            "total_recovery": 0.75,
            "recovery_error": 0.0,
            "recycle_ratio": 0,
            "min_flux_ratio": 0.9,
            "max_flux_ratio": 1.0,
            "stages": [
                {
                    "stage_number": 1,
                    "n_vessels": 10,
                    "feed_flow_m3h": 100.0,
                    "permeate_flow_m3h": 45.0,
                    "concentrate_flow_m3h": 55.0,
                    "stage_recovery": 0.45,
                    "design_flux_lmh": 18.0,
                    "flux_ratio": 1.0,
                    "membrane_area_m2": 2602.0
                },
                {
                    "stage_number": 2,
                    "n_vessels": 5,
                    "feed_flow_m3h": 55.0,
                    "permeate_flow_m3h": 30.0,
                    "concentrate_flow_m3h": 25.0,
                    "stage_recovery": 0.545,
                    "design_flux_lmh": 15.0,
                    "flux_ratio": 0.9,
                    "membrane_area_m2": 1301.0
                }
            ]
        }
        
        formatted = format_configuration_response(config)
        
        assert formatted["stage_count"] == 2
        assert formatted["array_notation"] == "10:5"
        assert formatted["total_vessels"] == 15
        assert formatted["total_membrane_area_m2"] == 3903.0
        assert formatted["achieved_recovery"] == 0.75
        assert formatted["recovery_error"] == 0.0
        assert len(formatted["stages"]) == 2
        assert formatted["recycle_info"]["uses_recycle"] is False
        assert formatted["recovery_achievement"]["met_target"] is True
        assert formatted["flux_summary"]["min_flux_ratio"] == 0.9
        assert formatted["flux_summary"]["max_flux_ratio"] == 1.0
        assert formatted["flux_summary"]["average_flux_lmh"] == pytest.approx(16.5, rel=0.01)


class TestFormatOptimizationResponse:
    """Tests for complete optimization response formatting."""
    
    @pytest.mark.unit
    def test_format_multiple_configurations(self):
        """Test formatting response with multiple configurations."""
        configurations = [
            {
                "n_stages": 1,
                "array_notation": "20",
                "total_vessels": 20,
                "total_membrane_area_m2": 5204.0,
                "total_recovery": 0.65,
                "recovery_error": 0.10,
                "recycle_ratio": 0,
                "stages": [
                    {
                        "stage_number": 1,
                        "n_vessels": 20,
                        "feed_flow_m3h": 100.0,
                        "permeate_flow_m3h": 65.0,
                        "concentrate_flow_m3h": 35.0,
                        "stage_recovery": 0.65,
                        "design_flux_lmh": 18.0,
                        "flux_ratio": 1.0,
                        "membrane_area_m2": 5204.0
                    }
                ]
            },
            {
                "n_stages": 2,
                "array_notation": "10:5",
                "total_vessels": 15,
                "total_membrane_area_m2": 3903.0,
                "total_recovery": 0.74,
                "recovery_error": 0.01,
                "recycle_ratio": 0.2,
                "recycle_flow_m3h": 20.0,
                "recycle_split_ratio": 0.8,
                "effective_feed_flow_m3h": 120.0,
                "disposal_flow_m3h": 4.0,
                "stages": [
                    {
                        "stage_number": 1,
                        "n_vessels": 10,
                        "feed_flow_m3h": 120.0,
                        "permeate_flow_m3h": 50.0,
                        "concentrate_flow_m3h": 70.0,
                        "stage_recovery": 0.417,
                        "design_flux_lmh": 18.0,
                        "flux_ratio": 1.0,
                        "membrane_area_m2": 2602.0
                    },
                    {
                        "stage_number": 2,
                        "n_vessels": 5,
                        "feed_flow_m3h": 70.0,
                        "permeate_flow_m3h": 30.0,
                        "concentrate_flow_m3h": 40.0,
                        "stage_recovery": 0.429,
                        "design_flux_lmh": 15.0,
                        "flux_ratio": 0.9,
                        "membrane_area_m2": 1301.0
                    }
                ]
            }
        ]
        
        response = format_optimization_response(
            configurations=configurations,
            feed_flow_m3h=100.0,
            target_recovery=0.75,
            membrane_type="brackish"
        )
        
        assert response["status"] == "success"
        assert len(response["configurations"]) == 2
        assert response["summary"]["feed_flow_m3h"] == 100.0
        assert response["summary"]["target_recovery_percent"] == 75.0
        assert response["summary"]["membrane_type"] == "brackish"
        assert response["summary"]["configurations_found"] == 2
        
        # Check configuration diversity
        assert response["summary"]["configuration_types"]["stage_counts"] == [1, 2]
        assert response["summary"]["configuration_types"]["includes_recycle_options"] is True
        assert response["summary"]["configuration_types"]["includes_non_recycle_options"] is True
    
    @pytest.mark.unit
    def test_format_empty_configurations(self):
        """Test formatting with no configurations."""
        response = format_optimization_response(
            configurations=[],
            feed_flow_m3h=100.0,
            target_recovery=0.90,
            membrane_type="seawater"
        )
        
        assert response["status"] == "success"
        assert len(response["configurations"]) == 0
        assert response["summary"]["configurations_found"] == 0
        assert "configuration_types" not in response["summary"]


class TestFormatErrorResponse:
    """Tests for error response formatting."""
    
    @pytest.mark.unit
    def test_format_value_error(self):
        """Test formatting ValueError response."""
        error = ValueError("Invalid feed flow: -10")
        request_params = {
            "feed_flow_m3h": -10,
            "water_recovery_fraction": 0.75,
            "membrane_type": "brackish"
        }
        
        response = format_error_response(error, request_params)
        
        assert response["status"] == "error"
        assert response["error"]["type"] == "ValueError"
        assert response["error"]["message"] == "Invalid feed flow: -10"
        assert response["error"]["request_parameters"] == request_params
        assert response["configurations"] == []
    
    @pytest.mark.unit
    def test_format_generic_exception(self):
        """Test formatting generic exception."""
        error = Exception("Something went wrong")
        request_params = {"some": "params"}
        
        response = format_error_response(error, request_params)
        
        assert response["status"] == "error"
        assert response["error"]["type"] == "Exception"
        assert response["error"]["message"] == "Something went wrong"
        assert response["error"]["request_parameters"] == request_params