"""
Elegant RO initialization utilities for WaterTAP models.

This module provides physics-based initialization functions that prevent
FBBT (Feasibility-Based Bound Tightening) infeasibility by ensuring
pressure variables are properly set before initialization.
"""

from typing import Dict, Any, Optional
from pyomo.environ import value, units as pyunits
from idaes.core.util.initialization import propagate_state
import logging

logger = logging.getLogger(__name__)


def get_stream_tds_ppm(stream_state) -> float:
    """
    Extract actual TDS from a stream state block.
    
    Args:
        stream_state: Stream state block from WaterTAP model
        
    Returns:
        float: TDS concentration in ppm
    """
    try:
        # Get property package from parent block
        property_package = stream_state.parent_block().config.property_package
        
        h2o_flow = value(stream_state.flow_mass_phase_comp[0, 'Liq', 'H2O'])
        
        if hasattr(property_package, 'solute_set'):
            # MCAS package
            tds_flow = sum(
                value(stream_state.flow_mass_phase_comp[0, 'Liq', comp])
                for comp in property_package.solute_set
            )
        else:
            # Standard package
            tds_flow = value(stream_state.flow_mass_phase_comp[0, 'Liq', 'TDS'])
        
        total_flow = h2o_flow + tds_flow
        return (tds_flow / total_flow) * 1e6 if total_flow > 0 else 0
        
    except (KeyError, AttributeError) as e:
        logger.error(f"Failed to extract TDS from stream: {e}")
        raise ValueError(f"Could not extract TDS from stream state: {e}")


def calculate_osmotic_pressure(tds_ppm: float) -> float:
    """
    Calculate osmotic pressure from TDS concentration.
    
    Uses simplified correlation: π (Pa) ≈ 0.7 * TDS (g/L) * 1e5
    
    Args:
        tds_ppm: Total dissolved solids in ppm (mg/L)
        
    Returns:
        Osmotic pressure in Pa
    """
    # Convert ppm to g/L
    tds_g_l = tds_ppm / 1000
    
    # Calculate osmotic pressure in bar, then convert to Pa
    osmotic_bar = 0.7 * tds_g_l
    osmotic_pa = osmotic_bar * 1e5
    
    return osmotic_pa


def calculate_concentrate_tds(
    feed_tds_ppm: float, 
    recovery: float, 
    salt_passage: float
) -> float:
    """
    Calculate concentrate TDS based on recovery and salt passage.
    
    Uses formula: C_conc = C_feed * (1 - SP*R) / (1 - R)
    where SP is the salt passage fraction.
    
    Args:
        feed_tds_ppm: Feed TDS concentration in ppm (mg/L)
        recovery: Water recovery fraction (0-1)
        salt_passage: Salt passage fraction (0-1) - REQUIRED parameter
                     Typical values:
                     - Brackish water RO: 0.01-0.02 (1-2%)
                     - Seawater RO: 0.003-0.005 (0.3-0.5%)
                     - High rejection RO: 0.001-0.003 (0.1-0.3%)
        
    Returns:
        float: Concentrate TDS in ppm
        
    Raises:
        ValueError: If recovery >= 1.0
    """
    if recovery >= 1.0:
        raise ValueError(f"Recovery must be less than 1, got {recovery}")
    
    # With salt passage: concentrate_tds = feed_tds * (1 - SP*R) / (1 - R)
    concentrate_tds_ppm = feed_tds_ppm * (1 - salt_passage * recovery) / (1 - recovery)
    
    # Sanity check - warn but don't fail
    if concentrate_tds_ppm > 100000:
        logger.warning(
            f"Calculated concentrate TDS ({concentrate_tds_ppm:.0f} ppm) exceeds 100,000 ppm. "
            f"Check recovery ({recovery:.2%}) and salt passage ({salt_passage:.3f})"
        )
    
    return concentrate_tds_ppm


