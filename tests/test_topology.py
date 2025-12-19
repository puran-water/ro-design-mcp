#!/usr/bin/env python3
"""Test topology and arc naming consistency in RO models."""

import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.ro_model_builder import build_ro_model_mcas
from utils.mcas_builder import build_mcas_property_configuration
from pyomo.environ import value


class TestArcNaming(unittest.TestCase):
    """Test arc naming consistency across model builders."""
    
    def setUp(self):
        """Set up test configurations."""
        self.mcas_config = build_mcas_property_configuration(
            feed_composition={'Na_+': 787, 'Cl_-': 1213},
            include_scaling_ions=False,
            include_ph_species=False
        )
    
    def test_single_stage_arcs(self):
        """Test arc naming for single-stage model with unified architecture."""
        config = {
            'stage_count': 1,
            'stages': [{'vessel_count': 10, 'membrane_area_m2': 2601.2}],
            'feed_flow_m3h': 150
        }
        
        m = build_ro_model_mcas(config, self.mcas_config, 2000, 25.0, 'brackish')
        
        # Expected arcs for single stage with unified architecture
        expected_arcs = [
            'fresh_to_mixer',  # Always present in unified model
            'mixer_to_pump1',  # Feed goes through mixer
            'pump1_to_ro_stage1',
            'ro_stage1_perm_to_prod',
            'final_conc_to_split',  # Always goes to splitter
            'split_to_disposal',
            'split_to_recycle'
        ]
        
        for arc_name in expected_arcs:
            self.assertTrue(hasattr(m.fs, arc_name), 
                          f"Arc {arc_name} not found in single-stage unified model")
    
    def test_two_stage_arcs(self):
        """Test arc naming for two-stage model with unified architecture."""
        config = {
            'stage_count': 2,
            'stages': [
                {'vessel_count': 17, 'membrane_area_m2': 4422.04},
                {'vessel_count': 8, 'membrane_area_m2': 2080.96}
            ],
            'feed_flow_m3h': 150
        }
        
        m = build_ro_model_mcas(config, self.mcas_config, 2000, 25.0, 'brackish')
        
        # Expected arcs for two stages with unified architecture
        expected_arcs = [
            'fresh_to_mixer',
            'mixer_to_pump1',
            'pump1_to_ro_stage1',
            'ro_stage1_perm_to_prod',
            'ro_stage1_to_pump2',  # Critical inter-stage arc
            'pump2_to_ro_stage2',
            'ro_stage2_perm_to_prod2',
            'final_conc_to_split',
            'split_to_disposal',
            'split_to_recycle'
        ]
        
        for arc_name in expected_arcs:
            self.assertTrue(hasattr(m.fs, arc_name), 
                          f"Arc {arc_name} not found in two-stage unified model")
    
    def test_three_stage_arcs(self):
        """Test arc naming for three-stage model with unified architecture."""
        config = {
            'stage_count': 3,
            'stages': [
                {'vessel_count': 20, 'membrane_area_m2': 5203.2},
                {'vessel_count': 10, 'membrane_area_m2': 2601.6},
                {'vessel_count': 5, 'membrane_area_m2': 1300.8}
            ],
            'feed_flow_m3h': 150
        }
        
        m = build_ro_model_mcas(config, self.mcas_config, 2000, 25.0, 'brackish')
        
        # Check inter-stage arcs follow consistent pattern
        for i in range(1, 3):  # stages 1 and 2 have connections to next stage
            arc_name = f"ro_stage{i}_to_pump{i+1}"
            self.assertTrue(hasattr(m.fs, arc_name), 
                          f"Inter-stage arc {arc_name} not found")
            
            arc_name = f"pump{i+1}_to_ro_stage{i+1}"
            self.assertTrue(hasattr(m.fs, arc_name), 
                          f"Pump to RO arc {arc_name} not found")
    
    def test_recycle_model_arcs(self):
        """Test arc naming for model with recycle enabled."""
        config = {
            'stage_count': 2,
            'stages': [
                {'vessel_count': 17, 'membrane_area_m2': 4422.04},
                {'vessel_count': 8, 'membrane_area_m2': 2080.96}
            ],
            'feed_flow_m3h': 150,
            'recycle_info': {
                'uses_recycle': True,
                'recycle_split_ratio': 0.5
            }
        }
        
        m = build_ro_model_mcas(
            config, self.mcas_config, 2000, 25.0, 'brackish'
        )
        
        # Expected recycle-specific arcs (same as all unified models)
        expected_arcs = [
            'fresh_to_mixer',
            'mixer_to_pump1',
            'split_to_disposal',
            'split_to_recycle',
            'final_conc_to_split'
        ]
        
        for arc_name in expected_arcs:
            self.assertTrue(hasattr(m.fs, arc_name), 
                          f"Arc {arc_name} not found in unified model")
        
        # Check fresh_feed block exists (not an alias anymore)
        self.assertTrue(hasattr(m.fs, 'fresh_feed'), 
                      "Fresh feed block not found in unified model")
    
    def test_arc_connectivity(self):
        """Test that arcs properly connect components in unified model."""
        config = {
            'stage_count': 2,
            'stages': [
                {'vessel_count': 10, 'membrane_area_m2': 2601.2},
                {'vessel_count': 5, 'membrane_area_m2': 1300.6}
            ],
            'feed_flow_m3h': 100
        }
        
        m = build_ro_model_mcas(config, self.mcas_config, 2000, 25.0, 'brackish')
        
        # Check arc connectivity
        # Stage 1 to pump 2 arc
        arc = m.fs.ro_stage1_to_pump2
        self.assertTrue(arc.source.parent_block().name.endswith('ro_stage1'))
        self.assertTrue(arc.destination.parent_block().name.endswith('pump2'))
        
        # Pump 2 to stage 2 arc
        arc = m.fs.pump2_to_ro_stage2
        self.assertTrue(arc.source.parent_block().name.endswith('pump2'))
        self.assertTrue(arc.destination.parent_block().name.endswith('ro_stage2'))


