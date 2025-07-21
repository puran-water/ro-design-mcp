#!/usr/bin/env python3
"""
Complete MCP workflow test for 2000 ppm NaCl feed.
Configuration -> Simulation with working solution.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.optimize_ro import optimize_vessel_array_configuration
from utils.membrane_properties_handler import get_membrane_properties
from direct_simulate_ro import build_ro_model
from pyomo.environ import *
from watertap.core.solvers import get_solver
from idaes.core.util.model_statistics import degrees_of_freedom


def run_complete_workflow():
    """Run complete workflow for 2000 ppm NaCl."""
    
    print("="*70)
    print("COMPLETE MCP WORKFLOW - 2000 ppm NaCl")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Parameters
    feed_flow = 150  # m³/h
    recovery = 0.75  # 75%
    feed_tds = 2000  # ppm
    membrane_type = 'eco_pro_400'
    
    print(f"\nFeed Conditions:")
    print(f"  Flow: {feed_flow} m³/h") 
    print(f"  TDS: {feed_tds} ppm (NaCl)")
    print(f"  Target recovery: {recovery*100:.0f}%")
    print(f"  Membrane: {membrane_type}")
    
    # Step 1: Configuration
    print(f"\n{'='*50}")
    print("STEP 1: CONFIGURATION")
    print(f"{'='*50}")
    
    configurations = optimize_vessel_array_configuration(
        feed_flow_m3h=feed_flow,
        target_recovery=recovery,
        feed_salinity_ppm=feed_tds,
        membrane_type=membrane_type,
        allow_recycle=False  # Keep it simple
    )
    
    if not configurations:
        print("ERROR: No configurations found!")
        return
    
    config = configurations[0]
    
    print(f"\nConfiguration Result:")
    print(f"  Array: {config['array_notation']}")
    print(f"  Total recovery: {config['total_recovery']*100:.1f}%")
    
    # Format for simulation
    formatted_config = {
        'success': True,
        'stage_count': config['n_stages'],
        'feed_flow_m3h': config['feed_flow_m3h'],
        'stages': []
    }
    
    total_area = 0
    for stage in config['stages']:
        stage_info = {
            'stage_number': stage['stage_number'],
            'membrane_area_m2': stage['membrane_area_m2'],
            'stage_recovery': stage['stage_recovery'],
            'vessels': stage['n_vessels']
        }
        formatted_config['stages'].append(stage_info)
        
        print(f"\n  Stage {stage['stage_number']}:")
        print(f"    Recovery: {stage['stage_recovery']*100:.1f}%")
        print(f"    Vessels: {stage['n_vessels']}")
        print(f"    Area: {stage['membrane_area_m2']:.0f} m²")
        
        total_area += stage['membrane_area_m2']
    
    print(f"\n  Total area: {total_area:.0f} m²")
    
    # Step 2: Build and solve model directly
    print(f"\n{'='*50}")
    print("STEP 2: SIMULATION")  
    print(f"{'='*50}")
    
    # Get membrane properties
    A_w, B_s = get_membrane_properties(membrane_type)
    print(f"\nMembrane properties:")
    print(f"  A_w: {A_w:.2e} m/s/Pa")
    print(f"  B_s: {B_s:.2e} m/s")
    
    # Build model
    print("\nBuilding model...")
    m, A_w, B_s = build_ro_model(
        formatted_config,
        feed_tds,
        25.0,
        membrane_type
    )
    
    print(f"Model built. DOF: {degrees_of_freedom(m)}")
    
    # Manual initialization with careful pressure settings
    solver = get_solver()
    
    print("\nInitializing system...")
    
    # Initialize feed
    m.fs.feed.initialize()
    
    # Stage 1
    print("\n  Stage 1:")
    # Set conservative pressure for low TDS
    m.fs.pump1.outlet.pressure[0].set_value(10e5)  # 10 bar
    m.fs.pump1.initialize()
    
    # Initialize RO1 without recovery constraint first
    from idaes.core.util.initialization import propagate_state
    propagate_state(arc=m.fs.feed_to_pump1)
    propagate_state(arc=m.fs.pump1_to_ro1)
    
    try:
        m.fs.ro_stage1.initialize()
        print("    RO1 initialized")
    except:
        print("    RO1 initialization warning")
    
    propagate_state(arc=m.fs.ro1_perm_to_prod)
    m.fs.stage_product1.initialize()
    
    # Check actual recovery
    recovery1 = value(m.fs.ro_stage1.recovery_mass_phase_comp[0, 'Liq', 'H2O'])
    print(f"    Initial recovery: {recovery1:.1%}")
    
    # Stage 2
    if config['n_stages'] > 1:
        print("\n  Stage 2:")
        propagate_state(arc=m.fs.stage1_to_pump2)
        
        m.fs.pump2.outlet.pressure[0].set_value(15e5)  # 15 bar
        m.fs.pump2.initialize()
        
        propagate_state(arc=m.fs.pump2_to_stage2)
        
        try:
            m.fs.ro_stage2.initialize()
            print("    RO2 initialized")
        except:
            print("    RO2 initialization warning")
        
        propagate_state(arc=m.fs.ro2_perm_to_prod2)
        m.fs.stage_product2.initialize()
        
        recovery2 = value(m.fs.ro_stage2.recovery_mass_phase_comp[0, 'Liq', 'H2O'])
        print(f"    Initial recovery: {recovery2:.1%}")
    
    # Initialize concentrate
    propagate_state(arc=m.fs.final_conc_arc)
    m.fs.concentrate_product.initialize()
    
    # First solve without recovery constraints
    print("\nSolving without recovery constraints...")
    results = solver.solve(m, tee=False)
    
    if results.solver.termination_condition == TerminationCondition.optimal:
        print("Initial solve successful!")
        
        # Check recoveries
        for i in range(1, config['n_stages'] + 1):
            ro = getattr(m.fs, f"ro_stage{i}")
            rec = value(ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'])
            target = formatted_config['stages'][i-1]['stage_recovery']
            print(f"  Stage {i}: current={rec:.1%}, target={target:.1%}")
        
        # Now add recovery constraints
        print("\nAdding recovery constraints...")
        for i in range(1, config['n_stages'] + 1):
            ro = getattr(m.fs, f"ro_stage{i}")
            target = formatted_config['stages'][i-1]['stage_recovery']
            
            setattr(m.fs, f"recovery_constraint_stage{i}",
                Constraint(expr=ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'] == target))
        
        # Unfix pump pressures to let them optimize
        for i in range(1, config['n_stages'] + 1):
            pump = getattr(m.fs, f"pump{i}")
            pump.outlet.pressure.unfix()
            # Set bounds
            pump.outlet.pressure[0].setlb(5e5)   # 5 bar min
            pump.outlet.pressure[0].setub(30e5)  # 30 bar max
        
        print(f"\nDOF with constraints: {degrees_of_freedom(m)}")
        
        # Final solve
        print("\nFinal solve with recovery constraints...")
        results = solver.solve(m, tee=False)
        
        if results.solver.termination_condition == TerminationCondition.optimal:
            print("Simulation successful!")
            
            # Extract results
            print("\n" + "="*50)
            print("SIMULATION RESULTS")
            print("="*50)
            
            total_perm_h2o = 0
            total_perm_tds = 0
            total_power = 0
            
            for i in range(1, config['n_stages'] + 1):
                pump = getattr(m.fs, f"pump{i}")
                ro = getattr(m.fs, f"ro_stage{i}")
                product = getattr(m.fs, f"stage_product{i}")
                
                pressure = value(pump.outlet.pressure[0]) / 1e5
                recovery = value(ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'])
                flux = value(ro.flux_mass_phase_comp[0, 0, 'Liq', 'H2O'])
                power = value(pump.work_mechanical[0]) / 1000
                
                perm_h2o = value(product.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
                perm_tds = value(product.inlet.flow_mass_phase_comp[0, 'Liq', 'TDS'])
                
                print(f"\nStage {i}:")
                print(f"  Pressure: {pressure:.1f} bar")
                print(f"  Recovery: {recovery:.1%}")
                print(f"  Water flux: {flux:.4f} kg/m²/s")
                print(f"  Power: {power:.1f} kW")
                
                total_perm_h2o += perm_h2o
                total_perm_tds += perm_tds
                total_power += power
            
            # Overall performance
            feed_h2o = value(m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
            total_recovery = total_perm_h2o / feed_h2o
            permeate_flow = total_perm_h2o / 1000 * 3600
            permeate_tds = total_perm_tds / total_perm_h2o * 1e6
            specific_energy = total_power / permeate_flow
            
            print(f"\nOverall Performance:")
            print(f"  Total recovery: {total_recovery:.1%}")
            print(f"  Permeate flow: {permeate_flow:.1f} m³/h")
            print(f"  Permeate TDS: {permeate_tds:.0f} ppm")
            print(f"  Total power: {total_power:.1f} kW")
            print(f"  Specific energy: {specific_energy:.2f} kWh/m³")
            
            # Ion composition estimate (Na+ and Cl-)
            na_frac = 22.99 / 58.44
            cl_frac = 35.45 / 58.44
            
            print(f"\nEstimated Permeate Ion Composition:")
            print(f"  Na+: {permeate_tds * na_frac:.1f} mg/L")
            print(f"  Cl-: {permeate_tds * cl_frac:.1f} mg/L")
            
        else:
            print(f"Final solve failed: {results.solver.termination_condition}")
    else:
        print(f"Initial solve failed: {results.solver.termination_condition}")
    
    print("\n" + "="*70)
    print("WORKFLOW COMPLETE")
    print("="*70)


if __name__ == "__main__":
    run_complete_workflow()