def calculate_required_pressure(
    feed_tds_ppm: float,
    target_recovery: float,
    permeate_pressure: float = 101325,  # 1 atm default
    min_driving_pressure: float = 15e5,  # 15 bar default
    pressure_drop: float = 0.5e5,  # 0.5 bar default
    salt_passage: float = None,
    membrane_permeability: float = None,  # A_comp in m/s/Pa
    membrane_area: float = None,  # Total area in m²
    feed_flow: float = None  # Feed flow in kg/s
) -> float:
    """
    Calculate required feed pressure for RO operation.
    
    Args:
        feed_tds_ppm: Feed TDS concentration in ppm
        target_recovery: Target water recovery fraction (0-1)
        permeate_pressure: Permeate pressure in Pa (default 1 atm)
        min_driving_pressure: Minimum net driving pressure in Pa (default 15 bar)
        pressure_drop: Pressure drop across membrane in Pa (default 0.5 bar)
        salt_passage: Salt passage fraction (0-1) - REQUIRED parameter
                     See calculate_concentrate_tds for typical values
        
    Returns:
        float: Required feed pressure in Pa
        
    Note:
        For high TDS (>60,000 ppm), the linear osmotic pressure approximation
        may underpredict. Consider using property package osmotic pressure
        calculations for more accuracy.
    """
    if salt_passage is None:
        raise ValueError("salt_passage parameter is required")
    # Calculate concentrate TDS with salt passage
    conc_tds_ppm = calculate_concentrate_tds(feed_tds_ppm, target_recovery, salt_passage)
    
    # For high TDS, warn about approximation limitations
    if conc_tds_ppm > 60000:
        logger.info(
            f"High concentrate TDS ({conc_tds_ppm:.0f} ppm) - "
            f"linear osmotic approximation may underpredict. "
            f"Consider using MCAS property package for accurate osmotic pressure."
        )
    
    # Calculate average osmotic pressure
    feed_osmotic = calculate_osmotic_pressure(feed_tds_ppm)
    conc_osmotic = calculate_osmotic_pressure(conc_tds_ppm)
    avg_osmotic = (feed_osmotic + conc_osmotic) / 2
    
    # If membrane properties are provided, calculate pressure based on flux requirements
    if membrane_permeability and membrane_area and feed_flow:
        # Calculate required permeate flux based on recovery
        permeate_flow = feed_flow * target_recovery  # kg/s
        density = 1000  # kg/m³ approximation
        volumetric_flux = permeate_flow / density / membrane_area  # m/s
        
        # From SD model: J = A * (ΔP - Δπ)
        # Required driving pressure = J/A + avg_osmotic
        required_driving = volumetric_flux / membrane_permeability  # Pa
        
        # Total pressure = permeate + driving + drop
        required_pressure = permeate_pressure + required_driving + pressure_drop
        
        # Ensure minimum driving pressure for mass transfer
        min_total = permeate_pressure + avg_osmotic + 5e5 + pressure_drop  # 5 bar minimum
        if required_pressure < min_total:
            logger.info(f"Membrane-aware pressure too low ({required_pressure/1e5:.1f} bar), "
                       f"using minimum {min_total/1e5:.1f} bar")
            required_pressure = min_total
        else:
            logger.info(f"Using membrane-aware pressure: {required_pressure/1e5:.1f} bar "
                       f"(A={membrane_permeability:.2e} m/s/Pa, flux={volumetric_flux:.2e} m/s)")
    else:
        # Standard calculation without membrane awareness
        required_pressure = (
            permeate_pressure + 
            avg_osmotic + 
            min_driving_pressure + 
            pressure_drop
        )
    
    logger.info(
        f"Pressure calculation for {target_recovery:.0%} recovery:\n"
        f"  Feed TDS: {feed_tds_ppm:.0f} ppm\n"
        f"  Concentrate TDS: {conc_tds_ppm:.0f} ppm (SP={salt_passage:.3f})\n"
        f"  Avg osmotic pressure: {avg_osmotic/1e5:.1f} bar\n"
        f"  Required pressure: {required_pressure/1e5:.1f} bar"
    )
    
    return required_pressure


