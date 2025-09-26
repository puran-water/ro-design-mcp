"""
Stage pressure calculator using reject osmotic pressure.

Critical: Uses REJECT (concentrate) osmotic pressure for feed pressure calculation.
This is the industry standard approach as the membrane must overcome the highest
osmotic pressure in the stage (at the reject end).
"""

import math
from typing import Dict, Optional
import logging
from utils.pressure_drop_calculator import calculate_stage_pressure_drop
from utils.permeate_calculator import calculate_stage_permeate_concentration

logger = logging.getLogger(__name__)


def calculate_required_feed_pressure(
    stage_config: dict,
    stage_feed_composition_mg_l: dict,
    membrane_properties: dict,
    temperature_c: float = 25,
    permeate_pressure_bar: float = 1.0
) -> dict:
    """
    Calculate required feed pressure for a stage using REJECT osmotic pressure.

    CRITICAL: This function uses the STAGE-SPECIFIC parameters:
    - Feed composition TO THIS STAGE (not system feed)
    - Recovery OF THIS STAGE (not cumulative)
    - Reject osmotic pressure OF THIS STAGE

    The key insight from literature is that feed pressure must overcome:
    1. Osmotic pressure at the REJECT end (highest in stage)
    2. Net driving pressure for desired flux
    3. Pressure drop through the stage
    4. Permeate backpressure

    Parameters
    ----------
    stage_config : dict
        Stage configuration with:
        - feed_flow_m3h: Feed flow TO THIS STAGE
        - concentrate_flow_m3h: Reject flow FROM THIS STAGE
        - stage_recovery: Recovery OF THIS STAGE
        - n_vessels: Vessels in THIS STAGE
        - n_elements: Total elements in THIS STAGE
        - design_flux_lmh: Target flux for THIS STAGE
    stage_feed_composition_mg_l : dict
        Ion composition of feed TO THIS STAGE (mg/L)
    membrane_properties : dict
        Membrane properties including A value and rejections
    temperature_c : float
        Operating temperature
    permeate_pressure_bar : float
        Permeate side pressure (typically 1 bar)

    Returns
    -------
    dict
        Pressure components and total required feed pressure
    """
    # Step 1: Calculate STAGE-SPECIFIC reject composition
    # This is critical - we need the reject of THIS stage, not the system
    stage_recovery = stage_config['stage_recovery']

    # Get permeate and reject compositions for this stage
    permeate_comp, reject_comp = calculate_stage_permeate_concentration(
        stage_feed_composition_mg_l,
        stage_recovery,
        membrane_properties,
        temperature_c
    )

    # Step 2: Calculate osmotic pressure of STAGE REJECT
    # This is the key - use reject osmotic pressure, not feed
    reject_osmotic_pressure_pa = calculate_osmotic_pressure(
        reject_comp,
        temperature_c
    )

    # Step 3: Calculate required NDP from target flux
    target_flux_lmh = stage_config.get('design_flux_lmh', 18.0)
    A_value = membrane_properties.get('A_value', 4.2e-12)  # m/s/Pa

    ndp_required_pa = calculate_ndp_from_flux(
        target_flux_lmh,
        A_value,
        temperature_c
    )

    # Step 4: Calculate pressure drop using STAGE-SPECIFIC flows
    pressure_drop_pa = calculate_stage_pressure_drop(
        feed_flow_m3h=stage_config['feed_flow_m3h'],
        reject_flow_m3h=stage_config['concentrate_flow_m3h'],
        n_vessels=stage_config['n_vessels'],
        n_elements_per_vessel=stage_config['n_elements'] / stage_config['n_vessels']
    )

    # Step 5: Total feed pressure required
    # P_feed = P_osmotic_reject + NDP + ΔP + P_permeate
    permeate_pressure_pa = permeate_pressure_bar * 1e5

    feed_pressure_pa = (
        reject_osmotic_pressure_pa +  # Overcome reject osmotic pressure
        ndp_required_pa +              # Net driving pressure for flux
        pressure_drop_pa +             # Pressure loss through stage
        permeate_pressure_pa           # Permeate side pressure
    )

    return {
        'feed_pressure_bar': feed_pressure_pa / 1e5,
        'feed_pressure_pa': feed_pressure_pa,
        'components': {
            'osmotic_reject_bar': reject_osmotic_pressure_pa / 1e5,
            'ndp_bar': ndp_required_pa / 1e5,
            'pressure_drop_bar': pressure_drop_pa / 1e5,
            'permeate_pressure_bar': permeate_pressure_bar
        },
        'stage_data': {
            'feed_tds_mg_l': sum(stage_feed_composition_mg_l.values()),
            'reject_tds_mg_l': sum(reject_comp.values()),
            'permeate_tds_mg_l': sum(permeate_comp.values()),
            'stage_recovery': stage_recovery,
            'concentration_factor': 1 / (1 - stage_recovery)
        }
    }


