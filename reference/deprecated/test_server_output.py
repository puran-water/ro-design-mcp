#!/usr/bin/env python3
"""
Test that server output doesn't corrupt MCP protocol.

This directly tests the functions that the MCP server calls,
ensuring they don't produce unwanted stdout output.
"""

import sys
import io
import json
import logging

# Set up stderr logging before imports
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)

# Import our functions
from utils.optimize_ro import optimize_vessel_array_configuration
from utils.simulate_ro import run_ro_simulation


def capture_stdout(func, *args, **kwargs):
    """Run a function and capture any stdout output."""
    old_stdout = sys.stdout
    stdout_buffer = io.StringIO()
    try:
        sys.stdout = stdout_buffer
        result = func(*args, **kwargs)
        return result, stdout_buffer.getvalue()
    finally:
        sys.stdout = old_stdout


def test_optimize_ro_no_stdout():
    """Test that optimize_ro doesn't produce stdout."""
    print("Testing optimize_vessel_array_configuration...")
    
    result, stdout_output = capture_stdout(
        optimize_vessel_array_configuration,
        feed_flow_m3h=150.0,
        target_recovery=0.75,
        feed_salinity_ppm=5000,
        membrane_type="brackish"
    )
    
    if stdout_output:
        print(f"ERROR: Function produced stdout output:")
        print(f"---\n{stdout_output}\n---")
        return False
    else:
        print("SUCCESS: No stdout output detected")
        return True


def test_simulate_ro_no_stdout():
    """Test that simulate_ro doesn't produce stdout."""
    print("\nTesting run_ro_simulation...")
    
    # Create a simple configuration
    configuration = {
        'array_notation': '2:1',
        'feed_flow_m3h': 100,
        'stage_count': 2,
        'n_stages': 2,
        'stages': [
            {'stage_recovery': 0.5, 'stage_number': 1, 'membrane_area_m2': 260},
            {'stage_recovery': 0.4, 'stage_number': 2, 'membrane_area_m2': 260}
        ],
        'recycle_info': {
            'uses_recycle': False,
            'recycle_ratio': 0,
            'recycle_split_ratio': 0
        },
        'feed_salinity_ppm': 2000
    }
    
    # Simple ion composition
    feed_ion_composition = {
        'Na_+': 2000 * 0.393,
        'Cl_-': 2000 * 0.607,
    }
    
    result, stdout_output = capture_stdout(
        run_ro_simulation,
        configuration=configuration,
        feed_salinity_ppm=2000,
        feed_ion_composition=feed_ion_composition,
        feed_temperature_c=25.0,
        membrane_type="brackish",
        optimize_pumps=False
    )
    
    if stdout_output:
        print(f"ERROR: Function produced stdout output:")
        print(f"---\n{stdout_output}\n---")
        return False
    else:
        print("SUCCESS: No stdout output detected")
        return True


def main():
    """Run all tests."""
    print("=== Testing for stdout output that would corrupt MCP protocol ===\n")
    
    tests_passed = 0
    tests_total = 2
    
    # Test 1
    if test_optimize_ro_no_stdout():
        tests_passed += 1
    
    # Test 2
    if test_simulate_ro_no_stdout():
        tests_passed += 1
    
    print(f"\n=== Results: {tests_passed}/{tests_total} tests passed ===")
    
    if tests_passed == tests_total:
        print("\nAll tests passed! The server should work correctly with MCP clients.")
        return 0
    else:
        print("\nSome tests failed. Check the stdout output above for issues.")
        return 1


if __name__ == "__main__":
    sys.exit(main())