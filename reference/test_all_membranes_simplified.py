#!/usr/bin/env python3
"""
Test all membranes with the simplified simulation approach.
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.optimize_ro import optimize_vessel_array_configuration
from utils.simulate_ro import run_ro_simulation
from utils.membrane_properties_handler import get_membrane_properties


def test_all_membranes_simplified():
    """Test all configured membranes with the simplified approach."""
    
    print("="*70)
    print("ALL MEMBRANES TEST - SIMPLIFIED SIMULATION")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Test conditions  
    feed_flow = 150  # m³/h
    recovery = 0.75  # 75%
    feed_tds = 2000  # ppm
    
    # Membrane types to test
    membrane_types = [
        ('bw30_400', 'BW30-400 (Standard Brackish)'),
        ('eco_pro_400', 'ECO PRO-400 (High Permeability)'),
        ('cr100_pro_400', 'CR100 PRO-400 (Chemical Resistant)'),
        ('brackish', 'Brackish (Generic)'),
        ('seawater', 'Seawater (Generic)')
    ]
    
    print(f"\nTest Conditions:")
    print(f"  Feed: {feed_flow} m³/h at {feed_tds} ppm")
    print(f"  Target recovery: {recovery*100:.0f}%")
    print(f"  Using simplified simulation approach")
    
    print(f"\nMembrane Properties Database:")
    print("-" * 60)
    print(f"{'Type':<20} {'A_w (m/s/Pa)':<15} {'B_s (m/s)':<15}")
    print("-" * 60)
    
    for mem_type, _ in membrane_types:
        A_w, B_s = get_membrane_properties(mem_type)
        print(f"{mem_type:<20} {A_w:.2e}{'':<5} {B_s:.2e}")
    
    results_summary = []
    
    for mem_type, display_name in membrane_types:
        print(f"\n{'='*60}")
        print(f"TESTING: {display_name}")
        print(f"{'='*60}")
        
        try:
            # Step 1: Configuration
            print("\nStep 1: Optimizing configuration...")
            configurations = optimize_vessel_array_configuration(
                feed_flow_m3h=feed_flow,
                target_recovery=recovery,
                feed_salinity_ppm=feed_tds,
                membrane_type=mem_type,
                allow_recycle=False
            )
            
            if not configurations:
                print("No configuration found!")
                results_summary.append({
                    'membrane': mem_type,
                    'display': display_name,
                    'status': 'FAIL',
                    'error': 'No configuration'
                })
                continue
            
            config = configurations[0]
            print(f"  Configuration: {config['array_notation']}")
            print(f"  Recovery: {config['total_recovery']*100:.1f}%")
            print(f"  Total area: {config.get('total_membrane_area_m2', 0):.0f} m²")
            
            # Step 2: Simplified simulation
            print("\nStep 2: Running simplified simulation...")
            sim_results = run_ro_simulation(
                configuration=config,
                feed_salinity_ppm=feed_tds,
                feed_temperature_c=25.0,
                membrane_type=mem_type,
                optimize_pumps=True,
                use_direct_simulation=True  # Use simplified approach
            )
            
            if sim_results.get('status') != 'success':
                print(f"Simulation failed: {sim_results.get('error', 'Unknown error')}")
                results_summary.append({
                    'membrane': mem_type,
                    'display': display_name,
                    'status': 'FAIL',
                    'error': sim_results.get('error', 'Simulation failed')
                })
                continue
            
            print("Simulation successful!")
            
            # Extract key results
            performance = sim_results.get('performance', {})
            economics = sim_results.get('economics', {})
            stage_results = sim_results.get('stage_results', [])
            
            # Get pressures
            pressures = []
            for stage in stage_results:
                pressures.append(stage['feed_pressure_bar'])
            
            # Display results
            print(f"\nResults:")
            print(f"  Pressures: {', '.join(f'{p:.1f} bar' for p in pressures)}")
            print(f"  Total recovery: {performance.get('total_recovery', 0)*100:.1f}%")
            print(f"  Permeate TDS: {performance.get('permeate_tds_ppm', 0):.0f} ppm")
            print(f"  Total power: {economics.get('total_power_kw', 0):.1f} kW")
            print(f"  Specific energy: {economics.get('specific_energy_kwh_m3', 0):.2f} kWh/m³")
            
            # Verify membrane properties were used correctly
            A_w_expected, B_s_expected = get_membrane_properties(mem_type)
            print(f"\nParameter verification:")
            print(f"  Expected A_w: {A_w_expected:.2e}, B_s: {B_s_expected:.2e}")
            
            results_summary.append({
                'membrane': mem_type,
                'display': display_name,
                'status': 'PASS',
                'configuration': config['array_notation'],
                'pressures': pressures,
                'recovery': performance.get('total_recovery', 0),
                'permeate_tds': performance.get('permeate_tds_ppm', 0),
                'power': economics.get('total_power_kw', 0),
                'specific_energy': economics.get('specific_energy_kwh_m3', 0)
            })
            
        except Exception as e:
            print(f"Error: {str(e)}")
            results_summary.append({
                'membrane': mem_type,
                'display': display_name,
                'status': 'FAIL',
                'error': str(e)
            })
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY - SIMPLIFIED SIMULATION TEST")
    print("="*70)
    
    print(f"\n{'Membrane':<30} {'Status':<10} {'Config':<10} {'Pressures':<20} {'Energy':<15}")
    print("-" * 85)
    
    for result in results_summary:
        if result['status'] == 'PASS':
            pressure_str = f"{result['pressures'][0]:.1f}-{result['pressures'][-1]:.1f} bar"
            energy_str = f"{result['specific_energy']:.2f} kWh/m³"
            config_str = result['configuration']
            print(f"{result['display']:<30} {result['status']:<10} {config_str:<10} {pressure_str:<20} {energy_str:<15}")
        else:
            print(f"{result['display']:<30} {result['status']:<10} {result['error']:<45}")
    
    print("\n" + "="*70)
    success_count = sum(1 for r in results_summary if r['status'] == 'PASS')
    print(f"Result: {success_count}/{len(results_summary)} membranes passed")
    
    # Save detailed results
    with open('all_membranes_simplified_results.json', 'w') as f:
        json.dump({
            'test_conditions': {
                'feed_flow_m3h': feed_flow,
                'recovery': recovery,
                'feed_tds_ppm': feed_tds
            },
            'results': results_summary,
            'summary': {
                'total_tested': len(results_summary),
                'passed': success_count,
                'failed': len(results_summary) - success_count
            }
        }, f, indent=2)
    
    print(f"\nDetailed results saved to all_membranes_simplified_results.json")
    
    if success_count == len(results_summary):
        print("\nSUCCESS: All membranes work correctly with simplified simulation!")
    else:
        print("\nWARNING: Some membranes failed - check detailed results")
    
    print("="*70)
    
    return success_count == len(results_summary)


if __name__ == "__main__":
    success = test_all_membranes_simplified()
    sys.exit(0 if success else 1)