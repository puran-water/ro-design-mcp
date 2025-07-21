#!/usr/bin/env python3
"""
Test the optimize_ro_configuration function directly.
"""

import asyncio
from utils.optimize_ro import optimize_vessel_array_configuration

async def test_direct():
    """Test the tool function directly."""
    try:
        result = optimize_vessel_array_configuration(
            feed_flow_m3h=150.0,
            water_recovery_fraction=0.75,
            membrane_type="brackish"
        )
        print("Direct call successful")
        print(f"  Status: {result.get('status')}")
        print(f"  Configurations found: {len(result.get('configurations', []))}")
        return True
    except Exception as e:
        print(f"Direct call failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_direct())
    exit(0 if success else 1)