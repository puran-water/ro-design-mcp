#!/usr/bin/env python3
"""
Test all membranes with manual initialization approach that works.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.optimize_ro import optimize_vessel_array_configuration
from utils.membrane_properties_handler import get_membrane_properties
from test_complete_workflow_2000ppm import run_complete_workflow


def test_all_membranes():
    """Test all configured membranes with the working manual approach."""
    
    print("="*70)
    print("ALL MEMBRANES TEST - 2000 ppm NaCl")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Test conditions  
    feed_flow = 150  # m³/h
    recovery = 0.75  # 75%
    feed_tds = 2000  # ppm
    
    # Membrane types to test
    membrane_types = [
        ('bw30_400', 'BW30-400 (Standard Brackish)'),
        ('eco_pro_400', 'ECO PRO-400 (High Permeability)'),
        ('cr100_pro_400', 'CR100 PRO-400 (Chemical Resistant)'),
        ('brackish', 'Brackish (Generic)'),
        ('seawater', 'Seawater (Generic)')
    ]
    
    print(f"\nTest Conditions:")
    print(f"  Feed: {feed_flow} m³/h at {feed_tds} ppm")
    print(f"  Target recovery: {recovery*100:.0f}%")
    
    print(f"\nMembrane Properties Database:")
    print("-" * 60)
    print(f"{'Type':<20} {'A_w (m/s/Pa)':<15} {'B_s (m/s)':<15}")
    print("-" * 60)
    
    for mem_type, display_name in membrane_types:
        A_w, B_s = get_membrane_properties(mem_type)
        print(f"{mem_type:<20} {A_w:.2e}{'':<5} {B_s:.2e}")
    
    # Import the working manual simulation approach
    from test_complete_workflow_2000ppm import build_ro_model
    from pyomo.environ import Constraint, value, TerminationCondition
    from watertap.core.solvers import get_solver
    from idaes.core.util.model_statistics import degrees_of_freedom
    from idaes.core.util.initialization import propagate_state
    
    results_summary = []
    
    for mem_type, display_name in membrane_types:
        print(f"\n{'='*60}")
        print(f"TESTING: {display_name}")
        print(f"{'='*60}")
        
        try:
            # Step 1: Configuration
            configurations = optimize_vessel_array_configuration(
                feed_flow_m3h=feed_flow,
                target_recovery=recovery,
                feed_salinity_ppm=feed_tds,
                membrane_type=mem_type,
                allow_recycle=False
            )
            
            if not configurations:
                print("No configuration found!")
                results_summary.append({
                    'membrane': mem_type,
                    'display': display_name,
                    'success': False,
                    'error': 'No configuration'
                })
                continue
            
            config = configurations[0]
            print(f"\nConfiguration: {config['array_notation']}, {config['total_recovery']*100:.1f}% recovery")
            
            # Format configuration
            formatted_config = {
                'success': True,
                'stage_count': config['n_stages'],
                'feed_flow_m3h': config['feed_flow_m3h'],
                'stages': []
            }
            
            for stage in config['stages']:
                formatted_config['stages'].append({
                    'stage_number': stage['stage_number'],
                    'membrane_area_m2': stage['membrane_area_m2'],
                    'stage_recovery': stage['stage_recovery'],
                    'vessels': stage['n_vessels']
                })
            
            # Step 2: Build model
            A_w, B_s = get_membrane_properties(mem_type)
            print(f"Using A_w={A_w:.2e}, B_s={B_s:.2e}")
            
            m, A_w_model, B_s_model = build_ro_model(
                formatted_config,
                feed_tds,
                25.0,
                mem_type
            )
            
            # Verify parameters
            if A_w != A_w_model or B_s != B_s_model:
                print("ERROR: Membrane parameters mismatch!")
                results_summary.append({
                    'membrane': mem_type,
                    'display': display_name,
                    'success': False,
                    'error': 'Parameter mismatch'
                })
                continue
            
            # Step 3: Initialize and solve
            solver = get_solver()
            m.fs.feed.initialize()
            
            # Initialize stages
            for i in range(1, formatted_config['stage_count'] + 1):
                pump = getattr(m.fs, f"pump{i}")
                ro = getattr(m.fs, f"ro_stage{i}")
                product = getattr(m.fs, f"stage_product{i}")
                
                # Set initial pressure based on membrane type
                if 'seawater' in mem_type:
                    init_pressure = (15 + i*5) * 1e5  # Higher for seawater
                elif 'eco' in mem_type:
                    init_pressure = (8 + i*2) * 1e5   # Lower for high perm
                else:
                    init_pressure = (10 + i*2) * 1e5  # Standard
                
                pump.outlet.pressure[0].set_value(init_pressure)
                pump.initialize()
                
                if i == 1:
                    propagate_state(arc=m.fs.feed_to_pump1)
                    propagate_state(arc=m.fs.pump1_to_ro1)
                else:
                    propagate_state(arc=getattr(m.fs, f"stage{i-1}_to_pump{i}"))
                    propagate_state(arc=getattr(m.fs, f"pump{i}_to_stage{i}"))
                
                try:
                    ro.initialize()
                except:
                    pass
                
                if i == 1:
                    propagate_state(arc=m.fs.ro1_perm_to_prod)
                else:
                    propagate_state(arc=getattr(m.fs, f"ro{i}_perm_to_prod{i}"))
                
                product.initialize()
            
            propagate_state(arc=m.fs.final_conc_arc)
            m.fs.concentrate_product.initialize()
            
            # First solve
            results = solver.solve(m, tee=False)
            
            if results.solver.termination_condition != TerminationCondition.optimal:
                print(f"Initial solve failed!")
                results_summary.append({
                    'membrane': mem_type,
                    'display': display_name,
                    'success': False,
                    'error': 'Initial solve failed'
                })
                continue
            
            # Add recovery constraints
            for i in range(1, formatted_config['stage_count'] + 1):
                ro = getattr(m.fs, f"ro_stage{i}")
                target = formatted_config['stages'][i-1]['stage_recovery']
                
                setattr(m.fs, f"recovery_constraint_stage{i}",
                    Constraint(expr=ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'] == target))
            
            # Unfix pressures
            for i in range(1, formatted_config['stage_count'] + 1):
                pump = getattr(m.fs, f"pump{i}")
                pump.outlet.pressure.unfix()
                pump.outlet.pressure[0].setlb(3e5)
                pump.outlet.pressure[0].setub(40e5)
            
            # Final solve
            results = solver.solve(m, tee=False)
            
            if results.solver.termination_condition == TerminationCondition.optimal:
                print("Simulation successful!")
                
                # Extract results
                total_power = 0
                pressures = []
                
                for i in range(1, formatted_config['stage_count'] + 1):
                    pump = getattr(m.fs, f"pump{i}")
                    pressure = value(pump.outlet.pressure[0]) / 1e5
                    power = value(pump.work_mechanical[0]) / 1000
                    
                    pressures.append(pressure)
                    total_power += power
                
                print(f"Pressures: {', '.join(f'{p:.1f} bar' for p in pressures)}")
                print(f"Total power: {total_power:.1f} kW")
                print(f"Specific energy: {total_power/112.5:.2f} kWh/m³")
                
                # Verify membrane properties in model
                for i in range(1, formatted_config['stage_count'] + 1):
                    ro = getattr(m.fs, f"ro_stage{i}")
                    A_check = value(ro.A_comp[0.0, 'H2O'])
                    B_check = value(ro.B_comp[0.0, 'TDS'])
                    
                    if abs(A_check - A_w) > 1e-15 or abs(B_check - B_s) > 1e-15:
                        print(f"WARNING: Stage {i} parameters don't match!")
                
                results_summary.append({
                    'membrane': mem_type,
                    'display': display_name,
                    'success': True,
                    'pressures': pressures,
                    'power': total_power,
                    'specific_energy': total_power/112.5
                })
                
            else:
                print("Final solve failed!")
                results_summary.append({
                    'membrane': mem_type,
                    'display': display_name,
                    'success': False,
                    'error': 'Final solve failed'
                })
                
        except Exception as e:
            print(f"Error: {str(e)}")
            results_summary.append({
                'membrane': mem_type,
                'display': display_name,
                'success': False,
                'error': str(e)
            })
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY - MEMBRANE PARAMETER VERIFICATION")
    print("="*70)
    
    print(f"\n{'Membrane':<30} {'Status':<10} {'Pressures':<20} {'Energy':<15}")
    print("-" * 75)
    
    for result in results_summary:
        if result['success']:
            pressure_str = f"{result['pressures'][0]:.1f}-{result['pressures'][-1]:.1f} bar"
            energy_str = f"{result['specific_energy']:.2f} kWh/m³"
            print(f"{result['display']:<30} {'PASS':<10} {pressure_str:<20} {energy_str:<15}")
        else:
            print(f"{result['display']:<30} {'FAIL':<10} {result['error']:<20} {'-':<15}")
    
    print("\n" + "="*70)
    success_count = sum(1 for r in results_summary if r['success'])
    print(f"Result: {success_count}/{len(results_summary)} membranes passed")
    print("="*70)
    
    if success_count == len(results_summary):
        print("\n✓ All membrane parameters are being correctly passed to the simulation!")
    else:
        print("\n✗ Some membranes failed - check initialization approach")


if __name__ == "__main__":
    test_all_membranes()