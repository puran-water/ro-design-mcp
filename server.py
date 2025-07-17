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
from utils.validation import (
    validate_optimize_ro_inputs,
    parse_flux_targets
)
from utils.response_formatter import (
    format_optimization_response,
    format_error_response
)
from utils.helpers import validate_salinity

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
    optimize_pumps: bool = True
) -> Dict[str, Any]:
    """
    Run WaterTAP simulation for the specified RO configuration using MCAS property package.
    
    This tool creates a WaterTAP model with detailed ion modeling, runs the simulation,
    and returns performance metrics including LCOW, energy consumption, detailed
    stage results, ion speciation, and scaling prediction.
    
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
        - performance: Overall system performance metrics
        - economics: LCOW and energy consumption
        - stage_results: Detailed results for each stage
        - mass_balance: System mass balance verification
        - ion_analysis: Ion rejection and speciation (if ion composition provided)
    
    Note:
        This tool requires WaterTAP to be installed and will execute
        a parameterized Jupyter notebook for the simulation.
    
    Example:
        ```python
        # MCAS simulation with ion composition (required)
        result = await simulate_ro_system(
            configuration=config_from_optimization,
            feed_salinity_ppm=5000,
            feed_temperature_c=25.0,
            feed_ion_composition='{"Na+": 1200, "Ca2+": 120, "Mg2+": 60, "Cl-": 2100, "SO4-2": 200, "HCO3-": 150}'
        )
        ```
    """
    try:
        # Import simulation module
        from utils.simulate_ro import run_ro_simulation, calculate_lcow, estimate_capital_cost
        
        # Validate inputs
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
        
        # Log the request
        logger.info(f"Running WaterTAP MCAS simulation for {configuration.get('array_notation', 'unknown')} array")
        
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
        
        # Run simulation
        sim_results = run_ro_simulation(
            configuration=configuration,
            feed_salinity_ppm=feed_salinity_ppm,
            feed_ion_composition=parsed_ion_composition,
            feed_temperature_c=feed_temperature_c,
            membrane_type=membrane_type,
            membrane_properties=membrane_properties,
            optimize_pumps=optimize_pumps
        )
        
        # If simulation was successful, add economic analysis
        if sim_results.get("status") == "success":
            # Get key metrics
            total_power_kw = sim_results["economics"].get("total_power_kw", 0)
            specific_energy = sim_results["economics"].get("specific_energy_kwh_m3", 0)
            total_recovery = sim_results["performance"].get("total_recovery", 0)
            
            # Estimate costs
            total_membrane_area = configuration.get("total_membrane_area_m2", 0)
            
            # Capital cost estimation (uses config values)
            capital_cost = estimate_capital_cost(
                total_membrane_area_m2=total_membrane_area,
                total_power_kw=total_power_kw * 1.2  # 20% margin
            )
            
            # Operating cost estimation (simplified)
            from utils.config import get_config
            
            feed_flow_m3h = configuration.get("feed_flow_m3h", 100)
            plant_availability = get_config('operating.plant_availability', 0.9)
            annual_production = feed_flow_m3h * total_recovery * 8760 * plant_availability
            
            electricity_cost_kwh = get_config('energy.electricity_cost_usd_kwh', 0.07)
            annual_energy_cost = annual_production * specific_energy * electricity_cost_kwh
            
            # Membrane replacement
            membrane_lifetime = get_config('operating.membrane_lifetime_years', 7)
            membrane_cost_m2 = get_config('capital.membrane_cost_usd_m2', 30.0)
            annual_membrane_cost = (total_membrane_area * membrane_cost_m2) / membrane_lifetime
            
            # Other O&M
            maintenance_fraction = get_config('operating.maintenance_fraction', 0.02)
            other_om_cost = capital_cost * maintenance_fraction
            
            total_annual_opex = annual_energy_cost + annual_membrane_cost + other_om_cost
            
            # Calculate LCOW
            discount_rate = get_config('financial.discount_rate', 0.08)
            plant_lifetime = get_config('financial.plant_lifetime_years', 20)
            
            lcow = calculate_lcow(
                capital_cost=capital_cost,
                annual_opex=total_annual_opex,
                annual_production_m3=annual_production,
                discount_rate=discount_rate,
                plant_lifetime_years=plant_lifetime
            )
            
            # Add to results
            sim_results["economics"]["capital_cost_usd"] = capital_cost
            sim_results["economics"]["annual_opex_usd"] = total_annual_opex
            sim_results["economics"]["lcow_usd_m3"] = lcow
            sim_results["economics"]["annual_production_m3"] = annual_production
        
        return sim_results
        
    except ImportError as e:
        logger.error(f"WaterTAP dependencies not available: {str(e)}")
        return {
            "status": "error",
            "error": "WaterTAP dependencies not installed",
            "message": "Please install WaterTAP and its dependencies to use this tool"
        }
    except Exception as e:
        logger.error(f"Error in simulate_ro_system: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to run RO system simulation"
        }


# Main entry point
def main():
    """Run the MCP server."""
    logger.info("Starting RO Design MCP Server...")
    
    # Log available tools
    logger.info("Available tools:")
    logger.info("  - optimize_ro_configuration: Generate optimal RO vessel array configurations")
    logger.info("  - simulate_ro_system: Run WaterTAP simulation for detailed performance analysis")
    
    # Run the server
    mcp.run()


if __name__ == "__main__":
    main()