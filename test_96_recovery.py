#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Focused test for 96% recovery to understand stage configurations.
"""

import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.optimize_ro import optimize_vessel_array_configuration

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def test_96_recovery():
    """Test 96% recovery in detail."""
    
    print("\nTesting 96% recovery with recycle...")
    print("=" * 70)
    
    configs = optimize_vessel_array_configuration(
        feed_flow_m3h=150,
        target_recovery=0.96,
        feed_salinity_ppm=5000,
        membrane_type='brackish',
        allow_recycle=True,
        max_recycle_ratio=0.9
    )
    
    print(f"\nFound {len(configs)} configuration(s):")
    for config in configs:
        print(f"\n{config['n_stages']}-stage configuration:")
        print(f"  Array: {config['array_notation']}")
        print(f"  Recovery: {config['total_recovery']*100:.1f}%")
        print(f"  Recycle: {config.get('recycle_ratio', 0)*100:.0f}%")
        print(f"  Total area: {config['total_membrane_area_m2']:.0f} m²")
        
        # Check if this meets target
        if config['meets_target_recovery']:
            print("  [OK] Meets target recovery")
        else:
            print("  [X] Does not meet target recovery")
        
        # Show stage details
        for stage in config['stages']:
            print(f"\n  Stage {stage['stage_number']}:")
            print(f"    Vessels: {stage['n_vessels']}")
            print(f"    Flux: {stage['design_flux_lmh']:.1f} LMH ({stage['flux_ratio']*100:.0f}%)")
            print(f"    Recovery: {stage['stage_recovery']*100:.1f}%")


if __name__ == "__main__":
    test_96_recovery()