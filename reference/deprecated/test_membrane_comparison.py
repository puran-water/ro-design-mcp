#!/usr/bin/env python3
"""
Test RO workflow with different membrane types for comparison.
"""

import sys
import json
from tabulate import tabulate
from utils.optimize_ro import optimize_vessel_array_configuration
from utils.simulate_ro import run_ro_simulation

# Test scenarios with different membrane types
scenarios = [
    # Brackish water @ 2000 ppm - standard membrane
    {
        "name": "BW30-400 @ 2000ppm",
        "feed_flow_m3h": 150,
        "target_recovery": 0.75,
        "feed_salinity_ppm": 2000,
        "membrane_type": "brackish",
        "custom_membrane": "bw30_400",
        "feed_temperature_c": 25
    },
    # Brackish water @ 2000 ppm - high flux membrane
    {
        "name": "ECO-PRO-400 @ 2000ppm",
        "feed_flow_m3h": 150,
        "target_recovery": 0.75,
        "feed_salinity_ppm": 2000,
        "membrane_type": "brackish",
        "custom_membrane": "eco_pro_400",
        "feed_temperature_c": 25
    },
    # Brackish water @ 5000 ppm - standard
    {
        "name": "BW30-400 @ 5000ppm",
        "feed_flow_m3h": 150,
        "target_recovery": 0.70,
        "feed_salinity_ppm": 5000,
        "membrane_type": "brackish",
        "custom_membrane": "bw30_400",
        "feed_temperature_c": 25
    },
    # Brackish water @ 5000 ppm - high flux
    {
        "name": "ECO-PRO-400 @ 5000ppm",
        "feed_flow_m3h": 150,
        "target_recovery": 0.70,
        "feed_salinity_ppm": 5000,
        "membrane_type": "brackish",
        "custom_membrane": "eco_pro_400",
        "feed_temperature_c": 25
    },
    # Seawater - standard flux
    {
        "name": "SW30XLE @ 35000ppm",
        "feed_flow_m3h": 100,
        "target_recovery": 0.45,
        "feed_salinity_ppm": 35000,
        "membrane_type": "seawater",
        "custom_membrane": None,  # Use default seawater
        "feed_temperature_c": 25
    },
    # High salinity brackish
    {
        "name": "BW30-400 @ 10000ppm",
        "feed_flow_m3h": 120,
        "target_recovery": 0.60,
        "feed_salinity_ppm": 10000,
        "membrane_type": "brackish",
        "custom_membrane": "bw30_400",
        "feed_temperature_c": 25
    }
]

def get_simple_ion_composition(salinity_ppm):
    """Get simple NaCl composition."""
    na_fraction = 0.393
    cl_fraction = 0.607
    
    return {
        'Na_+': salinity_ppm * na_fraction,
        'Cl_-': salinity_ppm * cl_fraction
    }

def get_membrane_properties(membrane_name):
    """Get membrane properties by name."""
    # From config file values
    membrane_props = {
        "bw30_400": {
            "A_w": 9.63e-12,  # m/s/Pa
            "B_s": 5.58e-8    # m/s
        },
        "eco_pro_400": {
            "A_w": 1.60e-11,  # m/s/Pa - higher flux
            "B_s": 4.24e-8    # m/s - slightly better rejection
        },
        "cr100_pro_400": {
            "A_w": 1.06e-11,  # m/s/Pa
            "B_s": 4.16e-8    # m/s
        },
        "seawater": {
            "A_w": 3.0e-12,   # m/s/Pa - lower flux
            "B_s": 1.5e-8     # m/s - much better rejection
        }
    }
    
    return membrane_props.get(membrane_name)

