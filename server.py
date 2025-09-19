#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RO Design MCP Server

An STDIO MCP server for reverse osmosis system design optimization.
Provides tools for vessel array configuration and WaterTAP simulation.

Note: The simulation tool runs WaterTAP in a child Python process to
isolate stdout/stderr from the MCP stdio transport and avoid protocol
corruption or deadlocks from solver/native output.
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

# Import direct simulation and artifact management
from utils.simulate_ro import run_ro_simulation
from utils.artifacts import (
    deterministic_run_id,
    check_existing_results,
    write_artifacts,
    capture_context,
    artifacts_root
)
from utils.schemas import (
    ROSimulationInput,
    ROConfiguration,
    FeedComposition,
    SimulationOptions,
    MembraneProperties
)

# Configure logging for MCP - CRITICAL for protocol integrity
from utils.logging_config import configure_mcp_logging, get_configured_logger
configure_mcp_logging()
logger = get_configured_logger(__name__)

# Create FastMCP instance
mcp = FastMCP("RO Design Server")

# Async-friendly subprocess runner for simulation isolation
import anyio
import subprocess

PROJECT_ROOT = Path(__file__).parent


def _run_simulation_in_subprocess(sim_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the WaterTAP simulation in a child Python process to isolate stdout.

    This prevents any native or solver-level output from corrupting the MCP STDIO
    channel in the parent process.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "utils.simulate_ro_cli"],
            input=json.dumps(sim_input),
            text=True,
            capture_output=True,
            cwd=str(PROJECT_ROOT),
            check=False,
        )

        if proc.returncode != 0:
            logger.error(f"Child simulation process failed (code {proc.returncode}). Stderr: {proc.stderr[:2000]}")
            try:
                return json.loads(proc.stdout) if proc.stdout else {
                    "status": "error",
                    "message": f"Child process failed with code {proc.returncode}",
                    "stderr": proc.stderr,
                }
            except json.JSONDecodeError:
                return {
                    "status": "error",
                    "message": f"Child process failed and returned non-JSON stdout",
                    "stderr": proc.stderr,
                    "raw_stdout": proc.stdout,
                }

        # Parse JSON from child's stdout
        try:
            return json.loads(proc.stdout) if proc.stdout else {
                "status": "error",
                "message": "No output from child process",
            }
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse child JSON: {e}. Raw: {proc.stdout[:500]}")
            return {
                "status": "error",
                "message": f"Invalid JSON from child process: {e}",
                "raw_stdout": proc.stdout,
            }
    except Exception as e:
        logger.error(f"Exception launching child process: {e}")
        return {"status": "error", "message": f"Failed to launch child process: {e}"}


