#!/usr/bin/env python
"""
Directly build and solve a simple RO model to extract CP data.
This bypasses the complex simulation infrastructure.
"""

import os
os.environ['WATERTAP_DEBUG_MODE'] = 'false'

from pyomo.environ import ConcreteModel, value, TransformationFactory, Constraint, SolverStatus, TerminationCondition
from pyomo.network import Arc
from idaes.core import FlowsheetBlock
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.core.util.initialization import propagate_state
from idaes.models.unit_models import Feed, Product
from watertap.core.solvers import get_solver
from watertap.unit_models.reverse_osmosis_0D import (
    ReverseOsmosis0D,
    ConcentrationPolarizationType,
    MassTransferCoefficient,
    PressureChangeType
)
from watertap.unit_models.pressure_changer import Pump
from watertap.property_models.NaCl_prop_pack import NaClParameterBlock

def build_simple_ro_model():
    """Build a simple single-stage RO model."""
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    
    # Property package
    m.fs.properties = NaClParameterBlock()
    
    # Units
    m.fs.feed = Feed(property_package=m.fs.properties)
    m.fs.pump = Pump(property_package=m.fs.properties)
    m.fs.ro = ReverseOsmosis0D(
        property_package=m.fs.properties,
        has_pressure_change=True,
        concentration_polarization_type=ConcentrationPolarizationType.calculated,
        mass_transfer_coefficient=MassTransferCoefficient.calculated,
        pressure_change_type=PressureChangeType.calculated
    )
    m.fs.permeate = Product(property_package=m.fs.properties)
    m.fs.concentrate = Product(property_package=m.fs.properties)
    
    # Connections
    m.fs.s01 = Arc(source=m.fs.feed.outlet, destination=m.fs.pump.inlet)
    m.fs.s02 = Arc(source=m.fs.pump.outlet, destination=m.fs.ro.inlet)
    m.fs.s03 = Arc(source=m.fs.ro.permeate, destination=m.fs.permeate.inlet)
    m.fs.s04 = Arc(source=m.fs.ro.retentate, destination=m.fs.concentrate.inlet)
    
    TransformationFactory("network.expand_arcs").apply_to(m)
    
    return m

def set_operating_conditions(m):
    """Set operating conditions for the model."""
    # Feed: 50 m³/h at 2700 ppm (smaller scale for single vessel equivalent)
    flow_m3_s = 50 / 3600
    feed_mass_frac = 2700 / 1e6
    
    m.fs.feed.outlet.pressure[0].fix(101325)  # 1 atm
    m.fs.feed.outlet.temperature[0].fix(298.15)  # 25°C
    m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'].fix(
        flow_m3_s * 1000 * (1 - feed_mass_frac)
    )
    m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'NaCl'].fix(
        flow_m3_s * 1000 * feed_mass_frac
    )
    
    # Pump
    m.fs.pump.efficiency_pump.fix(0.8)
    m.fs.pump.outlet.pressure[0].fix(20e5)  # 20 bar initial
    
    # Membrane properties (brackish)
    m.fs.ro.A_comp.fix(1.1e-9)  # m/s/Pa
    m.fs.ro.B_comp.fix(8.5e-8)  # m/s
    m.fs.ro.area.fix(1000)  # m²
    m.fs.ro.feed_side.channel_height.fix(0.001)  # m
    m.fs.ro.feed_side.spacer_porosity.fix(0.85)
    m.fs.ro.permeate.pressure[0].fix(101325)  # 1 atm
    
    # For calculated pressure change type, need length and width
    m.fs.ro.length.fix(10)  # m
    m.fs.ro.width.fix(100)  # m (area = length * width = 1000 m²)

def solve_model(m):
    """Initialize and solve the model."""
    print("Initializing model...")
    
    # Initialize units
    m.fs.feed.initialize()
    propagate_state(m.fs.s01)
    m.fs.pump.initialize()
    propagate_state(m.fs.s02)
    
    # Initialize RO
    m.fs.ro.initialize()
    
    propagate_state(m.fs.s03)
    m.fs.permeate.initialize()
    propagate_state(m.fs.s04)
    m.fs.concentrate.initialize()
    
    # Check DOF
    print(f"Degrees of freedom: {degrees_of_freedom(m)}")
    
    # Unfix pump pressure and add recovery constraint
    m.fs.pump.outlet.pressure[0].unfix()
    m.fs.pump.outlet.pressure[0].setlb(5e5)
    m.fs.pump.outlet.pressure[0].setub(40e5)
    
    # Target 50% recovery
    m.fs.recovery_constraint = Constraint(
        expr=m.fs.ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'] == 0.50
    )
    
    print(f"DOF after adding constraint: {degrees_of_freedom(m)}")
    
    # Solve
    solver = get_solver()
    print("Solving...")
    results = solver.solve(m, tee=False)
    
    return results

