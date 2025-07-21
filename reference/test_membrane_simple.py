#!/usr/bin/env python
"""
Simple test of membrane properties handler.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import just the handler
from utils.membrane_properties_handler import get_membrane_properties


def test_membrane_handler():
    """Test that different membrane types return different properties."""
    
    print("Testing membrane properties handler...")
    print("="*60)
    
    # Test different membrane types
    membrane_types = ["brackish", "seawater", "bw30_400", "eco_pro_400", "cr100_pro_400"]
    
    results = {}
    
    for membrane_type in membrane_types:
        try:
            A_w, B_s = get_membrane_properties(membrane_type)
            results[membrane_type] = (A_w, B_s)
            print(f"{membrane_type:15} A_w = {A_w:.2e} m/s/Pa, B_s = {B_s:.2e} m/s")
        except Exception as e:
            print(f"{membrane_type:15} ERROR: {str(e)}")
            results[membrane_type] = None
    
    # Test custom properties
    print("\nTesting custom properties...")
    custom_props = {"A_w": 2.0e-11, "B_s": 3.0e-8}
    try:
        A_w, B_s = get_membrane_properties("brackish", custom_props)
        print(f"custom:         A_w = {A_w:.2e} m/s/Pa, B_s = {B_s:.2e} m/s")
        results["custom"] = (A_w, B_s)
    except Exception as e:
        print(f"custom:         ERROR: {str(e)}")
    
    # Check for variations
    print("\n" + "="*60)
    print("ANALYSIS")
    print("="*60)
    
    unique_values = set(results.values())
    unique_values.discard(None)  # Remove None values
    
    if len(unique_values) == 1:
        print("ERROR: All membrane types returned the SAME properties!")
        print("This indicates a problem with the configuration loading.")
    else:
        print(f"SUCCESS: Found {len(unique_values)} different property sets")
        
        # Show differences
        if "bw30_400" in results and results["bw30_400"]:
            baseline_A_w, baseline_B_s = results["bw30_400"]
            print(f"\nComparison to BW30-400 baseline (A_w = {baseline_A_w:.2e}):")
            
            for membrane_type, props in results.items():
                if props and membrane_type != "bw30_400":
                    A_w, B_s = props
                    A_w_ratio = A_w / baseline_A_w
                    B_s_ratio = B_s / baseline_B_s
                    print(f"  {membrane_type:15} A_w ratio = {A_w_ratio:.2f}x, B_s ratio = {B_s_ratio:.2f}x")
    
    # Expected values from config
    print("\n" + "="*60)
    print("EXPECTED VALUES (from system_defaults.yaml)")
    print("="*60)
    print("bw30_400:       A_w = 9.63e-12 m/s/Pa, B_s = 5.58e-08 m/s")
    print("eco_pro_400:    A_w = 1.60e-11 m/s/Pa, B_s = 4.24e-08 m/s")
    print("cr100_pro_400:  A_w = 1.06e-11 m/s/Pa, B_s = 4.16e-08 m/s")
    print("seawater:       A_w = 3.00e-12 m/s/Pa, B_s = 1.50e-08 m/s")
    
    return results


if __name__ == "__main__":
    print("Simple Membrane Properties Test")
    print("="*60)
    
    # Run the test
    results = test_membrane_handler()
    
    print("\nTest complete!")