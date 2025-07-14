"""
Elegant RO initialization utilities for WaterTAP models.

This module provides physics-based initialization functions that prevent
FBBT (Feasibility-Based Bound Tightening) infeasibility by ensuring
pressure variables are properly set before initialization.
"""

from typing import Dict, Any, Optional
from pyomo.environ import value
from idaes.core.util.initialization import propagate_state
import logging

logger = logging.getLogger(__name__)


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


def calculate_concentrate_tds(feed_tds_ppm: float, recovery: float) -> float:
    """
    Calculate concentrate TDS based on recovery and perfect salt rejection.
    
    Args:
        feed_tds_ppm: Feed TDS concentration in ppm
        recovery: Water recovery fraction (0-1)
        
    Returns:
        Concentrate TDS in ppm
    """
    if recovery >= 1.0:
        raise ValueError(f"Recovery must be less than 1, got {recovery}")
    
    # Assuming perfect salt rejection
    concentrate_tds_ppm = feed_tds_ppm / (1 - recovery)
    
    return concentrate_tds_ppm


def calculate_required_pressure(
    feed_tds_ppm: float,
    target_recovery: float,
    permeate_pressure: float = 101325,  # 1 atm default
    min_driving_pressure: float = 15e5,  # 15 bar default
    pressure_drop: float = 0.5e5  # 0.5 bar default
) -> float:
    """
    Calculate required feed pressure for RO operation.
    
    Args:
        feed_tds_ppm: Feed TDS concentration in ppm
        target_recovery: Target water recovery fraction
        permeate_pressure: Permeate pressure in Pa
        min_driving_pressure: Minimum net driving pressure in Pa
        pressure_drop: Pressure drop across membrane in Pa
        
    Returns:
        Required feed pressure in Pa
    """
    # Calculate concentrate TDS
    conc_tds_ppm = calculate_concentrate_tds(feed_tds_ppm, target_recovery)
    
    # Calculate average osmotic pressure
    feed_osmotic = calculate_osmotic_pressure(feed_tds_ppm)
    conc_osmotic = calculate_osmotic_pressure(conc_tds_ppm)
    avg_osmotic = (feed_osmotic + conc_osmotic) / 2
    
    # Required pressure = permeate pressure + osmotic + driving + drop
    required_pressure = (
        permeate_pressure + 
        avg_osmotic + 
        min_driving_pressure + 
        pressure_drop
    )
    
    logger.info(
        f"Pressure calculation for {target_recovery:.0%} recovery:\n"
        f"  Feed TDS: {feed_tds_ppm:.0f} ppm\n"
        f"  Concentrate TDS: {conc_tds_ppm:.0f} ppm\n"
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
    # Fix pressure for stable initialization
    pump.outlet.pressure[0].fix(required_pressure)
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
        'nlp_scaling_method': 'user-scaling',
        'linear_solver': 'ma27'
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
            arc_name = f"ro{i-1}_to_pump{i}" if hasattr(model.fs, f"ro{i-1}_to_pump{i}") else f"stage{i-1}_to_pump{i}"
            propagate_state(arc=getattr(model.fs, arc_name))
        
        # Calculate required pressure for this stage
        # For high recovery, need higher driving pressure
        min_driving = 15e5 if target_recovery < 0.5 else 20e5
        if target_recovery > 0.7:
            min_driving = 25e5  # 25 bar for high recovery
        
        required_pressure = calculate_required_pressure(
            current_tds_ppm,
            target_recovery,
            permeate_pressure=101325,  # 1 atm
            min_driving_pressure=min_driving,
            pressure_drop=0.5e5  # Account for pressure drop
        )
        
        # Add safety factor for later stages and high recovery
        safety_factor = 1.1 + 0.1 * (i - 1) + 0.2 * max(0, target_recovery - 0.5)
        required_pressure *= safety_factor
        
        # Cap at maximum pressure
        max_pressure = 80e5  # 80 bar
        required_pressure = min(required_pressure, max_pressure)
        
        # Initialize pump with calculated pressure (fixed for stability)
        initialize_pump_with_pressure(pump, required_pressure)
        
        # Propagate to RO
        if i == 1:
            propagate_state(arc=model.fs.pump1_to_ro1)
        else:
            arc_name = f"pump{i}_to_ro{i}" if hasattr(model.fs, f"pump{i}_to_ro{i}") else f"pump{i}_to_stage{i}"
            propagate_state(arc=getattr(model.fs, arc_name))
        
        # Initialize RO with elegant approach
        initialize_ro_unit_elegant(ro, target_recovery, verbose)
        
        # Update TDS for next stage (concentrate from this stage)
        current_tds_ppm = calculate_concentrate_tds(current_tds_ppm, target_recovery)
        
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