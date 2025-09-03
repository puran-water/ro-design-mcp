#!/usr/bin/env python
"""
Test script for direct execution of RO simulation with artifact management.
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.simulate_ro import run_ro_simulation
from utils.artifacts import (
    deterministic_run_id,
    check_existing_results,
    write_artifacts,
    capture_context,
    artifacts_root
)
from utils.optimize_ro import optimize_vessel_array_configuration


def test_direct_execution():
    """Test the complete workflow with direct execution."""
    
    print("=" * 60)
    print("Testing Direct Execution with Artifact Management")
    print("=" * 60)
    
    # Step 1: Optimize configuration
    print("\n1. Optimizing RO configuration...")
    configurations = optimize_vessel_array_configuration(
        feed_flow_m3h=100.0,
        target_recovery=0.75,
        feed_salinity_ppm=5000,
        membrane_type="brackish",
        allow_recycle=False
    )
    
    if not configurations:
        print("ERROR: No configurations found")
        return False
    
    # Get the first configuration (2-stage without recycle)
    config = configurations[0]
    print(f"   Selected configuration: {config['array_notation']} array")
    print(f"   Stages: {config['n_stages']}")
    print(f"   Total vessels: {config['total_vessels']}")
    print(f"   Achieved recovery: {config['total_recovery']:.1%}")
    
    # Step 2: Prepare simulation inputs
    print("\n2. Preparing simulation inputs...")
    feed_ion_composition = {
        "Na+": 1500,
        "Cl-": 2400, 
        "Ca2+": 120,
        "Mg2+": 60,
        "SO4-2": 200,
        "HCO3-": 150
    }
    
    input_payload = {
        "configuration": config,
        "feed_salinity_ppm": 5000,
        "feed_ion_composition": feed_ion_composition,
        "feed_temperature_c": 25.0,
        "membrane_type": "brackish",
        "membrane_properties": {},
        "optimize_pumps": True
    }
    
    # Step 3: Generate deterministic run ID
    run_id = deterministic_run_id(
        tool_name="simulate_ro_system",
        input_payload=input_payload
    )
    print(f"   Generated run ID: {run_id}")
    
    # Step 4: Check for existing results
    print("\n3. Checking for cached results...")
    existing_results = check_existing_results(run_id)
    if existing_results:
        print(f"   Found cached results for run_id: {run_id}")
        print(f"   Recovery: {existing_results['performance']['system_recovery']:.1%}")
        print(f"   Permeate TDS: {existing_results['performance']['total_permeate_tds_mg_l']:.0f} mg/L")
        return True
    else:
        print("   No cached results found, running simulation...")
    
    # Step 5: Run simulation
    print("\n4. Running WaterTAP simulation...")
    print("   This may take 20-30 seconds...")
    
    try:
        results = run_ro_simulation(
            configuration=config,
            feed_salinity_ppm=5000,
            feed_ion_composition=feed_ion_composition,
            feed_temperature_c=25.0,
            membrane_type="brackish",
            membrane_properties=None,
            optimize_pumps=True,
            initialization_strategy="sequential",
            use_nacl_equivalent=True
        )
        
        if results["status"] != "success":
            print(f"   ERROR: Simulation failed: {results.get('message', 'Unknown error')}")
            return False
        
        print("   Simulation completed successfully!")
        print(f"   Recovery: {results['performance']['system_recovery']:.1%}")
        print(f"   Permeate TDS: {results['performance']['total_permeate_tds_mg_l']:.0f} mg/L")
        print(f"   Specific energy: {results['performance']['specific_energy_kWh_m3']:.2f} kWh/m³")
        
    except Exception as e:
        print(f"   ERROR during simulation: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 6: Write artifacts
    print("\n5. Writing artifacts...")
    try:
        context = capture_context(
            tool_name="simulate_ro_system",
            run_id=run_id
        )
        
        warnings = []
        if "trace_ion_info" in results:
            warnings.append(f"Trace ion handling: {results['trace_ion_info']['handling_strategy']}")
        
        artifact_dir = write_artifacts(
            run_id=run_id,
            tool_name="simulate_ro_system",
            input_data=input_payload,
            results_data=results,
            context=context,
            warnings=warnings if warnings else None
        )
        
        print(f"   Artifacts written to: {artifact_dir}")
        
        # List artifact files
        artifact_files = list(artifact_dir.glob("*"))
        print(f"   Created {len(artifact_files)} artifact files:")
        for f in sorted(artifact_files):
            size_kb = f.stat().st_size / 1024
            print(f"     - {f.name} ({size_kb:.1f} KB)")
        
    except Exception as e:
        print(f"   ERROR writing artifacts: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 7: Verify idempotency
    print("\n6. Verifying idempotency...")
    cached_results = check_existing_results(run_id)
    if cached_results:
        print("   Successfully retrieved cached results!")
        print(f"   Results match: {cached_results['status'] == results['status']}")
    else:
        print("   WARNING: Could not retrieve cached results")
    
    print("\n" + "=" * 60)
    print("Test completed successfully!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = test_direct_execution()
    sys.exit(0 if success else 1)