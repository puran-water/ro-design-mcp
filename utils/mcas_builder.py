"""
MCAS (Multi-Component Aqueous Solution) property package builder for WaterTAP.

This module handles the creation of MCAS property packages from ion compositions,
including charge balance checking and adjustment.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from pyomo.environ import units as pyunits
from watertap.property_models.multicomp_aq_sol_prop_pack import ActivityCoefficientModel

logger = logging.getLogger(__name__)

# User-friendly ion notation mapping to WaterTAP notation
ION_NOTATION_MAP = {
    # Cations
    "Na+": "Na_+",
    "Ca2+": "Ca_2+", 
    "Mg2+": "Mg_2+",
    "K+": "K_+",
    "NH4+": "NH4_+",
    "H+": "H_+",
    "Ba2+": "Ba_2+",
    "Sr2+": "Sr_2+",
    "Fe2+": "Fe_2+",
    "Fe3+": "Fe_3+",
    # Anions
    "Cl-": "Cl_-",
    "SO4-2": "SO4_2-",
    "HCO3-": "HCO3_-",
    "CO3-2": "CO3_2-",
    "NO3-": "NO3_-",
    "PO4-3": "PO4_3-",
    "F-": "F_-",
    "Br-": "Br_-",
    "OH-": "OH_-",
    "SiO3-2": "SiO3_2-",
}


# Ion data - molecular weights, charges, diffusivities, and Stokes radii
# Note: WaterTAP MCAS uses underscores in ion notation (e.g., Ca_2+ not Ca2+)
# Stokes radii calculated from diffusivity using Stokes-Einstein equation
ION_DATA = {
    # Cations
    "Na_+": {"mw": 22.99, "charge": 1, "diffusivity": 1.33e-9, "stokes_radius": 1.84e-10},
    "Ca_2+": {"mw": 40.08, "charge": 2, "diffusivity": 0.79e-9, "stokes_radius": 3.10e-10},
    "Mg_2+": {"mw": 24.31, "charge": 2, "diffusivity": 0.71e-9, "stokes_radius": 3.45e-10},
    "K_+": {"mw": 39.10, "charge": 1, "diffusivity": 1.96e-9, "stokes_radius": 1.25e-10},
    "NH4_+": {"mw": 18.04, "charge": 1, "diffusivity": 1.98e-9, "stokes_radius": 1.24e-10},
    "H_+": {"mw": 1.01, "charge": 1, "diffusivity": 9.31e-9, "stokes_radius": 0.26e-10},
    "Ba_2+": {"mw": 137.33, "charge": 2, "diffusivity": 0.85e-9, "stokes_radius": 2.88e-10},
    "Sr_2+": {"mw": 87.62, "charge": 2, "diffusivity": 0.79e-9, "stokes_radius": 3.10e-10},
    "Fe_2+": {"mw": 55.85, "charge": 2, "diffusivity": 0.72e-9, "stokes_radius": 3.39e-10},
    "Fe_3+": {"mw": 55.85, "charge": 3, "diffusivity": 0.60e-9, "stokes_radius": 4.07e-10},
    
    # Anions
    "Cl_-": {"mw": 35.45, "charge": -1, "diffusivity": 2.03e-9, "stokes_radius": 1.21e-10},
    "SO4_2-": {"mw": 96.06, "charge": -2, "diffusivity": 1.07e-9, "stokes_radius": 2.29e-10},
    "HCO3_-": {"mw": 61.02, "charge": -1, "diffusivity": 1.18e-9, "stokes_radius": 2.07e-10},
    "CO3_2-": {"mw": 60.01, "charge": -2, "diffusivity": 0.92e-9, "stokes_radius": 2.66e-10},
    "NO3_-": {"mw": 62.00, "charge": -1, "diffusivity": 1.90e-9, "stokes_radius": 1.28e-10},
    "PO4_3-": {"mw": 94.97, "charge": -3, "diffusivity": 0.61e-9, "stokes_radius": 4.00e-10},
    "F_-": {"mw": 19.00, "charge": -1, "diffusivity": 1.46e-9, "stokes_radius": 1.67e-10},
    "Br_-": {"mw": 79.90, "charge": -1, "diffusivity": 2.01e-9, "stokes_radius": 1.22e-10},
    "OH_-": {"mw": 17.01, "charge": -1, "diffusivity": 5.27e-9, "stokes_radius": 0.46e-10},
    "SiO3_2-": {"mw": 76.08, "charge": -2, "diffusivity": 1.00e-9, "stokes_radius": 2.44e-10},
}


def convert_ion_notation(ion_composition: Dict[str, float]) -> Dict[str, float]:
    """
    Convert user-friendly ion notation to WaterTAP MCAS notation.
    
    Args:
        ion_composition: Dictionary with user notation (e.g., "Ca2+")
        
    Returns:
        Dictionary with WaterTAP notation (e.g., "Ca_2+")
    """
    converted = {}
    for ion, conc in ion_composition.items():
        if ion in ION_NOTATION_MAP:
            converted[ION_NOTATION_MAP[ion]] = conc
        elif ion in ION_DATA:
            # Already in WaterTAP notation
            converted[ion] = conc
        else:
            logger.warning(f"Unknown ion notation: {ion}")
    return converted


def check_electroneutrality(
    ion_composition: Dict[str, float],
    tolerance: float = 0.01
) -> Tuple[bool, float]:
    """
    Check if the ion composition is electroneutral.
    
    Args:
        ion_composition: Dictionary of ion names and concentrations (mg/L)
        tolerance: Acceptable charge imbalance as fraction
        
    Returns:
        Tuple of (is_neutral, charge_imbalance_fraction)
    """
    # Ensure we're working with WaterTAP notation
    ion_composition = convert_ion_notation(ion_composition)
    
    total_positive = 0.0
    total_negative = 0.0
    
    for ion, conc_mg_l in ion_composition.items():
        if ion not in ION_DATA:
            logger.warning(f"Unknown ion: {ion}")
            continue
            
        # Convert mg/L to mol/L
        mol_l = conc_mg_l / 1000 / ION_DATA[ion]["mw"]
        
        # Calculate charge contribution
        charge_eq_l = mol_l * abs(ION_DATA[ion]["charge"])
        
        if ION_DATA[ion]["charge"] > 0:
            total_positive += charge_eq_l
        else:
            total_negative += charge_eq_l
    
    # Calculate imbalance
    total_charge = total_positive + total_negative
    if total_charge > 0:
        imbalance_fraction = abs(total_positive - total_negative) / total_charge
    else:
        imbalance_fraction = 0.0
    
    is_neutral = imbalance_fraction <= tolerance
    
    logger.info(f"Charge balance: +{total_positive:.3e} / -{total_negative:.3e} eq/L")
    logger.info(f"Imbalance: {imbalance_fraction*100:.1f}%")
    
    return is_neutral, imbalance_fraction


def adjust_for_electroneutrality(
    ion_composition: Dict[str, float],
    adjustment_ion: str = "Cl_-",
    max_adjustment: float = 0.10
) -> Dict[str, float]:
    """
    Adjust ion composition to achieve electroneutrality.
    
    Args:
        ion_composition: Dictionary of ion names and concentrations (mg/L)
        adjustment_ion: Ion to use for charge balance adjustment
        max_adjustment: Maximum allowed adjustment as fraction of total
        
    Returns:
        Adjusted ion composition
    """
    # Ensure we're working with WaterTAP notation
    ion_composition = convert_ion_notation(ion_composition)
    
    is_neutral, imbalance = check_electroneutrality(ion_composition)
    
    if is_neutral:
        return ion_composition.copy()
    
    if adjustment_ion not in ION_DATA:
        raise ValueError(f"Unknown adjustment ion: {adjustment_ion}")
    
    # Calculate required adjustment
    total_positive = 0.0
    total_negative = 0.0
    
    for ion, conc_mg_l in ion_composition.items():
        if ion not in ION_DATA:
            continue
        mol_l = conc_mg_l / 1000 / ION_DATA[ion]["mw"]
        charge_eq_l = mol_l * abs(ION_DATA[ion]["charge"])
        
        if ION_DATA[ion]["charge"] > 0:
            total_positive += charge_eq_l
        else:
            total_negative += charge_eq_l
    
    # Calculate deficit
    charge_deficit = total_positive - total_negative  # Positive if cation excess
    
    # Validate adjustment ion charge is appropriate
    adj_charge = ION_DATA[adjustment_ion]["charge"]
    if charge_deficit > 0 and adj_charge > 0:
        raise ValueError(
            f"Cannot use cation {adjustment_ion} to balance cation excess. "
            f"Choose an anion like Cl_- instead."
        )
    elif charge_deficit < 0 and adj_charge < 0:
        raise ValueError(
            f"Cannot use anion {adjustment_ion} to balance anion excess. "
            f"Choose a cation like Na_+ instead."
        )
    
    # Calculate required moles of adjustment ion
    required_mol_l = abs(charge_deficit / adj_charge)
    required_mg_l = required_mol_l * ION_DATA[adjustment_ion]["mw"] * 1000
    
    # Check if adjustment is too large
    current_conc = ion_composition.get(adjustment_ion, 0.0)
    if current_conc > 0:
        adjustment_fraction = required_mg_l / current_conc
        if adjustment_fraction > max_adjustment:
            logger.warning(
                f"Required adjustment ({adjustment_fraction:.1%}) exceeds "
                f"maximum ({max_adjustment:.1%})"
            )
    
    # Apply adjustment
    adjusted = ion_composition.copy()
    
    # Add the required amount of adjustment ion
    adjusted[adjustment_ion] = current_conc + required_mg_l
    logger.info(f"Added {required_mg_l:.1f} mg/L of {adjustment_ion} for charge balance")
    
    return adjusted


def build_mcas_from_ions(
    ion_composition: Dict[str, float],
    balance_charge: bool = True,
    adjustment_ion: str = "Cl_-"
) -> Dict:
    """
    Build MCAS property package configuration from ion composition.
    
    Args:
        ion_composition: Dictionary of ion names and concentrations (mg/L)
        balance_charge: Whether to adjust for electroneutrality
        adjustment_ion: Ion to use for charge balance
        
    Returns:
        Dictionary configuration for MCAS property package
    """
    # Convert notation first to ensure proper handling
    ion_composition = convert_ion_notation(ion_composition)
    
    # Check and adjust charge balance if requested
    if balance_charge:
        working_composition = adjust_for_electroneutrality(
            ion_composition, adjustment_ion
        )
    else:
        working_composition = ion_composition.copy()
        is_neutral, imbalance = check_electroneutrality(working_composition)
        if not is_neutral:
            logger.warning(f"Charge imbalance: {imbalance:.1%}")
    
    # Build component list
    components = ["H2O"]
    for ion in working_composition:
        if ion in ION_DATA and working_composition[ion] > 0:
            components.append(ion)
    
    # Build MCAS configuration
    mcas_config = {
        "components": components,
        "phases": {
            "Liq": {
                "type": "AqueousPhase",
                "equation_of_state": "MCAS"
            }
        },
        "base_units": {
            "time": pyunits.s,
            "length": pyunits.m,
            "mass": pyunits.kg,
            "amount": pyunits.mol,
            "temperature": pyunits.K
        },
        "state_definition": "FTPx",
        "state_bounds": {
            "flow_mass_phase_comp": (0, None, pyunits.kg/pyunits.s),
            "temperature": (273.15, 373.15, pyunits.K),
            "pressure": (5e4, 1e7, pyunits.Pa)
        },
        "state_components": "true",
        "pressure_ref": 101325,
        "temperature_ref": 298.15
    }
    
    # Add component-specific data
    for comp in components:
        if comp == "H2O":
            continue
        if comp in ION_DATA:
            # Add molecular weight and other properties
            # This would be used by MCAS internally
            pass
    
    return mcas_config, working_composition


def get_total_dissolved_solids(ion_composition: Dict[str, float]) -> float:
    """
    Calculate total dissolved solids from ion composition.
    
    Args:
        ion_composition: Dictionary of ion names and concentrations (mg/L)
        
    Returns:
        Total dissolved solids in mg/L (ppm)
    """
    return sum(ion_composition.values())


def build_mcas_property_configuration(
    feed_composition: Dict[str, float],
    include_scaling_ions: bool = True,
    include_ph_species: bool = True
) -> Dict[str, Any]:
    """
    Build complete MCAS property configuration for WaterTAP RO model.
    
    Args:
        feed_composition: Ion composition in mg/L (accepts both user and WaterTAP notation)
        include_scaling_ions: Include ions relevant for scaling prediction
        include_ph_species: Include pH-related species
        
    Returns:
        Complete property configuration for WaterTAP MCASParameterBlock
    """
    # Convert to WaterTAP notation if needed
    feed_composition = convert_ion_notation(feed_composition)
    
    # Determine appropriate adjustment ion based on charge imbalance
    is_neutral, imbalance = check_electroneutrality(feed_composition)
    
    if not is_neutral:
        # Calculate charge balance to determine which type of ion to use
        total_positive = 0.0
        total_negative = 0.0
        
        for ion, conc_mg_l in feed_composition.items():
            if ion in ION_DATA:
                mol_l = conc_mg_l / 1000 / ION_DATA[ion]["mw"]
                charge_eq_l = mol_l * abs(ION_DATA[ion]["charge"])
                
                if ION_DATA[ion]["charge"] > 0:
                    total_positive += charge_eq_l
                else:
                    total_negative += charge_eq_l
        
        # Choose adjustment ion based on imbalance
        charge_deficit = total_positive - total_negative
        if charge_deficit > 0:
            # Cation excess - use Cl- for adjustment
            adjustment_ion = "Cl_-"
        else:
            # Anion excess - use Na+ for adjustment
            adjustment_ion = "Na_+"
        
        # Adjust for electroneutrality
        balanced_composition = adjust_for_electroneutrality(
            feed_composition, 
            adjustment_ion=adjustment_ion
        )
    else:
        balanced_composition = feed_composition.copy()
    
    # Build solute list (excluding H2O)
    solute_list = []
    for ion in balanced_composition:
        if ion in ION_DATA and balanced_composition[ion] > 0:
            solute_list.append(ion)
    
    # Build molecular weight data
    mw_data = {"H2O": 18.015 / 1000}  # Water MW in kg/mol
    for ion in solute_list:
        if ion in ION_DATA:
            mw_data[ion] = ION_DATA[ion]["mw"] / 1000  # Convert to kg/mol
    
    # Build charge data (MCASParameterBlock expects 'charge' not 'charge_data')
    charge = {}
    for ion in solute_list:
        if ion in ION_DATA:
            charge[ion] = ION_DATA[ion]["charge"]
    
    # Build diffusivity data with correct key format
    diffusivity_data = {}
    for ion in solute_list:
        if ion in ION_DATA:
            # Keys must be tuples of (phase, component)
            diffusivity_data[("Liq", ion)] = ION_DATA[ion]["diffusivity"]
    
    # Build Stokes radius data
    stokes_radius_data = {}
    for ion in solute_list:
        if ion in ION_DATA:
            stokes_radius_data[ion] = ION_DATA[ion]["stokes_radius"]
    
    # Build MCAS configuration with correct structure
    mcas_config = {
        # Required parameters for MCASParameterBlock
        "solute_list": solute_list,
        "mw_data": mw_data,
        
        # Additional required data
        "charge": charge,
        "diffusivity_data": diffusivity_data,
        "stokes_radius_data": stokes_radius_data,
        
        # Store composition for reference (not passed to MCASParameterBlock)
        "ion_composition_mg_l": balanced_composition,
        
        # Activity coefficient model
        "activity_coefficient_model": ActivityCoefficientModel.davies
    }
    
    # Add scaling ion groups if requested
    if include_scaling_ions:
        mcas_config["scaling_ions"] = {
            "calcium_carbonate": ["Ca_2+", "CO3_2-", "HCO3_-"],
            "calcium_sulfate": ["Ca_2+", "SO4_2-"],
            "barium_sulfate": ["Ba_2+", "SO4_2-"],
            "strontium_sulfate": ["Sr_2+", "SO4_2-"],
            "calcium_fluoride": ["Ca_2+", "F_-"],
            "silica": ["SiO3_2-"]
        }
    
    # Add pH species if requested
    if include_ph_species:
        mcas_config["ph_species"] = {
            "water_dissociation": ["H_+", "OH_-"],
            "carbonate_system": ["H_+", "HCO3_-", "CO3_2-"]
        }
    
    # Add osmotic pressure calculation method
    mcas_config["osmotic_pressure_calculation"] = "activity_based"
    
    return mcas_config


def convert_to_molar_basis(
    ion_composition_mg_l: Dict[str, float]
) -> Dict[str, float]:
    """
    Convert ion composition from mg/L to mol/L.
    
    Args:
        ion_composition_mg_l: Ion concentrations in mg/L
        
    Returns:
        Ion concentrations in mol/L
    """
    molar_composition = {}
    
    for ion, conc_mg_l in ion_composition_mg_l.items():
        if ion in ION_DATA:
            mol_l = conc_mg_l / 1000 / ION_DATA[ion]["mw"]
            molar_composition[ion] = mol_l
        else:
            logger.warning(f"Unknown ion {ion}, skipping conversion")
    
    return molar_composition


def calculate_ionic_strength(ion_composition_mg_l: Dict[str, float]) -> float:
    """
    Calculate ionic strength of solution.
    
    Args:
        ion_composition_mg_l: Ion concentrations in mg/L
        
    Returns:
        Ionic strength in mol/L
    """
    ionic_strength = 0.0
    
    for ion, conc_mg_l in ion_composition_mg_l.items():
        if ion in ION_DATA:
            mol_l = conc_mg_l / 1000 / ION_DATA[ion]["mw"]
            charge = ION_DATA[ion]["charge"]
            ionic_strength += 0.5 * mol_l * charge**2
    
    return ionic_strength


def estimate_solution_density(
    tds_mg_l: float,
    temperature_c: float = 25.0
) -> float:
    """
    Estimate solution density from TDS.
    
    Args:
        tds_mg_l: Total dissolved solids in mg/L
        temperature_c: Temperature in Celsius
        
    Returns:
        Density in kg/m³
    """
    # Simple correlation for density
    # ρ = ρ_water + k * TDS
    # where k ≈ 0.00068 kg/m³ per mg/L TDS
    
    # Water density at temperature (simplified)
    water_density = 997.0 - 0.0025 * (temperature_c - 25.0)**2
    
    # Add TDS contribution
    density = water_density + 0.00068 * tds_mg_l
    
    return density


def create_watertap_property_block(
    mcas_config: Dict[str, Any],
    flow_basis: str = "mass"
) -> Dict[str, Any]:
    """
    Create property block configuration for WaterTAP.
    
    Args:
        mcas_config: MCAS configuration from build_mcas_property_configuration
        flow_basis: "mass" or "molar" flow basis
        
    Returns:
        Property block configuration
    """
    # This would be used directly in WaterTAP
    property_config = {
        "property_package": "MCAS",
        "configuration": mcas_config,
        "flow_basis": flow_basis,
        "has_phase_equilibrium": False,
        "default_arguments": {
            "has_phase_equilibrium": False,
            "defined_state": True
        }
    }
    
    return property_config