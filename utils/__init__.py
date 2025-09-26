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
    DEFAULT_ELECTRICITY_COST,
    DEFAULT_MEMBRANE_COST,
    TYPICAL_COMPOSITIONS,
    MW_DATA,
    CHARGE_MAP,
    STOKES_RADIUS_DATA,
    DEFAULT_SALT_PASSAGE
)

# Full WaterTAP simulator removed - use hybrid_ro_simulator instead

# RO initialization utilities
from .ro_initialization import (
    calculate_required_pressure,
    initialize_pump_with_pressure,
    initialize_ro_unit_elegant,
    initialize_multistage_ro_elegant,
    calculate_concentrate_tds
)

# MCAS configuration builder
from .mcas_builder import (
    build_mcas_property_configuration,
    check_electroneutrality,
    get_total_dissolved_solids,
    calculate_ionic_strength
)

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
    "DEFAULT_ELECTRICITY_COST",
    "DEFAULT_MEMBRANE_COST",
    "TYPICAL_COMPOSITIONS",
    "MW_DATA",
    "CHARGE_MAP",
    "STOKES_RADIUS_DATA",
    "DEFAULT_SALT_PASSAGE",

    # RO initialization
    "calculate_required_pressure",
    "initialize_pump_with_pressure",
    "initialize_ro_unit_elegant",
    "initialize_multistage_ro_elegant",
    "calculate_concentrate_tds",

    # MCAS configuration
    "build_mcas_property_configuration",
    "check_electroneutrality",
    "get_total_dissolved_solids",
    "calculate_ionic_strength"
]