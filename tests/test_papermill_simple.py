"""
Simple test of papermill execution with minimal notebook.
"""

import os
import sys
import json
import tempfile
import logging
from pathlib import Path
import papermill as pm
import nbformat

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_test_notebook():
    """Create a minimal test notebook."""
    nb = nbformat.v4.new_notebook()
    
    # Set notebook metadata
    nb.metadata = {
        'kernelspec': {
            'display_name': 'Python 3',
            'language': 'python',
            'name': 'python3'
        },
        'language_info': {
            'name': 'python',
            'version': '3.12.10'
        }
    }
    
    # Cell 1: Parameters
    nb.cells.append(nbformat.v4.new_code_cell(
        source='# Parameters\ntest_param = "default"',
        metadata={'tags': ['parameters']}
    ))
    
    # Cell 2: Test solver availability
    nb.cells.append(nbformat.v4.new_code_cell(
        source='''import os
import sys
from pyomo.environ import SolverFactory

print(f"LOCALAPPDATA: {os.environ.get('LOCALAPPDATA', 'NOT SET')}")
print(f"Python executable: {sys.executable}")

# Test solver
solver = SolverFactory('ipopt')
available = solver.available()
print(f"Solver available: {available}")

if available:
    print(f"Solver path: {solver.executable()}")
else:
    print("Solver NOT available!")
    
# Try to import idaes
try:
    import idaes
    print(f"IDAES bin directory: {idaes.bin_directory}")
except Exception as e:
    print(f"Error importing idaes: {e}")

result = {"solver_available": available}'''
    ))
    
    # Cell 3: Return result
    nb.cells.append(nbformat.v4.new_code_cell(
        source='result',
        metadata={'tags': ['results']}
    ))
    
    return nb

def run_test():
    """Run papermill test."""
    logger.info("Creating test notebook...")
    
    # Create temporary notebook
    with tempfile.NamedTemporaryFile(suffix='.ipynb', delete=False, mode='w') as f:
        nb = create_test_notebook()
        nbformat.write(nb, f)
        input_path = f.name
    
    # Output path
    with tempfile.NamedTemporaryFile(suffix='.ipynb', delete=False) as f:
        output_path = f.name
    
    logger.info(f"Input notebook: {input_path}")
    logger.info(f"Output notebook: {output_path}")
    
    # Run with papermill
    try:
        logger.info("Running papermill...")
        pm.execute_notebook(
            input_path=input_path,
            output_path=output_path,
            parameters={'test_param': 'from_papermill'},
            kernel_name='python3'
        )
        logger.info("Papermill execution completed!")
        
        # Read output
        with open(output_path, 'r') as f:
            out_nb = nbformat.read(f, as_version=4)
            
        # Extract outputs
        for cell in out_nb.cells:
            if cell.cell_type == 'code' and cell.outputs:
                for output in cell.outputs:
                    if output.output_type == 'stream':
                        logger.info("Cell output:")
                        for line in output.text.splitlines():
                            logger.info(f"  {line}")
                    elif output.output_type == 'error':
                        logger.error(f"Cell error: {output.ename}: {output.evalue}")
                        
    except Exception as e:
        logger.error(f"Papermill error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        try:
            os.unlink(input_path)
            os.unlink(output_path)
        except:
            pass

def main():
    logger.info("=" * 60)
    logger.info("Simple Papermill Test")
    logger.info("=" * 60)
    
    logger.info(f"Current LOCALAPPDATA: {os.environ.get('LOCALAPPDATA', 'NOT SET')}")
    
    # Ensure LOCALAPPDATA is set correctly
    if 'LOCALAPPDATA' not in os.environ:
        os.environ['LOCALAPPDATA'] = os.path.join(os.path.expanduser("~"), "AppData", "Local")
        logger.info(f"Set LOCALAPPDATA to: {os.environ['LOCALAPPDATA']}")
    
    run_test()
    
    logger.info("\nTest complete!")

if __name__ == "__main__":
    main()