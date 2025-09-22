"""
Enhanced RO model building utilities with detailed economic modeling (v2).

This module provides advanced model building with:
- WaterTAPCostingDetailed for full economic transparency  
- ZO pretreatment units (cartridge filters, chemical dosing)
- Energy Recovery Devices (ERD) with auto-detection
- CIP system modeling
- Chemical consumption tracking
- Support for plant-wide optimization
"""

from typing import Dict, Any, Optional
import logging

from pyomo.environ import (
    ConcreteModel, Constraint, value, TransformationFactory, 
    Reference, units as pyunits, Var, Expression, Block
)
from pyomo.network import Arc
from idaes.core import FlowsheetBlock, UnitModelCostingBlock
from idaes.core.util.scaling import calculate_scaling_factors
from idaes.models.unit_models import Feed, Product, Mixer, Separator, Translator
from idaes.models.unit_models.mixer import MixingType, MomentumMixingType

# WaterTAP imports
from watertap.unit_models.reverse_osmosis_0D import (
    ReverseOsmosis0D,
    ConcentrationPolarizationType,
    MassTransferCoefficient,
    PressureChangeType
)
from watertap.unit_models.pressure_changer import Pump
from watertap.costing import WaterTAPCostingDetailed  # Use detailed costing
from watertap.costing.unit_models.pump import cost_pump
from watertap.costing.unit_models.reverse_osmosis import cost_reverse_osmosis
from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock, MaterialFlowBasis
from watertap.core.membrane_channel_base import TransportModel
from watertap.core import ModuleType

# Zero-order models for pretreatment
from watertap.unit_models.zero_order import (
    CartridgeFiltrationZO,
    ChemicalAdditionZO
)
from watertap.core.zero_order_properties import WaterParameterBlock
from watertap.core.wt_database import Database

# Energy recovery device
from watertap.unit_models.pressure_exchanger import PressureExchanger
from watertap.costing.unit_models.energy_recovery_device import cost_pressure_exchanger_erd

# Import membrane properties handler
from .membrane_properties_handler import (
    get_membrane_properties_mcas,
    get_membrane_from_catalog,
)
from .mcas_builder import estimate_solution_density
from .ro_initialization import calculate_concentrate_tds
from .logging_config import get_configured_logger

logger = get_configured_logger(__name__)


