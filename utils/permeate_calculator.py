"""
Permeate quality calculator using log-mean concentration approach.

Based on Solution-Diffusion model and FilmTec Technical Manual.
Uses log-mean concentration for accurate stage-wise calculations.
"""

import math
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


def calculate_stage_permeate_concentration(
    stage_feed_conc_mg_l: dict,
    stage_recovery: float,
    membrane_properties: dict,
    temperature_c: float = 25
) -> tuple[dict, dict]:
    """
    Calculate stage permeate and reject concentrations using log-mean approach.

    This function calculates STAGE-SPECIFIC concentrations based on:
    - The feed concentration TO THIS STAGE (not system feed)
    - The recovery OF THIS STAGE (not system recovery)
    - Stage-specific rejection characteristics

    Parameters
    ----------
    stage_feed_conc_mg_l : dict
        Ion concentrations in the FEED TO THIS STAGE (mg/L)
        This is the reject from previous stage or system feed for stage 1
    stage_recovery : float
        Recovery fraction FOR THIS STAGE (0-1)
        NOT the cumulative system recovery
    membrane_properties : dict
        Membrane properties including ion-specific rejections
    temperature_c : float
        Operating temperature in Celsius

    Returns
    -------
    tuple[dict, dict]
        (permeate_conc, reject_conc) - both in mg/L
    """
    permeate_conc = {}
    reject_conc = {}

    # First calculate reject concentration for this stage
    # Using stage-specific recovery
    concentration_factor = 1 / (1 - stage_recovery)

    for ion, feed_conc in stage_feed_conc_mg_l.items():
        # Get ion-specific rejection (or default)
        rejection = get_ion_rejection(ion, membrane_properties, temperature_c)

        # Calculate approximate reject concentration for this stage
        # This accounts for both concentration and rejection effects
        reject_conc[ion] = feed_conc * concentration_factor

        # Calculate log-mean concentration between stage feed and reject
        if abs(reject_conc[ion] - feed_conc) > 0.01:  # Avoid division by zero
            c_lm = (reject_conc[ion] - feed_conc) / math.log(reject_conc[ion] / feed_conc)
        else:
            c_lm = feed_conc

        # Calculate permeate concentration using log-mean and rejection
        permeate_conc[ion] = c_lm * (1 - rejection)

        # Refine reject concentration using mass balance for this stage
        # Mass in = Mass out (permeate + reject)
        # feed_conc * feed_flow = permeate_conc * permeate_flow + reject_conc * reject_flow
        # Solving for reject_conc:
        mass_in = feed_conc * 1.0  # Normalized flow = 1
        mass_out_permeate = permeate_conc[ion] * stage_recovery
        mass_out_reject = mass_in - mass_out_permeate
        reject_flow = 1.0 - stage_recovery

        if reject_flow > 0:
            reject_conc[ion] = mass_out_reject / reject_flow

    return permeate_conc, reject_conc


def get_ion_rejection(
    ion: str,
    membrane_properties: dict,
    temperature_c: float = 25
) -> float:
    """
    Get ion-specific rejection coefficient with temperature correction.

    Parameters
    ----------
    ion : str
        Ion name (e.g., 'Na+', 'Cl-', 'SO4-2')
    membrane_properties : dict
        Membrane properties including rejection data
    temperature_c : float
        Temperature in Celsius

    Returns
    -------
    float
        Rejection coefficient (0-1)
    """
    # Base rejections at 25°C (typical values from literature)
    default_rejections = {
        'Na+': 0.985,      # Monovalent cations
        'K+': 0.985,
        'NH4+': 0.98,
        'Cl-': 0.985,      # Monovalent anions
        'NO3-': 0.93,
        'HCO3-': 0.95,
        'Ca+2': 0.99,      # Divalent cations
        'Mg+2': 0.99,
        'Ba+2': 0.99,
        'Sr+2': 0.99,
        'SO4-2': 0.998,    # Divalent anions
        'CO3-2': 0.995,
        'SiO2': 0.97,      # Silica
        'B': 0.70,         # Boron (low rejection)
    }

    # Check for specific rejection in membrane properties
    specific_key = f'rejection_{ion}'
    if specific_key in membrane_properties:
        base_rejection = membrane_properties[specific_key]
    elif ion in default_rejections:
        base_rejection = default_rejections[ion]
    else:
        # Default for unknown ions
        logger.warning(f"Unknown ion {ion}, using default rejection 0.98")
        base_rejection = membrane_properties.get('rejection_default', 0.98)

    # Temperature correction (approximate)
    # Rejection typically decreases with temperature
    temp_factor = 1.0 - 0.002 * (temperature_c - 25)  # 0.2% per °C

    return min(0.999, base_rejection * temp_factor)


def calculate_stage_mixed_permeate(
    stage_permeate_flows: list,
    stage_permeate_concentrations: list
) -> dict:
    """
    Calculate mixed permeate concentration when multiple stages combine.

    Used for systems where permeate from multiple stages is collected.

    Parameters
    ----------
    stage_permeate_flows : list
        List of permeate flow rates from each stage (m³/h)
    stage_permeate_concentrations : list
        List of dicts with ion concentrations for each stage (mg/L)

    Returns
    -------
    dict
        Mixed permeate ion concentrations (mg/L)
    """
    total_flow = sum(stage_permeate_flows)
    mixed_conc = {}

    # Get all ions present
    all_ions = set()
    for conc_dict in stage_permeate_concentrations:
        all_ions.update(conc_dict.keys())

    # Calculate flow-weighted average for each ion
    for ion in all_ions:
        total_mass = 0
        for flow, conc_dict in zip(stage_permeate_flows, stage_permeate_concentrations):
            if ion in conc_dict:
                total_mass += flow * conc_dict[ion]

        mixed_conc[ion] = total_mass / total_flow if total_flow > 0 else 0

    return mixed_conc


def estimate_permeate_tds(
    permeate_conc_mg_l: dict,
    include_co2: bool = True
) -> float:
    """
    Estimate total dissolved solids in permeate.

    Parameters
    ----------
    permeate_conc_mg_l : dict
        Ion concentrations in permeate (mg/L)
    include_co2 : bool
        Whether to estimate CO2 contribution

    Returns
    -------
    float
        Estimated TDS (mg/L)
    """
    tds = sum(permeate_conc_mg_l.values())

    # CO2 passes freely through RO membranes
    # Estimate based on typical feedwater
    if include_co2 and 'HCO3-' in permeate_conc_mg_l:
        # Rough estimate: CO2 ≈ 10% of bicarbonate in typical waters
        co2_estimate = permeate_conc_mg_l['HCO3-'] * 0.1
        tds += co2_estimate

    return tds