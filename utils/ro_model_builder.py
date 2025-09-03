"""
RO model building utilities for WaterTAP simulations.

This module provides functions to build WaterTAP RO models with MCAS property package
for both standard and recycle configurations.
"""

from typing import Dict, Any, Optional
import logging
import sys

# Import everything we need - avoid importing from utils to prevent circular imports
from pyomo.environ import ConcreteModel, Constraint, value, TransformationFactory, Reference, units as pyunits
from pyomo.network import Arc
from idaes.core import FlowsheetBlock, UnitModelCostingBlock
from idaes.core.util.scaling import calculate_scaling_factors
from idaes.models.unit_models import Feed, Product, Mixer, Separator
from idaes.models.unit_models.mixer import MixingType, MomentumMixingType
from watertap.unit_models.reverse_osmosis_0D import (
    ReverseOsmosis0D,
    ConcentrationPolarizationType,
    MassTransferCoefficient,
    PressureChangeType
)
from watertap.unit_models.pressure_changer import Pump
from watertap.costing import WaterTAPCosting
from watertap.costing.unit_models.pump import cost_pump
from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock, MaterialFlowBasis
from watertap.core.membrane_channel_base import TransportModel
from watertap.core import ModuleType

# Import membrane properties handler
from .membrane_properties_handler import get_membrane_properties_mcas
# Import density estimation function
from .mcas_builder import estimate_solution_density

# Get logger configured for MCP
from .logging_config import get_configured_logger
logger = get_configured_logger(__name__)


