#!/usr/bin/env python3
"""Unit tests for the RO design MCP server."""

import unittest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestArcNaming(unittest.TestCase):
    """Test arc naming consistency in model builders."""
    
    def test_two_stage_arc_naming(self):
        """Test that 2-stage model has consistent arc naming."""
        from utils.ro_model_builder import build_ro_model_mcas
        from utils.mcas_builder import build_mcas_property_configuration
        
        # Create a 2-stage configuration
        config = {
            'stage_count': 2,
            'stages': [
                {'vessel_count': 17, 'membrane_area_m2': 4422.04},
                {'vessel_count': 8, 'membrane_area_m2': 2080.96}
            ],
            'feed_flow_m3h': 150
        }
        
        # Create MCAS config
        mcas_config = build_mcas_property_configuration(
            feed_composition={'Na_+': 787, 'Cl_-': 1213},
            include_scaling_ions=False,
            include_ph_species=False
        )
        
        # Build model
        m = build_ro_model_mcas(config, mcas_config, 25.0, 'brackish')
        
        # Check for expected arcs
        expected_arcs = [
            'ro_stage1_to_pump2',  # Critical arc that was missing
            'pump2_to_ro_stage2',
            'ro_stage2_perm_to_prod2'
        ]
        
        for arc_name in expected_arcs:
            self.assertTrue(hasattr(m.fs, arc_name), 
                          f"Arc {arc_name} not found in flowsheet")


class TestTDSCalculation(unittest.TestCase):
    """Test TDS calculations and mass fraction conversions."""
    
    def test_mass_fraction_to_ppm(self):
        """Test that mass fraction is correctly converted to PPM."""
        from utils.ro_model_builder import build_ro_model_mcas
        from utils.mcas_builder import build_mcas_property_configuration
        from pyomo.environ import value
        
        # Test configuration
        config = {
            'stage_count': 1,
            'stages': [{'vessel_count': 10, 'membrane_area_m2': 2601.2}],
            'feed_flow_m3h': 150
        }
        
        # Ion composition: 2000 mg/L total
        ion_composition = {'Na_+': 787, 'Cl_-': 1213}
        
        # Create MCAS config
        mcas_config = build_mcas_property_configuration(
            feed_composition=ion_composition,
            include_scaling_ions=False,
            include_ph_species=False
        )
        
        # Build model
        m = build_ro_model_mcas(config, mcas_config, 25.0, 'brackish')
        
        # Get flows
        h2o_flow = value(m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
        na_flow = value(m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'Na_+'])
        cl_flow = value(m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'Cl_-'])
        
        # Calculate mass fraction and PPM
        tds_flow = na_flow + cl_flow
        total_flow = h2o_flow + tds_flow
        mass_fraction = tds_flow / total_flow
        ppm = mass_fraction * 1e6
        
        # Check result (should be ~2000 ppm)
        self.assertAlmostEqual(ppm, 2000, delta=20,
                             msg=f"Expected ~2000 ppm, got {ppm:.0f} ppm")
    
    def test_salinity_validation(self):
        """Test validation when both salinity and ion composition are provided."""
        from utils.mcas_builder import get_total_dissolved_solids
        
        # Test case: stated salinity doesn't match ion composition
        feed_salinity_ppm = 5000
        feed_ion_composition = {'Na_+': 787, 'Cl_-': 1213}  # Actually 2000 mg/L
        
        actual_tds = get_total_dissolved_solids(feed_ion_composition)
        mismatch = abs(actual_tds - feed_salinity_ppm) / feed_salinity_ppm
        
        # Should detect >5% mismatch
        self.assertGreater(mismatch, 0.05,
                         "Should detect significant mismatch between stated and actual TDS")


class TestInitialization(unittest.TestCase):
    """Test initialization functions."""
    
    def test_tds_calculation_in_initialization(self):
        """Test that TDS is calculated correctly during initialization."""
        # This would test the ro_initialization.py functions
        # but requires a full model setup, so keeping it simple for now
        pass


if __name__ == '__main__':
    # Run tests
    print("Running unit tests for RO design MCP server...")
    unittest.main(verbosity=2)