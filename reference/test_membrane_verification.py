#!/usr/bin/env python
"""
Test script to verify that different membrane properties produce different simulation results.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import the server functions
from server import simulate_ro_system, optimize_ro_configuration


async def test_membrane_properties():
    """Test different membrane properties to ensure they produce different results."""
    
    # First optimize a configuration
    print("1. Optimizing RO configuration...")
    config = await optimize_ro_configuration(
        feed_flow_m3h=100,
        water_recovery_fraction=0.5,
        membrane_type="brackish"
    )
    
    # Get the first configuration
    if config['status'] != 'success' or not config['configurations']:
        print(f"ERROR: Configuration optimization failed: {config}")
        return
    
    test_config = config['configurations'][0]
    print(f"   Using configuration: {test_config['array_notation']}")
    
    # Test different membrane types
    membrane_tests = [
        ("brackish", None),
        ("bw30_400", None),
        ("eco_pro_400", None),
        ("cr100_pro_400", None),
        ("custom", '{"A_w": 2.0e-11, "B_s": 3.0e-8}')
    ]
    
    results = {}
    
    for membrane_type, membrane_props in membrane_tests:
        print(f"\n2. Testing membrane: {membrane_type}")
        if membrane_props:
            print(f"   Custom properties: {membrane_props}")
        
        try:
            # Run simulation
            result = await simulate_ro_system(
                configuration=test_config,
                feed_salinity_ppm=5000,
                feed_temperature_c=25.0,
                membrane_type=membrane_type if membrane_type != "custom" else "brackish",
                membrane_properties=membrane_props,
                optimize_pumps=False  # Fixed pumps for consistent comparison
            )
            
            if result['status'] == 'success':
                # Extract key metrics
                metrics = {
                    'specific_energy': result['economics'].get('specific_energy_kwh_m3', 0),
                    'total_power': result['economics'].get('total_power_kw', 0),
                    'recovery': result['performance'].get('total_recovery', 0),
                    'stage1_pressure': result['stage_results'][0]['feed_pressure_bar'] if result['stage_results'] else 0,
                    'permeate_tds': result['stage_results'][0]['permeate_tds_ppm'] if result['stage_results'] else 0
                }
                results[membrane_type] = metrics
                
                print(f"   Specific energy: {metrics['specific_energy']:.3f} kWh/m³")
                print(f"   Total power: {metrics['total_power']:.1f} kW")
                print(f"   Recovery: {metrics['recovery']:.1%}")
                print(f"   Stage 1 pressure: {metrics['stage1_pressure']:.1f} bar")
                print(f"   Permeate TDS: {metrics['permeate_tds']:.1f} ppm")
            else:
                print(f"   ERROR: {result.get('message', 'Unknown error')}")
                results[membrane_type] = None
                
        except Exception as e:
            print(f"   EXCEPTION: {str(e)}")
            results[membrane_type] = None
    
    # Analyze results
    print("\n" + "="*60)
    print("RESULTS ANALYSIS")
    print("="*60)
    
    # Check if all results are identical
    unique_results = set()
    for membrane, metrics in results.items():
        if metrics:
            # Create a hashable representation
            result_tuple = (
                round(metrics['specific_energy'], 3),
                round(metrics['total_power'], 1),
                round(metrics['recovery'], 3),
                round(metrics['permeate_tds'], 1)
            )
            unique_results.add(result_tuple)
    
    if len(unique_results) == 1:
        print("ERROR: All membrane types produced IDENTICAL results!")
        print("This indicates membrane properties are NOT being applied correctly.")
    else:
        print(f"SUCCESS: Found {len(unique_results)} different result sets")
        print("\nVariations observed:")
        
        # Compare each membrane to brackish baseline
        if 'brackish' in results and results['brackish']:
            baseline = results['brackish']
            for membrane, metrics in results.items():
                if metrics and membrane != 'brackish':
                    print(f"\n{membrane} vs brackish:")
                    energy_diff = ((metrics['specific_energy'] - baseline['specific_energy']) / baseline['specific_energy']) * 100
                    power_diff = ((metrics['total_power'] - baseline['total_power']) / baseline['total_power']) * 100
                    tds_diff = ((metrics['permeate_tds'] - baseline['permeate_tds']) / baseline['permeate_tds']) * 100
                    
                    print(f"  Energy: {energy_diff:+.1f}%")
                    print(f"  Power: {power_diff:+.1f}%")
                    print(f"  Permeate TDS: {tds_diff:+.1f}%")
    
    # Expected differences based on membrane properties
    print("\n" + "="*60)
    print("EXPECTED DIFFERENCES (based on A_w values)")
    print("="*60)
    print("bw30_400: A_w = 9.63e-12 m/s/Pa (baseline)")
    print("eco_pro_400: A_w = 1.60e-11 m/s/Pa (66% higher - should need less pressure)")
    print("cr100_pro_400: A_w = 1.06e-11 m/s/Pa (10% higher)")
    print("custom: A_w = 2.0e-11 m/s/Pa (108% higher)")
    
    return results


if __name__ == "__main__":
    print("Membrane Properties Verification Test")
    print("="*60)
    
    # Run the async test
    results = asyncio.run(test_membrane_properties())
    
    print("\nTest complete!")