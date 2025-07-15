"""
WaterTAP simulation utilities for RO systems.

This module handles the execution of WaterTAP simulations using
parameterized Jupyter notebooks via papermill.
"""

import os
import json
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
import papermill as pm
import nbformat
import logging

logger = logging.getLogger(__name__)


def run_ro_simulation(
    configuration: Dict[str, Any],
    feed_salinity_ppm: float,
    feed_temperature_c: float = 25.0,
    membrane_type: str = "brackish",
    membrane_properties: Optional[Dict[str, float]] = None,
    optimize_pumps: bool = True,
    feed_ion_composition: Optional[Dict[str, float]] = None,
    initialization_strategy: str = "sequential"
) -> Dict[str, Any]:
    """
    Run WaterTAP simulation for RO system configuration.
    
    Args:
        configuration: RO configuration from optimize_ro_configuration
        feed_salinity_ppm: Feed water salinity in ppm
        feed_temperature_c: Feed temperature in Celsius
        membrane_type: Type of membrane ("brackish" or "seawater")
        membrane_properties: Optional custom membrane properties
        optimize_pumps: Whether to optimize pump pressures to match recovery targets.
            Defaults to True to ensure simulations match the configuration tool's
            hydraulic design. When True, pump pressures are optimized to achieve
            the target recovery specified in the configuration. When False, pumps
            are fixed at initial values and recovery is not constrained.
        feed_ion_composition: Optional detailed ion composition in mg/L
        initialization_strategy: Strategy for model initialization
            - "sequential": Default sequential initialization
            - "block_triangular": Block triangularization
            - "custom_guess": Custom initial values
            - "relaxation": Constraint relaxation
        
    Returns:
        Dictionary containing simulation results
    """
    try:
        # Get notebook template path
        notebook_dir = Path(__file__).parent.parent / "notebooks"
        
        # Check if recycle is configured
        recycle_info = configuration.get('recycle_info', {})
        has_recycle = recycle_info.get('uses_recycle', False) or recycle_info.get('recycle_ratio', 0) > 0
        
        # Choose template based on features needed
        if feed_ion_composition:
            template_path = notebook_dir / "ro_simulation_mcas_template.ipynb"
            logger.info("Using MCAS template for detailed ion modeling")
            if has_recycle:
                logger.warning("MCAS template does not yet support recycle. Recycle configuration will be ignored.")
                logger.warning(f"This will cause recovery mismatch: effective feed {configuration.get('feed_flow_m3h', 0):.1f} m³/h includes {recycle_info.get('recycle_flow_m3h', 0):.1f} m³/h recycle")
                logger.warning("Stage recoveries will not match configuration targets. Consider using non-MCAS simulation for systems with recycle.")
        elif has_recycle:
            template_path = notebook_dir / "ro_simulation_recycle_template.ipynb"
            logger.info(f"Using recycle-enabled template (recycle ratio: {recycle_info.get('recycle_ratio', 0)*100:.1f}%)")
        else:
            template_path = notebook_dir / "ro_simulation_template.ipynb"
            logger.info("Using standard template")
        
        if not template_path.exists():
            raise FileNotFoundError(f"Simulation template not found: {template_path}")
        
        # Create temporary output notebook
        with tempfile.NamedTemporaryFile(
            suffix=".ipynb", 
            delete=False,
            dir=tempfile.gettempdir()
        ) as tmp_output:
            output_path = tmp_output.name
        
        # Get project root directory for notebook imports
        project_root = str(Path(__file__).parent.parent.resolve())
        
        # Import platform for OS detection
        import platform
        
        # Ensure LOCALAPPDATA is set correctly for IDAES on Windows
        if platform.system() == "Windows" and 'LOCALAPPDATA' not in os.environ:
            # Set to the correct Windows AppData location
            os.environ['LOCALAPPDATA'] = os.path.join(os.path.expanduser("~"), "AppData", "Local")
            logger.info(f"Set LOCALAPPDATA to: {os.environ['LOCALAPPDATA']}")
        
        # Add IDAES binary directory to PATH for solver executables (especially ipopt)
        try:
            import idaes
            # Force reload to pick up correct LOCALAPPDATA
            import importlib
            importlib.reload(idaes)
            
            idaes_bin_dir = idaes.bin_directory
            if idaes_bin_dir and os.path.exists(idaes_bin_dir):
                # Add to PATH
                if 'PATH' in os.environ:
                    os.environ['PATH'] = f"{idaes_bin_dir};{os.environ['PATH']}"
                else:
                    os.environ['PATH'] = idaes_bin_dir
                logger.info(f"Added IDAES binary directory to PATH: {idaes_bin_dir}")
                
                # Check for ipopt executable
                ipopt_exe = "ipopt.exe" if platform.system() == "Windows" else "ipopt"
                ipopt_path = os.path.join(idaes_bin_dir, ipopt_exe)
                if os.path.exists(ipopt_path):
                    logger.info(f"Found ipopt executable at: {ipopt_path}")
                else:
                    logger.warning(f"ipopt executable not found at: {ipopt_path}")
                    logger.warning("You may need to run 'idaes get-extensions' to install solvers")
            else:
                logger.warning(f"IDAES binary directory not found or doesn't exist: {idaes_bin_dir}")
        except ImportError:
            logger.warning("Could not import idaes to get binary directory path")
        except Exception as e:
            logger.warning(f"Error setting up IDAES binary path: {str(e)}")
        
        # Add Pyomo library path for PyNumero DLL
        if platform.system() == "Windows":
            pyomo_lib_path = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Pyomo", "lib")
            if os.path.exists(pyomo_lib_path):
                # Add to PATH for DLL loading
                if 'PATH' in os.environ:
                    os.environ['PATH'] = f"{pyomo_lib_path};{os.environ['PATH']}"
                else:
                    os.environ['PATH'] = pyomo_lib_path
                logger.info(f"Added Pyomo lib path to PATH: {pyomo_lib_path}")
        
        # Prepare parameters
        parameters = {
            "project_root": project_root,
            "configuration": configuration,
            "feed_salinity_ppm": feed_salinity_ppm,
            "feed_temperature_c": feed_temperature_c,
            "membrane_type": membrane_type,
            "membrane_properties": membrane_properties or {},
            "optimize_pumps": optimize_pumps,
            # Pass solver paths to notebook
            "idaes_bin_dir": idaes_bin_dir if 'idaes_bin_dir' in locals() else None,
            "pyomo_lib_path": pyomo_lib_path if 'pyomo_lib_path' in locals() and os.path.exists(pyomo_lib_path) else None
        }
        
        # Add ion composition if using MCAS template
        if feed_ion_composition:
            parameters["feed_ion_composition"] = feed_ion_composition
            parameters["initialization_strategy"] = initialization_strategy
        
        logger.info(f"Running WaterTAP simulation for {configuration['array_notation']} array")
        
        # Log optimize_pumps setting
        if optimize_pumps:
            logger.info("Pump optimization enabled - will match configuration recovery targets")
        else:
            logger.info("Pump optimization disabled - using fixed pump pressures")
        
        # Execute notebook with papermill
        try:
            pm.execute_notebook(
                input_path=str(template_path),
                output_path=output_path,
                parameters=parameters,
                kernel_name="python3",
                progress_bar=False,
                log_output=False
            )
        except pm.PapermillExecutionError as e:
            logger.error(f"Notebook execution failed: {str(e)}")
            # Try to extract partial results
            results = extract_notebook_results(output_path)
            if results and "error" not in results:
                results["status"] = "partial"
                results["message"] = f"Simulation partially completed: {str(e)}"
            else:
                results = {
                    "status": "error",
                    "message": f"Simulation failed: {str(e)}",
                    "performance": {},
                    "economics": {},
                    "stage_results": [],
                    "mass_balance": {}
                }
            return results
        
        # Extract results from executed notebook
        results = extract_notebook_results(output_path)
        
        # Clean up temporary file
        try:
            os.unlink(output_path)
        except:
            pass
        
        return results
        
    except Exception as e:
        logger.error(f"Error in run_ro_simulation: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "performance": {},
            "economics": {},
            "stage_results": [],
            "mass_balance": {}
        }


