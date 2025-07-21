#!/usr/bin/env python3
"""
Quick test to verify ECO PRO-400 membrane (high permeability) works without FBBT errors.
This was the membrane type that was causing initialization failures.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pyomo.environ import *
from watertap.unit_models.reverse_osmosis_0D import ReverseOsmosis0D
from idaes.core import FlowsheetBlock
import watertap.property_models.seawater_prop_pack as props_sw
from utils.membrane_properties_handler import get_membrane_properties
from utils.ro_initialization import (
    calculate_required_pressure,
    validate_flux_bounds,
    initialize_ro_unit_elegant
)

def test_eco_pro_400():
    """Test ECO PRO-400 membrane initialization."""
    print("Testing ECO PRO-400 membrane (high permeability)")
    print("="*60)
    
    # Get membrane properties
    A_w, B_s = get_membrane_properties("eco_pro_400")
    print(f"Membrane properties: A_w = {A_w:.2e} m/s/Pa, B_s = {B_s:.2e} m/s")
    
    # Test configuration
    feed_tds_ppm = 2000
    target_recovery = 0.5
    
    # Calculate required pressure with flux validation
    print(f"\nCalculating required pressure for {feed_tds_ppm} ppm feed, {target_recovery:.0%} recovery...")
    
    required_pressure = calculate_required_pressure(
        feed_tds_ppm=feed_tds_ppm,
        target_recovery=target_recovery,
        A_w=A_w
    )
    
    print(f"Required pressure: {required_pressure/1e5:.1f} bar")
    
    # Validate flux bounds
    is_valid, expected_flux = validate_flux_bounds(
        A_w=A_w,
        pressure=required_pressure,
        osmotic_pressure=feed_tds_ppm * 0.7 * 1e5  # Simplified
    )
    
    print(f"Expected flux: {expected_flux:.4f} kg/m²/s")
    print(f"Flux validation: {'PASS' if is_valid else 'FAIL'}")
    print(f"WaterTAP flux limits: (0.0001, 0.03) kg/m²/s")
    
    if not is_valid:
        print("\nERROR: Flux bounds validation failed!")
        print("The calculate_required_pressure function is not properly capping pressure.")
        return False
    
    # Now test actual WaterTAP model initialization
    print("\nTesting WaterTAP model initialization...")
    
    # Create simple model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    m.fs.properties = props_sw.SeawaterParameterBlock()
    
    # Create RO unit
    m.fs.ro = ReverseOsmosis0D(
        property_package=m.fs.properties,
        has_pressure_change=True
    )
    
    # Set membrane properties
    m.fs.ro.A_comp.fix(A_w)
    m.fs.ro.B_comp[0, 'TDS'].fix(B_s)
    m.fs.ro.area.fix(100)  # 100 m²
    m.fs.ro.permeate.pressure.fix(101325)  # 1 atm
    
    # Set inlet conditions
    feed_flow_m3_s = 100 / 3600  # 100 m³/h
    feed_mass_frac = feed_tds_ppm / 1e6
    
    m.fs.ro.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O'].fix(
        feed_flow_m3_s * 1000 * (1 - feed_mass_frac)
    )
    m.fs.ro.inlet.flow_mass_phase_comp[0, 'Liq', 'TDS'].fix(
        feed_flow_m3_s * 1000 * feed_mass_frac
    )
    m.fs.ro.inlet.temperature[0].fix(298.15)  # 25°C
    m.fs.ro.inlet.pressure[0].fix(required_pressure)
    
    # Try to initialize
    try:
        print("Initializing RO unit...")
        initialize_ro_unit_elegant(m.fs.ro, target_recovery=target_recovery, verbose=True)
        print("\nSUCCESS: RO unit initialized without FBBT errors!")
        
        # Check actual flux
        actual_flux = value(m.fs.ro.flux_mass_phase_comp[0, 0, 'Liq', 'H2O'])
        print(f"\nActual water flux: {actual_flux:.4f} kg/m²/s")
        
        if actual_flux > 0.03:
            print("WARNING: Actual flux exceeds WaterTAP upper bound!")
            return False
        
        return True
        
    except Exception as e:
        print(f"\nERROR: Initialization failed: {str(e)}")
        if "FBBT" in str(e) or "infeasible" in str(e):
            print("FBBT infeasibility detected - flux validation fix not working!")
        return False


def test_all_membranes():
    """Test all membrane types."""
    membrane_types = ["bw30_400", "eco_pro_400", "cr100_pro_400"]
    results = []
    
    for membrane_type in membrane_types:
        print(f"\n\nTesting {membrane_type}...")
        A_w, B_s = get_membrane_properties(membrane_type)
        
        # Test at different pressures
        test_pressures = [20e5, 30e5, 40e5]  # 20, 30, 40 bar
        
        for pressure in test_pressures:
            is_valid, flux = validate_flux_bounds(A_w, pressure)
            status = "OK" if is_valid else "EXCEEDS LIMIT"
            results.append({
                "membrane": membrane_type,
                "pressure_bar": pressure/1e5,
                "flux": flux,
                "status": status
            })
            print(f"  {pressure/1e5:.0f} bar: flux = {flux:.4f} kg/m²/s - {status}")
    
    return results


if __name__ == "__main__":
    print("Flux Validation Test\n")
    
    # Test flux bounds for all membranes
    print("1. Testing flux bounds at different pressures:")
    print("="*60)
    test_all_membranes()
    
    # Test ECO PRO-400 initialization
    print("\n\n2. Testing ECO PRO-400 initialization (problematic case):")
    print("="*60)
    success = test_eco_pro_400()
    
    if success:
        print("\n\nTEST PASSED: Flux validation fixes are working correctly!")
        sys.exit(0)
    else:
        print("\n\nTEST FAILED: Further investigation needed.")
        sys.exit(1)