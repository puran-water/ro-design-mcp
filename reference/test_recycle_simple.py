"""
Simple test to check basic functionality
"""
import json
import logging
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from utils.simulate_ro import run_ro_simulation

# Test 1: Standard MCAS (no recycle) - should work
print("="*60)
print("TEST 1: Standard MCAS Template (No Recycle)")
print("="*60)

config_no_recycle = {
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

feed_composition = {
    "Na+": 1000,
    "Cl-": 1700,
    "Ca2+": 100,
    "SO4-2": 200
}

result1 = run_ro_simulation(
    configuration=config_no_recycle,
    feed_salinity_ppm=3000,
    feed_temperature_c=25.0,
    membrane_type="brackish",
    optimize_pumps=False,
    feed_ion_composition=feed_composition
)

print(f"Result: {result1['status']}")
if result1['status'] == 'success':
    print(f"Permeate TDS: {result1['performance']['total_permeate_tds_mg_l']:.0f} mg/L")
else:
    print(f"Error: {result1['message']}")

# Test 2: MCAS with minimal recycle
print("\n" + "="*60)
print("TEST 2: MCAS with Minimal Recycle (10%)")
print("="*60)

config_recycle = {
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
    "recycle_info": {
        "uses_recycle": True,
        "recycle_ratio": 0.1,  # Only 10% recycle
        "recycle_split_ratio": 0.2,  # 20% of concentrate to recycle
        "recycle_flow_m3h": 10.0,
        "effective_feed_flow_m3h": 110.0
    }
}

result2 = run_ro_simulation(
    configuration=config_recycle,
    feed_salinity_ppm=3000,
    feed_temperature_c=25.0,
    membrane_type="brackish",
    optimize_pumps=False,
    feed_ion_composition=feed_composition
)

print(f"Result: {result2['status']}")
if result2['status'] == 'success':
    print(f"Permeate TDS: {result2['performance']['total_permeate_tds_mg_l']:.0f} mg/L")
else:
    print(f"Error: {result2['message']}")