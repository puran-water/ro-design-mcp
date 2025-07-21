#!/usr/bin/env python3
"""
Test direct_simulate_ro.py with MCAS property package for ion composition.
This is a gate test - if this doesn't work, we need to fix MCAS support first.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.optimize_ro import optimize_vessel_array_configuration
from utils.membrane_properties_handler import get_membrane_properties
from direct_simulate_ro import run_direct_simulation


def test_direct_mcas():
    """Test direct simulation with ion composition (should fail currently)."""
    
    print("="*70)
    print("MCAS DIRECT SIMULATION TEST")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Test conditions - same as successful workflow
    feed_flow = 150  # m³/h
    recovery = 0.75  # 75%
    feed_tds = 2000  # ppm
    feed_temp = 25.0  # °C
    
    # Ion composition for 2000 ppm NaCl
    ion_composition = {
        "Na+": 786,    # mg/L
        "Cl-": 1214    # mg/L
    }
    
    print(f"\nTest Conditions:")
    print(f"  Feed flow: {feed_flow} m³/h")
    print(f"  Feed TDS: {feed_tds} ppm")
    print(f"  Ion composition: {ion_composition}")
    print(f"  Target recovery: {recovery*100:.0f}%")
    
    # Test with different membrane types
    membrane_types = [
        ('brackish', 'Brackish (BW30-400)'),
        ('eco_pro_400', 'ECO PRO-400')
    ]
    
    results = []
    
    for mem_type, display_name in membrane_types:
        print(f"\n{'='*50}")
        print(f"Testing: {display_name}")
        print(f"{'='*50}")
        
        try:
            # Step 1: Get configuration
            configurations = optimize_vessel_array_configuration(
                feed_flow_m3h=feed_flow,
                target_recovery=recovery,
                feed_salinity_ppm=feed_tds,
                membrane_type=mem_type,
                allow_recycle=False
            )
            
            if not configurations:
                print("No configuration found!")
                continue
            
            config = configurations[0]
            print(f"Configuration: {config['array_notation']}")
            
            # Format configuration
            formatted_config = {
                'success': True,
                'stage_count': config['n_stages'],
                'feed_flow_m3h': config['feed_flow_m3h'],
                'stages': []
            }
            
            for stage in config['stages']:
                formatted_config['stages'].append({
                    'stage_number': stage['stage_number'],
                    'membrane_area_m2': stage['membrane_area_m2'],
                    'stage_recovery': stage['stage_recovery'],
                    'vessels': stage['n_vessels']
                })
            
            # Step 2: Try direct simulation with ion composition
            print("\nTesting direct simulation with MCAS...")
            
            result = run_direct_simulation(
                configuration=formatted_config,
                feed_salinity_ppm=feed_tds,
                feed_temperature_c=feed_temp,
                membrane_type=mem_type,
                membrane_properties=None,
                optimize_pumps=True,
                feed_ion_composition=ion_composition  # This should trigger MCAS
            )
            
            if result['status'] == 'success':
                print("SUCCESS! Direct simulation with MCAS worked!")
                print(f"Total recovery: {result['performance']['total_recovery']:.1%}")
                print(f"Specific energy: {result['economics']['specific_energy_kwh_m3']:.2f} kWh/m³")
                
                # Check if ion analysis is present
                if 'ion_analysis' in result:
                    print("\nIon rejection results:")
                    for ion, data in result['ion_analysis'].items():
                        if isinstance(data, dict) and 'rejection' in data:
                            print(f"  {ion}: {data['rejection']:.1%} rejection")
                
                results.append({
                    'membrane': display_name,
                    'status': 'SUCCESS',
                    'recovery': result['performance']['total_recovery'],
                    'has_ion_analysis': 'ion_analysis' in result
                })
            else:
                print(f"Simulation failed: {result.get('message', 'Unknown error')}")
                results.append({
                    'membrane': display_name,
                    'status': 'FAILED',
                    'error': result.get('message', 'Unknown')
                })
                
        except NotImplementedError as e:
            print(f"NOT IMPLEMENTED: {str(e)}")
            results.append({
                'membrane': display_name,
                'status': 'NOT_IMPLEMENTED',
                'error': str(e)
            })
        except Exception as e:
            print(f"ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            results.append({
                'membrane': display_name,
                'status': 'ERROR',
                'error': str(e)
            })
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    for result in results:
        print(f"\n{result['membrane']}:")
        print(f"  Status: {result['status']}")
        if result['status'] == 'SUCCESS':
            print(f"  Recovery: {result['recovery']:.1%}")
            print(f"  Has ion analysis: {result['has_ion_analysis']}")
        else:
            print(f"  Error: {result.get('error', 'N/A')}")
    
    # Gate decision
    print("\n" + "="*70)
    success_count = sum(1 for r in results if r['status'] == 'SUCCESS')
    if success_count == len(results):
        print("GATE PASSED: All tests successful! Ready to proceed with refactoring.")
    elif any(r['status'] == 'NOT_IMPLEMENTED' for r in results):
        print("GATE BLOCKED: MCAS support not implemented in direct route.")
        print("Need to add MCAS functionality before proceeding.")
    else:
        print("GATE FAILED: Some tests failed. Need to fix issues first.")
    print("="*70)


if __name__ == "__main__":
    test_direct_mcas()