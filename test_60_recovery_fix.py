#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test the fix for 60% recovery overshooting issue.
"""

import sys
import os
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.optimize_ro import optimize_vessel_array_configuration

# Set up logging to see optimization details
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')


def test_60_recovery():
    """Test that 60% recovery is achieved precisely."""
    
    print("\nTesting 60% recovery with global flux optimization fix...")
    print("=" * 70)
    
    configs = optimize_vessel_array_configuration(
        feed_flow_m3h=150,
        target_recovery=0.60,
        feed_salinity_ppm=5000,
        membrane_type='brackish',
        allow_recycle=True,
        max_recycle_ratio=0.9
    )
    
    print(f"\nFound {len(configs)} configuration(s):")
    
    for i, config in enumerate(configs):
        print(f"\nConfiguration {i+1}:")
        print(f"  Stages: {config['n_stages']}")
        print(f"  Array: {config['array_notation']}")
        print(f"  Target recovery: {config['target_recovery']*100:.1f}%")
        print(f"  Achieved recovery: {config['total_recovery']*100:.1f}%")
        print(f"  Recovery error: {config['recovery_error']*100:.2f}%")
        print(f"  Within 2% tolerance: {'YES' if config['recovery_error'] <= 0.02 else 'NO'}")
        
        # Show flux details
        print("\n  Flux details:")
        for stage in config['stages']:
            print(f"    Stage {stage['stage_number']}: "
                  f"{stage['design_flux_lmh']:.1f} LMH "
                  f"({stage['flux_ratio']*100:.1f}% of target)")
        
        # Highlight if overshooting
        if config['total_recovery'] > 0.62:  # 60% + 2% tolerance
            print("\n  WARNING: Still overshooting target!")


if __name__ == "__main__":
    test_60_recovery()