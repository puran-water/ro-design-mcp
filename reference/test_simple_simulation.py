import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.simulate_ro import run_ro_simulation
from utils.membrane_properties_handler import get_membrane_properties
import json

def test_simple_simulation():
    """Test with a simple single-stage configuration"""
    
    configuration = {
        "stage_count": 1,
        "array_notation": "6:0",
        "total_vessels": 6,
        "total_membrane_area_m2": 1560.72,
        "achieved_recovery": 0.5,
        "recovery_error": 0,
        "feed_flow_m3h": 50,  # Add this at root level
        "stages": [
            {
                "stage_number": 1,
                "vessel_count": 6,
                "feed_flow_m3h": 50,
                "permeate_flow_m3h": 25,
                "concentrate_flow_m3h": 25,
                "stage_recovery": 0.5,
                "design_flux_lmh": 16,
                "flux_ratio": 1.0,
                "membrane_area_m2": 1560.72,
                "concentrate_per_vessel_m3h": 4.17,
                "min_concentrate_required_m3h": 3.5,
                "concentrate_margin_m3h": 0.67,
                "concentrate_margin_percent": 19.14
            }
        ],
        "recycle_info": {"uses_recycle": False},
        "recovery_achievement": {
            "met_target": True,
            "target_recovery_percent": 50,
            "achieved_recovery_percent": 50,
            "recovery_error_percent": 0
        },
        "flux_summary": {
            "min_flux_ratio": 1.0,
            "max_flux_ratio": 1.0,
            "average_flux_lmh": 16
        }
    }
    
    feed_salinity_ppm = 2000
    feed_temperature_c = 25
    
    # Test with different membrane types
    membrane_types = ["brackish", "eco_pro_400", "cr100_pro_400"]
    
    for membrane_type in membrane_types:
        print(f"\n{'='*60}")
        print(f"Testing {membrane_type} membrane")
        print(f"{'='*60}")
        
        # Get membrane properties
        A_w, B_s = get_membrane_properties(membrane_type)
        print(f"Membrane properties:")
        print(f"  A_w = {A_w:.2e} m/s/Pa")
        print(f"  B_s = {B_s:.2e} m/s")
        
        try:
            # Run simulation without ion composition (use standard template)
            result = run_ro_simulation(
                configuration,
                feed_salinity_ppm,
                feed_temperature_c,
                membrane_type,
                None,  # membrane_properties
                None,  # feed_ion_composition - None will use standard template
                False  # optimize_pumps=False for simpler test
            )
            
            print(f"\nSimulation status: {result.get('status', 'unknown')}")
            
            if result.get('status') == 'error':
                print(f"Error: {result.get('message', 'Unknown error')}")
                if 'traceback' in result:
                    print("\nTraceback (last few lines):")
                    traceback_lines = result['traceback'].split('\n')
                    print('\n'.join(traceback_lines[-10:]))
            else:
                print("\nResults summary:")
                if 'performance' in result:
                    print(f"  Total recovery: {result['performance'].get('total_recovery', 0):.2%}")
                if 'economics' in result:
                    print(f"  Total power: {result['economics'].get('total_power_kw', 0):.1f} kW")
                    print(f"  Specific energy: {result['economics'].get('specific_energy_kwh_m3', 0):.2f} kWh/m³")
                
                # Show first stage details
                if 'stage_results' in result and result['stage_results']:
                    stage1 = result['stage_results'][0]
                    print(f"\nStage 1 details:")
                    print(f"  Feed pressure: {stage1.get('feed_pressure_bar', 0):.1f} bar")
                    print(f"  Permeate TDS: {stage1.get('permeate_tds_ppm', 0):.0f} ppm")
                    print(f"  Pump power: {stage1.get('pump_power_kw', 0):.1f} kW")
        
        except Exception as e:
            print(f"\nSimulation failed with exception: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_simple_simulation()