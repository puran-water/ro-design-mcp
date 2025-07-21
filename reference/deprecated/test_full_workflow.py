#!/usr/bin/env python3
"""
Test full RO workflow from configuration to simulation for multiple scenarios.
"""

import sys
import json
from tabulate import tabulate
from utils.optimize_ro import optimize_vessel_array_configuration
from utils.simulate_ro import run_ro_simulation

# Test scenarios
scenarios = [
    # Scenario 1: Low recovery brackish water
    {
        "name": "Low Recovery Brackish",
        "feed_flow_m3h": 150,
        "target_recovery": 0.50,
        "feed_salinity_ppm": 2000,
        "membrane_type": "brackish",
        "feed_temperature_c": 25
    },
    # Scenario 2: Medium recovery brackish water
    {
        "name": "Medium Recovery Brackish",
        "feed_flow_m3h": 150,
        "target_recovery": 0.65,
        "feed_salinity_ppm": 2000,
        "membrane_type": "brackish",
        "feed_temperature_c": 25
    },
    # Scenario 3: High recovery brackish water
    {
        "name": "High Recovery Brackish",
        "feed_flow_m3h": 150,
        "target_recovery": 0.75,
        "feed_salinity_ppm": 2000,
        "membrane_type": "brackish",
        "feed_temperature_c": 25
    },
    # Scenario 4: Seawater low recovery
    {
        "name": "Seawater Low Recovery",
        "feed_flow_m3h": 100,
        "target_recovery": 0.40,
        "feed_salinity_ppm": 35000,
        "membrane_type": "seawater",
        "feed_temperature_c": 25
    },
    # Scenario 5: Seawater standard recovery
    {
        "name": "Seawater Standard",
        "feed_flow_m3h": 100,
        "target_recovery": 0.45,
        "feed_salinity_ppm": 35000,
        "membrane_type": "seawater",
        "feed_temperature_c": 25
    },
    # Scenario 6: High salinity brackish
    {
        "name": "High TDS Brackish",
        "feed_flow_m3h": 120,
        "target_recovery": 0.60,
        "feed_salinity_ppm": 10000,
        "membrane_type": "brackish",
        "feed_temperature_c": 25
    }
]

def get_ion_composition(salinity_ppm, membrane_type):
    """Get ion composition based on salinity and water type."""
    # Use simple NaCl for now to avoid FBBT issues
    # Na: 23, Cl: 35.5, so NaCl is 58.5
    # For electroneutrality: Na+ mass fraction = 23/58.5 = 0.393
    # Cl- mass fraction = 35.5/58.5 = 0.607
    
    na_fraction = 0.393
    cl_fraction = 0.607
    
    return {
        'Na_+': salinity_ppm * na_fraction,
        'Cl_-': salinity_ppm * cl_fraction
    }

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
        "membrane": scenario['membrane_type']
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
                "configuration": "-"
            })
            return results
        
        # Select best configuration (usually first one)
        best_config = config_result[0]
        print(f"Selected configuration: {best_config['array_notation']}")
        print(f"  Stages: {best_config['n_stages']}")
        print(f"  Expected recovery: {best_config['total_recovery']:.1%}")
        if best_config.get('recycle_info', {}).get('uses_recycle'):
            print(f"  Recycle ratio: {best_config['recycle_info']['recycle_ratio']:.1%}")
        
        results["configuration"] = best_config['array_notation']
        results["config_status"] = "Success"
        results["n_stages"] = best_config['n_stages']
        
        # Step 2: Run simulation
        print("\nStep 2: Running WaterTAP simulation...")
        
        # Get ion composition
        ion_composition = get_ion_composition(
            scenario['feed_salinity_ppm'],
            scenario['membrane_type']
        )
        
        sim_result = run_ro_simulation(
            configuration=best_config,
            feed_salinity_ppm=scenario['feed_salinity_ppm'],
            feed_ion_composition=ion_composition,
            feed_temperature_c=scenario['feed_temperature_c'],
            membrane_type=scenario['membrane_type'],
            optimize_pumps=True
        )
        
        if sim_result['status'] == 'success':
            results.update({
                "sim_status": "Success",
                "achieved_recovery": sim_result['performance']['system_recovery'],
                "permeate_tds": sim_result['performance']['total_permeate_tds_mg_l'],
                "energy_kwh_m3": sim_result['performance']['specific_energy_kWh_m3'],
                "stages": len(sim_result['stage_results'])
            })
            
            # Print stage details
            print("\nStage Results:")
            for i, stage in enumerate(sim_result['stage_results']):
                print(f"  Stage {i+1}: Recovery={stage['recovery']:.1%}, "
                      f"Pressure={stage['feed_pressure_bar']:.1f} bar")
        else:
            results.update({
                "sim_status": "Failed",
                "achieved_recovery": "-",
                "permeate_tds": "-",
                "energy_kwh_m3": "-"
            })
            print(f"Simulation failed: {sim_result.get('message', 'Unknown error')}")
            
    except Exception as e:
        print(f"Error in scenario: {str(e)}")
        import traceback
        traceback.print_exc()
        results.update({
            "config_status": "Error",
            "sim_status": "-",
            "achieved_recovery": "-",
            "permeate_tds": "-",
            "energy_kwh_m3": "-",
            "configuration": "-"
        })
    
    return results

def main():
    """Run all scenarios and display results."""
    print("Running comprehensive RO workflow tests...")
    print(f"Testing {len(scenarios)} scenarios\n")
    
    all_results = []
    
    for scenario in scenarios:
        result = run_scenario(scenario)
        all_results.append(result)
    
    # Display results table
    print("\n" + "="*100)
    print("SUMMARY OF RESULTS")
    print("="*100)
    
    # Prepare table data
    table_data = []
    for r in all_results:
        table_data.append([
            r['scenario'],
            f"{r['feed_flow']:.0f}",
            f"{r['target_recovery']:.0%}",
            f"{r['feed_tds']:,}",
            r['membrane'],
            r['configuration'],
            r['config_status'],
            r['sim_status'],
            f"{r['achieved_recovery']:.1%}" if r['achieved_recovery'] != '-' else '-',
            f"{r['permeate_tds']:.0f}" if r['permeate_tds'] != '-' else '-',
            f"{r['energy_kwh_m3']:.2f}" if r['energy_kwh_m3'] != '-' else '-'
        ])
    
    headers = [
        "Scenario", "Flow\n(m³/h)", "Target\nRecovery", "Feed TDS\n(ppm)", 
        "Membrane", "Config", "Config\nStatus", "Sim\nStatus", 
        "Achieved\nRecovery", "Permeate\nTDS (mg/L)", "Energy\n(kWh/m³)"
    ]
    
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    
    # Summary statistics
    successful_sims = sum(1 for r in all_results if r['sim_status'] == 'Success')
    print(f"\nSuccess Rate: {successful_sims}/{len(scenarios)} scenarios completed successfully")
    
    # Save detailed results to JSON
    with open('workflow_test_results.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    print("\nDetailed results saved to workflow_test_results.json")

if __name__ == "__main__":
    main()