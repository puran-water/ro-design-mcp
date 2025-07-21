"""
Tests for multi-configuration optimization output.
"""

import pytest
from utils.optimize_ro import optimize_vessel_array_configuration


class TestMultiConfiguration:
    """Tests for multi-configuration RO optimization."""
    
    @pytest.mark.optimization
    @pytest.mark.parametrize("feed_flow,recovery,min_configs,expected_stages", [
        (100, 0.50, 1, [1, 2]),      # 50% - should find 1 and possibly 2 stage
        (100, 0.75, 1, [2, 3]),      # 75% - should find 2 and possibly 3 stage
        (150, 0.96, 2, [2, 3]),      # 96% - should find recycle options
    ])
    def test_multiple_configurations_returned(self, feed_flow, recovery, min_configs, expected_stages):
        """Test that multiple viable configurations are returned."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=feed_flow,
            target_recovery=recovery,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            allow_recycle=True,
            max_recycle_ratio=0.9
        )
        
        # Should find at least the minimum expected configurations
        assert len(configs) >= min_configs, \
            f"Expected at least {min_configs} configs, got {len(configs)}"
        
        # Check stage counts
        stage_counts = [config['n_stages'] for config in configs]
        
        # At least one expected stage count should be present
        assert any(stage in stage_counts for stage in expected_stages), \
            f"Expected stages {expected_stages}, got {stage_counts}"
    
    @pytest.mark.optimization
    def test_configuration_diversity(self):
        """Test that returned configurations have meaningful differences."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.75,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            allow_recycle=True,
            max_recycle_ratio=0.9
        )
        
        if len(configs) > 1:
            # Extract key metrics for comparison
            stage_counts = [c['n_stages'] for c in configs]
            vessel_counts = [c['total_vessels'] for c in configs]
            areas = [c['total_membrane_area_m2'] for c in configs]
            uses_recycle = [c.get('recycle_ratio', 0) > 0 for c in configs]
            
            # Should have diversity in at least one dimension
            diversity_found = (
                len(set(stage_counts)) > 1 or
                len(set(vessel_counts)) > 1 or
                len(set(uses_recycle)) > 1 or
                max(areas) - min(areas) > 100  # Significant area difference
            )
            
            assert diversity_found, "Configurations lack meaningful diversity"
    
    @pytest.mark.optimization
    def test_recycle_configurations(self):
        """Test that high recovery targets produce recycle configurations."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=150,
            target_recovery=0.96,  # High recovery requiring recycle
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            allow_recycle=True,
            max_recycle_ratio=0.9
        )
        
        # Should have at least one configuration
        assert len(configs) >= 1
        
        # At least one should use recycle for 96% recovery
        recycle_configs = [c for c in configs if c.get('recycle_ratio', 0) > 0]
        assert len(recycle_configs) >= 1, "Expected recycle configurations for 96% recovery"
        
        # Check recycle parameters
        for config in recycle_configs:
            assert 0 < config['recycle_ratio'] <= 0.9
            assert config['recycle_flow_m3h'] > 0
            assert config['disposal_flow_m3h'] > 0
            # For recycle configurations, effective feed should be greater than the original feed
            assert config['effective_feed_flow_m3h'] > 100  # Original feed was 100 m3/h
    
    @pytest.mark.optimization
    def test_configuration_completeness(self):
        """Test that all configurations have complete information."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.75,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            allow_recycle=False
        )
        
        required_fields = [
            'n_stages', 'array_notation', 'total_vessels',
            'total_membrane_area_m2', 'total_recovery', 'recovery_error',
            'stages', 'min_flux_ratio', 'max_flux_ratio'
        ]
        
        for config in configs:
            # Check all required fields are present
            for field in required_fields:
                assert field in config, f"Missing required field: {field}"
            
            # Check stages have required information
            assert len(config['stages']) == config['n_stages']
            
            for stage in config['stages']:
                stage_fields = [
                    'stage_number', 'n_vessels', 'feed_flow_m3h',
                    'permeate_flow_m3h', 'concentrate_flow_m3h',
                    'stage_recovery', 'design_flux_lmh', 'flux_ratio'
                ]
                for field in stage_fields:
                    assert field in stage, f"Missing stage field: {field}"
    
    @pytest.mark.optimization
    @pytest.mark.parametrize("allow_recycle", [True, False])
    def test_recycle_toggle(self, allow_recycle):
        """Test that recycle can be enabled/disabled."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=150,
            target_recovery=0.90,  # High recovery where recycle helps
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            allow_recycle=allow_recycle,
            max_recycle_ratio=0.9
        )
        
        if allow_recycle:
            # Should have at least one configuration (might use recycle)
            assert len(configs) >= 1
        else:
            # Without recycle, might have fewer options or none for very high recovery
            # But should handle gracefully
            if configs:
                # If configs found, none should use recycle
                for config in configs:
                    assert config.get('recycle_ratio', 0) == 0
    
    @pytest.mark.optimization
    def test_flux_distribution(self):
        """Test that flux ratios are properly distributed across stages."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.75,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            allow_recycle=False
        )
        
        for config in configs:
            # Check flux ratio bounds
            assert 0.7 <= config['min_flux_ratio'] <= 1.1
            assert 0.7 <= config['max_flux_ratio'] <= 1.1
            assert config['min_flux_ratio'] <= config['max_flux_ratio']
            
            # Check individual stage flux ratios
            for stage in config['stages']:
                assert 0.7 <= stage['flux_ratio'] <= 1.1
                
                # Later stages typically have lower flux
                if stage['stage_number'] > 1:
                    prev_stage = config['stages'][stage['stage_number'] - 2]
                    # This is a soft check - not always true but common
                    if stage['flux_ratio'] > prev_stage['flux_ratio'] * 1.2:
                        # Log for debugging but don't fail
                        print(f"Note: Stage {stage['stage_number']} has higher flux than previous")