@mcp.tool()
async def optimize_ro_configuration(
    feed_flow_m3h: float,
    water_recovery_fraction: float,
    membrane_model: str,
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
        membrane_model: Specific membrane model (e.g., 'BW30_PRO_400', 'SW30HRLE_440')
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
            membrane_model="BW30_PRO_400"
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
        "membrane_model": membrane_model,
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
            membrane_model=membrane_model,
            allow_recycle=allow_recycle,
            max_recycle_ratio=max_recycle_ratio,
            flux_targets_lmh=flux_targets_lmh,
            flux_tolerance=flux_tolerance
        )
        
        # Log the request
        logger.info(f"Optimizing RO configuration: {feed_flow_m3h} m³/h, "
                   f"{water_recovery_fraction*100:.0f}% recovery, {membrane_model}")
        
        # Note: Feed salinity is NOT needed for configuration optimization
        # We use a placeholder value for internal calculations
        placeholder_salinity = 5000 if not membrane_model.startswith('SW') else 35000
        
        # Call the optimization function - now returns all viable configurations
        configurations = optimize_vessel_array_configuration(
            feed_flow_m3h=feed_flow_m3h,
            target_recovery=water_recovery_fraction,
            feed_salinity_ppm=placeholder_salinity,
            membrane_model=membrane_model,
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
            membrane_model=membrane_model
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


# Removed simulate_ro_system v1 - clients must use simulate_ro_system_v2
# v1 had issues with the new membrane catalog system and ion-specific B values


@mcp.tool()
async def simulate_ro_system_v2(
    configuration: Dict[str, Any],
    feed_salinity_ppm: float,
    feed_ion_composition: str,
    membrane_model: str,
    feed_temperature_c: float = 25.0,
    economic_params: Optional[Dict[str, Any]] = None,
    chemical_dosing: Optional[Dict[str, Any]] = None,
    optimization_mode: bool = False,
    ctx: Context = None
) -> Dict[str, Any]:
    """
    Run enhanced WaterTAP simulation with detailed economic modeling (v2).
    
    This version includes comprehensive costing with WaterTAPCostingDetailed,
    chemical consumption tracking, ancillary equipment, and optimization support.
    
    Args:
        configuration: Output from optimize_ro_configuration tool
        feed_salinity_ppm: Feed water salinity in ppm
        feed_ion_composition: JSON string of ion concentrations in mg/L
        feed_temperature_c: Feed temperature in Celsius (default 25°C)
        membrane_model: Specific membrane model (e.g., 'BW30_PRO_400', 'SW30HRLE_440')
        economic_params: Economic parameters (uses WaterTAP defaults if None)
            - wacc: Weighted average cost of capital (default 0.093)
            - plant_lifetime_years: Plant lifetime (default 30)
            - utilization_factor: Plant uptime fraction (default 0.9)
            - electricity_cost_usd_kwh: Electricity cost (default 0.07)
            - membrane_replacement_factor: Annual replacement (default 0.2)
            - And many more... call get_ro_defaults for full list
        chemical_dosing: Chemical dosing parameters (uses defaults if None)
            - antiscalant_dose_mg_L: Antiscalant dose (default 5.0)
            - cip_frequency_per_year: CIP frequency (default 4)
            - cip_dose_kg_per_m2: CIP chemical dose (default 0.5)
            - And more... call get_ro_defaults for full list
        optimization_mode: If True, returns model handle for plant-wide optimization
    
    Returns:
        Dictionary containing:
        - status: "success" or "error"
        - For normal mode: Full simulation results with detailed economics
        - For optimization mode: model_handle and metadata for orchestration
    
    Example:
        ```python
        # Basic call with defaults
        result = await simulate_ro_system_v2(
            configuration=config,
            feed_salinity_ppm=5000,
            feed_ion_composition='{"Na+": 1200, "Cl-": 2100, ...}'
        )
        
        # Custom economics
        result = await simulate_ro_system_v2(
            configuration=config,
            feed_salinity_ppm=35000,
            feed_ion_composition=seawater_ions,
            membrane_model="SW30HRLE_440",
            economic_params={"wacc": 0.06, "electricity_cost_usd_kwh": 0.10}
        )
        
        # Optimization mode
        result = await simulate_ro_system_v2(
            configuration=config,
            feed_salinity_ppm=5000,
            feed_ion_composition=ions,
            optimization_mode=True
        )
        ```
    """
    try:
        # Import economic defaults
        from utils.economic_defaults import (
            apply_economic_defaults, 
            apply_dosing_defaults,
            validate_economic_params,
            validate_dosing_params
        )
        
        # Validate inputs first
        if not isinstance(configuration, dict):
            raise ValueError("configuration must be a dictionary from optimize_ro_configuration")
        
        if "stages" not in configuration:
            raise ValueError("configuration must contain 'stages' key")
        
        validate_salinity(feed_salinity_ppm, "feed_salinity_ppm")
        
        if not 0 < feed_temperature_c < 100:
            raise ValueError(f"Temperature {feed_temperature_c}°C is outside reasonable range")
        
        # Validate membrane model exists (could be checked against catalog)
        # For now, just ensure it's provided
        if not membrane_model:
            raise ValueError("membrane_model is required")
        
        # Parse ion composition
        try:
            parsed_ion_composition = json.loads(feed_ion_composition)
            if not isinstance(parsed_ion_composition, dict):
                raise ValueError("Ion composition must be a JSON object")
            for ion, conc in parsed_ion_composition.items():
                if not isinstance(conc, (int, float)) or conc < 0:
                    raise ValueError(f"Invalid concentration for {ion}: {conc}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format for ion composition: {str(e)}")
        
        # Apply defaults and validate
        economic_params = apply_economic_defaults(economic_params, 'brackish' if not membrane_model.startswith('SW') else 'seawater')
        config_feed_flow = configuration.get("feed_flow_m3h")
        if config_feed_flow is not None and "feed_flow_m3h" not in economic_params:
            economic_params["feed_flow_m3h"] = config_feed_flow
        chemical_dosing = apply_dosing_defaults(chemical_dosing)

        validate_economic_params(economic_params)
        validate_dosing_params(chemical_dosing)
        
        # Create input payload for simulation
        input_payload = {
            "configuration": configuration,
            "feed_salinity_ppm": feed_salinity_ppm,
            "feed_ion_composition": parsed_ion_composition,
            "feed_temperature_c": feed_temperature_c,
            "membrane_model": membrane_model,
            "economic_params": economic_params,
            "chemical_dosing": chemical_dosing,
            "optimization_mode": optimization_mode,
            "api_version": "v2"
        }
        
        # Generate deterministic run ID
        run_id = deterministic_run_id(
            tool_name="simulate_ro_system_v2",
            input_payload=input_payload
        )
        
        logger.info(f"Generated run_id: {run_id} for v2 simulation")
        
        # Check for existing results (idempotency)
        if not optimization_mode:
            existing_results = check_existing_results(run_id)
            if existing_results:
                logger.info(f"Found cached results for run_id: {run_id}")
                artifact_dir = artifacts_root() / run_id
                return {
                    "status": "success",
                    "message": "Using cached results",
                    "results": existing_results,
                    "artifact_dir": str(artifact_dir),
                    "run_id": run_id,
                    "cached": True,
                    "api_version": "v2"
                }
        
        # Log the request
        logger.info(f"Starting v2 simulation for {configuration.get('array_notation', 'unknown')} array")
        logger.info(f"Economic mode: {'optimization' if optimization_mode else 'simulation'}")
        
        # Start timing
        start_time = time.time()
        
        # Run simulation in isolated child process
        logger.info("Running v2 simulation in child process...")
        sim_input = {
            **input_payload,
            "initialization_strategy": "sequential",
            # use_nacl_equivalent removed - defaults to False for direct MCAS modeling
        }

        simulation_results = await anyio.to_thread.run_sync(_run_simulation_in_subprocess, sim_input)
        
        execution_time = time.time() - start_time
        logger.info(f"V2 simulation completed in {execution_time:.1f} seconds")
        
        # Check if simulation was successful
        if simulation_results["status"] != "success":
            logger.error(f"V2 simulation failed: {simulation_results.get('message', 'Unknown error')}")
            return {
                "status": "error",
                "message": simulation_results.get("message", "Simulation failed"),
                "error_details": simulation_results,
                "execution_time_seconds": execution_time,
                "run_id": run_id,
                "api_version": "v2"
            }
        
        if optimization_mode:
            # Optimization mode not supported via server due to subprocess isolation
            logger.warning("Optimization mode requested but not supported via MCP server")
            logger.warning("Model handles cannot persist across subprocess boundaries")
            logger.warning("Use direct Python API (utils.simulate_ro_v2) for optimization mode")
            return {
                "status": "error",
                "error": "OptimizationModeUnsupported",
                "message": "Optimization mode is not supported via the MCP stdio server. Use utils.simulate_ro_v2 directly.",
                "execution_time_seconds": execution_time,
                "run_id": run_id,
                "api_version": "v2"
            }
        else:
            # Normal simulation mode - write artifacts
            context = capture_context(
                tool_name="simulate_ro_system_v2",
                run_id=run_id
            )
            
            # Write artifacts
            logger.info(f"Writing artifacts to {run_id}/")
            artifact_dir = write_artifacts(
                run_id=run_id,
                tool_name="simulate_ro_system_v2",
                input_data=input_payload,
                results_data=simulation_results,
                context=context,
                warnings=simulation_results.get("warnings")
            )
            
            # Add execution metadata
            simulation_results["execution_info"] = {
                "execution_time_seconds": execution_time,
                "timestamp": datetime.now().isoformat(),
                "run_id": run_id,
                "api_version": "v2"
            }
            
            logger.info(f"V2 simulation completed successfully in {execution_time:.1f} seconds")
            
            return {
                "status": "success",
                "message": f"V2 simulation completed in {execution_time:.1f} seconds",
                "results": simulation_results,
                "artifact_dir": str(artifact_dir),
                "run_id": run_id,
                "cached": False,
                "api_version": "v2"
            }
        
    except ImportError as e:
        logger.error(f"Import error: {str(e)}")
        return {
            "status": "error",
            "error": "Dependencies not installed",
            "message": f"Missing dependency: {str(e)}",
            "api_version": "v2"
        }
    except Exception as e:
        logger.error(f"Error in simulate_ro_system_v2: {str(e)}")
        return {
            "status": "error",
            "error": str(type(e).__name__),
            "message": str(e),
            "api_version": "v2"
        }


@mcp.tool()
async def get_ro_defaults() -> Dict[str, Any]:
    """
    Get default economic and chemical dosing parameters for RO simulation.
    
    Returns a dictionary with two sections:
    - economic_params: All economic parameters with WaterTAP defaults
    - chemical_dosing: All chemical dosing parameters with typical values
    
    This tool is useful for understanding available parameters and their
    default values before calling simulate_ro_system_v2.
    
    Example:
        ```python
        defaults = await get_ro_defaults()
        
        # View economic defaults
        print(defaults["economic_params"]["wacc"])  # 0.093
        print(defaults["economic_params"]["plant_lifetime_years"])  # 30
        
        # View dosing defaults  
        print(defaults["chemical_dosing"]["antiscalant_dose_mg_L"])  # 5.0
        print(defaults["chemical_dosing"]["cip_frequency_per_year"])  # 4
        ```
    """
    try:
        from utils.economic_defaults import (
            get_default_economic_params,
            get_default_chemical_dosing
        )
        
        return {
            "status": "success",
            "economic_params": get_default_economic_params(),
            "chemical_dosing": get_default_chemical_dosing(),
            "description": {
                "economic_params": "WaterTAP-aligned economic parameters for costing",
                "chemical_dosing": "Typical chemical dosing rates for RO systems"
            }
        }
    except Exception as e:
        logger.error(f"Error in get_ro_defaults: {str(e)}")
        return {
            "status": "error",
            "error": str(type(e).__name__),
            "message": str(e)
        }


# Main entry point
def main():
    """Run the MCP server."""
    logger.info("Starting RO Design MCP Server...")
    
    # Log available tools
    logger.info("Available tools:")
    logger.info("  - optimize_ro_configuration: Generate optimal RO vessel array configurations")
    logger.info("  - simulate_ro_system_v2: Run WaterTAP simulation with detailed economics")
    logger.info("  - get_ro_defaults: Get default economic and chemical parameters")
    
    # Run the server
    mcp.run()


if __name__ == "__main__":
    main()
