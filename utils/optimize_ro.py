# -*- coding: utf-8 -*-
"""
RO array optimization functions leveraging the proven notebook approach.

This module contains the exact optimization logic from the tested notebook
implementation, including the sophisticated two-phase approach and multi-configuration
capability for comprehensive RO system design.
"""

import numpy as np
import logging
from typing import Dict, List, Optional, Tuple, Union
from .helpers import (
    validate_flux_parameters,
    convert_numpy_types,
    estimate_initial_pump_pressure,
)
from .constants import (
    DEFAULT_MIN_CONCENTRATE_FLOW_M3H,
    DEFAULT_FLUX_TOLERANCE,
    DEFAULT_SALT_PASSAGE,
)

# Set up logging for this module
logger = logging.getLogger(__name__)


def optimize_vessel_array_configuration(
    feed_flow_m3h,
    target_recovery,
    feed_salinity_ppm,
    stage_flux_targets_lmh=None,
    min_concentrate_flow_per_vessel_m3h=None,
    element_area_m2=37.16,  # 400 ft²
    elements_per_vessel=7,
    max_stages=3,  # LIMITED TO 3 STAGES
    membrane_model='BW30_PRO_400',
    tolerance=0.02,  # 2% tolerance for recovery
    allow_recycle=True,
    max_recycle_ratio=0.5,
    # New optional flux parameters
    flux_targets_lmh=None,  # Optional custom flux targets
    flux_tolerance=None,  # Optional custom flux tolerance
    # Unused parameters kept for compatibility
    max_iterations=100,
    concentrate_target_range=(1.02, 2.50),
    weight_flux=0.35,
    weight_concentrate=0.15,
    weight_stages=0.40,
    weight_recovery=0.10
):
    """
    Optimize vessel array by MAXIMIZING recovery per stage while meeting constraints.
    
    Key improvements from notebook:
    1. No artificial stage boundaries - tries 1,2,3 stages for ANY recovery
    2. Two-phase optimization:
       - Phase 1: Find minimum stages using full flux flexibility
       - Phase 2: Global flux optimization to minimize deviation from targets
    3. Enhanced recycle optimization with correct mass balance
    4. Sophisticated recycle triggering (when target not met, not just when no solution)
    
    Parameters:
    -----------
    flux_targets_lmh : Optional[Union[float, List[float]]]
        Custom flux targets in LMH. Can be:
        - None: Use defaults [18, 15, 12]
        - Single float: Apply to all stages
        - List: Specific target per stage
    flux_tolerance : Optional[float]
        Flux tolerance as fraction (e.g., 0.1 for ±10%)
        If None, uses DEFAULT_FLUX_TOLERANCE (0.1)
    
    Algorithm:
    - Phase 1: Try all stage counts (1-3), maximize recovery per stage
    - Phase 2: Globally optimize flux across all stages to minimize total deviation
    - Phase 3: For high recovery or if target not met, use recycle with correct mass balance
    """
    
    # Handle flux parameters using the new optional inputs
    if flux_targets_lmh is not None or flux_tolerance is not None:
        # Use new parameter style - validate and normalize
        normalized_flux_targets, normalized_flux_tolerance = validate_flux_parameters(
            flux_targets_lmh, flux_tolerance, max_stages
        )
        stage_flux_targets_lmh = normalized_flux_targets
        flux_tolerance = normalized_flux_tolerance  # Update the variable for consistent logging
        # Calculate flux limits from tolerance
        flux_lower_limit = 1.0 - normalized_flux_tolerance
        flux_upper_limit = 1.0 + normalized_flux_tolerance
    elif stage_flux_targets_lmh is not None:
        # Legacy parameter was provided - use it as-is
        # Ensure it's a list
        if not isinstance(stage_flux_targets_lmh, list):
            stage_flux_targets_lmh = [stage_flux_targets_lmh] * max_stages
        # Use default flux tolerance
        flux_tolerance = DEFAULT_FLUX_TOLERANCE
        flux_lower_limit = 1.0 - flux_tolerance
        flux_upper_limit = 1.0 + flux_tolerance
    else:
        # Neither new nor legacy parameters provided - use defaults
        stage_flux_targets_lmh = [18, 15, 12]
        # Use default flux tolerance
        flux_tolerance = DEFAULT_FLUX_TOLERANCE
        flux_lower_limit = 1.0 - flux_tolerance  # e.g., 0.9 for 10% tolerance
        flux_upper_limit = 1.0 + flux_tolerance  # e.g., 1.1 for 10% tolerance
    
    if min_concentrate_flow_per_vessel_m3h is None:
        min_concentrate_flow_per_vessel_m3h = DEFAULT_MIN_CONCENTRATE_FLOW_M3H.copy()
    
    # Ensure we have values for all stages
    while len(stage_flux_targets_lmh) < max_stages:
        stage_flux_targets_lmh.append(stage_flux_targets_lmh[-1])
    while len(min_concentrate_flow_per_vessel_m3h) < max_stages:
        min_concentrate_flow_per_vessel_m3h.append(min_concentrate_flow_per_vessel_m3h[-1])
    
    vessel_area = element_area_m2 * elements_per_vessel
    
    # FIXED: Tighter convergence tolerance for recycle optimization
    CONVERGENCE_TOLERANCE = 0.01  # 0.01 m³/h instead of 0.5
    
    # Performance optimization: Cache for vessel evaluations
    vessel_eval_cache = {}
    
    # Pre-validation for large configurations
    def validate_configuration_scale(feed_flow, min_conc_flows):
        """
        Pre-validate if configuration will require optimized search.
        Returns warnings and recommended approach.
        """
        max_possible_vessels = []
        for stage_idx, min_conc in enumerate(min_conc_flows):
            max_vessels = int(feed_flow / min_conc)
            max_possible_vessels.append(max_vessels)
            if max_vessels > 500:
                logger.warning(f"Stage {stage_idx+1} could require up to {max_vessels} vessels - using optimized search")
            elif max_vessels > 100:
                logger.info(f"Stage {stage_idx+1} may require {max_vessels} vessels - using geometric search")
        
        total_max = sum(max_possible_vessels)
        if total_max > 1000:
            logger.warning(f"Configuration could require {total_max} total vessels across all stages")
            logger.info("Using highly optimized search strategies to prevent timeout")
            return 'ultra_optimized'
        elif total_max > 200:
            logger.info(f"Configuration may require up to {total_max} vessels - using optimized search")
            return 'optimized'
        else:
            return 'standard'
    
    # Validate scale at start
    search_mode = validate_configuration_scale(feed_flow_m3h, min_concentrate_flow_per_vessel_m3h[:max_stages])
    
    def binary_search_vessels(feed_flow, flux_target, min_conc_flow, target_recovery, tolerance):
        """
        Binary search for optimal vessel count - efficient for single stage.
        Returns best configuration that meets or exceeds target recovery.
        """
        max_vessels = int(feed_flow / min_conc_flow)
        
        # Quick bounds check
        if max_vessels <= 0:
            return None
            
        # For small vessel counts, use original approach
        if max_vessels <= 50:
            return None  # Signal to use original method
        
        left, right = 1, max_vessels
        best_config = None
        
        while left <= right:
            mid = (left + right) // 2
            config = evaluate_vessel_count_max_recovery(mid, feed_flow, flux_target, min_conc_flow)
            
            if config is None:
                # Can't achieve any recovery with this vessel count
                left = mid + 1
                continue
            
            recovery = config['recovery']
            
            if abs(recovery - target_recovery) <= tolerance:
                # Found exact match
                return config
            elif recovery < target_recovery:
                # Need more vessels for higher recovery
                left = mid + 1
            else:
                # Recovery exceeds target, try fewer vessels
                best_config = config  # Save as potential solution
                right = mid - 1
        
        return best_config
    
    def geometric_search_vessels(feed_flow, flux_target, min_conc_flow, search_down=True):
        """
        Geometric progression search for large vessel counts.
        Starts with powers of 2, then refines the best region.
        """
        max_vessels = int(feed_flow / min_conc_flow)
        
        if max_vessels <= 100:
            return None  # Use original method for small counts
        
        # Phase 1: Coarse search with geometric progression
        best_config = None
        best_recovery = 0
        promising_range = None
        
        # Determine step size based on scale
        if max_vessels > 1000:
            initial_steps = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024]
        elif max_vessels > 500:
            initial_steps = [1, 2, 4, 8, 16, 32, 64, 128, 256]
        else:
            initial_steps = [1, 2, 4, 8, 16, 32, 64]
        
        # Extend steps to cover full range
        while initial_steps[-1] < max_vessels:
            initial_steps.append(min(initial_steps[-1] * 2, max_vessels))
        
        # Test geometric points
        for n_vessels in initial_steps:
            if n_vessels > max_vessels:
                break
            
            config = evaluate_vessel_count_max_recovery(n_vessels, feed_flow, flux_target, min_conc_flow)
            if config and config['recovery'] > best_recovery:
                best_config = config
                best_recovery = config['recovery']
                # Remember promising range for refinement
                idx = initial_steps.index(n_vessels)
                if idx > 0:
                    promising_range = (initial_steps[idx-1], min(initial_steps[idx+1] if idx+1 < len(initial_steps) else n_vessels*2, max_vessels))
                else:
                    promising_range = (1, min(initial_steps[1] if len(initial_steps) > 1 else n_vessels*2, max_vessels))
        
        # Phase 2: Refine in promising range if found
        if promising_range and best_config:
            range_size = promising_range[1] - promising_range[0]
            if range_size > 10:
                # Test a few more points in the promising range
                refinement_points = np.linspace(promising_range[0], promising_range[1], min(10, range_size), dtype=int)
                for n_vessels in refinement_points:
                    config = evaluate_vessel_count_max_recovery(n_vessels, feed_flow, flux_target, min_conc_flow)
                    if config and config['recovery'] > best_recovery:
                        best_config = config
                        best_recovery = config['recovery']
        
        return best_config
    
    def evaluate_vessel_count_at_flux(n_vessels, feed_flow, flux, min_conc_flow):
        """
        Evaluate a specific vessel count at a specific flux.
        Returns configuration if valid, None otherwise.
        """
        # Calculate permeate at this flux
        permeate = n_vessels * vessel_area * flux / 1000  # m³/h
        
        # Can't produce more permeate than feed
        if permeate >= feed_flow:
            return None
        
        # Calculate concentrate
        concentrate = feed_flow - permeate
        conc_per_vessel = concentrate / n_vessels
        
        # Check concentrate constraint
        if conc_per_vessel < min_conc_flow:
            return None
        
        # If we get here, all constraints are satisfied
        recovery = permeate / feed_flow
        
        return {
            'n_vessels': n_vessels,
            'permeate': permeate,
            'concentrate': concentrate,
            'recovery': recovery,
            'flux': flux,
            'conc_per_vessel': conc_per_vessel,
        }
    
    def evaluate_vessel_count_max_recovery(n_vessels, feed_flow, flux_target, min_conc_flow):
        """
        Phase 1: Find maximum recovery for given vessel count.
        Allow flux to vary within tolerance to maximize recovery.
        If necessary to meet recovery target, allow going below flux_lower_limit.
        """
        best_config = None
        
        # Try different flux values within tolerance
        # Start with higher flux values to maximize recovery
        flux_factors = np.linspace(flux_upper_limit, flux_lower_limit, 10)
        
        for factor in flux_factors:
            flux = flux_target * factor
            config = evaluate_vessel_count_at_flux(n_vessels, feed_flow, flux, min_conc_flow)
            
            if config is not None:
                config['flux_ratio'] = factor
                config['flux_target'] = flux_target
                config['conc_ratio'] = config['conc_per_vessel'] / min_conc_flow
                
                if best_config is None or config['recovery'] > best_config['recovery']:
                    best_config = config
        
