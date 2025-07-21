#!/usr/bin/env python3
"""
Test complete MCP server workflow for 2000 ppm NaCl feed.
Configuration -> Simulation with ion composition.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.optimize_ro import optimize_vessel_array_configuration
from utils.simulate_ro import run_ro_simulation
from utils.membrane_properties_handler import get_membrane_properties


def main():
    """Run complete workflow from configuration to simulation."""
    
    print("="*70)
    print("MCP SERVER WORKFLOW TEST")
    print("Feed: 150 m³/h, 2000 ppm NaCl, 75% recovery target")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Test parameters
    feed_flow = 150  # m³/h
    recovery = 0.75  # 75%
    feed_tds = 2000  # ppm NaCl
    feed_temperature = 25.0  # °C
    
    # Ion composition for NaCl (mg/L)
    # Molecular weights: Na+ = 22.99, Cl- = 35.45, NaCl = 58.44
    # For 2000 ppm NaCl:
    na_fraction = 22.99 / 58.44  # 0.393
    cl_fraction = 35.45 / 58.44  # 0.607
    
    feed_ion_composition = {
        'Na+': feed_tds * na_fraction,  # ~786 mg/L
        'Cl-': feed_tds * cl_fraction   # ~1214 mg/L
    }
    
    print(f"\nFeed Conditions:")
    print(f"  Flow: {feed_flow} m³/h")
    print(f"  TDS: {feed_tds} ppm (NaCl)")
    print(f"  Temperature: {feed_temperature} °C")
    print(f"  Target recovery: {recovery*100:.0f}%")
    print(f"\nIon Composition:")
    print(f"  Na+: {feed_ion_composition['Na+']:.0f} mg/L")
    print(f"  Cl-: {feed_ion_composition['Cl-']:.0f} mg/L")
    
    # Try different membrane types
    membrane_types = [
        ('bw30_400', 'BW30-400 (Standard Brackish)'),
        ('eco_pro_400', 'ECO PRO-400 (High Permeability)'),
    ]
    
    for membrane_code, display_name in membrane_types:
        print(f"\n{'='*70}")
        print(f"TESTING {display_name}")
        print(f"{'='*70}")
        
        # Get membrane properties
        A_w, B_s = get_membrane_properties(membrane_code)
        print(f"\nMembrane properties:")
        print(f"  A_w: {A_w:.2e} m/s/Pa")
        print(f"  B_s: {B_s:.2e} m/s")
        
        # Step 1: Configuration
        print(f"\n1. CONFIGURATION STAGE")
        print(f"   Running configuration optimization...")
        
        try:
            # Call optimization
            configurations = optimize_vessel_array_configuration(
                feed_flow_m3h=feed_flow,
                target_recovery=recovery,
                feed_salinity_ppm=feed_tds,
                membrane_type=membrane_code,
                allow_recycle=True,
                max_recycle_ratio=0.5
            )
            
            if not configurations:
                print("   ERROR: No configurations found!")
                continue
            
            # Select best configuration
            config = configurations[0] if isinstance(configurations, list) else configurations
            
            print(f"\n   Configuration Result:")
            print(f"   - Array: {config['array_notation']}")
            print(f"   - Stage count: {config['n_stages']}")
            print(f"   - Total recovery: {config['total_recovery']*100:.1f}%")
            print(f"   - Has recycle: {config.get('recycle_ratio', 0) > 0}")
            if config.get('recycle_ratio', 0) > 0:
                print(f"   - Recycle ratio: {config.get('recycle_ratio', 0)*100:.1f}%")
            
            # Format configuration for simulation
            formatted_config = {
                'success': True,
                'stage_count': config['n_stages'],
                'has_recycle': config.get('recycle_ratio', 0) > 0,
                'recycle_ratio': config.get('recycle_ratio', 0),
                'array_notation': config.get('array_notation', f"{config['n_stages']}-stage"),
                'feed_flow_m3h': config['feed_flow_m3h'],
                'stages': []
            }
            
            # Add stage details
            total_area = 0
            print(f"\n   Stage Details:")
            for stage in config['stages']:
                stage_info = {
                    'stage_number': stage['stage_number'],
                    'vessels': stage['n_vessels'],
                    'membrane_area_m2': stage['membrane_area_m2'],
                    'feed_flow_m3h': stage['feed_flow_m3h'],
                    'permeate_flow_m3h': stage['permeate_flow_m3h'],
                    'stage_recovery': stage['stage_recovery'],
                    'expected_flux_lmh': stage['design_flux_lmh']
                }
                formatted_config['stages'].append(stage_info)
                
                print(f"   Stage {stage['stage_number']}:")
                print(f"     - Recovery: {stage['stage_recovery']*100:.1f}%")
                print(f"     - Vessels: {stage['n_vessels']}")
                print(f"     - Area: {stage['membrane_area_m2']:.0f} m²")
                print(f"     - Design flux: {stage['design_flux_lmh']:.1f} LMH")
                
                total_area += stage['membrane_area_m2']
            
            print(f"\n   Total membrane area: {total_area:.0f} m²")
            print(f"   Specific area: {total_area/(feed_flow*recovery):.1f} m²/(m³/h)")
            
        except Exception as e:
            print(f"   Configuration error: {str(e)}")
            import traceback
            traceback.print_exc()
            continue
        
        # Step 2: Simulation with ion composition
        print(f"\n2. SIMULATION STAGE")
        print(f"   Running simulation with ion composition...")
        
        try:
            # First try with ion composition (MCAS)
            print(f"   Attempting MCAS simulation with detailed ion modeling...")
            
            sim_result = run_ro_simulation(
                configuration=formatted_config,
                feed_salinity_ppm=feed_tds,
                feed_temperature_c=feed_temperature,
                membrane_type=membrane_code,
                membrane_properties=None,
                optimize_pumps=True,
                feed_ion_composition=feed_ion_composition,
                initialization_strategy="sequential",
                use_direct_simulation=False  # MCAS requires notebook
            )
            
            if sim_result.get('status') == 'success':
                print(f"\n   MCAS Simulation Results:")
                display_simulation_results(sim_result)
            else:
                # Fallback to simple simulation
                print(f"\n   MCAS simulation failed: {sim_result.get('message', 'Unknown error')}")
                print(f"   Falling back to simple TDS simulation...")
                
                sim_result = run_ro_simulation(
                    configuration=formatted_config,
                    feed_salinity_ppm=feed_tds,
                    feed_temperature_c=feed_temperature,
                    membrane_type=membrane_code,
                    membrane_properties=None,
                    optimize_pumps=True,
                    feed_ion_composition=None,  # No ion composition
                    use_direct_simulation=True  # Use direct approach
                )
                
                if sim_result.get('status') == 'success':
                    print(f"\n   Simple Simulation Results:")
                    display_simulation_results(sim_result)
                else:
                    print(f"   Simple simulation also failed: {sim_result.get('message', 'Unknown error')}")
                    
        except Exception as e:
            print(f"   Simulation error: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*70}")
    print("WORKFLOW COMPLETE")
    print(f"{'='*70}")


def display_simulation_results(sim_result):
    """Display simulation results in a formatted way."""
    perf = sim_result.get('performance', {})
    econ = sim_result.get('economics', {})
    
    print(f"   Overall Performance:")
    print(f"     - Recovery: {perf.get('total_recovery', 0)*100:.1f}%")
    print(f"     - Permeate flow: {perf.get('permeate_flow_m3h', 0):.1f} m³/h")
    print(f"     - Permeate TDS: {perf.get('permeate_tds_ppm', 0):.0f} ppm")
    print(f"     - Total power: {perf.get('total_pump_power_kw', 0):.1f} kW")
    print(f"     - Specific energy: {econ.get('specific_energy_kwh_m3', 0):.2f} kWh/m³")
    
    print(f"\n   Stage Operating Conditions:")
    for stage in sim_result.get('stage_results', []):
        print(f"   Stage {stage['stage_number']}:")
        print(f"     - Feed pressure: {stage['feed_pressure_bar']:.1f} bar")
        print(f"     - Recovery: {stage['recovery']*100:.1f}%")
        print(f"     - Permeate TDS: {stage['permeate_tds_ppm']:.0f} ppm")
        
    # Ion composition in permeate if available
    if 'ion_composition' in sim_result:
        print(f"\n   Permeate Ion Composition:")
        for ion, conc in sim_result['ion_composition'].items():
            print(f"     - {ion}: {conc:.1f} mg/L")


if __name__ == "__main__":
    main()