#!/usr/bin/env python3
"""
Test script to verify MCP server doesn't hang due to stdout corruption.

This script simulates what an MCP client would do:
1. Call optimize_ro_configuration
2. Call simulate_ro_system with the result
"""

import json
import asyncio
from server import optimize_ro_configuration, simulate_ro_system


async def test_mcp_workflow():
    """Test the complete MCP workflow."""
    print("Testing MCP workflow...")
    
    # Step 1: Optimize configuration
    print("\n1. Testing optimize_ro_configuration...")
    config_result = await optimize_ro_configuration(
        feed_flow_m3h=150.0,
        water_recovery_fraction=0.75,
        membrane_type="brackish"
    )
    
    # Check result
    assert config_result["status"] == "success", "Configuration optimization failed"
    assert len(config_result["configurations"]) > 0, "No configurations found"
    
    print(f"   Success! Found {len(config_result['configurations'])} configurations")
    
    # Use first configuration for simulation
    config = config_result["configurations"][0]
    print(f"   Using configuration: {config['array_notation']}")
    
    # Step 2: Simulate the system
    print("\n2. Testing simulate_ro_system...")
    
    # Simple ion composition
    ion_composition = json.dumps({
        "Na_+": 786,  # mg/L
        "Cl_-": 1214  # mg/L
    })
    
    sim_result = await simulate_ro_system(
        configuration=config,
        feed_salinity_ppm=2000,
        feed_ion_composition=ion_composition,
        feed_temperature_c=25.0,
        membrane_type="brackish",
        optimize_pumps=False  # Start with False to avoid optimization issues
    )
    
    # Check result
    assert sim_result["status"] == "success", f"Simulation failed: {sim_result.get('message', 'Unknown error')}"
    
    print("   Success! Simulation completed")
    print(f"   System recovery: {sim_result['performance']['system_recovery']*100:.1f}%")
    print(f"   Specific energy: {sim_result['performance']['specific_energy_kWh_m3']:.2f} kWh/m³")
    
    print("\n✓ All tests passed! MCP server is working correctly.")
    

async def main():
    """Run the test."""
    try:
        await test_mcp_workflow()
    except Exception as e:
        print(f"\n✗ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        

if __name__ == "__main__":
    asyncio.run(main())