def run_scenario(scenario):
    """Run a single scenario through configuration and simulation."""
    print(f"\n{'='*60}")
    print(f"Running: {scenario['name']}")
    print(f"{'='*60}")
    
    results = {
        "scenario": scenario['name'],
        "feed_flow": scenario['feed_flow_m3h'],
        "target_recovery": scenario['target_recovery'],
        "feed_tds": scenario['feed_salinity_ppm'],
        "membrane": scenario.get('custom_membrane', scenario['membrane_type'])
    }
    
    try:
        # Step 1: Configure RO system
        print("\nStep 1: Configuring RO system...")
        config_result = optimize_vessel_array_configuration(
            feed_flow_m3h=scenario['feed_flow_m3h'],
            target_recovery=scenario['target_recovery'],
            feed_salinity_ppm=scenario['feed_salinity_ppm'],
            membrane_type=scenario['membrane_type'],
            allow_recycle=True,
            max_recycle_ratio=0.9
        )
        
        if not config_result:
            print(f"Configuration failed: No configurations found")
            results.update({
                "config_status": "Failed",
                "sim_status": "-",
                "achieved_recovery": "-",
                "permeate_tds": "-",
                "energy_kwh_m3": "-",
                "max_pressure_bar": "-",
                "configuration": "-",
                "total_area_m2": "-"
            })
            return results
        
        # Select best configuration
        best_config = config_result[0]
        print(f"Selected configuration: {best_config['array_notation']}")
        print(f"  Stages: {best_config['n_stages']}")
        print(f"  Expected recovery: {best_config['total_recovery']:.1%}")
        
        # Calculate total membrane area
        total_area = sum(stage['membrane_area_m2'] for stage in best_config['stages'])
        
        results["configuration"] = best_config['array_notation']
        results["config_status"] = "Success"
        results["n_stages"] = best_config['n_stages']
        results["total_area_m2"] = total_area
        
        # Step 2: Run simulation
        print("\nStep 2: Running WaterTAP simulation...")
        
        # Get ion composition
        ion_composition = get_simple_ion_composition(scenario['feed_salinity_ppm'])
        
        # Get custom membrane properties if specified
        membrane_properties = None
        if scenario.get('custom_membrane'):
            props = get_membrane_properties(scenario['custom_membrane'])
            if props:
                membrane_properties = props
                print(f"Using custom membrane: {scenario['custom_membrane']}")
        
        sim_result = run_ro_simulation(
            configuration=best_config,
            feed_salinity_ppm=scenario['feed_salinity_ppm'],
            feed_ion_composition=ion_composition,
            feed_temperature_c=scenario['feed_temperature_c'],
            membrane_type=scenario['membrane_type'],
            membrane_properties=membrane_properties,
            optimize_pumps=True
        )
        
        if sim_result['status'] == 'success':
            # Find maximum pressure
            max_pressure = max(
                stage['feed_pressure_bar'] 
                for stage in sim_result['stage_results']
            )
            
            results.update({
                "sim_status": "Success",
                "achieved_recovery": sim_result['performance']['system_recovery'],
                "permeate_tds": sim_result['performance']['total_permeate_tds_mg_l'],
                "energy_kwh_m3": sim_result['performance']['specific_energy_kWh_m3'],
                "max_pressure_bar": max_pressure,
                "stages": len(sim_result['stage_results'])
            })
            
            # Print stage details
            print("\nStage Results:")
            for i, stage in enumerate(sim_result['stage_results']):
                print(f"  Stage {i+1}: Recovery={stage['recovery']:.1%}, "
                      f"Pressure={stage['feed_pressure_bar']:.1f} bar, "
                      f"Flux={stage['average_flux_lmh']:.1f} LMH")
        else:
            results.update({
                "sim_status": "Failed",
                "achieved_recovery": "-",
                "permeate_tds": "-",
                "energy_kwh_m3": "-",
                "max_pressure_bar": "-"
            })
            print(f"Simulation failed: {sim_result.get('message', 'Unknown error')}")
            
    except Exception as e:
        print(f"Error in scenario: {str(e)}")
        results.update({
            "config_status": "Error",
            "sim_status": "-",
            "achieved_recovery": "-",
            "permeate_tds": "-",
            "energy_kwh_m3": "-",
            "max_pressure_bar": "-",
            "configuration": "-",
            "total_area_m2": "-"
        })
    
    return results

