#!/usr/bin/env python3
"""
Debug configuration output.
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.optimize_ro import optimize_vessel_array_configuration
from utils.membrane_properties_handler import get_membrane_properties


def main():
    """Debug configuration output."""
    
    # Test parameters
    membrane_type = 'eco_pro_400'
    feed_flow = 150  # m³/h
    recovery = 0.75  # 75%
    feed_tds = 5000  # ppm
    
    print("Running configuration...")
    
    # Call optimization
    result = optimize_vessel_array_configuration(
        feed_flow_m3h=feed_flow,
        target_recovery=recovery,
        feed_salinity_ppm=feed_tds,
        membrane_type=membrane_type,
        allow_recycle=True,
        max_recycle_ratio=0.9
    )
    
    print(f"\nResult type: {type(result)}")
    
    if isinstance(result, list):
        print(f"Number of configurations: {len(result)}")
        if result:
            print(f"\nFirst configuration keys: {list(result[0].keys())}")
            print(f"\nFirst configuration summary:")
            config = result[0]
            print(f"  Recovery: {config.get('recovery', 'N/A')}")
            print(f"  Stages: {len(config.get('stages', []))}")
            print(f"  Has recycle: {config.get('has_recycle', False)}")
    elif isinstance(result, dict):
        print(f"Configuration keys: {list(result.keys())}")
    else:
        print("Unexpected result type!")
    
    # Print full result for inspection
    print(f"\nFull result (first 500 chars):")
    result_str = str(result)
    print(result_str[:500])


if __name__ == "__main__":
    main()