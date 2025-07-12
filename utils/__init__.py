# -*- coding: utf-8 -*-
"""
RO Design MCP Server utilities package.
"""

from .optimize_ro import optimize_vessel_array_configuration
from .helpers import (
    create_pump_initialization_guide,
    validate_recovery_target,
    validate_flow_rate,
    validate_salinity,
    check_mass_balance,
    format_array_notation
)
from .constants import (
    DEFAULT_FLUX_TARGETS_LMH,
    DEFAULT_MIN_CONCENTRATE_FLOW_M3H,
    MEMBRANE_PROPERTIES,
    BASE_PRESSURES,
    DEFAULT_ELECTRICITY_COST,
    DEFAULT_MEMBRANE_COST
)
from .notebook_runner import run_configuration_report

__all__ = [
    # Main optimization function
    "optimize_vessel_array_configuration",
    
    # Helper functions
    "create_pump_initialization_guide",
    "validate_recovery_target",
    "validate_flow_rate", 
    "validate_salinity",
    "check_mass_balance",
    "format_array_notation",
    
    # Constants
    "DEFAULT_FLUX_TARGETS_LMH",
    "DEFAULT_MIN_CONCENTRATE_FLOW_M3H",
    "MEMBRANE_PROPERTIES",
    "BASE_PRESSURES",
    "DEFAULT_ELECTRICITY_COST",
    "DEFAULT_MEMBRANE_COST",
    
    # Notebook runner
    "run_configuration_report"
]