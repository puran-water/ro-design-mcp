#!/usr/bin/env python3
"""
Test script to verify LOCALAPPDATA fix in MCP server environment.
This simulates the MCP server environment where LOCALAPPDATA might not be set.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Simulate MCP server environment by removing LOCALAPPDATA
original_localappdata = os.environ.pop('LOCALAPPDATA', None)

try:
    print("="*70)
    print("TEST LOCALAPPDATA FIX")
    print("="*70)
    print(f"\nLOCALAPPDATA before import: {os.environ.get('LOCALAPPDATA', 'NOT SET')}")
    
    # Now try to import and use the MCP server functions
    # This should set up LOCALAPPDATA automatically
    from server import main
    from utils.optimize_ro import optimize_vessel_array_configuration
    from utils.simulate_ro import run_ro_simulation
    
    print(f"LOCALAPPDATA after imports: {os.environ.get('LOCALAPPDATA', 'NOT SET')}")
    
    # Test 1: Run optimization (this should work regardless)
    print("\n" + "-"*50)
    print("TEST 1: Optimization")
    print("-"*50)
    
    try:
        configurations = optimize_vessel_array_configuration(
            feed_flow_m3h=150,
            target_recovery=0.75,
            feed_salinity_ppm=2000,
            membrane_type='brackish',
            allow_recycle=False
        )
        
        if configurations:
            config = configurations[0]
            print(f"SUCCESS: Configuration found - {config['array_notation']}")
        else:
            print("ERROR: No configurations found")
    except Exception as e:
        print(f"ERROR in optimization: {str(e)}")
    
    # Test 2: Run simulation (this is where LOCALAPPDATA error occurred)
    print("\n" + "-"*50)
    print("TEST 2: Simulation")
    print("-"*50)
    
    if configurations:
        try:
            print(f"LOCALAPPDATA before simulation: {os.environ.get('LOCALAPPDATA', 'NOT SET')}")
            
            sim_results = run_ro_simulation(
                configuration=config,
                feed_salinity_ppm=2000,
                feed_temperature_c=25.0,
                membrane_type='brackish',
                optimize_pumps=True,
                use_direct_simulation=True
            )
            
            if sim_results.get('status') == 'success':
                print("SUCCESS: Simulation completed successfully!")
                print(f"  Recovery: {sim_results['performance']['total_recovery']*100:.1f}%")
                print(f"  Specific energy: {sim_results['economics']['specific_energy_kwh_m3']:.2f} kWh/m³")
            else:
                print(f"ERROR: Simulation failed with status: {sim_results.get('status')}")
                print(f"  Error: {sim_results.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"ERROR in simulation: {str(e)}")
            import traceback
            traceback.print_exc()
    
    # Test 3: Direct server function test
    print("\n" + "-"*50)
    print("TEST 3: Server Initialization")
    print("-"*50)
    
    # This should set LOCALAPPDATA if needed
    try:
        # Call server setup without running the actual server
        import platform
        if platform.system() == "Windows" and 'LOCALAPPDATA' not in os.environ:
            os.environ['LOCALAPPDATA'] = os.path.join(os.path.expanduser("~"), "AppData", "Local")
            print(f"Server would set LOCALAPPDATA to: {os.environ['LOCALAPPDATA']}")
        else:
            print(f"LOCALAPPDATA already set or not Windows")
    except Exception as e:
        print(f"ERROR in server setup: {str(e)}")
    
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Final LOCALAPPDATA: {os.environ.get('LOCALAPPDATA', 'NOT SET')}")
    print("All tests completed. Check results above.")
    
finally:
    # Restore original LOCALAPPDATA if it existed
    if original_localappdata:
        os.environ['LOCALAPPDATA'] = original_localappdata
    
    print("\nEnvironment restored.")