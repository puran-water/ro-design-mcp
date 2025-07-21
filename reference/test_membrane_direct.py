#!/usr/bin/env python
"""
Direct test of membrane properties without MCP server dependencies.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import utilities directly
from utils.membrane_properties_handler import get_membrane_properties
from utils.simulate_ro import run_ro_simulation


def test_membrane_properties_direct():
    """Test different membrane properties to ensure they produce different results."""
    
    # Test configuration
    test_config = {
        'array_notation': '17',
        'n_stages': 1,
        'stage_count': 1,
        'feed_flow_m3h': 100.0,
        'stages': [{
            'stage_number': 1,
            'n_vessels': 17,
            'vessel_count': 17,
            'membrane_area_m2': 4421.04,  # 17 vessels * 7 elements * 37.16 m2
            'stage_recovery': 0.5,
            'feed_flow': 100.0
        }]
    }
    
    # Test different membrane types
    membrane_tests = [
        ("brackish", None),
        ("bw30_400", None),
        ("eco_pro_400", None),
        ("cr100_pro_400", None)
    ]
    
    print("Testing membrane properties handler...")
    print("="*60)
    
    # First check that we get different A_w and B_s values
    for membrane_type, _ in membrane_tests:
        A_w, B_s = get_membrane_properties(membrane_type)
        print(f"{membrane_type}: A_w = {A_w:.2e} m/s/Pa, B_s = {B_s:.2e} m/s")
    
    print("\n" + "="*60)
    print("Running simulations with different membranes...")
    print("="*60)
    
    results = {}
    
    for membrane_type, membrane_props in membrane_tests:
        print(f"\nTesting {membrane_type}...")
        
        try:
            # Run simulation
            result = run_ro_simulation(
                configuration=test_config,
                feed_salinity_ppm=5000,
                feed_temperature_c=25.0,
                membrane_type=membrane_type,
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
                
                print(f"  Specific energy: {metrics['specific_energy']:.3f} kWh/m³")
                print(f"  Recovery: {metrics['recovery']:.1%}")
                print(f"  Permeate TDS: {metrics['permeate_tds']:.1f} ppm")
            else:
                print(f"  ERROR: {result.get('message', 'Unknown error')}")
                results[membrane_type] = None
                
        except Exception as e:
            print(f"  EXCEPTION: {str(e)}")
            import traceback
            traceback.print_exc()
            results[membrane_type] = None
    
    # Analyze results
    print("\n" + "="*60)
    print("RESULTS ANALYSIS")
    print("="*60)
    
    # Check if results differ
    if len(results) > 1:
        # Get first successful result as baseline
        baseline_name = None
        baseline_metrics = None
        for name, metrics in results.items():
            if metrics:
                baseline_name = name
                baseline_metrics = metrics
                break
        
        if baseline_metrics:
            variations = False
            for name, metrics in results.items():
                if metrics and name != baseline_name:
                    # Check for any significant differences
                    energy_diff = abs(metrics['specific_energy'] - baseline_metrics['specific_energy'])
                    tds_diff = abs(metrics['permeate_tds'] - baseline_metrics['permeate_tds'])
                    
                    if energy_diff > 0.001 or tds_diff > 0.1:
                        variations = True
                        print(f"\n{name} differs from {baseline_name}:")
                        print(f"  Energy difference: {energy_diff:.3f} kWh/m³")
                        print(f"  TDS difference: {tds_diff:.1f} ppm")
            
            if not variations:
                print("\nERROR: All membrane types produced IDENTICAL results!")
                print("Membrane properties are NOT being applied correctly.")
            else:
                print("\nSUCCESS: Different membrane types produce different results!")
    
    return results


if __name__ == "__main__":
    print("Direct Membrane Properties Test")
    print("="*60)
    
    # Run the test
    results = test_membrane_properties_direct()
    
    print("\nTest complete!")