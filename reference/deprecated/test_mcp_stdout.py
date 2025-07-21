#!/usr/bin/env python3
"""
Test that the MCP server doesn't output to stdout, especially with recycle configurations.
"""

import subprocess
import sys
import json
import time


def test_server_stdout():
    """Test that server produces only valid JSON on stdout."""
    print("Testing MCP server stdout output...", file=sys.stderr)
    
    # Start the server as a subprocess
    proc = subprocess.Popen(
        [sys.executable, "server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=0  # Unbuffered
    )
    
    try:
        # Wait a moment for server to start
        time.sleep(1)
        
        # Send initialize request
        initialize_request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "0.1.0",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            },
            "id": 1
        }
        
        proc.stdin.write(json.dumps(initialize_request) + '\n')
        proc.stdin.flush()
        
        # Read response
        response_line = proc.stdout.readline()
        
        # Try to parse as JSON
        try:
            response = json.loads(response_line)
            print(f"✓ Got valid JSON response: {response.get('result', {}).get('serverInfo', {}).get('name', 'unknown')}", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"✗ ERROR: Invalid JSON on stdout: {response_line}", file=sys.stderr)
            print(f"  JSON Error: {e}", file=sys.stderr)
            return False
            
        # Test optimize_ro_configuration
        print("\nTesting optimize_ro_configuration...", file=sys.stderr)
        optimize_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "optimize_ro_configuration",
                "arguments": {
                    "feed_flow_m3h": 150.0,
                    "water_recovery_fraction": 0.75,
                    "membrane_type": "brackish"
                }
            },
            "id": 2
        }
        
        proc.stdin.write(json.dumps(optimize_request) + '\n')
        proc.stdin.flush()
        
        # Read response
        response_line = proc.stdout.readline()
        
        try:
            response = json.loads(response_line)
            print(f"✓ Got valid JSON response for optimize_ro_configuration", file=sys.stderr)
            
            # Debug response structure
            if 'error' in response:
                print(f"✗ ERROR in response: {response['error']}", file=sys.stderr)
                return False
                
            result = response.get('result', {})
            print(f"Response has result: {'result' in response}", file=sys.stderr)
            if result:
                print(f"Result keys: {list(result.keys())[:5]}...", file=sys.stderr)
            
            # Try different paths to find configurations
            configs = []
            if 'structuredContent' in result:
                configs = result['structuredContent'].get('configurations', [])
            elif 'content' in result:
                # The content might be a JSON string
                for content_item in result.get('content', []):
                    if content_item.get('type') == 'text':
                        try:
                            content_data = json.loads(content_item.get('text', '{}'))
                            configs = content_data.get('configurations', [])
                            break
                        except:
                            pass
            print(f"Found {len(configs)} configurations", file=sys.stderr)
            
            recycle_config = None
            non_recycle_config = None
            
            for config in configs:
                recycle_info = config.get('recycle_info', {})
                uses_recycle = recycle_info.get('uses_recycle', False)
                print(f"  - {config['array_notation']}: uses_recycle={uses_recycle}", file=sys.stderr)
                
                if uses_recycle:
                    recycle_config = config
                else:
                    non_recycle_config = config
                    
            # Use whichever we found (prefer recycle for testing)
            test_config = recycle_config or non_recycle_config
            
            if not test_config:
                print("✗ ERROR: No configuration found", file=sys.stderr)
                return False
                
            config_type = "recycle" if test_config.get('recycle_info', {}).get('uses_recycle', False) else "non-recycle"
            print(f"✓ Using {config_type} configuration: {test_config['array_notation']}", file=sys.stderr)
            
        except json.JSONDecodeError as e:
            print(f"✗ ERROR: Invalid JSON on stdout: {response_line}", file=sys.stderr)
            print(f"  JSON Error: {e}", file=sys.stderr)
            return False
            
        # Test simulate_ro_system with selected configuration
        print(f"\nTesting simulate_ro_system with {config_type} configuration...", file=sys.stderr)
        simulate_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "simulate_ro_system",
                "arguments": {
                    "configuration": test_config,
                    "feed_salinity_ppm": 2000,
                    "feed_ion_composition": json.dumps({"Na_+": 786, "Cl_-": 1214}),
                    "membrane_type": "brackish",
                    "optimize_pumps": False  # Start with False
                }
            },
            "id": 3
        }
        
        proc.stdin.write(json.dumps(simulate_request) + '\n')
        proc.stdin.flush()
        
        # Read response with timeout
        print("Waiting for simulate_ro_system response...", file=sys.stderr)
        start_time = time.time()
        timeout = 60  # 60 seconds timeout
        
        while True:
            if proc.stdout.readable():
                response_line = proc.stdout.readline()
                if response_line:
                    break
            
            if time.time() - start_time > timeout:
                print(f"✗ ERROR: Timeout waiting for response after {timeout} seconds", file=sys.stderr)
                # Check stderr for any errors
                stderr_output = proc.stderr.read()
                if stderr_output:
                    print(f"STDERR output:\n{stderr_output}", file=sys.stderr)
                return False
                
            time.sleep(0.1)
        
        try:
            response = json.loads(response_line)
            print(f"✓ Got valid JSON response for simulate_ro_system", file=sys.stderr)
            
            if response.get('result', {}).get('structuredContent', {}).get('status') == 'success':
                print("✓ Simulation completed successfully!", file=sys.stderr)
            else:
                print(f"✗ Simulation failed: {response.get('result', {}).get('structuredContent', {}).get('message', 'Unknown error')}", file=sys.stderr)
                
        except json.JSONDecodeError as e:
            print(f"✗ ERROR: Invalid JSON on stdout: {response_line}", file=sys.stderr)
            print(f"  JSON Error: {e}", file=sys.stderr)
            # Print any stderr output
            stderr_output = proc.stderr.read()
            if stderr_output:
                print(f"STDERR output:\n{stderr_output}", file=sys.stderr)
            return False
            
        return True
        
    finally:
        # Clean up
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    success = test_server_stdout()
    if success:
        print("\n✅ All tests passed! Server produces only valid JSON on stdout.", file=sys.stderr)
        sys.exit(0)
    else:
        print("\n❌ Tests failed! Server is corrupting stdout.", file=sys.stderr)
        sys.exit(1)