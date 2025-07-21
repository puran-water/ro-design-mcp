"""
Simple test to debug MCAS template issues
"""
import json
import logging
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from utils.simulate_ro import run_ro_simulation

# Very simple test configuration
test_config = {
    "array_notation": "1:0",
    "feed_flow_m3h": 100.0,
    "recovery": 0.5,
    "n_stages": 1,
    "stage_count": 1,
    "stages": [{
        "stage": 1,
        "n_vessels": 10,
        "vessel_count": 10,
        "membrane_area_m2": 400.0,
        "area_m2": 400.0,
        "stage_recovery": 0.5
    }],
    "recycle_info": {"uses_recycle": False}
}

# Simple feed composition
feed_composition = {
    "Na+": 1000,
    "Cl-": 1700,
    "Ca2+": 100,
    "SO4-2": 200
}

print("Running simple MCAS test...")
print(f"Feed TDS: ~{sum(feed_composition.values())} mg/L")
print(f"Target recovery: {test_config['recovery']*100}%")

try:
    result = run_ro_simulation(
        configuration=test_config,
        feed_salinity_ppm=3000,
        feed_temperature_c=25.0,
        membrane_type="brackish",
        optimize_pumps=False,  # Disable optimization for simpler test
        feed_ion_composition=feed_composition
    )
    
    print(f"\nResult status: {result['status']}")
    if result['status'] == 'success':
        print("Success!")
        print(f"Recovery: {result['performance']['total_recovery']:.1%}")
        print(f"Permeate TDS: {result['performance']['total_permeate_tds_mg_l']:.0f} mg/L")
        print(f"Power: {result['economics']['total_power_kw']:.1f} kW")
    else:
        print(f"Failed: {result['message']}")
        if 'traceback' in result:
            print("\nTraceback:")
            print(result['traceback'])
            
except Exception as e:
    print(f"Error: {str(e)}")
    import traceback
    traceback.print_exc()