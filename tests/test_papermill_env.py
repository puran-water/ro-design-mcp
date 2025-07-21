"""
Test script to simulate MCP server execution environment using papermill.

This script tests that ipopt solver can be found correctly when running
notebooks through papermill, exactly as the MCP server would.
"""

import os
import sys
import json
import tempfile
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_papermill_execution():
    """Test notebook execution in MCP-like environment."""
    
    # Add parent directory to path for imports
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    
    # Import the simulate_ro module
    from utils.simulate_ro import run_ro_simulation
    
    # Test configuration
    configuration = {
        'stages': 1,
        'elements_per_stage': [6],
        'array_notation': '1x6',
        'total_elements': 6,
        'recycle_ratio': 0.0
    }
    
    logger.info("Testing RO simulation with papermill...")
    logger.info(f"Current working directory: {os.getcwd()}")
    logger.info(f"LOCALAPPDATA: {os.environ.get('LOCALAPPDATA', 'NOT SET')}")
    logger.info(f"PATH includes: {os.environ.get('PATH', 'NOT SET')[:500]}...")
    
    # Run simulation
    try:
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
            logger.info(f"Recovery rate: {results['performance'].get('overall_recovery', 0)*100:.1f}%")
            logger.info(f"Specific energy: {results['performance'].get('specific_energy_kwh_m3', 0):.2f} kWh/m³")
            
            # Check if ipopt was used
            if 'solver_status' in results:
                logger.info(f"Solver status: {results['solver_status']}")
        else:
            logger.error(f"FAILED: {results.get('message', 'Unknown error')}")
            
            # Check if error is solver-related
            error_msg = results.get('message', '')
            if 'ipopt' in error_msg.lower() or 'solver' in error_msg.lower():
                logger.error("This appears to be a solver-related error!")
                
                # Try to find ipopt manually
                import platform
                if platform.system() == "Windows":
                    possible_paths = [
                        os.path.join(os.path.expanduser("~"), "AppData", "Local", "idaes", "bin", "ipopt.exe"),
                        os.path.join(os.environ.get('LOCALAPPDATA', ''), "idaes", "bin", "ipopt.exe"),
                        os.path.join(tempfile.gettempdir(), "idaes", "bin", "ipopt.exe")
                    ]
                    
                    logger.info("Checking for ipopt in possible locations:")
                    for path in possible_paths:
                        exists = os.path.exists(path) if path else False
                        logger.info(f"  {path}: {'EXISTS' if exists else 'NOT FOUND'}")
                
    except Exception as e:
        logger.error(f"Exception during simulation: {str(e)}")
        import traceback
        traceback.print_exc()


def test_idaes_import():
    """Test IDAES import and binary directory detection."""
    logger.info("\nTesting IDAES import and configuration...")
    
    try:
        # Test with current environment
        logger.info(f"Current LOCALAPPDATA: {os.environ.get('LOCALAPPDATA', 'NOT SET')}")
        
        import idaes
        logger.info("IDAES imported successfully")
        
        # Check binary directory
        bin_dir = idaes.bin_directory
        logger.info(f"IDAES binary directory: {bin_dir}")
        
        if bin_dir and os.path.exists(bin_dir):
            logger.info("Binary directory exists!")
            
            # List contents
            files = os.listdir(bin_dir)
            logger.info(f"Files in binary directory: {files}")
            
            # Check for ipopt
            import platform
            ipopt_exe = "ipopt.exe" if platform.system() == "Windows" else "ipopt"
            ipopt_path = os.path.join(bin_dir, ipopt_exe)
            if os.path.exists(ipopt_path):
                logger.info(f"ipopt found at: {ipopt_path}")
            else:
                logger.warning(f"ipopt NOT found at: {ipopt_path}")
        else:
            logger.error(f"Binary directory does not exist: {bin_dir}")
            
    except Exception as e:
        logger.error(f"Error testing IDAES: {str(e)}")
        import traceback
        traceback.print_exc()


def test_environment_variations():
    """Test different LOCALAPPDATA settings."""
    logger.info("\nTesting environment variations...")
    
    # Save original
    original_localappdata = os.environ.get('LOCALAPPDATA')
    
    test_cases = [
        ("Not set", None),
        ("Correct location", os.path.join(os.path.expanduser("~"), "AppData", "Local")),
        ("Temp directory", tempfile.gettempdir())
    ]
    
    for name, value in test_cases:
        logger.info(f"\nTest case: {name}")
        
        # Set environment
        if value is None:
            os.environ.pop('LOCALAPPDATA', None)
        else:
            os.environ['LOCALAPPDATA'] = value
            
        # Try to import idaes fresh
        if 'idaes' in sys.modules:
            del sys.modules['idaes']
            
        try:
            import idaes
            bin_dir = idaes.bin_directory
            logger.info(f"  LOCALAPPDATA: {os.environ.get('LOCALAPPDATA', 'NOT SET')}")
            logger.info(f"  Binary directory: {bin_dir}")
            logger.info(f"  Directory exists: {os.path.exists(bin_dir) if bin_dir else False}")
        except Exception as e:
            logger.error(f"  Error: {str(e)}")
    
    # Restore original
    if original_localappdata:
        os.environ['LOCALAPPDATA'] = original_localappdata
    else:
        os.environ.pop('LOCALAPPDATA', None)


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("MCP Server Environment Test")
    logger.info("=" * 80)
    
    # Run tests
    test_idaes_import()
    test_environment_variations()
    test_papermill_execution()
    
    logger.info("\nTest complete!")