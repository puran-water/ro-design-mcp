"""
Integration tests for optimization algorithm behavior.

These tests verify the optimization logic produces correct results
under various scenarios and edge cases.
"""

import pytest
from utils.optimize_ro import optimize_vessel_array_configuration
from utils.helpers import check_mass_balance


class TestOptimizationBehavior:
    """Test the optimization algorithm behavior and correctness."""
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_mass_balance_all_configurations(self):
        """Verify mass balance for all generated configurations."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.75,
            feed_salinity_ppm=5000,
            membrane_type='brackish'
        )
        
        for config in configs:
            # Check overall mass balance
            total_feed = 100.0
            total_permeate = sum(s['permeate_flow_m3h'] for s in config['stages'])
            total_concentrate = config['stages'][-1]['concentrate_flow_m3h']
            
            if config.get('recycle_ratio', 0) > 0:
                # With recycle, check effective flows
                assert abs(total_feed - (total_permeate + config['disposal_flow_m3h'])) < 0.01
            else:
                # Without recycle
                assert abs(total_feed - (total_permeate + total_concentrate)) < 0.01
            
            # Check stage-by-stage mass balance
            for i, stage in enumerate(config['stages']):
                feed = stage['feed_flow_m3h']
                permeate = stage['permeate_flow_m3h']
                concentrate = stage['concentrate_flow_m3h']
                assert abs(feed - (permeate + concentrate)) < 0.01
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_recovery_precision(self):
        """Test that optimizer achieves target recovery within tolerance."""
        target_recoveries = [0.50, 0.60, 0.70, 0.75, 0.80]
        
        for target in target_recoveries:
            configs = optimize_vessel_array_configuration(
                feed_flow_m3h=100,
                target_recovery=target,
                feed_salinity_ppm=5000,
                membrane_type='brackish'
            )
            
            # At least one configuration should meet the target
            met_target = False
            for config in configs:
                if abs(config['total_recovery'] - target) <= 0.02:
                    met_target = True
                    break
            
            assert met_target, f"No configuration met target recovery {target}"
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_stage_progression_logic(self):
        """Test that stages have logical progression of flows and concentrations."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=200,
            target_recovery=0.75,
            feed_salinity_ppm=5000,
            membrane_type='brackish'
        )
        
        for config in configs:
            if config['n_stages'] > 1:
                for i in range(1, len(config['stages'])):
                    prev_stage = config['stages'][i-1]
                    curr_stage = config['stages'][i]
                    
                    # Feed to next stage is concentrate from previous
                    assert abs(curr_stage['feed_flow_m3h'] - prev_stage['concentrate_flow_m3h']) < 0.01
                    
                    # Flow decreases through stages
                    assert curr_stage['feed_flow_m3h'] < prev_stage['feed_flow_m3h']
                    
                    # Salinity increases (implicitly through reduced recovery)
                    assert curr_stage['stage_recovery'] <= prev_stage['stage_recovery'] + 0.1
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_vessel_count_rationality(self):
        """Test that vessel counts are rational for given flow rates."""
        test_cases = [
            (50, 0.70),   # Small system
            (100, 0.75),  # Medium system
            (500, 0.75),  # Large system
            (1000, 0.70)  # Very large system
        ]
        
        for feed_flow, recovery in test_cases:
            configs = optimize_vessel_array_configuration(
                feed_flow_m3h=feed_flow,
                target_recovery=recovery,
                feed_salinity_ppm=5000,
                membrane_type='brackish'
            )
            
            for config in configs:
                # Total vessels should scale somewhat with flow
                vessels_per_100m3h = config['total_vessels'] / (feed_flow / 100)
                assert 5 <= vessels_per_100m3h <= 50, \
                    f"Unreasonable vessel count: {config['total_vessels']} for {feed_flow} m³/h"
                
                # Individual stages should have reasonable vessel counts
                for stage in config['stages']:
                    assert 1 <= stage['n_vessels'] <= 100
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_flux_emergency_limits(self):
        """Test that emergency flux limits are applied correctly."""
        # Request very high recovery that might trigger emergency limits
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.85,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            flux_targets_lmh=20,
            flux_tolerance=0.1
        )
        
        # Check if any configuration uses emergency limits
        for config in configs:
            for stage in config['stages']:
                # Emergency limit is 70% of target = 14 LMH
                if stage['design_flux_lmh'] < 18.0:  # Below normal tolerance
                    assert stage['design_flux_lmh'] >= 14.0, \
                        "Flux below emergency limit"
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_recycle_effectiveness(self):
        """Test that recycle improves recovery when needed."""
        # High recovery case
        configs_no_recycle = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.85,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            allow_recycle=False
        )
        
        configs_with_recycle = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.85,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            allow_recycle=True
        )
        
        # With recycle should achieve better recovery
        best_no_recycle = max((c['total_recovery'] for c in configs_no_recycle), default=0)
        best_with_recycle = max(c['total_recovery'] for c in configs_with_recycle)
        
        assert best_with_recycle >= best_no_recycle
        
        # Should have at least one config with recycle
        recycle_configs = [c for c in configs_with_recycle if c.get('recycle_ratio', 0) > 0]
        assert len(recycle_configs) > 0
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_membrane_area_calculation(self):
        """Test membrane area calculations are consistent."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=150,
            target_recovery=0.70,
            feed_salinity_ppm=5000,
            membrane_type='brackish'
        )
        
        ELEMENT_AREA = 37.16  # m²
        ELEMENTS_PER_VESSEL = 7
        
        for config in configs:
            # Total area should match sum of stages
            total_area_from_stages = sum(s['membrane_area_m2'] for s in config['stages'])
            assert abs(config['total_membrane_area_m2'] - total_area_from_stages) < 0.1
            
            # Area should match vessel count
            expected_area = config['total_vessels'] * ELEMENTS_PER_VESSEL * ELEMENT_AREA
            assert abs(config['total_membrane_area_m2'] - expected_area) < 0.1
            
            # Stage areas should match stage vessel counts
            for stage in config['stages']:
                stage_area = stage['n_vessels'] * ELEMENTS_PER_VESSEL * ELEMENT_AREA
                assert abs(stage['membrane_area_m2'] - stage_area) < 0.1
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_concentrate_flow_constraints(self):
        """Test that concentrate flow constraints are respected."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.80,
            feed_salinity_ppm=5000,
            membrane_type='brackish'
        )
        
        MIN_CONCENTRATE_FLOWS = [3.5, 3.8, 4.0]  # m³/h per vessel
        
        for config in configs:
            for stage in config['stages']:
                stage_num = stage['stage_number']
                if stage_num <= 3:
                    min_required = MIN_CONCENTRATE_FLOWS[stage_num - 1]
                    concentrate_per_vessel = stage['concentrate_flow_m3h'] / stage['n_vessels']
                    assert concentrate_per_vessel >= min_required * 0.95, \
                        f"Stage {stage_num} concentrate flow {concentrate_per_vessel:.2f} < {min_required}"
    
    @pytest.mark.integration
    @pytest.mark.optimization
    @pytest.mark.parametrize("membrane_type,max_recovery", [
        ("brackish", 0.85),
        ("seawater", 0.50)
    ])
    def test_membrane_type_limits(self, membrane_type, max_recovery):
        """Test that membrane types have appropriate recovery limits."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=max_recovery,
            feed_salinity_ppm=35000 if membrane_type == "seawater" else 5000,
            membrane_type=membrane_type
        )
        
        for config in configs:
            # Should not exceed reasonable recovery for membrane type
            if membrane_type == "seawater":
                assert config['total_recovery'] <= 0.55
            else:
                assert config['total_recovery'] <= 0.90
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_array_notation_correctness(self):
        """Test that array notation correctly represents configuration."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.75,
            feed_salinity_ppm=5000,
            membrane_type='brackish'
        )
        
        for config in configs:
            # Parse array notation
            vessel_counts = [int(x) for x in config['array_notation'].split(':')]
            
            # Should match stage count
            assert len(vessel_counts) == config['n_stages']
            
            # Should match individual stage vessels
            for i, count in enumerate(vessel_counts):
                assert count == config['stages'][i]['n_vessels']
            
            # Should sum to total vessels
            assert sum(vessel_counts) == config['total_vessels']
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_optimization_determinism(self):
        """Test that optimization produces consistent results."""
        # Run optimization multiple times with same inputs
        results = []
        for _ in range(3):
            configs = optimize_vessel_array_configuration(
                feed_flow_m3h=100,
                target_recovery=0.75,
                feed_salinity_ppm=5000,
                membrane_type='brackish',
                allow_recycle=False
            )
            results.append(configs)
        
        # Should produce same number of configurations
        assert len(results[0]) == len(results[1]) == len(results[2])
        
        # Array notations should be consistent
        notations_1 = sorted([c['array_notation'] for c in results[0]])
        notations_2 = sorted([c['array_notation'] for c in results[1]])
        notations_3 = sorted([c['array_notation'] for c in results[2]])
        
        assert notations_1 == notations_2 == notations_3
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_flux_ratio_bounds(self):
        """Test that flux ratios stay within reasonable bounds."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=200,
            target_recovery=0.75,
            feed_salinity_ppm=5000,
            membrane_type='brackish'
        )
        
        for config in configs:
            # Global bounds
            assert 0.6 <= config['min_flux_ratio'] <= 1.2
            assert 0.6 <= config['max_flux_ratio'] <= 1.2
            
            # Stage bounds
            for stage in config['stages']:
                assert 0.6 <= stage['flux_ratio'] <= 1.2
                
                # First stage often has highest ratio
                if stage['stage_number'] == 1:
                    assert stage['flux_ratio'] >= 0.8  # Not too low for first stage
    
    @pytest.mark.integration
    @pytest.mark.optimization
    def test_recycle_split_optimization(self):
        """Test that recycle split is optimized properly."""
        configs = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.88,
            feed_salinity_ppm=5000,
            membrane_type='brackish',
            allow_recycle=True
        )
        
        recycle_configs = [c for c in configs if c.get('recycle_ratio', 0) > 0]
        
        for config in recycle_configs:
            # Split ratio should be reasonable
            assert 0.3 <= config['recycle_split_ratio'] <= 1.0
            
            # Disposal flow should be positive
            assert config['disposal_flow_m3h'] > 0
            
            # Recycle flow calculation
            total_concentrate = config['stages'][-1]['concentrate_flow_m3h']
            expected_recycle = total_concentrate * config['recycle_split_ratio']
            assert abs(config['recycle_flow_m3h'] - expected_recycle) < 0.1