def initialize_pump_with_pressure(
    pump,
    required_pressure: float,
    efficiency: float = 0.8
) -> None:
    """
    Initialize pump with specified outlet pressure.
    
    Note: Pump pressure is ALWAYS fixed during initialization for stability.
    It should be unfixed later if optimization is needed.
    
    Args:
        pump: WaterTAP Pump unit
        required_pressure: Required outlet pressure in Pa
        efficiency: Pump efficiency (default 0.8)
    """
    # Fix pressure for stable initialization - convert Pa to proper units
    pump.outlet.pressure[0].fix(required_pressure * pyunits.Pa)
    logger.info(f"Pump pressure fixed at: {required_pressure/1e5:.1f} bar for initialization")
    
    pump.efficiency_pump.fix(efficiency)
    
    # Initialize pump with state args to avoid bound issues
    # Check property package type by examining the inlet state block
    inlet_params = pump.control_volume.properties_in[0].params
    if hasattr(inlet_params, 'solute_set'):
        # MCAS - include all components
        inlet_state = {
            'flow_mass_phase_comp': {
                ('Liq', comp): value(pump.inlet.flow_mass_phase_comp[0, 'Liq', comp])
                for comp in ['H2O'] + list(inlet_params.solute_set)
            },
            'temperature': value(pump.inlet.temperature[0]),
            'pressure': required_pressure  # Use required pressure to avoid bound conflicts
        }
    else:
        # Standard package with TDS
        inlet_state = {
            'flow_mass_phase_comp': {
                ('Liq', 'H2O'): value(pump.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O']),
                ('Liq', 'TDS'): value(pump.inlet.flow_mass_phase_comp[0, 'Liq', 'TDS'])
            },
            'temperature': value(pump.inlet.temperature[0]),
            'pressure': required_pressure  # Use required pressure to avoid bound conflicts
        }
    
    pump.initialize(state_args=inlet_state)
    
    logger.info(f"Pump initialized successfully")


def initialize_ro_unit_elegant(
    ro_unit,
    target_recovery: Optional[float] = None,
    verbose: bool = False
) -> None:
    """
    Initialize RO unit with physically consistent state arguments.
    
    This prevents FBBT infeasibility by ensuring the RO unit sees
    valid pressure and flow conditions from the start.
    
    Args:
        ro_unit: WaterTAP ReverseOsmosis0D unit
        target_recovery: Optional target recovery for initial guess
        verbose: Print detailed initialization info
    """
    # Get inlet conditions (must be already propagated)
    time = 0  # Steady state
    inlet = ro_unit.inlet
    
    # Extract inlet state
    inlet_pressure = value(inlet.pressure[time])
    inlet_temp = value(inlet.temperature[time])
    
    # Get component flows - handle both mass and molar basis
    flow_basis = 'mass' if hasattr(inlet, 'flow_mass_phase_comp') else 'mol'
    
    # Get property package from RO unit config
    prop_params = ro_unit.config.property_package
    
    if flow_basis == 'mass':
        inlet_flows = {
            comp: value(inlet.flow_mass_phase_comp[time, 'Liq', comp])
            for comp in prop_params.component_list
        }
        # Calculate TDS for osmotic pressure check
        h2o_flow = inlet_flows.get('H2O', 0)
        tds_flow = sum(v for k, v in inlet_flows.items() if k != 'H2O')
        if h2o_flow > 0:
            feed_tds_ppm = (tds_flow / (h2o_flow + tds_flow)) * 1e6
            # Add debug logging
            logger.info(f"TDS calculation (mass basis): h2o_flow={h2o_flow:.6f} kg/s, tds_flow={tds_flow:.6f} kg/s")
            logger.info(f"Mass fraction: {tds_flow / (h2o_flow + tds_flow):.6f}, TDS ppm: {feed_tds_ppm:.0f}")
        else:
            feed_tds_ppm = 0
    else:
        # Molar basis - need molecular weights
        inlet_flows_mol = {
            comp: value(inlet.flow_mol_phase_comp[time, 'Liq', comp])
            for comp in prop_params.component_list
        }
        # Convert to mass for TDS calculation
        mw_data = prop_params.mw_data
        h2o_flow_kg = inlet_flows_mol.get('H2O', 0) * mw_data['H2O'] / 1000
        tds_flow_kg = sum(
            flow * mw_data[comp] / 1000
            for comp, flow in inlet_flows_mol.items()
            if comp != 'H2O'
        )
        if h2o_flow_kg > 0:
            feed_tds_ppm = (tds_flow_kg / (h2o_flow_kg + tds_flow_kg)) * 1e6
        else:
            feed_tds_ppm = 0
    
    # Check if pressure is sufficient
    permeate_pressure = value(ro_unit.permeate.pressure[time]) if hasattr(ro_unit.permeate.pressure[time], 'value') else 101325
    feed_osmotic = calculate_osmotic_pressure(feed_tds_ppm)
    min_required = permeate_pressure + feed_osmotic + 5e5  # 5 bar minimum driving
    
    if inlet_pressure < min_required:
        raise ValueError(
            f"Inlet pressure ({inlet_pressure/1e5:.1f} bar) is too low. "
            f"Need at least {min_required/1e5:.1f} bar for "
            f"feed with {feed_tds_ppm:.0f} ppm TDS."
        )
    
    # Create state args based on flow basis
    if flow_basis == 'mass':
        state_args = {
            "flow_mass_phase_comp": {
                ('Liq', comp): flow
                for comp, flow in inlet_flows.items()
            },
            "temperature": inlet_temp,
            "pressure": inlet_pressure
        }
    else:
        state_args = {
            "flow_mol_phase_comp": {
                ('Liq', comp): flow
                for comp, flow in inlet_flows_mol.items()
            },
            "temperature": inlet_temp,
            "pressure": inlet_pressure
        }
    
    # Initialize with state args
    init_options = {
        'nlp_scaling_method': 'user-scaling'
        # Note: linear_solver should be passed to get_solver(), not here
    }
    
    if verbose:
        logger.info(
            f"Initializing RO with:\n"
            f"  Pressure: {inlet_pressure/1e5:.1f} bar\n"
            f"  Temperature: {inlet_temp:.1f} K\n"
            f"  Feed TDS: {feed_tds_ppm:.0f} ppm\n"
            f"  Osmotic pressure: {feed_osmotic/1e5:.1f} bar\n"
            f"  Net driving pressure: {(inlet_pressure - permeate_pressure - feed_osmotic)/1e5:.1f} bar"
        )
    
    # Initialize RO with additional options to avoid FBBT issues
    init_options['bound_push'] = 1e-8
    
    # For MCAS models, provide initialize_guess to help with FBBT
    if hasattr(prop_params, 'solute_set'):
        # Calculate reasonable initial guesses based on expected recovery
        if target_recovery:
            # Use provided target recovery
            recovery_guess = target_recovery
        else:
            # Default guess
            recovery_guess = 0.5
        
        # Provide initialization guesses to avoid FBBT issues
        initialize_guess = {
            'deltaP': -0.5e5,  # 0.5 bar pressure drop
            'solvent_recovery': recovery_guess,
            'solute_recovery': 0.02,  # 98% rejection (applies to all solutes)
            'cp_modulus': 1.1  # 10% concentration polarization
        }
        
        # Initialize RO with guesses
        ro_unit.initialize(
            state_args=state_args,
            initialize_guess=initialize_guess,
            optarg=init_options
        )
    else:
        # Standard initialization for non-MCAS
        ro_unit.initialize(
            state_args=state_args,
            optarg=init_options
        )
    
    if verbose:
        # Report actual recovery achieved
        if flow_basis == 'mass':
            perm_h2o = value(ro_unit.permeate.flow_mass_phase_comp[time, 'Liq', 'H2O'])
            feed_h2o = inlet_flows.get('H2O', 0)
        else:
            perm_h2o = value(ro_unit.permeate.flow_mol_phase_comp[time, 'Liq', 'H2O'])
            feed_h2o = inlet_flows_mol.get('H2O', 0)
        
        if feed_h2o > 0:
            actual_recovery = perm_h2o / feed_h2o
            logger.info(f"RO initialized with recovery: {actual_recovery:.1%}")


def initialize_multistage_ro_elegant(
    model,
    config_data: Dict[str, Any],
    verbose: bool = True
) -> None:
    """
    Initialize complete multi-stage RO system using elegant approach.
    
    Args:
        model: Pyomo ConcreteModel with RO flowsheet
        config_data: Configuration dictionary from configure_ro tool
        verbose: Print detailed progress
    """
    n_stages = config_data['stage_count']
    
    if verbose:
        logger.info(f"Initializing {n_stages}-stage RO system")
    
    # Initialize feed
    model.fs.feed.initialize()
    
    # Get feed composition for pressure calculations
    feed_h2o_kg_s = value(model.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
    
    # Check if using MCAS (multiple ions) or standard (TDS)
    if hasattr(model.fs.properties, 'solute_set'):
        # MCAS - sum all ion flows
        feed_tds_kg_s = 0
        for comp in model.fs.properties.solute_set:
            feed_tds_kg_s += value(model.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', comp])
    else:
        # Standard property package with TDS
        feed_tds_kg_s = value(model.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'TDS'])
    
    feed_tds_ppm = (feed_tds_kg_s / (feed_h2o_kg_s + feed_tds_kg_s)) * 1e6
    
    # Determine salt passage based on water type
    if feed_tds_ppm > 30000:  # Seawater/brine
        default_salt_passage = 0.05
    elif feed_tds_ppm > 10000:  # High brackish
        default_salt_passage = 0.03
    else:  # Standard brackish
        default_salt_passage = 0.015
    
    logger.info(f"Using salt passage estimate of {default_salt_passage:.3f} based on feed TDS")
    
    # Keep track of cumulative TDS for each stage
    current_tds_ppm = feed_tds_ppm
    
    for i in range(1, n_stages + 1):
        if verbose:
            logger.info(f"\n--- Initializing Stage {i} ---")
        
        pump = getattr(model.fs, f"pump{i}")
        ro = getattr(model.fs, f"ro_stage{i}")
        product = getattr(model.fs, f"stage_product{i}")
        
        # Get stage configuration
        stage_data = config_data['stages'][i-1]
        target_recovery = stage_data.get('stage_recovery', 0.5)
        
        # Propagate state to pump
        if i == 1:
            propagate_state(arc=model.fs.feed_to_pump1)
        else:
            # Use correct arc name that matches builder: ro_stage{i}_to_pump{i+1}
            arc_name = f"ro_stage{i-1}_to_pump{i}"
            if not hasattr(model.fs, arc_name):
                # Fallback for legacy naming
                arc_name = f"ro{i-1}_to_pump{i}" if hasattr(model.fs, f"ro{i-1}_to_pump{i}") else f"stage{i-1}_to_pump{i}"
            propagate_state(arc=getattr(model.fs, arc_name))
        
        # Calculate required pressure for this stage
        # Dynamic pressure requirements based on TDS and recovery
        # Higher TDS and recovery require exponentially more pressure
        if current_tds_ppm > 50000:  # Very high TDS
            min_driving = 30e5  # 30 bar minimum
        elif current_tds_ppm > 30000:  # High TDS
            min_driving = 25e5  # 25 bar minimum
        elif target_recovery > 0.7:  # High recovery
            min_driving = 25e5  # 25 bar for high recovery
        elif target_recovery > 0.5:  # Medium recovery
            min_driving = 20e5  # 20 bar
        else:
            min_driving = 15e5  # 15 bar for standard conditions
        
        # Additional driving pressure for later stages due to concentration effects
        stage_factor = 1 + 0.2 * (i - 1)  # 20% increase per stage
        min_driving *= stage_factor
        
        required_pressure = calculate_required_pressure(
            current_tds_ppm,
            target_recovery,
            permeate_pressure=101325,  # 1 atm
            min_driving_pressure=min_driving,
            pressure_drop=0.5e5,  # Account for pressure drop
            salt_passage=default_salt_passage
        )
        
        # Enhanced safety factor for robustness
        # Higher safety factor for: later stages, high recovery, high TDS
        tds_factor = 1 + min(0.3, current_tds_ppm / 100000)  # Up to 30% for very high TDS
        recovery_factor = 1 + 0.3 * max(0, target_recovery - 0.5)  # Up to 15% for high recovery
        stage_safety = 1 + 0.1 * (i - 1)  # 10% per stage
        
        safety_factor = tds_factor * recovery_factor * stage_safety
        required_pressure *= safety_factor
        
        # Cap at maximum pressure but warn if hitting limit
        max_pressure = 80e5  # 80 bar
        if required_pressure > max_pressure:
            logger.warning(
                f"Stage {i} calculated pressure ({required_pressure/1e5:.1f} bar) exceeds "
                f"maximum ({max_pressure/1e5:.1f} bar). Capping at maximum."
            )
            required_pressure = max_pressure
        
        # Initialize pump with calculated pressure (fixed for stability)
        initialize_pump_with_pressure(pump, required_pressure)
        
        # Propagate to RO
        if i == 1:
            # Use correct arc name that matches builder
            propagate_state(arc=model.fs.pump1_to_ro_stage1)
        else:
            # Check for correct arc names in order of preference
            arc_name = f"pump{i}_to_ro_stage{i}"
            if not hasattr(model.fs, arc_name):
                # Fallback for legacy naming
                arc_name = f"pump{i}_to_ro{i}" if hasattr(model.fs, f"pump{i}_to_ro{i}") else f"pump{i}_to_stage{i}"
            propagate_state(arc=getattr(model.fs, arc_name))
        
        # Initialize RO with elegant approach
        initialize_ro_unit_elegant(ro, target_recovery, verbose)
        
        # Update TDS for next stage using actual model results when available
        if i == 1:
            # For first stage, we don't have actual results yet during initialization
            # Use estimate with appropriate salt passage
            current_tds_ppm = calculate_concentrate_tds(
                current_tds_ppm, 
                target_recovery, 
                salt_passage=default_salt_passage
            )
            logger.info(f"Stage {i} estimated concentrate TDS: {current_tds_ppm:.0f} ppm")
        else:
            # For subsequent stages, try to use actual concentrate TDS from previous stage
            # but apply sanity checks and use conservative estimates if needed
            prev_ro = getattr(model.fs, f"ro_stage{i-1}")
            estimated_tds = calculate_concentrate_tds(
                current_tds_ppm, 
                target_recovery, 
                salt_passage=default_salt_passage
            )
            
            try:
                actual_tds = get_stream_tds_ppm(prev_ro.retentate)
                
                # Sanity check: actual TDS should be reasonable
                if actual_tds < current_tds_ppm * 0.5 or actual_tds > current_tds_ppm * 5:
                    logger.warning(
                        f"Stage {i-1} actual concentrate TDS ({actual_tds:.0f} ppm) seems unreasonable "
                        f"compared to feed TDS ({current_tds_ppm:.0f} ppm). Using conservative estimate."
                    )
                    # Use the higher of estimated or a conservative multiplier
                    current_tds_ppm = max(estimated_tds, current_tds_ppm * 1.5)
                else:
                    logger.info(
                        f"Stage {i-1} actual concentrate TDS: {actual_tds:.0f} ppm "
                        f"(estimated was {estimated_tds:.0f} ppm)"
                    )
                    # Use a weighted average favoring the actual value but with some conservatism
                    current_tds_ppm = 0.8 * actual_tds + 0.2 * max(actual_tds, estimated_tds)
                    
            except Exception as e:
                # Fallback if stream extraction fails
                logger.warning(
                    f"Could not extract actual TDS from stage {i-1}: {e}\n"
                    f"Using conservative estimate"
                )
                # Use conservative estimate for robustness
                current_tds_ppm = max(estimated_tds, current_tds_ppm * 1.3)
        
        # Sanity check to prevent numerical issues
        if current_tds_ppm > 100000:  # 100,000 ppm
            logger.warning(
                f"Stage {i-1} concentrate TDS ({current_tds_ppm:.0f} ppm) "
                f"exceeds 100,000 ppm - capping to prevent numerical issues"
            )
            current_tds_ppm = 100000
        
        # Propagate to product
        if i == 1:
            propagate_state(arc=model.fs.ro1_perm_to_prod)
        else:
            arc_name = f"ro{i}_perm_to_prod{i}"
            propagate_state(arc=getattr(model.fs, arc_name))
        
        product.initialize()
    
    # Initialize final concentrate product
    if hasattr(model.fs, 'concentrate_product'):
        propagate_state(arc=model.fs.final_conc_arc)
        model.fs.concentrate_product.initialize()
    
    if verbose:
        logger.info("\nMulti-stage RO initialization complete!")