def build_ro_model_v2(
    config_data: Dict[str, Any],
    mcas_config: Dict[str, Any],
    feed_salinity_ppm: float,
    feed_temperature_c: float,
    membrane_type: str,
    economic_params: Dict[str, Any] = None,
    chemical_dosing: Dict[str, Any] = None,
    membrane_properties: Optional[Dict[str, float]] = None,
    optimization_mode: bool = False
) -> ConcreteModel:
    """
    Build enhanced WaterTAP RO model with detailed economic modeling.
    
    Features:
    - WaterTAPCostingDetailed for full transparency
    - ZO pretreatment units (filters, dosing)
    - ERD with auto-detection for high pressure
    - CIP system with chemical consumption
    - Translator blocks for property package bridging
    - Support for optimization mode
    
    Args:
        config_data: RO configuration from optimize_ro_configuration
        mcas_config: MCAS property configuration
        feed_salinity_ppm: Feed salinity in ppm
        feed_temperature_c: Feed temperature in C
        membrane_type: "brackish" or "seawater"
        economic_params: Economic parameters (validated)
        chemical_dosing: Chemical dosing parameters (validated)
        membrane_properties: Optional membrane properties override
        optimization_mode: If True, prepare for optimization (don't fix all vars)
        
    Returns:
        ConcreteModel with enhanced RO system
    """
    # Create concrete model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    
    # Store configuration for later use
    m.config = config_data
    m.membrane_type = membrane_type
    
    # Extract configuration
    n_stages = config_data.get('n_stages', config_data.get('stage_count', 1))
    # Prefer unified recycle_info structure; fall back to legacy recycle_ratio
    recycle_info = config_data.get('recycle_info', {})
    has_recycle = recycle_info.get('uses_recycle', config_data.get('recycle_ratio', 0) > 0)
    
    logger.info(f"Building v2 model: {n_stages} stages, recycle={has_recycle}, membrane={membrane_type}")
    
    # =================================================================
    # Property Packages
    # =================================================================
    
    # MCAS property package for RO
    # Filter MCAS config to only include parameters MCASParameterBlock accepts
    mcas_params = {
        'solute_list': mcas_config['solute_list'],
        'mw_data': mcas_config['mw_data'],
        'material_flow_basis': MaterialFlowBasis.mass,  # Use mass flow for RO
    }
    
    # Add optional parameters if present in config
    if 'charge' in mcas_config:
        mcas_params['charge'] = mcas_config['charge']
    if 'diffusivity_data' in mcas_config:
        mcas_params['diffusivity_data'] = mcas_config['diffusivity_data']
    if 'stokes_radius_data' in mcas_config:
        mcas_params['stokes_radius_data'] = mcas_config['stokes_radius_data']
    if 'activity_coefficient_model' in mcas_config:
        mcas_params['activity_coefficient_model'] = mcas_config['activity_coefficient_model']
    
    m.fs.properties = MCASParameterBlock(**mcas_params)
    
    # =================================================================
    # Dynamic Scaling Setup (Critical for FBBT convergence)
    # =================================================================
    
    # Set dynamic scaling factors based on actual feed conditions
    from .mcas_builder import estimate_solution_density
    
    # Get feed conditions
    ion_composition_mg_l = mcas_config.get('ion_composition_mg_l', {})
    fresh_feed_flow_m3_s = config_data['feed_flow_m3h'] / 3600  # Convert to m³/s
    
    # Calculate total TDS for density estimation
    total_tds_mg_l = sum(ion_composition_mg_l.values()) if ion_composition_mg_l else feed_salinity_ppm
    
    # Estimate solution density
    solution_density_kg_m3 = estimate_solution_density(total_tds_mg_l)
    
    # Water gets scaling factor of 1 (it's ~1 kg/s scale)
    m.fs.properties.set_default_scaling("flow_mass_phase_comp", 1, index=("Liq", "H2O"))
    # Water concentration (density-based)
    m.fs.properties.set_default_scaling("conc_mass_phase_comp", 1.0/solution_density_kg_m3, index=("Liq", "H2O"))
    # Water mass fraction is close to 1
    m.fs.properties.set_default_scaling("mass_frac_phase_comp", 1.0, index=("Liq", "H2O"))
    
    # CRITICAL: Calculate total reference TDS to scale to actual feed_salinity_ppm
    total_tds_config = sum(ion_composition_mg_l.values())
    
    for comp in mcas_config['solute_list']:
        config_conc_mg_l = ion_composition_mg_l.get(comp, 0)
        
        # Scale concentration to actual feed_salinity_ppm
        if config_conc_mg_l > 0 and total_tds_config > 0:
            actual_conc_mg_l = config_conc_mg_l * (feed_salinity_ppm / total_tds_config)
        else:
            actual_conc_mg_l = config_conc_mg_l
        
        if actual_conc_mg_l > 0:
            # Calculate expected flow rate in kg/s using ACTUAL concentration
            expected_flow_kg_s = actual_conc_mg_l * fresh_feed_flow_m3_s / 1000
            # Calculate expected concentration in kg/m³
            conc_kg_m3 = actual_conc_mg_l * 1e-3
            # Calculate expected mass fraction
            mass_frac = conc_kg_m3 / solution_density_kg_m3
            
            if expected_flow_kg_s > 0:
                # Flow mass scaling
                flow_scale_factor = 1.0 / max(expected_flow_kg_s, 1e-12)
                flow_scale_factor = max(1e-2, min(1e6, flow_scale_factor))
                m.fs.properties.set_default_scaling("flow_mass_phase_comp", flow_scale_factor, index=("Liq", comp))
                
                # Concentration scaling - critical for FBBT
                conc_scale_factor = 1.0 / max(conc_kg_m3, 1e-9)
                conc_scale_factor = max(1e-2, min(1e6, conc_scale_factor))
                m.fs.properties.set_default_scaling("conc_mass_phase_comp", conc_scale_factor, index=("Liq", comp))
                
                # Mass fraction scaling
                frac_scale_factor = 1.0 / max(mass_frac, 1e-12)
                frac_scale_factor = max(1e-2, min(1e6, frac_scale_factor))
                m.fs.properties.set_default_scaling("mass_frac_phase_comp", frac_scale_factor, index=("Liq", comp))
                
                logger.debug(f"V2 Scaling for {comp}: flow={flow_scale_factor:.2e}, conc={conc_scale_factor:.2e} "
                           f"(actual: {actual_conc_mg_l:.1f} mg/L from {feed_salinity_ppm:.0f} mg/L TDS)")
            else:
                # Default for very small concentrations
                m.fs.properties.set_default_scaling("flow_mass_phase_comp", 1e4, index=("Liq", comp))
                m.fs.properties.set_default_scaling("conc_mass_phase_comp", 1e4, index=("Liq", comp))
                m.fs.properties.set_default_scaling("mass_frac_phase_comp", 1e4, index=("Liq", comp))
        else:
            # Default for zero concentration
            m.fs.properties.set_default_scaling("flow_mass_phase_comp", 1e3, index=("Liq", comp))
            m.fs.properties.set_default_scaling("conc_mass_phase_comp", 1e3, index=("Liq", comp))
            m.fs.properties.set_default_scaling("mass_frac_phase_comp", 1e3, index=("Liq", comp))
    
    # Pressure scaling (expecting ~50 bar = 5e6 Pa)
    m.fs.properties.set_default_scaling("pressure", 1e-6)
    # Temperature scaling (expecting ~300 K)
    m.fs.properties.set_default_scaling("temperature", 1e-2)
    
    # Water property package for ZO pretreatment (if needed)
    if economic_params and economic_params.get("include_cartridge_filters"):
        m.fs.properties_pretreat = WaterParameterBlock(
            solute_list=["tds", "tss"]
        )
        # Initialize database for ZO models
        m.db = Database()
    
    # =================================================================
    # Main RO System (existing logic with enhancements)
    # =================================================================
    
    # Check if we'll have ERD (needed to avoid creating conflicting arcs)
    will_have_erd = False
    if economic_params:
        will_have_erd = _should_include_erd(config_data, economic_params, membrane_type)
    
    # Build standard RO stages and recycle infrastructure (creates feed, product, disposal)
    _build_ro_stages(m, n_stages, config_data, has_recycle, will_have_erd)

    # =================================================================
    # Fresh Feed Initialization (critical to set correct TDS/flows)
    # Mirrors proven v1 logic to avoid default MCAS initial guesses
    # =================================================================
    try:
        # Volumetric feed flow [m^3/s]
        fresh_feed_flow_m3_s = config_data['feed_flow_m3h'] / 3600

        # Reference to fresh feed outlet state block
        feed_state = m.fs.fresh_feed.outlet

        # Fix temperature and pressure
        feed_state.temperature.fix((273.15 + feed_temperature_c) * pyunits.K)
        feed_state.pressure.fix(1 * pyunits.atm)

        # Component flows based on ion composition (mass basis)
        ion_composition_mg_l = mcas_config['ion_composition_mg_l']

        # Estimate realistic solution density from TDS and temperature
        total_tds_mg_l = sum(ion_composition_mg_l.values())
        solution_density_kg_m3 = estimate_solution_density(total_tds_mg_l, feed_temperature_c)
        logger.info(f"Solution density: {solution_density_kg_m3:.1f} kg/m³ (TDS: {total_tds_mg_l:.0f} mg/L)")

        # Fix solute flows; accumulate total solute mass flow
        total_ion_flow_kg_s = 0.0
        for comp in m.fs.properties.solute_set:
            conc_mg_l = ion_composition_mg_l.get(comp, 0.0)
            ion_flow_kg_s = conc_mg_l * fresh_feed_flow_m3_s / 1000.0  # mg/L * m³/s / 1000 = kg/s

            # Ensure tiny floor for numerical robustness (1 ppb of volumetric flow)
            min_flow_kg_s = 1e-9 * fresh_feed_flow_m3_s
            ion_flow_kg_s = max(ion_flow_kg_s, min_flow_kg_s)

            feed_state.flow_mass_phase_comp[0, 'Liq', comp].fix(ion_flow_kg_s)
            total_ion_flow_kg_s += ion_flow_kg_s

        # Fix water flow as total mass flow minus solutes
        total_mass_flow_kg_s = fresh_feed_flow_m3_s * solution_density_kg_m3
        water_flow_kg_s = total_mass_flow_kg_s - total_ion_flow_kg_s
        if water_flow_kg_s <= 0:
            raise ValueError(
                f"Calculated negative water flow ({water_flow_kg_s:.2e} kg/s). "
                f"Total ion flow ({total_ion_flow_kg_s:.2e} kg/s) exceeds total mass flow "
                f"({total_mass_flow_kg_s:.2e} kg/s)"
            )
        feed_state.flow_mass_phase_comp[0, 'Liq', 'H2O'].fix(water_flow_kg_s)

        # Also fix temperature/pressure on the properties block (defined_state True)
        m.fs.fresh_feed.properties[0].temperature.fix((273.15 + feed_temperature_c) * pyunits.K)
        m.fs.fresh_feed.properties[0].pressure.fix(1 * pyunits.atm)

    except Exception as e:
        logger.error(f"Failed to initialize fresh feed conditions: {e}")
        raise

    # -----------------------------------------------------------------
    # Apply critical physical bounds and initializations (mirror v1)
    # - Flux bounds and initial values to avoid non-physical recoveries
    # - Tight concentration bounds to aid FBBT and avoid extreme TDS states
    # - Reasonable pump pressure bounds to prevent > 83 bar solutions
    # -----------------------------------------------------------------
    try:
        # Per-stage RO settings
        solute_list = list(m.fs.properties.solute_set)
        ion_comp = mcas_config.get('ion_composition_mg_l', {})

        # Pre-compute an approximate stage feed TDS progression to inform bounds
        # Start with overall feed TDS; update using previous stage recovery
        approx_stage_feed_tds_ppm = {}
        default_sp = 0.015 if feed_salinity_ppm <= 10000 else (0.03 if feed_salinity_ppm <= 30000 else 0.05)
        running_tds = feed_salinity_ppm
        for i in range(1, n_stages + 1):
            approx_stage_feed_tds_ppm[i] = max(0.0, running_tds)
            # Next stage sees previous stage concentrate; if last stage, this is unused
            stage_data_tmp = config_data['stages'][i-1]
            stage_rec_tmp = stage_data_tmp.get('stage_recovery', 0.5)
            try:
                running_tds = calculate_concentrate_tds(running_tds, stage_rec_tmp, salt_passage=default_sp)
            except Exception:
                # Conservative fallback if calc fails
                running_tds = running_tds / max(1e-6, (1 - stage_rec_tmp))

        for i in range(1, n_stages + 1):
            ro = getattr(m.fs, f"ro_stage{i}")

            # Set TDS-aware bounds and initial values for water flux
            if hasattr(ro, 'flux_mass_phase_comp'):
                stage_data = config_data['stages'][i-1]
                stage_area_m2 = stage_data.get('membrane_area_m2', 0.0)
                expected_flux_lmh = None
                if stage_area_m2 and stage_area_m2 > 0:
                    permeate_flow_m3h = stage_data.get('permeate_flow_m3h')
                    if permeate_flow_m3h is not None:
                        expected_flux_lmh = (permeate_flow_m3h / stage_area_m2) * 1000.0
                    else:
                        stage_rec = stage_data.get('stage_recovery')
                        if stage_rec is not None:
                            stage_feed_flow_m3h = stage_data.get('feed_flow_m3h')
                            if stage_feed_flow_m3h is None and i == 1:
                                stage_feed_flow_m3h = config_data.get('feed_flow_m3h')
                            if stage_feed_flow_m3h:
                                expected_flux_lmh = (
                                    stage_feed_flow_m3h * stage_rec * 1000.0 / stage_area_m2
                                )

                # Initial guess based on A and TDS-appropriate pressure
                try:
                    A_w = value(ro.A_comp[0, 'H2O'])
                except Exception:
                    A_w = 2e-12  # conservative fallback
                
                rho_water = 1000
                
                # Determine stage-specific TDS-aware flux bounds and typical pressure
                # Use the approximate per-stage feed TDS (accounts for previous stage concentration)
                stage_tds_ppm = approx_stage_feed_tds_ppm.get(i, feed_salinity_ppm)
                # Conversion: 1 LMH = 2.778e-4 kg/m²/s at ρ=1000 kg/m³
                if stage_tds_ppm <= 1000:  # Low TDS at this stage
                    jw_min_lmh = 1.0   # relaxed from 2.0 to be more robust
                    jw_max_lmh = 40.0  # 40 LMH maximum
                    typical_dp = 10e5  # 10 bar typical
                elif stage_tds_ppm <= 10000:  # Medium TDS at this stage
                    jw_min_lmh = 0.5   # relaxed from 1.0 to avoid infeasibility at Stage 2
                    jw_max_lmh = 30.0  # 30 LMH maximum
                    typical_dp = 20e5  # 20 bar typical
                else:  # High TDS at this stage
                    # For seawater/high-TDS, permit very low initial flux to avoid infeasibility
                    if (membrane_type == 'seawater') or (stage_tds_ppm >= 30000):
                        jw_min_lmh = 0.05  # 0.05 LMH minimum for robustness
                        jw_max_lmh = 25.0  # Increased from 18 to 25 LMH for feasibility
                        typical_dp = 55e5  # 55 bar typical for SWRO
                    elif i >= 2 or stage_tds_ppm >= 8000:
                        # For Stage 2+ or high-TDS brackish, use very low LB to prevent FBBT issues
                        jw_min_lmh = 0.01  # Very low LB for Stage 2+ initialization
                        jw_max_lmh = 25.0  # 25 LMH maximum
                        typical_dp = 40e5  # 40 bar typical
                    else:
                        jw_min_lmh = 0.2   # more permissive lower bound for robustness
                        jw_max_lmh = 25.0  # 25 LMH maximum
                        typical_dp = 40e5  # 40 bar typical
                
                # For later stages, reduce maximum flux by 10% per stage
                if i > 1:
                    jw_max_lmh *= (0.9 ** (i - 1))

                if expected_flux_lmh is not None:
                    design_upper = expected_flux_lmh * 1.2 + 5.0
                    jw_max_lmh = max(jw_max_lmh, design_upper)
                    jw_max_lmh = min(jw_max_lmh, 120.0)
                    jw_min_lmh = min(
                        jw_min_lmh,
                        max(0.0, expected_flux_lmh * 0.2)
                    )

                if jw_min_lmh >= jw_max_lmh:
                    jw_min_lmh = max(0.0, jw_max_lmh * 0.5)

                # Convert LMH to kg/m²/s
                jw_min = jw_min_lmh * 2.778e-4
                jw_max = jw_max_lmh * 2.778e-4

                # Calculate initial value
                Jw_init_mass = max(jw_min, min(jw_max, A_w * typical_dp * rho_water))

                for x in ro.feed_side.length_domain:
                    ro.flux_mass_phase_comp[0, x, 'Liq', 'H2O'].setlb(jw_min)
                    ro.flux_mass_phase_comp[0, x, 'Liq', 'H2O'].setub(jw_max)
                    ro.flux_mass_phase_comp[0, x, 'Liq', 'H2O'].set_value(Jw_init_mass)
                
                if expected_flux_lmh is not None:
                    logger.debug(
                        f"Stage {i}: Water flux bounds = [{jw_min_lmh:.1f}, {jw_max_lmh:.1f}] LMH, "
                        f"expected ≈ {expected_flux_lmh:.1f} LMH, initial = {Jw_init_mass:.2e} kg/m²/s"
                    )
                else:
                    logger.debug(
                        f"Stage {i}: Water flux bounds = [{jw_min_lmh:.1f}, {jw_max_lmh:.1f}] LMH, "
                        f"initial = {Jw_init_mass:.2e} kg/m²/s"
                    )

                # Solute flux bounds and initials
                for comp in solute_list:
                    # Estimate based on B and bulk concentration
                    try:
                        B_comp = value(ro.B_comp[0, comp])
                    except Exception:
                        B_comp = 1e-8
                    C_bulk_est = ion_comp.get(comp, 1.0) * 1e-3  # mg/L -> kg/m³
                    Js_init = max(1e-12, min(1e-3, B_comp * C_bulk_est))
                    for x in ro.feed_side.length_domain:
                        ro.flux_mass_phase_comp[0, x, 'Liq', comp].setlb(0.0)
                        ro.flux_mass_phase_comp[0, x, 'Liq', comp].setub(1e-3)
                        ro.flux_mass_phase_comp[0, x, 'Liq', comp].set_value(Js_init)

            # Tighten concentration bounds on feed-side properties
            try:
                total_tds_mg_l = sum(ion_comp.values())
                solution_density = 1000 + 0.68 * total_tds_mg_l / 1000

                property_locations = []
                if hasattr(ro.feed_side, 'properties_in'):
                    property_locations.append(ro.feed_side.properties_in[0])
                if hasattr(ro.feed_side, 'properties'):
                    for x in ro.feed_side.length_domain:
                        property_locations.append(ro.feed_side.properties[0, x])

                for comp in solute_list:
                    conc_feed_mg_l = ion_comp.get(comp, 1.0)
                    conc_feed_kg_m3 = conc_feed_mg_l * 1e-3
                    mass_frac_feed = conc_feed_kg_m3 / solution_density

                    for prop_block in property_locations:
                        if hasattr(prop_block, 'conc_mass_phase_comp'):
                            upper = max(10 * conc_feed_kg_m3, 1e-3)
                            prop_block.conc_mass_phase_comp[0, 'Liq', comp].setub(upper)
                            if conc_feed_mg_l < 1.0:
                                prop_block.conc_mass_phase_comp[0, 'Liq', comp].setlb(1e-10)
                        if hasattr(prop_block, 'mass_frac_phase_comp'):
                            upper_frac = min(10 * mass_frac_feed, 0.1)
                            prop_block.mass_frac_phase_comp[0, 'Liq', comp].setub(upper_frac)
                            if conc_feed_mg_l < 1.0:
                                prop_block.mass_frac_phase_comp[0, 'Liq', comp].setlb(1e-12)
            except Exception as _e:
                logger.debug(f"Could not tighten concentration bounds for stage {i}: {_e}")

        # Reasonable pump pressure bounds
        # Allow higher upper bound for seawater systems which may need >83 bar
        is_seawater = (membrane_type == 'seawater') or (feed_salinity_ppm >= 30000)
        pump_ub_bar = 120 if is_seawater else 83
        for i in range(1, n_stages + 1):
            pump = getattr(m.fs, f"pump{i}")
            try:
                pump.outlet.pressure[0].setlb(1 * pyunits.bar)
                pump.outlet.pressure[0].setub(pump_ub_bar * pyunits.bar)
            except Exception as _e:
                logger.debug(f"Could not set pump{i} pressure bounds: {_e}")
    except Exception as e:
        logger.warning(f"Skipping physical bounds application due to: {e}")
    
    # =================================================================
    # Pretreatment Units (if included)
    # =================================================================
    
    if economic_params and economic_params.get("include_cartridge_filters"):
        # Pretreatment disabled for v2 - too many property package issues
        # CartridgeFiltrationZO needs WaterParameterBlock but we use MCAS
        # Translator between them doesn't work properly
        logger.warning("Pretreatment requested but disabled in v2 - property package incompatibility")
        logger.warning("CartridgeFiltrationZO requires WaterParameterBlock, fresh_feed uses MCAS")
    
    # =================================================================
    # Energy Recovery Device (auto or explicit)
    # =================================================================
    
    if economic_params:
        include_erd = _should_include_erd(config_data, economic_params, membrane_type)
        
        if include_erd:
            logger.info("Adding Energy Recovery Device (pressure exchanger)...")
            
            m.fs.erd = PressureExchanger(
                property_package=m.fs.properties
            )
            
            # Set ERD efficiency
            m.fs.erd.efficiency_pressure_exchanger.fix(
                economic_params.get("erd_efficiency", 0.95)
            )
            
            # Wire ERD connections - simplified approach without feed splitting
            # Connect final RO concentrate to ERD brine inlet
            last_stage = getattr(m.fs, f"ro_stage{n_stages}")
            
            # Route last stage concentrate through ERD
            # Note: final_conc_to_split was not created because will_have_erd=True
            m.fs.last_stage_to_erd = Arc(
                source=last_stage.retentate,
                destination=m.fs.erd.brine_inlet
            )
            logger.info(f"Created last_stage_to_erd arc: {m.fs.last_stage_to_erd}")
            
            # ERD brine outlet to recycle splitter
            m.fs.erd_to_split = Arc(
                source=m.fs.erd.brine_outlet,
                destination=m.fs.recycle_split.inlet
            )
            logger.info(f"Created erd_to_split arc: {m.fs.erd_to_split}")
            
            # For ERD feed side, create a dummy feed source
            # This represents the portion of feed that would go through ERD
            from idaes.models.unit_models import Feed
            m.fs.erd_feed_source = Feed(property_package=m.fs.properties)
            logger.info(f"Created erd_feed_source: {m.fs.erd_feed_source}")
            
            # Connect dummy feed to ERD feed inlet
            m.fs.erd_feed_to_erd = Arc(
                source=m.fs.erd_feed_source.outlet,
                destination=m.fs.erd.feed_inlet
            )
            logger.info(f"Created erd_feed_to_erd arc: {m.fs.erd_feed_to_erd}")
            
            # ERD feed outlet to product (represents boosted flow)
            m.fs.erd_product = Product(property_package=m.fs.properties)
            logger.info(f"Created erd_product: {m.fs.erd_product}")
            m.fs.erd_out_to_product = Arc(
                source=m.fs.erd.feed_outlet,
                destination=m.fs.erd_product.inlet
            )
            logger.info(f"Created erd_out_to_product arc: {m.fs.erd_out_to_product}")
            
            logger.info("ERD wired with simplified dummy feed approach (4 ports connected)")
    
    # =================================================================
    # CIP System (if included)
    # =================================================================
    
    if economic_params and economic_params.get("include_cip_system") and chemical_dosing:
        logger.info("Adding CIP system block...")
        
        m.fs.cip_system = Block()
        
        # Calculate total membrane area
        total_membrane_area = sum(
            getattr(m.fs, f"ro_stage{i}").area
            for i in range(1, n_stages + 1)
        )
        
        # CIP chemical consumption
        m.fs.cip_system.chemical_consumption_kg_year = Expression(
            expr=pyunits.convert(
                total_membrane_area
                * chemical_dosing["cip_dose_kg_per_m2"] * (pyunits.kg/pyunits.m**2)
                * chemical_dosing["cip_frequency_per_year"] / pyunits.year,
                to_units=pyunits.kg/pyunits.year,
            )
        )
        
        # CIP capital cost
        m.fs.cip_system.capital_cost_per_m2 = Var(
            initialize=economic_params.get("cip_capital_cost_usd_m2", 50)
            # Note: Currency units not directly supported in pyunits
        )
        m.fs.cip_system.capital_cost_per_m2.fix()
        
        m.fs.cip_system.capital_cost_total = Expression(
            expr=m.fs.cip_system.capital_cost_per_m2 * total_membrane_area
        )
    
    # =================================================================
    # WaterTAPCostingDetailed
    # =================================================================
    
    if economic_params:
        logger.info("Adding WaterTAPCostingDetailed framework...")
        
        m.fs.costing = WaterTAPCostingDetailed()
        
        # Set all economic parameters
        m.fs.costing.wacc.fix(economic_params["wacc"])
        m.fs.costing.plant_lifetime.fix(economic_params["plant_lifetime_years"])
        m.fs.costing.utilization_factor.fix(economic_params["utilization_factor"])
        # WaterTAP expects electricity cost in $/kWh; do not rescale
        m.fs.costing.electricity_cost.fix(
            economic_params["electricity_cost_usd_kwh"]
        )
        
        # Set detailed percentages
        m.fs.costing.land_cost_percent_FCI.fix(
            economic_params.get("land_cost_percent_FCI", 0.0015)
        )
        m.fs.costing.working_capital_percent_FCI.fix(
            economic_params.get("working_capital_percent_FCI", 0.05)
        )
        m.fs.costing.salaries_percent_FCI.fix(
            economic_params.get("salaries_percent_FCI", 0.001)
        )
        m.fs.costing.benefit_percent_of_salary.fix(
            economic_params.get("benefit_percent_of_salary", 0.9)
        )
        m.fs.costing.maintenance_costs_percent_FCI.fix(
            economic_params.get("maintenance_costs_percent_FCI", 0.008)
        )
        m.fs.costing.laboratory_fees_percent_FCI.fix(
            economic_params.get("laboratory_fees_percent_FCI", 0.003)
        )
        m.fs.costing.insurance_and_taxes_percent_FCI.fix(
            economic_params.get("insurance_and_taxes_percent_FCI", 0.002)
        )
        
        # Add unit costing blocks
        _add_unit_costing(m, n_stages, config_data, economic_params, membrane_type)
        
        # Add chemical flow costing
        if chemical_dosing:
            _add_chemical_costing(m, n_stages, economic_params, chemical_dosing)
        
        # Process costs to aggregate
        m.fs.costing.cost_process()
        
        # Add LCOW and SEC
        product_flow = _get_product_flow(m, n_stages)
        m.fs.costing.add_LCOW(product_flow)
        m.fs.costing.add_specific_energy_consumption(product_flow)
        
        # Initialize costing to set initial values and avoid lazy evaluation surprises
        try:
            m.fs.costing.initialize()
        except Exception as _e:
            logger.warning(f"Costing initialize() skipped or failed: {_e}")
        
        logger.info("WaterTAPCostingDetailed framework initialized successfully")
    
    # NOTE: Scaling factors are now calculated in simulate_ro_v2.py after pump initialization
    # This ensures positive Net Driving Pressure (NDP) before FBBT runs
    # calculate_scaling_factors(m)  # Moved to solver to fix FBBT errors
    
    # Expand arcs
    # Debug: Check all arcs before expansion
    logger.info("Checking all arcs before expansion...")
    for comp_name in m.fs.component_objects(Arc, active=True):
        arc = getattr(m.fs, comp_name.local_name)
        if arc is None:
            logger.error(f"Arc {comp_name.local_name} is None!")
        else:
            logger.debug(f"Arc {comp_name.local_name} exists: {arc}")
    
    TransformationFactory("network.expand_arcs").apply_to(m)
    
    return m


