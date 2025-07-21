#!/usr/bin/env python3
"""
Test permeate quality (TDS) for all membrane types.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.optimize_ro import optimize_vessel_array_configuration
from utils.membrane_properties_handler import get_membrane_properties
from test_complete_workflow_2000ppm import build_ro_model
from pyomo.environ import Constraint, value, TerminationCondition
from watertap.core.solvers import get_solver
from idaes.core.util.initialization import propagate_state


def test_permeate_quality():
    """Test permeate quality for all membranes."""
    
    print("="*70)
    print("PERMEATE QUALITY TEST - ALL MEMBRANES")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Test conditions
    feed_flow = 150  # m³/h
    recovery = 0.75  # 75%
    feed_tds = 2000  # ppm
    
    print(f"\nFeed Conditions:")
    print(f"  Flow: {feed_flow} m³/h")
    print(f"  TDS: {feed_tds} ppm NaCl")
    print(f"  Target recovery: {recovery*100:.0f}%")
    
    # Membrane types
    membrane_types = [
        ('bw30_400', 'BW30-400'),
        ('eco_pro_400', 'ECO PRO-400'),
        ('cr100_pro_400', 'CR100 PRO-400'),
        ('brackish', 'Brackish (Generic)'),
        ('seawater', 'Seawater')
    ]
    
    results = []
    
    for mem_type, display_name in membrane_types:
        print(f"\n{'='*50}")
        print(f"Testing: {display_name}")
        print(f"{'='*50}")
        
        try:
            # Get membrane properties
            A_w, B_s = get_membrane_properties(mem_type)
            print(f"A_w: {A_w:.2e} m/s/Pa, B_s: {B_s:.2e} m/s")
            
            # Get configuration
            configurations = optimize_vessel_array_configuration(
                feed_flow_m3h=feed_flow,
                target_recovery=recovery,
                feed_salinity_ppm=feed_tds,
                membrane_type=mem_type,
                allow_recycle=False
            )
            
            if not configurations:
                print("No configuration found!")
                continue
            
            config = configurations[0]
            
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
            
            # Build and solve model
            m, _, _ = build_ro_model(formatted_config, feed_tds, 25.0, mem_type)
            
            solver = get_solver()
            m.fs.feed.initialize()
            
            # Initialize with appropriate pressures
            for i in range(1, formatted_config['stage_count'] + 1):
                pump = getattr(m.fs, f"pump{i}")
                ro = getattr(m.fs, f"ro_stage{i}")
                product = getattr(m.fs, f"stage_product{i}")
                
                if 'seawater' in mem_type:
                    init_pressure = (15 + i*5) * 1e5
                elif 'eco' in mem_type:
                    init_pressure = (8 + i*2) * 1e5
                else:
                    init_pressure = (10 + i*2) * 1e5
                
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
            results_solve = solver.solve(m, tee=False)
            
            if results_solve.solver.termination_condition != TerminationCondition.optimal:
                print("Initial solve failed!")
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
            results_solve = solver.solve(m, tee=False)
            
            if results_solve.solver.termination_condition == TerminationCondition.optimal:
                # Extract permeate quality
                total_perm_h2o = 0
                total_perm_tds = 0
                stage_results = []
                
                for i in range(1, formatted_config['stage_count'] + 1):
                    product = getattr(m.fs, f"stage_product{i}")
                    
                    perm_h2o = value(product.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
                    perm_tds = value(product.inlet.flow_mass_phase_comp[0, 'Liq', 'TDS'])
                    stage_tds = perm_tds / (perm_h2o + perm_tds) * 1e6
                    
                    stage_results.append({
                        'stage': i,
                        'flow_m3h': perm_h2o * 3.6,
                        'tds_ppm': stage_tds
                    })
                    
                    total_perm_h2o += perm_h2o
                    total_perm_tds += perm_tds
                
                # Overall permeate quality
                overall_tds = total_perm_tds / total_perm_h2o * 1e6
                salt_rejection = (1 - overall_tds / feed_tds) * 100
                
                # Salt passage
                salt_passage = overall_tds / feed_tds * 100
                
                # Calculate B/A ratio (indicator of selectivity)
                B_A_ratio = B_s / A_w
                
                results.append({
                    'membrane': display_name,
                    'A_w': A_w,
                    'B_s': B_s,
                    'B_A_ratio': B_A_ratio,
                    'permeate_tds': overall_tds,
                    'salt_rejection': salt_rejection,
                    'salt_passage': salt_passage,
                    'stages': stage_results
                })
                
                print(f"\nResults:")
                print(f"  Overall permeate TDS: {overall_tds:.1f} ppm")
                print(f"  Salt rejection: {salt_rejection:.2f}%")
                print(f"  Salt passage: {salt_passage:.2f}%")
                
                for stage in stage_results:
                    print(f"  Stage {stage['stage']} permeate: {stage['tds_ppm']:.1f} ppm")
                
            else:
                print("Final solve failed!")
                
        except Exception as e:
            print(f"Error: {str(e)}")
    
    # Summary table
    print("\n" + "="*70)
    print("PERMEATE QUALITY SUMMARY")
    print("="*70)
    print(f"\n{'Membrane':<25} {'Permeate TDS':<15} {'Salt Rejection':<15} {'B/A Ratio':<15}")
    print("-" * 70)
    
    for r in results:
        print(f"{r['membrane']:<25} {r['permeate_tds']:.1f} ppm{'':<7} "
              f"{r['salt_rejection']:.2f}%{'':<8} {r['B_A_ratio']:.2e}")
    
    # Detailed comparison
    print(f"\n{'='*70}")
    print("DETAILED ANALYSIS")
    print("="*70)
    
    # Sort by permeate quality
    results_sorted = sorted(results, key=lambda x: x['permeate_tds'])
    
    print("\nRanked by Permeate Quality (Best to Worst):")
    for i, r in enumerate(results_sorted, 1):
        print(f"{i}. {r['membrane']}: {r['permeate_tds']:.1f} ppm "
              f"({r['salt_rejection']:.2f}% rejection)")
    
    # Analysis of B/A ratio
    print("\nMembrane Selectivity (B/A Ratio):")
    print("Lower B/A ratio = Better salt rejection")
    results_ba_sorted = sorted(results, key=lambda x: x['B_A_ratio'])
    for r in results_ba_sorted:
        print(f"  {r['membrane']}: B/A = {r['B_A_ratio']:.2e}")
    
    # Stage-by-stage comparison for 2-stage systems
    print("\nStage-by-Stage Permeate Quality:")
    for r in results:
        print(f"\n{r['membrane']}:")
        for stage in r['stages']:
            print(f"  Stage {stage['stage']}: {stage['tds_ppm']:.1f} ppm "
                  f"({stage['flow_m3h']:.1f} m³/h)")


if __name__ == "__main__":
    test_permeate_quality()