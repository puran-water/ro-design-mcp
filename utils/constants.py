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
        'A_w': get_config('membrane_properties.brackish.A_w', 4.2e-12),
        'B_s': get_config('membrane_properties.brackish.B_s', 3.5e-8),
        'reflect_coeff': get_config('membrane_properties.brackish.reflect_coeff', 0.95),
        'pressure_drop_stage1': get_config('membrane_properties.brackish.pressure_drop.stage1', 2e5),
        'pressure_drop_stage2': get_config('membrane_properties.brackish.pressure_drop.stage2', 1.5e5),
        'pressure_drop_stage3': get_config('membrane_properties.brackish.pressure_drop.stage3', 1e5),
        'max_pressure': get_config('membrane_properties.brackish.max_pressure', 82.7e5)
    },
    'seawater': {
        'A_w': get_config('membrane_properties.seawater.A_w', 1.5e-12),
        'B_s': get_config('membrane_properties.seawater.B_s', 1.0e-8),
        'reflect_coeff': get_config('membrane_properties.seawater.reflect_coeff', 0.95),
        'pressure_drop_stage1': get_config('membrane_properties.seawater.pressure_drop.stage1', 3e5),
        'pressure_drop_stage2': get_config('membrane_properties.seawater.pressure_drop.stage2', 2.5e5),
        'pressure_drop_stage3': get_config('membrane_properties.seawater.pressure_drop.stage3', 2e5),
        'max_pressure': get_config('membrane_properties.seawater.max_pressure', 120e5)
    }
}

# Base operating pressures (Pa)
BASE_PRESSURES = {
    'brackish': get_config('membrane_properties.brackish.base_pressures', [15e5, 20e5, 25e5]),
    'seawater': get_config('membrane_properties.seawater.base_pressures', [40e5, 50e5, 60e5])
}

# Economic parameters
DEFAULT_ELECTRICITY_COST = get_config('economics.electricity_cost_usd_kwh', 0.07)
DEFAULT_MEMBRANE_COST = get_config('economics.membrane_cost_usd_m2', 30)
DEFAULT_UTILIZATION_FACTOR = get_config('economics.utilization_factor', 0.9)
DEFAULT_PUMP_EFFICIENCY = get_config('economics.pump_efficiency', 0.8)