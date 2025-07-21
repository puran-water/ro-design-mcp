#!/usr/bin/env python3
"""
Test enhanced initialization with TDS-aware pressure calculations.

This script tests the new initialization approach on configurations that 
previously failed with FBBT infeasibility errors.
"""

import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('test_enhanced_init.log', mode='w')
    ]
)

from pyomo.environ import ConcreteModel, value
from idaes.core import FlowsheetBlock
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.models.properties.modular_properties import GenericParameterBlock
from watertap.property_models.seawater_prop_pack import SeawaterParameterBlock
from watertap.unit_models.reverse_osmosis_base import TransportModel

from utils.test_model_builder import build_multistage_ro_flowsheet
from utils.ro_initialization import initialize_multistage_ro_enhanced
from utils.ro_initialization_debug import FluxDebugLogger
from utils.membrane_properties_handler import get_membrane_properties


def test_eco_pro_400_initialization():
    """Test ECO PRO-400 membrane that previously failed."""
    
    print("\n" + "="*80)
    print("TESTING ECO PRO-400 MEMBRANE WITH ENHANCED INITIALIZATION")
    print("="*80)
    
    # Create model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    
    # Get membrane properties (returns tuple)
    # Use the key from config file: eco_pro_400
    A_w, B_s = get_membrane_properties('eco_pro_400')
    # Convert to dict format for model builder
    membrane_props = {
        'A_comp': A_w,
        'B_comp': B_s,
        'name': 'ECO PRO-400'
    }
    print(f"\nMembrane: ECO PRO-400 (eco_pro_400)")
    print(f"A_w: {A_w:.2e} m/s/Pa")
    print(f"B_s: {B_s:.2e} m/s")
    
    # Test configurations
    test_cases = [
        {
            'name': 'Low TDS, 3-stage',
            'feed_tds': 1000,  # ppm
            'feed_flow': 5,    # kg/s
            'recoveries': [0.5, 0.5, 0.5],
            'n_stages': 3
        },
        {
            'name': 'High TDS, 2-stage',
            'feed_tds': 5000,  # ppm
            'feed_flow': 5,    # kg/s
            'recoveries': [0.5, 0.5],
            'n_stages': 2
        },
        {
            'name': 'Seawater, single stage',
            'feed_tds': 35000,  # ppm
            'feed_flow': 2,     # kg/s
            'recoveries': [0.45],
            'n_stages': 1
        }
    ]
    
    results = []
    
    for test_case in test_cases:
        print(f"\n\nTest Case: {test_case['name']}")
        print("-"*60)
        
        try:
            # Build flowsheet
            build_multistage_ro_flowsheet(
                m,
                prop_package=SeawaterParameterBlock,
                number_of_stages=test_case['n_stages'],
                has_recycle=False,
                membrane_props=membrane_props,
                transport_model=TransportModel.SD
            )
            
            # Set feed conditions
            feed = m.fs.feed
            feed.properties[0].temperature.fix(298.15)
            feed.properties[0].pressure.fix(101325)
            
            # Set mass fractions
            mass_frac_H2O = 1 - test_case['feed_tds']/1e6
            mass_frac_TDS = test_case['feed_tds']/1e6
            
            feed.properties[0].flow_mass_phase_comp['Liq', 'H2O'].fix(
                test_case['feed_flow'] * mass_frac_H2O
            )
            feed.properties[0].flow_mass_phase_comp['Liq', 'TDS'].fix(
                test_case['feed_flow'] * mass_frac_TDS
            )
            
            print(f"Feed conditions set:")
            print(f"  TDS: {test_case['feed_tds']} ppm")
            print(f"  Flow: {test_case['feed_flow']} kg/s")
            print(f"  Stages: {test_case['n_stages']}")
            print(f"  Recoveries: {test_case['recoveries']}")
            
            # Check degrees of freedom
            print(f"\nDegrees of freedom: {degrees_of_freedom(m)}")
            
            # Create debug logger
            logger = FluxDebugLogger("enhanced_init_test")
            
            # Initialize with enhanced method
            print("\nRunning enhanced initialization...")
            stage_conditions = initialize_multistage_ro_enhanced(
                m,
                stage_recoveries=test_case['recoveries'],
                feed_tds_ppm=test_case['feed_tds'],
                A_w=membrane_props['A_comp'],
                verbose=True,
                debug_logger=logger
            )
            
            # Check results
            print("\nVerifying results...")
            
            # Check each stage
            stage_results = []
            for i in range(test_case['n_stages']):
                stage_num = i + 1
                if stage_num == 1:
                    ro = m.fs.ro1
                else:
                    ro = getattr(m.fs, f'ro{stage_num}')
                
                # Get actual values
                feed_pressure = value(ro.feed.pressure[0])
                actual_flux = value(ro.flux_mass_phase_comp[0, 0, 'Liq', 'H2O'])
                recovery = value(ro.recovery_frac_mass_H2O[0])
                
                stage_result = {
                    'stage': stage_num,
                    'feed_pressure_bar': feed_pressure / 1e5,
                    'flux_kg_m2_s': actual_flux,
                    'recovery': recovery,
                    'flux_ok': actual_flux < 0.03,
                    'pressure_ok': feed_pressure < 100e5  # 100 bar limit
                }
                stage_results.append(stage_result)
                
                print(f"\n  Stage {stage_num}:")
                print(f"    Feed pressure: {stage_result['feed_pressure_bar']:.1f} bar")
                print(f"    Flux: {stage_result['flux_kg_m2_s']:.4f} kg/m²/s")
                print(f"    Recovery: {stage_result['recovery']:.1%}")
                print(f"    Flux OK: {'PASS' if stage_result['flux_ok'] else 'FAIL'}")
            
            # Overall result
            success = all(sr['flux_ok'] for sr in stage_results)
            
            results.append({
                'test_case': test_case['name'],
                'success': success,
                'stage_results': stage_results,
                'error': None
            })
            
            print(f"\nOVERALL: {'SUCCESS' if success else 'FAILED'}")
            
        except Exception as e:
            print(f"\nERROR: {str(e)}")
            results.append({
                'test_case': test_case['name'],
                'success': False,
                'stage_results': None,
                'error': str(e)
            })
    
    # Summary
    print("\n\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for result in results:
        status = "PASS" if result['success'] else "FAIL"
        print(f"\n{result['test_case']}: {status}")
        
        if result['error']:
            print(f"  Error: {result['error']}")
        elif result['stage_results']:
            for sr in result['stage_results']:
                print(f"  Stage {sr['stage']}: "
                      f"{sr['feed_pressure_bar']:.1f} bar, "
                      f"{sr['flux_kg_m2_s']:.4f} kg/m²/s")
    
    # Overall success
    all_passed = all(r['success'] for r in results)
    print(f"\n{'='*80}")
    print(f"All tests passed: {'YES' if all_passed else 'NO'}")
    print(f"{'='*80}")
    
    return all_passed


def test_specific_failing_case():
    """Test the specific case that was failing with FBBT errors."""
    
    print("\n" + "="*80)
    print("TESTING SPECIFIC FAILING CONFIGURATION")
    print("="*80)
    
    # This is the configuration that was failing
    membrane_name = 'eco_pro_400'  # Use config key
    membrane_display_name = 'ECO PRO-400'
    feed_tds = 1000  # ppm
    feed_flow = 5    # kg/s
    recoveries = [0.5, 0.5, 0.5]
    
    # Create model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    
    # Get membrane properties (returns tuple)
    A_w, B_s = get_membrane_properties(membrane_name)
    # Convert to dict format for model builder
    membrane_props = {
        'A_comp': A_w,
        'B_comp': B_s,
        'name': membrane_name
    }
    
    # Build 3-stage system
    build_multistage_ro_flowsheet(
        m,
        prop_package=SeawaterParameterBlock,
        number_of_stages=3,
        has_recycle=False,
        membrane_props=membrane_props,
        transport_model=TransportModel.SD
    )
    
    # Set feed
    feed = m.fs.feed
    feed.properties[0].temperature.fix(298.15)
    feed.properties[0].pressure.fix(101325)
    
    mass_frac_H2O = 1 - feed_tds/1e6
    mass_frac_TDS = feed_tds/1e6
    
    feed.properties[0].flow_mass_phase_comp['Liq', 'H2O'].fix(feed_flow * mass_frac_H2O)
    feed.properties[0].flow_mass_phase_comp['Liq', 'TDS'].fix(feed_flow * mass_frac_TDS)
    
    print(f"\nConfiguration:")
    print(f"  Membrane: {membrane_display_name}")
    print(f"  Feed TDS: {feed_tds} ppm")
    print(f"  Feed flow: {feed_flow} kg/s")
    print(f"  Recoveries: {recoveries}")
    
    # Create debug logger
    logger = FluxDebugLogger("specific_case_test")
    
    try:
        # Enhanced initialization
        print("\nRunning enhanced initialization...")
        stage_conditions = initialize_multistage_ro_enhanced(
            m,
            stage_recoveries=recoveries,
            feed_tds_ppm=feed_tds,
            A_w=membrane_props['A_comp'],
            verbose=True,
            debug_logger=logger
        )
        
        print("\nSUCCESS: Enhanced initialization completed without FBBT errors!")
        
        return True
        
    except Exception as e:
        print(f"\nFAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run comprehensive tests
    print("Running comprehensive tests...")
    comprehensive_success = test_eco_pro_400_initialization()
    
    # Run specific failing case
    print("\n\nRunning specific failing case test...")
    specific_success = test_specific_failing_case()
    
    # Final result
    print("\n\n" + "="*80)
    print("FINAL RESULTS")
    print("="*80)
    print(f"Comprehensive tests: {'PASSED' if comprehensive_success else 'FAILED'}")
    print(f"Specific case test: {'PASSED' if specific_success else 'FAILED'}")
    print("="*80)