def _build_ro_stages(m, n_stages, config_data, has_recycle, will_have_erd=False):
    """Build RO stages with unified architecture matching v1."""
    
    # =================================================================
    # Create unified architecture components (like v1)
    # =================================================================
    
    # Fresh feed (renamed for consistency with solver expectations)
    m.fs.fresh_feed = Feed(property_package=m.fs.properties)
    
    # ALWAYS create recycle split (even for no-recycle case)
    m.fs.recycle_split = Separator(
        property_package=m.fs.properties,
        outlet_list=["disposal", "recycle"]
    )
    
    # ALWAYS create feed mixer (even for no-recycle case)
    m.fs.feed_mixer = Mixer(
        property_package=m.fs.properties,
        inlet_list=["fresh", "recycle"],
        energy_mixing_type=MixingType.none,  # Required for MCAS
        momentum_mixing_type=MomentumMixingType.none
    )
    
    # With MomentumMixingType.none, we need to explicitly set outlet pressure
    m.fs.mixer_pressure_constraint = Constraint(
        expr=m.fs.feed_mixer.outlet.pressure[0] == m.fs.feed_mixer.fresh.pressure[0]
    )
    
    # Per-stage products (to match v1 and solver expectations)
    for i in range(1, n_stages + 1):
        product = Product(property_package=m.fs.properties)
        setattr(m.fs, f"stage_product{i}", product)
    
    # Disposal product (required by solver)
    m.fs.disposal_product = Product(property_package=m.fs.properties)
    
    # Also create aggregate product/disposal for v2 reporting
    m.fs.product = Product(property_package=m.fs.properties)
    m.fs.disposal = Product(property_package=m.fs.properties)
    
    # =================================================================
    # Build RO stages (pumps and RO units)
    # =================================================================
    for i in range(1, n_stages + 1):
        # Create pump
        pump = Pump(property_package=m.fs.properties)
        setattr(m.fs, f"pump{i}", pump)
        
        # Create RO stage - use v1's proven configuration
        ro = ReverseOsmosis0D(
            property_package=m.fs.properties,
            has_pressure_change=True,
            pressure_change_type=PressureChangeType.fixed_per_stage,
            mass_transfer_coefficient=MassTransferCoefficient.fixed,
            concentration_polarization_type=ConcentrationPolarizationType.calculated,
            transport_model=TransportModel.SD,
            module_type=ModuleType.spiral_wound
        )
        setattr(m.fs, f"ro_stage{i}", ro)
        
        # Set membrane properties
        stage_data = config_data['stages'][i-1]
        solute_list = list(m.fs.properties.solute_set)
        membrane_props = get_membrane_properties_mcas(
            membrane_type=m.membrane_type,
            membrane_properties=None,
            solute_list=solute_list
        )

        # Determine membrane area for this stage. If the configuration did not
        # populate an explicit area, fall back to catalog data using the
        # membrane model and vessel count so downstream flux bounds can use
        # physically consistent limits.
        stage_area_m2 = stage_data.get('membrane_area_m2')
        membrane_model_name = (
            stage_data.get('membrane_model')
            or config_data.get('membrane_model')
            or m.membrane_type
        )

        if stage_area_m2 is None:
            element_area_m2 = None
            try:
                catalog_info = get_membrane_from_catalog(membrane_model_name)
                element_area_m2 = catalog_info.get('active_area_m2')
            except Exception as _e:
                logger.debug(
                    f"Stage {i}: Could not read catalog area for {membrane_model_name}: {_e}"
                )

            if element_area_m2 is None:
                # Sensible defaults for 8" spiral-wound elements
                element_area_m2 = 34.0 if m.membrane_type == 'seawater' else 37.0

            n_vessels = stage_data.get('n_vessels') or 0
            elements_per_vessel = stage_data.get('elements_per_vessel') or 0
            estimated_area = n_vessels * elements_per_vessel * element_area_m2

            if estimated_area <= 0:
                estimated_area = 1000.0  # conservative fallback
                logger.warning(f"Stage {i}: Invalid estimated area, using fallback {estimated_area} m²")

            stage_area_m2 = estimated_area
            stage_data['membrane_area_m2'] = stage_area_m2
            logger.info(f"Stage {i}: Calculated membrane area = {stage_area_m2:.1f} m² "
                       f"({n_vessels} vessels × {elements_per_vessel} elements × {element_area_m2:.1f} m²/element)")

        # Validate membrane area is reasonable
        if stage_area_m2 <= 0:
            raise ValueError(f"Stage {i}: Invalid membrane area {stage_area_m2} m²")
        if stage_area_m2 > 100000:
            logger.warning(f"Stage {i}: Unusually large membrane area {stage_area_m2} m²")

        ro.area.fix(stage_area_m2)

        # Set A_comp for water
        ro.A_comp[0, 'H2O'].fix(membrane_props['A_w'])

        # Set B_comp for each solute
        for comp in solute_list:
            if comp in membrane_props['B_comp']:
                ro.B_comp[0, comp].fix(membrane_props['B_comp'][comp])
            else:
                # Use default values based on membrane type
                if m.membrane_type == 'brackish':
                    ro.B_comp[0, comp].fix(3.5e-8)
                else:
                    ro.B_comp[0, comp].fix(1e-8)
        
        # Set pressure drop and permeate pressure
        ro.deltaP.fix(-0.5 * pyunits.bar)
        ro.permeate.pressure[0].fix(1 * pyunits.atm)

        # Fix mass transfer coefficient if needed
        if hasattr(ro.feed_side, 'K'):
            for comp in solute_list:
                ro.feed_side.K[0, 0.0, comp].fix(2e-5)
                ro.feed_side.K[0, 1.0, comp].fix(2e-5)

        # For RO0D with calculated CP, length/channel geometry may not exist; if present, set typical values
        if hasattr(ro, 'length'):
            ro.length.fix(1.016)  # 40" element length
        if hasattr(ro.feed_side, 'channel_height'):
            ro.feed_side.channel_height.fix(7.9e-4)
        if hasattr(ro.feed_side, 'spacer_porosity'):
            ro.feed_side.spacer_porosity.fix(0.85)
    
    # =================================================================
    # Create unified arcs (matching v1 and solver expectations)
    # =================================================================
    
    # Fresh feed to mixer
    m.fs.fresh_to_mixer = Arc(
        source=m.fs.fresh_feed.outlet,
        destination=m.fs.feed_mixer.fresh
    )
    
    # Mixer to first pump
    m.fs.mixer_to_pump1 = Arc(
        source=m.fs.feed_mixer.outlet,
        destination=m.fs.pump1.inlet
    )
    
    # Stage-specific connections
    for i in range(1, n_stages + 1):
        # Pump to RO
        pump_to_ro = Arc(
            source=getattr(m.fs, f"pump{i}").outlet,
            destination=getattr(m.fs, f"ro_stage{i}").inlet
        )
        setattr(m.fs, f"pump{i}_to_ro_stage{i}", pump_to_ro)
        
        # RO permeate to stage product
        if i == 1:
            # First stage uses specific arc name expected by solver
            m.fs.ro_stage1_perm_to_prod = Arc(
                source=m.fs.ro_stage1.permeate,
                destination=m.fs.stage_product1.inlet
            )
        else:
            ro_perm_to_prod = Arc(
                source=getattr(m.fs, f"ro_stage{i}").permeate,
                destination=getattr(m.fs, f"stage_product{i}").inlet
            )
            setattr(m.fs, f"ro_stage{i}_perm_to_prod{i}", ro_perm_to_prod)
        
        # RO retentate to next pump or final split
        if i < n_stages:
            ro_to_next_pump = Arc(
                source=getattr(m.fs, f"ro_stage{i}").retentate,
                destination=getattr(m.fs, f"pump{i+1}").inlet
            )
            setattr(m.fs, f"ro_stage{i}_to_pump{i+1}", ro_to_next_pump)
        else:
            # Final stage concentrate to split (unless ERD will handle it)
            if not will_have_erd:
                m.fs.final_conc_to_split = Arc(
                    source=getattr(m.fs, f"ro_stage{i}").retentate,
                    destination=m.fs.recycle_split.inlet
                )
    
    # Split to disposal and recycle
    m.fs.split_to_disposal = Arc(
        source=m.fs.recycle_split.disposal,
        destination=m.fs.disposal_product.inlet
    )
    
    m.fs.split_to_recycle = Arc(
        source=m.fs.recycle_split.recycle,
        destination=m.fs.feed_mixer.recycle
    )
    
    # For no-recycle case, fix split fraction to tiny value
    if not has_recycle:
        # Set recycle to tiny epsilon (not zero to avoid numerical issues)
        m.fs.recycle_split.split_fraction[0, "recycle"].fix(1e-8)
    
    # =================================================================
    # Create aggregate Expressions for v2 reporting (no physical arcs)
    # =================================================================
    # Products are sinks - we can't connect outlets. Instead, use Expressions
    # to calculate aggregate flows for reporting and costing.
    
    from pyomo.environ import Expression
    
    # Total permeate flow (volumetric)
    m.fs.total_permeate_flow_vol = Expression(
        expr=sum(getattr(m.fs, f"ro_stage{i}").mixed_permeate[0].flow_vol_phase['Liq'] 
                 for i in range(1, n_stages+1))
    )
    
    # Total permeate flow (mass, by component)
    for comp in m.fs.properties.component_list:
        setattr(m.fs, f"total_permeate_{comp}_kg_s",
            Expression(
                expr=sum(getattr(m.fs, f"ro_stage{i}").mixed_permeate[0].flow_mass_phase_comp['Liq', comp]
                        for i in range(1, n_stages+1))
            )
        )
    
    # Total disposal flow (from recycle split's disposal state)
    m.fs.total_disposal_flow_vol = Expression(
        expr=m.fs.recycle_split.mixed_state[0].flow_vol_phase['Liq']
    )


