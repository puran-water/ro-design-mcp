#!/usr/bin/env python3
"""
Debug energy calculations in RO simulation.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.simulate_ro import run_ro_simulation
from pyomo.environ import value
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def debug_energy_calculation():
    """Debug energy calculation for low brackish water case."""
    print("\n" + "="*60)
    print("DEBUGGING ENERGY CALCULATION")
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
        'Na_+': 2000 * 0.393,  # ~39.3% of TDS
        'Cl_-': 2000 * 0.607,  # ~60.7% of TDS
    }
    
    # Run simulation
    results = run_ro_simulation(
        configuration=configuration,
        feed_salinity_ppm=2000,
        feed_ion_composition=feed_ion_composition,
        feed_temperature_c=25.0,
        membrane_type="brackish",
        optimize_pumps=False,
        initialization_strategy="sequential"
    )
    
    if results['status'] == 'success':
        print(f"\nSimulation successful!")
        
        # Get the model
        m = results['model']
        
        # Check pump details
        print("\n" + "-"*40)
        print("PUMP ANALYSIS:")
        print("-"*40)
        
        for i in range(1, 3):
            pump = getattr(m.fs, f"pump{i}")
            
            # Get all pump variables
            inlet_pressure = value(pump.inlet.pressure[0]) / 1e5  # bar
            outlet_pressure = value(pump.outlet.pressure[0]) / 1e5  # bar
            delta_p = outlet_pressure - inlet_pressure
            
            inlet_flow = value(pump.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])  # kg/s
            work = value(pump.work_mechanical[0])  # W
            # work_isentropic = value(pump.work_isentropic[0])  # W  # Not available in basic pump model
            efficiency = value(pump.efficiency_pump[0])
            
            print(f"\nPump {i}:")
            print(f"  Inlet pressure: {inlet_pressure:.2f} bar")
            print(f"  Outlet pressure: {outlet_pressure:.2f} bar")
            print(f"  Pressure rise: {delta_p:.2f} bar")
            print(f"  Flow rate: {inlet_flow:.2f} kg/s ({inlet_flow*3.6:.2f} m³/h)")
            print(f"  Work (mechanical): {work:.0f} W ({work/1000:.2f} kW)")
            # print(f"  Work (isentropic): {work_isentropic:.0f} W")
            print(f"  Efficiency: {efficiency:.2f}")
            
            # Manual calculation check
            # Power = Flow * ΔP / (density * efficiency)
            # Power (W) = (m³/s) * (Pa) / efficiency
            flow_m3_s = inlet_flow / 1000  # kg/s to m³/s (density ~1000)
            delta_p_pa = delta_p * 1e5  # bar to Pa
            calc_power = flow_m3_s * delta_p_pa / efficiency
            print(f"  Calculated power: {calc_power:.0f} W")
            print(f"  Power ratio (actual/calc): {work/calc_power:.2f}")
        
        # Check overall results
        print("\n" + "-"*40)
        print("OVERALL RESULTS:")
        print("-"*40)
        print(f"Total power: {results['performance']['total_power_consumption_kW']:.2f} kW")
        print(f"Permeate flow: {results['performance']['total_permeate_flow_m3_h']:.2f} m³/h")
        print(f"Specific energy: {results['performance']['specific_energy_kWh_m3']:.2f} kWh/m³")
        
        # Manual calculation
        total_power_kw = results['performance']['total_power_consumption_kW']
        perm_flow_m3h = results['performance']['total_permeate_flow_m3_h']
        calc_specific = total_power_kw / perm_flow_m3h if perm_flow_m3h > 0 else 0
        print(f"\nManual specific energy: {total_power_kw:.2f} kW / {perm_flow_m3h:.2f} m³/h = {calc_specific:.2f} kWh/m³")
        
    else:
        print(f"Simulation failed: {results.get('message', 'Unknown error')}")

if __name__ == "__main__":
    debug_energy_calculation()