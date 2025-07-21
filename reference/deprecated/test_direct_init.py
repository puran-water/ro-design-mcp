#!/usr/bin/env python3
"""
Direct test of model initialization to isolate the 666,667 ppm error.
This bypasses the notebook to test the core functions directly.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.mcas_builder import build_mcas_property_configuration
from utils.ro_model_builder import build_ro_model_mcas
from utils.ro_solver import initialize_and_solve_mcas
import logging

# Enable detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s: %(message)s'
)

def test_direct_initialization():
    """Test model building and initialization directly."""
    print("\n" + "="*60)
    print("Direct Model Initialization Test")
    print("="*60)
    
    # Simple configuration
    configuration = {
        'array_notation': '1:0',
        'feed_flow_m3h': 100,
        'stage_count': 1,
        'n_stages': 1,
        'stages': [
            {'stage_recovery': 0.5, 'stage_number': 1, 'membrane_area_m2': 260}
        ],
        'recycle_info': {
            'uses_recycle': False,
            'recycle_ratio': 0,
            'recycle_split_ratio': 0
        },
        'feed_salinity_ppm': 5000
    }
    
    # Ion composition
    feed_ion_composition = {
        'Na+': 5000 * 0.393,
        'Cl-': 5000 * 0.607,
    }
    
    try:
        # Build MCAS config
        print("\n1. Building MCAS configuration...")
        mcas_config = build_mcas_property_configuration(
            feed_composition=feed_ion_composition,
            include_scaling_ions=False,
            include_ph_species=False
        )
        print("   MCAS config created successfully")
        
        # Build model
        print("\n2. Building RO model...")
        model = build_ro_model_mcas(
            configuration,
            mcas_config,
            5000,  # feed_salinity_ppm
            25.0,  # temperature
            "brackish"
        )
        print("   Model built successfully")
        
        # Check feed initialization
        print("\n3. Checking feed state...")
        from pyomo.environ import value
        feed_outlet = model.fs.fresh_feed.outlet
        h2o_flow = value(feed_outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
        na_flow = value(feed_outlet.flow_mass_phase_comp[0, 'Liq', 'Na+'])
        cl_flow = value(feed_outlet.flow_mass_phase_comp[0, 'Liq', 'Cl-'])
        
        total_flow = h2o_flow + na_flow + cl_flow
        tds_flow = na_flow + cl_flow
        tds_ppm = (tds_flow / total_flow) * 1e6
        
        print(f"   H2O flow: {h2o_flow:.4f} kg/s")
        print(f"   Na+ flow: {na_flow:.6f} kg/s")
        print(f"   Cl- flow: {cl_flow:.6f} kg/s")
        print(f"   TDS: {tds_ppm:.0f} ppm (expected: 5000 ppm)")
        
        if abs(tds_ppm - 5000) > 100:
            print("   WARNING: Feed TDS doesn't match expected value!")
        
        # Initialize and solve
        print("\n4. Initializing and solving model...")
        result = initialize_and_solve_mcas(model, configuration, optimize_pumps=False)
        
        if result['status'] == 'success':
            print("\n[SUCCESS] Model initialized without 666,667 ppm error!")
            return True
        else:
            error_msg = result.get('message', '')
            if '666667' in str(error_msg):
                print(f"\n[FAIL] 666,667 ppm error detected: {error_msg}")
                
                # Additional debugging
                print("\n5. Debugging mixer outlet state...")
                mixer_outlet = model.fs.feed_mixer.outlet
                mixer_h2o = value(mixer_outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
                mixer_na = value(mixer_outlet.flow_mass_phase_comp[0, 'Liq', 'Na+'])
                mixer_cl = value(mixer_outlet.flow_mass_phase_comp[0, 'Liq', 'Cl-'])
                
                mixer_total = mixer_h2o + mixer_na + mixer_cl
                mixer_tds = mixer_na + mixer_cl
                mixer_tds_ppm = (mixer_tds / mixer_total) * 1e6 if mixer_total > 0 else 0
                
                print(f"   Mixer H2O flow: {mixer_h2o:.4f} kg/s")
                print(f"   Mixer Na+ flow: {mixer_na:.6f} kg/s")
                print(f"   Mixer Cl- flow: {mixer_cl:.6f} kg/s")
                print(f"   Mixer outlet TDS: {mixer_tds_ppm:.0f} ppm")
                
                return False
            else:
                print(f"\n[INFO] Different error: {error_msg}")
                return True
                
    except Exception as e:
        print(f"\n[ERROR] Exception occurred: {str(e)}")
        if '666667' in str(e):
            print("[FAIL] 666,667 ppm error in exception!")
            
            # Try to debug where it's coming from
            import traceback
            print("\nTraceback:")
            traceback.print_exc()
            
            return False
        else:
            return True


def main():
    """Run the direct test."""
    passed = test_direct_initialization()
    
    print("\n" + "="*60)
    if passed:
        print("[SUCCESS] Direct initialization test passed - No 666,667 ppm error!")
    else:
        print("[FAIL] Direct initialization test failed - 666,667 ppm error present!")
    print("="*60)
    
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())