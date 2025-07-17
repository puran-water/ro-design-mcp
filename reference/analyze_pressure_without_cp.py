#!/usr/bin/env python
"""
Analyze pressure requirements with and without CP to infer CP impact.
This approach avoids the initialization issues with CP calculation.
"""

import os
os.environ['WATERTAP_DEBUG_MODE'] = 'false'

from pyomo.environ import ConcreteModel, value, TransformationFactory, Constraint, TerminationCondition
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

def build_and_solve_ro(cp_type=ConcentrationPolarizationType.none):
    """Build and solve RO model with specified CP type."""
    
    # Build model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    m.fs.properties = NaClParameterBlock()
    
    # Units
    m.fs.feed = Feed(property_package=m.fs.properties)
    m.fs.pump = Pump(property_package=m.fs.properties)
    m.fs.ro = ReverseOsmosis0D(
        property_package=m.fs.properties,
        has_pressure_change=True,
        concentration_polarization_type=cp_type,
        mass_transfer_coefficient=MassTransferCoefficient.none,
        pressure_change_type=PressureChangeType.fixed_per_stage
    )
    m.fs.permeate = Product(property_package=m.fs.properties)
    m.fs.concentrate = Product(property_package=m.fs.properties)
    
    # Connect
    m.fs.s01 = Arc(source=m.fs.feed.outlet, destination=m.fs.pump.inlet)
    m.fs.s02 = Arc(source=m.fs.pump.outlet, destination=m.fs.ro.inlet)
    m.fs.s03 = Arc(source=m.fs.ro.permeate, destination=m.fs.permeate.inlet)
    m.fs.s04 = Arc(source=m.fs.ro.retentate, destination=m.fs.concentrate.inlet)
    TransformationFactory("network.expand_arcs").apply_to(m)
    
    # Feed: 150 m³/h at 2700 ppm
    flow_m3_s = 150 / 3600
    feed_mass_frac = 2700 / 1e6
    
    m.fs.feed.outlet.pressure[0].fix(101325)
    m.fs.feed.outlet.temperature[0].fix(298.15)
    m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'].fix(
        flow_m3_s * 1000 * (1 - feed_mass_frac)
    )
    m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'NaCl'].fix(
        flow_m3_s * 1000 * feed_mass_frac
    )
    
    # Pump
    m.fs.pump.efficiency_pump.fix(0.8)
    
    # Membrane (aggregate for 17 vessels)
    m.fs.ro.A_comp.fix(1.1e-9)  # m/s/Pa
    m.fs.ro.B_comp.fix(8.5e-8)  # m/s
    m.fs.ro.area.fix(4422.04)   # Total area for 17 vessels
    m.fs.ro.deltaP.fix(-50000)   # -0.5 bar
    m.fs.ro.permeate.pressure[0].fix(101325)
    
    # Initialize
    m.fs.feed.initialize()
    propagate_state(m.fs.s01)
    m.fs.pump.outlet.pressure[0].fix(20e5)  # Initial guess
    m.fs.pump.initialize()
    propagate_state(m.fs.s02)
    m.fs.ro.initialize()
    propagate_state(m.fs.s03)
    m.fs.permeate.initialize()
    propagate_state(m.fs.s04)
    m.fs.concentrate.initialize()
    
    # Set up for optimization
    m.fs.pump.outlet.pressure[0].unfix()
    m.fs.pump.outlet.pressure[0].setlb(5e5)
    m.fs.pump.outlet.pressure[0].setub(40e5)
    
    # Target 55.8% recovery (Stage 1 of 17:8)
    m.fs.recovery_constraint = Constraint(
        expr=m.fs.ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'] == 0.558
    )
    
    # Solve
    solver = get_solver()
    results = solver.solve(m, tee=False)
    
    if results.solver.termination_condition == TerminationCondition.optimal:
        return m, True
    else:
        return m, False

