#!/usr/bin/env python3
"""
Test energy optimization with different settings.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.simulate_ro import run_ro_simulation

def test_energy_optimization():
    """Test different optimization settings."""
    print("\n" + "="*60)
    print("TESTING ENERGY OPTIMIZATION")
    print("="*60)
    
    # Simple 2-stage configuration
    configuration = {
        'array_notation': '2:1',
        'feed_flow_m3h': 100,
        'stage_count': 2,
        'n_stages': 2,
        'stages': [
            {'stage_recovery': 0.5, 'stage_number': 1, 'membrane_area_m2': 260},
            {'stage_recovery': 0.4, 'stage_number': 2, 'membrane_area_m2': 260}
        ],
        'recycle_info': {
            'uses_recycle': False,
            'recycle_ratio': 0,
            'recycle_split_ratio': 0
        },
        'feed_salinity_ppm': 2000
    }
    
    # Simple ion composition
    feed_ion_composition = {
        'Na_+': 2000 * 0.393,
        'Cl_-': 2000 * 0.607,
    }
    
    # Test both with and without pump optimization
    for optimize_pumps in [False, True]:
        print(f"\n\nTesting with optimize_pumps={optimize_pumps}")
        print("-"*40)
        
        results = run_ro_simulation(
            configuration=configuration,
            feed_salinity_ppm=2000,
            feed_ion_composition=feed_ion_composition,
            feed_temperature_c=25.0,
            membrane_type="brackish",
            optimize_pumps=optimize_pumps,
            initialization_strategy="sequential"
        )
        
        if results['status'] == 'success':
            print(f"Simulation successful!")
            
            # Get the model
            m = results['model']
            
            # Print results
            print(f"\nSystem recovery: {results['performance']['system_recovery']*100:.1f}%")
            print(f"Permeate flow: {results['performance']['total_permeate_flow_m3_h']:.2f} m³/h")
            print(f"Total power: {results['performance']['total_power_consumption_kW']:.2f} kW")
            print(f"Specific energy: {results['performance']['specific_energy_kWh_m3']:.2f} kWh/m³")
            print(f"Permeate TDS: {results['performance']['total_permeate_tds_mg_l']:.0f} mg/L")
            
            # Check actual stage recoveries
            from pyomo.environ import value
            print("\nStage recoveries:")
            for i in range(1, 3):
                ro = getattr(m.fs, f"ro_stage{i}")
                recovery = value(ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'])
                print(f"  Stage {i}: {recovery:.3f}")
                
            # Check pump pressures
            print("\nPump pressures:")
            for i in range(1, 3):
                pump = getattr(m.fs, f"pump{i}")
                outlet_p = value(pump.outlet.pressure[0]) / 1e5
                print(f"  Pump {i}: {outlet_p:.1f} bar")
        else:
            print(f"Simulation failed: {results.get('message', 'Unknown error')}")

if __name__ == "__main__":
    test_energy_optimization()
