"""
Response formatting utilities for the RO Design MCP Server.
"""

from typing import Dict, Any, List


def format_stage_info(stage: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format stage information for response.
    
    Args:
        stage: Stage configuration dictionary
        
    Returns:
        Formatted stage information
    """
    return {
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
        "concentrate_per_vessel_m3h": stage.get(
            "concentrate_per_vessel_m3h", 
            stage["concentrate_flow_m3h"] / stage["n_vessels"]
        ),
        "min_concentrate_required_m3h": stage.get("min_concentrate_required"),
        "concentrate_margin_m3h": stage.get(
            "concentrate_per_vessel_m3h", 
            stage["concentrate_flow_m3h"] / stage["n_vessels"]
        ) - stage.get("min_concentrate_required", 0),
        "concentrate_margin_percent": (
            (stage.get("concentrate_per_vessel_m3h", 
                      stage["concentrate_flow_m3h"] / stage["n_vessels"]) / 
             stage.get("min_concentrate_required", 1) - 1) * 100
        ) if stage.get("min_concentrate_required", 0) > 0 else None
    }


def format_recycle_info(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format recycle information for response.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Formatted recycle information
    """
    if config.get("recycle_ratio", 0) > 0:
        return {
            "uses_recycle": True,
            "recycle_ratio": config["recycle_ratio"],
            "recycle_flow_m3h": config["recycle_flow_m3h"],
            "recycle_split_ratio": config["recycle_split_ratio"],
            "effective_feed_flow_m3h": config["effective_feed_flow_m3h"],
            "disposal_flow_m3h": config["disposal_flow_m3h"]
        }
    else:
        return {
            "uses_recycle": False
        }


def format_recovery_achievement(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format recovery achievement status.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Recovery achievement information
    """
    recovery_error = config.get("recovery_error", 0)
    target_recovery = config.get("target_recovery", 0)
    achieved_recovery = config.get("total_recovery", 0)
    
    return {
        "met_target": recovery_error <= 0.02,  # Within 2% tolerance
        "target_recovery_percent": target_recovery * 100,
        "achieved_recovery_percent": achieved_recovery * 100,
        "recovery_error_percent": recovery_error * 100
    }


def format_configuration_response(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format a single configuration for response.
    
    IMPORTANT: This function now returns the complete raw configuration
    to ensure compatibility with simulate_ro_system.
    
    Args:
        config: Raw configuration from optimizer
        
    Returns:
        Complete configuration with additional formatted fields
    """
    # Start with the complete raw configuration to preserve all fields
    # This ensures simulate_ro_system gets everything it needs
    formatted = config.copy()
    
    # Add formatted display fields (these are for user display)
    formatted["stage_count"] = config["n_stages"]
    formatted["achieved_recovery"] = config["total_recovery"]
    
    # Add recycle information
    formatted["recycle_info"] = format_recycle_info(config)
    
    # Add recovery achievement status
    formatted["recovery_achievement"] = format_recovery_achievement(config)
    
    # Add flux summary
    formatted["flux_summary"] = {
        "min_flux_ratio": config.get("min_flux_ratio"),
        "max_flux_ratio": config.get("max_flux_ratio"),
        "average_flux_lmh": sum(s["design_flux_lmh"] for s in config["stages"]) / len(config["stages"])
    }
    
    return formatted


def format_optimization_response(
    configurations: List[Dict[str, Any]],
    feed_flow_m3h: float,
    target_recovery: float,
    membrane_type: str
) -> Dict[str, Any]:
    """
    Format the complete optimization response.
    
    Args:
        configurations: List of configurations from optimizer
        feed_flow_m3h: Feed flow rate
        target_recovery: Target recovery fraction
        membrane_type: Type of membrane
        
    Returns:
        Formatted response dictionary
    """
    response = {
        "status": "success",
        "configurations": [],
        "summary": {
            "feed_flow_m3h": feed_flow_m3h,
            "target_recovery_percent": target_recovery * 100,
            "membrane_type": membrane_type,
            "configurations_found": len(configurations)
        }
    }
    
    # Format each configuration
    for config in configurations:
        response["configurations"].append(format_configuration_response(config))
    
    # Add configuration diversity summary
    if configurations:
        stage_counts = [c["n_stages"] for c in configurations]
        uses_recycle = [c.get("recycle_ratio", 0) > 0 for c in configurations]
        
        response["summary"]["configuration_types"] = {
            "stage_counts": sorted(list(set(stage_counts))),
            "includes_recycle_options": any(uses_recycle),
            "includes_non_recycle_options": not all(uses_recycle)
        }
    
    return response


def format_error_response(error: Exception, request_params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format an error response.
    
    Args:
        error: The exception that occurred
        request_params: Original request parameters
        
    Returns:
        Formatted error response
    """
    return {
        "status": "error",
        "error": {
            "type": type(error).__name__,
            "message": str(error),
            "request_parameters": request_params
        },
        "configurations": []
    }


def format_simulation_response(sim_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format simulation results for MCP response.
    
    This ensures the simulation results are properly structured for
    the MCP client, similar to how optimize_ro_configuration formats
    its responses.
    
    Args:
        sim_results: Raw simulation results from run_ro_simulation
        
    Returns:
        Formatted response dictionary
    """
    # If already has proper status field, validate it
    if "status" in sim_results:
        if sim_results["status"] == "error":
            return sim_results  # Already formatted error response
        elif sim_results["status"] != "success":
            # Handle partial or other statuses
            return {
                "status": sim_results["status"],
                "message": sim_results.get("message", "Simulation completed with warnings"),
                "results": {
                    "performance": sim_results.get("performance", {}),
                    "economics": sim_results.get("economics", {}),
                    "stage_results": sim_results.get("stage_results", []),
                    "mass_balance": sim_results.get("mass_balance", {}),
                    "ion_analysis": sim_results.get("ion_tracking", {})
                }
            }
    
    # Format successful response
    response = {
        "status": "success",
        "message": "RO system simulation completed successfully",
        "results": {
            "performance": sim_results.get("performance", {}),
            "economics": sim_results.get("economics", {}),
            "stage_results": sim_results.get("stage_results", []),
            "mass_balance": sim_results.get("mass_balance", {}),
            "ion_analysis": sim_results.get("ion_tracking", {})
        }
    }
    
    # Add optional fields if present
    if "solve_info" in sim_results:
        response["solve_info"] = sim_results["solve_info"]
    
    if "trace_ion_info" in sim_results:
        response["results"]["trace_ion_info"] = sim_results["trace_ion_info"]
    
    # Add summary metrics for easy access
    if sim_results.get("performance"):
        perf = sim_results["performance"]
        response["summary"] = {
            "system_recovery": perf.get("system_recovery", 0),
            "permeate_tds_mg_l": perf.get("total_permeate_tds_mg_l", 0),
            "specific_energy_kwh_m3": perf.get("specific_energy_kWh_m3", 0),
            "total_power_kw": sim_results.get("economics", {}).get("total_power_kw", 0)
        }
    
    return response