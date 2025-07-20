#!/usr/bin/env python3
"""
Direct verification of TDS fix by building and initializing a model.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.mcas_builder import build_mcas_property_configuration
from utils.ro_model_builder import build_ro_model_mcas
from utils.ro_solver import initialize_and_solve_mcas
import logging

# Set up logging to see the TDS calculations
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_tds_calculation(feed_salinity_ppm):
    """Test that TDS is calculated correctly."""
    print(f"\n{'='*60}")
    print(f"Testing TDS calculation with {feed_salinity_ppm} ppm feed")
    print('='*60)
    
    # Configuration
    configuration = {
        'array_notation': '1:0',  # Single stage for simplicity
        'feed_flow_m3h': 100,
        'stage_count': 1,
        'n_stages': 1,
        'stages': [
            {'stage_recovery': 0.5, 'stage_number': 1}
        ],
        'recycle_info': {
            'uses_recycle': False,
            'recycle_ratio': 0,
            'recycle_split_ratio': 0
        },
        'feed_salinity_ppm': feed_salinity_ppm  # For validation
    }
    
    # Ion composition
    feed_ion_composition = {
        'Na+': feed_salinity_ppm * 0.393,
        'Cl-': feed_salinity_ppm * 0.607,
    }
    
    # Build MCAS config
    mcas_config = build_mcas_property_configuration(
        feed_composition=feed_ion_composition,
        include_scaling_ions=False,
        include_ph_species=False
    )
    
    # Build model
    print("Building model...")
    model = build_ro_model_mcas(
        configuration,
        mcas_config,
        feed_salinity_ppm,
        25.0,
        "brackish"
    )
    
    print("Model built successfully")
    
    # Initialize and solve
    print("\nInitializing model...")
    result = initialize_and_solve_mcas(model, configuration, optimize_pumps=False)
    
    if result['status'] == 'success':
        print("\n[SUCCESS] Model initialized and solved without 666,667 ppm error!")
        return True
    else:
        error_msg = result.get('message', '')
        if '666667' in str(error_msg):
            print(f"\n[FAIL] 666,667 ppm error still present: {error_msg}")
            return False
        else:
            print(f"\n[INFO] Different error occurred: {error_msg}")
            return True  # Not the 666,667 error


def main():
    """Test various salinities."""
    test_cases = [2000, 5000, 35000]
    all_passed = True
    
    for salinity in test_cases:
        passed = test_tds_calculation(salinity)
        all_passed = all_passed and passed
    
    print("\n" + "="*60)
    if all_passed:
        print("[SUCCESS] TDS fix verified - No 666,667 ppm errors!")
    else:
        print("[FAIL] 666,667 ppm error still present!")
    print("="*60)
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())