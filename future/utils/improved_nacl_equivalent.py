"""
Improved NaCl equivalent conversion for multi-ion RO simulation.

This module implements charge-balanced conversion using milliequivalents,
multi-ion osmotic pressure calculations, and ion-specific post-processing.
"""

from typing import Dict, Tuple, Optional, Any
import logging
import math

logger = logging.getLogger(__name__)

# Ion properties: (molecular weight, charge)
ION_PROPERTIES = {
    # Cations
    'Na_+': (22.99, 1),
    'Na+': (22.99, 1),
    'K_+': (39.10, 1),
    'K+': (39.10, 1),
    'Ca_2+': (40.08, 2),
    'Ca2+': (40.08, 2),
    'Mg_2+': (24.31, 2),
    'Mg2+': (24.31, 2),
    'Fe_2+': (55.85, 2),
    'Fe2+': (55.85, 2),
    'Fe_3+': (55.85, 3),
    'Fe3+': (55.85, 3),
    'Sr_2+': (87.62, 2),
    'Sr2+': (87.62, 2),
    'Ba_2+': (137.33, 2),
    'Ba2+': (137.33, 2),
    'H_+': (1.01, 1),
    'H+': (1.01, 1),
    'NH4_+': (18.04, 1),
    'NH4+': (18.04, 1),
    
    # Anions
    'Cl_-': (35.45, -1),
    'Cl-': (35.45, -1),
    'SO4_2-': (96.06, -2),
    'SO4-2': (96.06, -2),
    'SO4_-2': (96.06, -2),
    'HCO3_-': (61.02, -1),
    'HCO3-': (61.02, -1),
    'CO3_2-': (60.01, -2),
    'CO3-2': (60.01, -2),
    'CO3_-2': (60.01, -2),
    'NO3_-': (62.00, -1),
    'NO3-': (62.00, -1),
    'PO4_3-': (94.97, -3),
    'PO4-3': (94.97, -3),
    'PO4_-3': (94.97, -3),
    'F_-': (19.00, -1),
    'F-': (19.00, -1),
    'Br_-': (79.90, -1),
    'Br-': (79.90, -1),
    'OH_-': (17.01, -1),
    'OH-': (17.01, -1),
}


def mg_to_meq(conc_mg_L: float, ion: str) -> float:
    """
    Convert concentration from mg/L to meq/L.
    
    Args:
        conc_mg_L: Concentration in mg/L
        ion: Ion name (must be in ION_PROPERTIES)
        
    Returns:
        Concentration in meq/L
    """
    if ion not in ION_PROPERTIES:
        # Default to Na+ if unknown (shouldn't happen)
        logger.warning(f"Ion {ion} not in properties database, using Na+ properties")
        mw, charge = ION_PROPERTIES['Na_+']
    else:
        mw, charge = ION_PROPERTIES[ion]
    
    return conc_mg_L * abs(charge) / mw


def meq_to_mg(conc_meq_L: float, ion: str) -> float:
    """
    Convert concentration from meq/L to mg/L.
    
    Args:
        conc_meq_L: Concentration in meq/L
        ion: Ion name (must be in ION_PROPERTIES)
        
    Returns:
        Concentration in mg/L
    """
    if ion not in ION_PROPERTIES:
        logger.warning(f"Ion {ion} not in properties database, using Na+ properties")
        mw, charge = ION_PROPERTIES['Na_+']
    else:
        mw, charge = ION_PROPERTIES[ion]
    
    return conc_meq_L * mw / abs(charge)


