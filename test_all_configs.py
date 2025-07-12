#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test to force all stage configurations and see what's possible.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.optimize_ro import optimize_vessel_array_configuration


def test_all_stage_configs():
    """Force different stage configurations to see what's achievable."""
    
    print("\nForcing different stage configurations...")
    print("=" * 70)
    
    # Test 75% recovery with different max stages
    target_recovery = 0.75
    feed_flow = 100
    
    for max_stages in [1, 2, 3]:
        print(f"\nMax stages: {max_stages}")
        
        try:
            configs = optimize_vessel_array_configuration(
                feed_flow_m3h=feed_flow,
                target_recovery=target_recovery,
                feed_salinity_ppm=5000,
                membrane_type='brackish',
                allow_recycle=True,
                max_stages=max_stages
            )
            
            if configs:
                for config in configs:
                    print(f"  {config['n_stages']}-stage: {config['array_notation']}, "
                          f"recovery={config['total_recovery']*100:.1f}%, "
                          f"recycle={config.get('recycle_ratio', 0)*100:.0f}%")
            else:
                print(f"  No viable configuration")
                
        except Exception as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    test_all_stage_configs()