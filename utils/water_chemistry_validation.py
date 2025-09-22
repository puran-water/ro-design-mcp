"""
Water chemistry validation utilities for RO system design.

Provides consistent validation and parsing of ion composition data
across all tools to ensure DRY principle compliance.
"""

import json
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Valid ions and their properties
VALID_IONS = {
    # Cations
    "Na+": {"charge": 1, "mw": 22.99, "name": "Sodium"},
    "Ca2+": {"charge": 2, "mw": 40.08, "name": "Calcium"},
    "Mg2+": {"charge": 2, "mw": 24.31, "name": "Magnesium"},
    "K+": {"charge": 1, "mw": 39.10, "name": "Potassium"},
    "Fe2+": {"charge": 2, "mw": 55.85, "name": "Iron(II)"},
    "Fe3+": {"charge": 3, "mw": 55.85, "name": "Iron(III)"},
    "Mn2+": {"charge": 2, "mw": 54.94, "name": "Manganese"},
    "Ba2+": {"charge": 2, "mw": 137.33, "name": "Barium"},
    "Sr2+": {"charge": 2, "mw": 87.62, "name": "Strontium"},
    "NH4+": {"charge": 1, "mw": 18.04, "name": "Ammonium"},
    "H+": {"charge": 1, "mw": 1.01, "name": "Hydrogen"},

    # Anions
    "Cl-": {"charge": -1, "mw": 35.45, "name": "Chloride"},
    "SO4-2": {"charge": -2, "mw": 96.06, "name": "Sulfate"},
    "HCO3-": {"charge": -1, "mw": 61.02, "name": "Bicarbonate"},
    "CO3-2": {"charge": -2, "mw": 60.01, "name": "Carbonate"},
    "NO3-": {"charge": -1, "mw": 62.00, "name": "Nitrate"},
    "F-": {"charge": -1, "mw": 19.00, "name": "Fluoride"},
    "PO4-3": {"charge": -3, "mw": 94.97, "name": "Phosphate"},
    "SiO3-2": {"charge": -2, "mw": 76.08, "name": "Silicate"},
    "OH-": {"charge": -1, "mw": 17.01, "name": "Hydroxide"},
    "Br-": {"charge": -1, "mw": 79.90, "name": "Bromide"},
    "B(OH)4-": {"charge": -1, "mw": 78.84, "name": "Borate"},
}

# Common water type templates for reference
WATER_TEMPLATES = {
    "seawater": {
        "Na+": 10770, "Mg2+": 1290, "Ca2+": 412, "K+": 399,
        "Sr2+": 7.9, "Cl-": 19350, "SO4-2": 2712, "HCO3-": 142,
        "Br-": 67, "B(OH)4-": 4.5, "F-": 1.3
    },
    "brackish": {
        "Na+": 1000, "Ca2+": 100, "Mg2+": 50, "K+": 20,
        "Cl-": 1500, "SO4-2": 200, "HCO3-": 200
    },
    "municipal": {
        "Na+": 50, "Ca2+": 40, "Mg2+": 10, "K+": 5,
        "Cl-": 60, "SO4-2": 30, "HCO3-": 120, "NO3-": 10
    }
}