class TestUnifiedModelStructure(unittest.TestCase):
    """Test unified model structure consistency."""
    
    def setUp(self):
        """Set up test configurations."""
        self.mcas_config = build_mcas_property_configuration(
            feed_composition={'Na_+': 787, 'Cl_-': 1213},
            include_scaling_ions=False,
            include_ph_species=False
        )
    
    def test_fresh_feed_exists(self):
        """Test that fresh_feed block exists in unified model."""
        config = {
            'stage_count': 1,
            'stages': [{'vessel_count': 10, 'membrane_area_m2': 2601.2}],
            'feed_flow_m3h': 150
        }
        
        m = build_ro_model_mcas(config, self.mcas_config, 2000, 25.0, 'brackish')
        
        # Check fresh_feed exists as a real Feed block
        self.assertTrue(hasattr(m.fs, 'fresh_feed'), "Fresh_feed block not found")
        
        # Check it's a Feed unit, not an alias
        from idaes.models.unit_models import Feed
        self.assertIsInstance(m.fs.fresh_feed, Feed, 
                            "fresh_feed should be a Feed unit in unified model")
    
    def test_recycle_infrastructure_always_present(self):
        """Test that recycle infrastructure is always present."""
        config = {
            'stage_count': 1,
            'stages': [{'vessel_count': 10, 'membrane_area_m2': 2601.2}],
            'feed_flow_m3h': 150
        }
        
        m = build_ro_model_mcas(config, self.mcas_config, 2000, 25.0, 'brackish')
        
        # Check all recycle components exist
        self.assertTrue(hasattr(m.fs, 'feed_mixer'), "Feed mixer not found")
        self.assertTrue(hasattr(m.fs, 'recycle_split'), "Recycle splitter not found")
        self.assertTrue(hasattr(m.fs, 'disposal_product'), "Disposal product not found")
        
        # Check recycle split fraction is set to epsilon for non-recycle
        recycle_split_value = value(m.fs.recycle_split.split_fraction[0, "recycle"])
        self.assertLess(recycle_split_value, 1e-6, 
                       "Recycle split should be ~0 for non-recycle configuration")


if __name__ == '__main__':
    unittest.main(verbosity=2)