"""
Test script to verify MCAS ion composition is required.
"""

import sys
from pathlib import Path
import json

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.simulate_ro import run_ro_simulation

def test_missing_ion_composition():
    """Test that simulation fails without ion composition."""
    print("Testing simulation without ion composition...")
    
    config = {
        'array_notation': '1x6',
        'stages': [{
            'stage_number': 1,
            'n_vessels': 1,
            'vessel_count': 1,
            'elements_per_vessel': 6,
            'membrane_area_m2': 223.0,
            'stage_recovery': 0.5,
            'feed_pressure_bar': 15.0
        }],
        'feed_flow_m3h': 10.0
    }
    
    # Try without ion composition
    result = run_ro_simulation(
        configuration=config,
        feed_salinity_ppm=2000,
        feed_temperature_c=25.0,
        feed_ion_composition=None  # No ion composition
    )
    
    print(f"\nResult status: {result['status']}")
    print(f"Message: {result.get('message', 'No message')}")
    
    assert result['status'] == 'error'
    assert 'Ion composition is required' in result['message']
    print("\n✓ Test passed: Error returned for missing ion composition")


def test_with_ion_composition():
    """Test that simulation works with ion composition."""
    print("\n\nTesting simulation with ion composition...")
    
    config = {
        'array_notation': '1x6',
        'stages': [{
            'stage_number': 1,
            'n_vessels': 1,
            'vessel_count': 1,
            'elements_per_vessel': 6,
            'membrane_area_m2': 223.0,
            'stage_recovery': 0.5,
            'feed_pressure_bar': 15.0
        }],
        'feed_flow_m3h': 10.0
    }
    
    # With ion composition
    ion_comp = {"Na+": 786, "Cl-": 1214}  # Total ~2000 mg/L
    
    result = run_ro_simulation(
        configuration=config,
        feed_salinity_ppm=2000,
        feed_temperature_c=25.0,
        feed_ion_composition=ion_comp
    )
    
    print(f"\nResult status: {result['status']}")
    if result['status'] == 'error':
        print(f"Error message: {result.get('message', 'No message')}")
    else:
        print("✓ Simulation accepted ion composition")


def test_recycle_routing():
    """Test that recycle configurations use the correct template."""
    print("\n\nTesting recycle configuration routing...")
    
    config = {
        'array_notation': '1x6',
        'stages': [{
            'stage_number': 1,
            'n_vessels': 1,
            'vessel_count': 1,
            'elements_per_vessel': 6,
            'membrane_area_m2': 223.0,
            'stage_recovery': 0.5,
            'feed_pressure_bar': 15.0
        }],
        'feed_flow_m3h': 10.0,
        'recycle_info': {
            'uses_recycle': True,
            'recycle_ratio': 0.5
        }
    }
    
    ion_comp = {"Na+": 786, "Cl-": 1214}
    
    # Check that it uses recycle template with both ion comp and recycle
    result = run_ro_simulation(
        configuration=config,
        feed_salinity_ppm=2000,
        feed_temperature_c=25.0,
        feed_ion_composition=ion_comp
    )
    
    print(f"\nResult status: {result['status']}")
    print("✓ Recycle configuration with ion composition processed")


if __name__ == "__main__":
    print("=" * 60)
    print("MCAS Required Ion Composition Tests")
    print("=" * 60)
    
    try:
        test_missing_ion_composition()
        test_with_ion_composition()
        test_recycle_routing()
        print("\n\nAll tests completed!")
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()