def parse_and_validate_ion_composition(
    ion_composition_json: str,
    allow_missing_ions: bool = True
) -> Dict[str, float]:
    """
    Parse and validate ion composition from JSON string.

    Args:
        ion_composition_json: JSON string of ion concentrations in mg/L
        allow_missing_ions: Whether to allow ions not in VALID_IONS list

    Returns:
        Validated dictionary of ion concentrations in mg/L

    Raises:
        ValueError: If JSON is invalid or concentrations are invalid
    """
    # Parse JSON
    try:
        ion_dict = json.loads(ion_composition_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format for ion composition: {str(e)}")

    if not isinstance(ion_dict, dict):
        raise ValueError("Ion composition must be a JSON object/dictionary")

    # Validate each ion
    validated = {}
    for ion, concentration in ion_dict.items():
        # Check if ion is recognized
        if ion not in VALID_IONS and not allow_missing_ions:
            raise ValueError(f"Unknown ion: {ion}. Valid ions: {', '.join(VALID_IONS.keys())}")

        # Validate concentration
        if not isinstance(concentration, (int, float)):
            raise ValueError(f"Concentration for {ion} must be a number, got: {type(concentration).__name__}")

        if concentration < 0:
            raise ValueError(f"Concentration for {ion} cannot be negative: {concentration}")

        if concentration > 100000:  # 100 g/L sanity check
            logger.warning(f"Very high concentration for {ion}: {concentration} mg/L")

        validated[ion] = float(concentration)

    # Check for minimum required ions
    if not validated:
        raise ValueError("Ion composition cannot be empty")

    # Log charge balance warning if significantly imbalanced
    charge_balance = calculate_charge_balance(validated)
    if abs(charge_balance) > 5:  # 5% imbalance
        logger.warning(f"Significant charge imbalance detected: {charge_balance:.1f}%")

    return validated


def calculate_charge_balance(ion_dict: Dict[str, float]) -> float:
    """
    Calculate charge balance for ion composition.

    Args:
        ion_dict: Dictionary of ion concentrations in mg/L

    Returns:
        Charge balance percentage (positive = excess cations)
    """
    cation_meq = 0
    anion_meq = 0

    for ion, conc_mg_l in ion_dict.items():
        if ion in VALID_IONS:
            ion_data = VALID_IONS[ion]
            meq_l = conc_mg_l / ion_data["mw"] * abs(ion_data["charge"])

            if ion_data["charge"] > 0:
                cation_meq += meq_l
            else:
                anion_meq += meq_l

    total_meq = cation_meq + anion_meq
    if total_meq == 0:
        return 0

    return (cation_meq - anion_meq) / total_meq * 100


def validate_water_chemistry_params(
    temperature_c: float,
    ph: float
) -> Tuple[float, float]:
    """
    Validate temperature and pH parameters.

    Args:
        temperature_c: Temperature in Celsius
        ph: pH value

    Returns:
        Validated (temperature, pH) tuple

    Raises:
        ValueError: If parameters are out of range
    """
    # Validate temperature
    if not 0 < temperature_c < 100:
        raise ValueError(f"Temperature {temperature_c}°C is outside reasonable range (0-100°C)")

    if temperature_c > 45:
        logger.warning(f"High temperature {temperature_c}°C may damage membranes")

    # Validate pH
    if not 2 <= ph <= 12:
        raise ValueError(f"pH {ph} is outside reasonable range (2-12)")

    if ph < 4 or ph > 10:
        logger.warning(f"Extreme pH {ph} may require special membrane selection")

    return temperature_c, ph


def estimate_tds_from_ions(ion_dict: Dict[str, float]) -> float:
    """
    Estimate TDS from ion composition.

    Args:
        ion_dict: Dictionary of ion concentrations in mg/L

    Returns:
        Estimated TDS in mg/L
    """
    # Sum all ion concentrations
    tds = sum(ion_dict.values())

    # Add estimated uncharged species (typically 5-10% for natural waters)
    tds *= 1.05

    return tds


def create_feed_water_chemistry(
    ion_composition_mg_l: Dict[str, float],
    temperature_c: float = 25.0,
    ph: float = 7.5,
    sustainable_recovery: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Create standardized feed water chemistry dictionary.

    This creates a consistent structure for water chemistry data
    that can be passed between tools.

    Args:
        ion_composition_mg_l: Validated ion concentrations
        temperature_c: Temperature in Celsius
        ph: pH value
        sustainable_recovery: Optional sustainable recovery calculation results

    Returns:
        Standardized water chemistry dictionary
    """
    return {
        "ion_composition_mg_l": ion_composition_mg_l,
        "temperature_c": temperature_c,
        "ph": ph,
        "estimated_tds_mg_l": estimate_tds_from_ions(ion_composition_mg_l),
        "charge_balance_percent": calculate_charge_balance(ion_composition_mg_l),
        "sustainable_recovery": sustainable_recovery
    }


def extract_water_chemistry_from_config(
    configuration: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Extract water chemistry data from configuration if present.

    Args:
        configuration: Configuration dictionary from optimize_ro_configuration

    Returns:
        Water chemistry dictionary if present, None otherwise
    """
    return configuration.get("feed_water_chemistry", None)