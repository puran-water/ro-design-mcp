#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for multi-configuration RO optimization.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.optimize_ro import optimize_vessel_array_configuration


def test_multi_config():
    """Test various recovery scenarios to verify multiple configurations are returned."""
    
    test_cases = [
        # (feed_flow, recovery, description)
        (100, 0.50, "50% recovery - should find 1 and 2 stage options"),
        (100, 0.75, "75% recovery - should find 2 and 3 stage options"),
        (150, 0.96, "96% recovery - should find recycle options with different stages"),
    ]
    
    # Set logging level for debugging
    import logging
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
    
    for feed_flow, recovery, description in test_cases:
        print(f"\n{'='*70}")
        print(f"TEST: {description}")
        print(f"Feed: {feed_flow} m³/h, Target Recovery: {recovery*100:.0f}%")
        print(f"{'='*70}")
        
        try:
            # Call the optimization function
            configs = optimize_vessel_array_configuration(
                feed_flow_m3h=feed_flow,
                target_recovery=recovery,
                feed_salinity_ppm=5000,
                membrane_type='brackish',
                allow_recycle=True,
                max_recycle_ratio=0.9
            )
            
            print(f"\nFound {len(configs)} viable configuration(s):")
            print("\nStage | Array     | Recovery | Recycle | Flux Range | Area (m²)")
            print("-" * 65)
            
            for config in configs:
                flux_range = f"{config['min_flux_ratio']*100:.0f}-{config['max_flux_ratio']*100:.0f}%"
                recycle_str = f"{config['recycle_ratio']*100:.0f}%" if config.get('recycle_ratio', 0) > 0 else "No"
                
                print(f"{config['n_stages']:5d} | {config['array_notation']:9s} | "
                      f"{config['total_recovery']*100:7.1f}% | {recycle_str:7s} | "
                      f"{flux_range:10s} | {config['total_membrane_area_m2']:8.0f}")
                
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    test_multi_config()