def _should_include_erd(config_data, economic_params, membrane_type):
    """Determine if ERD should be included based on pressure and settings."""
    
    if not economic_params.get("auto_include_erd", True):
        return False
    
    # Check pressure threshold
    threshold = economic_params.get("erd_pressure_threshold_bar", 45)
    
    # Check if any stage operates above threshold
    for stage in config_data.get("stages", []):
        if stage.get("feed_pressure_bar", 0) >= threshold:
            return True
    
    # Also include for seawater
    if membrane_type == "seawater":
        return True
    
    return False


def _add_unit_costing(m, n_stages, config_data, economic_params, membrane_type):
    """Add costing blocks to all units."""
    
    # Pump costing
    for i in range(1, n_stages + 1):
        pump = getattr(m.fs, f"pump{i}")
        stage_data = config_data['stages'][i-1]
        
        # Determine pump type based on pressure
        feed_pressure_bar = stage_data.get('feed_pressure_bar', 30)
        pump_type = "high_pressure" if feed_pressure_bar >= 45 else "low_pressure"
        
        pump.costing = UnitModelCostingBlock(
            flowsheet_costing_block=m.fs.costing,
            costing_method=cost_pump,
            costing_method_arguments={"pump_type": pump_type}
        )
        logger.info(f"Added {pump_type} costing to pump{i}")
    
    # RO costing with membrane specifics
    for i in range(1, n_stages + 1):
        ro = getattr(m.fs, f"ro_stage{i}")
        stage_data = config_data['stages'][i-1]
        
        # Determine RO type
        feed_pressure_bar = stage_data.get('feed_pressure_bar', 30)
        ro_type = "high_pressure" if (membrane_type == "seawater" or feed_pressure_bar >= 45) else "standard"
        
        # Get membrane cost
        if ro_type == "high_pressure":
            membrane_cost = economic_params.get("membrane_cost_seawater_usd_m2", 75)
        else:
            membrane_cost = economic_params.get("membrane_cost_brackish_usd_m2", 30)
        
        ro.costing = UnitModelCostingBlock(
            flowsheet_costing_block=m.fs.costing,
            costing_method=cost_reverse_osmosis,
            costing_method_arguments={
                "ro_type": ro_type
            }
        )
        logger.info(f"Added {ro_type} RO costing to stage{i}")
    
    # Skip ZeroOrder unit costing for now - incompatible with WaterTAPCostingDetailed
    # The operational costs are still tracked via flow registration
    # if hasattr(m.fs, "cartridge_filter"):
    #     m.fs.cartridge_filter.costing = UnitModelCostingBlock(
    #         flowsheet_costing_block=m.fs.costing
    #     )
    
    # Skip ChemicalAdditionZO costing for now - incompatible with WaterTAPCostingDetailed
    # The chemical flow cost is still tracked via register_flow_type below
    # if hasattr(m.fs, "antiscalant_addition"):
    #     m.fs.antiscalant_addition.costing = UnitModelCostingBlock(
    #         flowsheet_costing_block=m.fs.costing
    #     )
    
    # ERD costing
    if hasattr(m.fs, "erd"):
        # Use WaterTAP's pressure exchanger costing
        try:
            from watertap.costing import cost_pressure_exchanger
            m.fs.erd.costing = UnitModelCostingBlock(
                flowsheet_costing_block=m.fs.costing,
                costing_method=cost_pressure_exchanger
            )
            logger.info("Added ERD costing via cost_pressure_exchanger")
        except Exception as _e:
            logger.warning(f"ERD costing attachment failed: {_e}. Using fallback manual ERD costing.")
            # Fallback: Manual ERD capital costing
            from pyomo.environ import Var
            m.fs.erd.capital_cost = Var(
                initialize=535 * economic_params.get("feed_flow_m3h", 100),  # $535/m³/hr
                units=m.fs.costing.base_currency,
                doc="ERD capital cost"
            )
            m.fs.erd.capital_cost.fix()

    # CIP system capital cost (add to aggregate capital cost directly)
    if hasattr(m.fs, "cip_system"):
        # CIP capital is already calculated in cip_system.capital_cost_total
        # We'll include it in the results extractor as additional capex
        logger.info("CIP system capital cost will be added in results extraction")

    # Cartridge filter capital cost (will be added in results extraction)
    if economic_params.get("include_cartridge_filters", False):
        # Cartridge filter capital will be estimated in results extractor
        logger.info("Cartridge filter capital cost will be added in results extraction")


