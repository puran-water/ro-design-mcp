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
from .notebook_runner import run_configuration_report

# RO Model building and solving functions
from .ro_model_builder import (
    build_ro_model_mcas
)
from .ro_solver import (
    initialize_and_solve_mcas,
    initialize_model_sequential,
    initialize_with_block_triangularization,
    initialize_with_custom_guess,
    initialize_with_relaxation,
    initialize_model_advanced
)
from .ro_results_extractor import (
    extract_results_mcas,
    predict_scaling_potential
)

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
    
    # RO model building
    "build_ro_model_mcas",
    
    # RO solving
    "initialize_and_solve_mcas",
    "initialize_model_sequential",
    "initialize_with_block_triangularization",
    "initialize_with_custom_guess",
    "initialize_with_relaxation",
    "initialize_model_advanced",
    
    # RO results extraction
    "extract_results_mcas",
    "predict_scaling_potential",
    
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
    "calculate_ionic_strength",
    
    # Notebook runner
    "run_configuration_report"
]