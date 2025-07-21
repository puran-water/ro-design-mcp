#!/usr/bin/env python3
"""
Test complete MCP workflow for 2000 ppm NaCl feed with ALL configured membranes.
Verifies that membrane parameters are correctly passed from database to simulation.
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
from utils.config import get_config
from direct_simulate_ro import build_ro_model
from pyomo.environ import *
from watertap.core.solvers import get_solver
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.core.util.initialization import propagate_state


def test_membrane_workflow(membrane_type: str, display_name: str, feed_flow: float, 
                          recovery: float, feed_tds: float):
    """Test complete workflow for a specific membrane type."""
    
    print(f"\n{'='*70}")
    print(f"TESTING: {display_name}")
    print(f"{'='*70}")
    
    # Get membrane properties from database
    A_w, B_s = get_membrane_properties(membrane_type)
    print(f"\nMembrane properties from database:")
    print(f"  Type: {membrane_type}")
    print(f"  A_w: {A_w:.2e} m/s/Pa")
    print(f"  B_s: {B_s:.2e} m/s")
    
    # Step 1: Configuration
    print(f"\n1. CONFIGURATION STAGE")
    print("-" * 50)
    
    try:
        configurations = optimize_vessel_array_configuration(
            feed_flow_m3h=feed_flow,
            target_recovery=recovery,
            feed_salinity_ppm=feed_tds,
            membrane_type=membrane_type,
            allow_recycle=False
        )
        
        if not configurations:
            print("  ERROR: No configurations found!")
            return False, None
        
        config = configurations[0]
        
        print(f"  Configuration found:")
        print(f"    Array: {config['array_notation']}")
        print(f"    Total recovery: {config['total_recovery']*100:.1f}%")
        
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
            
            print(f"    Stage {stage['stage_number']}: {stage['n_vessels']} vessels, "
                  f"{stage['membrane_area_m2']:.0f} m², {stage['stage_recovery']*100:.1f}% recovery")
            
            total_area += stage['membrane_area_m2']
        
        print(f"    Total area: {total_area:.0f} m²")
        
    except Exception as e:
        print(f"  Configuration error: {str(e)}")
        return False, None
    
    # Step 2: Simulation
    print(f"\n2. SIMULATION STAGE")
    print("-" * 50)
    
    try:
        # Build model
        m, A_w_sim, B_s_sim = build_ro_model(
            formatted_config,
            feed_tds,
            25.0,
            membrane_type
        )
        
        # Verify membrane properties were passed correctly
        print(f"\n  Verifying membrane parameters:")
        print(f"    A_w in model: {A_w_sim:.2e} m/s/Pa")
        print(f"    B_s in model: {B_s_sim:.2e} m/s")
        print(f"    Match database: A_w {A_w == A_w_sim}, B_s {B_s == B_s_sim}")
        
        if A_w != A_w_sim or B_s != B_s_sim:
            print("    ERROR: Membrane parameters don't match!")
            return False, None
        
        # Initialize and solve
        solver = get_solver()
        
        # Initialize feed
        m.fs.feed.initialize()
        
        # Initialize stages with appropriate pressures
        for i in range(1, formatted_config['stage_count'] + 1):
            pump = getattr(m.fs, f"pump{i}")
            ro = getattr(m.fs, f"ro_stage{i}")
            product = getattr(m.fs, f"stage_product{i}")
            
            # Set pressure based on membrane type and stage
            if 'eco' in membrane_type.lower():
                base_pressure = 8e5  # 8 bar for high perm
            elif 'xle' in membrane_type.lower():
                base_pressure = 10e5  # 10 bar for ultra-low energy
            elif 'bw30' in membrane_type.lower():
                base_pressure = 12e5  # 12 bar for standard
            else:
                base_pressure = 15e5  # 15 bar for others
            
            pump.outlet.pressure[0].set_value(base_pressure + (i-1)*2e5)
            pump.initialize()
            
            # Propagate and initialize
            if i == 1:
                propagate_state(arc=m.fs.feed_to_pump1)
                propagate_state(arc=m.fs.pump1_to_ro1)
            else:
                propagate_state(arc=getattr(m.fs, f"stage{i-1}_to_pump{i}"))
                propagate_state(arc=getattr(m.fs, f"pump{i}_to_stage{i}"))
            
            try:
                ro.initialize()
            except:
                pass  # Continue even if warning
            
            if i == 1:
                propagate_state(arc=m.fs.ro1_perm_to_prod)
            else:
                propagate_state(arc=getattr(m.fs, f"ro{i}_perm_to_prod{i}"))
            
            product.initialize()
        
        # Initialize concentrate
        propagate_state(arc=m.fs.final_conc_arc)
        m.fs.concentrate_product.initialize()
        
        # First solve
        results = solver.solve(m, tee=False)
        
        if results.solver.termination_condition != TerminationCondition.optimal:
            print(f"  Initial solve failed: {results.solver.termination_condition}")
            return False, None
        
        # Add recovery constraints
        for i in range(1, formatted_config['stage_count'] + 1):
            ro = getattr(m.fs, f"ro_stage{i}")
            target = formatted_config['stages'][i-1]['stage_recovery']
            
            setattr(m.fs, f"recovery_constraint_stage{i}",
                Constraint(expr=ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'] == target))
        
        # Unfix pump pressures
        for i in range(1, formatted_config['stage_count'] + 1):
            pump = getattr(m.fs, f"pump{i}")
            pump.outlet.pressure.unfix()
            pump.outlet.pressure[0].setlb(3e5)   # 3 bar min
            pump.outlet.pressure[0].setub(40e5)  # 40 bar max
        
        # Final solve
        results = solver.solve(m, tee=False)
        
        if results.solver.termination_condition == TerminationCondition.optimal:
            print("  Simulation successful!")
            
            # Extract results
            results_data = {
                'membrane_type': membrane_type,
                'stages': [],
                'total_recovery': 0,
                'total_power': 0,
                'permeate_tds': 0
            }
            
            total_perm_h2o = 0
            total_perm_tds = 0
            total_power = 0
            
            for i in range(1, formatted_config['stage_count'] + 1):
                pump = getattr(m.fs, f"pump{i}")
                ro = getattr(m.fs, f"ro_stage{i}")
                product = getattr(m.fs, f"stage_product{i}")
                
                # Verify membrane properties in each RO unit
                A_w_stage = value(ro.A_comp[0.0, 'H2O'])
                B_s_stage = value(ro.B_comp[0.0, 'TDS'])
                
                pressure = value(pump.outlet.pressure[0]) / 1e5
                recovery = value(ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'])
                flux = value(ro.flux_mass_phase_comp[0, 0, 'Liq', 'H2O'])
                power = value(pump.work_mechanical[0]) / 1000
                
                perm_h2o = value(product.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
                perm_tds = value(product.inlet.flow_mass_phase_comp[0, 'Liq', 'TDS'])
                
                stage_data = {
                    'stage': i,
                    'pressure_bar': pressure,
                    'recovery': recovery,
                    'flux': flux,
                    'A_w': A_w_stage,
                    'B_s': B_s_stage
                }
                results_data['stages'].append(stage_data)
                
                total_perm_h2o += perm_h2o
                total_perm_tds += perm_tds
                total_power += power
            
            feed_h2o = value(m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
            results_data['total_recovery'] = total_perm_h2o / feed_h2o
            results_data['total_power'] = total_power
            results_data['permeate_tds'] = total_perm_tds / total_perm_h2o * 1e6
            results_data['specific_energy'] = total_power / (total_perm_h2o * 3.6)
            
            return True, results_data
            
        else:
            print(f"  Final solve failed: {results.solver.termination_condition}")
            return False, None
            
    except Exception as e:
        print(f"  Simulation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False, None


def main():
    """Test all configured membranes."""
    
    print("="*70)
    print("COMPREHENSIVE MEMBRANE PARAMETER VERIFICATION TEST")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Test conditions
    feed_flow = 150  # m³/h
    recovery = 0.75  # 75%
    feed_tds = 2000  # ppm
    
    print(f"\nTest Conditions:")
    print(f"  Feed flow: {feed_flow} m³/h")
    print(f"  Feed TDS: {feed_tds} ppm (NaCl)")
    print(f"  Target recovery: {recovery*100:.0f}%")
    
    # Get configured membranes from config
    membrane_types = [
        'bw30_400',
        'eco_pro_400', 
        'cr100_pro_400',
        'brackish',
        'seawater'
    ]
    
    print(f"\nConfigured Membranes in Database:")
    print("-" * 50)
    for mem_type in membrane_types:
        try:
            A_w, B_s = get_membrane_properties(mem_type)
            print(f"  {mem_type}: A_w={A_w:.2e}, B_s={B_s:.2e}")
        except:
            print(f"  {mem_type}: Error loading properties")
    
    # Test each membrane
    results_summary = []
    
    for membrane_type in membrane_types:
        display_name = membrane_type.upper().replace('_', ' ')
        
        success, results = test_membrane_workflow(
            membrane_type, 
            display_name,
            feed_flow,
            recovery,
            feed_tds
        )
        
        results_summary.append({
            'membrane': membrane_type,
            'display_name': display_name,
            'success': success,
            'results': results
        })
    
    # Summary report
    print("\n" + "="*70)
    print("SUMMARY REPORT")
    print("="*70)
    
    print("\nMembrane Parameter Verification:")
    print("-" * 50)
    print(f"{'Membrane Type':<20} {'Status':<10} {'A_w Match':<12} {'B_s Match':<12}")
    print("-" * 50)
    
    all_passed = True
    for summary in results_summary:
        if summary['success']:
            # Check if parameters match in all stages
            param_match = True
            if summary['results']:
                A_w_db, B_s_db = get_membrane_properties(summary['membrane'])
                for stage in summary['results']['stages']:
                    if abs(stage['A_w'] - A_w_db) > 1e-15 or abs(stage['B_s'] - B_s_db) > 1e-15:
                        param_match = False
                        break
            
            status = "PASS" if param_match else "FAIL"
            a_match = "✓" if param_match else "✗"
            b_match = "✓" if param_match else "✗"
        else:
            status = "FAIL"
            a_match = "✗"
            b_match = "✗"
            all_passed = False
        
        print(f"{summary['display_name']:<20} {status:<10} {a_match:<12} {b_match:<12}")
    
    print("\nSimulation Results:")
    print("-" * 50)
    print(f"{'Membrane':<20} {'Recovery':<12} {'Energy':<12} {'Permeate TDS':<15} {'Pressure Range':<20}")
    print("-" * 50)
    
    for summary in results_summary:
        if summary['success'] and summary['results']:
            r = summary['results']
            pressures = [s['pressure_bar'] for s in r['stages']]
            pressure_range = f"{min(pressures):.1f}-{max(pressures):.1f} bar"
            
            print(f"{summary['display_name']:<20} "
                  f"{r['total_recovery']*100:.1f}%{'':<7} "
                  f"{r['specific_energy']:.2f} kWh/m³{'':<3} "
                  f"{r['permeate_tds']:.0f} ppm{'':<10} "
                  f"{pressure_range:<20}")
        else:
            print(f"{summary['display_name']:<20} {'FAILED':<12} {'-':<12} {'-':<15} {'-':<20}")
    
    print("\n" + "="*70)
    print(f"Overall Result: {'ALL MEMBRANES PASSED' if all_passed else 'SOME MEMBRANES FAILED'}")
    print("="*70)
    
    # Detailed results for successful runs
    print("\nDetailed Stage Results for Successful Simulations:")
    for summary in results_summary:
        if summary['success'] and summary['results']:
            print(f"\n{summary['display_name']}:")
            for stage in summary['results']['stages']:
                print(f"  Stage {stage['stage']}: "
                      f"{stage['pressure_bar']:.1f} bar, "
                      f"{stage['recovery']*100:.1f}% recovery, "
                      f"{stage['flux']:.4f} kg/m²/s flux")


if __name__ == "__main__":
    main()