"""
Pressure drop calculator for RO stages using literature-validated correlations.

Based on FilmTec Technical Manual equations and industry best practices.
Uses arithmetic average flow per vessel as per standard design practice.
"""

import math
from typing import Dict, Optional


def calculate_stage_pressure_drop(
    feed_flow_m3h: float,
    reject_flow_m3h: float,
    n_vessels: int,
    n_elements_per_vessel: int,
    element_diameter_inch: int = 8,
    spacer_thickness_mil: int = 28
) -> float:
    """
    Calculate pressure drop across an RO stage using average flow.

    Based on FilmTec design equations (Eq. 65-67) and industry correlations.
    Uses arithmetic average flow as per standard practice, NOT log-mean.

    Parameters
    ----------
    feed_flow_m3h : float
        Stage feed flow rate (m³/h)
    reject_flow_m3h : float
        Stage reject/concentrate flow rate (m³/h)
    n_vessels : int
        Number of pressure vessels in parallel
    n_elements_per_vessel : int
        Number of elements in series per vessel
    element_diameter_inch : int
        Element diameter (4 or 8 inches)
    spacer_thickness_mil : int
        Feed spacer thickness in mils (28, 31, or 34 typical)

    Returns
    -------
    float
        Total pressure drop across stage in Pa
    """
    # Calculate arithmetic average flow per vessel
    # This is industry standard practice (FilmTec Manual Table 28)
    avg_flow_per_vessel_m3h = ((feed_flow_m3h + reject_flow_m3h) / 2) / n_vessels

    # Convert to gpm for correlation (US units common in industry)
    avg_flow_gpm = avg_flow_per_vessel_m3h * 4.4028

    # Pressure drop correlation based on element size and spacer
    # From FilmTec Manual and validated against WAVE software
    if element_diameter_inch == 8:
        # 8-inch element correlations
        if spacer_thickness_mil <= 28:
            # High packing density, higher pressure drop
            k_factor = 0.012
            exponent = 1.7
        elif spacer_thickness_mil == 31:
            # Standard spacer
            k_factor = 0.010
            exponent = 1.7
        else:  # 34 mil or thicker
            # Thick spacer for fouling resistance
            k_factor = 0.008
            exponent = 1.65
    else:  # 4-inch elements
        # 4-inch element correlations
        k_factor = 0.020
        exponent = 1.7

    # Calculate pressure drop per element
    # ΔP = k * Q^n where Q is in gpm and ΔP in psi
    dP_per_element_psi = k_factor * (avg_flow_gpm ** exponent)

    # Total pressure drop for all elements in series
    total_dP_psi = dP_per_element_psi * n_elements_per_vessel

    # Convert to Pa
    total_dP_pa = total_dP_psi * 6894.76

    return total_dP_pa


def calculate_element_reynolds_number(
    flow_per_vessel_m3h: float,
    spacer_thickness_mil: int = 28,
    temperature_c: float = 25
) -> float:
    """
    Calculate Reynolds number for flow in feed channel.

    Used to verify flow regime (turbulent vs laminar).

    Parameters
    ----------
    flow_per_vessel_m3h : float
        Flow rate per vessel (m³/h)
    spacer_thickness_mil : int
        Feed spacer thickness in mils
    temperature_c : float
        Temperature in Celsius

    Returns
    -------
    float
        Reynolds number
    """
    # Channel dimensions
    channel_height_m = spacer_thickness_mil * 0.0254 / 1000  # mil to m
    channel_width_m = 1.0  # Standard width assumption

    # Cross-sectional area
    cross_section_m2 = channel_height_m * channel_width_m

    # Velocity
    flow_m3s = flow_per_vessel_m3h / 3600
    velocity_ms = flow_m3s / cross_section_m2

    # Hydraulic diameter (4 * Area / Perimeter)
    # For wide channel: Dh ≈ 2 * channel_height
    hydraulic_diameter_m = 2 * channel_height_m

    # Water properties at temperature
    # Kinematic viscosity correlation
    nu = 1.792e-6 * math.exp(-0.025 * temperature_c)  # m²/s

    # Reynolds number
    Re = velocity_ms * hydraulic_diameter_m / nu

    return Re


def estimate_pressure_drop_simple(
    stage_config: Dict,
    membrane_type: str = 'brackish'
) -> float:
    """
    Simple pressure drop estimation for quick calculations.

    Uses typical values from literature for standard configurations.

    Parameters
    ----------
    stage_config : dict
        Stage configuration with flow and vessel information
    membrane_type : str
        'brackish' or 'seawater'

    Returns
    -------
    float
        Estimated pressure drop in Pa
    """
    # Typical pressure drops from literature
    # Based on 6-7 elements per vessel
    if membrane_type == 'seawater':
        # Higher flows and pressures
        dp_bar_per_stage = 2.0  # 2 bar typical
    else:
        # Brackish water
        if stage_config.get('stage_number', 1) == 1:
            dp_bar_per_stage = 1.0  # 1 bar for first stage
        else:
            dp_bar_per_stage = 0.5  # 0.5 bar for later stages (lower flow)

    return dp_bar_per_stage * 1e5  # Convert to Pa