#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test concentrate flow margins in the optimization results.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.optimize_ro import optimize_vessel_array_configuration


def test_concentrate_margins():
    """Test that concentrate margins are properly calculated."""
    
    print("\nTesting concentrate flow margins...")
    print("=" * 70)
    
    # Test a case
    configs = optimize_vessel_array_configuration(
        feed_flow_m3h=100,
        target_recovery=0.50,
        feed_salinity_ppm=5000,
        membrane_type='brackish'
    )
    
    for config in configs:
        print(f"\n{config['n_stages']}-stage configuration: {config['array_notation']}")
        print(f"Total recovery: {config['total_recovery']*100:.1f}%")
        
        for stage in config['stages']:
            print(f"\n  Stage {stage['stage_number']}:")
            print(f"    Vessels: {stage['n_vessels']}")
            print(f"    Concentrate flow: {stage['concentrate_flow_m3h']:.1f} m³/h")
            print(f"    Per vessel: {stage['concentrate_per_vessel_m3h']:.2f} m³/h")
            print(f"    Min required: {stage['min_concentrate_required']:.2f} m³/h")
            margin = stage['concentrate_per_vessel_m3h'] - stage['min_concentrate_required']
            margin_pct = (stage['concentrate_per_vessel_m3h'] / stage['min_concentrate_required'] - 1) * 100
            print(f"    Margin: {margin:.2f} m³/h ({margin_pct:.1f}%)")


if __name__ == "__main__":
    test_concentrate_margins()