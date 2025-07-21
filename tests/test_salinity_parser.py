#!/usr/bin/env python3
"""Test salinity parsing and TDS calculations."""

import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.mcas_builder import (
    get_total_dissolved_solids,
    build_mcas_property_configuration,
    check_electroneutrality
)
from utils.ro_model_builder import build_ro_model_mcas
from pyomo.environ import value


class TestSalinityCalculations(unittest.TestCase):
    """Test salinity and TDS calculations."""
    
    def test_tds_calculation_from_ions(self):
        """Test TDS calculation from ion composition."""
        # Test case 1: Simple NaCl solution
        ion_comp_1 = {'Na_+': 787, 'Cl_-': 1213}
        tds_1 = get_total_dissolved_solids(ion_comp_1)
        self.assertAlmostEqual(tds_1, 2000, delta=1,
                             msg="TDS calculation for NaCl failed")
        
        # Test case 2: Complex ion mixture
        ion_comp_2 = {
            'Na_+': 1000,
            'Cl_-': 1500,
            'Ca_2+': 200,
            'Mg_2+': 100,
            'SO4_2-': 300,
            'HCO3_-': 150
        }
        tds_2 = get_total_dissolved_solids(ion_comp_2)
        self.assertAlmostEqual(tds_2, 3250, delta=1,
                             msg="TDS calculation for complex mixture failed")
    
    def test_mass_fraction_to_ppm_conversion(self):
        """Test that mass fraction correctly converts to PPM in model."""
        config = {
            'stage_count': 1,
            'stages': [{'vessel_count': 10, 'membrane_area_m2': 2601.2}],
            'feed_flow_m3h': 150  # 0.04167 m³/s
        }
        
        # Ion composition: 2000 mg/L total
        ion_composition = {'Na_+': 787, 'Cl_-': 1213}
        
        mcas_config = build_mcas_property_configuration(
            feed_composition=ion_composition,
            include_scaling_ions=False,
            include_ph_species=False
        )
        
        # Build model
        m = build_ro_model_mcas(config, mcas_config, 2000, 25.0, 'brackish')
        
        # Get flows - unified model uses fresh_feed
        h2o_flow = value(m.fs.fresh_feed.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
        na_flow = value(m.fs.fresh_feed.outlet.flow_mass_phase_comp[0, 'Liq', 'Na_+'])
        cl_flow = value(m.fs.fresh_feed.outlet.flow_mass_phase_comp[0, 'Liq', 'Cl_-'])
        
        # Calculate mass fraction and PPM
        tds_flow = na_flow + cl_flow
        total_flow = h2o_flow + tds_flow
        mass_fraction = tds_flow / total_flow
        ppm = mass_fraction * 1e6
        
        # Check result (should be ~2000 ppm)
        self.assertAlmostEqual(ppm, 2000, delta=20,
                             msg=f"Expected ~2000 ppm, got {ppm:.0f} ppm")
        
        # Verify individual ion flows
        feed_flow_m3_s = config['feed_flow_m3h'] / 3600
        expected_na_flow = 787 * feed_flow_m3_s / 1000  # mg/L * m³/s / 1000 = kg/s
        expected_cl_flow = 1213 * feed_flow_m3_s / 1000
        
        self.assertAlmostEqual(na_flow, expected_na_flow, delta=1e-6,
                             msg="Na+ flow rate incorrect")
        self.assertAlmostEqual(cl_flow, expected_cl_flow, delta=1e-6,
                             msg="Cl- flow rate incorrect")
    
    def test_salinity_mismatch_detection(self):
        """Test detection of mismatch between stated salinity and ion composition."""
        # Test case: stated salinity doesn't match ion composition
        feed_salinity_ppm = 5000
        feed_ion_composition = {'Na_+': 787, 'Cl_-': 1213}  # Actually 2000 mg/L
        
        # Calculate mismatch
        actual_tds = get_total_dissolved_solids(feed_ion_composition)
        mismatch = abs(actual_tds - feed_salinity_ppm) / feed_salinity_ppm
        
        # Should detect >5% mismatch
        self.assertGreater(mismatch, 0.05,
                         "Should detect significant mismatch between stated and actual TDS")
        
        # Verify the actual TDS is what we expect
        self.assertAlmostEqual(actual_tds, 2000, 1,
                             "Ion composition should sum to 2000 mg/L")
    
    def test_high_tds_calculation(self):
        """Test TDS calculations for high salinity waters."""
        # Seawater composition
        seawater_comp = {
            'Na_+': 10760,
            'Cl_-': 19350,
            'Mg_2+': 1290,
            'Ca_2+': 410,
            'K_+': 390,
            'SO4_2-': 2710,
            'HCO3_-': 142
        }
        
        tds = get_total_dissolved_solids(seawater_comp)
        self.assertAlmostEqual(tds, 35052, delta=10,
                             msg="Seawater TDS calculation incorrect")
    
    def test_electroneutrality_check(self):
        """Test electroneutrality checking."""
        # Balanced composition
        balanced = {'Na_+': 1000, 'Cl_-': 1547}  # Molar charge balanced
        is_neutral, imbalance = check_electroneutrality(balanced)
        self.assertLess(abs(imbalance), 0.05,
                       msg="Balanced composition should have <5% charge imbalance")
        
        # Unbalanced composition
        unbalanced = {'Na_+': 1000, 'Cl_-': 500}  # Very unbalanced
        is_neutral, imbalance = check_electroneutrality(unbalanced)
        self.assertGreater(abs(imbalance), 0.05,
                          msg="Unbalanced composition should have >5% charge imbalance")
    
    def test_no_salinity_multiplication(self):
        """Test that salinity is not multiplied during feed parsing."""
        config = {
            'stage_count': 1,
            'stages': [{'vessel_count': 10, 'membrane_area_m2': 2601.2}],
            'feed_flow_m3h': 100
        }
        
        # Test with exact salinity match
        target_salinity = 3000
        ion_comp = {'Na_+': 1180, 'Cl_-': 1820}  # Exactly 3000 mg/L
        
        mcas_config = build_mcas_property_configuration(
            feed_composition=ion_comp,
            include_scaling_ions=False,
            include_ph_species=False
        )
        
        # Verify MCAS config has correct ion composition
        self.assertEqual(mcas_config['ion_composition_mg_l']['Na_+'], 1180)
        self.assertEqual(mcas_config['ion_composition_mg_l']['Cl_-'], 1820)
        
        # Build model and check flows
        m = build_ro_model_mcas(config, mcas_config, target_salinity, 25.0, 'brackish')
        
        # Calculate TDS from model - unified model uses fresh_feed
        h2o_flow = value(m.fs.fresh_feed.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
        na_flow = value(m.fs.fresh_feed.outlet.flow_mass_phase_comp[0, 'Liq', 'Na_+'])
        cl_flow = value(m.fs.fresh_feed.outlet.flow_mass_phase_comp[0, 'Liq', 'Cl_-'])
        
        tds_flow = na_flow + cl_flow
        total_flow = h2o_flow + tds_flow
        model_tds_ppm = (tds_flow / total_flow) * 1e6
        
        # Should be exactly 3000 ppm (within numerical tolerance)
        self.assertAlmostEqual(model_tds_ppm, target_salinity, delta=30,
                             msg=f"Model TDS ({model_tds_ppm:.0f}) should match target ({target_salinity})")


if __name__ == '__main__':
    unittest.main(verbosity=2)