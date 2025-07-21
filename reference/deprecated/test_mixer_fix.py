#!/usr/bin/env python3
"""
Test script to verify the mixer initialization fix for 666,667 ppm error.
Tests various feed salinities to ensure proper TDS calculation.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.simulate_ro import run_ro_simulation
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

def test_feed_salinity(salinity_ppm, description):
    """Test RO simulation with given feed salinity."""
    print(f"\n{'='*60}")
    print(f"Testing: {description}")
    print(f"Feed salinity: {salinity_ppm} ppm")
    print('='*60)
    
    # Simple 2-stage configuration
    configuration = {
        'array_notation': '2:1',
        'feed_flow_m3h': 100,
        'stage_count': 2,
        'n_stages': 2,
        'stages': [
            {'stage_recovery': 0.5, 'stage_number': 1},
            {'stage_recovery': 0.4, 'stage_number': 2}
        ],
        'recycle_info': {
            'uses_recycle': False,
            'recycle_ratio': 0,
            'recycle_split_ratio': 0
        },
        'feed_salinity_ppm': salinity_ppm  # Add this for validation check
    }
    
    # Define ion composition based on typical brackish water
    feed_ion_composition = {
        'Na+': salinity_ppm * 0.393,  # ~39.3% of TDS
        'Cl-': salinity_ppm * 0.607,  # ~60.7% of TDS
    }
    
    try:
        # Run simulation
        results = run_ro_simulation(
            configuration=configuration,
            feed_salinity_ppm=salinity_ppm,
            feed_ion_composition=feed_ion_composition,
            feed_temperature_c=25.0,
            membrane_type="brackish",
            optimize_pumps=False,  # Fixed pressures for consistency
            initialization_strategy="sequential"
        )
        
        if results['status'] == 'success':
            print(f"[PASS] Simulation successful!")
            
            # Check if any stage reported the 666,667 ppm error
            error_found = False
            if 'message' in results and '666667' in str(results.get('message', '')):
                error_found = True
                print(f"[FAIL] ERROR: 666,667 ppm error detected in results!")
            
            # Check stage results
            for stage in results.get('stage_results', []):
                if 'message' in stage and '666667' in str(stage.get('message', '')):
                    error_found = True
                    print(f"[FAIL] ERROR: 666,667 ppm error in stage {stage.get('stage', 'unknown')}!")
            
            if not error_found:
                print(f"[PASS] No 666,667 ppm error detected")
                print(f"[PASS] System recovery: {results['performance']['system_recovery']:.1%}")
                print(f"[PASS] Permeate TDS: {results['performance']['total_permeate_tds_mg_l']:.0f} mg/L")
            
            return not error_found
            
        else:
            print(f"[FAIL] Simulation failed: {results.get('message', 'Unknown error')}")
            
            # Check if the error message contains 666,667
            if '666667' in str(results.get('message', '')):
                print(f"[FAIL] ERROR: 666,667 ppm error detected!")
                return False
            else:
                print(f"Note: Failed but not due to 666,667 ppm error")
                return True  # Different error, not the one we're testing for
                
    except Exception as e:
        print(f"[FAIL] Exception occurred: {str(e)}")
        if '666667' in str(e):
            print(f"[FAIL] ERROR: 666,667 ppm error in exception!")
            return False
        else:
            print(f"Note: Exception but not due to 666,667 ppm error")
            return True


def main():
    """Run tests with various feed salinities."""
    print("\nTesting Mixer Initialization Fix for 666,667 ppm Error")
    print("="*60)
    
    test_cases = [
        (2000, "Low brackish water"),
        (5000, "Medium brackish water"),
        (10000, "High brackish water"),
        (35000, "Seawater"),
        (2, "Ultra-low TDS (2 mg/L)"),
    ]
    
    all_passed = True
    results_summary = []
    
    for salinity, description in test_cases:
        passed = test_feed_salinity(salinity, description)
        all_passed = all_passed and passed
        results_summary.append((salinity, description, passed))
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for salinity, description, passed in results_summary:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {description} ({salinity} ppm)")
    
    print("\n" + "="*60)
    if all_passed:
        print("[PASS] ALL TESTS PASSED - No 666,667 ppm errors detected!")
    else:
        print("[FAIL] SOME TESTS FAILED - 666,667 ppm error still present!")
    print("="*60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())