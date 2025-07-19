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
from idaes.core import FlowsheetBlock
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
from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock, MaterialFlowBasis
from watertap.core.membrane_channel_base import TransportModel
from watertap.core import ModuleType

# Import membrane properties handler
from .membrane_properties_handler import get_membrane_properties_mcas

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
        setattr(m.fs, f"ro_stage{i}", ReverseOsmosis0D(
            property_package=m.fs.properties,
            has_pressure_change=True,
            concentration_polarization_type=ConcentrationPolarizationType.calculated,
            mass_transfer_coefficient=MassTransferCoefficient.calculated,
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
        
        # Channel geometry
        ro.feed_side.channel_height.fix(0.001)  # 1 mm
        ro.feed_side.spacer_porosity.fix(0.85)
        
        # Set total membrane area for the stage (all vessels in parallel)
        total_area = stage_data.get('membrane_area_m2', 
                                   stage_data.get('area_m2', 260.16))
        vessel_count = stage_data.get('vessel_count', 1)
        
        logger.info(f"Stage {i}: Total membrane area = {total_area:.1f} m² "
                   f"({vessel_count} vessels in parallel)")
            
        ro.area.fix(total_area)
        
        # For calculated mass transfer coefficient with spiral wound modules,
        # we need to fix either length, width, or inlet Reynolds number.
        # Let's try fixing inlet Reynolds number to a typical value.
        if hasattr(ro.feed_side, 'N_Re'):
            # Typical Reynolds number for spiral wound RO: 100-500
            # Higher Re for first stage (cleaner water), lower for later stages
            typical_Re = 300 - 100 * (i - 1)  # 300 for stage 1, 200 for stage 2, etc.
            ro.feed_side.N_Re[0, 0].fix(typical_Re)
            logger.info(f"Stage {i}: Fixed inlet Reynolds number = {typical_Re}")
            # Length and width will be calculated from area and Re
    
    # Set fresh feed conditions (always based on fresh feed, not effective)
    feed_state = m.fs.fresh_feed.outlet
    
    # Temperature and pressure - use proper units
    feed_state.temperature.fix((273.15 + feed_temperature_c) * pyunits.K)
    feed_state.pressure.fix(1 * pyunits.atm)  # 1 atm
    
    # Component flows based on ion composition (mass basis)
    ion_composition_mg_l = mcas_config['ion_composition_mg_l']
    total_ion_flow_kg_s = 0
    
    # Set ion flows
    for comp in mcas_config['solute_list']:
        conc_mg_l = ion_composition_mg_l[comp]
        ion_flow_kg_s = conc_mg_l * fresh_feed_flow_m3_s / 1000  # mg/L * m³/s / 1000 = kg/s
        feed_state.flow_mass_phase_comp[0, 'Liq', comp].fix(ion_flow_kg_s)
        total_ion_flow_kg_s += ion_flow_kg_s
    
    # Water flow
    water_flow_kg_s = fresh_feed_flow_m3_s * 1000 - total_ion_flow_kg_s  # ~1000 kg/m³
    feed_state.flow_mass_phase_comp[0, 'Liq', 'H2O'].fix(water_flow_kg_s)
    
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
    
    # Set scaling factors
    m.fs.properties.set_default_scaling("flow_mass_phase_comp", 1, index=("Liq", "H2O"))
    for comp in mcas_config['solute_list']:
        m.fs.properties.set_default_scaling("flow_mass_phase_comp", 1e4, index=("Liq", comp))
    calculate_scaling_factors(m)
    
    return m


