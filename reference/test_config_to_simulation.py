#!/usr/bin/env python3
"""
Test configuration tool to simulation workflow for multiple membrane types.

This test runs the complete workflow:
1. Configuration tool to size RO system
2. Simulation with calculated areas
"""

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from server import RODesignMCPServer


def test_membrane_type(membrane_type: str, display_name: str):
    """Test configuration and simulation for a specific membrane type."""
    
    print(f"\n{'='*70}")
    print(f"TESTING {display_name}")
    print(f"{'='*70}")
    
    # Initialize server
    server = RODesignMCPServer()
    
    # Test parameters
    feed_flow = 150  # m³/h
    recovery = 0.75  # 75%
    feed_tds = 5000  # ppm
    
    print(f"\nFeed conditions:")
    print(f"  Flow: {feed_flow} m³/h")
    print(f"  TDS: {feed_tds} ppm")
    print(f"  Target recovery: {recovery*100:.0f}%")
    
    # Step 1: Configuration
    print(f"\n1. Running configuration tool...")
    config_params = {
        'feed_flow_m3h': feed_flow,
        'feed_tds_ppm': feed_tds,
        'min_permeate_tds_ppm': 100,
        'recovery': recovery,
        'membrane_type': membrane_type
    }
    
    try:
        config_result = server.configure_ro_system(json.dumps(config_params))
        config_data = json.loads(config_result)
        
        if config_data.get('success'):
            print(f"   Configuration successful!")
            print(f"   Stages: {config_data['stage_count']}")
            
            # Display stage details
            for i, stage in enumerate(config_data['stages']):
                print(f"\n   Stage {i+1}:")
                print(f"     Recovery: {stage['stage_recovery']*100:.1f}%")
                print(f"     Vessels: {stage['vessels']}")
                print(f"     Total area: {stage['membrane_area_m2']:.0f} m²")
                print(f"     Feed flow: {stage['feed_flow_m3h']:.1f} m³/h")
                print(f"     Permeate flow: {stage['permeate_flow_m3h']:.1f} m³/h")
                print(f"     Expected flux: {stage['expected_flux_lmh']:.1f} LMH")
        else:
            print(f"   Configuration failed: {config_data.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"   Configuration error: {str(e)}")
        return False
    
    # Step 2: Simulation
    print(f"\n2. Running simulation...")
    
    # Use the configuration output directly
    sim_params = {
        'configuration': config_data,
        'feed_salinity_ppm': feed_tds,
        'feed_temperature_c': 25,
        'membrane_type': membrane_type
    }
    
    try:
        sim_result = server.simulate_ro_system(json.dumps(sim_params))
        sim_data = json.loads(sim_result)
        
        if sim_data.get('status') == 'success':
            print(f"   Simulation successful!")
            
            # Display performance
            perf = sim_data.get('performance', {})
            print(f"\n   Overall Performance:")
            print(f"     Total recovery: {perf.get('total_recovery', 0)*100:.1f}%")
            print(f"     Permeate flow: {perf.get('permeate_flow_m3h', 0):.1f} m³/h")
            print(f"     Permeate TDS: {perf.get('permeate_tds_ppm', 0):.0f} ppm")
            print(f"     Total power: {perf.get('total_pump_power_kw', 0):.1f} kW")
            print(f"     Specific energy: {sim_data.get('economics', {}).get('specific_energy_kwh_m3', 0):.2f} kWh/m³")
            
            # Display stage results
            print(f"\n   Stage Results:")
            for stage in sim_data.get('stage_results', []):
                print(f"\n     Stage {stage['stage_number']}:")
                print(f"       Feed pressure: {stage['feed_pressure_bar']:.1f} bar")
                print(f"       Recovery: {stage['recovery']*100:.1f}%")
                print(f"       Permeate TDS: {stage['permeate_tds_ppm']:.0f} ppm")
                
                # Check flux if available
                if 'flux_kg_m2_s' in stage:
                    flux_lmh = stage['flux_kg_m2_s'] * 3600 / 1000 * 1000  # Convert to LMH
                    print(f"       Water flux: {flux_lmh:.1f} LMH")
                
            return True
        else:
            print(f"   Simulation failed: {sim_data.get('message', 'Unknown error')}")
            if 'traceback' in sim_data:
                print(f"   Error details: {sim_data['traceback'].split('Error:')[-1].strip()}")
            return False
            
    except Exception as e:
        print(f"   Simulation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run tests for all configured membrane types."""
    
    print("\n" + "="*70)
    print("CONFIGURATION TO SIMULATION WORKFLOW TEST")
    print("="*70)
    print("\nTesting complete workflow for multiple membrane types")
    print("Feed: 150 m³/h, 5000 ppm TDS, 75% recovery target")
    
    # Test each membrane type
    membrane_types = [
        ('bw30_400', 'BW30-400 (Standard Brackish)'),
        ('eco_pro_400', 'ECO PRO-400 (High Permeability)'),
        ('cr100_pro_400', 'CR100 PRO-400 (Chemical Resistant)'),
    ]
    
    results = []
    
    for membrane_code, display_name in membrane_types:
        success = test_membrane_type(membrane_code, display_name)
        results.append({
            'membrane': display_name,
            'success': success
        })
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    for result in results:
        status = "✓ PASS" if result['success'] else "✗ FAIL"
        print(f"\n{result['membrane']}: {status}")
    
    all_passed = all(r['success'] for r in results)
    print(f"\n{'='*70}")
    print(f"Overall result: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    print(f"{'='*70}")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)