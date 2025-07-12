#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test to understand effective recovery requirements for 96% overall recovery.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.optimize_ro import optimize_vessel_array_configuration


def analyze_effective_recovery():
    """Analyze what effective recovery is needed for 96% overall."""
    
    print("\nAnalyzing effective recovery requirements for 96% overall recovery")
    print("=" * 70)
    
    # For 96% recovery with 150 m³/h feed
    feed_flow = 150
    target_recovery = 0.96
    
    required_permeate = feed_flow * target_recovery  # 144 m³/h
    required_disposal = feed_flow * (1 - target_recovery)  # 6 m³/h
    
    print(f"Feed flow: {feed_flow} m³/h")
    print(f"Target recovery: {target_recovery*100:.0f}%")
    print(f"Required permeate: {required_permeate} m³/h")
    print(f"Required disposal: {required_disposal} m³/h")
    
    print("\nEffective recovery scenarios:")
    print("-" * 50)
    
    # Test different effective recoveries
    for eff_recovery in [0.60, 0.65, 0.70, 0.75, 0.80, 0.85]:
        eff_feed = required_permeate / eff_recovery
        eff_concentrate = eff_feed - required_permeate
        recycle = eff_concentrate - required_disposal
        
        print(f"\nEffective recovery: {eff_recovery*100:.0f}%")
        print(f"  Effective feed: {eff_feed:.1f} m³/h")
        print(f"  Concentrate: {eff_concentrate:.1f} m³/h")
        print(f"  Recycle: {recycle:.1f} m³/h")
        print(f"  Recycle ratio: {recycle/eff_feed*100:.1f}%")
        
        # Check if single stage can achieve this
        # Single stage max recovery is about 57% at 110% flux
        if eff_recovery > 0.57:
            print("  -> Single stage CANNOT achieve this recovery")
        else:
            print("  -> Single stage might achieve this")
            
    print("\n\nConclusion:")
    print("For 96% overall recovery, we need effective recoveries > 60%")
    print("Single stage can only achieve ~57% recovery at maximum flux")
    print("Therefore, single stage is NOT viable for 96% recovery with recycle")


if __name__ == "__main__":
    analyze_effective_recovery()