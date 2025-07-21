#!/usr/bin/env python3
"""
Direct test of functions to ensure no stdout pollution.
"""

import sys
import io
import json

# Configure logging before any imports
from utils.logging_config import configure_mcp_logging
configure_mcp_logging()

# Now import the functions
from utils.optimize_ro import optimize_vessel_array_configuration
from utils.simulate_ro import run_ro_simulation


def capture_stdout(func, *args, **kwargs):
    """Run a function and capture stdout."""
    old_stdout = sys.stdout
    stdout_capture = io.StringIO()
    try:
        sys.stdout = stdout_capture
        result = func(*args, **kwargs)
        stdout_output = stdout_capture.getvalue()
        return result, stdout_output
    finally:
        sys.stdout = old_stdout


def test_optimize_direct():
    """Test optimize function directly."""
    print("Testing optimize_vessel_array_configuration directly...", file=sys.stderr)
    
    configs, stdout = capture_stdout(
        optimize_vessel_array_configuration,
        feed_flow_m3h=150.0,
        target_recovery=0.75,
        feed_salinity_ppm=5000,
        membrane_type="brackish"
    )
    
    if stdout:
        print(f"✗ STDOUT POLLUTION DETECTED:", file=sys.stderr)
        print(f"---\n{stdout}\n---", file=sys.stderr)
        return False
    else:
        print(f"✓ No stdout output", file=sys.stderr)
        print(f"✓ Found {len(configs)} configurations", file=sys.stderr)
        return True


def test_simulate_direct():
    """Test simulate function directly with recycle config."""
    print("\nTesting run_ro_simulation directly with recycle...", file=sys.stderr)
    
    # Create a recycle configuration
    config = {
        'array_notation': '18:8',
        'feed_flow_m3h': 152.68,
        'stage_count': 2,
        'n_stages': 2,
        'stages': [
            {
                'stage_recovery': 0.55,
                'stage_number': 1,
                'membrane_area_m2': 4682.16,
                'vessel_count': 18,
                'n_vessels': 18,
                'elements_per_vessel': 7
            },
            {
                'stage_recovery': 0.41,
                'stage_number': 2,
                'membrane_area_m2': 2080.96,
                'vessel_count': 8,
                'n_vessels': 8,
                'elements_per_vessel': 7
            }
        ],
        'recycle_info': {
            'uses_recycle': True,
            'recycle_ratio': 0.0176,
            'recycle_split_ratio': 0.0667,
            'effective_feed_flow_m3h': 152.68
        }
    }
    
    ion_comp = {
        'Na_+': 786,
        'Cl_-': 1214
    }
    
    print("Starting simulation...", file=sys.stderr)
    
    result, stdout = capture_stdout(
        run_ro_simulation,
        configuration=config,
        feed_salinity_ppm=2000,
        feed_ion_composition=ion_comp,
        feed_temperature_c=25.0,
        membrane_type="brackish",
        optimize_pumps=True
    )
    
    if stdout:
        print(f"✗ STDOUT POLLUTION DETECTED:", file=sys.stderr)
        print(f"---\n{stdout}\n---", file=sys.stderr)
        return False
    else:
        print(f"✓ No stdout output", file=sys.stderr)
        if result['status'] == 'success':
            print(f"✓ Simulation successful", file=sys.stderr)
        else:
            print(f"✗ Simulation failed: {result.get('message', 'Unknown error')}", file=sys.stderr)
        return stdout == ""


def main():
    """Run all tests."""
    print("=== Testing for stdout pollution ===\n", file=sys.stderr)
    
    test1 = test_optimize_direct()
    test2 = test_simulate_direct()
    
    if test1 and test2:
        print("\n✅ All tests passed! No stdout pollution detected.", file=sys.stderr)
        return 0
    else:
        print("\n❌ Tests failed! Functions are polluting stdout.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())