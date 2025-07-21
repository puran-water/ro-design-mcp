import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.simulate_ro import run_ro_simulation
from utils.membrane_properties_handler import get_membrane_properties
import json

def test_simulation():
    """Test the simulation directly without going through MCP"""
    
    configuration = {
        "stage_count": 2,
        "array_notation": "17:8",
        "total_vessels": 25,
        "total_membrane_area_m2": 6503,
        "achieved_recovery": 0.7544117457777778,
        "recovery_error": 0.004411745777777809,
        "stages": [
            {
                "stage_number": 1,
                "vessel_count": 17,
                "feed_flow_m3h": 150,
                "permeate_flow_m3h": 83.72762691428572,
                "concentrate_flow_m3h": 66.27237308571428,
                "stage_recovery": 0.5581841794285715,
                "design_flux_lmh": 18.934163172265677,
                "flux_ratio": 1.05189795401476,
                "membrane_area_m2": 4422.04,
                "concentrate_per_vessel_m3h": 3.8983748873949575,
                "min_concentrate_required_m3h": 3.5,
                "concentrate_margin_m3h": 0.3983748873949575,
                "concentrate_margin_percent": 11.382139639855925
            },
            {
                "stage_number": 2,
                "vessel_count": 8,
                "feed_flow_m3h": 66.27237308571428,
                "permeate_flow_m3h": 29.434134952380948,
                "concentrate_flow_m3h": 36.838238133333334,
                "stage_recovery": 0.444138840694778,
                "design_flux_lmh": 14.144498189480311,
                "flux_ratio": 0.9429665459653541,
                "membrane_area_m2": 2080.96,
                "concentrate_per_vessel_m3h": 4.604779766666667,
                "min_concentrate_required_m3h": 3.8,
                "concentrate_margin_m3h": 0.804779766666667,
                "concentrate_margin_percent": 21.17841491228072
            }
        ],
        "recycle_info": {"uses_recycle": False},
        "recovery_achievement": {
            "met_target": True,
            "target_recovery_percent": 75,
            "achieved_recovery_percent": 75.44117457777779,
            "recovery_error_percent": 0.4411745777777809
        },
        "flux_summary": {
            "min_flux_ratio": 0.9429665459653541,
            "max_flux_ratio": 1.05189795401476,
            "average_flux_lmh": 16.539330680872993
        }
    }
    
    feed_salinity_ppm = 2000
    feed_temperature_c = 25
    membrane_type = "brackish"
    feed_ion_composition_str = '{"Na+": 786.8, "Cl-": 1213.2}'
    feed_ion_composition = json.loads(feed_ion_composition_str)
    
    print("Testing simulation with brackish membrane (BW30-400)...")
    print(f"Feed salinity: {feed_salinity_ppm} ppm")
    print(f"Feed temperature: {feed_temperature_c}°C")
    print(f"Membrane type: {membrane_type}")
    print(f"Feed ion composition: {feed_ion_composition}")
    
    # Get membrane properties
    A_w, B_s = get_membrane_properties(membrane_type)
    print(f"\nMembrane properties:")
    print(f"  A_w = {A_w:.2e} m/s/Pa")
    print(f"  B_s = {B_s:.2e} m/s")
    
    try:
        # Run simulation
        result = run_ro_simulation(
            configuration,
            feed_salinity_ppm,
            feed_temperature_c,
            membrane_type,
            None,  # membrane_properties
            feed_ion_composition,  # Pass as dict, not string
            True   # optimize_pumps
        )
        
        print("\nSimulation completed!")
        print(f"Status: {result.get('status', 'unknown')}")
        
        if result.get('status') == 'error':
            print(f"Error: {result.get('message', 'Unknown error')}")
            if 'traceback' in result:
                print("\nTraceback:")
                print(result['traceback'])
        else:
            print("\nResults summary:")
            if 'performance' in result:
                print(f"  Total recovery: {result['performance'].get('total_recovery', 0):.2%}")
            if 'economics' in result:
                print(f"  Total power: {result['economics'].get('total_power_kw', 0):.1f} kW")
                print(f"  Specific energy: {result['economics'].get('specific_energy_kwh_m3', 0):.2f} kWh/m³")
        
    except Exception as e:
        print(f"\nSimulation failed with error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simulation()