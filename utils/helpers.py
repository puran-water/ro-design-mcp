# -*- coding: utf-8 -*-
"""
Helper functions for RO design calculations.

Based on WaterTAP best practices where pump pressures are optimization
outputs rather than fixed inputs.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Union
from .constants import *


def calculate_vessel_area(element_area_m2: float = STANDARD_ELEMENT_AREA_M2,
                         elements_per_vessel: int = ELEMENTS_PER_VESSEL) -> float:
    """Calculate total membrane area per vessel."""
    return element_area_m2 * elements_per_vessel


def estimate_osmotic_pressure_bar(salinity_ppm: float) -> float:
    """
    Estimate osmotic pressure from salinity.
    
    Simple approximation: π ≈ 0.75 bar per 1000 ppm
    This is used for initialization, not final design.
    """
    return salinity_ppm / 1000 * 0.75


def calculate_brine_osmotic_pressure(feed_salinity_ppm: float,
                                   water_recovery: float,
                                   salt_passage: float = 0.01) -> float:
    """
    Calculate brine osmotic pressure for given recovery.
    
    This mimics WaterTAP's calculate_operating_pressure approach
    by estimating the concentrated brine properties.
    
    Parameters:
    -----------
    feed_salinity_ppm : float
        Feed water salinity in ppm
    water_recovery : float
        Target water recovery fraction
    salt_passage : float
        Fraction of salt that passes through membrane (default 1%)
        
    Returns:
    --------
    float : Estimated brine osmotic pressure in bar
    """
    # Calculate brine concentration factor
    # Mass balance: Feed_salt * (1 - salt_passage) = Brine_salt
    # Brine_flow = Feed_flow * (1 - water_recovery)
    concentration_factor = (1 - salt_passage) / (1 - water_recovery)
    brine_salinity_ppm = feed_salinity_ppm * concentration_factor
    
    return estimate_osmotic_pressure_bar(brine_salinity_ppm)


def estimate_initial_pump_pressure(feed_salinity_ppm: float,
                                 water_recovery: float,
                                 over_pressure: float = 0.3,
                                 membrane_type: str = 'brackish') -> float:
    """
    Estimate initial pump pressure for WaterTAP model initialization.
    
    This follows WaterTAP's calculate_operating_pressure approach:
    - Calculate brine osmotic pressure at target recovery
    - Add over-pressure factor for driving force
    
    Note: This is an initialization estimate. WaterTAP will optimize
    the actual pressure during solving.
    
    Parameters:
    -----------
    feed_salinity_ppm : float
        Feed water salinity
    water_recovery : float
        Target recovery fraction
    over_pressure : float
        Fraction above osmotic pressure (default 30%)
    membrane_type : str
        Membrane type for bounds checking
        
    Returns:
    --------
    float : Estimated pump outlet pressure in Pa
    """
    # Calculate brine osmotic pressure
    brine_osmotic_bar = calculate_brine_osmotic_pressure(
        feed_salinity_ppm, water_recovery
    )
    
    # Add over-pressure factor
    required_pressure_bar = brine_osmotic_bar * (1 + over_pressure)
    required_pressure_pa = required_pressure_bar * 1e5
    
    # Apply membrane-specific limits
    max_pressure = MEMBRANE_PROPERTIES[membrane_type]['max_pressure']
    
    return min(required_pressure_pa, max_pressure)


def get_pump_pressure_bounds(membrane_type: str = 'brackish',
                           stage: int = 1) -> Tuple[float, float]:
    """
    Get recommended pressure bounds for pump optimization.
    
    Based on WaterTAP examples where pumps have:
    - Lower bound: typically 10 bar (10e5 Pa)
    - Upper bound: membrane-specific maximum
    
    Parameters:
    -----------
    membrane_type : str
        Type of membrane
    stage : int
        Stage number (later stages may have different bounds)
        
    Returns:
    --------
    Tuple[float, float] : (lower_bound_pa, upper_bound_pa)
    """
    # Standard lower bound from WaterTAP examples
    lower_bound = 10e5  # 10 bar
    
    # Upper bound based on membrane type
    if membrane_type == 'brackish':
        # Brackish water typical bounds
        if stage == 1:
            upper_bound = 65e5  # 65 bar for first stages
        else:
            upper_bound = 85e5  # 85 bar for last stage
    else:
        # Seawater bounds
        upper_bound = MEMBRANE_PROPERTIES[membrane_type]['max_pressure']
    
    return lower_bound, upper_bound


def estimate_minimum_water_flux(membrane_type: str = 'brackish') -> float:
    """
    Estimate minimum water flux constraint for optimization.
    
    From WaterTAP examples: typically 1.0 kg/m²/hr = 1/3600 kg/m²/s
    
    This constraint ensures pumps provide sufficient pressure
    to achieve meaningful permeate production.
    """
    # Standard minimum flux from WaterTAP examples
    return 1.0 / 3600.0  # kg/m²/s


def calculate_pressure_drop(flow_rate_m3h: float,
                          stage: int,
                          membrane_type: str = 'brackish') -> float:
    """
    Estimate pressure drop through RO stage.
    
    Uses default values from membrane properties.
    
    Returns:
    --------
    float : Pressure drop in Pa (positive value)
    """
    pressure_drop_key = f'pressure_drop_stage{stage}'
    default_drops = MEMBRANE_PROPERTIES[membrane_type]
    
    if pressure_drop_key in default_drops:
        return default_drops[pressure_drop_key]
    else:
        # Default 1 bar drop
        return 1e5


def format_array_notation(vessel_counts: List[int]) -> str:
    """
    Format vessel counts as array notation.
    
    Example: [10, 5, 3] -> "10:5:3"
    """
    return ':'.join(str(n) for n in vessel_counts)


def calculate_effective_salinity(fresh_feed_flow: float,
                               fresh_feed_salinity: float,
                               recycle_flow: float,
                               brine_salinity: float) -> float:
    """
    Calculate effective feed salinity with recycle.
    
    Parameters:
    -----------
    fresh_feed_flow : float
        Fresh feed flow rate
    fresh_feed_salinity : float
        Fresh feed salinity
    recycle_flow : float
        Recycle flow rate
    brine_salinity : float
        Estimated brine salinity
        
    Returns:
    --------
    float : Effective feed salinity
    """
    total_flow = fresh_feed_flow + recycle_flow
    if total_flow == 0:
        return fresh_feed_salinity
    
    return (fresh_feed_flow * fresh_feed_salinity + 
            recycle_flow * brine_salinity) / total_flow


def validate_recovery_target(recovery: float) -> None:
    """Validate recovery is within reasonable bounds."""
    if not 0.1 <= recovery <= 0.99:
        raise ValueError(f"Recovery {recovery:.1%} is outside reasonable bounds (10-99%)")


def validate_flow_rate(flow_rate: float, param_name: str = "flow_rate") -> None:
    """Validate flow rate is positive."""
    if flow_rate <= 0:
        raise ValueError(f"{param_name} must be positive, got {flow_rate}")


def validate_salinity(salinity_ppm: float, param_name: str = "salinity") -> None:
    """Validate salinity is within reasonable bounds."""
    if not 100 <= salinity_ppm <= 100000:
        raise ValueError(f"{param_name} {salinity_ppm} ppm is outside reasonable bounds (100-100,000 ppm)")


def validate_flux_parameters(flux_targets: Optional[Union[float, List[float]]] = None,
                           flux_tolerance: Optional[float] = None,
                           max_stages: int = MAX_STAGES) -> Tuple[List[float], float]:
    """
    Validate and normalize flux parameters.
    
    Parameters:
    -----------
    flux_targets : Optional[Union[float, List[float]]]
        Single flux target for all stages or list of targets per stage
    flux_tolerance : Optional[float]
        Fractional tolerance for flux envelope (e.g., 0.1 for ±10%)
    max_stages : int
        Maximum number of stages
        
    Returns:
    --------
    Tuple[List[float], float] : (normalized_flux_targets, flux_tolerance)
    """
    # Handle flux tolerance
    if flux_tolerance is None:
        flux_tolerance = DEFAULT_FLUX_TOLERANCE
    elif flux_tolerance < 0 or flux_tolerance > 1:
        raise ValueError(f"Flux tolerance must be between 0 and 1, got {flux_tolerance}")
    
    # Handle flux targets
    if flux_targets is None:
        # Use defaults
        normalized_targets = DEFAULT_FLUX_TARGETS_LMH.copy()
    elif isinstance(flux_targets, (int, float)):
        # Single value - apply to all stages
        if flux_targets <= 0:
            raise ValueError(f"Flux target must be positive, got {flux_targets}")
        normalized_targets = [float(flux_targets)] * max_stages
    elif isinstance(flux_targets, list):
        # List of values
        if not all(isinstance(x, (int, float)) and x > 0 for x in flux_targets):
            raise ValueError("All flux targets must be positive numbers")
        
        if len(flux_targets) == 0:
            raise ValueError("Flux targets list cannot be empty")
        elif len(flux_targets) < max_stages:
            # Extend with last value
            normalized_targets = list(flux_targets) + [flux_targets[-1]] * (max_stages - len(flux_targets))
        else:
            # Use first max_stages values
            normalized_targets = flux_targets[:max_stages]
    else:
        raise TypeError(f"flux_targets must be float or list, got {type(flux_targets)}")
    
    return normalized_targets, flux_tolerance


def check_mass_balance(feed_flow: float,
                      permeate_flow: float,
                      concentrate_flow: float,
                      tolerance: float = 0.01) -> Tuple[bool, float]:
    """
    Check mass balance closure.
    
    Returns:
    --------
    Tuple[bool, float] : (is_balanced, error_magnitude)
    """
    error = abs(feed_flow - (permeate_flow + concentrate_flow))
    is_balanced = error < tolerance
    return is_balanced, error


def create_pump_initialization_guide(config: Dict) -> Dict:
    """
    Create initialization suggestions for pump pressures.
    
    This provides guidance for WaterTAP model initialization
    based on the vessel array configuration.
    
    Parameters:
    -----------
    config : dict
        Vessel array configuration from optimization
        
    Returns:
    --------
    dict : Pump initialization suggestions
    """
    suggestions = {
        'approach': 'These are initialization estimates only. WaterTAP will optimize actual values.',
        'stages': []
    }
    
    # Get feed conditions
    feed_salinity = config.get('feed_salinity_ppm', 5000)
    is_recycle = config.get('recycle_ratio', 0) > 0
    
    if is_recycle:
        # Use effective salinity for recycle cases
        feed_salinity = config.get('effective_feed_salinity_ppm', feed_salinity)
    
    # Provide suggestions for each stage
    for i, stage in enumerate(config['stages']):
        stage_num = stage['stage_number']
        stage_recovery = stage['stage_recovery']
        
        # Estimate required pressure for this stage
        init_pressure = estimate_initial_pump_pressure(
            feed_salinity_ppm=feed_salinity,
            water_recovery=stage_recovery,
            over_pressure=0.3,
            membrane_type=config.get('membrane_type', 'brackish')
        )
        
        # Get optimization bounds
        lower_bound, upper_bound = get_pump_pressure_bounds(
            membrane_type=config.get('membrane_type', 'brackish'),
            stage=stage_num
        )
        
        suggestions['stages'].append({
            'stage_number': stage_num,
            'initial_pressure_pa': init_pressure,
            'initial_pressure_bar': init_pressure / 1e5,
            'optimization_bounds_pa': (lower_bound, upper_bound),
            'optimization_bounds_bar': (lower_bound / 1e5, upper_bound / 1e5),
            'pressure_drop_pa': calculate_pressure_drop(
                stage['feed_flow_m3h'], stage_num, config.get('membrane_type', 'brackish')
            )
        })
    
    # Add overall system suggestions
    suggestions['minimum_water_flux_kg_m2_s'] = estimate_minimum_water_flux()
    suggestions['optimization_notes'] = [
        'Unfix pump outlet pressures for optimization',
        'Add minimum water flux constraint to ensure feasibility',
        'Consider product quality constraints (e.g., max TDS)',
        'LCOW or specific energy consumption as objective'
    ]
    
    return suggestions


def convert_numpy_types(obj):
    """
    Recursively convert numpy types to native Python types for JSON serialization.
    
    This fixes the "Unable to serialize unknown type" error when numpy types
    are present in the results dictionary returned by optimization functions.
    
    Parameters:
    -----------
    obj : Any
        Object that may contain numpy types
        
    Returns:
    --------
    Any : Object with numpy types converted to Python types
    """
    if isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_numpy_types(item) for item in obj)
    else:
        return obj


def get_spiral_wound_dimensions(membrane_type: str = "8040") -> Dict[str, float]:
    """
    Get standard spiral wound membrane dimensions.
    
    Parameters:
    -----------
    membrane_type : str
        Membrane element type (e.g., "8040", "8021", etc.)
        Currently only supports 8" diameter elements
        
    Returns:
    --------
    dict : Dictionary containing membrane dimensions in meters
    """
    # Import config utilities
    from .config import get_config
    
    # Get all membrane dimensions from config
    all_membrane_dims = get_config("membrane_dimensions", {})
    
    # Get dimensions for the specified membrane type
    if membrane_type in all_membrane_dims:
        type_dims = all_membrane_dims[membrane_type]
        dimensions = {
            "diameter_m": type_dims.get("diameter_m"),
            "length_m": type_dims.get("length_m"),
            "active_area_m2": type_dims.get("active_area_m2"),
            "elements_per_vessel": type_dims.get("elements_per_vessel")
        }
    else:
        dimensions = {
            "diameter_m": None,
            "length_m": None,
            "active_area_m2": None,
            "elements_per_vessel": None
        }
    
    # Check if we got valid dimensions
    if any(v is None for v in dimensions.values()):
        # Fallback to default 8040 dimensions if type not found
        dimensions = {
            "diameter_m": 0.2032,  # 8 inches
            "length_m": 1.016,     # 40 inches
            "active_area_m2": 37.16,  # 400 ft²
            "elements_per_vessel": 7
        }
    
    return dimensions


def calculate_spiral_wound_width(
    total_area_m2: float,
    length_m: float,
    n_modules: int = 1
) -> float:
    """
    Calculate required width for spiral wound modules to achieve target area.
    
    For spiral wound modules, the area formula is:
    A = length × 2 × width × n_modules
    
    The factor of 2 accounts for the membrane being folded.
    
    Parameters:
    -----------
    total_area_m2 : float
        Total target membrane area in m²
    length_m : float
        Length of the membrane module(s) in meters
    n_modules : int
        Number of modules in parallel (default 1)
        
    Returns:
    --------
    float : Required width per module in meters
    """
    if length_m <= 0 or n_modules <= 0:
        raise ValueError("Length and number of modules must be positive")
    
    # Rearrange area formula: A = L × 2 × W × n
    # Therefore: W = A / (2 × L × n)
    width_per_module = total_area_m2 / (2 * length_m * n_modules)
    
    return width_per_module


def calculate_vessel_arrangement_spiral_wound(
    total_area_m2: float,
    n_vessels: int,
    membrane_type: str = "8040"
) -> Dict[str, float]:
    """
    Calculate spiral wound membrane arrangement for given vessels.
    
    Parameters:
    -----------
    total_area_m2 : float
        Total required membrane area
    n_vessels : int
        Number of pressure vessels
    membrane_type : str
        Type of membrane element (default "8040")
        
    Returns:
    --------
    dict : Configuration details including length, width, and validation
    """
    # Get standard dimensions
    dimensions = get_spiral_wound_dimensions(membrane_type)
    
    element_area = dimensions["active_area_m2"]
    element_length = dimensions["length_m"]
    elements_per_vessel = dimensions["elements_per_vessel"]
    
    # Calculate total elements needed
    total_elements_needed = total_area_m2 / element_area
    elements_per_vessel_calc = total_elements_needed / n_vessels
    
    # For spiral wound, elements are in series within a vessel
    # Total length is element length × number of elements in series
    total_length = element_length * elements_per_vessel
    
    # Calculate required width for WaterTAP model
    # Area = length × 2 × width × n_vessels (for spiral wound)
    required_width = calculate_spiral_wound_width(
        total_area_m2, 
        total_length, 
        n_vessels
    )
    
    # Aggregate width for all vessels
    aggregate_width = required_width * n_vessels
    
    return {
        "membrane_type": membrane_type,
        "element_area_m2": element_area,
        "element_length_m": element_length,
        "elements_per_vessel": elements_per_vessel,
        "total_elements": int(np.ceil(total_elements_needed)),
        "vessel_length_m": total_length,
        "width_per_vessel_m": required_width,
        "aggregate_width_m": aggregate_width,
        "total_area_m2": total_area_m2,
        "n_vessels": n_vessels,
        "area_check_m2": total_length * 2 * aggregate_width,  # Should equal total_area_m2
        "configuration": f"{n_vessels} vessels × {elements_per_vessel} elements"
    }