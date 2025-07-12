# -*- coding: utf-8 -*-
"""
Test script for Tool 1: optimize_ro_configuration

This script tests the RO configuration optimization directly
without running the full MCP server.
"""

import asyncio
import json
from utils.optimize_ro import optimize_vessel_array_configuration


def test_basic_configuration():
    """Test basic 75% recovery configuration."""
    print("\n" + "="*60)
    print("TEST 1: Basic 75% Recovery Configuration")
    print("="*60)
    
    result = optimize_vessel_array_configuration(
        feed_flow_m3h=100,
        target_recovery=0.75,
        feed_salinity_ppm=5000,  # Placeholder
        membrane_type="brackish"
    )
    
    print(f"\nConfiguration: {result['array_notation']}")
    print(f"Total vessels: {result['total_vessels']}")
    print(f"Achieved recovery: {result['total_recovery']*100:.1f}%")
    print(f"Number of stages: {result['n_stages']}")
    
    print("\nStage details:")
    for stage in result['stages']:
        print(f"  Stage {stage['stage_number']}: {stage['n_vessels']} vessels, "
              f"flux={stage['design_flux_lmh']:.1f} LMH ({stage['flux_ratio']*100:.0f}% of target)")
    
    return result


def test_high_recovery_with_recycle():
    """Test 90% recovery with concentrate recycle."""
    print("\n" + "="*60)
    print("TEST 2: High Recovery (90%) with Recycle")
    print("="*60)
    
    result = optimize_vessel_array_configuration(
        feed_flow_m3h=100,
        target_recovery=0.90,
        feed_salinity_ppm=5000,
        membrane_type="brackish",
        allow_recycle=True,
        max_recycle_ratio=0.8
    )
    
    print(f"\nConfiguration: {result['array_notation']}")
    print(f"Total vessels: {result['total_vessels']}")
    print(f"Achieved recovery: {result['total_recovery']*100:.1f}%")
    
    if result.get('recycle_ratio', 0) > 0:
        print(f"\nRecycle information:")
        print(f"  Recycle ratio: {result['recycle_ratio']*100:.1f}%")
        print(f"  Recycle flow: {result['recycle_flow_m3h']:.1f} m³/h")
        print(f"  Disposal flow: {result['disposal_flow_m3h']:.1f} m³/h")
        print(f"  Effective feed: {result['effective_feed_flow_m3h']:.1f} m³/h")
    
    return result


def test_seawater_configuration():
    """Test seawater RO configuration."""
    print("\n" + "="*60)
    print("TEST 3: Seawater RO Configuration")
    print("="*60)
    
    result = optimize_vessel_array_configuration(
        feed_flow_m3h=1000,
        target_recovery=0.45,
        feed_salinity_ppm=35000,
        membrane_type="seawater"
    )
    
    print(f"\nConfiguration: {result['array_notation']}")
    print(f"Total vessels: {result['total_vessels']}")
    print(f"Total membrane area: {result['total_membrane_area_m2']:,.0f} m²")
    print(f"Achieved recovery: {result['total_recovery']*100:.1f}%")
    
    return result


def test_edge_cases():
    """Test edge cases and error handling."""
    print("\n" + "="*60)
    print("TEST 5: Edge Cases")
    print("="*60)
    
    # Test 1: Very high recovery (98%)
    print("\n5.1: Ultra-high recovery (98%)...")
    try:
        result = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.98,
            feed_salinity_ppm=5000,
            membrane_type="brackish",
            allow_recycle=True,
            max_recycle_ratio=0.95
        )
        print(f"  SUCCESS: {result['array_notation']}, recycle={result.get('recycle_ratio', 0)*100:.0f}%")
    except Exception as e:
        print(f"  FAILED: {str(e)}")
    
    # Test 2: Small flow
    print("\n5.2: Small flow (10 m³/h)...")
    try:
        result = optimize_vessel_array_configuration(
            feed_flow_m3h=10,
            target_recovery=0.75,
            feed_salinity_ppm=5000,
            membrane_type="brackish"
        )
        print(f"  SUCCESS: {result['array_notation']}")
    except Exception as e:
        print(f"  FAILED: {str(e)}")
    
    # Test 3: Single stage limit
    print("\n5.3: Single stage at 60% recovery...")
    try:
        result = optimize_vessel_array_configuration(
            feed_flow_m3h=100,
            target_recovery=0.60,
            feed_salinity_ppm=5000,
            membrane_type="brackish"
        )
        print(f"  SUCCESS: {result['n_stages']} stage(s), flux={result['stages'][0]['flux_ratio']*100:.0f}%")
    except Exception as e:
        print(f"  FAILED: {str(e)}")


def main():
    """Run all tests."""
    print("RO Design MCP Server - Tool 1 Testing")
    print("=====================================")
    
    # Run tests
    test_basic_configuration()
    test_high_recovery_with_recycle()
    test_seawater_configuration()
    test_edge_cases()
    
    print("\n\nAll tests completed!")
    print("="*60)


if __name__ == "__main__":
    main()