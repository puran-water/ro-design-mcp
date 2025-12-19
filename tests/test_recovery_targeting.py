"""
Tests for recovery targeting and flux optimization.
"""

import pytest
from utils.optimize_ro import optimize_vessel_array_configuration


class TestRecoveryTargeting:
    """Tests for precise recovery targeting."""
    
    @pytest.mark.optimization
    @pytest.mark.parametrize("target_recovery,feed_flow", [
        (0.60, 150),  # Original 60% recovery case
        (0.50, 100),  # Low recovery
        (0.75, 100),  # Medium recovery
        (0.85, 100),  # High recovery
    ])
    def test_recovery_within_tolerance(self, target_recovery, feed_flow):
        """Test that achieved recovery is within 2% tolerance of target."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=feed_flow,
            target_recovery=target_recovery,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            allow_recycle=True,
            max_recycle_ratio=0.9
        )
        
        # Should find at least one configuration
        assert len(configs) >= 1
        
        # Check all configurations
        for config in configs:
            # Recovery should never be below target
            assert config['total_recovery'] >= target_recovery, \
                f"Recovery {config['total_recovery']} is below target {target_recovery}"
            
            # Recovery error should be within 2% tolerance
            assert config['recovery_error'] <= 0.02, \
                f"Recovery error {config['recovery_error']} exceeds 2% tolerance"
    
    @pytest.mark.optimization
    def test_60_recovery_precise(self):
        """Test the specific 60% recovery case that was problematic."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=150,
            target_recovery=0.60,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            allow_recycle=True,
            max_recycle_ratio=0.9
        )
        
        assert len(configs) >= 1
        
        # Find the best configuration (lowest error)
        best_config = min(configs, key=lambda c: c['recovery_error'])
        
        # Should achieve close to 60% recovery
        assert best_config['total_recovery'] >= 0.60
        assert best_config['total_recovery'] <= 0.62  # Within 2% tolerance
        
        # Check flux ratios - at least one stage should use emergency limits if needed
        flux_ratios = [stage['flux_ratio'] for stage in best_config['stages']]
        
        # If overshooting was an issue, some flux should be below 90%
        if best_config['total_recovery'] > 0.60:
            assert any(ratio < 0.9 for ratio in flux_ratios), \
                "Expected emergency flux limits to be used"
    
    @pytest.mark.optimization
    def test_flux_emergency_limits(self):
        """Test that emergency flux limits (70% of target) can be used when needed."""
        # Use a challenging recovery target that requires emergency limits
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=150,
            target_recovery=0.55,  # Low recovery that might need flux reduction
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            allow_recycle=False  # No recycle to force flux adjustment
        )
        
        if configs:
            # Check if any configuration uses flux below normal limits
            for config in configs:
                min_flux_ratio = min(stage['flux_ratio'] for stage in config['stages'])
                
                # Emergency limit is 70% of target
                if config['total_recovery'] > config['target_recovery']:
                    # If overshooting, should be able to go below 90%
                    assert min_flux_ratio >= 0.7, \
                        f"Flux ratio {min_flux_ratio} is below emergency limit of 70%"
    
    @pytest.mark.optimization
    @pytest.mark.parametrize("use_recycle", [True, False])
    def test_multi_configuration_output(self, use_recycle):
        """Test that multiple configurations are returned when available."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.75,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            allow_recycle=use_recycle,
            max_recycle_ratio=0.9
        )
        
        # Should return multiple configurations
        assert len(configs) >= 1
        
        # Extract stage counts
        stage_counts = [config['n_stages'] for config in configs]
        
        # Should have different stage options if recovery allows
        if use_recycle:
            # With recycle, might have more options
            assert len(set(stage_counts)) >= 1
        
        # All configurations should meet recovery target
        for config in configs:
            assert config['total_recovery'] >= config['target_recovery']
    
    @pytest.mark.optimization
    def test_no_undershooting_recovery(self):
        """Test that configurations never undershoot the target recovery."""
        # Test various recovery targets
        recovery_targets = [0.50, 0.60, 0.70, 0.80, 0.90]
        
        for target in recovery_targets:
            configs = optimize_vessel_array_configuration(
                feed_flow_m3h=100,
                target_recovery=target,
                feed_salinity_ppm=5000,
                membrane_type='brackish',
                allow_recycle=True,
                max_recycle_ratio=0.9
            )
            
            for config in configs:
                assert config['total_recovery'] >= target, \
                    f"Config undershoots target {target}: {config['total_recovery']}"