#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test server response format with concentrate margins.
"""

import json
import asyncio
from server import optimize_ro_configuration


async def test_server_response():
    """Test the server response format."""
    
    print("\nTesting server response with concentrate margins...")
    print("=" * 70)
    
    # Test a simple case
    result = await optimize_ro_configuration(
        feed_flow_m3h=100,
        water_recovery_fraction=0.50,
        membrane_type="brackish"
    )
    
    # Pretty print the response
    print(json.dumps(result, indent=2))
    
    # Check concentrate margins
    if result['status'] == 'success':
        print("\nConcentrate flow margins:")
        for config in result['configurations']:
            print(f"\nConfiguration: {config['array_notation']}")
            for stage in config['stages']:
                print(f"  Stage {stage['stage_number']}:")
                print(f"    Concentrate per vessel: {stage['concentrate_per_vessel_m3h']:.2f} m³/h")
                print(f"    Min required: {stage['min_concentrate_required_m3h']:.2f} m³/h")
                print(f"    Margin: {stage['concentrate_margin_m3h']:.2f} m³/h "
                      f"({stage['concentrate_margin_percent']:.1f}%)")


if __name__ == "__main__":
    asyncio.run(test_server_response())