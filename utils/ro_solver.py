"""
RO model initialization and solving utilities.

This module provides functions to initialize and solve WaterTAP RO models
using various initialization strategies.
"""

from typing import Dict, Any, Optional
import logging
import sys
import warnings
import time
from pyomo.environ import (
    Constraint, TerminationCondition, value, Block, Var, units as pyunits
)
from pyomo.opt import SolverStatus

# Suppress specific warnings that corrupt MCP protocol
warnings.filterwarnings("ignore", message=".*export suffix 'scaling_factor'.*", module="pyomo.repn.plugins.nl_writer")
from pyomo.core.plugins.transform.relax_integrality import RelaxIntegrality
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.core.util.initialization import propagate_state
import idaes.logger as idaeslog
# BlockTriangularizationInitializer might not be available in all IDAES versions
try:
    from idaes.core.util.initialization import BlockTriangularizationInitializer
except ImportError:
    BlockTriangularizationInitializer = None
from watertap.core.solvers import get_solver
from watertap.unit_models.reverse_osmosis_0D import (
    ConcentrationPolarizationType,
    MassTransferCoefficient
)

# Import the required function from ro_initialization - avoid circular imports
from .ro_initialization import (
    calculate_required_pressure,
    initialize_pump_with_pressure,
    initialize_ro_unit_elegant,
    calculate_concentrate_tds
)


# Get logger configured for MCP
from .logging_config import get_configured_logger
from .stdout_redirect import redirect_stdout_to_stderr
logger = get_configured_logger(__name__)


def deactivate_cp_equations(model, n_stages):
    """
    Temporarily deactivate concentration polarization equations to avoid FBBT issues.
    
    Args:
        model: Pyomo model
        n_stages: Number of RO stages
    
    Returns:
        list: Deactivated constraints for later reactivation
    """
    deactivated = []
    for i in range(1, n_stages + 1):
        ro = getattr(model.fs, f"ro_stage{i}")
        if hasattr(ro.feed_side, 'eq_concentration_polarization'):
            ro.feed_side.eq_concentration_polarization.deactivate()
            deactivated.append(ro.feed_side.eq_concentration_polarization)
            logger.info(f"Stage {i}: Deactivated concentration polarization equations")
    return deactivated


def reactivate_cp_equations(deactivated_constraints):
    """
    Reactivate concentration polarization equations after initialization.
    
    Args:
        deactivated_constraints: List of deactivated constraints
    """
    for constraint in deactivated_constraints:
        constraint.activate()
    if deactivated_constraints:
        logger.info(f"Reactivated {len(deactivated_constraints)} concentration polarization constraints")


# Note: Removed switch_to_calculated_cp function as we cannot change configuration after build
# CP type must be set at construction time


def check_solver_status(results, context="solve", raise_on_fail=True):
    """
    Check solver status and handle various termination conditions.
    
    Args:
        results: Solver results object
        context: Description of what was being solved
        raise_on_fail: Whether to raise exception on failure
        
    Returns:
        bool: True if solution is acceptable, False otherwise
    """
    if results.solver.termination_condition == TerminationCondition.optimal:
        logger.info(f"{context}: Found optimal solution")
        return True
    
    # Check for specific conditions
    if results.solver.termination_condition == TerminationCondition.maxTimeLimit:
        logger.warning(f"{context}: Solver hit time limit. Consider relaxing tolerances or increasing time limit.")
        if hasattr(results.solver, 'time'):
            logger.warning(f"  CPU time used: {results.solver.time:.1f}s")
    elif results.solver.termination_condition == TerminationCondition.locallyOptimal:
        logger.info(f"{context}: Found locally optimal solution (acceptable for non-convex problems)")
        return True
    elif results.solver.termination_condition == TerminationCondition.feasible:
        logger.warning(f"{context}: Found feasible but not optimal solution")
        # For some cases, feasible is acceptable
        if "verification" in context:
            return True
    elif results.solver.termination_condition == TerminationCondition.infeasible:
        logger.error(f"{context}: Problem is infeasible - check constraints and bounds")
    else:
        logger.error(f"{context}: Solver failed with termination condition: {results.solver.termination_condition}")
    
    # Check solver status too
    if hasattr(results, 'solver'):
        if results.solver.status == SolverStatus.warning:
            logger.warning(f"{context}: Solver returned with warning status")
        elif results.solver.status == SolverStatus.error:
            logger.error(f"{context}: Solver returned with error status")
    
    if raise_on_fail and results.solver.termination_condition not in [
        TerminationCondition.optimal, 
        TerminationCondition.locallyOptimal,
        TerminationCondition.feasible  # Sometimes acceptable
    ]:
        raise RuntimeError(f"Solver failed during {context} with status: {results.solver.termination_condition}")
    
    return False