def build_ro_model_mcas(config_data, mcas_config, feed_salinity_ppm, 
                        feed_temperature_c, membrane_type, 
                        membrane_properties=None):
    """
    Build unified WaterTAP RO model with MCAS property package and recycle infrastructure.
    
    Key features:
    - Always builds recycle infrastructure for consistency
    - Uses recycle_split_ratio=0 (epsilon) for non-recycle operation
    - Uses MCASParameterBlock for ion-specific modeling
    - Implements recycle loop with Mixer and Separator
    - Uses consistent arc naming to avoid initialization issues
    - Sets up model structure before fixing membrane properties
    - Uses SKK transport model for better field data matching
    """
    # Create concrete model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    
    # Filter MCAS config to only include parameters MCASParameterBlock accepts
    mcas_params = {
        'solute_list': mcas_config['solute_list'],
        'mw_data': mcas_config['mw_data'],
        'material_flow_basis': MaterialFlowBasis.mass,  # Use mass flow for RO
    }
    
    # Add optional parameters if they exist
    optional_params = [
        'stokes_radius_data', 'diffusivity_data', 'charge', 
        'activity_coefficient_model'
    ]
    
    for param in optional_params:
        if param in mcas_config:
            mcas_params[param] = mcas_config[param]
    
    # Create MCAS property package
    m.fs.properties = MCASParameterBlock(**mcas_params)
    
    # Feed conditions
    fresh_feed_flow_m3_s = config_data['feed_flow_m3h'] / 3600  # Convert to m³/s
    
    # Create fresh feed unit
    m.fs.fresh_feed = Feed(property_package=m.fs.properties)
    
    # Always create recycle components for unified architecture
    logger.info("Building unified model with recycle infrastructure...")
    
    # Separator for final concentrate split
    m.fs.recycle_split = Separator(
        property_package=m.fs.properties,
        outlet_list=["disposal", "recycle"]
    )
    
    # Mixer for fresh feed and recycle
    m.fs.feed_mixer = Mixer(
        property_package=m.fs.properties,
        inlet_list=["fresh", "recycle"],
        energy_mixing_type=MixingType.none,  # Required for MCAS
        momentum_mixing_type=MomentumMixingType.none
    )
    
    # With MomentumMixingType.none, we need to explicitly set outlet pressure
    # Set it equal to the fresh feed pressure (which should be the lower pressure)
    m.fs.mixer_pressure_constraint = Constraint(
        expr=m.fs.feed_mixer.outlet.pressure[0] == m.fs.feed_mixer.fresh.pressure[0]
    )
    
    # Effective feed is always mixer outlet
    effective_feed = m.fs.feed_mixer.outlet
    
    # Build stages - using n_stages consistently
    n_stages = config_data.get('n_stages', config_data.get('stage_count', 1))
    
    # Create all RO stages and pumps with consistent naming
    for i in range(1, n_stages + 1):
        # Create pump for stage
        setattr(m.fs, f"pump{i}", Pump(property_package=m.fs.properties))
        
        # Create RO stage with spiral wound modules
        # Use calculated CP with fixed K for robustness
        initial_cp_type = ConcentrationPolarizationType.calculated  # Use calculated CP
        initial_mass_transfer = MassTransferCoefficient.fixed  # Fix K to avoid correlation issues
        
        setattr(m.fs, f"ro_stage{i}", ReverseOsmosis0D(
            property_package=m.fs.properties,
            has_pressure_change=True,
            concentration_polarization_type=initial_cp_type,
            mass_transfer_coefficient=initial_mass_transfer,
            pressure_change_type=PressureChangeType.fixed_per_stage,
            transport_model=TransportModel.SD,  # Use SD model (Solution-Diffusion)
            module_type=ModuleType.spiral_wound  # Always use spiral wound
        ))
        
        # Create permeate product for each stage
        setattr(m.fs, f"stage_product{i}", Product(property_package=m.fs.properties))
    
    # Create final products - always create disposal product for unified architecture
    m.fs.disposal_product = Product(property_package=m.fs.properties)
    
    # Build connectivity with consistent naming - always use mixer path
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
    
    # Connect first pump to first RO
    m.fs.pump1_to_ro_stage1 = Arc(
        source=m.fs.pump1.outlet,
        destination=m.fs.ro_stage1.inlet
    )
    
    # Connect permeate from first RO to product
    m.fs.ro_stage1_perm_to_prod = Arc(
        source=m.fs.ro_stage1.permeate,
        destination=m.fs.stage_product1.inlet
    )
    
    # Connect stages if multiple
    if n_stages > 1:
        for i in range(1, n_stages):
            # Concentrate of stage i to pump i+1
            setattr(m.fs, f"ro_stage{i}_to_pump{i+1}", Arc(
                source=getattr(m.fs, f"ro_stage{i}").retentate,
                destination=getattr(m.fs, f"pump{i+1}").inlet
            ))
            
            # Pump i+1 to RO i+1
            setattr(m.fs, f"pump{i+1}_to_ro_stage{i+1}", Arc(
                source=getattr(m.fs, f"pump{i+1}").outlet,
                destination=getattr(m.fs, f"ro_stage{i+1}").inlet
            ))
            
            # Permeate to product
            setattr(m.fs, f"ro_stage{i+1}_perm_to_prod{i+1}", Arc(
                source=getattr(m.fs, f"ro_stage{i+1}").permeate,
                destination=getattr(m.fs, f"stage_product{i+1}").inlet
            ))
    
    # Connect final concentrate - always use recycle split path
    final_stage = n_stages
    # Final concentrate to recycle split
    m.fs.final_conc_to_split = Arc(
        source=getattr(m.fs, f"ro_stage{final_stage}").retentate,
        destination=m.fs.recycle_split.inlet
    )
    
    # Recycle split outputs
    m.fs.split_to_disposal = Arc(
        source=m.fs.recycle_split.disposal,
        destination=m.fs.disposal_product.inlet
    )
    
    m.fs.split_to_recycle = Arc(
        source=m.fs.recycle_split.recycle,
        destination=m.fs.feed_mixer.recycle
    )
    
    # Apply arcs to expand the network
    TransformationFactory("network.expand_arcs").apply_to(m)
    
    # NOW set membrane properties after model structure is built
    for i in range(1, n_stages + 1):
        stage_data = config_data['stages'][i-1]
        ro = getattr(m.fs, f"ro_stage{i}")
        
        # Note: reflect_coeff is only used for SKK model, not SD model
        
        # Get membrane properties from handler (handles commercial membranes)
        membrane_props = get_membrane_properties_mcas(
            membrane_type=membrane_type,
            membrane_properties=membrane_properties,
            solute_list=mcas_config['solute_list']
        )
        
        # Set A_comp (water permeability) - indexed by time and solvent_set
        ro.A_comp[0, 'H2O'].fix(membrane_props['A_w'])
        logger.info(f"Stage {i}: A_comp[0, 'H2O'] = {membrane_props['A_w']:.2e} m/s/Pa")
        
        # Set B_comp for each ion
        for comp in mcas_config['solute_list']:
            if comp in membrane_props['B_comp']:
                ro.B_comp[0, comp].fix(membrane_props['B_comp'][comp])
                logger.info(f"Stage {i}: B_comp[{comp}] = {membrane_props['B_comp'][comp]:.2e} m/s")
            else:
                # Fallback value if not specified
                default_B = 3.5e-8 if membrane_type != "seawater" else 1.0e-8
                ro.B_comp[0, comp].fix(default_B)
                logger.warning(f"Stage {i}: B_comp[{comp}] using default = {default_B:.2e} m/s")
        
        # Set fixed pressure drop
        ro.deltaP.fix(-0.5 * pyunits.bar)  # 0.5 bar pressure drop
        
        # Fix permeate pressure
        ro.permeate.pressure[0].fix(1 * pyunits.atm)  # 1 atm
        
        
        # Set total membrane area for the stage (all vessels in parallel)
        total_area = stage_data.get('membrane_area_m2', 
                                   stage_data.get('area_m2', 260.16))
        vessel_count = stage_data.get('vessel_count', 1)
        elements_per_vessel = stage_data.get('elements_per_vessel', 7)
        
        logger.info(f"Stage {i}: Total membrane area = {total_area:.1f} m² "
                   f"({vessel_count} vessels × {elements_per_vessel} elements/vessel)")
            
        ro.area.fix(total_area)
        
        # Fix K values for all solutes at both boundary positions
        # Required when using MassTransferCoefficient.fixed
        if hasattr(ro.feed_side, 'K'):
            # Fix at both x=0.0 and x=1.0 for RO0D
            for x in [0.0, 1.0]:
                for comp in mcas_config['solute_list']:
                    # Fix K at typical value for brackish water RO
                    ro.feed_side.K[0, x, comp].fix(2e-5)  # 20 μm/s
            logger.info(f"Stage {i}: Fixed K = 2e-5 m/s for all solutes at x=0.0 and x=1.0")
        
        # Fix membrane geometry if variables exist
        # Length/width only exist when K or pressure drop is calculated
        if hasattr(ro, 'length'):
            element_length = 1.016  # Standard 40" element length in meters
            ro.length.fix(element_length)
            logger.info(f"Stage {i}: Fixed membrane length = {element_length} m (lumped model)")
        else:
            logger.info(f"Stage {i}: Length not created (using fixed K, no pressure drop calc)")
        
        # Width will be calculated from area and length by WaterTAP
        # For spiral wound: area = 2 * length * width
        
        # Fix channel geometry for spiral wound modules
        # These variables only exist when CP/K/pressure is calculated
        if hasattr(ro.feed_side, 'channel_height'):
            ro.feed_side.channel_height.fix(7.9e-4)  # 31 mil (0.79 mm) feed spacer
            logger.info(f"Stage {i}: Fixed channel height = 0.79 mm (31 mil feed spacer)")
        else:
            logger.info(f"Stage {i}: Channel height not created (not needed for current config)")
        
        if hasattr(ro.feed_side, 'spacer_porosity'):
            ro.feed_side.spacer_porosity.fix(0.85)  # Typical for spiral wound
            logger.info(f"Stage {i}: Fixed spacer porosity = 0.85")
        else:
            logger.info(f"Stage {i}: Spacer porosity not created (not needed for current config)")
        
        # CRITICAL FIX: Prevent division by zero in concentration polarization equation
        # Following WaterTAP best practices for FBBT robustness
        logger.info(f"Stage {i}: Setting flux bounds and initial values per WaterTAP standards...")
        
        # Get water permeability for initial flux estimate
        A_w = value(ro.A_comp[0, 'H2O'])  # Water permeability coefficient
        typical_dp = 20e5  # 20 bar typical driving pressure
        rho_water = 1000  # kg/m³ approximate water density
        
        # Set bounds and initial values for water flux (flux variables are on main RO unit)
        if hasattr(ro, 'flux_mass_phase_comp'):
            for x in ro.feed_side.length_domain:
                # Set bounds for water flux to prevent division by zero
                # Use less restrictive lower bound per Codex recommendation
                ro.flux_mass_phase_comp[0, x, 'Liq', 'H2O'].setlb(1e-6)  # kg/m²/s minimum (less restrictive)
                ro.flux_mass_phase_comp[0, x, 'Liq', 'H2O'].setub(3e-2)  # kg/m²/s maximum
                
                # Set reasonable initial value based on membrane permeability
                Jw_init_vol = A_w * typical_dp  # m/s volumetric flux
                Jw_init_mass = Jw_init_vol * rho_water  # kg/m²/s mass flux
                # Ensure initial value is within bounds
                Jw_init_mass = max(1e-6, min(3e-2, Jw_init_mass))
                ro.flux_mass_phase_comp[0, x, 'Liq', 'H2O'].set_value(Jw_init_mass)
                
            logger.info(f"Stage {i}: Water flux bounds = [1e-6, 3e-2] kg/m²/s, initial = {Jw_init_mass:.2e} kg/m²/s")
            
            # Set bounds and initialize solute fluxes based on SD transport model
            for comp in mcas_config['solute_list']:
                B_comp = value(ro.B_comp[0, comp])  # Solute permeability
                # Use feed concentration as initial estimate
                if comp in mcas_config['ion_composition_mg_l']:
                    C_bulk_est = mcas_config['ion_composition_mg_l'][comp] * 1e-3  # Convert mg/L to kg/m³
                else:
                    C_bulk_est = 1e-3  # Default for unmapped components
                    
                for x in ro.feed_side.length_domain:
                    # WaterTAP standard bounds for solute fluxes
                    ro.flux_mass_phase_comp[0, x, 'Liq', comp].setlb(0.0)  # Non-negative
                    ro.flux_mass_phase_comp[0, x, 'Liq', comp].setub(1e-3)  # kg/m²/s maximum (WaterTAP standard)
                    
                    # Initialize solute flux: Js = B * C_bulk
                    Js_init = B_comp * C_bulk_est  # kg/m²/s
                    Js_init = max(1e-12, min(1e-3, Js_init))  # Ensure within bounds
                    ro.flux_mass_phase_comp[0, x, 'Liq', comp].set_value(Js_init)
        else:
            logger.warning(f"Stage {i}: flux_mass_phase_comp not found on RO unit, skipping flux initialization")
        
        
        # Tighten concentration bounds based on feed composition to prevent FBBT from exploring unrealistic ranges
        logger.info(f"Stage {i}: Tightening concentration bounds for trace components...")
        
        # Access properties at different locations if they exist
        property_locations = []
        if hasattr(ro.feed_side, 'properties_in'):
            property_locations.append(('inlet', ro.feed_side.properties_in[0]))
        if hasattr(ro.feed_side, 'properties'):
            for x in ro.feed_side.length_domain:
                property_locations.append((f'x={x}', ro.feed_side.properties[0, x]))
        
        # Get solution density for mass fraction calculations
        total_tds_mg_l = sum(mcas_config['ion_composition_mg_l'].values())
        solution_density = 1000 + 0.68 * total_tds_mg_l / 1000  # Approximate density
        
        for comp in mcas_config['solute_list']:
            # Get feed concentration
            conc_feed_mg_l = mcas_config['ion_composition_mg_l'].get(comp, 1.0)
            conc_feed_kg_m3 = conc_feed_mg_l * 1e-3
            mass_frac_feed = conc_feed_kg_m3 / solution_density
            
            # Set bounds on all property locations
            for loc_name, prop_block in property_locations:
                try:
                    # Tighten concentration upper bound (10x feed for concentrate side)
                    if hasattr(prop_block, 'conc_mass_phase_comp'):
                        upper_bound = max(10 * conc_feed_kg_m3, 1e-3)
                        prop_block.conc_mass_phase_comp[0, 'Liq', comp].setub(upper_bound)
                        
                        # Set minimum concentration floor for very trace components to prevent underflow
                        if conc_feed_mg_l < 1.0:  # Very trace component
                            prop_block.conc_mass_phase_comp[0, 'Liq', comp].setlb(1e-10)
                    
                    # Tighten mass fraction upper bound
                    if hasattr(prop_block, 'mass_frac_phase_comp'):
                        upper_bound = min(10 * mass_frac_feed, 0.1)
                        prop_block.mass_frac_phase_comp[0, 'Liq', comp].setub(upper_bound)
                        
                        # Set minimum mass fraction floor for trace components
                        if conc_feed_mg_l < 1.0:
                            prop_block.mass_frac_phase_comp[0, 'Liq', comp].setlb(1e-12)
                            
                except Exception as e:
                    logger.debug(f"Stage {i}: Could not set bounds for {comp} at {loc_name}: {e}")
        
        logger.info(f"Stage {i}: Concentration bounds tightened based on feed composition")
    
    # Set fresh feed conditions (always based on fresh feed, not effective)
    feed_state = m.fs.fresh_feed.outlet
    
    # Temperature and pressure - use proper units
    feed_state.temperature.fix((273.15 + feed_temperature_c) * pyunits.K)
    feed_state.pressure.fix(1 * pyunits.atm)  # 1 atm
    
    # Component flows based on ion composition (mass basis)
    ion_composition_mg_l = mcas_config['ion_composition_mg_l']
    total_ion_flow_kg_s = 0
    
    # Calculate realistic solution density based on TDS and temperature
    total_tds_mg_l = sum(ion_composition_mg_l.values())
    solution_density_kg_m3 = estimate_solution_density(total_tds_mg_l, feed_temperature_c)
    logger.info(f"Solution density: {solution_density_kg_m3:.1f} kg/m³ (TDS: {total_tds_mg_l:.0f} mg/L)")
    
    # Set ion flows with minimum values to avoid numerical issues
    for comp in mcas_config['solute_list']:
        conc_mg_l = ion_composition_mg_l[comp]
        ion_flow_kg_s = conc_mg_l * fresh_feed_flow_m3_s / 1000  # mg/L * m³/s / 1000 = kg/s
        
        # Ensure minimum flow to avoid numerical issues with trace components
        # This is 1 ppb minimum, which is below detection limits but prevents zero
        min_flow_kg_s = 1e-9 * fresh_feed_flow_m3_s  # 1 ppb * m³/s
        ion_flow_kg_s = max(ion_flow_kg_s, min_flow_kg_s)
        
        feed_state.flow_mass_phase_comp[0, 'Liq', comp].fix(ion_flow_kg_s)
        total_ion_flow_kg_s += ion_flow_kg_s
    
    # Water flow using realistic density
    water_flow_kg_s = fresh_feed_flow_m3_s * solution_density_kg_m3 - total_ion_flow_kg_s
    
    # Sanity check for water flow
    if water_flow_kg_s <= 0:
        raise ValueError(
            f"Calculated negative water flow ({water_flow_kg_s:.2e} kg/s). "
            f"Total ion flow ({total_ion_flow_kg_s:.2e} kg/s) exceeds total mass flow "
            f"({fresh_feed_flow_m3_s * solution_density_kg_m3:.2e} kg/s)"
        )
    
    feed_state.flow_mass_phase_comp[0, 'Liq', 'H2O'].fix(water_flow_kg_s)
    
    # Fix temperature and pressure on fresh_feed
    m.fs.fresh_feed.properties[0].temperature.fix((273.15 + feed_temperature_c) * pyunits.K)
    m.fs.fresh_feed.properties[0].pressure.fix(1 * pyunits.atm)
    
    # Assert electroneutrality for multi-ion systems
    if len(ion_composition_mg_l) > 2:  # More than just Na+/Cl-
        # Use Cl- as adjustment ion if present, otherwise use the most abundant anion
        adjustment_ion = None
        if 'Cl_-' in ion_composition_mg_l:
            adjustment_ion = 'Cl_-'
        else:
            # Find the most abundant anion
            anions = [(comp, conc) for comp, conc in ion_composition_mg_l.items() 
                     if comp in mcas_config['charge'] and mcas_config['charge'][comp] < 0]
            if anions:
                adjustment_ion = max(anions, key=lambda x: x[1])[0]
        
        if adjustment_ion:
            try:
                # Assert electroneutrality on the fresh_feed state block
                m.fs.fresh_feed.properties[0].assert_electroneutrality(
                    defined_state=True,
                    adjust_by_ion=adjustment_ion,
                    tol=1e-8
                )
                logger.info(f"Asserted electroneutrality by adjusting {adjustment_ion}")
            except Exception as e:
                logger.warning(f"Could not assert electroneutrality: {str(e)}")
    
    # Set recycle split ratio - use epsilon for "no recycle" to avoid numerical issues
    recycle_info = config_data.get('recycle_info', {})
    if recycle_info.get('uses_recycle', False):
        recycle_split_ratio = recycle_info.get('recycle_split_ratio', 0.5)
    else:
        # Use small epsilon for numerical stability when no recycle
        recycle_split_ratio = 1e-8
    
    # Only fix one split fraction - the other is calculated from sum = 1 constraint
    m.fs.recycle_split.split_fraction[0, "recycle"].fix(recycle_split_ratio)
    
    # Set pump efficiencies
    for i in range(1, n_stages + 1):
        getattr(m.fs, f"pump{i}").efficiency_pump.fix(0.8)
    
    # Set scaling factors with sophisticated handling for trace ions
    # Water gets scaling factor of 1 (it's ~1 kg/s scale)
    m.fs.properties.set_default_scaling("flow_mass_phase_comp", 1, index=("Liq", "H2O"))
    
    # Set scaling for water concentration (density-based)
    m.fs.properties.set_default_scaling("conc_mass_phase_comp", 1.0/solution_density_kg_m3, index=("Liq", "H2O"))
    # Water mass fraction is close to 1
    m.fs.properties.set_default_scaling("mass_frac_phase_comp", 1.0, index=("Liq", "H2O"))
    
    for comp in mcas_config['solute_list']:
        conc_mg_l = ion_composition_mg_l.get(comp, 0)
        
        if conc_mg_l > 0:
            # Calculate expected flow rate in kg/s
            expected_flow_kg_s = conc_mg_l * fresh_feed_flow_m3_s / 1000  # mg/L * m³/s / 1000 = kg/s
            
            # Calculate expected concentration in kg/m³
            conc_kg_m3 = conc_mg_l * 1e-3  # mg/L to kg/m³
            
            # Calculate expected mass fraction
            mass_frac = conc_kg_m3 / solution_density_kg_m3
            
            # Scaling factor should be inverse of expected magnitude
            # Goal: bring scaled value to range 0.01-100
            if expected_flow_kg_s > 0:
                # Flow mass scaling
                flow_scale_factor = 1.0 / expected_flow_kg_s
                flow_scale_factor = max(1e-2, min(1e8, flow_scale_factor))
                m.fs.properties.set_default_scaling("flow_mass_phase_comp", flow_scale_factor, index=("Liq", comp))
                
                # Concentration scaling - critical for FBBT
                conc_scale_factor = 1.0 / max(conc_kg_m3, 1e-9)
                conc_scale_factor = max(1e-2, min(1e8, conc_scale_factor))
                m.fs.properties.set_default_scaling("conc_mass_phase_comp", conc_scale_factor, index=("Liq", comp))
                
                # Mass fraction scaling
                frac_scale_factor = 1.0 / max(mass_frac, 1e-12)
                frac_scale_factor = max(1e-2, min(1e8, frac_scale_factor))
                m.fs.properties.set_default_scaling("mass_frac_phase_comp", frac_scale_factor, index=("Liq", comp))
                
                logger.info(f"Scaling for {comp}: flow={flow_scale_factor:.2e}, conc={conc_scale_factor:.2e}, frac={frac_scale_factor:.2e} "
                          f"(conc: {conc_mg_l} mg/L, flow: {expected_flow_kg_s:.2e} kg/s)")
            else:
                # Default for very small concentrations
                m.fs.properties.set_default_scaling("flow_mass_phase_comp", 1e6, index=("Liq", comp))
                m.fs.properties.set_default_scaling("conc_mass_phase_comp", 1e6, index=("Liq", comp))
                m.fs.properties.set_default_scaling("mass_frac_phase_comp", 1e6, index=("Liq", comp))
        else:
            # Default for zero concentration
            m.fs.properties.set_default_scaling("flow_mass_phase_comp", 1e4, index=("Liq", comp))
            m.fs.properties.set_default_scaling("conc_mass_phase_comp", 1e4, index=("Liq", comp))
            m.fs.properties.set_default_scaling("mass_frac_phase_comp", 1e4, index=("Liq", comp))
    
    # Also set scaling for other important variables
    # Pressure scaling (expecting ~50 bar = 5e6 Pa)
    m.fs.properties.set_default_scaling("pressure", 1e-6)
    
    # Temperature scaling (expecting ~300 K)
    m.fs.properties.set_default_scaling("temperature", 1e-2)
    
    # Apply all scaling factors
    calculate_scaling_factors(m)
    
    # Add WaterTAP costing if enabled
    if config_data.get('include_costing', True):
        logger.info("Adding WaterTAP costing framework...")
        
        # Create WaterTAP costing block
        m.fs.costing = WaterTAPCosting()
        
        # Add costing to each pump
        for i in range(1, n_stages + 1):
            pump = getattr(m.fs, f"pump{i}")
            
            # Determine pump type based on stage pressure requirements
            # Get expected pressure from configuration
            stage_data = config_data['stages'][i-1]
            feed_pressure_bar = stage_data.get('feed_pressure_bar', 30)  # Default to 30 bar
            
            # Classify pump type based on pressure
            # Low pressure: < 45 bar (650 psi)
            # High pressure: >= 45 bar (650 psi)
            if feed_pressure_bar < 45:
                pump_type = "low_pressure"
                logger.info(f"Stage {i} pump classified as low_pressure ({feed_pressure_bar:.1f} bar)")
            else:
                pump_type = "high_pressure"
                logger.info(f"Stage {i} pump classified as high_pressure ({feed_pressure_bar:.1f} bar)")
            
            pump.costing = UnitModelCostingBlock(
                flowsheet_costing_block=m.fs.costing,
                costing_method=cost_pump,
                costing_method_arguments={"pump_type": pump_type}
            )
            logger.info(f"Added {pump_type} costing block to pump{i}")
        
        # Add costing to each RO stage
        for i in range(1, n_stages + 1):
            ro = getattr(m.fs, f"ro_stage{i}")
            ro.costing = UnitModelCostingBlock(
                flowsheet_costing_block=m.fs.costing
            )
            logger.info(f"Added costing block to ro_stage{i}")
        
        # Process costs to aggregate from all units
        m.fs.costing.cost_process()
        
        # For LCOW calculation, use the volumetric flow property from mixed_permeate
        if n_stages == 1:
            # Single stage - use permeate volumetric flow directly
            product_flow = m.fs.ro_stage1.mixed_permeate[0].flow_vol_phase['Liq']
        else:
            # Multiple stages - sum volumetric flows from all permeate streams
            from pyomo.environ import Expression
            def total_permeate_vol_flow(fs):
                return sum(
                    getattr(fs, f"ro_stage{i}").mixed_permeate[0].flow_vol_phase['Liq']
                    for i in range(1, n_stages + 1)
                )
            m.fs.total_permeate_flow_vol = Expression(rule=total_permeate_vol_flow)
            product_flow = m.fs.total_permeate_flow_vol
        
        # Add LCOW and specific energy consumption metrics
        m.fs.costing.add_LCOW(product_flow)
        m.fs.costing.add_specific_energy_consumption(product_flow)
        
        logger.info("WaterTAP costing framework initialized successfully")
    
    return m