def extract_notebook_results(notebook_path: str) -> Dict[str, Any]:
    """
    Extract results from executed notebook.
    
    Args:
        notebook_path: Path to executed notebook
        
    Returns:
        Dictionary containing simulation results
    """
    try:
        # Read notebook
        with open(notebook_path, 'r') as f:
            nb = nbformat.read(f, as_version=4)
        
        # Find results cell (tagged with "results")
        for cell in nb.cells:
            if cell.cell_type == 'code' and 'results' in cell.metadata.get('tags', []):
                # Look for output
                for output in cell.outputs:
                    if output.output_type == 'execute_result':
                        # Parse the result data
                        if 'application/json' in output.data:
                            return json.loads(output.data['application/json'])
                        elif 'text/plain' in output.data:
                            # Try to parse as JSON
                            try:
                                # Remove quotes if present
                                text = output.data['text/plain']
                                if text.startswith("'") and text.endswith("'"):
                                    text = text[1:-1]
                                return json.loads(text)
                            except:
                                # Try eval as last resort
                                try:
                                    return eval(output.data['text/plain'])
                                except:
                                    pass
        
        # If no results found, check for errors
        for cell in nb.cells:
            if cell.cell_type == 'code':
                for output in cell.outputs:
                    if output.output_type == 'error':
                        return {
                            "status": "error",
                            "message": f"{output.ename}: {output.evalue}",
                            "performance": {},
                            "economics": {},
                            "stage_results": [],
                            "mass_balance": {}
                        }
        
        # No results found
        return {
            "status": "error",
            "message": "No results found in notebook",
            "performance": {},
            "economics": {},
            "stage_results": [],
            "mass_balance": {}
        }
        
    except Exception as e:
        logger.error(f"Error extracting notebook results: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to extract results: {str(e)}",
            "performance": {},
            "economics": {},
            "stage_results": [],
            "mass_balance": {}
        }


