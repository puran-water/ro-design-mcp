#!/usr/bin/env python
"""
Direct test of membrane-aware initialization without async/MCP wrapper.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import utilities directly
from utils.optimize_ro import optimize_vessel_array_configuration
from utils.simulate_ro import run_ro_simulation


def test_membrane_initialization():
    """Test initialization with different membrane types."""
    
    print("Testing Membrane-Aware Initialization (Direct)")
    print("=" * 60)
    
    # Test configuration
    feed_flow_m3h = 100
    target_recovery = 0.75
    feed_salinity_ppm = 5000
    feed_temperature_c = 25
    
    # First get an optimal configuration
    print("\n1. Getting optimal configuration...")
    configurations = optimize_vessel_array_configuration(
        feed_flow_m3h=feed_flow_m3h,
        target_recovery=target_recovery,
        feed_salinity_ppm=feed_salinity_ppm,
        membrane_type="brackish"
    )
    
    if not configurations:
        print("ERROR: No viable configurations found!")
        return
    
    # Use the first configuration
    configuration = configurations[0]
    print(f"   Using configuration: {configuration['array_notation']}")
    print(f"   Stage count: {len(configuration['stages'])}")
    
    # Test different membrane types
    membrane_types = ["bw30_400", "eco_pro_400", "cr100_pro_400"]
    results = {}
    
    print("\n2. Testing different membrane types...")
    print("-" * 60)
    
    for membrane_type in membrane_types:
        print(f"\n   Testing {membrane_type}...")
        
        try:
            # Run simulation
            sim_result = run_ro_simulation(
                configuration=configuration,
                feed_salinity_ppm=feed_salinity_ppm,
                feed_temperature_c=feed_temperature_c,
                membrane_type=membrane_type,
                membrane_properties=None,
                optimize_pumps=True,
                feed_ion_composition=None
            )
            
            if sim_result["status"] == "success":
                # Extract key metrics
                perf = sim_result["performance"]
                econ = sim_result["economics"]
                stage1 = sim_result["stage_results"][0] if sim_result["stage_results"] else {}
                
                results[membrane_type] = {
                    "recovery": perf.get("total_recovery", 0),
                    "energy": econ.get("specific_energy_kwh_m3", 0),
                    "power": econ.get("total_power_kw", 0),
                    "stage1_pressure": stage1.get("feed_pressure_bar", 0),
                    "permeate_tds": perf.get("permeate_tds_mg_l", 0)
                }
                
                print(f"      SUCCESS: Recovery={results[membrane_type]['recovery']:.1%}, "
                      f"Energy={results[membrane_type]['energy']:.2f} kWh/m³, "
                      f"Stage 1 Pressure={results[membrane_type]['stage1_pressure']:.1f} bar")
            else:
                print(f"      FAILED: {sim_result.get('error', 'Unknown error')}")
                results[membrane_type] = {"error": sim_result.get("error", "Unknown")}
                
        except Exception as e:
            import traceback
            print(f"      EXCEPTION: {str(e)}")
            print("      Traceback:")
            traceback.print_exc()
            results[membrane_type] = {"error": str(e)}
    
    # Analyze results
    print("\n" + "=" * 60)
    print("ANALYSIS")
    print("=" * 60)
    
    successful_results = {k: v for k, v in results.items() if "error" not in v}
    
    if len(successful_results) == 0:
        print("ERROR: All simulations failed!")
        return results
    
    # Check for variations in pressure and energy
    pressures = [v["stage1_pressure"] for v in successful_results.values()]
    energies = [v["energy"] for v in successful_results.values()]
    
    if len(pressures) > 1:
        pressure_variation = (max(pressures) - min(pressures)) / min(pressures) if min(pressures) > 0 else 0
        energy_variation = (max(energies) - min(energies)) / min(energies) if min(energies) > 0 else 0
        
        print(f"\nPressure variation: {pressure_variation:.1%}")
        print(f"Energy variation: {energy_variation:.1%}")
        
        if pressure_variation < 0.05:  # Less than 5% variation
            print("\nWARNING: Low pressure variation suggests membrane properties may not be affecting initialization!")
        else:
            print("\nSUCCESS: Significant pressure variation confirms membrane-aware initialization is working!")
    
    # Compare to expected behavior
    print("\nExpected behavior based on A_w values:")
    print("  BW30-400 (A_w=9.63e-12): Baseline pressure")
    print("  ECO PRO-400 (A_w=1.60e-11, 66% higher): ~20-30% lower pressure")
    print("  CR100 PRO-400 (A_w=1.06e-11, 10% higher): ~5-10% lower pressure")
    
    # Show detailed comparison
    if "bw30_400" in successful_results:
        baseline = successful_results["bw30_400"]
        print(f"\nActual results (compared to BW30-400):")
        
        for membrane, data in successful_results.items():
            if membrane != "bw30_400" and "error" not in data:
                pressure_diff = (data["stage1_pressure"] - baseline["stage1_pressure"]) / baseline["stage1_pressure"]
                energy_diff = (data["energy"] - baseline["energy"]) / baseline["energy"]
                
                print(f"  {membrane}: Pressure {pressure_diff:+.1%}, Energy {energy_diff:+.1%}")
    
    # Print all pressures for comparison
    print("\nDetailed pressure comparison:")
    for membrane, data in results.items():
        if "error" not in data:
            print(f"  {membrane}: {data['stage1_pressure']:.1f} bar")
    
    return results


if __name__ == "__main__":
    print("Direct Membrane Initialization Test")
    print("=" * 60)
    
    # Run the test
    results = test_membrane_initialization()
    
    print("\nTest complete!")