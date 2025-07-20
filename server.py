#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RO Design MCP Server

An STDIO MCP server for reverse osmosis system design optimization.
Provides tools for vessel array configuration and WaterTAP simulation.
"""

import os
import sys
from pathlib import Path

# Load environment variables before any other imports
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed, continue without it
    pass

# Set required environment variables for IDAES
if 'LOCALAPPDATA' not in os.environ:
    if sys.platform == 'win32':
        # On Windows, use the standard AppData\Local path
        os.environ['LOCALAPPDATA'] = os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    else:
        # On other platforms, use a reasonable fallback
        os.environ['LOCALAPPDATA'] = os.path.join(os.path.expanduser('~'), '.local')

# Set Jupyter platform dirs to avoid deprecation warning
if 'JUPYTER_PLATFORM_DIRS' not in os.environ:
    os.environ['JUPYTER_PLATFORM_DIRS'] = '1'

# Now do the rest of the imports
import json
import logging
from typing import Dict, Any, Optional, List
import time
from datetime import datetime

from fastmcp import FastMCP, Context

# Import our utilities
from utils.optimize_ro import optimize_vessel_array_configuration
from utils.validation import (
    validate_optimize_ro_inputs,
    parse_flux_targets
)
from utils.response_formatter import (
    format_optimization_response,
    format_error_response,
    format_simulation_response
)
from utils.helpers import validate_salinity
from utils.stdout_redirect import redirect_stdout_to_stderr

# Configure logging for MCP - CRITICAL for protocol integrity
from utils.logging_config import configure_mcp_logging, get_configured_logger
configure_mcp_logging()
logger = get_configured_logger(__name__)

# Create FastMCP instance
mcp = FastMCP("RO Design Server")


@mcp.tool()
async def optimize_ro_configuration(
    feed_flow_m3h: float,
    water_recovery_fraction: float,
    membrane_type: str = "brackish",
    allow_recycle: bool = True,
    max_recycle_ratio: float = 0.9,
    flux_targets_lmh: Optional[str] = None,
    flux_tolerance: Optional[float] = None
) -> Dict[str, Any]:
    """
    Generate optimal RO vessel array configuration based on flow and recovery.
    
    This tool determines ALL viable vessel array configurations (1, 2, and 3 stages)
    to achieve target recovery while meeting flux and concentrate flow constraints.
    
    Args:
        feed_flow_m3h: Feed flow rate in m³/h
        water_recovery_fraction: Target water recovery as fraction (0-1)
        membrane_type: Type of membrane ("brackish" or "seawater")
        allow_recycle: Whether to allow concentrate recycle for high recovery
        max_recycle_ratio: Maximum allowed recycle ratio (0-1)
        flux_targets_lmh: Optional flux targets in LMH. Accepts:
                         - Simple numbers: "20" or "18.5"
                         - JSON arrays: "[22, 18, 15]" for per-stage targets
        flux_tolerance: Optional flux tolerance as fraction (e.g., 0.1 for ±10%)
    
    Returns:
        Dictionary containing:
        - status: "success" or error status
        - configurations: List of ALL viable configurations (1, 2, 3 stages)
        - summary: Feed conditions and configuration count
        Each configuration includes vessel counts, flows, and recovery metrics
    
    Example:
        ```python
        # Basic configuration with defaults
        config = await optimize_ro_configuration(
            feed_flow_m3h=100,
            water_recovery_fraction=0.75,
            membrane_type="brackish"
        )
        
        # Custom flux targets
        config = await optimize_ro_configuration(
            feed_flow_m3h=100,
            water_recovery_fraction=0.75,
            flux_targets_lmh="[20, 17, 14]",  # Higher flux targets as JSON string
            flux_tolerance=0.15  # ±15% tolerance
        )
        ```
    """
    # Store request parameters for error reporting
    request_params = {
        "feed_flow_m3h": feed_flow_m3h,
        "water_recovery_fraction": water_recovery_fraction,
        "membrane_type": membrane_type,
        "allow_recycle": allow_recycle,
        "max_recycle_ratio": max_recycle_ratio,
        "flux_targets_lmh": flux_targets_lmh,
        "flux_tolerance": flux_tolerance
    }
    
    try:
        # Validate all inputs and parse flux targets
        parsed_flux_targets, validated_flux_tolerance = validate_optimize_ro_inputs(
            feed_flow_m3h=feed_flow_m3h,
            water_recovery_fraction=water_recovery_fraction,
            membrane_type=membrane_type,
            allow_recycle=allow_recycle,
            max_recycle_ratio=max_recycle_ratio,
            flux_targets_lmh=flux_targets_lmh,
            flux_tolerance=flux_tolerance
        )
        
        # Log the request
        logger.info(f"Optimizing RO configuration: {feed_flow_m3h} m³/h, "
                   f"{water_recovery_fraction*100:.0f}% recovery, {membrane_type}")
        
        # Note: Feed salinity is NOT needed for configuration optimization
        # We use a placeholder value for internal calculations
        placeholder_salinity = 5000 if membrane_type == "brackish" else 35000
        
        # Call the optimization function - now returns all viable configurations
        configurations = optimize_vessel_array_configuration(
            feed_flow_m3h=feed_flow_m3h,
            target_recovery=water_recovery_fraction,
            feed_salinity_ppm=placeholder_salinity,
            membrane_type=membrane_type,
            allow_recycle=allow_recycle,
            max_recycle_ratio=max_recycle_ratio,
            flux_targets_lmh=parsed_flux_targets,
            flux_tolerance=validated_flux_tolerance
        )
        
        # Format the response using the formatter
        response = format_optimization_response(
            configurations=configurations,
            feed_flow_m3h=feed_flow_m3h,
            target_recovery=water_recovery_fraction,
            membrane_type=membrane_type
        )
        
        # Add warnings if no configuration met the target
        configs_meeting_target = [
            c for c in response["configurations"] 
            if c["recovery_achievement"]["met_target"]
        ]
        
        if not configs_meeting_target and response["configurations"]:
            best_recovery = max(
                c["achieved_recovery"] for c in response["configurations"]
            )
            response["warning"] = (
                f"No configuration achieved the target recovery of {water_recovery_fraction:.1%}. "
                f"Best achieved: {best_recovery:.1%}"
            )
            response["recommendation"] = (
                "Consider adjusting flux targets, allowing recycle, "
                "or accepting lower recovery."
            )
        
        return response
        
    except Exception as e:
        logger.error(f"Error in optimize_ro_configuration: {str(e)}")
        return format_error_response(e, request_params)


@mcp.tool()
async def simulate_ro_system(
    configuration: Dict[str, Any],
    feed_salinity_ppm: float,
    feed_ion_composition: str,
    feed_temperature_c: float = 25.0,
    membrane_type: str = "brackish",
    membrane_properties: Optional[Dict[str, float]] = None,
    optimize_pumps: bool = True,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Run WaterTAP simulation for the specified RO configuration using MCAS property package.
    
    This tool executes a parameterized Jupyter notebook that creates a WaterTAP model
    with detailed ion modeling, runs the simulation, and returns complete results.
    The notebook runs in a subprocess to avoid blocking issues.
    
    Args:
        configuration: Output from optimize_ro_configuration tool
        feed_salinity_ppm: Feed water salinity in ppm
        feed_ion_composition: Required JSON string of ion concentrations in mg/L
                             e.g., '{"Na+": 1200, "Cl-": 2100, "Ca2+": 120}'
        feed_temperature_c: Feed temperature in Celsius (default 25°C)
        membrane_type: Type of membrane ("brackish" or "seawater")
        membrane_properties: Optional custom membrane properties
        optimize_pumps: Whether to optimize pump pressures to match recovery targets exactly (default True)
    
    Returns:
        Dictionary containing:
        - status: "success" indicating simulation completed successfully  
        - results: Complete simulation results including performance, economics, etc.
        - message: Status message with execution time
        - notebook_path: Path to the output notebook for reference
    
    Note:
        This tool waits for simulation completion and returns full results in one call.
        Typical execution time is 20-30 seconds for standard configurations.
    
    Example:
        ```python
        # Run complete MCAS simulation
        result = await simulate_ro_system(
            configuration=config_from_optimization,
            feed_salinity_ppm=5000,
            feed_temperature_c=25.0,
            feed_ion_composition='{"Na+": 1200, "Ca2+": 120, "Mg2+": 60, "Cl-": 2100, "SO4-2": 200, "HCO3-": 150}'
        )
        # Returns complete results immediately
        print(result['results']['performance']['system_recovery'])
        ```
    """
    try:
        import papermill as pm
        from pathlib import Path
        from datetime import datetime
        
        # Validate inputs first
        if not isinstance(configuration, dict):
            raise ValueError("configuration must be a dictionary from optimize_ro_configuration")
        
        if "stages" not in configuration:
            raise ValueError("configuration must contain 'stages' key")
        
        validate_salinity(feed_salinity_ppm, "feed_salinity_ppm")
        
        if not 0 < feed_temperature_c < 100:
            raise ValueError(f"Temperature {feed_temperature_c}°C is outside reasonable range")
        
        if membrane_type not in ["brackish", "seawater"]:
            raise ValueError(f"Invalid membrane_type: {membrane_type}")
        
        # Parse ion composition (required)
        try:
            parsed_ion_composition = json.loads(feed_ion_composition)
            # Validate it's a dictionary with numeric values
            if not isinstance(parsed_ion_composition, dict):
                raise ValueError("Ion composition must be a JSON object")
            for ion, conc in parsed_ion_composition.items():
                if not isinstance(conc, (int, float)) or conc < 0:
                    raise ValueError(f"Invalid concentration for {ion}: {conc}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format for ion composition: {str(e)}")
        
        # Create output directory if it doesn't exist
        output_dir = Path(__file__).parent / "results"
        output_dir.mkdir(exist_ok=True)
        
        # Generate unique output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"ro_simulation_mcas_{timestamp}.ipynb"
        output_path = output_dir / output_filename
        
        # Select appropriate notebook template
        template_path = Path(__file__).parent / "notebooks" / "ro_simulation_mcas_template.ipynb"
        
        if not template_path.exists():
            raise FileNotFoundError(f"Notebook template not found: {template_path}")
        
        # Fix configuration structure - add feed_flow_m3h at root level if missing
        if "feed_flow_m3h" not in configuration:
            # Check if it's in recycle_info
            if "recycle_info" in configuration and "effective_feed_flow_m3h" in configuration["recycle_info"]:
                configuration["feed_flow_m3h"] = configuration["recycle_info"]["effective_feed_flow_m3h"]
                logger.info(f"Added feed_flow_m3h from recycle_info: {configuration['feed_flow_m3h']} m³/h")
            else:
                # Try to calculate from first stage if available
                if "stages" in configuration and len(configuration["stages"]) > 0:
                    first_stage = configuration["stages"][0]
                    if "feed_flow_m3h" in first_stage:
                        configuration["feed_flow_m3h"] = first_stage["feed_flow_m3h"]
                        logger.info(f"Added feed_flow_m3h from first stage: {configuration['feed_flow_m3h']} m³/h")
                    else:
                        # Default to 100 m³/h as fallback
                        configuration["feed_flow_m3h"] = 100.0
                        logger.warning("Could not find feed_flow_m3h, using default 100 m³/h")
                else:
                    configuration["feed_flow_m3h"] = 100.0
                    logger.warning("Could not find feed_flow_m3h, using default 100 m³/h")
        
        # Prepare parameters for notebook
        parameters = {
            "project_root": str(Path(__file__).parent),
            "configuration": configuration,
            "feed_salinity_ppm": feed_salinity_ppm,
            "feed_ion_composition": feed_ion_composition,  # Pass as string, notebook will parse
            "feed_temperature_c": feed_temperature_c,
            "membrane_type": membrane_type,
            "membrane_properties": membrane_properties,
            "optimize_pumps": optimize_pumps,
            "initialization_strategy": "sequential"
        }
        
        # Log the request
        logger.info(f"Starting notebook execution for {configuration.get('array_notation', 'unknown')} array")
        logger.info(f"Output notebook: {output_path}")
        
        # Execute notebook - this waits for completion (subprocess isolation prevents blocking)
        start_time = time.time()
        
        pm.execute_notebook(
            str(template_path),
            str(output_path),
            parameters=parameters,
            kernel_name="python3",
            start_timeout=60,  # Allow 60 seconds for kernel startup
            execution_timeout=1800  # Allow 30 minutes for execution
        )
        
        execution_time = time.time() - start_time
        logger.info(f"Notebook execution completed in {execution_time:.1f} seconds")
        
        # Immediately extract results from the completed notebook
        try:
            # Import result extraction functions
            import nbformat
            
            # Read the completed notebook
            with open(output_path, 'r', encoding='utf-8') as f:
                nb = nbformat.read(f, as_version=4)
            
            # Look for the results cell (tagged with "results")
            results_data = None
            for cell in nb.cells:
                if (cell.cell_type == 'code' and 
                    'tags' in cell.metadata and 
                    'results' in cell.metadata.tags and
                    cell.outputs):
                    
                    # Extract results from the output
                    for output in cell.outputs:
                        if output.get('output_type') == 'execute_result':
                            if 'data' in output and 'text/plain' in output['data']:
                                results_str = output['data']['text/plain']
                                # Parse the results safely
                                import ast
                                try:
                                    results_data = ast.literal_eval(results_str)
                                    break
                                except:
                                    try:
                                        results_data = json.loads(results_str)
                                        break
                                    except:
                                        logger.warning("Could not parse results from notebook")
                    
                    if results_data:
                        break
            
            if results_data:
                # Add execution metadata
                results_data["execution_info"] = {
                    "execution_time_seconds": execution_time,
                    "notebook_path": str(output_path),
                    "timestamp": datetime.now().isoformat()
                }
                
                return {
                    "status": "success",
                    "message": f"Simulation completed successfully in {execution_time:.1f} seconds",
                    "results": results_data,
                    "notebook_path": str(output_path)
                }
            else:
                return {
                    "status": "error",
                    "message": "Simulation completed but no results found in notebook",
                    "notebook_path": str(output_path),
                    "execution_time_seconds": execution_time
                }
                
        except Exception as e:
            logger.error(f"Error extracting results: {str(e)}")
            return {
                "status": "partial_success",
                "message": f"Simulation completed in {execution_time:.1f}s but failed to extract results: {str(e)}",
                "notebook_path": str(output_path),
                "execution_time_seconds": execution_time,
                "instructions": "Use get_simulation_results tool to manually extract results"
            }
        
    except ImportError as e:
        if "papermill" in str(e):
            logger.error("Papermill not available")
            return {
                "status": "error",
                "error": "Papermill not installed",
                "message": "Please install papermill to use notebook-based simulation"
            }
        else:
            logger.error(f"Import error: {str(e)}")
            return {
                "status": "error",
                "error": "Dependencies not installed",
                "message": f"Missing dependency: {str(e)}"
            }
    except Exception as e:
        logger.error(f"Error in simulate_ro_system: {str(e)}")
        return {
            "status": "error",
            "error": str(type(e).__name__),
            "message": str(e)
        }


# Removed check_simulation_status and get_simulation_results tools
# With the improved single-tool architecture, simulate_ro_system returns complete results
# These tools are no longer needed and add unnecessary complexity


# Main entry point
def main():
    """Run the MCP server."""
    logger.info("Starting RO Design MCP Server...")
    
    # Log available tools
    logger.info("Available tools:")
    logger.info("  - optimize_ro_configuration: Generate optimal RO vessel array configurations")
    logger.info("  - simulate_ro_system: Run WaterTAP simulation and return complete results")
    
    # Run the server
    mcp.run()


if __name__ == "__main__":
    main()