def calculate_ndp_from_flux(
    flux_lmh: float,
    A_value: float,
    temperature_c: float = 25
) -> float:
    """
    Calculate required Net Driving Pressure from target flux.

    Based on Solution-Diffusion model:
    J_w = A * NDP

    Parameters
    ----------
    flux_lmh : float
        Target water flux (L/m²/h)
    A_value : float
        Water permeability coefficient (m/s/Pa)
    temperature_c : float
        Temperature in Celsius

    Returns
    -------
    float
        Required NDP in Pa
    """
    # Convert flux from LMH to m/s
    flux_m_s = flux_lmh / (1000 * 3600)  # L/m²/h to m³/m²/s = m/s

    # Temperature correction factor for A value
    tcf = calculate_temperature_correction_factor(temperature_c)
    A_corrected = A_value * tcf

    # Calculate NDP
    # J_w = A * NDP (density is already included in A value units)
    # NDP = J_w / A
    ndp_pa = flux_m_s / A_corrected

    return ndp_pa


def calculate_osmotic_pressure(
    ion_composition_mg_l: dict,
    temperature_c: float,
    method: str = 'phreeqc'
) -> float:
    """
    Calculate osmotic pressure using PHREEQC or simple correlation.

    Parameters
    ----------
    ion_composition_mg_l : dict
        Ion concentrations (mg/L)
    temperature_c : float
        Temperature in Celsius
    method : str
        'phreeqc' or 'simple'

    Returns
    -------
    float
        Osmotic pressure in Pa
    """
    if method == 'phreeqc':
        try:
            from utils.phreeqc_interface import calculate_osmotic_pressure_phreeqc
            return calculate_osmotic_pressure_phreeqc(
                ion_composition_mg_l,
                temperature_c
            )
        except ImportError:
            logger.warning("PHREEQC not available, using simple correlation")
            method = 'simple'

    if method == 'simple':
        # Simple correlation for osmotic pressure
        # For seawater-like solutions: π (bar) ≈ 0.77 * TDS (g/L)
        # This gives ~0.77 bar for 1 g/L TDS at 25°C
        # Temperature correction: ~2% per 10°C
        total_tds_g_l = sum(ion_composition_mg_l.values()) / 1000  # Convert mg/L to g/L

        # Base osmotic pressure at 25°C
        # Using empirical correlation from literature
        pi_bar_25 = 0.77 * total_tds_g_l

        # Temperature correction (increases with temperature)
        # Based on van't Hoff equation temperature dependence
        temp_factor = (273.15 + temperature_c) / 298.15
        pi_bar = pi_bar_25 * temp_factor

        return pi_bar * 1e5  # Convert bar to Pa


def calculate_water_density(temperature_c: float) -> float:
    """
    Calculate water density as function of temperature.

    Parameters
    ----------
    temperature_c : float
        Temperature in Celsius

    Returns
    -------
    float
        Water density (kg/m³)
    """
    # Polynomial fit for water density
    # Valid for 0-100°C
    t = temperature_c
    rho = 999.84 + 0.065 * t - 0.0085 * t**2 + 0.000035 * t**3
    return rho


def calculate_temperature_correction_factor(temperature_c: float) -> float:
    """
    Calculate temperature correction factor for membrane permeability.

    Based on FilmTec correlation.

    Parameters
    ----------
    temperature_c : float
        Temperature in Celsius

    Returns
    -------
    float
        Temperature correction factor
    """
    # FilmTec correlation: TCF = exp[K * (1/298 - 1/(273+T))]
    # Where K ≈ 2640 for most membranes
    K = 2640
    tcf = math.exp(K * (1/298 - 1/(273.15 + temperature_c)))
    return tcf


def calculate_interstage_pressure_requirements(
    stages_config: list,
    feed_composition_mg_l: dict,
    membrane_properties: dict,
    temperature_c: float = 25
) -> list:
    """
    Calculate pressure requirements for multi-stage system.

    Tracks composition changes through stages and calculates
    required pressure for each stage.

    Parameters
    ----------
    stages_config : list
        List of stage configurations
    feed_composition_mg_l : dict
        System feed composition (mg/L)
    membrane_properties : dict
        Membrane properties
    temperature_c : float
        Operating temperature

    Returns
    -------
    list
        Pressure requirements for each stage
    """
    results = []
    current_feed = feed_composition_mg_l.copy()

    for i, stage_config in enumerate(stages_config):
        # Calculate pressure for this stage
        pressure_result = calculate_required_feed_pressure(
            stage_config,
            current_feed,  # Feed TO THIS STAGE
            membrane_properties,
            temperature_c
        )

        # Add stage number for clarity
        pressure_result['stage_number'] = i + 1
        results.append(pressure_result)

        # Update feed for next stage (current reject becomes next feed)
        _, reject_comp = calculate_stage_permeate_concentration(
            current_feed,
            stage_config['stage_recovery'],
            membrane_properties,
            temperature_c
        )
        current_feed = reject_comp

    return results