def analyze_results(m, cp_type_name):
    """Extract and display results."""
    
    # Get key values
    feed_pressure = value(m.fs.pump.outlet.pressure[0]) / 1e5
    recovery = value(m.fs.ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'])
    
    # Flows
    feed_flow = value(m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O']) + \
                value(m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'NaCl'])
    conc_h2o = value(m.fs.concentrate.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
    conc_salt = value(m.fs.concentrate.inlet.flow_mass_phase_comp[0, 'Liq', 'NaCl'])
    conc_flow = conc_h2o + conc_salt
    
    # Concentrations
    feed_tds = value(m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'NaCl']) / feed_flow * 1e6
    conc_tds = conc_salt / conc_flow * 1e6
    
    # Flux
    water_flux = value(m.fs.ro.flux_mass_phase_comp[0, 0, 'Liq', 'H2O']) * 3600
    
    # Osmotic pressures
    feed_osm = value(m.fs.ro.feed_side.properties[0, 0].pressure_osm) / 1e5
    perm_osm = value(m.fs.ro.mixed_permeate[0].pressure_osm) / 1e5
    conc_osm = value(m.fs.ro.feed_side.properties[0, 1].pressure_osm) / 1e5
    
    print(f"\n{cp_type_name} Results:")
    print(f"  Required feed pressure: {feed_pressure:.1f} bar")
    print(f"  Recovery: {recovery*100:.1f}%")
    print(f"  Water flux: {water_flux:.1f} kg/m²/h")
    print(f"  Feed TDS: {feed_tds:.0f} ppm")
    print(f"  Concentrate TDS: {conc_tds:.0f} ppm")
    print(f"  Concentrate flow: {conc_flow/1000*3600:.1f} m³/h ({conc_flow/1000*3600/17:.2f} m³/h per vessel)")
    print(f"  Feed osmotic pressure: {feed_osm:.2f} bar")
    print(f"  Concentrate osmotic pressure: {conc_osm:.2f} bar")
    print(f"  Permeate osmotic pressure: {perm_osm:.2f} bar")
    
    # Calculate NDP
    ndp = feed_pressure - 1.01325 - (feed_osm - perm_osm)
    print(f"  Net driving pressure: {ndp:.1f} bar")
    
    return {
        'pressure': feed_pressure,
        'flux': water_flux,
        'ndp': ndp,
        'feed_osm': feed_osm,
        'conc_flow_per_vessel': conc_flow/1000*3600/17
    }

def main():
    """Run the analysis."""
    print("="*80)
    print("CONCENTRATION POLARIZATION IMPACT ANALYSIS")
    print("="*80)
    print("\nComparing pressure requirements with and without CP consideration")
    print("Configuration: 17 vessels, 150 m³/h feed at 2700 ppm, 55.8% recovery")
    
    # Run without CP
    print("\n1. Running simulation WITHOUT concentration polarization...")
    m_no_cp, success = build_and_solve_ro(ConcentrationPolarizationType.none)
    
    if not success:
        print("Failed to solve without CP!")
        return
    
    results_no_cp = analyze_results(m_no_cp, "WITHOUT CP")
    
    # Try to run with CP (may fail)
    print("\n2. Attempting simulation WITH concentration polarization...")
    try:
        m_with_cp, success = build_and_solve_ro(ConcentrationPolarizationType.calculated)
        if success:
            results_with_cp = analyze_results(m_with_cp, "WITH CP")
        else:
            print("Failed to solve with CP calculation")
            results_with_cp = None
    except Exception as e:
        print(f"Error with CP calculation: {str(e)}")
        results_with_cp = None
    
    # Analysis
    print("\n" + "="*80)
    print("CONCENTRATION POLARIZATION IMPACT")
    print("="*80)
    
    print(f"\nWithout CP consideration:")
    print(f"  Required pressure: {results_no_cp['pressure']:.1f} bar")
    print(f"  This assumes bulk concentrations at membrane surface")
    
    print(f"\nKnown actual pressure from previous runs: ~23.5 bar")
    print(f"Difference: {23.5 - results_no_cp['pressure']:.1f} bar")
    
    # Estimate CP impact
    if results_no_cp['pressure'] < 20:
        cp_pressure_impact = 23.5 - results_no_cp['pressure']
        cp_factor_estimate = 1 + (cp_pressure_impact / results_no_cp['pressure'])
        
        print(f"\nEstimated CP impact:")
        print(f"  Additional pressure needed due to CP: ~{cp_pressure_impact:.1f} bar")
        print(f"  Estimated CP factor: ~{cp_factor_estimate:.1f}")
        print(f"  This suggests interface concentration is ~{cp_factor_estimate:.1f}x bulk")
        
        # Given the concentrate flow rate
        print(f"\nWith concentrate flow of {results_no_cp['conc_flow_per_vessel']:.2f} m³/h per vessel,")
        print(f"a CP factor of {cp_factor_estimate:.1f} is {'reasonable' if cp_factor_estimate < 2.5 else 'high but plausible'}")
    
    # Check membrane permeability
    A_value = value(m_no_cp.fs.ro.A_comp)
    A_lmh_bar = A_value * 3.6e9
    print(f"\nMembrane permeability used:")
    print(f"  A = {A_value:.2e} m/s/Pa ({A_lmh_bar:.1f} LMH/bar)")
    print(f"  This is {'appropriate' if A_lmh_bar > 5 else 'LOW'} for brackish membranes")
    
    if A_lmh_bar < 5:
        print(f"\nNOTE: The code uses {A_lmh_bar:.1f} LMH/bar")
        print(f"Modern brackish membranes typically have 6-8 LMH/bar")
        print(f"This accounts for part of the high pressure requirement")

if __name__ == "__main__":
    main()