"""
Test MCAS notebook execution with minimal configuration
"""
import sys
from pathlib import Path
import json
import tempfile
import papermill as pm

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Minimal test configuration
config = {
    "array_notation": "1:0",
    "feed_flow_m3h": 100.0,
    "recovery": 0.5,
    "n_stages": 1,
    "stage_count": 1,
    "stages": [{
        "stage": 1,
        "n_vessels": 10,
        "vessel_count": 10,
        "membrane_area_m2": 400.0,
        "area_m2": 400.0,
        "stage_recovery": 0.5
    }],
    "recycle_info": {"uses_recycle": False}
}

feed_composition = {
    "Na+": 1000,
    "Cl-": 1700,
    "Ca2+": 100,
    "SO4-2": 200
}

# Prepare parameters
parameters = {
    'project_root': str(project_root),
    'configuration': config,
    'feed_salinity_ppm': 3000,
    'feed_temperature_c': 25.0,
    'membrane_type': 'brackish',
    'membrane_properties': None,
    'optimize_pumps': False,  # Start without optimization
    'feed_ion_composition': feed_composition,
    'initialization_strategy': 'sequential'
}

# Run notebook
input_nb = project_root / 'notebooks' / 'ro_simulation_mcas_template.ipynb'
output_nb = tempfile.mktemp(suffix='.ipynb')

print(f"Running notebook: {input_nb}")
print(f"Output: {output_nb}")
print(f"Parameters: {json.dumps(parameters, indent=2)}")

try:
    pm.execute_notebook(
        input_nb,
        output_nb,
        parameters=parameters,
        kernel_name='python3'
    )
    print("[PASS] Notebook executed successfully")
    
    # Try to read results using nbformat
    import nbformat
    with open(output_nb, 'r') as f:
        nb = nbformat.read(f, as_version=4)
    for cell in nb.cells:
        if cell.cell_type == 'code' and 'results' in cell.metadata.get('tags', []):
            if cell.outputs:
                results = cell.outputs[0].get('data', {}).get('text/plain', '')
                print(f"Results found: {results[:100]}...")
                break
    
except Exception as e:
    print(f"[FAIL] Notebook execution failed: {e}")
    import traceback
    traceback.print_exc()
    
    # Try to get error details from notebook
    try:
        import nbformat
        with open(output_nb, 'r') as f:
            nb = nbformat.read(f, as_version=4)
        for cell in nb.cells:
            if cell.cell_type == 'code' and cell.outputs:
                for output in cell.outputs:
                    if output.get('output_type') == 'error':
                        print("\nError in notebook:")
                        print(output.get('ename', 'Unknown'))
                        print(output.get('evalue', 'No message'))
                        for line in output.get('traceback', []):
                            print(line)
    except:
        pass