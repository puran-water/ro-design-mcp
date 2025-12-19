"""
Direct test of solver availability in different environments.
"""

import os
import sys
import platform
import tempfile
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def find_ipopt():
    """Find ipopt executable in various locations."""
    ipopt_exe = "ipopt.exe" if platform.system() == "Windows" else "ipopt"
    
    possible_locations = [
        # Standard IDAES location
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "idaes", "bin", ipopt_exe),
        # Temp location
        os.path.join(tempfile.gettempdir(), "idaes", "bin", ipopt_exe),
        # From LOCALAPPDATA
        os.path.join(os.environ.get('LOCALAPPDATA', ''), "idaes", "bin", ipopt_exe) if os.environ.get('LOCALAPPDATA') else None,
    ]
    
    # Check PATH
    if 'PATH' in os.environ:
        for path_dir in os.environ['PATH'].split(';' if platform.system() == 'Windows' else ':'):
            possible_locations.append(os.path.join(path_dir, ipopt_exe))
    
    found_locations = []
    for loc in possible_locations:
        if loc and os.path.exists(loc):
            found_locations.append(loc)
    
    return found_locations

def test_pyomo_solver():
    """Test if Pyomo can find ipopt."""
    try:
        from pyomo.environ import SolverFactory
        from pyomo.opt import SolverStatus, TerminationCondition
        
        # Try to create ipopt solver
        solver = SolverFactory('ipopt')
        logger.info(f"Solver factory created: {solver}")
        
        # Check if solver is available
        available = solver.available()
        logger.info(f"Solver available: {available}")
        
        if available:
            # Get solver executable path
            if hasattr(solver, 'executable'):
                logger.info(f"Solver executable: {solver.executable()}")
        else:
            logger.warning("Solver not available!")
            
            # Try to find manually
            locations = find_ipopt()
            if locations:
                logger.info("Found ipopt at these locations:")
                for loc in locations:
                    logger.info(f"  - {loc}")
                
                # Try setting the first found location
                solver.set_executable(locations[0])
                logger.info(f"Set solver executable to: {locations[0]}")
                
                # Test again
                available = solver.available()
                logger.info(f"Solver available after setting path: {available}")
            else:
                logger.error("Could not find ipopt executable anywhere!")
                
    except Exception as e:
        logger.error(f"Error testing Pyomo solver: {str(e)}")
        import traceback
        traceback.print_exc()

def test_idaes_config():
    """Test IDAES configuration and binary locations."""
    logger.info("\nTesting IDAES configuration...")
    
    try:
        import idaes
        logger.info(f"IDAES version: {idaes.__version__}")
        logger.info(f"IDAES binary directory: {idaes.bin_directory}")
        
        # Check config file
        config_file = os.path.join(os.path.expanduser("~"), ".idaes", "idaes.conf")
        if os.path.exists(config_file):
            logger.info(f"IDAES config file exists: {config_file}")
            with open(config_file, 'r') as f:
                logger.info("Config contents:")
                for line in f:
                    logger.info(f"  {line.strip()}")
        else:
            logger.warning(f"IDAES config file not found: {config_file}")
            
    except Exception as e:
        logger.error(f"Error checking IDAES config: {str(e)}")

def main():
    logger.info("=" * 60)
    logger.info("Direct Solver Test")
    logger.info("=" * 60)
    
    # Log environment
    logger.info(f"Platform: {platform.system()}")
    logger.info(f"Python: {sys.version}")
    logger.info(f"LOCALAPPDATA: {os.environ.get('LOCALAPPDATA', 'NOT SET')}")
    logger.info(f"Working directory: {os.getcwd()}")
    
    # Find ipopt
    logger.info("\nSearching for ipopt executable...")
    locations = find_ipopt()
    if locations:
        logger.info("Found ipopt at:")
        for loc in locations:
            logger.info(f"  - {loc}")
    else:
        logger.error("ipopt not found!")
    
    # Test IDAES config
    test_idaes_config()
    
    # Test Pyomo solver
    logger.info("\nTesting Pyomo solver factory...")
    test_pyomo_solver()
    
    logger.info("\nTest complete!")

if __name__ == "__main__":
    main()