def convert_to_nacl_equivalent_meq(
    ion_composition: Dict[str, float]
) -> Tuple[Dict[str, float], float, float]:
    """
    Convert multi-ion composition to charge-balanced NaCl equivalent.
    
    This uses milliequivalents to ensure proper charge balance.
    
    Args:
        ion_composition: Ion concentrations in mg/L
        
    Returns:
        Tuple of (nacl_composition, total_cation_meq, total_anion_meq)
        - nacl_composition: {'Na_+': mg/L, 'Cl_-': mg/L}
        - total_cation_meq: Total cation milliequivalents
        - total_anion_meq: Total anion milliequivalents (absolute value)
    """
    # Calculate total cation and anion equivalents
    total_cation_meq = 0.0
    total_anion_meq = 0.0
    
    for ion, conc_mg_L in ion_composition.items():
        meq = mg_to_meq(conc_mg_L, ion)
        
        # Determine if cation or anion
        if ion in ION_PROPERTIES:
            charge = ION_PROPERTIES[ion][1]
            if charge > 0:
                total_cation_meq += meq
            else:
                total_anion_meq += meq  # Already positive from abs() in mg_to_meq
    
    # Balance and convert to NaCl
    avg_meq = (total_cation_meq + total_anion_meq) / 2
    
    # Convert back to mg/L
    na_conc = meq_to_mg(avg_meq, 'Na_+')
    cl_conc = meq_to_mg(avg_meq, 'Cl_-')
    
    nacl_composition = {
        'Na_+': na_conc,
        'Cl_-': cl_conc
    }
    
    logger.info(f"Charge-balanced conversion:")
    logger.info(f"  Total cations: {total_cation_meq:.1f} meq/L")
    logger.info(f"  Total anions: {total_anion_meq:.1f} meq/L")
    logger.info(f"  Balanced at: {avg_meq:.1f} meq/L")
    logger.info(f"  NaCl equivalent: {na_conc + cl_conc:.0f} mg/L")
    
    return nacl_composition, total_cation_meq, total_anion_meq


def calculate_multi_ion_osmotic_pressure(
    ion_composition: Dict[str, float],
    temperature_k: float = 298.15
) -> float:
    """
    Calculate osmotic pressure for multi-ion solution.
    
    Uses van't Hoff equation with sum of all ion molar concentrations.
    
    Args:
        ion_composition: Ion concentrations in mg/L
        temperature_k: Temperature in Kelvin
        
    Returns:
        Osmotic pressure in Pa
    """
    R = 8.314  # J/mol/K
    
    # Calculate total molar concentration
    total_molar = 0.0
    
    for ion, conc_mg_L in ion_composition.items():
        if ion in ION_PROPERTIES:
            mw = ION_PROPERTIES[ion][0]
            # Convert mg/L to mol/L
            molar_conc = (conc_mg_L / 1000) / mw  # g/L / (g/mol) = mol/L
            total_molar += molar_conc
    
    # π = R * T * ΣC_i
    osmotic_pressure_pa = R * temperature_k * total_molar * 1000  # Convert to Pa
    
    # Convert to bar for logging
    osmotic_pressure_bar = osmotic_pressure_pa / 1e5
    
    logger.info(f"Multi-ion osmotic pressure: {osmotic_pressure_bar:.2f} bar")
    
    return osmotic_pressure_pa


def calculate_nacl_osmotic_pressure(
    nacl_composition: Dict[str, float],
    temperature_k: float = 298.15
) -> float:
    """
    Calculate osmotic pressure for NaCl solution.
    
    Uses van't Hoff equation with activity coefficient correction.
    
    Args:
        nacl_composition: {'Na_+': mg/L, 'Cl_-': mg/L}
        temperature_k: Temperature in Kelvin
        
    Returns:
        Osmotic pressure in Pa
    """
    R = 8.314  # J/mol/K
    
    # Get total NaCl concentration
    na_conc = nacl_composition.get('Na_+', 0)
    cl_conc = nacl_composition.get('Cl_-', 0)
    
    # Convert to molality (approximation)
    mw_nacl = 58.44
    nacl_g_L = (na_conc + cl_conc) / 1000  # g/L
    molality = nacl_g_L / mw_nacl  # mol/L ≈ mol/kg for dilute solutions
    
    # Simple osmotic coefficient correlation for NaCl
    # φ ≈ 0.93 for typical brackish water concentrations
    phi = 0.93
    
    # π = 2 * φ * m * ρ_w * R * T (for NaCl which dissociates into 2 ions)
    rho_w = 997  # kg/m³
    osmotic_pressure_pa = 2 * phi * molality * rho_w * R * temperature_k
    
    # Convert to bar for logging
    osmotic_pressure_bar = osmotic_pressure_pa / 1e5
    
    logger.info(f"NaCl equivalent osmotic pressure: {osmotic_pressure_bar:.2f} bar")
    
    return osmotic_pressure_pa


