#!/usr/bin/env python3
"""
Simple test to verify flux capping logic in calculate_required_pressure.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.ro_initialization import calculate_required_pressure, validate_flux_bounds

def test_flux_capping():
    """Test that calculate_required_pressure caps pressure for high-permeability membranes."""
    
    # Test cases: (membrane_name, A_w, should_be_capped_at_30bar)
    test_cases = [
        ("BW30-400 (baseline)", 9.63e-12, False),  # Should not be capped
        ("ECO PRO-400 (high perm)", 1.60e-11, True),   # Should be capped
        ("CR100 PRO-400 (moderate)", 1.06e-11, False), # Borderline
    ]
    
    print("Testing flux capping in calculate_required_pressure")
    print("="*60)
    
    # Test parameters
    feed_tds_ppm = 2000
    target_recovery = 0.5
    
    all_passed = True
    
    for membrane_name, A_w, should_cap in test_cases:
        print(f"\nTesting {membrane_name}:")
        print(f"  A_w = {A_w:.2e} m/s/Pa")
        
        # Calculate required pressure
        pressure = calculate_required_pressure(
            feed_tds_ppm=feed_tds_ppm,
            target_recovery=target_recovery,
            A_w=A_w
        )
        
        print(f"  Calculated pressure: {pressure/1e5:.1f} bar")
        
        # Validate flux
        is_valid, flux = validate_flux_bounds(A_w, pressure)
        print(f"  Expected flux: {flux:.4f} kg/m²/s")
        print(f"  Flux validation: {'PASS' if is_valid else 'FAIL'}")
        
        # Check if capping worked as expected
        if should_cap:
            # For high permeability membranes, flux should be close to limit
            if flux > 0.025:
                print(f"  ERROR: Flux {flux:.4f} exceeds safety limit of 0.025!")
                all_passed = False
            elif flux < 0.020:
                print(f"  WARNING: Flux {flux:.4f} is too conservative")
            else:
                print(f"  GOOD: Flux is properly capped near limit")
        else:
            # For normal membranes, flux should be well below limit
            if flux > 0.025:
                print(f"  ERROR: Unexpected high flux {flux:.4f}!")
                all_passed = False
            else:
                print(f"  GOOD: Flux is within normal range")
    
    # Test extreme case
    print("\n\nTesting extreme case (very high permeability):")
    extreme_A_w = 5e-11  # 5x higher than BW30-400
    pressure = calculate_required_pressure(
        feed_tds_ppm=feed_tds_ppm,
        target_recovery=target_recovery,
        A_w=extreme_A_w
    )
    
    is_valid, flux = validate_flux_bounds(extreme_A_w, pressure)
    print(f"  A_w = {extreme_A_w:.2e} m/s/Pa")
    print(f"  Calculated pressure: {pressure/1e5:.1f} bar")
    print(f"  Expected flux: {flux:.4f} kg/m²/s")
    print(f"  Flux validation: {'PASS' if is_valid else 'FAIL'}")
    
    if flux > 0.025:
        print("  ERROR: Flux capping failed for extreme case!")
        all_passed = False
    else:
        print("  GOOD: Flux properly capped even for extreme permeability")
    
    return all_passed


def test_pressure_sweep():
    """Test flux values across pressure range for different membranes."""
    print("\n\nFlux vs Pressure for Different Membranes")
    print("="*60)
    
    membranes = [
        ("BW30-400", 9.63e-12),
        ("ECO PRO-400", 1.60e-11),
        ("CR100 PRO-400", 1.06e-11)
    ]
    
    pressures_bar = [10, 15, 20, 25, 30, 35, 40]
    
    # Print header
    print(f"{'Pressure (bar)':<15}", end="")
    for name, _ in membranes:
        print(f"{name:<20}", end="")
    print()
    print("-" * 75)
    
    # Calculate and print flux values
    for p_bar in pressures_bar:
        p_pa = p_bar * 1e5
        print(f"{p_bar:<15}", end="")
        
        for name, A_w in membranes:
            is_valid, flux = validate_flux_bounds(A_w, p_pa)
            status = f"{flux:.4f}" if is_valid else f"{flux:.4f}*"
            print(f"{status:<20}", end="")
        print()
    
    print("\n* = Exceeds flux limit of 0.025 kg/m²/s")


if __name__ == "__main__":
    print("Flux Capping Verification Test\n")
    
    # Run main test
    passed = test_flux_capping()
    
    # Show pressure sweep
    test_pressure_sweep()
    
    if passed:
        print("\n\nALL TESTS PASSED!")
        print("The calculate_required_pressure function correctly caps pressure to respect flux bounds.")
        sys.exit(0)
    else:
        print("\n\nSOME TESTS FAILED!")
        print("The flux capping logic needs further investigation.")
        sys.exit(1)