"""
Membrane properties handler for RO simulations.

This module provides functions to handle membrane properties from different sources:
- Specific membrane models from catalog (e.g., 'BW30_PRO_400', 'SW30HRLE_440')
- Generic types ('brackish', 'seawater') for backward compatibility
- Custom properties passed directly
"""

from typing import Dict, Optional, Tuple, List
import logging
import yaml
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)


def get_membrane_properties(
    membrane_type: str = 'brackish',
    membrane_properties: Optional[Dict[str, float]] = None,
    config_path: Optional[str] = None
) -> Tuple[float, float]:
    """
    Get membrane permeability coefficients (A_w and B_s).
    
    Args:
        membrane_type: Type/model of membrane (e.g., 'brackish', 'seawater', 'bw30_400')
        membrane_properties: Optional dict with 'A_w' and 'B_s' to override defaults
        config_path: Optional path to config file (defaults to system_defaults.yaml)
        
    Returns:
        Tuple of (A_w, B_s) values in SI units (m/s/Pa and m/s)
    """
    # If custom properties provided, use them
    if membrane_properties and 'A_w' in membrane_properties and 'B_s' in membrane_properties:
        logger.info(f"Using custom membrane properties: A_w={membrane_properties['A_w']:.2e}, B_s={membrane_properties['B_s']:.2e}")
        return membrane_properties['A_w'], membrane_properties['B_s']
    
    # Otherwise, get from configuration
    try:
        from utils.config import get_config
        
        # Try to get specific membrane model first
        membrane_config = get_config(f'membrane_properties.{membrane_type}')
        
        if membrane_config:
            A_w = membrane_config.get('A_w')
            B_s = membrane_config.get('B_s')
            if A_w and B_s:
                logger.info(f"Using {membrane_type} membrane properties from config: A_w={A_w:.2e}, B_s={B_s:.2e}")
                return A_w, B_s
        
        # Fallback to defaults based on generic type
        if 'sea' in membrane_type.lower():
            # Default seawater values
            A_w = 3.0e-12  # m/s/Pa
            B_s = 1.5e-8   # m/s
            logger.warning(f"Using default seawater membrane properties")
        else:
            # Default brackish values (BW30-400)
            A_w = 9.63e-12  # m/s/Pa
            B_s = 5.58e-8   # m/s
            logger.warning(f"Using default brackish water membrane properties")
            
        return A_w, B_s
        
    except ImportError:
        # If config module not available, use hardcoded defaults
        logger.warning("Config module not available, using hardcoded defaults")
        
        defaults = {
            'bw30_400': (9.63e-12, 5.58e-8),
            'eco_pro_400': (1.60e-11, 4.24e-8),
            'cr100_pro_400': (1.06e-11, 4.16e-8),
            'brackish': (9.63e-12, 5.58e-8),
            'seawater': (3.0e-12, 1.5e-8),
        }
        
        if membrane_type in defaults:
            A_w, B_s = defaults[membrane_type]
            logger.info(f"Using {membrane_type} defaults: A_w={A_w:.2e}, B_s={B_s:.2e}")
            return A_w, B_s
        else:
            # Ultimate fallback
            A_w, B_s = 9.63e-12, 5.58e-8  # BW30-400 values
            logger.warning(f"Unknown membrane type '{membrane_type}', using BW30-400 defaults")
            return A_w, B_s