def main():
    """Run all scenarios and display results."""
    print("Comparing RO performance with different membrane types...")
    print(f"Testing {len(scenarios)} scenarios\n")
    
    all_results = []
    
    for scenario in scenarios:
        result = run_scenario(scenario)
        all_results.append(result)
    
    # Display results table
    print("\n" + "="*120)
    print("MEMBRANE COMPARISON RESULTS")
    print("="*120)
    
    # Prepare table data
    table_data = []
    for r in all_results:
        table_data.append([
            r['scenario'],
            f"{r['feed_flow']:.0f}",
            f"{r['target_recovery']:.0%}",
            f"{r['feed_tds']:,}",
            r['configuration'],
            f"{r['total_area_m2']:.0f}" if r.get('total_area_m2') != '-' else '-',
            f"{r['achieved_recovery']:.1%}" if r['achieved_recovery'] != '-' else '-',
            f"{r['permeate_tds']:.0f}" if r['permeate_tds'] != '-' else '-',
            f"{r['energy_kwh_m3']:.2f}" if r['energy_kwh_m3'] != '-' else '-',
            f"{r['max_pressure_bar']:.1f}" if r.get('max_pressure_bar') != '-' else '-'
        ])
    
    headers = [
        "Scenario", "Flow\n(m³/h)", "Target\nRecovery", "Feed TDS\n(ppm)", 
        "Config", "Total Area\n(m²)", "Achieved\nRecovery", 
        "Permeate\nTDS (mg/L)", "Energy\n(kWh/m³)", "Max Press.\n(bar)"
    ]
    
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    
    # Membrane comparison for 2000 ppm scenarios
    print("\n" + "="*80)
    print("MEMBRANE PERFORMANCE COMPARISON @ 2000 ppm TDS")
    print("="*80)
    
    bw30_2000 = next((r for r in all_results if "BW30-400 @ 2000ppm" in r['scenario']), None)
    eco_2000 = next((r for r in all_results if "ECO-PRO-400 @ 2000ppm" in r['scenario']), None)
    
    if bw30_2000 and eco_2000 and bw30_2000['sim_status'] == 'Success' and eco_2000['sim_status'] == 'Success':
        comparison_data = [
            ["Metric", "BW30-400", "ECO-PRO-400", "Difference"],
            ["Configuration", bw30_2000['configuration'], eco_2000['configuration'], "-"],
            ["Total Area (m²)", f"{bw30_2000['total_area_m2']:.0f}", f"{eco_2000['total_area_m2']:.0f}", 
             f"{((eco_2000['total_area_m2']/bw30_2000['total_area_m2'])-1)*100:+.1f}%"],
            ["Energy (kWh/m³)", f"{bw30_2000['energy_kwh_m3']:.2f}", f"{eco_2000['energy_kwh_m3']:.2f}", 
             f"{((eco_2000['energy_kwh_m3']/bw30_2000['energy_kwh_m3'])-1)*100:+.1f}%"],
            ["Permeate TDS (mg/L)", f"{bw30_2000['permeate_tds']:.0f}", f"{eco_2000['permeate_tds']:.0f}", 
             f"{((eco_2000['permeate_tds']/bw30_2000['permeate_tds'])-1)*100:+.1f}%"],
            ["Max Pressure (bar)", f"{bw30_2000['max_pressure_bar']:.1f}", f"{eco_2000['max_pressure_bar']:.1f}", 
             f"{eco_2000['max_pressure_bar']-bw30_2000['max_pressure_bar']:+.1f}"]
        ]
        
        print(tabulate(comparison_data[1:], headers=comparison_data[0], tablefmt="grid"))
    
    # Save detailed results
    with open('membrane_comparison_results.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    print("\nDetailed results saved to membrane_comparison_results.json")

if __name__ == "__main__":
    main()