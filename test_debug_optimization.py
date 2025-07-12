#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug the global flux optimization convergence.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Monkey patch to add detailed logging
from utils import optimize_ro


# Replace the fine_tune_flux_globally function with a debug version
original_func = optimize_ro.fine_tune_flux_globally


def debug_fine_tune_flux_globally(stages_config, target_recovery_param, tolerance_param, base_feed_flow):
    """Debug version with detailed logging."""
    print(f"\n=== ENTERING GLOBAL FLUX OPTIMIZATION ===")
    print(f"Target recovery: {target_recovery_param*100:.1f}%")
    print(f"Tolerance: {tolerance_param*100:.1f}%")
    
    # Call original function but add our own logging
    current_stages = stages_config['stages'].copy()
    
    # Initial state
    total_permeate = sum(s['permeate_flow'] for s in current_stages)
    current_recovery = total_permeate / base_feed_flow
    print(f"Initial recovery: {current_recovery*100:.1f}%")
    print(f"Need to reduce by: {(current_recovery - target_recovery_param)*100:.1f}%")
    
    # Check flux limits
    print("\nFlux limits:")
    print(f"  Lower limit: 85% of target")
    print(f"  Upper limit: 110% of target")
    
    print("\nInitial flux ratios:")
    for i, stage in enumerate(current_stages):
        print(f"  Stage {i+1}: {stage['flux_ratio']*100:.1f}% (room to reduce: {(stage['flux_ratio']-0.85)*100:.1f}%)")
    
    # Call original
    result = original_func(stages_config, target_recovery_param, tolerance_param, base_feed_flow)
    
    # Final state
    final_stages = result['stages']
    final_recovery = result['total_recovery']
    print(f"\nFinal recovery: {final_recovery*100:.1f}%")
    print(f"Remaining error: {(final_recovery - target_recovery_param)*100:.1f}%")
    
    print("\nFinal flux ratios:")
    for i, stage in enumerate(final_stages):
        print(f"  Stage {i+1}: {stage['flux_ratio']*100:.1f}%")
    
    print("=== EXITING GLOBAL FLUX OPTIMIZATION ===\n")
    
    return result


# Monkey patch
optimize_ro.fine_tune_flux_globally = debug_fine_tune_flux_globally


def test_60_recovery_debug():
    """Test 60% recovery with detailed debugging."""
    
    print("\nTesting 60% recovery optimization convergence...")
    print("=" * 70)
    
    from utils.optimize_ro import optimize_vessel_array_configuration
    
    configs = optimize_vessel_array_configuration(
        feed_flow_m3h=150,
        target_recovery=0.60,
        feed_salinity_ppm=5000,
        membrane_type='brackish',
        allow_recycle=False  # Disable recycle to focus on the issue
    )
    
    print(f"\nFinal result: {len(configs)} configuration(s)")
    for config in configs:
        print(f"  {config['n_stages']}-stage: recovery={config['total_recovery']*100:.1f}%")


if __name__ == "__main__":
    test_60_recovery_debug()