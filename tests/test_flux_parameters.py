"""
Tests for flux parameter handling and validation.
"""

import pytest
from utils.optimize_ro import optimize_vessel_array_configuration
from utils.helpers import validate_flux_parameters


class TestFluxParameterValidation:
    """Tests for flux parameter validation in helpers."""
    
    @pytest.mark.unit
    @pytest.mark.helpers
    def test_flux_validation_defaults(self):
        """Test flux validation with default values."""
        targets, tolerance = validate_flux_parameters(None, None)
        assert targets == [18, 15, 12]
        assert tolerance == 0.1
    
    @pytest.mark.unit
    @pytest.mark.helpers
    @pytest.mark.parametrize("flux_input,expected", [
        (20.0, [20.0, 20.0, 20.0]),
        (18.5, [18.5, 18.5, 18.5]),
        ([24, 20, 16], [24, 20, 16]),
        ([22], [22, 22, 22]),  # Extended to 3 stages
    ])
    def test_flux_validation_valid_inputs(self, flux_input, expected):
        """Test flux validation with various valid inputs."""
        targets, tolerance = validate_flux_parameters(flux_input, None)
        assert targets == expected
        assert tolerance == 0.1  # Default tolerance
    
    @pytest.mark.unit
    @pytest.mark.helpers
    @pytest.mark.parametrize("flux_input,tolerance_input,expected_tolerance", [
        (None, 0.15, 0.15),
        (20.0, 0.08, 0.08),
        ([24, 20, 16], 0.12, 0.12),
    ])
    def test_flux_validation_custom_tolerance(self, flux_input, tolerance_input, expected_tolerance):
        """Test flux validation with custom tolerance."""
        targets, tolerance = validate_flux_parameters(flux_input, tolerance_input)
        assert tolerance == expected_tolerance
    
    @pytest.mark.unit
    @pytest.mark.helpers
    @pytest.mark.parametrize("flux_input,tolerance_input,error_msg", [
        (-5.0, None, "Flux target must be positive"),
        (0.0, None, "Flux target must be positive"),
        ([], None, "Flux targets list cannot be empty"),
        ([20, -5, 15], None, "All flux targets must be positive"),
        (None, -0.1, "Flux tolerance must be between 0 and 1"),
        (None, 1.5, "Flux tolerance must be between 0 and 1"),
    ])
    def test_flux_validation_invalid_inputs(self, flux_input, tolerance_input, error_msg):
        """Test flux validation with invalid inputs."""
        with pytest.raises(ValueError, match=error_msg):
            validate_flux_parameters(flux_input, tolerance_input)


class TestFluxParameterIntegration:
    """Integration tests for flux parameters in optimization."""
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_single_flux_target(self):
        """Test optimization with single flux target."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.70,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            flux_targets_lmh=20.0,
            flux_tolerance=None
        )
        
        assert len(configs) >= 1
        
        # Check that flux targets are respected
        for config in configs:
            for stage in config['stages']:
                # Default tolerance is 10%
                assert 18.0 <= stage['design_flux_lmh'] <= 22.0
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_list_flux_targets(self):
        """Test optimization with per-stage flux targets."""
        flux_targets = [24, 20, 16]
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.75,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            flux_targets_lmh=flux_targets,
            flux_tolerance=0.15  # 15% tolerance
        )
        
        assert len(configs) >= 1
        
        # Check flux targets by stage
        for config in configs:
            for stage in config['stages']:
                stage_idx = stage['stage_number'] - 1
                if stage_idx < len(flux_targets):
                    target = flux_targets[stage_idx]
                else:
                    target = flux_targets[-1]  # Last value extended
                
                # With 15% tolerance
                lower = target * 0.85
                upper = target * 1.15
                
                assert lower <= stage['design_flux_lmh'] <= upper, \
                    f"Stage {stage['stage_number']} flux {stage['design_flux_lmh']} outside bounds [{lower}, {upper}]"
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_flux_tolerance_effect(self):
        """Test that flux tolerance affects optimization results."""
        # Run with tight tolerance
        configs_tight = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.70,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            flux_targets_lmh=18.0,
            flux_tolerance=0.05  # 5% tolerance
        )
        
        # Run with loose tolerance
        configs_loose = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.70,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            flux_targets_lmh=18.0,
            flux_tolerance=0.20  # 20% tolerance
        )
        
        # Both should find solutions
        assert len(configs_tight) >= 1
        assert len(configs_loose) >= 1
        
        # Tight tolerance should have flux closer to target
        for config in configs_tight:
            for stage in config['stages']:
                assert 17.1 <= stage['design_flux_lmh'] <= 18.9  # 5% bounds
        
        # Loose tolerance allows more variation
        for config in configs_loose:
            for stage in config['stages']:
                assert 14.4 <= stage['design_flux_lmh'] <= 21.6  # 20% bounds
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_emergency_flux_limits(self):
        """Test that emergency flux limits work during global optimization."""
        # Use a case that requires flux below normal tolerance
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=150,
            target_recovery=0.60,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            flux_targets_lmh=18.0,
            flux_tolerance=0.10,
            allow_recycle=False  # Force flux adjustment
        )
        
        if configs:
            # Check if any configuration uses emergency limits
            for config in configs:
                min_flux_ratio = min(stage['flux_ratio'] for stage in config['stages'])
                
                # Emergency limit is 70% of target
                assert min_flux_ratio >= 0.70, \
                    f"Flux ratio {min_flux_ratio} below emergency limit"
                
                # If recovery is close to target, flux might be below normal 90%
                if abs(config['total_recovery'] - 0.60) < 0.02:
                    # Successfully used emergency limits if needed
                    if min_flux_ratio < 0.90:
                        assert min_flux_ratio >= 0.70, "Emergency limits working"