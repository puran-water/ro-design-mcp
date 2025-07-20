"""
Trace ion handling utilities for RO simulations.

This module provides functions to handle trace ions that would otherwise
cause FBBT errors due to recovery bounds in WaterTAP RO models.
"""

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


def categorize_ions_by_concentration(
    ion_composition: Dict[str, float],
    trace_threshold_mg_l: float = 10.0
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Categorize ions into major and trace based on concentration.
    
    Args:
        ion_composition: Ion concentrations in mg/L
        trace_threshold_mg_l: Threshold below which ions are considered trace
        
    Returns:
        Tuple of (major_ions, trace_ions) dictionaries
    """
    major_ions = {}
    trace_ions = {}
    
    for ion, conc in ion_composition.items():
        if conc < trace_threshold_mg_l:
            trace_ions[ion] = conc
        else:
            major_ions[ion] = conc
    
    return major_ions, trace_ions


def create_lumped_trace_composition(
    ion_composition: Dict[str, float],
    trace_threshold_mg_l: float = 10.0,
    min_lumped_concentration: float = 50.0
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Create a lumped composition where trace ions are grouped.
    
    This avoids FBBT errors by ensuring all components have sufficient
    concentration for WaterTAP's recovery bounds.
    
    Args:
        ion_composition: Original ion concentrations in mg/L
        trace_threshold_mg_l: Threshold for trace classification
        min_lumped_concentration: Minimum concentration for lumped component
        
    Returns:
        Tuple of (simulation_composition, trace_mapping)
        - simulation_composition: Modified composition for simulation
        - trace_mapping: Mapping of original trace ions to lumped component
    """
    major_ions, trace_ions = categorize_ions_by_concentration(
        ion_composition, trace_threshold_mg_l
    )
    
    if not trace_ions:
        # No trace ions, return original
        return ion_composition.copy(), {}
    
    # Calculate total trace concentration
    total_trace_conc = sum(trace_ions.values())
    
    # Determine charge of trace ions
    cation_trace = 0.0
    anion_trace = 0.0
    
    for ion, conc in trace_ions.items():
        if ion.endswith('_+') or ion.endswith('_2+') or ion.endswith('_3+'):
            cation_trace += conc
        else:
            anion_trace += conc
    
    # Create simulation composition
    simulation_comp = major_ions.copy()
    
    # Add lumped trace components if significant
    if cation_trace > 0.1:  # More than 0.1 mg/L
        # Use Na+ as proxy for trace cations
        lumped_cation_conc = max(cation_trace, min_lumped_concentration)
        if 'Na_+' in simulation_comp:
            simulation_comp['Na_+'] += lumped_cation_conc - cation_trace
        else:
            simulation_comp['Na_+'] = lumped_cation_conc
            
    if anion_trace > 0.1:  # More than 0.1 mg/L
        # Use Cl- as proxy for trace anions
        lumped_anion_conc = max(anion_trace, min_lumped_concentration)
        if 'Cl_-' in simulation_comp:
            simulation_comp['Cl_-'] += lumped_anion_conc - anion_trace
        else:
            simulation_comp['Cl_-'] = lumped_anion_conc
    
    # Log the lumping
    logger.info(f"Lumped {len(trace_ions)} trace ions (total {total_trace_conc:.2f} mg/L)")
    logger.info(f"Trace cations: {cation_trace:.2f} mg/L, Trace anions: {anion_trace:.2f} mg/L")
    
    return simulation_comp, trace_ions


def post_process_trace_rejection(
    simulation_results: Dict,
    trace_mapping: Dict[str, float],
    lumped_rejection: float = 0.99
) -> Dict[str, float]:
    """
    Post-process simulation results to estimate trace ion rejection.
    
    Args:
        simulation_results: Results from RO simulation
        trace_mapping: Mapping of trace ions from lumping
        lumped_rejection: Assumed rejection for lumped trace (default 99%)
        
    Returns:
        Dictionary of trace ion rejections
    """
    trace_rejections = {}
    
    # For most trace ions, RO rejection is very high (>95%)
    # Use typical values based on ion characteristics
    for ion, conc in trace_mapping.items():
        if ion in ['Fe_2+', 'Fe_3+', 'Ba_2+', 'Sr_2+']:
            # Multivalent cations - very high rejection
            trace_rejections[ion] = 0.99
        elif ion in ['F_-', 'Br_-']:
            # Small monovalent anions - slightly lower rejection
            trace_rejections[ion] = 0.95
        else:
            # Default high rejection
            trace_rejections[ion] = lumped_rejection
    
    return trace_rejections


def create_practical_simulation_composition(
    ion_composition: Dict[str, float]
) -> Tuple[Dict[str, float], Dict[str, float], str]:
    """
    Create a practical composition for RO simulation that avoids FBBT errors.
    
    This is the main function to use for preparing multi-ion compositions
    for WaterTAP RO simulations.
    
    Args:
        ion_composition: Original ion concentrations in mg/L
        
    Returns:
        Tuple of (simulation_comp, trace_ions, strategy)
        - simulation_comp: Composition to use in simulation
        - trace_ions: Dictionary of trace ions that were handled specially
        - strategy: Description of strategy used
    """
    # First check if we have trace ions
    major_ions, trace_ions = categorize_ions_by_concentration(ion_composition)
    
    if not trace_ions:
        return ion_composition.copy(), {}, "No trace ions - using original composition"
    
    # Check total trace concentration
    total_trace = sum(trace_ions.values())
    
    if total_trace < 1.0:  # Less than 1 mg/L total
        # Very low trace - use lumping approach
        sim_comp, trace_map = create_lumped_trace_composition(ion_composition)
        return sim_comp, trace_map, "Lumped trace ions due to very low concentration"
    
    elif len(trace_ions) > 3:  # Many trace components
        # Too many trace ions - use lumping to simplify
        sim_comp, trace_map = create_lumped_trace_composition(ion_composition)
        return sim_comp, trace_map, f"Lumped {len(trace_ions)} trace ions to simplify"
    
    else:
        # Moderate trace levels - boost to minimum for simulation
        sim_comp = major_ions.copy()
        boosted_ions = {}
        
        for ion, conc in trace_ions.items():
            if conc < 1.0:  # Below 1 mg/L
                # Boost to 5 mg/L for numerical stability
                sim_comp[ion] = 5.0
                boosted_ions[ion] = conc
                logger.info(f"Boosted {ion} from {conc} to 5.0 mg/L for simulation")
            else:
                sim_comp[ion] = conc
        
        return sim_comp, boosted_ions, "Boosted sub-ppm ions to minimum levels"