def post_process_multi_ion_results(
    nacl_results: Dict[str, Any],
    original_composition: Dict[str, float],
    b_comp_values: Optional[Dict[str, float]] = None,
    membrane_type: str = "brackish"
) -> Dict[str, Dict[str, float]]:
    """
    Post-process NaCl simulation results to estimate individual ion concentrations.
    
    Args:
        nacl_results: Results from NaCl equivalent simulation
        original_composition: Original multi-ion feed composition (mg/L)
        b_comp_values: Optional ion-specific B values. If None, uses defaults.
        membrane_type: Type of membrane for default B values
        
    Returns:
        Dictionary with:
        - 'permeate': Ion concentrations in permeate (mg/L)
        - 'retentate': Ion concentrations in retentate (mg/L)
        - 'rejection': Ion-specific rejection fractions
    """
    # Get NaCl rejection from simulation
    if 'salt_rejection' in nacl_results.get('performance', {}):
        r_nacl = nacl_results['performance']['salt_rejection']
    else:
        # Try to calculate from stage results
        stage_results = nacl_results.get('stage_results', [])
        if stage_results and 'rejection' in stage_results[0]:
            r_nacl = stage_results[0]['rejection']
        else:
            logger.warning("Could not find salt rejection in results, using 0.95")
            r_nacl = 0.95
    
    # Get recovery
    if 'system_recovery' in nacl_results.get('performance', {}):
        recovery = nacl_results['performance']['system_recovery']
    else:
        logger.warning("Could not find system recovery in results, using 0.5")
        recovery = 0.5
    
    # Set up B_comp values if not provided
    if b_comp_values is None:
        # Use defaults based on membrane type
        if membrane_type == "seawater":
            b_nacl = 1.0e-8  # m/s
            b_comp_values = {
                'Na_+': b_nacl,
                'Na+': b_nacl,
                'Cl_-': b_nacl,
                'Cl-': b_nacl,
                'K_+': b_nacl,
                'K+': b_nacl,
                'Ca_2+': 0.5e-8,
                'Ca2+': 0.5e-8,
                'Mg_2+': 0.5e-8,
                'Mg2+': 0.5e-8,
                'SO4_2-': 0.5e-8,
                'SO4-2': 0.5e-8,
                'SO4_-2': 0.5e-8,
                'HCO3_-': 0.8e-8,
                'HCO3-': 0.8e-8,
            }
        else:  # brackish
            b_nacl = 5.58e-8  # m/s
            b_comp_values = {
                'Na_+': b_nacl,
                'Na+': b_nacl,
                'Cl_-': b_nacl,
                'Cl-': b_nacl,
                'K_+': b_nacl,
                'K+': b_nacl,
                'Ca_2+': b_nacl * 0.4,
                'Ca2+': b_nacl * 0.4,
                'Mg_2+': b_nacl * 0.4,
                'Mg2+': b_nacl * 0.4,
                'SO4_2-': b_nacl * 0.4,
                'SO4-2': b_nacl * 0.4,
                'SO4_-2': b_nacl * 0.4,
                'HCO3_-': b_nacl * 0.7,
                'HCO3-': b_nacl * 0.7,
            }
    
    # Calculate individual ion rejections
    rejections = {}
    permeate_conc = {}
    retentate_conc = {}
    
    # Get reference B value (use Na+ or first available)
    b_ref = b_comp_values.get('Na_+', b_comp_values.get('Na+', 5.58e-8))
    
    # Calculate feed mass flows
    total_feed_mass = sum(original_composition.values())
    
    for ion, feed_conc in original_composition.items():
        # Get B value for this ion
        if ion in b_comp_values:
            b_ion = b_comp_values[ion]
        else:
            # Default based on charge
            if ion in ION_PROPERTIES:
                charge = abs(ION_PROPERTIES[ion][1])
                if charge == 1:
                    b_ion = b_ref
                elif charge >= 2:
                    b_ion = b_ref * 0.4  # Better rejection for multivalent
                else:
                    b_ion = b_ref * 0.7
            else:
                b_ion = b_ref
        
        # Calculate rejection using B ratio
        # R_i = 1 - B_i/B_ref * (1 - R_NaCl)
        b_ratio = b_ion / b_ref
        r_ion = 1 - b_ratio * (1 - r_nacl)
        
        # Ensure rejection is in valid range
        r_ion = max(0, min(0.999, r_ion))
        rejections[ion] = r_ion
        
        # Calculate permeate concentration
        # C_p,i = C_f,i * (1 - R_i)
        permeate_conc[ion] = feed_conc * (1 - r_ion)
        
        # Calculate retentate concentration using mass balance
        # Mass in = Mass out (permeate + retentate)
        # C_r,i = (C_f,i - recovery * C_p,i) / (1 - recovery)
        if recovery < 0.999:
            retentate_conc[ion] = (feed_conc - recovery * permeate_conc[ion]) / (1 - recovery)
        else:
            retentate_conc[ion] = feed_conc  # Edge case
    
    # Check and enforce electroneutrality in permeate
    permeate_conc = _enforce_electroneutrality(permeate_conc)
    
    # Log results
    logger.info(f"Ion-specific rejections (NaCl base: {r_nacl:.1%}):")
    for ion, r in rejections.items():
        logger.info(f"  {ion}: {r:.1%}")
    
    return {
        'permeate': permeate_conc,
        'retentate': retentate_conc,
        'rejection': rejections
    }


