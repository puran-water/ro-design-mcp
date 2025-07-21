"""
Test script that simulates MCP server environment exactly.
"""

import os
import sys
import json
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_mcp_simulation():
    """Test simulation in MCP-like environment."""
    
    # Clear any existing LOCALAPPDATA to simulate MCP environment
    original_localappdata = os.environ.pop('LOCALAPPDATA', None)
    
    try:
        # Add project root to path
        project_root = Path(__file__).parent.parent
        sys.path.insert(0, str(project_root))
        
        logger.info("Testing MCP simulation...")
        logger.info(f"LOCALAPPDATA at start: {os.environ.get('LOCALAPPDATA', 'NOT SET')}")
        
        # Import simulate_ro (this will set LOCALAPPDATA)
        from utils.simulate_ro import run_ro_simulation
        
        # Test configuration
        configuration = {
            'stages': 1,
            'elements_per_stage': [6],
            'array_notation': '1x6',
            'total_elements': 6,
            'recycle_ratio': 0.0,
            'feed_flow_m3h': 100.0,
            'stage_count': 1,
            'stages': [{
                'stage_number': 1,
                'n_vessels': 10,
                'vessel_count': 10,
                'elements_per_vessel': 6,
                'membrane_area_m2': 2229.6,  # 10 vessels * 6 elements * 37.16 m2/element
                'stage_recovery': 0.5,
                'feed_pressure_bar': 60.0
            }]
        }
        
        # Run simulation
        results = run_ro_simulation(
            configuration=configuration,
            feed_salinity_ppm=35000,
            feed_temperature_c=25.0,
            membrane_type="seawater",
            optimize_pumps=False
        )
        
        logger.info(f"Simulation status: {results.get('status', 'unknown')}")
        
        if results['status'] == 'success':
            logger.info("SUCCESS: Simulation completed successfully!")
            logger.info(f"Total recovery: {results['performance'].get('total_recovery', 0)*100:.1f}%")
            if 'specific_energy_kwh_m3' in results['economics']:
                logger.info(f"Specific energy: {results['economics']['specific_energy_kwh_m3']:.2f} kWh/m³")
        else:
            logger.error(f"FAILED: {results.get('message', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Exception: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # Restore original LOCALAPPDATA
        if original_localappdata:
            os.environ['LOCALAPPDATA'] = original_localappdata
        
        logger.info(f"LOCALAPPDATA at end: {os.environ.get('LOCALAPPDATA', 'NOT SET')}")


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("MCP Simulation Test")
    logger.info("=" * 60)
    
    test_mcp_simulation()
    
    logger.info("\nTest complete!")