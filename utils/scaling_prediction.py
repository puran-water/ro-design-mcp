"""
Scaling prediction utilities for RO systems using PHREEQC.

This module provides accurate scaling prediction using PHREEQC
for thermodynamic calculations.
"""

import logging
from typing import Dict, Optional, Tuple, List
import numpy as np
from .phreeqc_client import PhreeqcROClient

logger = logging.getLogger(__name__)


# Initialize PHREEQC client
phreeqc_client = PhreeqcROClient()


def get_scaling_tendency(SI: float) -> str:
    """
    Interpret saturation index for scaling tendency.
    
    Args:
        SI: Saturation index
        
    Returns:
        Scaling tendency description
    """
    if SI < -0.5:
        return "Undersaturated - No scaling"
    elif -0.5 <= SI < 0:
        return "Near equilibrium - Low scaling risk"
    elif 0 <= SI < 0.5:
        return "Slightly supersaturated - Moderate scaling risk"
    elif 0.5 <= SI < 1.0:
        return "Supersaturated - High scaling risk"
    else:
        return "Highly supersaturated - Severe scaling risk"


def get_scaling_severity(SI: float) -> float:
    """
    Get scaling severity score (0-1).
    
    Args:
        SI: Saturation index
        
    Returns:
        Severity score
    """
    if SI < 0:
        return 0.0
    elif SI < 0.5:
        return SI / 0.5 * 0.5
    elif SI < 1.0:
        return 0.5 + (SI - 0.5) / 0.5 * 0.3
    else:
        return min(0.8 + (SI - 1.0) * 0.1, 1.0)


def predict_scaling(
    ion_composition_mg_l: Dict[str, float],
    temperature_c: float = 25.0,
    pressure_bar: float = 1.0,
    ph: float = 7.5,
    ionic_strength: Optional[float] = None,
    recovery: float = 0.0
) -> Dict[str, Dict[str, float]]:
    """
    Predict scaling potential using PHREEQC.

    Args:
        ion_composition_mg_l: Ion concentrations in mg/L
        temperature_c: Temperature in Celsius
        pressure_bar: Pressure in bar (not used by PHREEQC)
        ph: pH value
        ionic_strength: Pre-calculated ionic strength (mol/L) - not used with PHREEQC
        recovery: Recovery fraction for concentrate calculations (default 0 for feed)

    Returns:
        Dictionary with scaling predictions
    """
    # Use PHREEQC for accurate calculations
    result = phreeqc_client.calculate_scaling_potential(
        feed_composition=ion_composition_mg_l,
        recovery=recovery,
        temperature_c=temperature_c,
        ph=ph
    )

    # Convert to expected format
    formatted = {}
    for mineral, si_value in result.get("saturation_indices", {}).items():
        formatted[mineral] = {
            "saturation_index": si_value,
            "scaling_tendency": get_scaling_tendency(si_value),
            "severity": get_scaling_severity(si_value)
        }

    return formatted


def calculate_sustainable_recovery(
    ion_composition_mg_l: Dict[str, float],
    temperature_c: float = 25.0,
    pressure_bar: float = 1.0,
    ph: float = 7.5,
    with_antiscalant: bool = True
) -> Dict[str, any]:
    """
    Calculate maximum sustainable recovery based on supersaturation limits.

    Args:
        ion_composition_mg_l: Feed water ion concentrations in mg/L
        temperature_c: Temperature in Celsius
        pressure_bar: Pressure in bar
        ph: pH value
        with_antiscalant: Whether antiscalant is used

    Returns:
        Dictionary with sustainable recovery and limiting factors
    """
    # Find maximum recovery using PHREEQC
    result = phreeqc_client.find_maximum_recovery(
        feed_composition=ion_composition_mg_l,
        temperature_c=temperature_c,
        ph=ph,
        use_antiscalant=with_antiscalant
    )

    max_recovery = result["maximum_recovery"]
    limiting_minerals = [result["limiting_factor"]] if result["limiting_factor"] else []

    # Get scaling prediction at max recovery
    concentration_factor = 1 / (1 - max_recovery)
    brine_composition = {
        ion: conc * concentration_factor
        for ion, conc in ion_composition_mg_l.items()
    }

    # Note: We pass the original feed composition with recovery rather than pre-calculated brine
    # This allows PHREEQC to properly calculate the concentrate chemistry
    scaling_results = predict_scaling(
        ion_composition_mg_l,  # Feed composition
        temperature_c,
        pressure_bar,
        ph,
        recovery=max_recovery  # Let PHREEQC calculate concentrate
    )

    return {
        "max_recovery": max_recovery,
        "max_recovery_percent": max_recovery * 100,
        "concentration_factor": concentration_factor,
        "limiting_minerals": limiting_minerals,
        "scaling_at_max_recovery": scaling_results,
        "recommendations": {
            "operating_recovery": max_recovery * 0.95,  # 5% safety margin
            "operating_recovery_percent": max_recovery * 95,
            "safety_margin": 0.05,
            "antiscalant_required": with_antiscalant,
            "monitoring_parameters": [
                "LSI in concentrate",
                "Conductivity trend",
                "Normalized permeate flow",
                "Differential pressure"
            ]
        }
    }


def recommend_antiscalant(
    scaling_results: Dict[str, Dict[str, float]]
) -> Dict[str, any]:
    """
    Recommend antiscalant based on scaling predictions.
    
    Args:
        scaling_results: Output from predict_scaling
        
    Returns:
        Antiscalant recommendations
    """
    recommendations = {
        "primary_concern": None,
        "antiscalant_type": None,
        "dosage_ppm": 0,
        "specific_products": []
    }
    
    # Find primary scaling concern
    max_severity = 0
    primary_mineral = None
    
    for mineral, data in scaling_results.items():
        if "severity" in data and data["severity"] > max_severity:
            max_severity = data["severity"]
            primary_mineral = mineral
    
    if max_severity < 0.3:
        recommendations["antiscalant_type"] = "None required"
        return recommendations
    
    recommendations["primary_concern"] = primary_mineral
    
    # Recommend based on primary concern
    if primary_mineral in ["CaCO3", "CaCO3_aragonite"]:
        recommendations["antiscalant_type"] = "Polyacrylic acid or phosphonate"
        recommendations["dosage_ppm"] = 2 + max_severity * 3
        recommendations["specific_products"] = [
            "Nalco PermaTreat PC-191",
            "SUEZ Hypersperse MDC220",
            "Avista Vitec 3000"
        ]
    
    elif primary_mineral in ["CaSO4", "BaSO4", "SrSO4"]:
        recommendations["antiscalant_type"] = "Phosphonate or polymaleic acid"
        recommendations["dosage_ppm"] = 3 + max_severity * 4
        recommendations["specific_products"] = [
            "Nalco PermaTreat PC-510",
            "SUEZ Hypersperse MDC150",
            "Avista Vitec 4000"
        ]
    
    elif primary_mineral == "CaF2":
        recommendations["antiscalant_type"] = "Specialized fluoride inhibitor"
        recommendations["dosage_ppm"] = 4 + max_severity * 5
        recommendations["specific_products"] = [
            "Nalco PermaTreat PC-1020T",
            "Specialty fluoride antiscalant"
        ]
    
    elif primary_mineral in ["SiO2", "SiO2_quartz"]:
        recommendations["antiscalant_type"] = "Silica dispersant"
        recommendations["dosage_ppm"] = 5 + max_severity * 10
        recommendations["specific_products"] = [
            "Nalco PermaTreat PC-700T",
            "SUEZ Hypersperse SI",
            "Avista Vitec 5000"
        ]
    
    return recommendations