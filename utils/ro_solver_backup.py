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
    Constraint, TerminationCondition, value, Block, Var, units as pyunits,
    Objective, minimize, Param, RangeSet, NonNegativeReals
)
from pyomo.opt import SolverStatus
from idaes.core.util.scaling import calculate_scaling_factors

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
    calculate_concentrate_tds,
    calculate_osmotic_pressure
)

# Get logger configured for MCP - MUST be before using logger
from .logging_config import get_configured_logger
from .stdout_redirect import redirect_stdout_to_stderr
logger = get_configured_logger(__name__)

# Import interval_initializer for FBBT robustness
try:
    from watertap.core.util.initialization import interval_initializer
    import inspect
    # Check if interval_initializer supports bound_push parameter
    sig = inspect.signature(interval_initializer)
    interval_initializer_supports_bound_push = "bound_push" in sig.parameters
    logger.info(f"interval_initializer available, bound_push support: {interval_initializer_supports_bound_push}")
except ImportError:
    interval_initializer = None
    interval_initializer_supports_bound_push = False
    logger.warning("interval_initializer not available - FBBT robustness reduced")


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


def check_solver_status(results, context="solve", raise_on_fail=True, m=None, n_stages=None, allow_feasible=False):
    """
    Check solver status and handle various termination conditions.

    Args:
        results: Solver results object
        context: Description of what was being solved
        raise_on_fail: Whether to raise exception on failure
        m: Model object for diagnostic output (optional)
        n_stages: Number of stages for diagnostic output (optional)
        allow_feasible: Whether to accept feasible (non-optimal) solutions

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
        if allow_feasible:
            logger.info(f"  Accepting feasible solution (allow_feasible=True)")
            return True
        # For some cases, feasible is acceptable
        if "verification" in context:
            return True
        return False
    elif results.solver.termination_condition == TerminationCondition.infeasible:
        logger.error(f"{context}: Problem is infeasible - check constraints and bounds")
    elif results.solver.termination_condition == TerminationCondition.other:
        # AMPL evaluation error - add diagnostic output
        logger.error(f"{context}: AMPL evaluation error detected - checking for problematic values:")

        if m and n_stages:
            # Diagnostic output for AMPL errors
            for i in range(1, n_stages + 1):
                try:
                    pump = getattr(m.fs, f"pump{i}")
                    ro = getattr(m.fs, f"ro_stage{i}")

                    # Log pressure differential
                    feed_pressure = value(ro.inlet.pressure[0])
                    logger.error(f"Stage {i} feed pressure: {feed_pressure/1e5:.2f} bar")

                    # Check for problematic concentrations
                    for x in ro.feed_side.length_domain:
                        if hasattr(ro.feed_side.properties[0, x], 'conc_mass_phase_comp'):
                            for comp in m.fs.properties.solute_set:
                                try:
                                    conc = value(ro.feed_side.properties[0, x].conc_mass_phase_comp['Liq', comp])
                                    if conc <= 0 or conc > 1000:  # kg/m³
                                        logger.error(f"Stage {i} problematic {comp} concentration at x={x}: {conc:.3e} kg/m³")
                                except:
                                    logger.error(f"Stage {i} could not evaluate concentration for {comp} at x={x}")

                    # Check osmotic vs feed pressure
                    if hasattr(ro, 'feed_side'):
                        try:
                            osmotic_in = value(ro.feed_side.properties[0, 0].pressure_osm_phase['Liq'])
                            delta_p = feed_pressure - osmotic_in
                            logger.error(f"Stage {i} ΔP - Δπ = {delta_p/1e5:.2f} bar (must be positive)")
                            if delta_p < 0:
                                logger.error(f"Stage {i} ERROR: Negative driving pressure!")
                        except:
                            logger.error(f"Stage {i} could not evaluate osmotic pressure")

                except Exception as e:
                    logger.error(f"Stage {i} diagnostic error: {str(e)}")
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
    # Add try-catch to identify AMPL errors
    try:
        # Check total flow is reasonable before touching mass fractions
        total_flow = sum(value(m.fs.feed_mixer.outlet.flow_mass_phase_comp[0, 'Liq', comp])
                        for comp in m.fs.properties.component_list)
        logger.info(f"Mixer outlet total flow: {total_flow:.4f} kg/s")

        if total_flow < 1e-6:
            logger.error(f"ERROR: Mixer total flow too low: {total_flow:.2e} kg/s")
            raise ValueError("Mixer outlet flow is near zero - check mass balance")

        # Only touch mass_frac if total flow is reasonable
        m.fs.feed_mixer.mixed_state[0].mass_frac_phase_comp
    except Exception as e:
        logger.error(f"\n=== MIXER INITIALIZATION ERROR ===")
        logger.error(f"Error touching mass_frac_phase_comp: {str(e)}")

        # Log component flows for debugging
        for comp in m.fs.properties.component_list:
            flow_val = value(m.fs.feed_mixer.outlet.flow_mass_phase_comp[0, 'Liq', comp])
            logger.error(f"  {comp}: {flow_val:.4e} kg/s")

        # Check inlet flows
        fresh_total = sum(value(m.fs.feed_mixer.fresh.flow_mass_phase_comp[0, 'Liq', comp])
                         for comp in m.fs.properties.component_list)
        logger.error(f"Fresh inlet total: {fresh_total:.4f} kg/s")

        if has_recycle:
            recycle_total = sum(value(m.fs.feed_mixer.recycle.flow_mass_phase_comp[0, 'Liq', comp])
                               for comp in m.fs.properties.component_list)
            logger.error(f"Recycle inlet total: {recycle_total:.4f} kg/s")

        raise  # Re-raise to maintain error handling

    logger.info("Mixer mass balance completed in <1 second")

    # Deactivate mixer pressure constraint for recycle cases
    # This prevents over-constraining the system with recycle
    if hasattr(m.fs, 'mixer_pressure_constraint'):
        if recycle_flow_m3h > 0:
            # Ensure mixer outlet pressure is bounded before deactivating
            # This prevents unbounded behavior when pump inlet is unconstrained
            m.fs.feed_mixer.outlet.pressure[0].setlb(1e5)  # Min 1 bar
            m.fs.feed_mixer.outlet.pressure[0].setub(50e5)  # Max 50 bar
            m.fs.mixer_pressure_constraint.deactivate()
            logger.info("Deactivated mixer pressure constraint with bounded outlet pressure [1-50 bar]")


def initialize_erd_if_present(m, n_stages):
    """
    Initialize ERD if present in flowsheet, otherwise use standard arc.
    
    Args:
        m: Pyomo model
        n_stages: Number of RO stages
    """
    from pyomo.environ import value
    from pyomo.environ import units as pyunits
    
    if not hasattr(m.fs, "erd"):
        # No ERD; use the standard arc
        propagate_state(arc=m.fs.final_conc_to_split)
        return
    
    logger.info("Initializing Energy Recovery Device...")
    
    # Brine side from last RO stage
    propagate_state(arc=m.fs.last_stage_to_erd)
    
    # Build feed side: equal flow, lower pressure than brine
    br_in = m.fs.erd.brine_inlet
    feed_src = m.fs.erd_feed_source.outlet
    
    # Copy mass flows to ensure volumetric equality (MCAS is mass-basis)
    for comp in m.fs.properties.component_list:
        feed_src.flow_mass_phase_comp[0, 'Liq', comp].set_value(
            value(br_in.flow_mass_phase_comp[0, 'Liq', comp])
        )
    
    # Low pressure and sensible temperature
    feed_src.pressure[0].set_value(pyunits.convert(1*pyunits.atm, to_units=pyunits.Pa))
    feed_src.temperature[0].set_value(value(m.fs.fresh_feed.outlet.temperature[0]))
    
    # Initialize feed source
    m.fs.erd_feed_source.initialize(outlvl=idaeslog.NOTSET)
    
    # Push feed state into ERD
    propagate_state(arc=m.fs.erd_feed_to_erd)
    
    # Initialize ERD
    m.fs.erd.initialize(outlvl=idaeslog.NOTSET)
    
    # Propagate ERD outlets forward
    propagate_state(arc=m.fs.erd_to_split)
    propagate_state(arc=m.fs.erd_out_to_product)
    m.fs.erd_product.initialize(outlvl=idaeslog.NOTSET)
    
    logger.info("ERD initialization complete")


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


def initialize_and_solve_mcas(model, config_data, optimize_pumps=True, use_staged_solve=True):
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

        progressive_tolerances = config_data.get(
            'progressive_recovery_tolerances',
            [0.10, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.025, 0.02, 0.015, 0.01]
        )
        # Guarantee descending order to avoid tightening in the wrong direction
        if progressive_tolerances and progressive_tolerances[0] < progressive_tolerances[-1]:
            progressive_tolerances = list(reversed(progressive_tolerances))
        if not progressive_tolerances:
            progressive_tolerances = [0.10, 0.01]
        final_recovery_tolerance = progressive_tolerances[-1]
        
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

        # Initialize recycle inlet if present
        if has_recycle:
            recycle_info = config_data.get('recycle_info', {})
            recycle_flow_m3h = recycle_info.get('recycle_flow_m3h', 0)

            if recycle_flow_m3h > 0:
                # Initialize recycle inlet with concentrate-like composition
                # Use recovery to estimate concentrate TDS
                target_recovery = config_data.get('achieved_recovery', 0.75)

                # Get fresh feed values
                fresh_h2o = value(m.fs.feed_mixer.fresh.flow_mass_phase_comp[0, 'Liq', 'H2O'])
                fresh_tds = sum(value(m.fs.feed_mixer.fresh.flow_mass_phase_comp[0, 'Liq', comp])
                               for comp in m.fs.properties.solute_set)
                fresh_total = fresh_h2o + fresh_tds
                feed_tds_ppm = (fresh_tds / fresh_total) * 1e6 if fresh_total > 0 else 5000

                # Estimate concentrate TDS
                concentrate_tds_ppm = feed_tds_ppm / max(0.1, (1 - target_recovery))
                recycle_tds_fraction = min(0.1, concentrate_tds_ppm / 1e6)  # Cap at 10% for stability

                # Convert recycle flow to kg/s
                recycle_mass_flow = recycle_flow_m3h / 3.6  # m³/h to kg/s

                # Set recycle inlet flows
                recycle_h2o = recycle_mass_flow * (1 - recycle_tds_fraction)
                recycle_tds = recycle_mass_flow * recycle_tds_fraction

                # Set H2O
                m.fs.feed_mixer.recycle.flow_mass_phase_comp[0, 'Liq', 'H2O'].set_value(recycle_h2o)

                # Distribute TDS proportionally
                for comp in m.fs.properties.solute_set:
                    fresh_comp = value(m.fs.feed_mixer.fresh.flow_mass_phase_comp[0, 'Liq', comp])
                    comp_fraction = fresh_comp / fresh_tds if fresh_tds > 0 else 1.0 / len(m.fs.properties.solute_set)
                    m.fs.feed_mixer.recycle.flow_mass_phase_comp[0, 'Liq', comp].set_value(
                        recycle_tds * comp_fraction
                    )

                # Set T and P same as fresh
                m.fs.feed_mixer.recycle.temperature[0].set_value(
                    value(m.fs.feed_mixer.fresh.temperature[0])
                )
                m.fs.feed_mixer.recycle.pressure[0].set_value(
                    value(m.fs.feed_mixer.fresh.pressure[0])
                )

                logger.info(f"Initialized recycle inlet: {recycle_flow_m3h:.2f} m³/h, "
                           f"TDS ≈ {concentrate_tds_ppm:.0f} ppm")
            else:
                # Zero recycle flow
                for comp in m.fs.properties.component_list:
                    m.fs.feed_mixer.recycle.flow_mass_phase_comp[0, 'Liq', comp].set_value(0)
                m.fs.feed_mixer.recycle.temperature[0].set_value(298.15)
                m.fs.feed_mixer.recycle.pressure[0].set_value(101325)
                logger.info("Initialized recycle inlet with zero flow")

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
        # Use lower salt passage for seawater membranes
        membrane_type = config_data.get('membrane_type', getattr(m, 'membrane_type', 'brackish'))
        if membrane_type == 'seawater' or feed_tds_ppm >= 30000:
            default_salt_passage = 0.005  # 0.5% typical for SWRO
        else:
            default_salt_passage = 0.015  # 1.5% for brackish RO
        
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
        
        # Apply scaling factors once after at least the first pump is initialized
        scaling_applied = False

        for i in range(1, n_stages + 1):
            logger.info(f"[TIMING {time.time()-start_time:.1f}s] --- Stage {i} ---")

            pump = getattr(m.fs, f"pump{i}")
            ro = getattr(m.fs, f"ro_stage{i}")

            # Get stage recovery target
            stage_data = config_data['stages'][i-1]
            target_recovery = stage_data.get('stage_recovery', 0.5)

            # For downstream stages, calculate actual concentrate TDS from previous stage
            if i > 1:
                # Calculate actual TDS from previous stage concentrate
                prev_stage_recovery = config_data['stages'][i-2].get('stage_recovery', 0.5)
                prev_stage_salt_passage = default_salt_passage

                # Update TDS based on previous stage concentration
                prev_concentrate_tds = calculate_concentrate_tds(
                    current_tds_ppm,
                    prev_stage_recovery,
                    salt_passage=prev_stage_salt_passage
                )
                current_tds_ppm = prev_concentrate_tds
                logger.info(f"Stage {i}: Updated TDS from Stage {i-1} concentrate: {current_tds_ppm:.0f} ppm")

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
            
            configured_pressure_bar = stage_data.get('feed_pressure_bar')

            if configured_pressure_bar is not None and configured_pressure_bar > 0:
                required_pressure = configured_pressure_bar * 1e5
                logger.info(
                    f"Stage {i}: Using configured feed pressure {configured_pressure_bar:.2f} bar from optimization"
                )
                pressure_factor = 1.02  # Small cushion only
            else:
                # Calculate expected flux to determine a realistic minimum driving pressure
                expected_flux_lmh = None
                if stage_data.get('permeate_flow_m3h') and membrane_area > 0:
                    expected_flux_lmh = (stage_data['permeate_flow_m3h'] / membrane_area) * 1000.0
                elif stage_data.get('stage_recovery') and stage_data.get('feed_flow_m3h') and membrane_area > 0:
                    expected_flux_lmh = (
                        stage_data['feed_flow_m3h'] * stage_data['stage_recovery'] * 1000.0 / membrane_area
                    )

                if expected_flux_lmh and expected_flux_lmh > 0 and membrane_permeability > 0:
                    jw_vol = expected_flux_lmh / 1000.0 / 3600.0  # Convert LMH to m/s
                    min_driving_pressure = max(2e5, jw_vol / membrane_permeability)  # Pa
                else:
                    min_driving_pressure = 5e5  # 5 bar fallback

                required_pressure = calculate_required_pressure(
                    current_tds_ppm,
                    target_recovery,
                    permeate_pressure=101325,
                    min_driving_pressure=min_driving_pressure,
                    pressure_drop=0.5e5,
                    salt_passage=default_salt_passage,
                    membrane_permeability=membrane_permeability,
                    membrane_area=membrane_area,
                    feed_flow=feed_flow,
                    stage_number=i
                )

                if i > 1:
                    # Higher pressure factor for concentrated brine in downstream stages
                    pressure_factor = 1.5  # Increased from 1.15 to handle higher TDS
                    logger.info(f"Applying {pressure_factor:.2f}x pressure safety factor for downstream stage {i} (concentrated brine)")
                elif current_tds_ppm >= 7000:
                    pressure_factor = 1.15
                    logger.info(
                        f"Applying {pressure_factor:.2f}x pressure factor for high TDS Stage {i} ({current_tds_ppm:.0f} ppm)"
                    )
                else:
                    pressure_factor = 1.05

            required_pressure = required_pressure * pressure_factor

            # Add safeguard for minimum NDP (Net Driving Pressure)
            osmotic_pressure = calculate_osmotic_pressure(current_tds_ppm)
            min_safe_pressure = osmotic_pressure + 2e5  # 2 bar minimum NDP

            if required_pressure < min_safe_pressure:
                logger.warning(
                    f"Stage {i}: Calculated pressure {required_pressure/1e5:.1f} bar < safe minimum "
                    f"{min_safe_pressure/1e5:.1f} bar (osmotic: {osmotic_pressure/1e5:.1f} bar)"
                )
                required_pressure = min_safe_pressure

            max_bar = 120.0 if membrane_type == 'seawater' else 80.0
            required_pressure = min(required_pressure, max_bar * 1e5)
            
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

            # Apply scaling AFTER first pump initialization but BEFORE RO initialization
            # This ensures proper pressure values exist for scaling calculations
            if not scaling_applied and i == 1:
                try:
                    from idaes.core.util.scaling import calculate_scaling_factors
                    logger.info(f"[TIMING {time.time()-start_time:.1f}s] Applying scaling factors after pump1 initialization")
                    calculate_scaling_factors(m)
                    scaling_applied = True
                    logger.info("Scaling factors applied - subsequent RO stages will initialize with scaled constraints")
                except Exception as _e:
                    logger.warning(f"Could not calculate scaling factors: {_e}")

            # Propagate to RO (handle both arc naming conventions)
            arc_name_stage = f"pump{i}_to_ro_stage{i}"
            arc_name_simple = f"pump{i}_to_ro{i}"
            if hasattr(m.fs, arc_name_stage):
                propagate_state(arc=getattr(m.fs, arc_name_stage))
            elif hasattr(m.fs, arc_name_simple):
                propagate_state(arc=getattr(m.fs, arc_name_simple))
            else:
                raise AttributeError(f"Flowsheet missing pump to RO arc for stage {i} (tried {arc_name_stage} and {arc_name_simple})")
            
            # Apply interval_initializer for FBBT robustness before RO initialization
            # For high-TDS stages or later stages, interval FBBT can over-tighten bounds and hurt convergence.
            # Use it for Stage 1 (or low-TDS) only; skip for Stage >=2 or high TDS.
            if interval_initializer is not None:
                if i == 1 and current_tds_ppm < 10000:
                    logger.info(f"[TIMING {time.time()-start_time:.1f}s] Applying interval_initializer for stage {i}")
                    try:
                        # Apply to RO unit with reasonable tolerances
                        # Check signature to avoid TypeError with different WaterTAP versions
                        kwargs = {"feasibility_tol": 1e-7}
                        if interval_initializer_supports_bound_push:
                            kwargs["bound_push"] = 1e-7
                        interval_initializer(ro, **kwargs)
                        logger.info(f"Stage {i}: interval_initializer applied successfully")
                    except Exception as e:
                        logger.warning(f"Stage {i}: interval_initializer failed: {e}")
                        # Continue without it - not critical
                else:
                    logger.info(f"Skipping interval_initializer for stage {i} (later stage or high TDS)")
            
            # Touch RO properties to ensure trace components are built
            # Access properties through the actual property blocks
            if hasattr(ro.feed_side, 'properties'):
                # For membrane models, properties are indexed by position and time
                for t in ro.flowsheet().time:
                    for x in ro.feed_side.length_domain:
                        if hasattr(ro.feed_side.properties[t, x], 'mass_frac_phase_comp'):
                            # Touch the variable to ensure it's built
                            ro.feed_side.properties[t, x].mass_frac_phase_comp
            
            # Touch inlet-side properties to ensure they're built (helps FBBT)
            # Do NOT delete MCAS charge_balance constraints; they are required for electroneutrality
            if hasattr(ro.feed_side, 'properties_in'):
                inlet_prop = ro.feed_side.properties_in[0]
                try:
                    if hasattr(inlet_prop, 'mass_frac_phase_comp'):
                        _ = inlet_prop.mass_frac_phase_comp
                    if hasattr(inlet_prop, 'conc_mass_phase_comp'):
                        _ = inlet_prop.conc_mass_phase_comp
                except Exception:
                    pass  # Properties might not be needed
                # Log DOF to verify we're not over/under-constrained
                try:
                    dof = degrees_of_freedom(inlet_prop)
                    logger.info(f"Stage {i}: RO inlet DOF = {dof}")
                except Exception:
                    pass
            
            # Initialize RO with elegant approach, with a fallback relaxation for robustness
            logger.info(f"[TIMING {time.time()-start_time:.1f}s] Starting RO{i} initialization")
            # For high-TDS stages, initialize with CP temporarily deactivated to avoid FBBT conflicts
            cp_temp_deactivated = False
            try:
                if current_tds_ppm >= 10000 and hasattr(ro.feed_side, 'eq_concentration_polarization'):
                    try:
                        ro.feed_side.eq_concentration_polarization.deactivate()
                        cp_temp_deactivated = True
                        logger.info(f"Stage {i}: Temporarily deactivated CP equations for initialization")
                    except Exception as _e:
                        logger.debug(f"Stage {i}: Could not deactivate CP equations: {_e}")

                initialize_ro_unit_elegant(ro, target_recovery, verbose=True)
                logger.info(f"[TIMING {time.time()-start_time:.1f}s] RO{i} initialized")
            except Exception as e_init:
                # If the failure is due to insufficient inlet pressure, parse and bump pump pressure
                err_msg = str(e_init)
                if "Inlet pressure" in err_msg and "Need at least" in err_msg:
                    import re
                    match = re.search(r"Need at least ([\d.]+) bar", err_msg)
                    if match:
                        min_bar = float(match.group(1))
                        new_pressure = min(80.0, min_bar * 1.25)  # 25% margin, cap at 80 bar
                        logger.warning(
                            f"Stage {i}: Increasing pump pressure to {new_pressure:.1f} bar based on RO requirement"
                        )
                        # Set new pump pressure and re-propagate
                        pump.outlet.pressure[0].fix(new_pressure * 1e5)
                        # Re-propagate into RO
                        if hasattr(m.fs, arc_name_stage):
                            propagate_state(arc=getattr(m.fs, arc_name_stage))
                        elif hasattr(m.fs, arc_name_simple):
                            propagate_state(arc=getattr(m.fs, arc_name_simple))
                        # Retry initialization
                        initialize_ro_unit_elegant(ro, target_recovery, verbose=True)
                        logger.info(f"[TIMING {time.time()-start_time:.1f}s] RO{i} initialized after pressure bump")
                        # Proceed
                    else:
                        logger.warning(
                            f"Stage {i}: Could not parse minimum pressure from error; falling back to flux relaxation"
                        )
                        # Fall through to flux relaxation below
                else:
                    logger.warning(
                        f"Stage {i}: RO initialize failed: {e_init}. Attempting flux bound relaxation and retry."
                    )
                # Relax water flux lower bound and retry once
                try:
                    # Make the lower bound fully non-negative for maximum permissiveness
                    # 0.00 LMH in kg/m^2/s
                    jw_min_relaxed = 0.0
                    if hasattr(ro, 'feed_side') and hasattr(ro, 'flux_mass_phase_comp'):
                        for x in ro.feed_side.length_domain:
                            # Relax lower bound
                            ro.flux_mass_phase_comp[0, x, 'Liq', 'H2O'].setlb(jw_min_relaxed)
                    initialize_ro_unit_elegant(ro, target_recovery, verbose=True)
                    logger.info(f"[TIMING {time.time()-start_time:.1f}s] RO{i} initialized after flux relaxation")
                except Exception as e_retry:
                    logger.error(f"Stage {i}: RO initialize retry failed: {e_retry}")
                    raise
            finally:
                # Reactivate CP equations if we temporarily deactivated them
                if cp_temp_deactivated:
                    try:
                        ro.feed_side.eq_concentration_polarization.activate()
                        logger.info(f"Stage {i}: Reactivated CP equations after initialization")
                    except Exception as _e:
                        logger.debug(f"Stage {i}: Could not reactivate CP equations: {_e}")
            
            # TDS update moved to BEFORE pressure calculation for proper Stage 2+ initialization
            # Keep this commented as documentation of the change
            # current_tds_ppm = calculate_concentrate_tds(
            #     current_tds_ppm,
            #     target_recovery,
            #     salt_passage=default_salt_passage
            # )
            
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
            initialize_erd_if_present(m, n_stages)
            m.fs.recycle_split.initialize(outlvl=idaeslog.NOTSET)
            
            propagate_state(arc=m.fs.split_to_disposal)
            m.fs.disposal_product.initialize(outlvl=idaeslog.NOTSET)
            
            # Calculate recycle split fraction from recycle ratio
            # recycle_ratio = recycle_flow / fresh_feed_flow
            # recycle_split_fraction = recycle / (recycle + disposal)
            # If R is recycle_ratio, then fraction = R / (1 + R)
            recycle_ratio = config_data.get('recycle_ratio', recycle_info.get('recycle_ratio', 0.2))
            if recycle_ratio > 0:
                recycle_split_fraction = recycle_ratio / (1 + recycle_ratio)
            else:
                recycle_split_fraction = 0

            logger.info(f"\nRecycle ratio from config: {recycle_ratio:.3f}")
            logger.info(f"Calculated recycle split fraction: {recycle_split_fraction:.3f}")

            # Only fix one split fraction - the other is calculated from sum = 1 constraint
            m.fs.recycle_split.split_fraction[0, "recycle"].fix(recycle_split_fraction)
            
            # Re-initialize splitter
            m.fs.recycle_split.initialize(outlvl=idaeslog.NOTSET)
            
            # Optional: Refine mixer composition based on actual concentrate
            if config_data.get('refine_recycle', True):
                refine_recycle_composition(m, config_data)
        else:
            # Initialize disposal product for non-recycle case (unified architecture)
            final_stage = n_stages
            initialize_erd_if_present(m, n_stages)
            m.fs.recycle_split.initialize(outlvl=idaeslog.NOTSET)
            
            propagate_state(arc=m.fs.split_to_disposal)
            m.fs.disposal_product.initialize(outlvl=idaeslog.NOTSET)
        
        # Apply scaling factors NOW after pumps are initialized with proper pressures
        # This ensures positive Net Driving Pressure (NDP) before FBBT runs
        logger.info("\n=== Applying Scaling Factors ===")
        logger.info("Calculating scaling factors with initialized pump pressures...")
        from idaes.core.util.scaling import calculate_scaling_factors
        calculate_scaling_factors(m)
        logger.info("Scaling factors applied successfully")
        
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
            membrane_type_cfg = config_data.get('membrane_type', getattr(m, 'membrane_type', 'brackish'))
            is_seawater_case = (membrane_type_cfg == 'seawater')

            if is_seawater_case:
                # Unfix all pump pressures
                for i in range(1, n_stages + 1):
                    pump = getattr(m.fs, f"pump{i}")
                    pump.outlet.pressure[0].unfix()
                    logger.info(f"Stage {i}: Unfixed pump pressure (was {value(pump.outlet.pressure[0])/1e5:.1f} bar)")

                    # Set realistic pressure bounds based on design pressure
                    design_pressure_bar = stage_data.get('feed_pressure_bar', 10)

                    # Determine tolerance based on stage and system type
                    stage_tds_ppm = config_data.get('feed_salinity_ppm', 5000) * (1.5 ** (i - 1))  # Estimate TDS increase
                    membrane_type = config_data.get('membrane_model', 'BW30').lower()

                    if 'sw' in membrane_type or stage_tds_ppm >= 30000:
                        pressure_tolerance = 0.5  # ±50% for seawater
                    elif i >= 2:  # Later stages
                        pressure_tolerance = 0.4  # ±40% for high-recovery stages
                    else:  # Stage 1 brackish
                        pressure_tolerance = 0.3  # ±30% for first stage

                    # Apply bounds without arbitrary min/max limits
                    min_pressure_bar = design_pressure_bar * (1 - pressure_tolerance)
                    max_pressure_bar = design_pressure_bar * (1 + pressure_tolerance)

                    # Keep physical minimum only where necessary
                    if min_pressure_bar < 2:  # Below 2 bar is physically unrealistic
                        min_pressure_bar = 2
                    # Remove the 60 bar ceiling - let seawater go higher if needed

                    if hasattr(pump, 'deltaP'):
                        pump.deltaP[0].setlb(min_pressure_bar * 1e5)
                        pump.deltaP[0].setub(max_pressure_bar * 1e5)
                        logger.info(f"Stage {i}: Set pump ΔP bounds [{min_pressure_bar:.1f}, {max_pressure_bar:.1f}] bar")
                    else:
                        # Fallback: bound outlet pressure relative to inlet
                        inlet_p = value(pump.inlet.pressure[0])
                        pump.outlet.pressure[0].setlb(inlet_p + min_pressure_bar * 1e5)
                        pump.outlet.pressure[0].setub(inlet_p + max_pressure_bar * 1e5)
                        logger.info(f"Stage {i}: Set outlet pressure bounds [inlet+{min_pressure_bar:.1f}, inlet+{max_pressure_bar:.1f}] bar")

                    # Also prevent negative work
                    if hasattr(pump, 'work_mechanical'):
                        pump.work_mechanical[0].setlb(0)
                        logger.info(f"Stage {i}: Set minimum pump work to 0 (no turbine mode)")

                # Add a single system-level recovery constraint (inequality) to avoid infeasibility
                system_target = config_data.get('achieved_recovery', 0.45)
                system_tol = 0.05  # Allow 5% tolerance for seawater systems

                feed_h2o = m.fs.fresh_feed.properties[0].flow_mass_phase_comp['Liq', 'H2O']
                total_perm_h2o = sum(
                    getattr(m.fs, f"ro_stage{i}").mixed_permeate[0].flow_mass_phase_comp['Liq', 'H2O']
                    for i in range(1, n_stages + 1)
                )

                setattr(m.fs, 'system_recovery_constraint',
                        Constraint(expr=total_perm_h2o >= (system_target - system_tol) * feed_h2o))
                logger.info(f"Added system recovery constraint: >= {(system_target - system_tol):.3f} of feed H2O")

                # Add flux constraints for seawater configuration
                for i in range(1, n_stages + 1):
                    ro = getattr(m.fs, f"ro_stage{i}")
                    stage_data = config_data['stages'][i-1]
                    target_flux_lmh = stage_data.get('flux_target_lmh')
                    if False and target_flux_lmh:  # TEMPORARILY DISABLED FOR DEBUGGING
                        # Convert LMH to kg/m²/s (WaterTAP internal units)
                        target_flux_kg_m2_s = target_flux_lmh * 2.778e-4

                        # Apply average flux constraint instead of constraining every point
                        # This is less restrictive and should help convergence
                        from pyomo.environ import sum_product
                        n_points = len(ro.feed_side.length_domain)
                        avg_flux = sum(ro.flux_mass_phase_comp[0, x, 'Liq', 'H2O']
                                     for x in ro.feed_side.length_domain) / n_points
                        flux_avg_name = f"flux_avg_constraint_stage{i}"
                        setattr(m.fs, flux_avg_name,
                                Constraint(expr=avg_flux >= target_flux_kg_m2_s))
                        logger.info(f"Stage {i}: Added average flux constraint >= {target_flux_lmh:.1f} LMH")

            else:
                for i in range(1, n_stages + 1):
                    pump = getattr(m.fs, f"pump{i}")
                    ro = getattr(m.fs, f"ro_stage{i}")
                    stage_data = config_data['stages'][i-1]
                    target_recovery = stage_data.get('stage_recovery', 0.5)

                    # Unfix pump pressure
                    pump.outlet.pressure[0].unfix()
                    logger.info(f"Stage {i}: Unfixed pump pressure (was {value(pump.outlet.pressure[0])/1e5:.1f} bar)")

                    # Set realistic pressure bounds based on design pressure
                    design_pressure_bar = stage_data.get('feed_pressure_bar', 10)

                    # Determine tolerance based on stage and system type
                    stage_tds_ppm = config_data.get('feed_salinity_ppm', 5000) * (1.5 ** (i - 1))  # Estimate TDS increase
                    membrane_type = config_data.get('membrane_model', 'BW30').lower()

                    if 'sw' in membrane_type or stage_tds_ppm >= 30000:
                        pressure_tolerance = 0.5  # ±50% for seawater
                    elif i >= 2:  # Later stages
                        pressure_tolerance = 0.4  # ±40% for high-recovery stages
                    else:  # Stage 1 brackish
                        pressure_tolerance = 0.3  # ±30% for first stage

                    # Apply bounds without arbitrary min/max limits
                    min_pressure_bar = design_pressure_bar * (1 - pressure_tolerance)
                    max_pressure_bar = design_pressure_bar * (1 + pressure_tolerance)

                    # Keep physical minimum only where necessary
                    if min_pressure_bar < 2:  # Below 2 bar is physically unrealistic
                        min_pressure_bar = 2
                    # Remove the 60 bar ceiling - let seawater go higher if needed

                    if hasattr(pump, 'deltaP'):
                        pump.deltaP[0].setlb(min_pressure_bar * 1e5)
                        pump.deltaP[0].setub(max_pressure_bar * 1e5)
                        logger.info(f"Stage {i}: Set pump ΔP bounds [{min_pressure_bar:.1f}, {max_pressure_bar:.1f}] bar")
                    else:
                        # Fallback: bound outlet pressure relative to inlet
                        inlet_p = value(pump.inlet.pressure[0])
                        pump.outlet.pressure[0].setlb(inlet_p + min_pressure_bar * 1e5)
                        pump.outlet.pressure[0].setub(inlet_p + max_pressure_bar * 1e5)
                        logger.info(f"Stage {i}: Set outlet pressure bounds [inlet+{min_pressure_bar:.1f}, inlet+{max_pressure_bar:.1f}] bar")

                    # Also prevent negative work
                    if hasattr(pump, 'work_mechanical'):
                        pump.work_mechanical[0].setlb(0)
                        logger.info(f"Stage {i}: Set minimum pump work to 0 (no turbine mode)")

                    # Only use flux constraint - recovery will follow automatically
                    # With fixed membrane area: recovery = flux × area / feed_flow
                    target_flux_lmh = stage_data.get('flux_target_lmh')
                    if target_flux_lmh:  # Re-enabled
                        # Convert LMH to kg/m²/s (WaterTAP internal units)
                        target_flux_kg_m2_s = target_flux_lmh * 2.778e-4

                        # Apply average flux constraint instead of constraining every point
                        # This is less restrictive and should help convergence
                        from pyomo.environ import sum_product
                        n_points = len(ro.feed_side.length_domain)
                        avg_flux = sum(ro.flux_mass_phase_comp[0, x, 'Liq', 'H2O']
                                     for x in ro.feed_side.length_domain) / n_points
                        flux_avg_name = f"flux_avg_constraint_stage{i}"
                        setattr(m.fs, flux_avg_name,
                                Constraint(expr=avg_flux >= target_flux_kg_m2_s))
                        logger.info(f"Stage {i}: Added average flux constraint >= {target_flux_lmh:.1f} LMH")
                        logger.info(f"Stage {i}: Recovery will be determined by flux × area / feed_flow")
                    elif not use_staged_solve:
                        # Fallback to recovery constraint if no flux target provided
                        constraint_name = f"recovery_constraint_stage{i}"
                        recovery_tolerance = 0.01  # Allow 1% tolerance (legacy behaviour)
                        setattr(
                            m.fs,
                            constraint_name,
                            Constraint(expr=ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'] >= target_recovery - recovery_tolerance),
                        )
                        logger.info(
                            f"Stage {i}: No flux target, using recovery constraint: {target_recovery - recovery_tolerance:.3f} <= recovery"
                            f" (legacy tolerance)"
                        )
                    else:
                        logger.info(
                            f"Stage {i}: Progressive tightening enabled; recovery bounds handled via staged constraints"
                        )

            # Add system-level recovery constraint for recycle systems
            if has_recycle and not use_staged_solve:
                logger.info("\n=== Adding System-Level Recovery Constraint for Recycle ===")
                recovery_tolerance = 0.005  # Allow 0.5% tolerance (tighter)

                # Get the SYSTEM target recovery from config, not stage recovery
                system_target_recovery = config_data.get('target_recovery', 0.70)

                # Fresh feed water flow (inlet to system)
                fresh_h2o = m.fs.fresh_feed.properties[0].flow_mass_phase_comp['Liq', 'H2O']

                # Disposal water flow (leaving system)
                disposal_h2o = m.fs.disposal_product.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O']

                # System recovery = (fresh_feed - disposal) / fresh_feed
                # This is equivalent to permeate / fresh_feed
                # One-sided constraint to avoid over-constraining
                system_tolerance = 0.01  # 1% tolerance for system recovery
                m.fs.system_recovery_constraint = Constraint(
                    expr=(fresh_h2o - disposal_h2o) / fresh_h2o >= system_target_recovery - system_tolerance
                )
                logger.info(
                    f"Added system recovery constraint: recovery >= {system_target_recovery - system_tolerance:.3f} (one-sided)"
                )
                logger.info(
                    f"Target SYSTEM recovery: {system_target_recovery:.3f} (from config, not stage recovery)"
                )
            elif has_recycle:
                logger.info(
                    "\n=== Progressive tightening enabled; system recovery bounds will be handled with staged constraints ==="
                )

            if use_staged_solve:
                stage_data_list = config_data.get('stages', [])
                if len(stage_data_list) < n_stages:
                    stage_data_list = stage_data_list + [{}] * (n_stages - len(stage_data_list))

                if not hasattr(m.fs, 'stage_index'):
                    m.fs.stage_index = RangeSet(1, n_stages)

                # Stage target recoveries default to stage_recovery then target_recovery
                stage_targets = {
                    i: stage_data_list[i-1].get(
                        'target_recovery',
                        stage_data_list[i-1].get('stage_recovery', 0.5),
                    )
                    for i in range(1, n_stages + 1)
                }

                if hasattr(m.fs, 'stage_recovery_target'):
                    m.fs.del_component(m.fs.stage_recovery_target)
                m.fs.stage_recovery_target = Param(
                    m.fs.stage_index,
                    initialize=stage_targets,
                )

                initial_tol = progressive_tolerances[0]
                tolerance_init = {i: initial_tol for i in range(1, n_stages + 1)}

                if hasattr(m.fs, 'recovery_tolerance'):
                    m.fs.del_component(m.fs.recovery_tolerance)
                m.fs.recovery_tolerance = Param(
                    m.fs.stage_index,
                    mutable=True,
                    initialize=tolerance_init,
                )

                if hasattr(m.fs, 'stage_recovery_slack_pos'):
                    m.fs.del_component(m.fs.stage_recovery_slack_pos)
                if hasattr(m.fs, 'stage_recovery_slack_neg'):
                    m.fs.del_component(m.fs.stage_recovery_slack_neg)
                m.fs.stage_recovery_slack_pos = Var(
                    m.fs.stage_index,
                    domain=NonNegativeReals,
                    initialize=0.0,
                )
                m.fs.stage_recovery_slack_neg = Var(
                    m.fs.stage_index,
                    domain=NonNegativeReals,
                    initialize=0.0,
                )

                def _stage_upper_rule(fs, i):
                    ro_blk = getattr(fs, f"ro_stage{i}")
                    return (
                        ro_blk.recovery_mass_phase_comp[0, 'Liq', 'H2O']
                        <= fs.stage_recovery_target[i]
                        + fs.recovery_tolerance[i]
                        + fs.stage_recovery_slack_pos[i]
                    )

                def _stage_lower_rule(fs, i):
                    ro_blk = getattr(fs, f"ro_stage{i}")
                    return (
                        ro_blk.recovery_mass_phase_comp[0, 'Liq', 'H2O']
                        >= fs.stage_recovery_target[i]
                        - fs.recovery_tolerance[i]
                        - fs.stage_recovery_slack_neg[i]
                    )

                if hasattr(m.fs, 'stage_recovery_upper'):
                    m.fs.del_component(m.fs.stage_recovery_upper)
                if hasattr(m.fs, 'stage_recovery_lower'):
                    m.fs.del_component(m.fs.stage_recovery_lower)
                m.fs.stage_recovery_upper = Constraint(
                    m.fs.stage_index,
                    rule=_stage_upper_rule,
                )
                m.fs.stage_recovery_lower = Constraint(
                    m.fs.stage_index,
                    rule=_stage_lower_rule,
                )

                # System-level recovery bounds when recycle is present
                if has_recycle:
                    system_target = config_data.get('target_recovery', 0.70)
                    if hasattr(m.fs, 'system_recovery_target'):
                        m.fs.del_component(m.fs.system_recovery_target)
                    m.fs.system_recovery_target = Param(initialize=system_target)

                    if hasattr(m.fs, 'system_recovery_tolerance'):
                        m.fs.del_component(m.fs.system_recovery_tolerance)
                    m.fs.system_recovery_tolerance = Param(
                        mutable=True,
                        initialize=initial_tol,
                    )

                    if hasattr(m.fs, 'system_recovery_slack_pos'):
                        m.fs.del_component(m.fs.system_recovery_slack_pos)
                    if hasattr(m.fs, 'system_recovery_slack_neg'):
                        m.fs.del_component(m.fs.system_recovery_slack_neg)

                    m.fs.system_recovery_slack_pos = Var(
                        domain=NonNegativeReals,
                        initialize=0.0,
                    )
                    m.fs.system_recovery_slack_neg = Var(
                        domain=NonNegativeReals,
                        initialize=0.0,
                    )

                    def _system_upper_rule(fs):
                        fresh_h2o = fs.fresh_feed.properties[0].flow_mass_phase_comp['Liq', 'H2O']
                        disposal_h2o = fs.disposal_product.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O']
                        return (
                            (fresh_h2o - disposal_h2o) / fresh_h2o
                            <= fs.system_recovery_target
                            + fs.system_recovery_tolerance
                            + fs.system_recovery_slack_pos
                        )

                    def _system_lower_rule(fs):
                        fresh_h2o = fs.fresh_feed.properties[0].flow_mass_phase_comp['Liq', 'H2O']
                        disposal_h2o = fs.disposal_product.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O']
                        return (
                            (fresh_h2o - disposal_h2o) / fresh_h2o
                            >= fs.system_recovery_target
                            - fs.system_recovery_tolerance
                            - fs.system_recovery_slack_neg
                        )

                    if hasattr(m.fs, 'system_recovery_upper'):
                        m.fs.del_component(m.fs.system_recovery_upper)
                    if hasattr(m.fs, 'system_recovery_lower'):
                        m.fs.del_component(m.fs.system_recovery_lower)
                    m.fs.system_recovery_upper = Constraint(rule=_system_upper_rule)
                    m.fs.system_recovery_lower = Constraint(rule=_system_lower_rule)

                slack_penalty_weight = config_data.get('recovery_slack_penalty', 1e6)
                penalty_expr = sum(
                    slack_penalty_weight
                    * (m.fs.stage_recovery_slack_pos[i] ** 2 + m.fs.stage_recovery_slack_neg[i] ** 2)
                    for i in m.fs.stage_index
                )
                if has_recycle:
                    penalty_expr += slack_penalty_weight * (
                        m.fs.system_recovery_slack_pos ** 2 + m.fs.system_recovery_slack_neg ** 2
                    )
                m.fs.slack_penalty_expr = penalty_expr

                logger.info(
                    "Initialized staged recovery bounds with initial tolerance "
                    f"±{initial_tol * 100:.1f}% and slack penalty weight {slack_penalty_weight:.1e}"
                )

            # Check degrees of freedom
            dof = degrees_of_freedom(m)
            logger.info(f"\nDegrees of freedom after adding constraints: {dof}")

            def _build_deviation_objective(include_slack=True):
                stage_config_list = config_data.get('stages', [])
                if len(stage_config_list) < n_stages:
                    stage_config_list = stage_config_list + [{}] * (n_stages - len(stage_config_list))

                objective_expr = 0

                for i in range(1, n_stages + 1):
                    ro_blk = getattr(m.fs, f"ro_stage{i}")
                    stage_cfg = stage_config_list[i - 1]
                    design_flux_lmh = stage_cfg.get('design_flux_lmh', 18)
                    design_flux_kg = design_flux_lmh / 3.6e6 if design_flux_lmh else 1.0
                    avg_flux = ro_blk.flux_mass_phase_comp_avg[0, 'Liq', 'H2O']
                    objective_expr += 3 * ((avg_flux - design_flux_kg) / design_flux_kg) ** 2

                for i in range(1, n_stages + 1):
                    pump_blk = getattr(m.fs, f"pump{i}")
                    stage_cfg = stage_config_list[i - 1]
                    design_pressure_pa = stage_cfg.get('feed_pressure_bar', 10) * 1e5
                    objective_expr += ((pump_blk.outlet.pressure[0] - design_pressure_pa) / design_pressure_pa) ** 2

                if include_slack and hasattr(m.fs, 'slack_penalty_expr'):
                    objective_expr += m.fs.slack_penalty_expr
                    logger.info("Combined deviation objective with slack penalty")

                if hasattr(m.fs, 'minimize_deviations'):
                    m.fs.del_component(m.fs.minimize_deviations)

                m.fs.minimize_deviations = Objective(expr=objective_expr, sense=minimize)
                logger.info(
                    "Added multi-objective: 3×flux_deviation + 1×pressure_deviation"
                    + (" + slack_penalty" if include_slack and hasattr(m.fs, 'slack_penalty_expr') else "")
                )

            # Staged solving: First try without objective for feasibility
            phase = 1 if use_staged_solve else 2
            add_objective = not use_staged_solve  # Skip objective in Phase 1

            if dof > 0 and add_objective:
                _build_deviation_objective(include_slack=True)
                logger.info("This will prioritize flux matching while keeping pressures reasonable and minimizing slack")
                dof = degrees_of_freedom(m)
                logger.info(f"Degrees of freedom after adding objective: {dof} (should be 0 for optimization)")
            elif dof > 0 and not add_objective:
                logger.info(f"Phase 1: Skipping objective for initial feasibility solve (DOF = {dof})")
                logger.info("Will add objective in Phase 2 if initial solve succeeds")
            elif dof == 0:
                logger.info("System is fully constrained (DOF = 0)")
                logger.info("Optimization will be limited - consider unfixing some variables if needed")
            elif dof < 0:
                logger.error(f"System is over-constrained! DOF = {dof}")
                logger.error("This typically means conflicting constraints between:")
                logger.error("  - Recovery constraints (stage and system)")
                logger.error("  - Flux bounds")
                logger.error("  - Pressure bounds")
                logger.error("Consider relaxing recovery tolerance or widening flux bounds")
        
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
                
                # Solve model with symbolic labels for debugging
                try:
                    results = solver.solve(m, tee=False, symbolic_solver_labels=True, options={
                        'linear_solver': 'ma27',
                        'max_cpu_time': 600,  # 10 minutes for main solve
                        'tol': 1e-6,  # Moderately relaxed for balance of speed/accuracy
                        'constr_viol_tol': 1e-6,
                        'acceptable_tol': 1e-3,  # Fallback for difficult problems
                        'acceptable_constr_viol_tol': 1e-3,
                        'print_level': 0,  # Suppress all IPOPT output
                        'halt_on_ampl_error': 'yes'  # Stop immediately on AMPL error
                    })
                except Exception as e:
                    logger.error(f"\n=== AMPL ERROR DIAGNOSTICS (Iteration {iteration+1}) ===")
                    logger.error(f"Error message: {str(e)}")

                    # Try to extract problematic values
                    for i in range(1, n_stages + 1):
                        try:
                            ro = getattr(m.fs, f"ro_stage{i}")
                            pump = getattr(m.fs, f"pump{i}")

                            # Check pressures
                            feed_p = value(ro.inlet.pressure[0])/1e5
                            logger.error(f"Stage {i} feed pressure: {feed_p:.2f} bar")

                            # Check for negative driving pressure
                            osm_in = value(ro.feed_side.properties[0, 0].pressure_osm_phase['Liq'])/1e5
                            ndp = feed_p - osm_in
                            logger.error(f"Stage {i} NDP = {ndp:.2f} bar (feed: {feed_p:.2f}, osmotic: {osm_in:.2f})")

                            if ndp < 0:
                                logger.error(f"Stage {i} ERROR: NEGATIVE DRIVING PRESSURE!")
                        except Exception as diag_e:
                            logger.error(f"Stage {i} diagnostic failed: {str(diag_e)}")

                    # DIAGNOSTIC: Check pump actual values
                    logger.info("\n=== PUMP DIAGNOSTIC AFTER SOLVE ===")
                    for i in range(1, n_stages + 1):
                        try:
                            pump = getattr(m.fs, f"pump{i}")
                            logger.info(f"\nPump {i}:")
                            logger.info(f"  Inlet pressure: {value(pump.inlet.pressure[0])/1e5:.2f} bar ({value(pump.inlet.pressure[0]):.0f} Pa)")
                            logger.info(f"  Outlet pressure: {value(pump.outlet.pressure[0])/1e5:.2f} bar ({value(pump.outlet.pressure[0]):.0f} Pa)")
                            if hasattr(pump, 'deltaP'):
                                logger.info(f"  DeltaP: {value(pump.deltaP[0])/1e5:.2f} bar")
                            logger.info(f"  Inlet flow: {value(pump.control_volume.properties_in[0].flow_vol)*3600:.2f} m³/h")
                            logger.info(f"  Work mechanical: {value(pump.work_mechanical[0])/1000:.2f} kW")
                            if hasattr(pump, 'work_fluid'):
                                logger.info(f"  Work fluid: {value(pump.work_fluid[0])/1000:.2f} kW")
                            logger.info(f"  Efficiency: {value(pump.efficiency_pump[0]):.3f}")
                        except Exception as pump_diag_e:
                            logger.error(f"Pump {i} diagnostic failed: {str(pump_diag_e)}")

                    # Check mixer state if recycle
                    if has_recycle:
                        try:
                            mixer = m.fs.feed_mixer
                            fresh_tds = value(mixer.fresh.conc_mass_phase_comp[0, 'Liq', 'tds'])
                            recycle_tds = value(mixer.recycle.conc_mass_phase_comp[0, 'Liq', 'tds'])
                            mixed_tds = value(mixer.outlet.conc_mass_phase_comp[0, 'Liq', 'tds'])
                            logger.error(f"Mixer TDS: fresh={fresh_tds:.1f}, recycle={recycle_tds:.1f}, mixed={mixed_tds:.1f} kg/m³")
                        except Exception as mix_e:
                            logger.error(f"Mixer diagnostic failed: {str(mix_e)}")

                    raise  # Re-raise the original exception

                # Check solver status with diagnostic info
                check_solver_status(results, context=f"Recycle iteration {iteration+1}",
                                  raise_on_fail=True, m=m, n_stages=n_stages)
                
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
            # Single solve for non-recycle or fixed pump cases with symbolic labels
            try:
                results = solver.solve(m, tee=False, symbolic_solver_labels=True, options={
                    'linear_solver': 'ma27',
                    'max_cpu_time': 600,  # 10 minutes for main solve
                    'tol': 1e-6,  # Moderately relaxed for balance of speed/accuracy
                    'constr_viol_tol': 1e-6,
                    'acceptable_tol': 1e-3,  # Fallback for difficult problems
                    'acceptable_constr_viol_tol': 1e-3,
                    'print_level': 0,  # Suppress all IPOPT output
                    'halt_on_ampl_error': 'yes'  # Stop immediately on AMPL error
                })
            except Exception as e:
                logger.error(f"\n=== AMPL ERROR DIAGNOSTICS ===")
                logger.error(f"Error message: {str(e)}")

                # Try to extract problematic values
                for i in range(1, n_stages + 1):
                    try:
                        ro = getattr(m.fs, f"ro_stage{i}")
                        pump = getattr(m.fs, f"pump{i}")

                        # Check pressures
                        feed_p = value(ro.inlet.pressure[0])/1e5
                        logger.error(f"Stage {i} feed pressure: {feed_p:.2f} bar")

                        # Check for negative driving pressure
                        osm_in = value(ro.feed_side.properties[0, 0].pressure_osm_phase['Liq'])/1e5
                        ndp = feed_p - osm_in
                        logger.error(f"Stage {i} NDP = {ndp:.2f} bar (feed: {feed_p:.2f}, osmotic: {osm_in:.2f})")

                        if ndp < 0:
                            logger.error(f"Stage {i} ERROR: NEGATIVE DRIVING PRESSURE!")
                    except Exception as diag_e:
                        logger.error(f"Stage {i} diagnostic failed: {str(diag_e)}")

                # Check mixer state if recycle
                if has_recycle:
                    try:
                        mixer = m.fs.feed_mixer
                        fresh_tds = value(mixer.fresh.conc_mass_phase_comp[0, 'Liq', 'tds'])
                        recycle_tds = value(mixer.recycle.conc_mass_phase_comp[0, 'Liq', 'tds'])
                        mixed_tds = value(mixer.outlet.conc_mass_phase_comp[0, 'Liq', 'tds'])
                        logger.error(f"Mixer TDS: fresh={fresh_tds:.1f}, recycle={recycle_tds:.1f}, mixed={mixed_tds:.1f} kg/m³")
                    except Exception as mix_e:
                        logger.error(f"Mixer diagnostic failed: {str(mix_e)}")

                raise  # Re-raise the original exception

            # Check solver status with diagnostic info
            # Phase 1 is a pure feasibility problem, so accept feasible solutions
            initial_solve_success = check_solver_status(results, context="Main solve (Phase 1)", raise_on_fail=False,
                              m=m, n_stages=n_stages, allow_feasible=True)

        # Phase 2: Progressive constraint tightening with DOF-aware objective management
        logger.info(f"\nPhase 2 conditions - initial_solve_success: {initial_solve_success}, use_staged_solve: {use_staged_solve}")

        # Explicitly log if Phase 2 is being skipped
        if not initial_solve_success:
            logger.warning("Phase 2 skipped: initial_solve_success is False")
        if not use_staged_solve:
            logger.warning("Phase 2 skipped: use_staged_solve is False")

        if initial_solve_success and use_staged_solve:
            logger.info("\n=== Phase 2: Progressive Constraint Tightening ===")

            # Try-except to catch any errors in Phase 2
            try:
                _build_deviation_objective(include_slack=True)

                def _stage_recovery_violation():
                    worst = 0.0
                    for idx in m.fs.stage_index:
                        ro_blk = getattr(m.fs, f"ro_stage{idx}")
                        actual = value(ro_blk.recovery_mass_phase_comp[0, 'Liq', 'H2O'])
                        target = value(m.fs.stage_recovery_target[idx])
                        tol = value(m.fs.recovery_tolerance[idx])
                        above = max(0.0, actual - (target + tol))
                        below = max(0.0, (target - tol) - actual)
                        worst = max(worst, above, below)
                    return worst

                def _system_recovery_violation():
                    if not has_recycle:
                        return 0.0
                    feed_h2o = value(m.fs.fresh_feed.properties[0].flow_mass_phase_comp['Liq', 'H2O'])
                    if feed_h2o <= 0:
                        return 0.0
                    disposal_h2o = value(m.fs.disposal_product.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
                    actual = (feed_h2o - disposal_h2o) / feed_h2o
                    target = value(m.fs.system_recovery_target)
                    tol = value(m.fs.system_recovery_tolerance)
                    above = max(0.0, actual - (target + tol))
                    below = max(0.0, (target - tol) - actual)
                    return max(above, below)

                try:
                    calculate_scaling_factors(m)
                    logger.info("Applied scaling factors prior to tightening loop")
                except Exception as scale_error:
                    logger.debug(f"Scaling warning before Phase 2: {scale_error}")

                stage_violation = _stage_recovery_violation()
                system_violation = _system_recovery_violation()
                current_violation = max(stage_violation, system_violation)

                logger.info(
                    f"Phase 2 starting point: stage deviation={stage_violation*100:.2f}%, system deviation={system_violation*100:.2f}%"
                )
                logger.info(f"Target final tolerance: ±{final_recovery_tolerance*100:.1f}%")

                achieved_tolerance = None
                if current_violation <= final_recovery_tolerance + 1e-4:
                    logger.info("Phase 1 solution already within final tolerance; skipping tightening loop")
                    achieved_tolerance = final_recovery_tolerance
                else:
                    tolerance_sequence = progressive_tolerances[1:] if len(progressive_tolerances) > 1 else []

                    for step_idx, tol in enumerate(tolerance_sequence, start=1):
                        logger.info(f"\n--- Stage 2 step {step_idx}: tightening to ±{tol*100:.1f}% ---")

                        for idx in m.fs.stage_index:
                            m.fs.recovery_tolerance[idx].value = tol
                            m.fs.stage_recovery_slack_pos[idx].setlb(0.0)
                            m.fs.stage_recovery_slack_neg[idx].setlb(0.0)
                            m.fs.stage_recovery_slack_pos[idx].value = 0.0
                            m.fs.stage_recovery_slack_neg[idx].value = 0.0

                        if has_recycle:
                            m.fs.system_recovery_tolerance.value = tol
                            m.fs.system_recovery_slack_pos.setlb(0.0)
                            m.fs.system_recovery_slack_neg.setlb(0.0)
                            m.fs.system_recovery_slack_pos.value = 0.0
                            m.fs.system_recovery_slack_neg.value = 0.0

                        try:
                            calculate_scaling_factors(m)
                        except Exception as scale_error:
                            logger.debug(f"Scaling warning at tolerance {tol:.3f}: {scale_error}")

                        solver_options = {
                            'linear_solver': 'ma27',
                            'max_iter': 400 + 120 * step_idx,
                            'tol': max(1e-8, tol * 1e-2),
                            'constr_viol_tol': max(1e-8, tol * 1e-2),
                            'acceptable_tol': 1e-6,
                            'warm_start_init_point': 'yes',
                            'warm_start_bound_push': 1e-8,
                            'warm_start_slack_bound_push': 1e-8,
                            'mu_strategy': 'monotone',
                            'print_level': 0,
                        }

                        if current_violation <= tol + 5e-4:
                            logger.info(
                                f"  Current deviation {current_violation*100:.2f}% already within ±{tol*100:.1f}%; skipping solve"
                            )
                            achieved_tolerance = tol
                            continue

                        results = solver.solve(m, tee=False, options=solver_options)
                        status = str(results.solver.status)
                        term = str(results.solver.termination_condition)
                        logger.info(f"  Solve status={status}, termination={term}")

                        if check_solver_status(
                            results,
                            context=f"Stage 2 tighten to ±{tol*100:.1f}%",
                            raise_on_fail=False,
                            allow_feasible=True,
                        ):
                            stage_slack_pos = max(value(m.fs.stage_recovery_slack_pos[idx]) for idx in m.fs.stage_index)
                            stage_slack_neg = max(value(m.fs.stage_recovery_slack_neg[idx]) for idx in m.fs.stage_index)
                            max_slack = max(stage_slack_pos, stage_slack_neg)
                            if has_recycle:
                                max_slack = max(
                                    max_slack,
                                    value(m.fs.system_recovery_slack_pos),
                                    value(m.fs.system_recovery_slack_neg),
                                )
                            if max_slack > 5e-4:
                                logger.warning(f"  Slack magnitude {max_slack:.4e} remains; consider increasing penalty if persistent")

                            stage_violation = _stage_recovery_violation()
                            system_violation = _system_recovery_violation()
                            current_violation = max(stage_violation, system_violation)

                            logger.info(
                                f"  Post-solve deviation: stage={stage_violation*100:.2f}%, system={system_violation*100:.2f}%"
                            )

                            if current_violation <= tol + 5e-4:
                                achieved_tolerance = tol
                            else:
                                logger.warning(
                                    f"  Remaining deviation {current_violation*100:.2f}% exceeds ±{tol*100:.1f}%"
                                )
                        else:
                            stage_violation = _stage_recovery_violation()
                            system_violation = _system_recovery_violation()
                            current_violation = max(stage_violation, system_violation)
                            logger.warning(
                                f"  Solver did not converge cleanly; violation now {current_violation*100:.2f}%"
                            )

                    stage_violation = _stage_recovery_violation()
                    system_violation = _system_recovery_violation()
                    final_violation = max(stage_violation, system_violation)

                    if final_violation <= final_recovery_tolerance + 5e-4:
                        achieved_tolerance = final_recovery_tolerance

                if achieved_tolerance is not None:
                    logger.info(
                        f"\n=== Phase 2 Complete: Achieved ±{achieved_tolerance*100:.1f}% tolerance (final deviation {max(stage_violation, system_violation)*100:.2f}%) ==="
                    )
                else:
                    logger.warning(
                        f"Phase 2 ended with deviation {max(stage_violation, system_violation)*100:.2f}% (> ±{final_recovery_tolerance*100:.1f}%)"
                    )

                logger.info("Final slack variable values:")
                for idx in m.fs.stage_index:
                    pos_val = value(m.fs.stage_recovery_slack_pos[idx])
                    neg_val = value(m.fs.stage_recovery_slack_neg[idx])
                    if max(pos_val, neg_val) > 1e-8:
                        logger.info(
                            f"  Stage {idx}: slack_pos={pos_val:.6f}, slack_neg={neg_val:.6f}"
                        )

                if has_recycle:
                    pos_val = value(m.fs.system_recovery_slack_pos)
                    neg_val = value(m.fs.system_recovery_slack_neg)
                    if max(pos_val, neg_val) > 1e-8:
                        logger.info(
                            f"  System: slack_pos={pos_val:.6f}, slack_neg={neg_val:.6f}"
                        )

                total_permeate = sum(
                    value(getattr(m.fs, f"ro_stage{idx}").mixed_permeate[0].flow_mass_phase_comp['Liq', 'H2O'])
                    for idx in range(1, n_stages + 1)
                )
                feed_h2o = value(m.fs.feed.properties[0].flow_mass_phase_comp['Liq', 'H2O'])
                final_recovery = total_permeate / feed_h2o if feed_h2o > 0 else 0.0
                logger.info(
                    f"Final system recovery: {final_recovery*100:.2f}% (target: {config_data['target_recovery']*100:.1f}%)"
                )

            except Exception as phase2_error:
                logger.error(f"Phase 2 error: {str(phase2_error)}")
                logger.warning("Phase 2 failed, continuing with Phase 1 solution")

        elif not initial_solve_success:
            # Phase 3: Fallback with progressive relaxation
            logger.warning("\n=== Phase 3: Attempting Fallback with Relaxed Constraints ===")

            # Try relaxing recovery tolerance
            for i in range(1, n_stages + 1):
                if hasattr(m.fs, f"recovery_constraint_stage{i}"):
                    constraint = getattr(m.fs, f"recovery_constraint_stage{i}")
                    constraint.deactivate()

                    # Add relaxed constraint
                    ro = getattr(m.fs, f"ro_stage{i}")
                    stage_data = config_data['stages'][i-1]
                    target_recovery = stage_data.get('target_recovery', 0.70)
                    recovery_tolerance = 0.02  # Relax to 2%

                    setattr(m.fs, f"recovery_constraint_stage{i}_relaxed",
                           Constraint(expr=ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'] >= target_recovery - recovery_tolerance))
                    logger.info(f"Stage {i}: Relaxed recovery tolerance to {recovery_tolerance:.1%}")

            # Try solving with relaxed constraints
            try:
                results = solver.solve(m, tee=False, options={
                    'linear_solver': 'ma27',
                    'max_cpu_time': 600,
                    'tol': 1e-4,  # More relaxed
                    'constr_viol_tol': 1e-4,
                    'acceptable_tol': 1e-2,
                    'acceptable_constr_viol_tol': 1e-2,
                    'print_level': 0
                })

                if not check_solver_status(results, context="Phase 3 fallback", raise_on_fail=False):
                    raise RuntimeError("All solve attempts failed")

                logger.info("Phase 3 fallback successful with relaxed constraints")
            except Exception as e:
                logger.error(f"Phase 3 fallback failed: {str(e)}")
                raise RuntimeError("Unable to find feasible solution even with relaxed constraints")

        logger.info("\n=== Solution Complete ===")
        
        # Report final recoveries and pressures
        for i in range(1, n_stages + 1):
            pump = getattr(m.fs, f"pump{i}")
            ro = getattr(m.fs, f"ro_stage{i}")
            
            pressure = value(pump.outlet.pressure[0]) / 1e5  # bar
            recovery = value(ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'])
            
            logger.info(f"Stage {i}: Pressure = {pressure:.1f} bar, Recovery = {recovery:.3f}")

        # Verify concentrate flows for hydraulic safety
        if has_recycle:
            logger.info("\n=== Concentrate Flow Verification ===")
            for i in range(1, n_stages + 1):
                ro = getattr(m.fs, f"ro_stage{i}")
                stage_data = config_data['stages'][i-1]
                n_vessels = stage_data.get('n_vessels', 1)

                # Get concentrate flow in m³/h
                conc_flow = value(ro.retentate.flow_vol_phase[0, 'Liq']) * 3600
                per_vessel = conc_flow / n_vessels

                if per_vessel < 3.5:
                    logger.warning(f"Stage {i}: LOW concentrate flow {per_vessel:.2f} m³/h per vessel (min: 3.5)")
                else:
                    logger.info(f"Stage {i}: Concentrate flow {per_vessel:.2f} m³/h per vessel (OK)")

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