def get_membrane_properties_mcas(
    membrane_type: str = 'brackish',
    membrane_properties: Optional[Dict[str, float]] = None,
    solute_list: list = None
) -> Dict[str, Dict[str, float]]:
    """
    Get membrane permeability coefficients for MCAS multi-component simulations.
    
    For MCAS, we need B values for each ion species separately.
    
    Args:
        membrane_type: Type/model of membrane
        membrane_properties: Optional dict with 'A_w' and ion-specific B values
        solute_list: List of solute species in the simulation
        
    Returns:
        Dict with 'A_w' and 'B_comp' (dict of B values by component)
    """
    # Get base A_w value
    A_w, B_s_default = get_membrane_properties(membrane_type, membrane_properties)
    
    # If custom properties provided with ion-specific B values
    if membrane_properties and 'B_comp' in membrane_properties:
        return {
            'A_w': membrane_properties.get('A_w', A_w),
            'B_comp': membrane_properties['B_comp']
        }
    
    # Otherwise, use heuristics for ion-specific B values
    B_comp = {}
    
    if not solute_list:
        # Default for NaCl only
        return {'A_w': A_w, 'B_comp': {'Na_+': B_s_default, 'Cl_-': B_s_default}}
    
    # Set B values based on ion type and membrane type
    for ion in solute_list:
        if membrane_type == 'seawater' or 'sea' in membrane_type.lower():
            # Seawater membranes - tighter, lower B values
            if ion in ['Na_+', 'Cl_-', 'Na+', 'Cl-']:
                B_comp[ion] = 1.0e-8  # m/s
            elif ion in ['Ca_2+', 'Mg_2+', 'SO4_2-', 'Ca2+', 'Mg2+', 'SO4-2']:
                B_comp[ion] = 5.0e-9  # m/s - higher rejection for divalent
            else:
                B_comp[ion] = 8.0e-9  # m/s - default
        else:
            # Brackish water membranes - looser, higher B values
            if ion in ['Na_+', 'Cl_-', 'Na+', 'Cl-']:
                B_comp[ion] = B_s_default  # Use default from config
            elif ion in ['Ca_2+', 'Mg_2+', 'SO4_2-', 'Ca2+', 'Mg2+', 'SO4-2']:
                B_comp[ion] = B_s_default * 0.4  # Better rejection for divalent
            else:
                B_comp[ion] = B_s_default * 0.7  # Moderate rejection
    
    logger.info(f"Generated ion-specific B values for {membrane_type}: {B_comp}")
    
    return {'A_w': A_w, 'B_comp': B_comp}


def load_membrane_catalog() -> Dict:
    """Load the membrane catalog from YAML file."""
    catalog_path = Path(__file__).parent.parent / 'config' / 'membrane_catalog.yaml'

    if not catalog_path.exists():
        logger.warning(f"Membrane catalog not found at {catalog_path}")
        return {}

    with open(catalog_path, 'r') as f:
        data = yaml.safe_load(f)

    return data.get('membrane_catalog', {})


def load_spacer_profiles() -> Dict:
    """Load spacer profiles from YAML file."""
    profiles_path = Path(__file__).parent.parent / 'config' / 'spacer_profiles.yaml'

    if not profiles_path.exists():
        logger.warning(f"Spacer profiles not found at {profiles_path}")
        return {}

    with open(profiles_path, 'r') as f:
        data = yaml.safe_load(f)

    return data.get('spacer_profiles', {})