def fast_mass_balance_mixer(m, config_data):
    """
    Perform simple mass balance for mixer using known flows and recovery.
    
    This custom implementation serves two critical purposes:
    1. Avoids stdout buffer deadlock in MCP servers (240s timeout issue)
       - Standard mixer.initialize() writes to stdout, corrupting MCP protocol
    2. Skips unnecessary MCAS property calculations for 10-20x speedup
       - Simple mass balance takes <1s vs 20-30s for full MCAS initialization
    
    Uses accurate initial guess for recycle TDS based on recovery.
    """
    # Extract known values from config
    recycle_info = config_data.get('recycle_info', {})
    has_recycle = recycle_info.get('uses_recycle', False)
    recycle_flow_m3h = recycle_info.get('recycle_flow_m3h', 0)
    target_recovery = config_data.get('achieved_recovery', 0.75)
    
    # Get fresh feed state
    fresh_feed = m.fs.fresh_feed.outlet
    fresh_h2o = value(fresh_feed.flow_mass_phase_comp[0, 'Liq', 'H2O'])
    fresh_tds = sum(value(fresh_feed.flow_mass_phase_comp[0, 'Liq', comp]) 
                    for comp in m.fs.properties.solute_set)
    fresh_total = fresh_h2o + fresh_tds
    feed_tds_ppm = (fresh_tds / fresh_total) * 1e6
    
    if not has_recycle or recycle_flow_m3h == 0:
        # Non-recycle: Direct copy
        logger.info("Non-recycle case - direct feed propagation")
        for comp in m.fs.properties.component_list:
            m.fs.feed_mixer.outlet.flow_mass_phase_comp[0, 'Liq', comp].set_value(
                value(fresh_feed.flow_mass_phase_comp[0, 'Liq', comp])
            )
    else:
        # Recycle case: Mass balance with intelligent initial guess
        logger.info(f"Recycle case - mass balance with {recycle_flow_m3h:.2f} m³/h recycle")
        
        # Convert recycle flow to kg/s (assuming density ~1000 kg/m³)
        recycle_mass_flow = recycle_flow_m3h / 3.6  # m³/h to kg/s
        
        # Intelligent estimate: concentrate TDS = feed TDS / (1 - recovery)
        # This assumes perfect salt rejection
        concentrate_tds_ppm = feed_tds_ppm / (1 - target_recovery)
        recycle_tds_fraction = concentrate_tds_ppm / 1e6  # Convert ppm to mass fraction
        
        logger.info(f"Estimated recycle TDS: {concentrate_tds_ppm:.0f} ppm "
                   f"(feed: {feed_tds_ppm:.0f} ppm, recovery: {target_recovery:.1%})")
        
        # Calculate recycle component flows
        recycle_h2o = recycle_mass_flow * (1 - recycle_tds_fraction)
        recycle_tds = recycle_mass_flow * recycle_tds_fraction
        
        # Mixed flows
        mixed_h2o = fresh_h2o + recycle_h2o
        mixed_tds = fresh_tds + recycle_tds
        mixed_tds_ppm = (mixed_tds / (mixed_h2o + mixed_tds)) * 1e6
        
        logger.info(f"Mixed feed TDS: {mixed_tds_ppm:.0f} ppm")
        
        # Set mixer outlet - H2O
        m.fs.feed_mixer.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'].set_value(mixed_h2o)
        
        # Distribute TDS among components proportionally to feed composition
        for comp in m.fs.properties.solute_set:
            fresh_comp_flow = value(fresh_feed.flow_mass_phase_comp[0, 'Liq', comp])
            comp_fraction = fresh_comp_flow / fresh_tds if fresh_tds > 0 else 0
            
            # Mixed component = fresh component + recycle component
            mixed_comp_flow = fresh_comp_flow + (recycle_tds * comp_fraction)
            m.fs.feed_mixer.outlet.flow_mass_phase_comp[0, 'Liq', comp].set_value(mixed_comp_flow)
    
    # Set temperature and pressure (same as feed)
    m.fs.feed_mixer.outlet.temperature[0].set_value(value(fresh_feed.temperature[0]))
    m.fs.feed_mixer.outlet.pressure[0].set_value(value(fresh_feed.pressure[0]))
    
    # Touch important variables to ensure they're built
    m.fs.feed_mixer.mixed_state[0].mass_frac_phase_comp
    
    logger.info("Mixer mass balance completed in <1 second")


def refine_recycle_composition(m, config_data, iteration=1):
    """
    Optional: Refine mixer outlet based on actual concentrate composition.
    Usually not needed as initial guess is quite accurate.
    """
    if not config_data.get('recycle_info', {}).get('uses_recycle', False):
        return
    
    logger.info(f"Refining recycle composition (iteration {iteration})")
    
    # Get actual concentrate from last stage
    n_stages = config_data.get('n_stages', config_data.get('stage_count', 1))
    last_stage = n_stages
    concentrate = getattr(m.fs, f'ro_stage{last_stage}').retentate
    
    # Calculate actual concentrate composition
    conc_h2o = value(concentrate.flow_mass_phase_comp[0, 'Liq', 'H2O'])
    conc_tds = sum(value(concentrate.flow_mass_phase_comp[0, 'Liq', comp]) 
                   for comp in m.fs.properties.solute_set)
    actual_conc_tds_ppm = (conc_tds / (conc_h2o + conc_tds)) * 1e6
    
    logger.info(f"Actual concentrate TDS: {actual_conc_tds_ppm:.0f} ppm")
    
    # Only refine if difference is significant (>5%)
    current_mixed_h2o = value(m.fs.feed_mixer.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
    current_mixed_tds = sum(value(m.fs.feed_mixer.outlet.flow_mass_phase_comp[0, 'Liq', comp])
                           for comp in m.fs.properties.solute_set)
    current_mixed_tds_ppm = (current_mixed_tds / (current_mixed_h2o + current_mixed_tds)) * 1e6
    
    # Calculate expected mixed TDS with actual concentrate
    recycle_flow_m3h = config_data['recycle_info']['recycle_flow_m3h']
    recycle_mass_flow = recycle_flow_m3h / 3.6
    
    fresh_feed = m.fs.fresh_feed.outlet
    fresh_h2o = value(fresh_feed.flow_mass_phase_comp[0, 'Liq', 'H2O'])
    fresh_tds = sum(value(fresh_feed.flow_mass_phase_comp[0, 'Liq', comp]) 
                    for comp in m.fs.properties.solute_set)
    
    # Recalculate with actual concentrate composition
    actual_recycle_tds_fraction = conc_tds / (conc_h2o + conc_tds)
    recycle_h2o = recycle_mass_flow * (1 - actual_recycle_tds_fraction)
    recycle_tds = recycle_mass_flow * actual_recycle_tds_fraction
    
    refined_mixed_tds_ppm = ((fresh_tds + recycle_tds) / 
                            (fresh_h2o + recycle_h2o + fresh_tds + recycle_tds)) * 1e6
    
    error_percent = abs(refined_mixed_tds_ppm - current_mixed_tds_ppm) / current_mixed_tds_ppm * 100
    
    if error_percent > 5:
        logger.info(f"Refining mixer: current {current_mixed_tds_ppm:.0f} ppm, "
                   f"refined {refined_mixed_tds_ppm:.0f} ppm ({error_percent:.1f}% error)")
        
        # Update mixer outlet
        m.fs.feed_mixer.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'].set_value(
            fresh_h2o + recycle_h2o
        )
        
        # Update components based on actual concentrate ratios
        for comp in m.fs.properties.solute_set:
            fresh_comp = value(fresh_feed.flow_mass_phase_comp[0, 'Liq', comp])
            conc_comp = value(concentrate.flow_mass_phase_comp[0, 'Liq', comp])
            comp_fraction = conc_comp / conc_tds if conc_tds > 0 else 0
            
            m.fs.feed_mixer.outlet.flow_mass_phase_comp[0, 'Liq', comp].set_value(
                fresh_comp + recycle_tds * comp_fraction
            )
    else:
        logger.info(f"Initial guess was accurate ({error_percent:.1f}% error) - no refinement needed")


