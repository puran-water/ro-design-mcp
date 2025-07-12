#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RO Design MCP Server

An STDIO MCP server for reverse osmosis system design optimization.
Provides tools for vessel array configuration and WaterTAP simulation.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from fastmcp import FastMCP

# Import our utilities
from utils.optimize_ro import optimize_vessel_array_configuration
from utils.helpers import (
    validate_recovery_target,
    validate_flow_rate,
    validate_salinity
)
from utils.constants import (
    DEFAULT_FLUX_TARGETS_LMH,
    DEFAULT_MIN_CONCENTRATE_FLOW_M3H,
    MEMBRANE_PROPERTIES
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
        flux_targets_lmh: Optional flux targets in LMH as JSON string.
                         Examples: "20" for single value, "[22, 18, 15]" for per-stage
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
    try:
        # Validate inputs
        validate_flow_rate(feed_flow_m3h, "feed_flow_m3h")
        validate_recovery_target(water_recovery_fraction)
        
        if membrane_type not in ["brackish", "seawater"]:
            raise ValueError(f"Invalid membrane_type: {membrane_type}")
        
        # Log the request
        logger.info(f"Optimizing RO configuration: {feed_flow_m3h} m³/h, "
                   f"{water_recovery_fraction*100:.0f}% recovery, {membrane_type}")
        
        # Parse flux targets if provided
        parsed_flux_targets = None
        if flux_targets_lmh is not None:
            try:
                # Try to parse as JSON
                parsed_value = json.loads(flux_targets_lmh)
                if isinstance(parsed_value, (int, float)):
                    parsed_flux_targets = float(parsed_value)
                elif isinstance(parsed_value, list):
                    parsed_flux_targets = [float(x) for x in parsed_value]
                else:
                    raise ValueError("flux_targets_lmh must be a number or array of numbers")
            except (json.JSONDecodeError, ValueError) as e:
                # Try as plain number
                try:
                    parsed_flux_targets = float(flux_targets_lmh)
                except ValueError:
                    raise ValueError(f"Invalid flux_targets_lmh format: {flux_targets_lmh}. "
                                   f"Use '20' for single value or '[22, 18, 15]' for per-stage")
        
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
            flux_tolerance=flux_tolerance
        )
        
        # Format the response
        response = {
            "status": "success",
            "configurations": []
        }
        
        for config in configurations:
            # Format configuration
            formatted_config = {
                "stage_count": config["n_stages"],
                "array_notation": config["array_notation"],
                "total_vessels": config["total_vessels"],
                "total_membrane_area_m2": config["total_membrane_area_m2"],
                "achieved_recovery": config["total_recovery"],
                "recovery_error": config["recovery_error"],
                "stages": []
            }
            
            # Add stage details
            for stage in config["stages"]:
                stage_info = {
                    "stage_number": stage["stage_number"],
                    "vessel_count": stage["n_vessels"],
                    "feed_flow_m3h": stage["feed_flow_m3h"],
                    "permeate_flow_m3h": stage["permeate_flow_m3h"],
                    "concentrate_flow_m3h": stage["concentrate_flow_m3h"],
                    "stage_recovery": stage["stage_recovery"],
                    "design_flux_lmh": stage["design_flux_lmh"],
                    "flux_ratio": stage["flux_ratio"],
                    "membrane_area_m2": stage["membrane_area_m2"],
                    # Add concentrate flow margin information
                    "concentrate_per_vessel_m3h": stage.get("concentrate_per_vessel_m3h", 
                                                           stage["concentrate_flow_m3h"] / stage["n_vessels"]),
                    "min_concentrate_required_m3h": stage.get("min_concentrate_required"),
                    "concentrate_margin_m3h": stage.get("concentrate_per_vessel_m3h", 
                                                       stage["concentrate_flow_m3h"] / stage["n_vessels"]) - 
                                            stage.get("min_concentrate_required", 0),
                    "concentrate_margin_percent": ((stage.get("concentrate_per_vessel_m3h", 
                                                            stage["concentrate_flow_m3h"] / stage["n_vessels"]) / 
                                                  stage.get("min_concentrate_required", 1) - 1) * 100) 
                                                if stage.get("min_concentrate_required", 0) > 0 else None
                }
                formatted_config["stages"].append(stage_info)
            
            # Add recycle information if applicable
            if config.get("recycle_ratio", 0) > 0:
                formatted_config["recycle_info"] = {
                    "uses_recycle": True,
                    "recycle_ratio": config["recycle_ratio"],
                    "recycle_flow_m3h": config["recycle_flow_m3h"],
                    "recycle_split_ratio": config["recycle_split_ratio"],
                    "effective_feed_flow_m3h": config["effective_feed_flow_m3h"],
                    "disposal_flow_m3h": config["disposal_flow_m3h"]
                }
            else:
                formatted_config["recycle_info"] = {
                    "uses_recycle": False
                }
            
            # Add recovery achievement status
            formatted_config["meets_target_recovery"] = config.get("meets_target_recovery", False)
            
            response["configurations"].append(formatted_config)
        
        # Add summary
        response["summary"] = {
            "feed_flow_m3h": feed_flow_m3h,
            "target_recovery": water_recovery_fraction,
            "membrane_type": membrane_type,
            "configurations_found": len(configurations)
        }
        
        # Check if any configuration met the target
        configs_meeting_target = [c for c in response["configurations"] if c["meets_target_recovery"]]
        if not configs_meeting_target:
            response["warning"] = (f"No configuration achieved the target recovery of {water_recovery_fraction:.1%}. "
                                 f"Best achieved: {response['configurations'][0]['achieved_recovery']:.1%}")
            response["recommendation"] = "Consider adjusting flux targets, allowing recycle, or accepting lower recovery."
        
        return response
        
    except Exception as e:
        logger.error(f"Error in optimize_ro_configuration: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to optimize RO configuration"
        }


