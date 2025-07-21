"""
Test script for verifying the updated MCAS recycle template initialization.
"""
import json
import logging
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.simulate_ro import run_ro_simulation

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Test configuration with recycle
test_config = {
    "array_notation": "2:1",
    "feed_flow_m3h": 100.0,
    "recovery": 0.85,
    "n_stages": 2,
    "stage_count": 2,
    "stages": [
        {
            "stage": 1,
            "n_vessels": 14,
            "vessel_count": 14,
            "membrane_area_m2": 520.0,
            "area_m2": 520.0,
            "stage_recovery": 0.65
        },
        {
            "stage": 2,
            "n_vessels": 7,
            "vessel_count": 7,
            "membrane_area_m2": 260.0,
            "area_m2": 260.0,
            "stage_recovery": 0.5
        }
    ],
    "recycle_info": {
        "uses_recycle": True,
        "recycle_ratio": 0.5,  # 50% of fresh feed is recycled
        "recycle_split_ratio": 0.85,  # 85% of concentrate goes to recycle
        "recycle_flow_m3h": 50.0,
        "effective_feed_flow_m3h": 150.0
    }
}

# Feed composition
feed_ion_composition = {
    "Na+": 1200,
    "Ca2+": 120,
    "Mg2+": 60,
    "K+": 20,
    "Cl-": 2100,
    "SO4-2": 200,
    "HCO3-": 150,
    "SiO3-2": 10
}

# Test 1: With recycle and pump optimization
print("\n" + "="*60)
print("TEST 1: MCAS Recycle Template with Pump Optimization")
print("="*60)

result1 = run_ro_simulation(
    configuration=test_config,
    feed_salinity_ppm=5000,
    feed_temperature_c=25.0,
    membrane_type="brackish",
    membrane_properties=None,
    optimize_pumps=True,
    feed_ion_composition=feed_ion_composition,
    initialization_strategy="sequential"
)

if result1["status"] == "success":
    print("\nTEST 1 PASSED!")
    print(f"System Recovery: {result1['performance']['system_recovery']:.1%}")
    print(f"Permeate TDS: {result1['performance']['total_permeate_tds_mg_l']:.0f} mg/L")
    print(f"Specific Energy: {result1['performance']['specific_energy_kWh_m3']:.2f} kWh/m³")
    
    # Check recycle metrics
    if "recycle_metrics" in result1:
        rm = result1["recycle_metrics"]
        print(f"\nRecycle Metrics:")
        print(f"  Recycle Flow: {rm['recycle_flow_kg_s']*3.6:.1f} m³/h")
        print(f"  Disposal Flow: {rm['disposal_flow_kg_s']*3.6:.1f} m³/h")
        
        # Check ion accumulation
        if "effective_ion_composition" in rm:
            print(f"\nIon Accumulation Factors:")
            for ion, data in sorted(rm["effective_ion_composition"].items())[:3]:  # Show first 3
                print(f"  {ion}: {data['accumulation_factor']:.2f}x")
else:
    print("\nTEST 1 FAILED!")
    print(f"Error: {result1['message']}")

# Test 2: Without recycle (standard case)
print("\n" + "="*60)
print("TEST 2: MCAS Standard Template (No Recycle)")
print("="*60)

test_config_no_recycle = test_config.copy()
test_config_no_recycle["recycle_info"] = {"uses_recycle": False}

result2 = run_ro_simulation(
    configuration=test_config_no_recycle,
    feed_salinity_ppm=5000,
    feed_temperature_c=25.0,
    membrane_type="brackish",
    membrane_properties=None,
    optimize_pumps=True,
    feed_ion_composition=feed_ion_composition,
    initialization_strategy="sequential"
)

if result2["status"] == "success":
    print("\nTEST 2 PASSED!")
    print(f"System Recovery: {result2['performance']['system_recovery']:.1%}")
    print(f"Permeate TDS: {result2['performance']['total_permeate_tds_mg_l']:.0f} mg/L")
    print(f"Specific Energy: {result2['performance']['specific_energy_kWh_m3']:.2f} kWh/m³")
else:
    print("\nTEST 2 FAILED!")
    print(f"Error: {result2['message']}")

# Summary
print("\n" + "="*60)
print("TEST SUMMARY")
print("="*60)
print(f"Test 1 (With Recycle): {'PASSED' if result1['status'] == 'success' else 'FAILED'}")
print(f"Test 2 (No Recycle): {'PASSED' if result2['status'] == 'success' else 'FAILED'}")

if result1["status"] == "success" and result2["status"] == "success":
    print("\nAll tests passed! The updated initialization is working correctly.")
else:
    print("\nSome tests failed. Check the error messages above.")