def _enforce_electroneutrality(
    ion_composition: Dict[str, float],
    tolerance: float = 0.01
) -> Dict[str, float]:
    """
    Adjust ion concentrations to enforce electroneutrality.
    
    Args:
        ion_composition: Ion concentrations in mg/L
        tolerance: Acceptable charge imbalance fraction
        
    Returns:
        Adjusted ion composition
    """
    # Calculate current charge balance
    total_positive_meq = 0.0
    total_negative_meq = 0.0
    
    for ion, conc in ion_composition.items():
        if ion in ION_PROPERTIES:
            meq = mg_to_meq(conc, ion)
            charge = ION_PROPERTIES[ion][1]
            if charge > 0:
                total_positive_meq += meq
            else:
                total_negative_meq += meq
    
    # Check if adjustment needed
    imbalance = (total_positive_meq - total_negative_meq) / (total_positive_meq + total_negative_meq)
    
    if abs(imbalance) < tolerance:
        return ion_composition  # Already balanced
    
    # Adjust by scaling the dominant charge
    adjusted = ion_composition.copy()
    
    if total_positive_meq > total_negative_meq:
        # Too many cations, scale them down
        scale_factor = total_negative_meq / total_positive_meq
        for ion, conc in ion_composition.items():
            if ion in ION_PROPERTIES and ION_PROPERTIES[ion][1] > 0:
                adjusted[ion] = conc * scale_factor
    else:
        # Too many anions, scale them down
        scale_factor = total_positive_meq / total_negative_meq
        for ion, conc in ion_composition.items():
            if ion in ION_PROPERTIES and ION_PROPERTIES[ion][1] < 0:
                adjusted[ion] = conc * scale_factor
    
    logger.debug(f"Enforced electroneutrality (imbalance: {imbalance:.3f})")
    
    return adjusted