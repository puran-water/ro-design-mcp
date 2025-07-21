#!/usr/bin/env python
"""
Simple test of 17:8 configuration using the working approach.
"""

import sys
import os
from pathlib import Path

# Disable debug mode
os.environ['WATERTAP_DEBUG_MODE'] = 'false'

sys.path.insert(0, str(Path(__file__).parent))

from utils.simulate_ro import run_ro_simulation
import pandas as pd
import json

def main():
    """Run 17:8 simulation with known working configuration."""
    print("="*80)
    print("17:8 RO ARRAY SIMULATION - SIMPLE TEST")
    print("="*80)
    
    # 17:8 configuration from optimization
    simulation_config = {
        'feed_flow_m3h': 150,
        'stage_count': 2,
        'n_stages': 2,
        'array_notation': '17:8',
        'target_recovery': 0.753,
        'achieved_recovery': 0.753,
        'total_membrane_area_m2': 6504.48,
        'total_vessels': 25,
        'stages': [
            {
                'stage_number': 1,
                'n_vessels': 17,
                'vessel_count': 17,
                'membrane_area_m2': 4423.04,
                'stage_recovery': 0.592
            },
            {
                'stage_number': 2,
                'n_vessels': 8,
                'vessel_count': 8,
                'membrane_area_m2': 2081.44,
                'stage_recovery': 0.388
            }
        ]
    }
    
    print("\nConfiguration:")
    print(f"- Array: 17:8 (17 vessels stage 1, 8 vessels stage 2)")
    print(f"- Feed flow: 150 m³/h at 2700 mg/L TDS")
    print(f"- Target recovery: {simulation_config['target_recovery']*100:.1f}%")
    print(f"- Total membrane area: {simulation_config['total_membrane_area_m2']:.0f} m²")
    
    # Use brackish membrane
    membrane_properties = {
        "membrane_type": "brackish"
    }
    
    print("\nRunning simulation with simple property package...")
    
    try:
        # Run simulation
        result = run_ro_simulation(
            configuration=simulation_config,
            feed_salinity_ppm=2700,
            feed_temperature_c=25.0,
            membrane_type="brackish",
            membrane_properties=membrane_properties,
            optimize_pumps=True,
            feed_ion_composition=None  # Use simple NaCl
        )
        
        if result.get("status") != "success":
            print(f"\nERROR: {result.get('message')}")
            if 'traceback' in result:
                print("\nTraceback:")
                print(result['traceback'])
            return
        
        print("\nSIMULATION SUCCESSFUL!")
        
        # Display results in tables
        print("\n" + "="*80)
        print("SIMULATION RESULTS")
        print("="*80)
        
        # 1. Overall Performance
        print("\n1. OVERALL SYSTEM PERFORMANCE")
        print("-" * 60)
        overall_data = {
            'Parameter': [
                'Feed Flow',
                'Feed TDS',
                'Total Recovery',
                'Permeate Flow',
                'Permeate TDS',
                'Concentrate Flow',
                'Concentrate TDS',
                'Total Power',
                'Specific Energy'
            ],
            'Value': [
                f"{result['inputs']['feed_flow_m3h']:.1f} m³/h",
                f"{result['inputs']['feed_salinity_ppm']:.0f} mg/L",
                f"{result['performance']['total_recovery']*100:.1f}%",
                f"{result['performance']['total_permeate_m3h']:.1f} m³/h",
                f"{result['performance']['avg_permeate_tds']:.0f} mg/L",
                f"{result['performance']['final_concentrate_m3h']:.1f} m³/h",
                f"{result['performance']['final_concentrate_tds']:.0f} mg/L",
                f"{result['economics']['total_power_kw']:.1f} kW",
                f"{result['economics']['specific_energy_kwh_m3']:.2f} kWh/m³"
            ]
        }
        df = pd.DataFrame(overall_data)
        print(df.to_string(index=False))
        
        # 2. Stage Performance
        print("\n\n2. STAGE-BY-STAGE PERFORMANCE")
        print("-" * 100)
        
        headers = ['Stage', 'Vessels', 'Area(m²)', 'Feed(m³/h)', 'P_feed(bar)', 
                   'TDS_feed(mg/L)', 'Perm(m³/h)', 'TDS_perm(mg/L)', 'Recovery(%)', 'Power(kW)']
        
        stage_data = []
        for stage in result['stage_results']:
            stage_data.append([
                stage['stage_number'],
                stage['vessel_count'],
                f"{stage['membrane_area_m2']:.0f}",
                f"{stage['feed_flow_m3h']:.1f}",
                f"{stage['feed_pressure_bar']:.1f}",
                f"{stage['feed_tds_ppm']:.0f}",
                f"{stage['permeate_flow_m3h']:.1f}",
                f"{stage['permeate_tds_ppm']:.0f}",
                f"{stage['recovery_achieved']*100:.1f}",
                f"{stage['pump_power_kw']:.1f}"
            ])
        
        df_stages = pd.DataFrame(stage_data, columns=headers)
        print(df_stages.to_string(index=False))
        
        # 3. Membrane Performance
        print("\n\n3. MEMBRANE PERFORMANCE")
        print("-" * 80)
        
        if 'sd_model_parameters' in result:
            mem_headers = ['Stage', 'Water Flux(LMH)', 'Salt Flux(g/m²/h)', 'NDP(bar)', 
                          'π_feed(bar)', 'π_perm(bar)', 'Rejection(%)']
            
            mem_data = []
            for i in [1, 2]:
                if f"stage_{i}" in result['sd_model_parameters']:
                    sd = result['sd_model_parameters'][f"stage_{i}"]
                    mem_data.append([
                        i,
                        f"{sd['flux_analysis']['water_flux_avg_LMH']:.1f}",
                        f"{sd['flux_analysis']['salt_flux_avg_GMH']:.2f}",
                        f"{sd['driving_forces']['net_driving_pressure_bar']:.1f}",
                        f"{sd['osmotic_pressures_bar']['feed_interface_average']:.1f}",
                        f"{sd['osmotic_pressures_bar']['permeate']:.1f}",
                        f"{sd['performance']['salt_rejection']*100:.1f}"
                    ])
            
            df_mem = pd.DataFrame(mem_data, columns=mem_headers)
            print(df_mem.to_string(index=False))
        
        # 4. Mass Balance
        print("\n\n4. MASS BALANCE")
        print("-" * 60)
        mb_data = {
            'Stream': ['Feed', 'Total Permeate', 'Concentrate', 'Balance Error'],
            'Flow (m³/h)': [
                f"{result['mass_balance']['feed_flow_m3h']:.2f}",
                f"{result['mass_balance']['total_permeate_m3h']:.2f}",
                f"{result['mass_balance']['concentrate_flow_m3h']:.2f}",
                f"{result['mass_balance']['flow_balance_m3h']:.2e}"
            ],
            'Salt (kg/h)': [
                f"{result['mass_balance']['feed_salt_kgh']:.2f}",
                f"{result['mass_balance']['permeate_salt_kgh']:.2f}",
                f"{result['mass_balance']['concentrate_salt_kgh']:.2f}",
                f"{result['mass_balance']['salt_balance_kgh']:.2e}"
            ]
        }
        df_mb = pd.DataFrame(mb_data)
        print(df_mb.to_string(index=False))
        
        # 5. Economic Summary
        print("\n\n5. ECONOMIC SUMMARY")
        print("-" * 60)
        annual_hours = 8760
        electricity_cost = 0.10  # $/kWh
        
        econ_data = {
            'Parameter': [
                'Total Power',
                'Specific Energy',
                'Energy Cost per m³',
                'Daily Energy Cost',
                'Annual Energy Cost',
                'Water Production Cost'
            ],
            'Value': [
                f"{result['economics']['total_power_kw']:.1f} kW",
                f"{result['economics']['specific_energy_kwh_m3']:.2f} kWh/m³",
                f"${result['economics']['specific_energy_kwh_m3'] * electricity_cost:.3f}/m³",
                f"${result['economics']['total_power_kw'] * 24 * electricity_cost:.0f}/day",
                f"${result['economics']['total_power_kw'] * annual_hours * electricity_cost:,.0f}/year",
                f"${result['economics']['specific_energy_kwh_m3'] * electricity_cost:.3f}/m³"
            ]
        }
        df_econ = pd.DataFrame(econ_data)
        print(df_econ.to_string(index=False))
        
        print("\n" + "="*80)
        print("SIMULATION COMPLETE")
        print("="*80)
        
        # Save results
        with open('17_8_results.json', 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print("\nDetailed results saved to: 17_8_results.json")
        
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()