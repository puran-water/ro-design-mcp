#!/usr/bin/env python3
"""
Direct test of MCP server simulation tool to verify hanging fix.
"""

import sys
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import server module
import server


async def test_simulate_ro_system():
    """Test the simulate_ro_system tool directly."""
    
    print("="*70)
    print("DIRECT MCP SERVER SIMULATION TEST")
    print("="*70)
    
    # Test configuration from the MCP request
    test_config = {
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
        "recycle_info": {
            "uses_recycle": False
        },
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
    
    print("\nCalling simulate_ro_system with:")
    print(f"  Configuration: {test_config['array_notation']}")
    print(f"  Feed salinity: 2000 ppm")
    print(f"  Temperature: 25°C")
    print(f"  Membrane type: brackish")
    
    try:
        # Call the underlying function directly (bypassing MCP decorator)
        # Get the actual function from the decorated tool
        simulate_func = server.simulate_ro_system.fn
        result = await simulate_func(
            configuration=test_config,
            feed_salinity_ppm=2000,
            feed_temperature_c=25,
            membrane_type="brackish"
        )
        
        print("\nResult received!")
        print(f"Status: {result.get('status', 'unknown')}")
        
        if result.get('status') == 'success':
            perf = result.get('performance', {})
            econ = result.get('economics', {})
            print(f"Recovery: {perf.get('total_recovery', 0)*100:.1f}%")
            print(f"Permeate TDS: {perf.get('permeate_tds_ppm', 0):.0f} ppm")
            print(f"Specific energy: {econ.get('specific_energy_kwh_m3', 0):.2f} kWh/m³")
            print(f"LCOW: ${econ.get('lcow_usd_m3', 0):.2f}/m³")
            print("\nSUCCESS: Simulation completed without hanging!")
        else:
            print(f"ERROR: {result.get('error', 'Unknown error')}")
            print(f"Message: {result.get('message', '')}")
            
    except Exception as e:
        print(f"\nEXCEPTION: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "="*70)
    return result.get('status') == 'success'


if __name__ == "__main__":
    # Run the async test
    success = asyncio.run(test_simulate_ro_system())
    sys.exit(0 if success else 1)