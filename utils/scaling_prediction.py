"""
Scaling prediction utilities for RO systems.

This module provides scaling prediction capabilities with optional
Reaktoro integration for more accurate thermodynamic calculations.
"""

import logging
from typing import Dict, Optional, Tuple, List
import numpy as np

logger = logging.getLogger(__name__)

# Try to import Reaktoro - optional dependency
try:
    import reaktoro as rkt
    REAKTORO_AVAILABLE = True
except ImportError:
    REAKTORO_AVAILABLE = False
    logger.info("Reaktoro not available - using simplified scaling indices")


# Solubility product constants at 25°C (from literature)
# Values are -log10(Ksp)
SOLUBILITY_PRODUCTS = {
    "CaCO3": 8.48,      # Calcite
    "CaSO4": 4.36,      # Gypsum (CaSO4·2H2O)
    "BaSO4": 9.97,      # Barite
    "SrSO4": 6.63,      # Celestite
    "CaF2": 10.46,      # Fluorite
    "Mg(OH)2": 11.16,   # Brucite
    "SiO2": 2.71,       # Amorphous silica
}

# Ion activity coefficients (simplified Davies equation)
def calculate_activity_coefficient(charge: int, ionic_strength: float) -> float:
    """
    Calculate single ion activity coefficient using Davies equation.
    
    Args:
        charge: Ion charge
        ionic_strength: Solution ionic strength (mol/L)
        
    Returns:
        Activity coefficient
    """
    if ionic_strength == 0:
        return 1.0
    
    A = 0.5  # Davies constant
    z2 = charge ** 2
    sqrt_I = np.sqrt(ionic_strength)
    
    log_gamma = -A * z2 * (sqrt_I / (1 + sqrt_I) - 0.3 * ionic_strength)
    return 10 ** log_gamma


def calculate_saturation_index_simple(
    ion_activities: Dict[str, float],
    mineral: str,
    temperature_c: float = 25.0
) -> float:
    """
    Calculate saturation index using simplified approach.
    
    Args:
        ion_activities: Ion activities in mol/L
        mineral: Mineral name
        temperature_c: Temperature in Celsius
        
    Returns:
        Saturation index (SI = log10(IAP/Ksp))
    """
    # Get Ksp
    if mineral not in SOLUBILITY_PRODUCTS:
        return np.nan
    
    pKsp = SOLUBILITY_PRODUCTS[mineral]
    Ksp = 10 ** (-pKsp)
    
    # Calculate ion activity product (IAP)
    IAP = 1.0
    
    if mineral == "CaCO3":
        IAP = ion_activities.get("Ca2+", 0) * ion_activities.get("CO3-2", 0)
    elif mineral == "CaSO4":
        IAP = ion_activities.get("Ca2+", 0) * ion_activities.get("SO4-2", 0)
    elif mineral == "BaSO4":
        IAP = ion_activities.get("Ba2+", 0) * ion_activities.get("SO4-2", 0)
    elif mineral == "SrSO4":
        IAP = ion_activities.get("Sr2+", 0) * ion_activities.get("SO4-2", 0)
    elif mineral == "CaF2":
        IAP = ion_activities.get("Ca2+", 0) * (ion_activities.get("F-", 0) ** 2)
    elif mineral == "Mg(OH)2":
        IAP = ion_activities.get("Mg2+", 0) * (ion_activities.get("OH-", 0) ** 2)
    elif mineral == "SiO2":
        # Simplified - just use silica concentration
        IAP = ion_activities.get("SiO3-2", 0)
    
    # Temperature correction (van't Hoff equation - simplified)
    if temperature_c != 25.0:
        # Approximate enthalpy of dissolution
        delta_H = {"CaCO3": -12.3, "CaSO4": -4.6}.get(mineral, 0)  # kJ/mol
        if delta_H != 0:
            R = 8.314e-3  # kJ/mol/K
            T = temperature_c + 273.15
            T0 = 298.15
            Ksp *= np.exp(-delta_H / R * (1/T - 1/T0))
    
    # Calculate SI
    if IAP > 0:
        SI = np.log10(IAP / Ksp)
    else:
        SI = -999  # Undersaturated
    
    return SI


