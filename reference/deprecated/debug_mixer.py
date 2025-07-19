#!/usr/bin/env python3
"""
Debug mixer pressure issue.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.simulate_ro import run_ro_simulation
from pyomo.environ import value

def debug_mixer_pressure():
    """Debug mixer outlet pressure."""
    print("\n" + "="*60)
    print("DEBUGGING MIXER PRESSURE ISSUE")
    print("="*60)
    
    # Simple configuration
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
        m = results['model']
        
        # Check pressure propagation
        print("\nPRESSURE PROPAGATION:")
        print("-"*40)
        
        # Fresh feed
        fresh_p = value(m.fs.fresh_feed.outlet.pressure[0])
        print(f"Fresh feed outlet pressure: {fresh_p:.0f} Pa ({fresh_p/1e5:.2f} bar)")
        
        # Mixer inlets
        mixer_fresh_p = value(m.fs.feed_mixer.fresh.pressure[0])
        mixer_recycle_p = value(m.fs.feed_mixer.recycle.pressure[0])
        print(f"\nMixer fresh inlet pressure: {mixer_fresh_p:.0f} Pa ({mixer_fresh_p/1e5:.2f} bar)")
        print(f"Mixer recycle inlet pressure: {mixer_recycle_p:.0f} Pa ({mixer_recycle_p/1e5:.2f} bar)")
        
        # Mixer outlet
        mixer_out_p = value(m.fs.feed_mixer.outlet.pressure[0])
        print(f"\nMixer outlet pressure: {mixer_out_p:.0f} Pa ({mixer_out_p/1e5:.2f} bar)")
        
        # Pump 1 inlet
        pump1_in_p = value(m.fs.pump1.inlet.pressure[0])
        print(f"\nPump 1 inlet pressure: {pump1_in_p:.0f} Pa ({pump1_in_p/1e5:.2f} bar)")
        
        # Check if there's a factor of 100 somewhere
        print(f"\nRatio mixer_out/fresh_feed: {mixer_out_p/fresh_p:.1f}")
        print(f"Ratio pump1_in/mixer_out: {pump1_in_p/mixer_out_p:.1f}")

if __name__ == "__main__":
    debug_mixer_pressure()