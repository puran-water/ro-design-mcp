#!/usr/bin/env python3
"""
Test direct simulation for 2000 ppm feed without ion composition.
Focus on getting a working solution first.
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from direct_simulate_ro import run_direct_simulation


def test_2000ppm():
    """Test simulation with 2000 ppm feed."""
    
    print("Testing 2000 ppm NaCl Feed Simulation")
    print("="*50)
    
    # Configuration from optimization tool
    # Based on the output above, both membranes gave same configuration
    config = {
        'success': True,
        'stage_count': 2,
        'feed_flow_m3h': 150,
        'stages': [
            {
                'stage_number': 1,
                'membrane_area_m2': 4422,
                'stage_recovery': 0.558,
                'vessels': 17
            },
            {
                'stage_number': 2,
                'membrane_area_m2': 2081,
                'stage_recovery': 0.444,
                'vessels': 8
            }
        ]
    }
    
    # Test parameters
    feed_salinity_ppm = 2000
    feed_temperature_c = 25.0
    
    # Test with ECO PRO-400 (high permeability)
    print("\nTesting ECO PRO-400 membrane...")
    print("-" * 50)
    
    result = run_direct_simulation(
        configuration=config,
        feed_salinity_ppm=feed_salinity_ppm,
        feed_temperature_c=feed_temperature_c,
        membrane_type='eco_pro_400',
        optimize_pumps=False
    )
    
    print(f"\nResult: {result['status']}")
    if result['status'] == 'success':
        perf = result['performance']
        print(f"\nPerformance:")
        print(f"  Total recovery: {perf['total_recovery']:.1%}")
        print(f"  Permeate flow: {perf['permeate_flow_m3h']:.1f} m³/h")
        print(f"  Permeate TDS: {perf['permeate_tds_ppm']:.0f} ppm")
        print(f"  Specific energy: {result['economics']['specific_energy_kwh_m3']:.2f} kWh/m³")
        
        print(f"\nStage Results:")
        for stage in result['stage_results']:
            print(f"  Stage {stage['stage_number']}:")
            print(f"    Pressure: {stage['feed_pressure_bar']:.1f} bar")
            print(f"    Recovery: {stage['recovery']:.1%}")
            print(f"    Permeate TDS: {stage['permeate_tds_ppm']:.0f} ppm")
    else:
        print(f"Error: {result.get('message', 'Unknown error')}")
        if 'traceback' in result:
            print("\nTraceback:")
            print(result['traceback'])


if __name__ == "__main__":
    test_2000ppm()