def predict_scaling_simple(
    ion_composition_mg_l: Dict[str, float],
    ionic_strength: float,
    temperature_c: float = 25.0,
    ph: float = 7.5
) -> Dict[str, Dict[str, float]]:
    """
    Predict scaling using simplified calculations.
    
    Args:
        ion_composition_mg_l: Ion concentrations in mg/L
        ionic_strength: Ionic strength in mol/L
        temperature_c: Temperature in Celsius
        ph: pH value
        
    Returns:
        Dictionary with scaling predictions
    """
    from .mcas_builder import ION_DATA
    
    # Convert to molar and calculate activities
    ion_activities = {}
    
    for ion, conc_mg_l in ion_composition_mg_l.items():
        if ion in ION_DATA:
            # Convert to mol/L
            mol_l = conc_mg_l / 1000 / ION_DATA[ion]["mw"]
            
            # Calculate activity
            charge = ION_DATA[ion]["charge"]
            gamma = calculate_activity_coefficient(charge, ionic_strength)
            ion_activities[ion] = mol_l * gamma
    
    # Handle pH-dependent species
    # Carbonate equilibrium (simplified)
    if "HCO3-" in ion_activities:
        # CO2 + H2O <-> H2CO3 <-> H+ + HCO3- <-> 2H+ + CO3-2
        # pK1 = 6.35, pK2 = 10.33
        hco3_activity = ion_activities["HCO3-"]
        h_activity = 10 ** (-ph)
        
        # Calculate CO3-2 from HCO3-
        K2 = 10 ** (-10.33)
        co3_activity = K2 * hco3_activity / h_activity
        ion_activities["CO3-2"] = co3_activity
    
    # Calculate OH- from pH
    Kw = 1e-14
    ion_activities["OH-"] = Kw / (10 ** (-ph))
    
    # Calculate saturation indices
    results = {}
    minerals = ["CaCO3", "CaSO4", "BaSO4", "SrSO4", "CaF2", "Mg(OH)2", "SiO2"]
    
    for mineral in minerals:
        SI = calculate_saturation_index_simple(ion_activities, mineral, temperature_c)
        
        results[mineral] = {
            "saturation_index": SI,
            "scaling_tendency": get_scaling_tendency(SI),
            "severity": get_scaling_severity(SI)
        }
    
    return results


