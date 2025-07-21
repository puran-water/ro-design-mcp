
import papermill as pm
import json
import nbformat

# Parameters
params = {"project_root": "C:\\Users\\hvksh\\mcp-servers\\ro-design-mcp", "configuration": {"stage_count": 2, "array_notation": "25:12", "total_vessels": 37, "total_membrane_area_m2": 9624.44, "achieved_recovery": 0.9499751195980167, "stages": [{"stage_number": 1, "vessel_count": 25, "feed_flow_m3h": 194.61610929432143, "permeate_flow_m3h": 103.32544585397766, "concentrate_flow_m3h": 91.29066344034378, "stage_recovery": 0.5309192863254538, "membrane_area_m2": 6503.0}, {"stage_number": 2, "vessel_count": 12, "feed_flow_m3h": 91.29066344034378, "permeate_flow_m3h": 39.17082208572486, "concentrate_flow_m3h": 52.11984135461892, "stage_recovery": 0.4290780744662025, "membrane_area_m2": 3121.44}], "recycle_info": {"uses_recycle": true, "recycle_ratio": 0.22926666183699437, "recycle_flow_m3h": 44.61984135461891, "recycle_split_ratio": 0.8561008666743505, "effective_feed_flow_m3h": 194.61984135461893}, "feed_flow_m3h": 150}, "feed_salinity_ppm": 2000, "feed_temperature_c": 25.0, "membrane_type": "brackish", "membrane_properties": {}, "optimize_pumps": true, "feed_ion_composition": "{\"Na+\": 786.3, \"Cl-\": 1213.7}", "initialization_strategy": "sequential"}

# Run notebook
try:
    pm.execute_notebook(
        input_path="notebooks/ro_simulation_unified_template.ipynb",
        output_path="test_unified_output.ipynb",
        parameters=params,
        kernel_name="python3"
    )
    
    # Extract results
    with open("test_unified_output.ipynb", 'r') as f:
        nb = nbformat.read(f, as_version=4)
    
    # Find results cell
    for cell in nb.cells:
        if cell.cell_type == 'code' and 'results' in cell.metadata.get('tags', []):
            for output in cell.outputs:
                if output.output_type == 'execute_result':
                    results = eval(output.data['text/plain'])
                    
                    print("\nRESULTS:")
                    print("=" * 80)
                    print(f"Status: {results.get('status')}")
                    if results.get('status') == 'success':
                        print(f"Recovery: {results['performance']['total_recovery']*100:.1f}%")
                        print(f"Total Power: {results['economics']['total_power_kw']:.1f} kW")
                        
                        print("\nStage Results:")
                        for stage in results['stage_results']:
                            print(f"  Stage {stage['stage_number']}:")
                            print(f"    Pressure: {stage['feed_pressure_bar']:.1f} bar")
                            print(f"    Osmotic: {stage.get('feed_osmotic_pressure_bar', 0):.1f} bar")
                            print(f"    Recovery: {stage['water_recovery']*100:.1f}%")
                            print(f"    Concentrate TDS: {stage['concentrate_tds_ppm']:.0f} ppm")
                        
                        # Check if improvements worked
                        recovery = results['performance']['total_recovery']
                        stage1_p = results['stage_results'][0]['feed_pressure_bar']
                        stage2_p = results['stage_results'][1]['feed_pressure_bar']
                        
                        print("\nVERIFICATION:")
                        print(f"  Recovery matches 95%: {'YES' if abs(recovery - 0.95) < 0.01 else 'NO'}")
                        print(f"  Stage 2 > Stage 1 pressure: {'YES' if stage2_p > stage1_p else 'NO'}")
                        print(f"  Pressures > 30 bar: {'YES' if stage2_p > 30 else 'NO'}")
                        
                    else:
                        print(f"Error: {results.get('message')}")
                        
except Exception as e:
    print(f"\nERROR: {str(e)}")
    import traceback
    traceback.print_exc()