def calculate_lcow(
    capital_cost: float,
    annual_opex: float,
    annual_production_m3: float,
    discount_rate: float = 0.08,
    plant_lifetime_years: int = 20
) -> float:
    """
    Calculate Levelized Cost of Water (LCOW).
    
    Args:
        capital_cost: Total capital investment ($)
        annual_opex: Annual operating expenses ($/year)
        annual_production_m3: Annual water production (m³/year)
        discount_rate: Discount rate (fraction)
        plant_lifetime_years: Plant lifetime (years)
        
    Returns:
        LCOW in $/m³
    """
    # Calculate capital recovery factor
    crf = (discount_rate * (1 + discount_rate)**plant_lifetime_years) / \
          ((1 + discount_rate)**plant_lifetime_years - 1)
    
    # Annualized capital cost
    annual_capital = capital_cost * crf
    
    # Total annual cost
    total_annual_cost = annual_capital + annual_opex
    
    # LCOW
    lcow = total_annual_cost / annual_production_m3
    
    return lcow


def estimate_capital_cost(
    total_membrane_area_m2: float,
    total_power_kw: float,
    membrane_cost_per_m2: Optional[float] = None,
    power_cost_per_kw: Optional[float] = None,
    indirect_cost_factor: Optional[float] = None
) -> float:
    """
    Estimate capital cost for RO system.
    
    Args:
        total_membrane_area_m2: Total membrane area
        total_power_kw: Total installed power
        membrane_cost_per_m2: Membrane cost ($/m²), defaults to config value
        power_cost_per_kw: Power equipment cost ($/kW), defaults to config value
        indirect_cost_factor: Multiplier for indirect costs, defaults to config value
        
    Returns:
        Total capital cost ($)
    """
    # Import config utilities
    from .config import get_config
    
    # Use config values if not provided
    if membrane_cost_per_m2 is None:
        membrane_cost_per_m2 = get_config('capital.membrane_cost_usd_m2', 30.0)
    if power_cost_per_kw is None:
        power_cost_per_kw = get_config('capital.power_equipment_cost_usd_kw', 1000.0)
    if indirect_cost_factor is None:
        indirect_cost_factor = get_config('capital.indirect_cost_factor', 2.5)
    
    # Direct costs
    membrane_cost = total_membrane_area_m2 * membrane_cost_per_m2
    power_equipment_cost = total_power_kw * power_cost_per_kw
    
    direct_cost = membrane_cost + power_equipment_cost
    
    # Total installed cost
    total_cost = direct_cost * indirect_cost_factor
    
    return total_cost