@mcp.tool()
async def simulate_ro_system(
    configuration: Dict[str, Any],
    feed_salinity_ppm: float,
    feed_temperature_c: float = 25.0,
    membrane_type: str = "brackish",
    membrane_properties: Optional[Dict[str, float]] = None,
    optimize_pumps: bool = False
) -> Dict[str, Any]:
    """
    Run WaterTAP simulation for the specified RO configuration.
    
    This tool creates a WaterTAP model, runs the simulation, and returns
    performance metrics including LCOW, energy consumption, and detailed
    stage results.
    
    Args:
        configuration: Output from optimize_ro_configuration tool
        feed_salinity_ppm: Feed water salinity in ppm
        feed_temperature_c: Feed temperature in Celsius (default 25°C)
        membrane_type: Type of membrane ("brackish" or "seawater")
        membrane_properties: Optional custom membrane properties
        optimize_pumps: Whether to optimize pump pressures for minimum LCOW
    
    Returns:
        Dictionary containing:
        - performance: Overall system performance metrics
        - economics: LCOW and energy consumption
        - stage_results: Detailed results for each stage
        - mass_balance: System mass balance verification
    
    Note:
        This tool requires WaterTAP to be installed and will execute
        a parameterized Jupyter notebook for the simulation.
    """
    # TODO: Implement WaterTAP simulation
    # This will use papermill to run a parameterized notebook
    
    return {
        "status": "not_implemented",
        "message": "WaterTAP simulation tool is not yet implemented"
    }


# Main entry point
def main():
    """Run the MCP server."""
    logger.info("Starting RO Design MCP Server...")
    
    # Log available tools
    logger.info("Available tools:")
    logger.info("  - optimize_ro_configuration")
    logger.info("  - simulate_ro_system (not yet implemented)")
    
    # Run the server
    mcp.run()


if __name__ == "__main__":
    main()