# Emergency flux reduction removed - this should only be available during global optimization
        
        return best_config
    
    def fine_tune_flux_globally(stages_config, target_recovery_param, tolerance_param, base_feed_flow):
        """
        Phase 2: Global flux optimization to minimize total deviation from targets.
        This ensures all stages operate as close to their target flux as possible
        while precisely achieving the target recovery.
        
        FIXED: Maintains mass balance consistency by updating downstream feed flows.
        """
        current_stages = stages_config['stages'].copy()
        n_stages = len(current_stages)
        
        # Calculate current total recovery
        total_permeate = sum(s['permeate_flow'] for s in current_stages)
        current_recovery = total_permeate / base_feed_flow
        
        # If already within tolerance, return as-is
        if abs(current_recovery - target_recovery_param) <= tolerance_param:
            return stages_config
        
        # If undershooting, can't improve (already at max flux)
        if current_recovery < target_recovery_param:
            return stages_config
        
        logger.debug(f"\nGlobal flux optimization (current: {current_recovery*100:.1f}%, target: {target_recovery_param*100:.1f}%)")
        
        # Iterative global optimization
        for iteration in range(30):
            # Calculate current state
            total_permeate = sum(s['permeate_flow'] for s in current_stages)
            current_recovery = total_permeate / base_feed_flow
            recovery_error = current_recovery - target_recovery_param
            
            if abs(recovery_error) <= tolerance_param / 2:
                break
            
            # Calculate flexibility for each stage (how far from target flux)
            flexibilities = []
            total_flexibility = 0
            
            for stage in current_stages:
                current_ratio = stage['flux_ratio']
                # Flexibility is how much we can adjust flux
                if recovery_error > 0:  # Need to reduce recovery
                    # Can reduce flux down to lower limit
                    flexibility = current_ratio - flux_lower_limit
                else:  # Need to increase recovery
                    # Can increase flux toward upper limit
                    flexibility = flux_upper_limit - current_ratio
                
                flexibilities.append(flexibility)
                total_flexibility += flexibility
            
            if total_flexibility == 0:
                break
            
            # Distribute adjustment proportionally to flexibility
            required_permeate_change = -recovery_error * base_feed_flow
            
            for i, stage in enumerate(current_stages):
                if flexibilities[i] > 0:
                    # Calculate this stage's share of adjustment
                    weight = flexibilities[i] / total_flexibility
                    stage_permeate_change = required_permeate_change * weight
                    
                    # Convert to flux change
                    current_flux = stage['flux']
                    flux_change = stage_permeate_change * 1000 / (stage['n_vessels'] * vessel_area)
                    
                    # Apply with damping for stability (more aggressive when overshooting significantly)
                    if recovery_error > tolerance_param:
                        damping = 0.9  # More aggressive adjustment when overshooting
                    else:
                        damping = 0.7  # Conservative adjustment otherwise
                    new_flux = current_flux + flux_change * damping
                    
                    # Determine flux bounds - allow exception for recovery targeting
                    normal_lower_bound = stage['flux_target'] * flux_lower_limit
                    emergency_lower_bound = stage['flux_target'] * 0.7  # Emergency limit: 70% of target
                    upper_bound = stage['flux_target'] * flux_upper_limit
                    
                    # Use emergency lower bound if we're significantly overshooting target
                    if recovery_error > tolerance_param:
                        # Allow going below normal tolerance to achieve target recovery
                        effective_lower_bound = emergency_lower_bound
                        logger.debug(f"    Stage {i+1}: Using emergency flux limit ({effective_lower_bound/stage['flux_target']*100:.0f}% of target)")
                    else:
                        effective_lower_bound = normal_lower_bound
                    
                    # Ensure within bounds (now with conditional emergency limit)
                    new_flux = max(effective_lower_bound, min(upper_bound, new_flux))
                    
                    # Verify configuration is valid
                    test_config = evaluate_vessel_count_at_flux(
                        stage['n_vessels'],
                        stage['feed_flow'],
                        new_flux,
                        stage['min_conc_per_vessel']
                    )
                    
                    if test_config is not None:
                        # Update stage
                        stage['flux'] = new_flux
                        stage['flux_ratio'] = new_flux / stage['flux_target']
                        stage['permeate_flow'] = test_config['permeate']
                        stage['concentrate_flow'] = test_config['concentrate']
                        stage['stage_recovery'] = test_config['recovery']
                        stage['conc_per_vessel'] = test_config['conc_per_vessel']
                        stage['concentrate_ratio'] = test_config['conc_per_vessel'] / stage['min_conc_per_vessel']
                        
                        # FIXED: Update next stage's feed flow to maintain mass balance
                        if i < len(current_stages) - 1:
                            current_stages[i + 1]['feed_flow'] = test_config['concentrate']
        
        # Report final flux distribution
        logger.debug(f"  Iterations: {iteration + 1}")
        for i, stage in enumerate(current_stages):
            logger.debug(f"  Stage {i+1}: {stage['flux']:.1f} LMH ({stage['flux_ratio']*100:.0f}% of target)")
        
        # Update configuration
        stages_config['stages'] = current_stages
        # FIXED: Recalculate totals to ensure consistency
        stages_config['total_recovery'] = sum(s['permeate_flow'] for s in current_stages) / base_feed_flow
        stages_config['total_permeate'] = sum(s['permeate_flow'] for s in current_stages)
        # FIXED: Update final concentrate from last stage
        stages_config['final_concentrate'] = current_stages[-1]['concentrate_flow'] if current_stages else 0
        
        logger.debug(f"  Final recovery: {stages_config['total_recovery']*100:.1f}%")
        
        return stages_config
    
    def try_without_recycle():
        """Try to find all viable configurations without recycle."""
        viable_configs = []
        
        # NO ARTIFICIAL STAGE BOUNDARIES - try all stages for any recovery
        for n_stages in range(1, max_stages + 1):
            stages = []
            current_feed = feed_flow_m3h
            total_permeate = 0
            
            logger.info(f"\nTrying {n_stages}-stage configuration for {target_recovery*100:.0f}% recovery:")
            
            for stage_idx in range(n_stages):
                flux_target = stage_flux_targets_lmh[stage_idx]
                min_conc = min_concentrate_flow_per_vessel_m3h[stage_idx]
                
                # Maximum vessels limited by concentrate constraint at minimum flow
                max_vessels = int(current_feed / min_conc)
                
                # Find the configuration with maximum recovery
                best_stage_config = None
                best_stage_recovery = 0
                
                # For single stage trying to meet a specific recovery, also try lower vessel counts
                if n_stages == 1 and stage_idx == 0:
                    # Use intelligent search for large vessel counts
                    if max_vessels > 100:
                        logger.info(f"  Using binary search for {max_vessels} potential vessels...")
                        best_stage_config = binary_search_vessels(current_feed, flux_target, min_conc, target_recovery, tolerance)
                        if best_stage_config:
                            best_stage_recovery = best_stage_config['recovery']
                    else:
                        # Original approach for small vessel counts
                        for n_vessels in range(1, max_vessels + 1):
                            config = evaluate_vessel_count_max_recovery(n_vessels, current_feed, flux_target, min_conc)
                            
                            if config is not None:
                                stage_recovery = config['recovery']
                                # For single stage, we want recovery close to target
                                if stage_recovery >= target_recovery and stage_recovery <= target_recovery + tolerance:
                                    best_stage_config = config
                                    best_stage_recovery = stage_recovery
                                    break
                                elif stage_recovery > best_stage_recovery and stage_recovery < target_recovery:
                                    # Keep best option below target
                                    best_stage_recovery = stage_recovery
                                    best_stage_config = config
                else:
                    # For multi-stage, maximize recovery per stage
                    if max_vessels > 100:
                        logger.info(f"  Stage {stage_idx+1}: Using geometric search for {max_vessels} potential vessels...")
                        best_stage_config = geometric_search_vessels(current_feed, flux_target, min_conc)
                        if best_stage_config:
                            best_stage_recovery = best_stage_config['recovery']
                    else:
                        # Original approach for small vessel counts
                        for n_vessels in range(max_vessels, 0, -1):
                            config = evaluate_vessel_count_max_recovery(n_vessels, current_feed, flux_target, min_conc)
                            
                            if config is not None:
                                # Select configuration with highest recovery
                                if config['recovery'] > best_stage_recovery:
                                    best_stage_recovery = config['recovery']
                                    best_stage_config = config
                
                if best_stage_config is None:
                    logger.debug(f"  Stage {stage_idx+1}: No valid configuration found")
                    break
                
                logger.debug(f"  Stage {stage_idx+1}: {best_stage_config['n_vessels']} vessels, "
                      f"recovery={best_stage_config['recovery']:.1%}, "
                      f"flux={best_stage_config['flux']:.1f} LMH ({best_stage_config['flux_ratio']*100:.0f}% of target)")
                
                # Add stage to configuration
                stage_data = {
                    'stage_number': stage_idx + 1,
                    'n_vessels': best_stage_config['n_vessels'],
                    'feed_flow': current_feed,
                    'permeate_flow': best_stage_config['permeate'],
                    'concentrate_flow': best_stage_config['concentrate'],
                    'stage_recovery': best_stage_config['recovery'],
                    'flux': best_stage_config['flux'],
                    'flux_target': flux_target,
                    'flux_ratio': best_stage_config['flux_ratio'],
                    'conc_per_vessel': best_stage_config['conc_per_vessel'],
                    'min_conc_per_vessel': min_conc,
                    'concentrate_ratio': best_stage_config['conc_ratio']
                }
                stages.append(stage_data)
                
                total_permeate += best_stage_config['permeate']
                current_feed = best_stage_config['concentrate']
                
                # Check current total recovery
                total_recovery = total_permeate / feed_flow_m3h
                
                # If we've exceeded target by more than tolerance, don't add more stages
                if total_recovery > target_recovery + tolerance:
                    logger.debug(f"  Exceeded target recovery: {total_recovery:.1%}")
                    break
            
            # Check if configuration is viable (meets recovery target within tolerance)
            if len(stages) > 0 and len(stages) == n_stages:  # Ensure we have the intended number of stages
                total_recovery = total_permeate / feed_flow_m3h
                
                # Only accept configurations that meet the recovery target
                # NO TOLERANCE for undershooting - must meet or exceed target
                if total_recovery >= target_recovery:
                    config_dict = {
                        'n_stages': len(stages),
                        'stages': stages,
                        'total_recovery': total_recovery,
                        'total_permeate': total_permeate,
                        'final_concentrate': current_feed,
                        'feed_flow_m3h': feed_flow_m3h,
                        'feed_salinity_ppm': feed_salinity_ppm,
                        'target_recovery': target_recovery,
                        'membrane_model': membrane_model
                    }
                    
                    # Phase 2: Global flux optimization if overshooting
                    if total_recovery > target_recovery + tolerance:
                        config_dict = fine_tune_flux_globally(config_dict, target_recovery, tolerance, feed_flow_m3h)
                        total_recovery = config_dict['total_recovery']
                    
                    # Add to viable configurations list
                    viable_configs.append(config_dict)
                    logger.debug(f"  Viable {n_stages}-stage configuration found with recovery {total_recovery*100:.1f}%")
        
        return viable_configs
    
    def optimize_with_recycle():
        """
        FIXED concentrate recycle optimization with correct mass balance.
        
        Key fixes:
        1. Works backwards from required disposal to determine recycle
        2. Ensures recycle never exceeds final concentrate
        3. Uses consistent definitions throughout
        4. Tighter convergence tolerance (0.01 m³/h)
        """
        logger.debug("\nOptimizing concentrate recycle for high recovery...")
        
        # Required flows based on mass balance
        required_permeate = feed_flow_m3h * target_recovery
        required_disposal = feed_flow_m3h * (1 - target_recovery)
        
        logger.debug(f"\nMass balance requirements:")
        logger.debug(f"  Fresh feed: {feed_flow_m3h:.1f} m³/h")
        logger.debug(f"  Target recovery: {target_recovery*100:.1f}%")
        logger.debug(f"  Required permeate: {required_permeate:.1f} m³/h")
        logger.debug(f"  Required disposal: {required_disposal:.1f} m³/h")
        
        # Phase 1: Find feasible recycle configurations
        logger.debug("\nPhase 1: Finding feasible recycle configurations...")
        working_solutions = []
        
        # Search over different effective recovery values
        effective_recoveries = np.linspace(0.5, 0.9, 100)
        
        for eff_recovery in effective_recoveries:
            # For a given effective recovery, calculate required effective feed
            eff_feed_initial = required_permeate / eff_recovery
            
            # Iterate to find self-consistent solution
            eff_feed = eff_feed_initial
            
            converged = False
            for iter in range(5):
                # Design RO system with this effective feed and recovery
                configs = try_with_recycle_inner(eff_feed, eff_recovery, feed_salinity_ppm)
                
                if not configs:
                    break
                
                # Process ALL configurations from this iteration
                new_eff_feeds = []
                for config in configs:
                    # Get actual flows
                    actual_permeate = config['total_permeate']
                    actual_concentrate = config['final_concentrate']
                    
                    # Check if we can achieve target with this concentrate
                    if actual_concentrate < required_disposal:
                        continue
                    
                    # Calculate recycle needed
                    recycle_flow = actual_concentrate - required_disposal
                    
                    # Check physical constraint
                    if recycle_flow > actual_concentrate:
                        continue
                    
                    # Update effective feed (fresh + recycle)
                    new_eff_feed = feed_flow_m3h + recycle_flow
                    new_eff_feeds.append(new_eff_feed)
                    
                    # Store ALL viable solutions, not just converged ones
                    actual_recovery_from_fresh = actual_permeate / feed_flow_m3h
                    recovery_error = abs(actual_recovery_from_fresh - target_recovery)
                    
                    # Calculate recycle split ratio
                    recycle_split_ratio = recycle_flow / actual_concentrate

                    if recycle_split_ratio > max_recycle_ratio + 1e-6:
                        logger.debug(
                            "    Skipping solution with recycle split %.1f%% above max %.1f%%",
                            recycle_split_ratio * 100,
                            max_recycle_ratio * 100,
                        )
                        continue
                    
                    # Estimate effective salinity
                    conc_factor = 1 / (1 - eff_recovery)
                    brine_salinity = feed_salinity_ppm * conc_factor
                    effective_salinity = (feed_flow_m3h * feed_salinity_ppm + 
                                        recycle_flow * brine_salinity) / new_eff_feed
                    
                    solution = {
                        'effective_recovery': eff_recovery,
                        'effective_feed': new_eff_feed,
                        'actual_effective_feed_m3h': eff_feed,
                        'actual_permeate': actual_permeate,
                        'actual_concentrate': actual_concentrate,
                        'recycle_flow': recycle_flow,
                        'disposal_flow': required_disposal,
                        'recycle_split_ratio': recycle_split_ratio,
                        'actual_recovery_from_fresh': actual_recovery_from_fresh,
                        'recovery_error': recovery_error,
                        'effective_salinity': effective_salinity,
                        'config': config,
                        'iteration': iter,
                        'eff_recovery_target': eff_recovery
                    }
                    
                    working_solutions.append(solution)
                
                # Check convergence based on average effective feed
                if new_eff_feeds:
                    avg_new_eff_feed = sum(new_eff_feeds) / len(new_eff_feeds)
                    if abs(avg_new_eff_feed - eff_feed) < CONVERGENCE_TOLERANCE:
                        converged = True
                        break
                    eff_feed = avg_new_eff_feed
        
        if not working_solutions:
            logger.debug("No feasible recycle configurations found!")
            return []
        
        # Deduplicate solutions - keep best solution for each stage count
        unique_solutions = {}
        for solution in working_solutions:
            n_stages = solution['config']['n_stages']
            
            # For recycle cases, we want to keep different stage counts even if recovery is similar
            # Use stage count as primary key
            key = n_stages
            
            # Keep the solution with lowest recovery error for each stage count
            if key not in unique_solutions or solution['recovery_error'] < unique_solutions[key]['recovery_error']:
                unique_solutions[key] = solution
        
        logger.debug(f"\nFound {len(unique_solutions)} unique stage configurations from {len(working_solutions)} total solutions")
        for n_stages, solution in unique_solutions.items():
            logger.debug(f"  {n_stages}-stage: recovery={solution['actual_recovery_from_fresh']*100:.1f}%, "
                        f"recycle={solution['recycle_split_ratio']*100:.1f}%, "
                        f"error={solution['recovery_error']*100:.2f}%")
        
        # Return all viable solutions that meet recovery target
        viable_solutions = [s for s in unique_solutions.values() if s['recovery_error'] < tolerance]
        
        if not viable_solutions:
            # If none meet tight tolerance, return all within 2x tolerance
            viable_solutions = [s for s in unique_solutions.values() if s['recovery_error'] < tolerance * 2]
        
        return viable_solutions
    
    def try_with_recycle_inner(effective_feed_flow, effective_recovery_target, effective_salinity):
        """Inner function to design RO with given effective conditions."""
        viable_configs = []
        
        logger.debug(f"\n  Trying recycle design with eff_feed={effective_feed_flow:.1f}, eff_recovery={effective_recovery_target:.1%}")
        
        # Try ALL stage counts to find all viable configurations
        for n_stages in range(1, max_stages + 1):
            # Use the same maximize recovery approach
            stages = []
            current_feed = effective_feed_flow
            total_permeate = 0
            
            for stage_idx in range(n_stages):
                flux_target = stage_flux_targets_lmh[stage_idx]
                min_conc = min_concentrate_flow_per_vessel_m3h[stage_idx]
                
                # Maximum vessels limited by concentrate constraint
                max_vessels = int(current_feed / min_conc)
                
                # Find configuration with max recovery
                best_stage_config = None
                best_stage_recovery = 0
                
                # Use intelligent search for large vessel counts
                if max_vessels > 100:
                    best_stage_config = geometric_search_vessels(current_feed, flux_target, min_conc)
                    if best_stage_config:
                        best_stage_recovery = best_stage_config['recovery']
                else:
                    # Original approach for small vessel counts
                    for n_vessels in range(max_vessels, 0, -1):
                        config = evaluate_vessel_count_max_recovery(n_vessels, current_feed, flux_target, min_conc)
                        
                        if config is not None and config['recovery'] > best_stage_recovery:
                            best_stage_recovery = config['recovery']
                            best_stage_config = config
                
                if best_stage_config is None:
                    break
                
                # Add stage
                stage_data = {
                    'stage_number': stage_idx + 1,
                    'n_vessels': best_stage_config['n_vessels'],
                    'feed_flow': current_feed,
                    'permeate_flow': best_stage_config['permeate'],
                    'concentrate_flow': best_stage_config['concentrate'],
                    'stage_recovery': best_stage_config['recovery'],
                    'flux': best_stage_config['flux'],
                    'flux_target': flux_target,
                    'flux_ratio': best_stage_config['flux_ratio'],
                    'conc_per_vessel': best_stage_config['conc_per_vessel'],
                    'min_conc_per_vessel': min_conc,
                    'concentrate_ratio': best_stage_config['conc_ratio']
                }
                stages.append(stage_data)
                
                total_permeate += best_stage_config['permeate']
                current_feed = best_stage_config['concentrate']
                
                # Check if target achieved
                if total_permeate / effective_feed_flow >= effective_recovery_target - tolerance:
                    break
            
            if len(stages) > 0:
                total_recovery = total_permeate / effective_feed_flow
                
                # Check if configuration meets target (NO TOLERANCE for undershooting)
                if total_recovery >= effective_recovery_target:
                    config_dict = {
                        'n_stages': len(stages),
                        'stages': stages,
                        'total_recovery': total_recovery,
                        'total_permeate': total_permeate,
                        'final_concentrate': current_feed,
                        'effective_feed_flow_m3h': effective_feed_flow,
                        'effective_feed_salinity_ppm': effective_salinity,
                        'system_recovery': total_permeate / effective_feed_flow
                    }
                    
                    # Fine-tune if overshooting
                    if config_dict['total_recovery'] > effective_recovery_target + tolerance:
                        config_dict = fine_tune_flux_globally(config_dict, effective_recovery_target, 
                                                            tolerance, effective_feed_flow)
                    
                    # Calculate average flux ratio
                    flux_ratios = [s['flux_ratio'] for s in config_dict['stages']]
                    config_dict['average_flux_ratio'] = np.mean(flux_ratios)
                    
                    # Add to viable configurations
                    viable_configs.append(config_dict)
                    logger.debug(f"    Found viable {n_stages}-stage config: recovery={total_recovery:.1%}")
        
        logger.debug(f"  Total viable configs found: {len(viable_configs)}")
        # Return all viable configurations found
        return viable_configs
    
    # Main optimization logic
    logger.debug(f"Optimizing vessel array for {target_recovery*100:.0f}% recovery...")
    logger.debug(f"Using NOTEBOOK'S PROVEN TWO-PHASE OPTIMIZATION (max {max_stages} stages)")
    logger.debug(f"Phase 1: Try ALL stage counts, maximize recovery per stage")
    logger.debug(f"Phase 2: Global flux optimization to minimize total deviation")
    logger.debug(f"Flux tolerance: ±{flux_tolerance*100:.0f}% of target")
    
    # Collect all viable configurations
    all_viable_configs = []
    
    # First try without recycle
    configs_without_recycle = try_without_recycle()
    if configs_without_recycle:
        all_viable_configs.extend(configs_without_recycle)
    
    # Also try with recycle if allowed
    if allow_recycle:
        logger.debug("\nTrying with concentrate recycle...")
        
        # Use enhanced recycle optimization
        recycle_solutions = optimize_with_recycle()
        
        if recycle_solutions:
            for recycle_solution in recycle_solutions:
                config = recycle_solution['config']
                # Store recycle information with correct values
                config['recycle_flow_m3h'] = recycle_solution['recycle_flow']
                config['recycle_split_ratio'] = recycle_solution['recycle_split_ratio']
                config['disposal_flow_m3h'] = recycle_solution['disposal_flow']
                config['effective_feed_flow_m3h'] = recycle_solution['effective_feed']
                config['actual_effective_feed_m3h'] = recycle_solution.get('actual_effective_feed_m3h', recycle_solution['effective_feed'])
                config['effective_feed_salinity_ppm'] = recycle_solution['effective_salinity']
                config['actual_recovery_from_feed'] = recycle_solution['actual_recovery_from_fresh']
                
                # Calculate traditional recycle_ratio for compatibility
                config['recycle_ratio'] = recycle_solution['recycle_flow'] / (feed_flow_m3h + recycle_solution['recycle_flow'])
                
                all_viable_configs.append(config)
                logger.debug(f"Found solution with {config['n_stages']} stages and {recycle_solution['recycle_split_ratio']*100:.1f}% split to recycle")
    
    if not all_viable_configs:
        raise ValueError(f"No feasible configuration found. Target recovery of {target_recovery*100:.0f}% "
                        f"cannot be achieved in {max_stages} stages, even with recycle.")
    
    # Format all viable configurations
    formatted_configs = []
    
    for config in all_viable_configs:
        # Finalize results for each configuration
        results = {
            'feed_flow_m3h': feed_flow_m3h,
            'feed_salinity_ppm': feed_salinity_ppm,
            'target_recovery': target_recovery,
            'membrane_model': membrane_model,
            'n_stages': config['n_stages'],
            'stages': []
        }
    
        # Add recycle information if applicable
        if 'recycle_flow_m3h' in config:
            results['recycle_ratio'] = config['recycle_ratio']
            results['recycle_flow_m3h'] = config['recycle_flow_m3h']
            results['recycle_split_ratio'] = config['recycle_split_ratio']
            results['disposal_flow_m3h'] = config['disposal_flow_m3h']
            results['effective_feed_flow_m3h'] = config['effective_feed_flow_m3h']
            results['actual_effective_feed_m3h'] = config.get('actual_effective_feed_m3h', config['effective_feed_flow_m3h'])
            results['effective_feed_salinity_ppm'] = config['effective_feed_salinity_ppm']
            results['system_recovery'] = config['system_recovery']
        else:
            results['recycle_ratio'] = 0
            results['effective_feed_flow_m3h'] = feed_flow_m3h
            results['actual_effective_feed_m3h'] = feed_flow_m3h
            results['effective_feed_salinity_ppm'] = feed_salinity_ppm
        
        # Build detailed stage information
        # Determine salt passage based on membrane model
        if membrane_model.startswith('SW'):
            salt_passage = DEFAULT_SALT_PASSAGE['seawater']
        else:
            salt_passage = DEFAULT_SALT_PASSAGE['brackish']
        current_stage_salinity = results.get('effective_feed_salinity_ppm', feed_salinity_ppm)

        for stage_data in config['stages']:
            stage_config = {
                'stage_number': stage_data['stage_number'],
                'feed_flow_m3h': stage_data['feed_flow'],
                'permeate_flow_m3h': stage_data['permeate_flow'],
                'concentrate_flow_m3h': stage_data['concentrate_flow'],
                'stage_recovery': stage_data['stage_recovery'],
                'n_vessels': stage_data['n_vessels'],
                'vessel_count': stage_data['n_vessels'],  # Add vessel_count for compatibility
                'n_elements': stage_data['n_vessels'] * elements_per_vessel,
                'elements_per_vessel': elements_per_vessel,  # Add for model builder
                'membrane_area_m2': stage_data['n_vessels'] * vessel_area,
                'design_flux_lmh': stage_data['flux'],
                'flux_target_lmh': stage_data['flux_target'],
                'flux_ratio': stage_data['flux_ratio'],
                'concentrate_per_vessel_m3h': stage_data['conc_per_vessel'],
                'min_concentrate_required': stage_data['min_conc_per_vessel'],
                'concentrate_flow_ratio': stage_data['concentrate_ratio']
            }

            try:
                stage_recovery_for_pressure = min(max(stage_data['stage_recovery'], 1e-6), 0.99)
                stage_pressure_pa = estimate_initial_pump_pressure(
                    current_stage_salinity,
                    stage_recovery_for_pressure,
                    membrane_type=membrane_model,
                )
                stage_config['feed_pressure_bar'] = stage_pressure_pa / 1e5
            except Exception as _e:
                logger.debug(
                    "Could not estimate feed pressure for stage %s: %s",
                    stage_data['stage_number'],
                    _e,
                )

            results['stages'].append(stage_config)

            # Estimate next-stage salinity using mass balance to aid pressure estimates
            try:
                stage_recovery = min(max(stage_data['stage_recovery'], 1e-6), 0.99)
                concentration_factor = (1 - salt_passage) / max(1 - stage_recovery, 1e-6)
                next_salinity = current_stage_salinity * concentration_factor
                current_stage_salinity = min(max(next_salinity, 100.0), 100000.0)
            except Exception:
                # Fall back to leaving salinity unchanged if calculation fails
                pass
        
        # Summary statistics
        results['array_notation'] = ':'.join(str(s['n_vessels']) for s in results['stages'])
        results['total_vessels'] = sum(s['n_vessels'] for s in results['stages'])
        results['total_elements'] = sum(s['n_elements'] for s in results['stages'])
        results['total_membrane_area_m2'] = sum(s['membrane_area_m2'] for s in results['stages'])
        results['total_permeate_flow_m3h'] = config['total_permeate']
        results['total_recovery'] = config.get('actual_recovery_from_feed', config['total_recovery'])
        results['recovery_error'] = abs(results['total_recovery'] - target_recovery)
        
        # FIXED: Get final concentrate from last stage after optimization
        last_stage_data = config['stages'][-1] if config['stages'] else None
        if last_stage_data:
            results['final_concentrate_flow_m3h'] = last_stage_data['concentrate_flow']
        else:
            results['final_concentrate_flow_m3h'] = config.get('final_concentrate', 0)
        
        results['min_flux_ratio'] = min(s['flux_ratio'] for s in results['stages'])
        results['max_flux_ratio'] = max(s['flux_ratio'] for s in results['stages'])
        results['average_flux_ratio'] = np.mean([s['flux_ratio'] for s in results['stages']])
        results['average_concentrate_flow_ratio'] = np.mean([s['concentrate_flow_ratio'] for s in results['stages']])
        
        # Calculate flux deviation metrics
        flux_deviations = [abs(s['flux_ratio'] - 1.0) for s in results['stages']]
        results['total_flux_deviation'] = sum(flux_deviations)
        results['average_flux_deviation'] = np.mean(flux_deviations)
        results['max_flux_deviation'] = max(flux_deviations)
        
        # CRITICAL: Mark whether target recovery was achieved (must meet or exceed target)
        results['meets_target_recovery'] = results['total_recovery'] >= target_recovery
        
        # Convert numpy types to Python types for JSON serialization
        results = convert_numpy_types(results)
        
        formatted_configs.append(results)
    
    # Log summary
    logger.info(f"\n\nFound {len(formatted_configs)} viable configuration(s):")
    for config in formatted_configs:
        logger.info(f"  {config['n_stages']}-stage: {config['array_notation']}, "
                   f"recovery={config['total_recovery']*100:.1f}%, "
                   f"recycle={config['recycle_ratio']*100:.0f}%")
    
    return formatted_configs
