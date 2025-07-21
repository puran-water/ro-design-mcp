#!/usr/bin/env python
"""Test direct simulation workflow."""

import sys
from pathlib import Path
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.optimize_ro import optimize_vessel_array_configuration
from utils.simulate_ro import run_ro_simulation


def test_direct_workflow():
    """Test complete workflow using direct simulation."""
    
    print("="*70)
    print("TESTING DIRECT SIMULATION WORKFLOW")
    print(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Test parameters
    feed_flow = 150  # m³/h
    recovery = 0.75  # 75%
    feed_tds = 2000  # ppm
    
    print(f"\nTest Conditions:")
    print(f"  Feed flow: {feed_flow} m³/h")
    print(f"  Recovery: {recovery*100:.0f}%")
    print(f"  Feed TDS: {feed_tds} ppm")
    
    try:
        # Step 1: Configuration
        print("\n" + "-"*50)
        print("Step 1: Optimizing RO Configuration")
        print("-"*50)
        
        configurations = optimize_vessel_array_configuration(
            feed_flow_m3h=feed_flow,
            target_recovery=recovery,
            feed_salinity_ppm=feed_tds,
            membrane_type="brackish"
        )
        
        if not configurations:
            print("No viable configurations found!")
            return False
            
        print(f"Found {len(configurations)} configurations")
        
        # Use first configuration
        config = configurations[0]
        print(f"Using configuration: {config['array_notation']}")
        
        # Step 2: Simulation
        print("\n" + "-"*50)
        print("Step 2: Running Simulation")
        print("-"*50)
        
        # Test each membrane type
        membrane_types = ["bw30_400", "eco_pro_400", "cr100_pro_400"]
        
        results = {}
        for mem_type in membrane_types:
            print(f"\nTesting {mem_type}...")
            
            sim_result = run_ro_simulation(
                configuration=config,
                feed_salinity_ppm=feed_tds,
                feed_temperature_c=25.0,
                membrane_type=mem_type,
                optimize_pumps=True,
                use_direct_simulation=True  # Force direct simulation
            )
            
            results[mem_type] = sim_result
            
            if sim_result['status'] == 'success':
                print(f"  [SUCCESS]")
                print(f"    Recovery: {sim_result['performance']['total_recovery']:.1%}")
                print(f"    Permeate TDS: {sim_result['performance']['permeate_tds']:.0f} ppm")
                print(f"    Energy: {sim_result['economics']['specific_energy_kwh_m3']:.2f} kWh/m3")
            else:
                print(f"  [FAILED]: {sim_result.get('message', 'Unknown error')}")
                
        # Summary
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        
        success_count = sum(1 for r in results.values() if r['status'] == 'success')
        print(f"Successful simulations: {success_count}/{len(membrane_types)}")
        
        if success_count == len(membrane_types):
            print("\nPermeate TDS Comparison:")
            for mem_type, result in results.items():
                if result['status'] == 'success':
                    print(f"  {mem_type}: {result['performance']['permeate_tds']:.0f} ppm")
                    
            print("\nEnergy Comparison:")
            for mem_type, result in results.items():
                if result['status'] == 'success':
                    print(f"  {mem_type}: {result['economics']['specific_energy_kwh_m3']:.2f} kWh/m³")
        
        print("\n" + "="*70)
        print("TEST COMPLETE")
        print("="*70)
        
        return success_count == len(membrane_types)
        
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_direct_workflow()
    sys.exit(0 if success else 1)