def extract_cp_data(m):
    """Extract concentration polarization data from solved model."""
    print("\n" + "="*80)
    print("CONCENTRATION POLARIZATION DATA EXTRACTION")
    print("="*80)
    
    ro = m.fs.ro
    
    # Basic results
    feed_pressure = value(m.fs.pump.outlet.pressure[0]) / 1e5
    recovery = value(ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'])
    
    print(f"\nOperating Conditions:")
    print(f"  Feed pressure: {feed_pressure:.1f} bar")
    print(f"  Recovery: {recovery*100:.1f}%")
    
    # Try to get bulk properties
    try:
        # Bulk properties at inlet
        bulk_conc_in = value(ro.feed_side.properties[0, 0].conc_mass_phase_comp['Liq', 'NaCl'])
        bulk_pressure_in = value(ro.feed_side.properties[0, 0].pressure) / 1e5
        
        print(f"\nBulk Properties at Inlet:")
        print(f"  NaCl concentration: {bulk_conc_in:.1f} g/L")
        print(f"  Pressure: {bulk_pressure_in:.1f} bar")
        
        # Check if concentration polarization is calculated
        if hasattr(ro, 'feed_side') and ConcentrationPolarizationType.calculated:
            print("\nConcentration polarization type: CALCULATED")
            
            # Try different ways to access CP data
            # Method 1: Direct CP modulus
            if hasattr(ro, 'cp_modulus'):
                try:
                    cp_mod = value(ro.cp_modulus[0, 0, 'NaCl'])
                    print(f"  CP modulus: {cp_mod:.2f}")
                except:
                    print("  CP modulus not accessible")
            
            # Method 2: Mass transfer coefficient
            if hasattr(ro.feed_side, 'K'):
                try:
                    k_value = value(ro.feed_side.K[0, 0, 'NaCl'])
                    print(f"  Mass transfer coefficient: {k_value:.2e} m/s")
                except:
                    print("  Mass transfer coefficient not accessible")
            
            # Method 3: Try to calculate from flux and driving force
            try:
                water_flux = value(ro.flux_mass_phase_comp[0, 0, 'Liq', 'H2O'])
                print(f"  Water flux: {water_flux*3600:.1f} kg/m²/h")
                
                # Get pressures
                p_feed = value(ro.feed_side.properties[0, 0].pressure) / 1e5
                p_perm = value(ro.permeate.pressure[0]) / 1e5
                
                # Get osmotic pressures
                if hasattr(ro.feed_side.properties[0, 0], 'pressure_osm'):
                    osm_feed = value(ro.feed_side.properties[0, 0].pressure_osm) / 1e5
                    osm_perm = value(ro.mixed_permeate[0].pressure_osm) / 1e5
                    
                    print(f"\nOsmotic Pressures:")
                    print(f"  Feed (bulk): {osm_feed:.2f} bar")
                    print(f"  Permeate: {osm_perm:.2f} bar")
                    
                    # Calculate what NDP would be without CP
                    ndp_no_cp = (p_feed - p_perm) - (osm_feed - osm_perm)
                    print(f"\nPressure Analysis (assuming no CP):")
                    print(f"  Hydraulic ΔP: {p_feed - p_perm:.1f} bar")
                    print(f"  Osmotic ΔP: {osm_feed - osm_perm:.1f} bar")
                    print(f"  NDP (if no CP): {ndp_no_cp:.1f} bar")
                    
                    # Calculate expected flux with this NDP
                    A_value = value(ro.A_comp)
                    expected_flux = ndp_no_cp * 1e5 * A_value * 3600  # kg/m²/h
                    actual_flux = water_flux * 3600
                    
                    print(f"\nFlux Analysis:")
                    print(f"  Expected flux (no CP): {expected_flux:.1f} kg/m²/h")
                    print(f"  Actual flux: {actual_flux:.1f} kg/m²/h")
                    print(f"  Ratio: {actual_flux/expected_flux:.2f}")
                    
                    if actual_flux < expected_flux * 0.8:
                        print("\n  INDICATION: Actual flux is significantly lower than expected")
                        print("  This suggests concentration polarization is reducing driving force")
                    
            except Exception as e:
                print(f"  Error in flux analysis: {str(e)}")
                
    except Exception as e:
        print(f"\nError extracting data: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # Try to get any CP-related variables
    print("\n\nSearching for CP-related variables in model...")
    for var in ro.component_data_objects(ctype=None):
        var_name = var.name if hasattr(var, 'name') else str(var)
        if any(term in var_name.lower() for term in ['interface', 'polariz', 'cp_', 'modulus']):
            try:
                var_value = value(var)
                print(f"  Found: {var_name} = {var_value}")
            except:
                pass

def main():
    """Run the analysis."""
    print("="*80)
    print("DIRECT CONCENTRATION POLARIZATION ANALYSIS")
    print("="*80)
    
    print("\nBuilding model...")
    m = build_simple_ro_model()
    
    print("Setting operating conditions...")
    set_operating_conditions(m)
    
    print("\nSolving model...")
    results = solve_model(m)
    
    if results.solver.termination_condition == TerminationCondition.optimal:
        print("Solution found!")
        extract_cp_data(m)
    else:
        print(f"Solver failed: {results.solver.termination_condition}")

if __name__ == "__main__":
    main()