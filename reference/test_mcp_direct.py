#!/usr/bin/env python
"""Test MCP server with direct simulation route."""

import json
import sys
import asyncio
from pathlib import Path
import subprocess
import time

# Add parent directory to path to import server
sys.path.insert(0, str(Path(__file__).parent))


async def test_mcp_workflow():
    """Test complete MCP workflow from configuration to simulation."""
    
    print("="*70)
    print("TESTING MCP SERVER WITH DIRECT SIMULATION")
    print(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # Test parameters
    feed_flow = 150  # m³/h
    recovery = 0.75  # 75%
    feed_tds = 2000  # ppm
    
    print(f"\nTest Conditions:")
    print(f"  Feed flow: {feed_flow} m³/h")
    print(f"  Recovery: {recovery*100:.0f}%")
    print(f"  Feed TDS: {feed_tds} ppm")
    
    try:
        # Step 1: Configuration
        print("\n" + "-"*50)
        print("Step 1: Optimizing RO Configuration")
        print("-"*50)
        
        config_result = await optimize_ro_configuration(
            feed_flow_m3h=feed_flow,
            water_recovery_fraction=recovery,
            membrane_type="brackish"
        )
        
        if config_result['status'] != 'success':
            print(f"Configuration failed: {config_result}")
            return False
            
        print(f"Found {len(config_result['configurations'])} configurations")
        
        # Use first configuration
        config = config_result['configurations'][0]
        print(f"Using configuration: {config['array_notation']}")
        
        # Step 2: Simulation
        print("\n" + "-"*50)
        print("Step 2: Running Simulation")
        print("-"*50)
        
        # Test each membrane type
        membrane_types = ["bw30_400", "eco_pro_400", "cr100_pro_400"]
        
        for mem_type in membrane_types:
            print(f"\nTesting {mem_type}...")
            
            sim_result = await simulate_ro_system(
                configuration=config,
                feed_salinity_ppm=feed_tds,
                feed_temperature_c=25.0,
                membrane_type=mem_type,
                optimize_pumps=True
            )
            
            if sim_result['status'] == 'success':
                print(f"  ✓ Success")
                print(f"    Recovery: {sim_result['performance']['total_recovery']:.1%}")
                print(f"    Permeate TDS: {sim_result['performance']['permeate_tds']:.0f} ppm")
                print(f"    Energy: {sim_result['economics']['specific_energy_kwh_m3']:.2f} kWh/m³")
            else:
                print(f"  ✗ Failed: {sim_result.get('error', 'Unknown error')}")
                
        print("\n" + "="*70)
        print("TEST COMPLETE")
        print("="*70)
        
        return True
        
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_server_process():
    """Test the server running as a subprocess (simulating MCP client)."""
    
    print("\n" + "="*70)
    print("TESTING MCP SERVER AS SUBPROCESS")
    print("="*70)
    
    # Start the server process
    server_path = Path(__file__).parent / "server.py"
    
    # Create a simple request
    request = {
        "jsonrpc": "2.0",
        "method": "optimize_ro_configuration",
        "params": {
            "feed_flow_m3h": 100,
            "water_recovery_fraction": 0.75,
            "membrane_type": "brackish"
        },
        "id": 1
    }
    
    try:
        # Run server and send request via stdin
        proc = subprocess.Popen(
            [sys.executable, str(server_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Send request
        proc.stdin.write(json.dumps(request) + "\n")
        proc.stdin.flush()
        
        # Wait for response (with timeout)
        import select
        ready, _, _ = select.select([proc.stdout], [], [], 5.0)
        
        if ready:
            response = proc.stdout.readline()
            print(f"\nResponse received: {response[:100]}...")
            
            # Parse response
            try:
                resp_data = json.loads(response)
                if 'result' in resp_data:
                    print("✓ Server responded successfully")
                else:
                    print(f"✗ Server error: {resp_data.get('error', 'Unknown')}")
            except json.JSONDecodeError:
                print(f"✗ Invalid JSON response: {response}")
        else:
            print("✗ No response received (timeout)")
            
        # Clean up
        proc.terminate()
        
    except Exception as e:
        print(f"✗ Error testing subprocess: {str(e)}")


if __name__ == "__main__":
    # Test 1: Direct function calls
    print("Test 1: Direct Function Calls")
    success = asyncio.run(test_mcp_workflow())
    
    # Test 2: Subprocess (like MCP would use)
    if sys.platform != "win32":  # select doesn't work well on Windows
        print("\nTest 2: Subprocess Communication")
        test_server_process()
    
    sys.exit(0 if success else 1)