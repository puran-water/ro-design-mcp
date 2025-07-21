#!/usr/bin/env python3
"""
Test stage pressure calculation directly.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.stage_pressure_calculation import (
    calculate_stage_pressure_with_flux_limit,
    calculate_multistage_pressures
)
from utils.membrane_properties_handler import get_membrane_properties


def main():
    """Test stage pressure calculations."""
    
    print("\n" + "="*60)
    print("TESTING STAGE PRESSURE CALCULATIONS")
    print("="*60)
    
    # Get ECO PRO-400 properties
    A_w, B_s = get_membrane_properties('eco_pro_400')
    print(f"\nMembrane: ECO PRO-400")
    print(f"A_w: {A_w:.2e} m/s/Pa")
    print(f"B_s: {B_s:.2e} m/s")
    
    # Test 1: Single stage calculation
    print("\n" + "-"*40)
    print("Test 1: Single stage with 1000 ppm TDS")
    print("-"*40)
    
    conditions = calculate_stage_pressure_with_flux_limit(
        stage_number=1,
        inlet_tds_ppm=1000,
        stage_recovery=0.5,
        A_w=A_w,
        B_s=B_s
    )
    
    print(f"Inlet TDS: {conditions.inlet_tds_ppm:.0f} ppm")
    print(f"Outlet TDS: {conditions.outlet_tds_ppm:.0f} ppm")
    print(f"Max pressure: {conditions.max_pressure_bar:.1f} bar")
    print(f"Recommended: {conditions.recommended_pressure_bar:.1f} bar")
    print(f"Expected flux: {conditions.expected_flux_kg_m2_s:.4f} kg/m²/s")
    print(f"Flux margin: {conditions.flux_margin_percent:.1f}%")
    
    # Test 2: Multi-stage system
    print("\n" + "-"*40)
    print("Test 2: 3-stage system with 1000 ppm feed")
    print("-"*40)
    
    stage_conditions = calculate_multistage_pressures(
        feed_tds_ppm=1000,
        stage_recoveries=[0.5, 0.5, 0.5],
        A_w=A_w,
        B_s=B_s,
        verbose=True
    )
    
    # Test 3: High TDS case
    print("\n" + "-"*40)
    print("Test 3: Single stage with 35000 ppm TDS")
    print("-"*40)
    
    conditions = calculate_stage_pressure_with_flux_limit(
        stage_number=1,
        inlet_tds_ppm=35000,
        stage_recovery=0.45,
        A_w=A_w,
        B_s=B_s
    )
    
    print(f"Inlet TDS: {conditions.inlet_tds_ppm:.0f} ppm")
    print(f"Outlet TDS: {conditions.outlet_tds_ppm:.0f} ppm")
    print(f"Max pressure: {conditions.max_pressure_bar:.1f} bar")
    print(f"Recommended: {conditions.recommended_pressure_bar:.1f} bar")
    print(f"Expected flux: {conditions.expected_flux_kg_m2_s:.4f} kg/m²/s")
    print(f"Flux margin: {conditions.flux_margin_percent:.1f}%")
    
    print("\n" + "="*60)
    print("Stage pressure calculations completed successfully!")
    print("="*60)


if __name__ == "__main__":
    main()