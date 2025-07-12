# -*- coding: utf-8 -*-
"""
Constants for RO design calculations.
"""

# Standard element and vessel parameters
STANDARD_ELEMENT_AREA_M2 = 37.16  # 400 ft² standard element
ELEMENTS_PER_VESSEL = 7

# Stage-specific design parameters
DEFAULT_FLUX_TARGETS_LMH = [18, 15, 12]  # LMH for stages 1, 2, 3+ (same for all membrane types)
DEFAULT_MIN_CONCENTRATE_FLOW_M3H = [3.5, 3.8, 4.0]  # m³/h per vessel

# Default flux tolerance (as fraction)
DEFAULT_FLUX_TOLERANCE = 0.1  # ±10% of target

# Recovery and optimization parameters
DEFAULT_RECOVERY_TOLERANCE = 0.02  # 2% tolerance
MAX_STAGES = 3  # Industry standard
DEFAULT_MAX_RECYCLE_RATIO = 0.9
CONVERGENCE_TOLERANCE = 0.01  # m³/h for recycle optimization

# Membrane properties (default values)
MEMBRANE_PROPERTIES = {
    'brackish': {
        'A_w': 4.2e-12,  # m/s/Pa - Water permeability
        'B_s': 3.5e-8,   # m/s - Salt permeability
        'reflect_coeff': 0.95,  # Reflection coefficient for SKK model
        'pressure_drop_stage1': 2e5,  # Pa
        'pressure_drop_stage2': 1.5e5,  # Pa
        'pressure_drop_stage3': 1e5,   # Pa
        'max_pressure': 82.7e5  # 82.7 bar
    },
    'seawater': {
        'A_w': 1.5e-12,  # m/s/Pa - Lower for SW membranes
        'B_s': 1.0e-8,   # m/s - Lower for SW membranes
        'reflect_coeff': 0.95,
        'pressure_drop_stage1': 3e5,  # Pa
        'pressure_drop_stage2': 2.5e5,  # Pa
        'pressure_drop_stage3': 2e5,   # Pa
        'max_pressure': 120e5  # 120 bar
    }
}

# Base operating pressures (Pa)
BASE_PRESSURES = {
    'brackish': [15e5, 20e5, 25e5],  # 15, 20, 25 bar
    'seawater': [40e5, 50e5, 60e5]   # 40, 50, 60 bar
}

# Economic parameters
DEFAULT_ELECTRICITY_COST = 0.07  # $/kWh
DEFAULT_MEMBRANE_COST = 30  # $/m²
DEFAULT_UTILIZATION_FACTOR = 0.9
DEFAULT_PUMP_EFFICIENCY = 0.8