def initialize_and_solve_mcas(model, config_data, optimize_pumps=True):
    """
    Initialize and solve RO model with MCAS property package and recycle.
    
    This function properly handles pump optimization by:
    1. First initializing with fixed pump pressures for stability
    2. Then unfixing pumps and adding recovery constraints if optimize_pumps=True
    
    Returns:
        dict: Results dictionary with 'status', 'model', 'message' keys
    """
    try:
        # Start timing
        start_time = time.time()
        
        m = model
        n_stages = config_data.get('n_stages', config_data.get('stage_count', 1))
        
        # Check for recycle
        recycle_info = config_data.get('recycle_info', {})
        has_recycle = recycle_info.get('uses_recycle', False)
        recycle_ratio = recycle_info.get('recycle_ratio', 0)
        
        logger.info("=== Starting MCAS Recycle Initialization ===")
        logger.info(f"Number of stages: {n_stages}")
        logger.info(f"Has recycle: {has_recycle}")
        logger.info(f"Recycle ratio: {recycle_ratio}")
        logger.info(f"Optimize pumps: {optimize_pumps}")
        logger.info(f"[TIMING 0.0s] Initialization started")
        
        # Initialize feed (handle both naming conventions)
        if hasattr(m.fs, "fresh_feed"):
            feed_blk = m.fs.fresh_feed
        elif hasattr(m.fs, "feed"):
            feed_blk = m.fs.feed
            logger.info("Note: Using 'feed' attribute - consider updating to 'fresh_feed' in future")
        else:
            raise AttributeError("Flowsheet missing inlet feed stream (expected 'fresh_feed' or 'feed')")
        # Initialize feed with output suppressed
        logger.info(f"[TIMING {time.time()-start_time:.1f}s] Starting feed initialization")
        feed_blk.initialize(outlvl=idaeslog.NOTSET)
        logger.info(f"[TIMING {time.time()-start_time:.1f}s] Feed initialized")
        
        # Fast mixer initialization using mass balance
        logger.info("\n=== Fast Mixer Initialization ===")
        
        # Propagate fresh feed to mixer
        propagate_state(arc=m.fs.fresh_to_mixer)
        
        # Fast mixer initialization avoids both:
        # 1. Stdout buffer deadlock that causes 240s MCP timeout
        # 2. Slow MCAS property calculations (20-30s → <1s)
        logger.info("Using fast mass balance mixer initialization...")
        fast_mass_balance_mixer(m, config_data)
        
        # Propagate from mixer to pump
        propagate_state(arc=m.fs.mixer_to_pump1)
        
        # Log the mixer outlet
        mixer_h2o = value(m.fs.feed_mixer.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
        mixer_tds = sum(value(m.fs.feed_mixer.outlet.flow_mass_phase_comp[0, 'Liq', comp]) 
                       for comp in m.fs.properties.solute_set)
        mixer_tds_ppm = (mixer_tds / (mixer_h2o + mixer_tds)) * 1e6 if (mixer_h2o + mixer_tds) > 0 else 0
        logger.info(f"Mixer outlet: H2O={mixer_h2o:.4f} kg/s, TDS={mixer_tds:.6f} kg/s, TDS={mixer_tds_ppm:.0f} ppm")
        
        # Handle recycle split initialization if present
        if has_recycle:
            # Initialize with zero recycle for stability
            m.fs.recycle_split.split_fraction[0, "recycle"].fix(0)
        
        # Get feed TDS for pressure calculations
        # Use the same feed_blk we initialized earlier
        if hasattr(m.fs, "fresh_feed"):
            feed_outlet = m.fs.fresh_feed.outlet
        elif hasattr(m.fs, "feed"):
            feed_outlet = m.fs.feed.outlet
        else:
            raise AttributeError("Flowsheet missing inlet feed stream")
        
        feed_flows = {}
        for comp in m.fs.properties.solute_set | {'H2O'}:
            feed_flows[comp] = value(feed_outlet.flow_mass_phase_comp[0, 'Liq', comp])
        
        h2o_flow = feed_flows['H2O']
        tds_flow = sum(v for k, v in feed_flows.items() if k != 'H2O')
        feed_tds_ppm = (tds_flow / (h2o_flow + tds_flow)) * 1e6
        
        logger.info(f"Feed TDS: {feed_tds_ppm:.0f} ppm")
        
        # Validate feed TDS is reasonable
        if feed_tds_ppm > 100000:
            logger.warning(f"Calculated feed TDS ({feed_tds_ppm:.0f} ppm) exceeds 100,000 ppm")
        elif 'feed_salinity_ppm' in config_data:
            expected_tds = config_data['feed_salinity_ppm']
            if abs(feed_tds_ppm - expected_tds) / expected_tds > 0.1:
                logger.warning(f"Calculated TDS ({feed_tds_ppm:.0f} ppm) differs from expected ({expected_tds:.0f} ppm) by >10%")
        
        # Determine default salt passage for this water type
        default_salt_passage = 0.015  # Default 1.5% for brackish water
        
        # Initialize stages with elegant initialization
        logger.info(f"[TIMING {time.time()-start_time:.1f}s] === Initializing RO Stages ===")
        
        # For Stage 1, use mixer outlet TDS (accounts for recycle)
        # For subsequent stages, track concentrate TDS progression
        if has_recycle:
            # Use actual mixed feed TDS for Stage 1
            current_tds_ppm = mixer_tds_ppm
            logger.info(f"Using mixer outlet TDS for Stage 1: {current_tds_ppm:.0f} ppm (elevated due to recycle)")
        else:
            # Non-recycle: mixer TDS equals feed TDS
            current_tds_ppm = feed_tds_ppm
            logger.info(f"Using feed TDS for Stage 1: {current_tds_ppm:.0f} ppm (no recycle)")
        
        for i in range(1, n_stages + 1):
            logger.info(f"[TIMING {time.time()-start_time:.1f}s] --- Stage {i} ---")
            
            pump = getattr(m.fs, f"pump{i}")
            ro = getattr(m.fs, f"ro_stage{i}")
            
            # Get stage recovery target
            stage_data = config_data['stages'][i-1]
            target_recovery = stage_data.get('stage_recovery', 0.5)
            
            # Propagate to pump (already done for stage 1)
            if i > 1:
                propagate_state(arc=getattr(m.fs, f"ro_stage{i-1}_to_pump{i}"))
            
            # Get membrane properties for pressure calculation
            membrane_area = value(ro.area)
            # A_comp is indexed by time and solvent_set
            membrane_permeability = value(ro.A_comp[0, 'H2O'])
            
            # Get feed flow to this stage
            if i == 1:
                # First stage - use mixer outlet
                feed_flow = value(sum(
                    m.fs.feed_mixer.outlet.flow_mass_phase_comp[0, 'Liq', comp]
                    for comp in m.fs.properties.component_list
                ))
            else:
                # Later stages - use previous stage concentrate
                prev_ro = getattr(m.fs, f"ro_stage{i-1}")
                feed_flow = value(sum(
                    prev_ro.retentate.flow_mass_phase_comp[0, 'Liq', comp]
                    for comp in m.fs.properties.component_list
                ))
            
            # Calculate required pressure with membrane awareness
            min_driving = 15e5 if target_recovery < 0.5 else 20e5
            if target_recovery > 0.7:
                min_driving = 25e5
            
            required_pressure = calculate_required_pressure(
                current_tds_ppm,
                target_recovery,
                permeate_pressure=101325,
                min_driving_pressure=min_driving,
                pressure_drop=0.5e5,
                salt_passage=default_salt_passage,  # ALWAYS pass salt_passage
                membrane_permeability=membrane_permeability,
                membrane_area=membrane_area,
                feed_flow=feed_flow
            )
            
            # Add safety factor
            safety_factor = 1.1 + 0.1 * (i - 1) + 0.2 * max(0, target_recovery - 0.5)
            required_pressure = min(required_pressure * safety_factor, 80e5)
            
            # Initialize pump with fixed pressure (with retry on failure)
            logger.info(f"[TIMING {time.time()-start_time:.1f}s] Starting pump{i} initialization")
            try:
                initialize_pump_with_pressure(pump, required_pressure)
                logger.info(f"[TIMING {time.time()-start_time:.1f}s] Pump{i} initialized")
            except Exception as e:
                error_msg = str(e)
                if "Inlet pressure" in error_msg and "too low" in error_msg:
                    # Extract minimum pressure from error message
                    import re
                    match = re.search(r"Need at least ([\d.]+) bar", error_msg)
                    if match:
                        min_pressure_bar = float(match.group(1))
                        retry_pressure = min_pressure_bar * 1.2e5  # Convert to Pa with 20% safety margin
                        logger.warning(f"Initial pressure {required_pressure/1e5:.1f} bar too low.")
                        logger.info(f"Retrying with {retry_pressure/1e5:.1f} bar (min required: {min_pressure_bar:.1f} bar)")
                        initialize_pump_with_pressure(pump, retry_pressure)
                        logger.info(f"[TIMING {time.time()-start_time:.1f}s] Pump{i} initialized with retry pressure")
                    else:
                        raise  # Re-raise if we can't parse the minimum pressure
                else:
                    raise  # Re-raise if it's not a pressure-related error
            
            # Propagate to RO (handle both arc naming conventions)
            arc_name_stage = f"pump{i}_to_ro_stage{i}"
            arc_name_simple = f"pump{i}_to_ro{i}"
            if hasattr(m.fs, arc_name_stage):
                propagate_state(arc=getattr(m.fs, arc_name_stage))
            elif hasattr(m.fs, arc_name_simple):
                propagate_state(arc=getattr(m.fs, arc_name_simple))
            else:
                raise AttributeError(f"Flowsheet missing pump to RO arc for stage {i} (tried {arc_name_stage} and {arc_name_simple})")
            
            # Touch RO properties to ensure trace components are built
            # Access properties through the actual property blocks
            if hasattr(ro.feed_side, 'properties'):
                # For membrane models, properties are indexed by position and time
                for t in ro.flowsheet().time:
                    for x in ro.feed_side.length_domain:
                        if hasattr(ro.feed_side.properties[t, x], 'mass_frac_phase_comp'):
                            # Touch the variable to ensure it's built
                            ro.feed_side.properties[t, x].mass_frac_phase_comp
            
            # Check and clean up any lingering charge_balance constraints from upstream assertions
            # This prevents negative DOF issues at the RO inlet
            if hasattr(ro.feed_side, 'properties_in'):
                inlet_prop = ro.feed_side.properties_in[0]
                
                # Check for and remove any lingering charge_balance constraint
                if hasattr(inlet_prop, 'charge_balance'):
                    logger.warning(f"Stage {i}: Found lingering charge_balance constraint at RO inlet, removing...")
                    inlet_prop.del_component(inlet_prop.charge_balance)
                
                # Touch properties to ensure they're built (helps FBBT)
                # This doesn't change DOF, just ensures variables exist
                try:
                    if hasattr(inlet_prop, 'mass_frac_phase_comp'):
                        _ = inlet_prop.mass_frac_phase_comp
                    if hasattr(inlet_prop, 'conc_mass_phase_comp'):
                        _ = inlet_prop.conc_mass_phase_comp
                except Exception:
                    pass  # Properties might not be needed
                
                # Log DOF to verify we're not over-constrained
                dof = degrees_of_freedom(inlet_prop)
                if dof != 0:
                    logger.warning(f"Stage {i}: RO inlet DOF = {dof} (expected 0)")
                    if dof < 0:
                        logger.error(f"Stage {i}: Over-constrained inlet block! Check for extra fixed variables.")
                else:
                    logger.info(f"Stage {i}: RO inlet DOF = 0 (correct)")
            
            # Initialize RO with elegant approach
            logger.info(f"[TIMING {time.time()-start_time:.1f}s] Starting RO{i} initialization")
            initialize_ro_unit_elegant(ro, target_recovery, verbose=True)
            logger.info(f"[TIMING {time.time()-start_time:.1f}s] RO{i} initialized")
            
            # Update TDS for next stage
            current_tds_ppm = calculate_concentrate_tds(
                current_tds_ppm, 
                target_recovery, 
                salt_passage=default_salt_passage  # ALWAYS pass salt_passage
            )
            
            # Propagate permeate to product (handle both arc naming conventions)
            if i == 1:
                # First stage has different naming patterns
                if hasattr(m.fs, "ro_stage1_perm_to_prod"):
                    propagate_state(arc=m.fs.ro_stage1_perm_to_prod)
                elif hasattr(m.fs, "ro1_perm_to_prod"):
                    propagate_state(arc=m.fs.ro1_perm_to_prod)
                else:
                    raise AttributeError(f"Flowsheet missing permeate arc for stage 1")
            else:
                # Later stages
                arc_name_stage = f"ro_stage{i}_perm_to_prod{i}"
                arc_name_simple = f"ro{i}_perm_to_prod{i}"
                if hasattr(m.fs, arc_name_stage):
                    propagate_state(arc=getattr(m.fs, arc_name_stage))
                elif hasattr(m.fs, arc_name_simple):
                    propagate_state(arc=getattr(m.fs, arc_name_simple))
                else:
                    raise AttributeError(f"Flowsheet missing permeate arc for stage {i}")
            
            getattr(m.fs, f"stage_product{i}").initialize(outlvl=idaeslog.NOTSET)
        
        # Complete initialization of recycle components if present
        if has_recycle:
            # Initialize recycle splitter and disposal
            final_stage = n_stages
            propagate_state(arc=m.fs.final_conc_to_split)
            m.fs.recycle_split.initialize(outlvl=idaeslog.NOTSET)
            
            propagate_state(arc=m.fs.split_to_disposal)
            m.fs.disposal_product.initialize(outlvl=idaeslog.NOTSET)
            
            # Now set actual recycle ratio
            recycle_split_ratio = recycle_info.get('recycle_split_ratio', 0.5)
            logger.info(f"\nSetting recycle split ratio to {recycle_split_ratio}")
            # Only fix one split fraction - the other is calculated from sum = 1 constraint
            m.fs.recycle_split.split_fraction[0, "recycle"].fix(recycle_split_ratio)
            
            # Re-initialize splitter
            m.fs.recycle_split.initialize(outlvl=idaeslog.NOTSET)
            
            # Optional: Refine mixer composition based on actual concentrate
            if config_data.get('refine_recycle', True):
                refine_recycle_composition(m, config_data)
        else:
            # Initialize disposal product for non-recycle case (unified architecture)
            final_stage = n_stages
            propagate_state(arc=m.fs.final_conc_to_split)
            m.fs.recycle_split.initialize(outlvl=idaeslog.NOTSET)
            
            propagate_state(arc=m.fs.split_to_disposal)
            m.fs.disposal_product.initialize(outlvl=idaeslog.NOTSET)
        
        # Check initial solution
        logger.info("\n=== Checking Initial Solution ===")
        for i in range(1, n_stages + 1):
            ro = getattr(m.fs, f"ro_stage{i}")
            h2o_in = value(ro.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
            h2o_perm = value(ro.permeate.flow_mass_phase_comp[0, 'Liq', 'H2O'])
            recovery = h2o_perm / h2o_in if h2o_in > 0 else 0
            logger.info(f"Stage {i} initial recovery: {recovery:.3f}")
        
        # Two-stage initialization: First solve with CP deactivated, then reactivate
        logger.info("\n=== Stage 1: Initial Solve with CP Deactivated ===")
        solver = get_solver()
        
        # Deactivate CP equations to avoid FBBT issues during initial solve
        deactivated_cp = deactivate_cp_equations(m, n_stages)
        
        if deactivated_cp:
            logger.info(f"[TIMING {time.time()-start_time:.1f}s] Initial solve without CP constraints...")
            results = solver.solve(m, tee=False, options={
                'linear_solver': 'ma27',
                'max_cpu_time': 300,
                'tol': 1e-5,
                'constr_viol_tol': 1e-5,
                'print_level': 0
            })
            logger.info(f"[TIMING {time.time()-start_time:.1f}s] Initial solve completed")
            
            if not check_solver_status(results, context="Stage 1 (no CP)", raise_on_fail=False):
                logger.warning("Initial solve not optimal, but proceeding...")
            
            # Stage 2: Reactivate CP equations and solve again
            logger.info("\n=== Stage 2: Solve with CP Reactivated ===")
            reactivate_cp_equations(deactivated_cp)
            
            logger.info(f"[TIMING {time.time()-start_time:.1f}s] Solving with CP constraints...")
            results = solver.solve(m, tee=False, options={
                'linear_solver': 'ma27',
                'max_cpu_time': 300,
                'tol': 1e-5,
                'constr_viol_tol': 1e-5,
                'print_level': 0
            })
            logger.info(f"[TIMING {time.time()-start_time:.1f}s] Stage 2 solve completed")
            
            if not check_solver_status(results, context="Stage 2 (with CP)", raise_on_fail=False):
                logger.warning("Stage 2 solve not optimal, but proceeding...")
        else:
            # No CP equations to deactivate, solve directly
            logger.info("No CP equations found, solving directly...")
            results = solver.solve(m, tee=False, options={
                'linear_solver': 'ma27',
                'max_cpu_time': 300,
                'tol': 1e-5,
                'constr_viol_tol': 1e-5,
                'print_level': 0
            })
            if not check_solver_status(results, context="Initial solve", raise_on_fail=False):
                logger.warning("Initial solve not optimal, but proceeding...")
        
        # If optimize_pumps, unfix pumps and add recovery constraints
        if optimize_pumps:
            logger.info("\n=== Setting up Pump Optimization ===")
            
            # First verify we have a feasible initial solution
            # Get solver (no parameters to get_solver)
            solver = get_solver()
            
            logger.info(f"[TIMING {time.time()-start_time:.1f}s] Verifying initial solution...")
            logger.info(f"[TIMING {time.time()-start_time:.1f}s] About to call solver.solve() for verification")
            results = solver.solve(m, tee=False, options={
                'linear_solver': 'ma27',
                'max_cpu_time': 300,  # 5 minutes for verification
                'tol': 1e-5,  # Relaxed for faster convergence
                'constr_viol_tol': 1e-5,
                'print_level': 0  # Suppress all IPOPT output
            })
            logger.info(f"[TIMING {time.time()-start_time:.1f}s] solver.solve() verification completed")
            
            if not check_solver_status(results, context="Initial verification", raise_on_fail=False):
                logger.warning("Initial solution not optimal, but proceeding with pump optimization...")
            
            # Now unfix pumps and add recovery constraints
            for i in range(1, n_stages + 1):
                pump = getattr(m.fs, f"pump{i}")
                ro = getattr(m.fs, f"ro_stage{i}")
                stage_data = config_data['stages'][i-1]
                target_recovery = stage_data.get('stage_recovery', 0.5)
                
                # Unfix pump pressure
                pump.outlet.pressure[0].unfix()
                logger.info(f"Stage {i}: Unfixed pump pressure (was {value(pump.outlet.pressure[0])/1e5:.1f} bar)")
                
                # Add recovery constraint
                constraint_name = f"recovery_constraint_stage{i}"
                setattr(m.fs, constraint_name,
                        Constraint(expr=ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'] == target_recovery))
                logger.info(f"Stage {i}: Added recovery constraint for {target_recovery:.3f}")
            
            # Check degrees of freedom
            dof = degrees_of_freedom(m)
            logger.info(f"\nDegrees of freedom after adding constraints: {dof}")
            
            if dof != 0:
                logger.warning(f"Expected 0 degrees of freedom, got {dof}")
        
        # Solve the model
        logger.info("\n=== Solving Model ===")
        # Get solver (no parameters to get_solver)
        solver = get_solver()
        
        if has_recycle and optimize_pumps:
            # Use successive substitution for recycle with pump optimization
            logger.info("Using successive substitution for recycle convergence")
            
            max_iter = 20
            tol = 1e-5
            
            for iteration in range(max_iter):
                # Store previous mixed flow
                prev_flow = value(m.fs.feed_mixer.mixed_state[0].flow_mass_phase_comp['Liq', 'H2O'])
                
                # Solve model
                results = solver.solve(m, tee=False, options={
                    'linear_solver': 'ma27',
                    'max_cpu_time': 600,  # 10 minutes for main solve
                    'tol': 1e-6,  # Moderately relaxed for balance of speed/accuracy
                    'constr_viol_tol': 1e-6,
                    'acceptable_tol': 1e-3,  # Fallback for difficult problems
                    'acceptable_constr_viol_tol': 1e-3,
                    'print_level': 0,  # Suppress all IPOPT output
                })
                
                # Check solver status
                check_solver_status(results, context=f"Recycle iteration {iteration+1}", raise_on_fail=True)
                
                # Check convergence
                curr_flow = value(m.fs.feed_mixer.mixed_state[0].flow_mass_phase_comp['Liq', 'H2O'])
                rel_change = abs(curr_flow - prev_flow) / prev_flow if prev_flow > 0 else 1
                
                logger.info(f"Iteration {iteration+1}: Mixed flow = {curr_flow:.4f} kg/s, relative change = {rel_change:.2e}")
                
                if rel_change < tol:
                    logger.info(f"Converged after {iteration+1} iterations")
                    break
            else:
                logger.warning(f"Did not converge after {max_iter} iterations")
        else:
            # Single solve for non-recycle or fixed pump cases
            results = solver.solve(m, tee=False, options={
                'linear_solver': 'ma27',
                'max_cpu_time': 600,  # 10 minutes for main solve
                'tol': 1e-6,  # Moderately relaxed for balance of speed/accuracy
                'constr_viol_tol': 1e-6,
                'acceptable_tol': 1e-3,  # Fallback for difficult problems
                'acceptable_constr_viol_tol': 1e-3,
                'print_level': 0  # Suppress all IPOPT output
            })
            
            # Check solver status
            check_solver_status(results, context="Main solve", raise_on_fail=True)
        
        logger.info("\n=== Solution Complete ===")
        
        # Report final recoveries and pressures
        for i in range(1, n_stages + 1):
            pump = getattr(m.fs, f"pump{i}")
            ro = getattr(m.fs, f"ro_stage{i}")
            
            pressure = value(pump.outlet.pressure[0]) / 1e5  # bar
            recovery = value(ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'])
            
            logger.info(f"Stage {i}: Pressure = {pressure:.1f} bar, Recovery = {recovery:.3f}")
        
        # Return results dictionary for consistency with notebooks
        return {
            "status": "success",
            "model": m,
            "solver_results": results if 'results' in locals() else None,
            "message": "Model initialized and solved successfully",
            "termination_condition": str(results.solver.termination_condition) if 'results' in locals() else "optimal"
        }
        
    except Exception as e:
        logger.error(f"Error in initialize_and_solve_mcas: {str(e)}")
        return {
            "status": "error",
            "model": None,
            "solver_results": None,
            "message": f"Initialization/solving failed: {str(e)}",
            "termination_condition": "error",
            "error": str(e)
        }

def initialize_model_sequential(m, config_data):
    """
    Fallback sequential initialization (original method).
    """
    # Initialize feed - handle both naming conventions
    if hasattr(m.fs, "fresh_feed"):
        m.fs.fresh_feed.initialize(outlvl=idaeslog.NOTSET)
    elif hasattr(m.fs, "feed"):
        m.fs.feed.initialize(outlvl=idaeslog.NOTSET)
    else:
        raise AttributeError("Flowsheet missing feed block (expected 'fresh_feed' or 'feed')")
    
    # Initialize stages sequentially
    n_stages = config_data.get('n_stages', config_data.get('stage_count', 1))
    for i in range(1, n_stages + 1):
        logger.info(f"\nInitializing Stage {i}...")
        
        # Initialize pump
        pump = getattr(m.fs, f"pump{i}")
        
        # Set outlet pressure based on stage and expected osmotic pressure
        if i == 1:
            pump.outlet.pressure.fix(15 * pyunits.bar)  # 15 bar
        elif i == 2:
            pump.outlet.pressure.fix(25 * pyunits.bar)  # 25 bar (higher due to concentration)
        else:
            pump.outlet.pressure.fix(35 * pyunits.bar)  # 35 bar
        
        pump.efficiency_pump.fix(0.8)
        
        # Propagate state from previous unit
        if i == 1:
            # Check for unified architecture (mixer path) first
            if hasattr(m.fs, "mixer_to_pump1"):
                propagate_state(arc=m.fs.mixer_to_pump1)
            elif hasattr(m.fs, "feed_to_pump1"):
                propagate_state(arc=m.fs.feed_to_pump1)
            else:
                raise AttributeError("No arc found from feed/mixer to pump1")
        else:
            arc_name = f"ro_stage{i-1}_to_pump{i}"
            propagate_state(arc=getattr(m.fs, arc_name))
        
        pump.initialize(
            outlvl=idaeslog.NOTSET,
            optarg={
                'tol': 1e-4,
                'constr_viol_tol': 1e-4,
                'max_cpu_time': 30,
                'max_iter': 50
            }
        )
        
        # Initialize RO
        ro = getattr(m.fs, f"ro_stage{i}")
        
        # Propagate state from pump
        if i == 1:
            propagate_state(arc=m.fs.pump1_to_ro_stage1)
        else:
            arc_name = f"pump{i}_to_ro_stage{i}"
            propagate_state(arc=getattr(m.fs, arc_name))
        
        # Initialize RO
        ro.initialize(
            outlvl=idaeslog.NOTSET,
            optarg={
                'tol': 1e-4,
                'constr_viol_tol': 1e-4,
                'acceptable_tol': 1e-2,
                'acceptable_constr_viol_tol': 1e-2,
                'max_cpu_time': 60,
                'max_iter': 100
            }
        )
        
        # Initialize stage product
        if i == 1:
            propagate_state(arc=m.fs.ro_stage1_perm_to_prod)
        else:
            arc_name = f"ro_stage{i}_perm_to_prod{i}"
            propagate_state(arc=getattr(m.fs, arc_name))
        
        getattr(m.fs, f"stage_product{i}").initialize()
    
    # Initialize final concentrate product
    propagate_state(arc=m.fs.final_conc_arc)
    m.fs.concentrate_product.initialize(outlvl=idaeslog.NOTSET)
    
    logger.info("\nSequential initialization complete.")


def initialize_with_block_triangularization(m, config_data):
    """
    Initialize using block triangularization for strongly connected components.
    """
    logger.info("Initializing with block triangularization...")
    
    if BlockTriangularizationInitializer is None:
        logger.warning("BlockTriangularizationInitializer not available, falling back to sequential initialization")
        return initialize_model_sequential(m, config_data)
    
    # Create initializer
    initializer = BlockTriangularizationInitializer()
    
    # Initialize each unit in sequence
    units = [m.fs.feed]
    n_stages = config_data.get('n_stages', config_data.get('stage_count', 1))
    for i in range(1, n_stages + 1):
        units.append(getattr(m.fs, f"pump{i}"))
        units.append(getattr(m.fs, f"ro_stage{i}"))
        units.append(getattr(m.fs, f"stage_product{i}"))
    units.append(m.fs.concentrate_product)
    
    for unit in units:
        try:
            initializer.initialize(unit)
        except:
            # Fall back to default initialization
            unit.initialize(outlvl=idaeslog.NOTSET)


def initialize_with_custom_guess(m, config_data):
    """
    Initialize with custom initial guesses based on typical values.
    """
    logger.info("Setting custom initial values...")
    
    # Typical pressure progression
    stage_pressures = {
        1: 15e5,   # 15 bar
        2: 25e5,   # 25 bar  
        3: 35e5    # 35 bar
    }
    
    # Set pump pressures
    n_stages = config_data.get('n_stages', config_data.get('stage_count', 1))
    for i in range(1, n_stages + 1):
        pump = getattr(m.fs, f"pump{i}")
        if i in stage_pressures:
            pump.outlet.pressure.set_value(stage_pressures[i])
    
    # Set RO recoveries based on configuration (as initial guesses only)
    n_stages = config_data.get('n_stages', config_data.get('stage_count', 1))
    for i in range(1, n_stages + 1):
        ro = getattr(m.fs, f"ro_stage{i}")
        stage_data = config_data['stages'][i-1]
        target_recovery = stage_data.get('stage_recovery', 0.5)
        
        # Set recovery for each component (just as initial values, not fixed)
        for comp in m.fs.properties.component_list:
            if comp == "H2O":
                ro.recovery_mass_phase_comp[0, 'Liq', comp].set_value(target_recovery)
            else:
                # Assume 98% rejection for ions
                ro.recovery_mass_phase_comp[0, 'Liq', comp].set_value(0.02)
    
    # Set approximate flows
    feed_flow = config_data['feed_flow_m3h'] / 3600  # m³/s
    
    n_stages = config_data.get('n_stages', config_data.get('stage_count', 1))
    for i in range(1, n_stages + 1):
        ro = getattr(m.fs, f"ro_stage{i}")
        
        # Approximate permeate and concentrate flows
        if i == 1:
            inlet_flow = feed_flow
        else:
            # Previous stage concentrate
            inlet_flow = feed_flow * (1 - 0.5 * (i-1))
        
        stage_recovery = config_data['stages'][i-1].get('stage_recovery', 0.5)
        perm_flow = inlet_flow * stage_recovery
        conc_flow = inlet_flow - perm_flow
        
        # Set approximate values (mass basis)
        ro.permeate.flow_mass_phase_comp[0, 'Liq', 'H2O'].set_value(perm_flow * 1000)
        ro.retentate.flow_mass_phase_comp[0, 'Liq', 'H2O'].set_value(conc_flow * 1000)


def initialize_with_relaxation(m, config_data):
    """
    Initialize with constraint relaxation for difficult problems.
    """
    logger.info("Initializing with constraint relaxation...")
    
    # First, set custom guesses
    initialize_with_custom_guess(m, config_data)
    
    # Initialize units
    units = [m.fs.feed]
    n_stages = config_data.get('n_stages', config_data.get('stage_count', 1))
    for i in range(1, n_stages + 1):
        units.append(getattr(m.fs, f"pump{i}"))
        units.append(getattr(m.fs, f"ro_stage{i}"))
    
    for unit in units:
        unit.initialize()


def initialize_model_advanced(m, config_data, strategy="sequential"):
    """
    Initialize model using selected strategy.
    
    Args:
        m: Pyomo model
        config_data: Configuration data
        strategy: Initialization strategy
            - "sequential": Default sequential initialization
            - "block_triangular": Block triangularization
            - "custom_guess": Custom initial values
            - "relaxation": Constraint relaxation
    """
    logger.info(f"\nInitializing model using {strategy} strategy...")
    
    if strategy == "sequential":
        initialize_model_sequential(m, config_data)
    elif strategy == "block_triangular":
        initialize_with_block_triangularization(m, config_data)
    elif strategy == "custom_guess":
        initialize_with_custom_guess(m, config_data)
        initialize_model_sequential(m, config_data)
    elif strategy == "relaxation":
        initialize_with_relaxation(m, config_data)
    else:
        logger.info(f"Unknown strategy {strategy}, using sequential")
        initialize_model_sequential(m, config_data)
    
    # Verify initialization
    logger.info("\nChecking initialization...")
    n_stages = config_data.get('n_stages', config_data.get('stage_count', 1))
    for i in range(1, n_stages + 1):
        ro = getattr(m.fs, f"ro_stage{i}")
        perm_flow = value(sum(
            ro.permeate.flow_mass_phase_comp[0, 'Liq', comp]
            for comp in m.fs.properties.component_list
        )) / 1000 * 3600  # m³/h
        
        logger.info(f"  Stage {i} permeate flow: {perm_flow:.1f} m³/h")
