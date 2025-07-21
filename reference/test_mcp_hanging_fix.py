#!/usr/bin/env python3
"""
Test script to verify the MCP hanging fix.

This simulates the MCP server environment and tests that imports don't
cause hanging by polluting stdout.
"""

import sys
import json
import io
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def simulate_mcp_environment():
    """
    Simulate MCP environment where stdout is used for JSON-RPC.
    """
    print("="*70)
    print("TEST: MCP HANGING FIX")
    print("="*70)
    
    # Test 1: Verify environment setup works
    print("\nTest 1: Environment setup...")
    try:
        from utils.import_protection import initialize_mcp_environment
        initialize_mcp_environment()
        print("SUCCESS: Environment initialized successfully")
    except Exception as e:
        print(f"FAILED: Environment setup failed: {str(e)}")
        return False
    
    # Test 2: Test imports with stdout capture
    print("\nTest 2: Testing imports with stdout capture...")
    
    # Capture stdout to detect any pollution
    original_stdout = sys.stdout
    captured_output = io.StringIO()
    
    try:
        # Redirect stdout to capture any output
        sys.stdout = captured_output
        
        # Try importing the simulation module
        start_time = time.time()
        from utils.stdio_safe_simulation import run_simulation_safe
        import_time = time.time() - start_time
        
        # Restore stdout
        sys.stdout = original_stdout
        
        # Check if any output was captured
        output = captured_output.getvalue()
        if output:
            print(f"FAILED: Import produced stdout output ({len(output)} chars):")
            print(f"  First 200 chars: {repr(output[:200])}")
            return False
        else:
            print(f"SUCCESS: Import successful with no stdout pollution (took {import_time:.2f}s)")
            
    except Exception as e:
        sys.stdout = original_stdout
        print(f"FAILED: Import failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 3: Test actual simulation call
    print("\nTest 3: Testing simulation execution...")
    
    # Test configuration
    test_config = {
        'array_notation': '17:8',
        'stage_count': 2,
        'n_stages': 2,
        'feed_flow_m3h': 150,
        'stages': [
            {
                'stage_number': 1,
                'vessel_count': 17,
                'elements_per_vessel': 6,
                'membrane_area_m2': 3733.2,
                'stage_recovery': 0.55,
                'feed_flow_m3h': 150
            },
            {
                'stage_number': 2,
                'vessel_count': 8,
                'elements_per_vessel': 6,
                'membrane_area_m2': 1756.8,
                'stage_recovery': 0.45,
                'feed_flow_m3h': 67.5
            }
        ],
        'total_recovery': 0.75,
        'total_membrane_area_m2': 5490
    }
    
    # Capture stdout during simulation
    sys.stdout = captured_output = io.StringIO()
    
    try:
        start_time = time.time()
        result = run_simulation_safe(
            configuration=test_config,
            feed_salinity_ppm=2000,
            feed_temperature_c=25.0,
            membrane_type='eco_pro_400',
            optimize_pumps=True,
            use_direct_simulation=True
        )
        sim_time = time.time() - start_time
        
        # Restore stdout
        sys.stdout = original_stdout
        
        # Check output
        output = captured_output.getvalue()
        if output:
            print(f"FAILED: Simulation produced stdout output ({len(output)} chars)")
            print(f"  First 200 chars: {repr(output[:200])}")
            return False
        
        # Check result
        if result.get('status') == 'success':
            print(f"SUCCESS: Simulation successful (took {sim_time:.2f}s)")
            print(f"  Recovery: {result['performance']['total_recovery']*100:.1f}%")
            print(f"  Specific energy: {result['economics']['specific_energy_kwh_m3']:.2f} kWh/m³")
        else:
            print(f"FAILED: Simulation failed: {result.get('error', 'Unknown error')}")
            return False
            
    except Exception as e:
        sys.stdout = original_stdout
        print(f"FAILED: Simulation error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test 4: Simulate JSON-RPC communication
    print("\nTest 4: Simulating MCP JSON-RPC communication...")
    
    # Create a mock JSON-RPC request
    request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "simulate_ro_system",
            "arguments": {
                "configuration": test_config,
                "feed_salinity_ppm": 2000,
                "feed_temperature_c": 25.0,
                "membrane_type": "eco_pro_400",
                "optimize_pumps": True
            }
        },
        "id": 1
    }
    
    # Simulate sending request (would go to stdin in real MCP)
    request_json = json.dumps(request)
    print(f"  Request size: {len(request_json)} bytes")
    
    # Simulate response (would go to stdout in real MCP)
    response = {
        "jsonrpc": "2.0",
        "result": {
            "content": [{
                "type": "text",
                "text": f"Simulation completed successfully. Recovery: {result['performance']['total_recovery']*100:.1f}%"
            }]
        },
        "id": 1
    }
    
    # Ensure we can serialize the response
    try:
        response_json = json.dumps(response)
        print(f"SUCCESS: JSON-RPC response serializable ({len(response_json)} bytes)")
    except Exception as e:
        print(f"FAILED: JSON serialization failed: {str(e)}")
        return False
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print("All tests passed! The MCP hanging issue should be resolved.")
    print("\nKey fixes applied:")
    print("1. Heavy imports moved to function level")
    print("2. STDIO protection added for imports")
    print("3. Environment variables set to disable interactive features")
    print("4. Logging directed to stderr instead of stdout")
    
    return True


if __name__ == "__main__":
    success = simulate_mcp_environment()
    sys.exit(0 if success else 1)