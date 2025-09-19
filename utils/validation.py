"""
Input validation utilities for the RO Design MCP Server.
"""

import json
from typing import Optional, Union, List, Tuple
from .helpers import validate_recovery_target, validate_flow_rate, validate_salinity


def validate_membrane_type(membrane_type: str) -> None:
    """
    Validate membrane type.
    
    Args:
        membrane_type: Type of membrane
        
    Raises:
        ValueError: If membrane type is invalid
    """
    valid_types = ["brackish", "seawater"]
    if membrane_type not in valid_types:
        raise ValueError(
            f"Invalid membrane_type: {membrane_type}. "
            f"Must be one of {valid_types}"
        )


def validate_recycle_parameters(
    allow_recycle: bool, 
    max_recycle_ratio: float
) -> None:
    """
    Validate recycle parameters.
    
    Args:
        allow_recycle: Whether recycle is allowed
        max_recycle_ratio: Maximum recycle ratio
        
    Raises:
        ValueError: If parameters are invalid
    """
    if not isinstance(allow_recycle, bool):
        raise ValueError(f"allow_recycle must be boolean, got {type(allow_recycle)}")
    
    if not isinstance(max_recycle_ratio, (int, float)):
        raise ValueError(f"max_recycle_ratio must be a number, got {type(max_recycle_ratio)}")
    
    if not 0 <= max_recycle_ratio <= 1:
        raise ValueError(f"max_recycle_ratio must be between 0 and 1, got {max_recycle_ratio}")


def parse_flux_targets(
    flux_targets_lmh: Optional[str]
) -> Optional[Union[float, List[float]]]:
    """
    Parse flux targets from string input.
    
    Args:
        flux_targets_lmh: Flux targets as string (e.g., "20" or "[22, 18, 15]")
        
    Returns:
        Parsed flux targets as float or list of floats, or None
        
    Raises:
        ValueError: If format is invalid
    """
    if flux_targets_lmh is None:
        return None
    
    try:
        # First try as plain number (most common case)
        return float(flux_targets_lmh)
    except ValueError:
        try:
            # Try to parse as JSON for array format
            parsed_value = json.loads(flux_targets_lmh)
            if isinstance(parsed_value, (int, float)):
                return float(parsed_value)
            elif isinstance(parsed_value, list):
                if not parsed_value:
                    raise ValueError("Flux targets array cannot be empty")
                result = [float(x) for x in parsed_value]
                if not all(x > 0 for x in result):
                    raise ValueError("All flux targets must be positive")
                return result
            else:
                raise ValueError("flux_targets_lmh must be a number or array of numbers")
        except (json.JSONDecodeError, TypeError) as e:
            raise ValueError(
                f"Invalid flux_targets_lmh format: '{flux_targets_lmh}'. "
                f"Use '20' for single value or '[22, 18, 15]' for per-stage arrays"
            )


def validate_flux_tolerance(flux_tolerance: Optional[float]) -> None:
    """
    Validate flux tolerance parameter.
    
    Args:
        flux_tolerance: Flux tolerance as fraction
        
    Raises:
        ValueError: If tolerance is invalid
    """
    if flux_tolerance is None:
        return
    
    if not isinstance(flux_tolerance, (int, float)):
        raise ValueError(f"flux_tolerance must be a number, got {type(flux_tolerance)}")
    
    if not 0 <= flux_tolerance <= 1:
        raise ValueError(f"flux_tolerance must be between 0 and 1, got {flux_tolerance}")


def validate_optimize_ro_inputs(
    feed_flow_m3h: float,
    water_recovery_fraction: float,
    membrane_model: str,
    allow_recycle: bool = True,
    max_recycle_ratio: float = 0.9,
    flux_targets_lmh: Optional[str] = None,
    flux_tolerance: Optional[float] = None
) -> Tuple[Optional[Union[float, List[float]]], Optional[float]]:
    """
    Validate all inputs for optimize_ro_configuration.

    Args:
        All parameters from optimize_ro_configuration

    Returns:
        Tuple of (parsed_flux_targets, flux_tolerance)

    Raises:
        ValueError: If any input is invalid
    """
    # Validate basic parameters
    validate_flow_rate(feed_flow_m3h, "feed_flow_m3h")
    validate_recovery_target(water_recovery_fraction)
    # Skip membrane validation - will be checked against catalog elsewhere
    if not membrane_model:
        raise ValueError("membrane_model is required")
    validate_recycle_parameters(allow_recycle, max_recycle_ratio)

    # Validate and parse flux parameters
    validate_flux_tolerance(flux_tolerance)
    parsed_flux_targets = parse_flux_targets(flux_targets_lmh)

    return parsed_flux_targets, flux_tolerance