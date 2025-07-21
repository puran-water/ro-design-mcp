#!/usr/bin/env python3
"""
Test that notebooks execute successfully with utils imports.

This test runs the notebooks with sample parameters to ensure they
work correctly after the refactoring.
"""

import pytest
import papermill as pm
import tempfile
import json
from pathlib import Path
import os


class TestNotebookExecution:
    """Test notebook execution with utils imports."""
    
    @pytest.fixture
    def project_root(self):
        """Get project root directory."""
        return Path(__file__).parent.parent
    
    @pytest.fixture
    def sample_configuration(self):
        """Sample configuration for testing."""
        return {
            "feed_flow_m3h": 100.0,
            "feed_salinity_ppm": 5000,
            "target_recovery": 0.75,
            "membrane_type": "brackish",
            "n_stages": 2,
            "array_notation": "3:2",
            "total_vessels": 5,
            "total_membrane_area_m2": 1301.6,
            "stages": [
                {
                    "stage_number": 1,
                    "n_vessels": 3,
                    "feed_flow_m3h": 100.0,
                    "permeate_flow_m3h": 60.0,
                    "concentrate_flow_m3h": 40.0,
                    "stage_recovery": 0.6,
                    "design_flux_lmh": 18.0
                },
                {
                    "stage_number": 2,
                    "n_vessels": 2,
                    "feed_flow_m3h": 40.0,
                    "permeate_flow_m3h": 15.0,
                    "concentrate_flow_m3h": 25.0,
                    "stage_recovery": 0.375,
                    "design_flux_lmh": 15.0
                }
            ]
        }
    
    @pytest.fixture
    def sample_ion_composition(self):
        """Sample ion composition for MCAS testing."""
        return {
            "Na+": 1200.0,
            "Ca2+": 120.0,
            "Mg2+": 60.0,
            "Cl-": 2100.0,
            "SO4-2": 200.0,
            "HCO3-": 150.0
        }
    
    def test_mcas_notebook_execution(self, project_root, sample_configuration, sample_ion_composition):
        """Test MCAS notebook executes successfully."""
        notebook_path = project_root / "notebooks" / "ro_simulation_mcas_template.ipynb"
        
        if not notebook_path.exists():
            pytest.skip("MCAS notebook not found")
        
        with tempfile.NamedTemporaryFile(suffix='.ipynb', delete=False) as tmp:
            output_path = tmp.name
        
        try:
            # Set up environment for notebook execution
            project_root_str = str(project_root.resolve())
            
            # Execute notebook
            pm.execute_notebook(
                str(notebook_path),
                output_path,
                parameters={
                    "project_root": project_root_str,
                    "configuration": sample_configuration,
                    "feed_salinity_ppm": 5000,
                    "feed_temperature_c": 25.0,
                    "membrane_type": "brackish",
                    "membrane_properties": {},
                    "optimize_pumps": False,
                    "feed_ion_composition": sample_ion_composition,
                    "initialization_strategy": "sequential"
                },
                kernel_name="python3"
            )
            
            # If we get here, notebook executed successfully
            assert True
            
        except pm.PapermillExecutionError as e:
            pytest.fail(f"MCAS notebook execution failed: {str(e)}")
        finally:
            # Clean up
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    def test_mcas_recycle_notebook_execution(self, project_root, sample_configuration, sample_ion_composition):
        """Test MCAS recycle notebook executes successfully."""
        notebook_path = project_root / "notebooks" / "ro_simulation_mcas_recycle_template.ipynb"
        
        if not notebook_path.exists():
            pytest.skip("MCAS recycle notebook not found")
        
        # Add recycle info to configuration
        config_with_recycle = sample_configuration.copy()
        config_with_recycle["recycle_ratio"] = 0.2
        config_with_recycle["recycle_flow_m3h"] = 20.0
        config_with_recycle["effective_feed_flow_m3h"] = 120.0
        config_with_recycle["effective_feed_salinity_ppm"] = 6000.0
        
        with tempfile.NamedTemporaryFile(suffix='.ipynb', delete=False) as tmp:
            output_path = tmp.name
        
        try:
            # Set up environment for notebook execution
            project_root_str = str(project_root.resolve())
            
            # Execute notebook
            pm.execute_notebook(
                str(notebook_path),
                output_path,
                parameters={
                    "project_root": project_root_str,
                    "configuration": config_with_recycle,
                    "feed_salinity_ppm": 5000,
                    "feed_temperature_c": 25.0,
                    "membrane_type": "brackish",
                    "membrane_properties": {},
                    "optimize_pumps": False,
                    "feed_ion_composition": sample_ion_composition,
                    "initialization_strategy": "sequential"
                },
                kernel_name="python3"
            )
            
            # If we get here, notebook executed successfully
            assert True
            
        except pm.PapermillExecutionError as e:
            pytest.fail(f"MCAS recycle notebook execution failed: {str(e)}")
        finally:
            # Clean up
            if os.path.exists(output_path):
                os.unlink(output_path)
    
    def test_notebook_imports_from_utils(self, project_root):
        """Test that notebooks properly import from utils."""
        import nbformat
        
        notebooks_to_check = [
            project_root / "notebooks" / "ro_simulation_mcas_template.ipynb",
            project_root / "notebooks" / "ro_simulation_mcas_recycle_template.ipynb"
        ]
        
        for notebook_path in notebooks_to_check:
            if not notebook_path.exists():
                continue
            
            with open(notebook_path, 'r', encoding='utf-8') as f:
                nb = nbformat.read(f, as_version=4)
            
            # Check for utils imports
            has_model_builder_import = False
            has_solver_import = False
            has_extractor_import = False
            
            for cell in nb.cells:
                if cell.cell_type == 'code':
                    if "from utils.ro_model_builder import" in cell.source:
                        has_model_builder_import = True
                    if "from utils.ro_solver import" in cell.source:
                        has_solver_import = True
                    if "from utils.ro_results_extractor import" in cell.source:
                        has_extractor_import = True
            
            # All three imports should be present
            assert has_model_builder_import, f"{notebook_path.name} missing ro_model_builder import"
            assert has_solver_import, f"{notebook_path.name} missing ro_solver import"
            assert has_extractor_import, f"{notebook_path.name} missing ro_results_extractor import"


if __name__ == "__main__":
    # Can be run directly for quick testing
    import sys
    sys.exit(pytest.main([__file__, "-v"]))