def predict_scaling_reaktoro(
    ion_composition_mg_l: Dict[str, float],
    temperature_c: float = 25.0,
    pressure_bar: float = 1.0,
    ph: Optional[float] = None
) -> Dict[str, Dict[str, float]]:
    """
    Predict scaling using Reaktoro for accurate thermodynamics.
    
    Args:
        ion_composition_mg_l: Ion concentrations in mg/L
        temperature_c: Temperature in Celsius
        pressure_bar: Pressure in bar
        ph: Optional pH constraint
        
    Returns:
        Dictionary with scaling predictions
    """
    if not REAKTORO_AVAILABLE:
        raise ImportError("Reaktoro is not installed")
    
    from .mcas_builder import ION_DATA
    
    # Create Reaktoro database
    db = rkt.PhreeqcDatabase("phreeqc.dat")
    
    # Define aqueous phase with relevant elements
    solution = rkt.AqueousPhase(rkt.speciate("H O C Ca Mg Na K Cl S Si F Ba Sr"))
    solution.setActivityModel(rkt.ActivityModelPitzer())
    
    # Define mineral phases to check
    minerals = rkt.MineralPhases([
        "Calcite",      # CaCO3
        "Aragonite",    # CaCO3 (polymorph)
        "Gypsum",       # CaSO4·2H2O
        "Anhydrite",    # CaSO4
        "Barite",       # BaSO4
        "Celestite",    # SrSO4
        "Fluorite",     # CaF2
        "Brucite",      # Mg(OH)2
        "Quartz",       # SiO2 (crystalline)
        "SiO2(am)"      # SiO2 (amorphous)
    ])
    
    # Create chemical system
    system = rkt.ChemicalSystem(db, solution, minerals)
    
    # Create equilibrium solver
    specs = rkt.EquilibriumSpecs(system)
    if ph is not None:
        specs.pH()
    
    conditions = rkt.EquilibriumConditions(specs)
    conditions.temperature(temperature_c + 273.15, "K")
    conditions.pressure(pressure_bar, "bar")
    if ph is not None:
        conditions.pH(ph)
    
    solver = rkt.EquilibriumSolver(specs)
    
    # Set up chemical state
    state = rkt.ChemicalState(system)
    
    # Add ions to the state
    total_mass_kg = 1.0  # 1 kg of water
    
    for ion, conc_mg_l in ion_composition_mg_l.items():
        if ion in ION_DATA:
            # Convert mg/L to mol/kg water
            mol_kg = conc_mg_l / 1000 / ION_DATA[ion]["mw"]
            
            # Map to Reaktoro species names
            reaktoro_species = {
                "Na+": "Na+",
                "Ca2+": "Ca+2",
                "Mg2+": "Mg+2",
                "K+": "K+",
                "Cl-": "Cl-",
                "SO4-2": "SO4-2",
                "HCO3-": "HCO3-",
                "F-": "F-",
                "Ba2+": "Ba+2",
                "Sr2+": "Sr+2",
                "SiO3-2": "H4SiO4"  # Silica species
            }
            
            if ion in reaktoro_species:
                species_name = reaktoro_species[ion]
                try:
                    state.set(species_name, mol_kg * total_mass_kg, "mol")
                except:
                    logger.warning(f"Could not set species {species_name}")
    
    # Add water
    state.set("H2O", total_mass_kg * 1000 / 18.015, "mol")  # ~55.5 mol
    
    # Calculate equilibrium
    result = solver.solve(state, conditions)
    
    if not result.succeeded():
        logger.warning("Reaktoro equilibrium calculation failed")
        return {}
    
    # Extract results
    props = rkt.ChemicalProps(state)
    results = {}
    
    for mineral in minerals.minerals():
        mineral_name = mineral.name()
        
        # Get saturation index
        SI = props.saturationIndex(mineral_name)
        
        # Map Reaktoro names to our standard names
        name_map = {
            "Calcite": "CaCO3",
            "Aragonite": "CaCO3_aragonite",
            "Gypsum": "CaSO4",
            "Anhydrite": "CaSO4_anhydrite",
            "Barite": "BaSO4",
            "Celestite": "SrSO4",
            "Fluorite": "CaF2",
            "Brucite": "Mg(OH)2",
            "Quartz": "SiO2_quartz",
            "SiO2(am)": "SiO2"
        }
        
        standard_name = name_map.get(mineral_name, mineral_name)
        
        results[standard_name] = {
            "saturation_index": SI,
            "scaling_tendency": get_scaling_tendency(SI),
            "severity": get_scaling_severity(SI),
            "saturation_ratio": 10 ** SI
        }
    
    # Add solution properties
    results["solution_properties"] = {
        "pH": props.pH(),
        "ionic_strength": props.ionicStrength(),
        "pe": props.pE(),
        "alkalinity": props.alkalinity()
    }
    
    return results


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
    use_reaktoro: bool = True
) -> Dict[str, Dict[str, float]]:
    """
    Main function to predict scaling potential.
    
    Args:
        ion_composition_mg_l: Ion concentrations in mg/L
        temperature_c: Temperature in Celsius
        pressure_bar: Pressure in bar
        ph: pH value
        ionic_strength: Pre-calculated ionic strength (mol/L)
        use_reaktoro: Whether to use Reaktoro if available
        
    Returns:
        Dictionary with scaling predictions
    """
    if use_reaktoro and REAKTORO_AVAILABLE:
        try:
            return predict_scaling_reaktoro(
                ion_composition_mg_l,
                temperature_c,
                pressure_bar,
                ph
            )
        except Exception as e:
            logger.warning(f"Reaktoro calculation failed: {e}, falling back to simple method")
    
    # Calculate ionic strength if not provided
    if ionic_strength is None:
        from .mcas_builder import calculate_ionic_strength
        ionic_strength = calculate_ionic_strength(ion_composition_mg_l)
    
    return predict_scaling_simple(
        ion_composition_mg_l,
        ionic_strength,
        temperature_c,
        ph
    )


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