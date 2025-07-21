#!/usr/bin/env python
"""
Test notebook execution with different membrane properties.
"""

import os
import json
import tempfile
from pathlib import Path
import papermill as pm
import nbformat


def test_notebook_membrane():
    """Test that notebooks use different membrane properties correctly."""
    
    # Get paths
    project_root = str(Path(__file__).parent.resolve())
    notebook_dir = Path(project_root) / "notebooks"
    template_path = notebook_dir / "ro_simulation_template.ipynb"
    
    if not template_path.exists():
        print(f"ERROR: Template not found at {template_path}")
        return
    
    # Test configuration
    test_config = {
        'array_notation': '17',
        'n_stages': 1,
        'stage_count': 1,
        'feed_flow_m3h': 100.0,
        'stages': [{
            'stage_number': 1,
            'n_vessels': 17,
            'vessel_count': 17,
            'membrane_area_m2': 4421.04,  # 17 vessels * 7 elements * 37.16 m2
            'stage_recovery': 0.5,
            'feed_flow': 100.0
        }]
    }
    
    # Test different membrane types
    membrane_tests = [
        ("brackish", None),
        ("eco_pro_400", None),
        ("custom", {"A_w": 2.0e-11, "B_s": 3.0e-8})
    ]
    
    results = {}
    
    for membrane_type, membrane_props in membrane_tests:
        print(f"\nTesting {membrane_type}...")
        
        # Create temporary output notebook
        with tempfile.NamedTemporaryFile(
            suffix=".ipynb", 
            delete=False,
            dir=tempfile.gettempdir()
        ) as tmp_output:
            output_path = tmp_output.name
        
        # Prepare parameters
        parameters = {
            "project_root": project_root,
            "configuration": test_config,
            "feed_salinity_ppm": 5000,
            "feed_temperature_c": 25.0,
            "membrane_type": membrane_type if membrane_type != "custom" else "brackish",
            "membrane_properties": membrane_props,
            "optimize_pumps": False
        }
        
        try:
            # Execute notebook
            pm.execute_notebook(
                input_path=str(template_path),
                output_path=output_path,
                parameters=parameters,
                kernel_name="python3",
                progress_bar=False,
                log_output=False
            )
            
            # Extract results
            with open(output_path, 'r', encoding='utf-8') as f:
                nb = nbformat.read(f, as_version=4)
            
            # Look for results
            for cell in nb.cells:
                if cell.cell_type == 'code' and 'results' in cell.metadata.get('tags', []):
                    for output in cell.outputs:
                        if output.output_type == 'execute_result':
                            if 'text/plain' in output.data:
                                try:
                                    result_text = output.data['text/plain']
                                    # Remove quotes if present
                                    if result_text.startswith("'") and result_text.endswith("'"):
                                        result_text = result_text[1:-1]
                                    result = eval(result_text)
                                    
                                    if result.get('status') == 'success':
                                        metrics = {
                                            'specific_energy': result['economics'].get('specific_energy_kwh_m3', 0),
                                            'total_power': result['economics'].get('total_power_kw', 0),
                                            'recovery': result['performance'].get('total_recovery', 0)
                                        }
                                        results[membrane_type] = metrics
                                        print(f"  Specific energy: {metrics['specific_energy']:.3f} kWh/m³")
                                        print(f"  Total power: {metrics['total_power']:.1f} kW")
                                        print(f"  Recovery: {metrics['recovery']:.1%}")
                                    else:
                                        print(f"  ERROR: {result.get('message', 'Unknown error')}")
                                except:
                                    pass
            
            # Also check for printed output showing membrane properties
            print("\n  Checking notebook output for membrane properties...")
            found_properties = False
            for cell in nb.cells:
                if cell.cell_type == 'code' and hasattr(cell, 'outputs'):
                    for output in cell.outputs:
                        if output.output_type == 'stream' and 'Membrane properties' in output.text:
                            print("  Found membrane property output:")
                            # Print relevant lines
                            lines = output.text.split('\n')
                            for line in lines:
                                if 'A_w' in line or 'B_s' in line or 'membrane' in line.lower():
                                    print(f"    {line.strip()}")
                            found_properties = True
            
            if not found_properties:
                print("  WARNING: No membrane property output found in notebook")
                    
        except Exception as e:
            print(f"  EXCEPTION: {str(e)}")
            results[membrane_type] = None
        finally:
            # Clean up
            try:
                os.unlink(output_path)
            except:
                pass
    
    # Analyze results
    print("\n" + "="*60)
    print("RESULTS ANALYSIS")
    print("="*60)
    
    if len(results) > 1:
        # Check for variations
        baseline = results.get('brackish')
        if baseline:
            for membrane_type, metrics in results.items():
                if metrics and membrane_type != 'brackish':
                    energy_diff = ((metrics['specific_energy'] - baseline['specific_energy']) / baseline['specific_energy']) * 100
                    power_diff = ((metrics['total_power'] - baseline['total_power']) / baseline['total_power']) * 100
                    
                    print(f"\n{membrane_type} vs brackish:")
                    print(f"  Energy difference: {energy_diff:+.1f}%")
                    print(f"  Power difference: {power_diff:+.1f}%")
                    
                    if abs(energy_diff) < 0.1 and abs(power_diff) < 0.1:
                        print("  WARNING: Results are nearly identical!")
    
    return results


if __name__ == "__main__":
    print("Notebook Membrane Properties Test")
    print("="*60)
    
    # Run the test
    results = test_notebook_membrane()
    
    print("\nTest complete!")