#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test what recovery is achievable with single stage.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.optimize_ro import optimize_vessel_array_configuration


def test_single_stage():
    """Test various recovery targets to see what single stage can achieve."""
    
    print("\nTesting single-stage achievable recoveries...")
    print("=" * 60)
    
    # Test different recovery targets
    for recovery in [0.40, 0.45, 0.50, 0.55, 0.60]:
        print(f"\nTarget: {recovery*100:.0f}% recovery")
        
        try:
            # Force single stage by setting max_stages=1
            configs = optimize_vessel_array_configuration(
                feed_flow_m3h=100,
                target_recovery=recovery,
                feed_salinity_ppm=5000,
                membrane_type='brackish',
                allow_recycle=False,
                max_stages=1  # Force single stage only
            )
            
            if configs:
                for config in configs:
                    print(f"  Found: {config['n_stages']} stage, "
                          f"{config['array_notation']}, "
                          f"recovery={config['total_recovery']*100:.1f}%, "
                          f"flux={config['stages'][0]['design_flux_lmh']:.1f} LMH "
                          f"({config['stages'][0]['flux_ratio']*100:.0f}% of target)")
            else:
                print(f"  No viable single-stage configuration")
                
        except Exception as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    test_single_stage()