def _add_chemical_costing(m, n_stages, economic_params, chemical_dosing):
    """Add chemical consumption and flow costing."""
    
    # Antiscalant flow
    if chemical_dosing.get("antiscalant_dose_mg_L", 0) > 0:
        # Calculate antiscalant mass flow
        # For Feed unit, flow_vol is in the properties block (m³/s)
        feed_state = m.fs.fresh_feed.properties[0]
        feed_flow_vol = feed_state.flow_vol  # m³/s
        
        # Convert: (m³/s) * (mg/L) * (1 kg/1e6 mg) * (1000 L/m³) = kg/s
        m.fs.antiscalant_flow_kg_s = Expression(
            expr=pyunits.convert(feed_flow_vol * (chemical_dosing["antiscalant_dose_mg_L"] * (pyunits.mg/pyunits.L)), to_units=pyunits.kg/pyunits.s),
            doc="Antiscalant mass flow rate (kg/s)"
        )
        
        # Register and cost antiscalant flow
        # Use base_currency from costing block (USD_2018 by default in WaterTAP)
        from pyomo.environ import Param
        m.fs.costing.antiscalant_cost = Param(
            initialize=economic_params.get("antiscalant_cost_usd_kg", 2.5),
            mutable=True,
            units=m.fs.costing.base_currency / pyunits.kg,
            doc="Antiscalant cost"
        )
        
        m.fs.costing.register_flow_type("antiscalant", m.fs.costing.antiscalant_cost)
        m.fs.costing.cost_flow(m.fs.antiscalant_flow_kg_s, "antiscalant")
        
        logger.info(f"Added antiscalant costing at {chemical_dosing['antiscalant_dose_mg_L']} mg/L")
    
    # CIP chemicals
    if hasattr(m.fs, "cip_system"):
        # CIP chemical flow (annualized to per second)
        m.fs.cip_chemical_flow_kg_s = Expression(
            expr=pyunits.convert(m.fs.cip_system.chemical_consumption_kg_year, to_units=pyunits.kg/pyunits.s)
        )
        
        # Register and cost CIP chemicals
        from pyomo.environ import Param
        m.fs.costing.cip_chemical_cost = Param(
            initialize=economic_params.get("cip_surfactant_cost_usd_kg", 3.0),
            mutable=True,
            units=m.fs.costing.base_currency / pyunits.kg,
            doc="CIP chemical cost"
        )
        
        m.fs.costing.register_flow_type("cip_chemical", m.fs.costing.cip_chemical_cost)
        m.fs.costing.cost_flow(m.fs.cip_chemical_flow_kg_s, "cip_chemical")
        
        logger.info(f"Added CIP chemical costing")


def _get_product_flow(m, n_stages):
    """Get total product flow for LCOW calculation."""
    
    if n_stages == 1:
        # Single stage - use permeate flow directly
        return m.fs.ro_stage1.mixed_permeate[0].flow_vol_phase['Liq']
    else:
        # Multiple stages - use existing Expression if available
        if hasattr(m.fs, 'total_permeate_flow_vol'):
            return m.fs.total_permeate_flow_vol
        else:
            # Create Expression if not already created
            from pyomo.environ import Expression
            
            def total_permeate_flow(fs):
                return sum(
                    getattr(fs, f"ro_stage{i}").mixed_permeate[0].flow_vol_phase['Liq']
                    for i in range(1, n_stages + 1)
                )
            
            m.fs.total_permeate_flow_vol = Expression(rule=total_permeate_flow)
            return m.fs.total_permeate_flow_vol
