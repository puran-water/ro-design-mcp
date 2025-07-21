#!/usr/bin/env python3
"""
Test the simplified simulation approach with 2000 ppm ECO PRO-400 case.
This should match the results from WORKFLOW_SUCCESS_2000PPM.md
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


def test_simplified_approach():
    """Test simplified simulation with the documented successful case."""
    
    print("="*70)
    print("TEST SIMPLIFIED SIMULATION APPROACH")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Test parameters from successful workflow
    feed_flow = 150  # m³/h
    recovery = 0.75  # 75%
    feed_tds = 2000  # ppm
    membrane_type = 'eco_pro_400'
    
    print(f"\nTest Case (from WORKFLOW_SUCCESS_2000PPM.md):")
    print(f"  Feed: {feed_flow} m³/h at {feed_tds} ppm")
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
        allow_recycle=False
    )
    
    if not configurations:
        print("ERROR: No configurations found!")
        return False
    
    config = configurations[0]
    print(f"\nConfiguration Result:")
    print(f"  Array: {config['array_notation']}")
    print(f"  Expected: 17:8 (from successful workflow)")
    print(f"  Total recovery: {config['total_recovery']*100:.1f}%")
    
    # Verify configuration matches documented case
    if config['array_notation'] != '17:8':
        print(f"WARNING: Configuration mismatch! Got {config['array_notation']}, expected 17:8")
    
    # Step 2: Simulation using simplified approach
    print(f"\n{'='*50}")
    print("STEP 2: SIMPLIFIED SIMULATION")
    print(f"{'='*50}")
    
    print("\nRunning simulation with simplified approach...")
    
    # Run simulation with new approach
    sim_results = run_ro_simulation(
        configuration=config,
        feed_salinity_ppm=feed_tds,
        feed_temperature_c=25.0,
        membrane_type=membrane_type,
        optimize_pumps=True,
        use_direct_simulation=True  # This triggers simplified approach
    )
    
    # Check results
    if sim_results.get('status') != 'success':
        print(f"\nERROR: Simulation failed!")
        print(f"Status: {sim_results.get('status')}")
        print(f"Error: {sim_results.get('error', 'Unknown error')}")
        print(f"Message: {sim_results.get('message', '')}")
        return False
    
    print("\nSimulation successful!")
    
    # Extract and display results
    print(f"\n{'='*50}")
    print("SIMULATION RESULTS")
    print(f"{'='*50}")
    
    # Overall performance
    performance = sim_results.get('performance', {})
    economics = sim_results.get('economics', {})
    
    print(f"\nOverall Performance:")
    print(f"  Total recovery: {performance.get('total_recovery', 0)*100:.1f}%")
    print(f"  Permeate flow: {performance.get('permeate_flow_m3h', 0):.1f} m³/h")
    print(f"  Permeate TDS: {performance.get('permeate_tds_ppm', 0):.0f} ppm")
    print(f"  Total power: {economics.get('total_power_kw', 0):.1f} kW")
    print(f"  Specific energy: {economics.get('specific_energy_kwh_m3', 0):.2f} kWh/m³")
    
    # Stage results
    print(f"\nStage Results:")
    for stage in sim_results.get('stage_results', []):
        print(f"\n  Stage {stage['stage_number']}:")
        print(f"    Pressure: {stage['feed_pressure_bar']:.1f} bar")
        print(f"    Recovery: {stage['recovery']*100:.1f}%")
        print(f"    Water flux: {stage['water_flux_kg_m2_s']:.4f} kg/m²/s")
        print(f"    Power: {stage['power_kw']:.1f} kW")
    
    # Compare with documented results
    print(f"\n{'='*50}")
    print("COMPARISON WITH DOCUMENTED RESULTS")
    print(f"{'='*50}")
    
    documented = {
        'stage1_pressure': 6.8,
        'stage2_pressure': 8.2,
        'total_recovery': 0.754,
        'permeate_flow': 112.9,
        'permeate_tds': 36,
        'total_power': 34.6,
        'specific_energy': 0.31
    }
    
    print(f"\n{'Metric':<25} {'Simulated':<15} {'Documented':<15} {'Match':<10}")
    print("-" * 65)
    
    # Stage pressures
    if len(sim_results.get('stage_results', [])) >= 2:
        stage1_pressure = sim_results['stage_results'][0]['feed_pressure_bar']
        stage2_pressure = sim_results['stage_results'][1]['feed_pressure_bar']
        
        print(f"{'Stage 1 Pressure (bar)':<25} {stage1_pressure:<15.1f} {documented['stage1_pressure']:<15.1f} "
              f"{'PASS' if abs(stage1_pressure - documented['stage1_pressure']) < 0.5 else 'FAIL':<10}")
        
        print(f"{'Stage 2 Pressure (bar)':<25} {stage2_pressure:<15.1f} {documented['stage2_pressure']:<15.1f} "
              f"{'PASS' if abs(stage2_pressure - documented['stage2_pressure']) < 0.5 else 'FAIL':<10}")
    
    # Other metrics
    metrics = [
        ('Total Recovery (%)', performance.get('total_recovery', 0)*100, documented['total_recovery']*100, 1),
        ('Permeate Flow (m³/h)', performance.get('permeate_flow_m3h', 0), documented['permeate_flow'], 2),
        ('Permeate TDS (ppm)', performance.get('permeate_tds_ppm', 0), documented['permeate_tds'], 5),
        ('Total Power (kW)', economics.get('total_power_kw', 0), documented['total_power'], 2),
        ('Specific Energy (kWh/m³)', economics.get('specific_energy_kwh_m3', 0), documented['specific_energy'], 0.05)
    ]
    
    all_match = True
    for name, simulated, expected, tolerance in metrics:
        match = abs(simulated - expected) <= tolerance
        print(f"{name:<25} {simulated:<15.2f} {expected:<15.2f} {'PASS' if match else 'FAIL':<10}")
        if not match:
            all_match = False
    
    print("\n" + "="*70)
    if all_match:
        print("SUCCESS: All metrics match documented results within tolerance!")
        print("The simplified simulation approach is working correctly.")
    else:
        print("WARNING: Some metrics don't match documented results.")
        print("Further investigation may be needed.")
    print("="*70)
    
    # Save results for debugging
    with open('simplified_simulation_results.json', 'w') as f:
        json.dump({
            'configuration': config,
            'simulation_results': sim_results,
            'documented_values': documented,
            'test_status': 'PASS' if all_match else 'FAIL'
        }, f, indent=2)
    
    print(f"\nResults saved to simplified_simulation_results.json")
    
    return all_match


if __name__ == "__main__":
    success = test_simplified_approach()
    sys.exit(0 if success else 1)