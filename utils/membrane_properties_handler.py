"""
Membrane properties handler for RO simulations.

This module provides functions to handle membrane properties from different sources:
- Specific membrane models (e.g., 'bw30_400', 'eco_pro_400')
- Generic types ('brackish', 'seawater')
- Custom properties passed directly
"""

from typing import Dict, Optional, Tuple
import logging

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