"""
Test script to verify MCAS templates work correctly after fixes
"""
import json
import logging
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

from utils.simulate_ro import run_ro_simulation

# Test configurations
test_configs = [
    {
        "name": "Standard MCAS - Single Stage",
        "config": {
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
        },
        "feed_composition": {
            "Na+": 1000,
            "Cl-": 1700,
            "Ca2+": 100,
            "SO4-2": 200
        }
    },
    {
        "name": "Standard MCAS - Two Stage",
        "config": {
            "array_notation": "2:1",
            "feed_flow_m3h": 100.0,
            "recovery": 0.75,
            "n_stages": 2,
            "stage_count": 2,
            "stages": [
                {
                    "stage": 1,
                    "n_vessels": 10,
                    "vessel_count": 10,
                    "membrane_area_m2": 400.0,
                    "area_m2": 400.0,
                    "stage_recovery": 0.5
                },
                {
                    "stage": 2,
                    "n_vessels": 5,
                    "vessel_count": 5,
                    "membrane_area_m2": 200.0,
                    "area_m2": 200.0,
                    "stage_recovery": 0.5
                }
            ],
            "recycle_info": {"uses_recycle": False}
        },
        "feed_composition": {
            "Na+": 1000,
            "Cl-": 1700,
            "Ca2+": 100,
            "SO4-2": 200
        }
    },
    {
        "name": "MCAS with Low Recycle (10%)",
        "config": {
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
                "recycle_ratio": 0.1,
                "recycle_split_ratio": 0.2,
                "recycle_flow_m3h": 10.0,
                "effective_feed_flow_m3h": 110.0
            }
        },
        "feed_composition": {
            "Na+": 1000,
            "Cl-": 1700,
            "Ca2+": 100,
            "SO4-2": 200
        }
    },
    {
        "name": "MCAS with Moderate Recycle (30%)",
        "config": {
            "array_notation": "1:0",
            "feed_flow_m3h": 100.0,
            "recovery": 0.6,
            "n_stages": 1,
            "stage_count": 1,
            "stages": [{
                "stage": 1,
                "n_vessels": 12,
                "vessel_count": 12,
                "membrane_area_m2": 480.0,
                "area_m2": 480.0,
                "stage_recovery": 0.6
            }],
            "recycle_info": {
                "uses_recycle": True,
                "recycle_ratio": 0.3,
                "recycle_split_ratio": 0.5,
                "recycle_flow_m3h": 30.0,
                "effective_feed_flow_m3h": 130.0
            }
        },
        "feed_composition": {
            "Na+": 1000,
            "Cl-": 1700,
            "Ca2+": 100,
            "SO4-2": 200,
            "Mg2+": 50,
            "HCO3-": 150
        }
    }
]

# Run tests
print("=" * 80)
print("MCAS TEMPLATE TESTING")
print("=" * 80)

results_summary = []

for test in test_configs:
    print(f"\nTest: {test['name']}")
    print("-" * 40)
    
    try:
        result = run_ro_simulation(
            configuration=test['config'],
            feed_salinity_ppm=3000,
            feed_temperature_c=25.0,
            membrane_type="brackish",
            optimize_pumps=True,
            feed_ion_composition=test['feed_composition']
        )
        
        if result['status'] == 'success':
            print(f"[PASS] SUCCESS")
            print(f"  Recovery: {result['performance']['total_recovery']:.1%}")
            print(f"  Permeate TDS: {result['performance']['total_permeate_tds_mg_l']:.0f} mg/L")
            print(f"  Power: {result['economics']['total_power_kw']:.1f} kW")
            print(f"  Specific Energy: {result['economics']['specific_energy_kwh_m3']:.2f} kWh/m³")
            
            if test['config']['recycle_info'].get('uses_recycle'):
                print(f"  Recycle metrics:")
                if 'effective_feed_tds' in result:
                    print(f"    Effective feed TDS: {result['effective_feed_tds']:.0f} mg/L")
                if 'accumulation_factor' in result:
                    print(f"    Accumulation factor: {result['accumulation_factor']:.2f}x")
            
            results_summary.append({
                'test': test['name'],
                'status': 'PASS',
                'recovery': result['performance']['total_recovery'],
                'permeate_tds': result['performance']['total_permeate_tds_mg_l']
            })
        else:
            print(f"[FAIL] FAILED: {result['message']}")
            results_summary.append({
                'test': test['name'],
                'status': 'FAIL',
                'error': result['message']
            })
            
    except Exception as e:
        print(f"[ERROR] ERROR: {str(e)}")
        results_summary.append({
            'test': test['name'],
            'status': 'ERROR',
            'error': str(e)
        })

# Print summary
print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)

pass_count = sum(1 for r in results_summary if r['status'] == 'PASS')
total_count = len(results_summary)

print(f"\nTotal tests: {total_count}")
print(f"Passed: {pass_count}")
print(f"Failed: {total_count - pass_count}")
print(f"Success rate: {pass_count/total_count*100:.0f}%")

print("\nDetailed results:")
for result in results_summary:
    status_symbol = "[PASS]" if result['status'] == 'PASS' else "[FAIL]"
    print(f"\n{status_symbol} {result['test']}: {result['status']}")
    if result['status'] == 'PASS':
        print(f"  Recovery: {result['recovery']:.1%}")
        print(f"  Permeate TDS: {result['permeate_tds']:.0f} mg/L")
    else:
        print(f"  Error: {result.get('error', 'Unknown error')}")

# Save results to file
with open('test_mcas_results.json', 'w') as f:
    json.dump(results_summary, f, indent=2)

print(f"\nResults saved to test_mcas_results.json")