def get_membrane_from_catalog(
    membrane_model: str,
    solute_list: Optional[List[str]] = None,
    temperature_K: float = 298.15
) -> Dict:
    """
    Get membrane properties from catalog with temperature correction.

    Args:
        membrane_model: Specific membrane model name (e.g., 'BW30_PRO_400')
        solute_list: List of solutes for which to get B values
        temperature_K: Operating temperature in Kelvin

    Returns:
        Dict with A_w, B_comp, and physical properties
    """
    catalog = load_membrane_catalog()
    spacer_profiles = load_spacer_profiles()

    # Normalize model name (handle variations)
    model_key = membrane_model.replace('-', '_').replace(' ', '_')

    if model_key not in catalog:
        # Try without spaces/hyphens
        for key in catalog.keys():
            if key.lower() == model_key.lower():
                model_key = key
                break
        else:
            logger.warning(f"Membrane model '{membrane_model}' not found in catalog")
            # Fall back to generic type
            if 'SW' in membrane_model.upper():
                return get_membrane_properties_mcas('seawater', None, solute_list)
            else:
                return get_membrane_properties_mcas('brackish', None, solute_list)

    membrane = catalog[model_key]

    # Get spacer properties
    spacer = spacer_profiles.get(membrane.get('spacer_profile', 'default'),
                                  spacer_profiles.get('default', {}))

    # Temperature correction using Arrhenius equation
    R = 8.314  # J/mol/K
    T_ref = membrane.get('temperature_corrections', {}).get('reference_temperature', 298.15)

    # Apply temperature correction to A_w
    E_a_A = membrane.get('temperature_corrections', {}).get('A_w_activation_energy', 20000)
    A_w_corrected = membrane['A_w'] * np.exp(
        -E_a_A / R * (1/temperature_K - 1/T_ref)
    )

    # Apply temperature correction to B values
    E_a_B = membrane.get('temperature_corrections', {}).get('B_activation_energy', 13000)
    B_comp_corrected = {}

    # If solute list provided, filter B values
    if solute_list:
        for solute in solute_list:
            # Normalize ion names (handle Na+ vs Na_+)
            ion_key = solute.replace('+', '_+').replace('-', '_-')
            if ion_key in membrane['B_comp']:
                B_comp_corrected[solute] = membrane['B_comp'][ion_key] * np.exp(
                    -E_a_B / R * (1/temperature_K - 1/T_ref)
                )
            else:
                # Use Na+ as default for unknown ions
                logger.warning(f"Ion {solute} not in membrane data, using Na+ value")
                B_comp_corrected[solute] = membrane['B_comp'].get('Na_+', 5e-8) * np.exp(
                    -E_a_B / R * (1/temperature_K - 1/T_ref)
                )
    else:
        # Return all B values with temperature correction
        for ion, B_val in membrane['B_comp'].items():
            B_comp_corrected[ion] = B_val * np.exp(
                -E_a_B / R * (1/temperature_K - 1/T_ref)
            )

    return {
        'A_w': A_w_corrected,
        'B_comp': B_comp_corrected,
        'channel_height': spacer.get('channel_height', 7.9e-4),
        'spacer_porosity': spacer.get('spacer_porosity', 0.85),
        'friction_factor': spacer.get('friction_factor', 6.8),
        'active_area_m2': membrane['physical']['active_area_m2'],
        'element_type': membrane['physical']['element_type'],
        'family': membrane.get('family', 'brackish'),
        'limits': membrane.get('limits', {}),
    }


def get_membrane_properties_enhanced(
    membrane_model: Optional[str] = None,
    membrane_type: Optional[str] = None,
    solute_list: Optional[List[str]] = None,
    temperature_K: float = 298.15,
    custom_properties: Optional[Dict] = None
) -> Dict:
    """
    Enhanced membrane properties handler that supports both catalog models and generic types.

    Args:
        membrane_model: Specific model from catalog (e.g., 'BW30_PRO_400')
        membrane_type: Generic type for backward compatibility ('brackish', 'seawater')
        solute_list: List of solutes
        temperature_K: Operating temperature
        custom_properties: Override properties

    Returns:
        Complete membrane properties dictionary
    """
    # Priority: custom_properties > membrane_model > membrane_type

    if custom_properties and 'A_w' in custom_properties and 'B_comp' in custom_properties:
        logger.info("Using custom membrane properties")
        return custom_properties

    if membrane_model:
        logger.info(f"Loading membrane model '{membrane_model}' from catalog")
        return get_membrane_from_catalog(membrane_model, solute_list, temperature_K)

    if membrane_type:
        logger.info(f"Using generic membrane type '{membrane_type}'")
        return get_membrane_properties_mcas(membrane_type, custom_properties, solute_list)

    # Default fallback
    logger.warning("No membrane specified, using default brackish properties")
    return get_membrane_properties_mcas('brackish', None, solute_list)