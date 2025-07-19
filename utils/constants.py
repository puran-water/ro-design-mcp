# -*- coding: utf-8 -*-
"""
Constants for RO design calculations.

This module provides backward compatibility while transitioning to 
the new configuration system. New code should use utils.config instead.
"""

from .config import get_config

# Standard element and vessel parameters
STANDARD_ELEMENT_AREA_M2 = get_config('element.standard_area_m2', 37.16)
ELEMENTS_PER_VESSEL = get_config('element.elements_per_vessel', 7)

# Stage-specific design parameters
DEFAULT_FLUX_TARGETS_LMH = get_config('stage_defaults.flux_targets_lmh', [18, 15, 12])
DEFAULT_MIN_CONCENTRATE_FLOW_M3H = get_config('stage_defaults.min_concentrate_flow_m3h', [3.5, 3.8, 4.0])

# Default flux tolerance (as fraction)
DEFAULT_FLUX_TOLERANCE = get_config('tolerances.flux_tolerance', 0.1)

# Recovery and optimization parameters
DEFAULT_RECOVERY_TOLERANCE = get_config('tolerances.recovery_tolerance', 0.02)
MAX_STAGES = get_config('optimization.max_stages', 3)
DEFAULT_MAX_RECYCLE_RATIO = get_config('optimization.max_recycle_ratio', 0.9)
CONVERGENCE_TOLERANCE = get_config('tolerances.convergence_tolerance', 0.01)

# Membrane properties (default values)
# Note: This maintains backward compatibility with the old structure
MEMBRANE_PROPERTIES = {
    'brackish': {
        'A_w': get_config('membrane_properties.brackish.A_w', 9.63e-12),
        'B_s': get_config('membrane_properties.brackish.B_s', 5.58e-8),
        'pressure_drop_stage1': get_config('membrane_properties.brackish.pressure_drop.stage1', 2e5),
        'pressure_drop_stage2': get_config('membrane_properties.brackish.pressure_drop.stage2', 1.5e5),
        'pressure_drop_stage3': get_config('membrane_properties.brackish.pressure_drop.stage3', 1e5),
        'max_pressure': get_config('membrane_properties.brackish.max_pressure', 4137000)
    },
    'seawater': {
        'A_w': get_config('membrane_properties.seawater.A_w', 3.0e-12),
        'B_s': get_config('membrane_properties.seawater.B_s', 1.5e-8),
        'pressure_drop_stage1': get_config('membrane_properties.seawater.pressure_drop.stage1', 3e5),
        'pressure_drop_stage2': get_config('membrane_properties.seawater.pressure_drop.stage2', 2.5e5),
        'pressure_drop_stage3': get_config('membrane_properties.seawater.pressure_drop.stage3', 2e5),
        'max_pressure': get_config('membrane_properties.seawater.max_pressure', 8270000)
    }
}

# Function to get membrane properties for any membrane type
def get_membrane_properties(membrane_type='brackish'):
    """
    Get membrane properties for a specific membrane type.
    
    Supports both generic types ('brackish', 'seawater') and
    specific models ('bw30_400', 'eco_pro_400', etc.)
    
    Args:
        membrane_type: Membrane type or model identifier
        
    Returns:
        Dictionary with membrane properties
    """
    # Check if it's in the backward-compatible dict
    if membrane_type in MEMBRANE_PROPERTIES:
        return MEMBRANE_PROPERTIES[membrane_type]
    
    # Otherwise try to get from config
    membrane_props = get_config(f'membrane_properties.{membrane_type}')
    if membrane_props:
        # Convert nested pressure_drop to flat structure for backward compatibility
        return {
            'A_w': membrane_props.get('A_w'),
            'B_s': membrane_props.get('B_s'),
            'pressure_drop_stage1': membrane_props.get('pressure_drop', {}).get('stage1'),
            'pressure_drop_stage2': membrane_props.get('pressure_drop', {}).get('stage2'),
            'pressure_drop_stage3': membrane_props.get('pressure_drop', {}).get('stage3'),
            'max_pressure': membrane_props.get('max_pressure')
        }
    
    # Default to brackish if not found
    return MEMBRANE_PROPERTIES['brackish']

# Base operating pressures - REMOVED (not used in SD model)

# Economic parameters
DEFAULT_ELECTRICITY_COST = get_config('economics.electricity_cost_usd_kwh', 0.07)
DEFAULT_MEMBRANE_COST = get_config('economics.membrane_cost_usd_m2', 30)
DEFAULT_UTILIZATION_FACTOR = get_config('economics.utilization_factor', 0.9)
DEFAULT_PUMP_EFFICIENCY = get_config('economics.pump_efficiency', 0.8)

# Ion composition constants (mg/L) for typical water types
TYPICAL_COMPOSITIONS = {
    "brackish": {
        "Na+": 1200,
        "Ca2+": 120,
        "Mg2+": 60,
        "K+": 20,
        "Cl-": 2100,
        "SO4-2": 200,
        "HCO3-": 150,
        "SiO3-2": 10
    },
    "seawater": {
        "Na+": 10800,
        "Ca2+": 420,
        "Mg2+": 1300,
        "K+": 400,
        "Sr2+": 8,
        "Cl-": 19400,
        "SO4-2": 2700,
        "HCO3-": 140,
        "Br-": 70,
        "F-": 1.3
    }
}

# Molecular weights (g/mol) for ions
MW_DATA = {
    "H2O": 18.015,
    "Na_+": 22.990,
    "Ca_2+": 40.078,
    "Mg_2+": 24.305,
    "K_+": 39.098,
    "Sr_2+": 87.620,
    "Cl_-": 35.453,
    "SO4_2-": 96.066,
    "HCO3_-": 61.017,
    "SiO3_2-": 76.083,
    "Br_-": 79.904,
    "F_-": 18.998
}

# Ion charges
CHARGE_MAP = {
    "Na_+": 1,
    "Ca_2+": 2,
    "Mg_2+": 2,
    "K_+": 1,
    "Sr_2+": 2,
    "Cl_-": -1,
    "SO4_2-": -2,
    "HCO3_-": -1,
    "SiO3_2-": -2,
    "Br_-": -1,
    "F_-": -1
}

# Stokes radii (m) for common ions
STOKES_RADIUS_DATA = {
    "Na_+": 1.84e-10,
    "Ca_2+": 3.09e-10,
    "Mg_2+": 3.47e-10,
    "K_+": 1.25e-10,
    "Sr_2+": 3.09e-10,
    "Cl_-": 1.21e-10,
    "SO4_2-": 2.30e-10,
    "HCO3_-": 1.56e-10,
    "SiO3_2-": 2.50e-10,
    "Br_-": 1.18e-10,
    "F_-": 1.66e-10
}

# Default salt passage for different membrane types
DEFAULT_SALT_PASSAGE = {
    "brackish": 0.015,  # 1.5%
    "seawater": 0.003   # 0.3%
}