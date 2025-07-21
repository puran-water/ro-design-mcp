#!/usr/bin/env python3
"""
Direct simulation test without notebooks to diagnose issues.
"""

import sys
from pathlib import Path
from pyomo.environ import *
from pyomo.network import Arc

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# WaterTAP imports
from watertap.core.solvers import get_solver
from watertap.unit_models.reverse_osmosis_0D import (
    ReverseOsmosis0D,
    ConcentrationPolarizationType,
    MassTransferCoefficient,
    PressureChangeType
)
from watertap.unit_models.pressure_changer import Pump
import watertap.property_models.seawater_prop_pack as props_sw
from watertap.core.membrane_channel_base import TransportModel

# IDAES imports
from idaes.core import FlowsheetBlock
from idaes.core.util.scaling import calculate_scaling_factors
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.core.util.initialization import propagate_state
from idaes.models.unit_models import Feed, Product

# Import membrane properties handler
from utils.membrane_properties_handler import get_membrane_properties
from utils.ro_initialization import initialize_multistage_ro_enhanced


def test_direct_build():
    """Test building a simple RO model directly."""
    
    print("Testing direct model build...")
    
    # Create concrete model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    
    # Property package
    m.fs.properties = props_sw.SeawaterParameterBlock()
    
    # Feed
    m.fs.feed = Feed(property_package=m.fs.properties)
    
    # Pump
    m.fs.pump = Pump(property_package=m.fs.properties)
    
    # RO unit with SD model
    m.fs.ro = ReverseOsmosis0D(
        property_package=m.fs.properties,
        has_pressure_change=True,
        concentration_polarization_type=ConcentrationPolarizationType.none,
        mass_transfer_coefficient=MassTransferCoefficient.none,
        pressure_change_type=PressureChangeType.fixed_per_stage,
        transport_model=TransportModel.SD
    )
    
    # Product
    m.fs.product = Product(property_package=m.fs.properties)
    
    # Concentrate
    m.fs.concentrate = Product(property_package=m.fs.properties)
    
    # Connect units
    m.fs.feed_to_pump = Arc(source=m.fs.feed.outlet, destination=m.fs.pump.inlet)
    m.fs.pump_to_ro = Arc(source=m.fs.pump.outlet, destination=m.fs.ro.inlet)
    m.fs.ro_to_product = Arc(source=m.fs.ro.permeate, destination=m.fs.product.inlet)
    m.fs.ro_to_conc = Arc(source=m.fs.ro.retentate, destination=m.fs.concentrate.inlet)
    
    TransformationFactory("network.expand_arcs").apply_to(m)
    
    # Set membrane properties
    membrane_type = 'eco_pro_400'
    A_w, B_s = get_membrane_properties(membrane_type)
    
    print(f"\nMembrane: {membrane_type}")
    print(f"A_w: {A_w:.2e} m/s/Pa")
    print(f"B_s: {B_s:.2e} m/s")
    
    # Check A_comp structure
    print("\nChecking A_comp structure...")
    print(f"A_comp type: {type(m.fs.ro.A_comp)}")
    print(f"A_comp index set: {m.fs.ro.A_comp.index_set()}")
    
    # Try different indexing approaches
    print("\nTrying different indexing approaches:")
    try:
        m.fs.ro.A_comp[0, 'H2O'].fix(A_w)
        print("  A_comp[0, 'H2O'] - SUCCESS")
    except Exception as e:
        print(f"  A_comp[0, 'H2O'] - FAILED: {e}")
    
    try:
        m.fs.ro.A_comp[0.0, 'H2O'].fix(A_w)
        print("  A_comp[0.0, 'H2O'] - SUCCESS")
    except Exception as e:
        print(f"  A_comp[0.0, 'H2O'] - FAILED: {e}")
    
    try:
        m.fs.ro.A_comp['H2O'].fix(A_w)
        print("  A_comp['H2O'] - SUCCESS")
    except Exception as e:
        print(f"  A_comp['H2O'] - FAILED: {e}")
    
    # Check what indices exist
    print("\nActual A_comp indices:")
    for idx in m.fs.ro.A_comp:
        print(f"  {idx}")
    
    # Same for B_comp
    print("\nChecking B_comp structure...")
    print(f"B_comp type: {type(m.fs.ro.B_comp)}")
    print(f"B_comp index set: {m.fs.ro.B_comp.index_set()}")
    
    print("\nActual B_comp indices:")
    for idx in m.fs.ro.B_comp:
        print(f"  {idx}")
    
    # Set properties using actual indices
    print("\nSetting membrane properties with correct indexing...")
    
    # Find the right index for water
    water_idx = None
    for idx in m.fs.ro.A_comp:
        if 'H2O' in str(idx):
            water_idx = idx
            break
    
    if water_idx is not None:
        m.fs.ro.A_comp[water_idx].fix(A_w)
        print(f"  Fixed A_comp[{water_idx}] = {A_w}")
    
    # Find the right index for TDS
    tds_idx = None
    for idx in m.fs.ro.B_comp:
        if 'TDS' in str(idx):
            tds_idx = idx
            break
            
    if tds_idx is not None:
        m.fs.ro.B_comp[tds_idx].fix(B_s)
        print(f"  Fixed B_comp[{tds_idx}] = {B_s}")
    
    # Set other properties
    m.fs.ro.area.fix(100)  # m²
    m.fs.ro.permeate.pressure.fix(101325)  # 1 atm
    m.fs.ro.deltaP.fix(-0.5e5)  # -0.5 bar
    
    # Feed conditions
    m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'].fix(0.995 * 150/3.6)  # kg/s
    m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'TDS'].fix(0.005 * 150/3.6)  # kg/s
    m.fs.feed.outlet.temperature.fix(298.15)  # K
    m.fs.feed.outlet.pressure.fix(101325)  # Pa
    
    # Pump
    m.fs.pump.efficiency_pump.fix(0.8)
    
    print(f"\nDegrees of freedom: {degrees_of_freedom(m)}")
    
    # Initialize
    print("\nInitializing...")
    m.fs.feed.initialize()
    propagate_state(arc=m.fs.feed_to_pump)
    
    # Set pump outlet pressure
    m.fs.pump.outlet.pressure[0].set_value(20e5)  # 20 bar
    m.fs.pump.initialize()
    
    propagate_state(arc=m.fs.pump_to_ro)
    
    try:
        m.fs.ro.initialize()
        print("RO initialization: SUCCESS")
    except Exception as e:
        print(f"RO initialization: FAILED - {e}")
        
        # Try to get more info
        print("\nDiagnosing RO state...")
        print(f"  Feed pressure: {value(m.fs.ro.inlet.pressure[0])/1e5:.1f} bar")
        print(f"  Feed flow H2O: {value(m.fs.ro.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O']):.2f} kg/s")
        print(f"  Feed flow TDS: {value(m.fs.ro.inlet.flow_mass_phase_comp[0, 'Liq', 'TDS']):.4f} kg/s")
        
        # Check if flux calculation works
        if water_idx is not None:
            A_w_val = value(m.fs.ro.A_comp[water_idx])
            p_feed = value(m.fs.ro.inlet.pressure[0])
            p_perm = value(m.fs.ro.permeate.pressure[0])
            
            # Simplified flux calculation
            flux_est = A_w_val * 1000 * (p_feed - p_perm)
            print(f"\n  Estimated flux: {flux_est:.4f} kg/m²/s")
            print(f"  WaterTAP limit: 0.03 kg/m²/s")
            
            if flux_est > 0.03:
                print("  WARNING: Flux exceeds WaterTAP limit!")
    
    return m


def test_enhanced_initialization():
    """Test the enhanced initialization with ECO PRO-400."""
    
    print("\n\n" + "="*70)
    print("Testing Enhanced Initialization")
    print("="*70)
    
    # Simple configuration for testing
    config = {
        'stage_count': 1,
        'feed_flow_m3h': 150,
        'stages': [{
            'stage_number': 1,
            'membrane_area_m2': 1000,
            'stage_recovery': 0.5
        }]
    }
    
    # Build a simple model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    
    # Property package
    m.fs.properties = props_sw.SeawaterParameterBlock()
    
    # Units
    m.fs.feed = Feed(property_package=m.fs.properties)
    m.fs.pump1 = Pump(property_package=m.fs.properties)
    m.fs.ro_stage1 = ReverseOsmosis0D(
        property_package=m.fs.properties,
        has_pressure_change=True,
        concentration_polarization_type=ConcentrationPolarizationType.none,
        mass_transfer_coefficient=MassTransferCoefficient.none,
        pressure_change_type=PressureChangeType.fixed_per_stage,
        transport_model=TransportModel.SD
    )
    m.fs.stage_product1 = Product(property_package=m.fs.properties)
    m.fs.concentrate_product = Product(property_package=m.fs.properties)
    
    # Arcs
    m.fs.feed_to_pump1 = Arc(source=m.fs.feed.outlet, destination=m.fs.pump1.inlet)
    m.fs.pump1_to_ro1 = Arc(source=m.fs.pump1.outlet, destination=m.fs.ro_stage1.inlet)
    m.fs.ro1_perm_to_prod = Arc(source=m.fs.ro_stage1.permeate, destination=m.fs.stage_product1.inlet)
    m.fs.final_conc_arc = Arc(source=m.fs.ro_stage1.retentate, destination=m.fs.concentrate_product.inlet)
    
    TransformationFactory("network.expand_arcs").apply_to(m)
    
    # Set membrane properties - need to find correct indices first
    membrane_type = 'eco_pro_400'
    A_w, B_s = get_membrane_properties(membrane_type)
    
    # Find indices
    water_idx = None
    for idx in m.fs.ro_stage1.A_comp:
        if 'H2O' in str(idx):
            water_idx = idx
            break
    
    tds_idx = None
    for idx in m.fs.ro_stage1.B_comp:
        if 'TDS' in str(idx):
            tds_idx = idx
            break
    
    if water_idx and tds_idx:
        m.fs.ro_stage1.A_comp[water_idx].fix(A_w)
        m.fs.ro_stage1.B_comp[tds_idx].fix(B_s)
        print(f"Set membrane properties: A_w={A_w:.2e}, B_s={B_s:.2e}")
    
    # Other RO properties
    m.fs.ro_stage1.area.fix(1000)
    m.fs.ro_stage1.permeate.pressure.fix(101325)
    m.fs.ro_stage1.deltaP.fix(-0.5e5)
    
    # Feed
    m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'].fix(41.0)  # kg/s
    m.fs.feed.outlet.flow_mass_phase_comp[0, 'Liq', 'TDS'].fix(0.208)  # kg/s
    m.fs.feed.outlet.temperature.fix(298.15)
    m.fs.feed.outlet.pressure.fix(101325)
    
    # Pump
    m.fs.pump1.efficiency_pump.fix(0.8)
    
    print(f"\nInitial DOF: {degrees_of_freedom(m)}")
    
    # Try enhanced initialization
    try:
        stage_conditions = initialize_multistage_ro_enhanced(
            m,
            stage_recoveries=[0.5],
            feed_tds_ppm=5000,
            A_w=A_w,
            verbose=True
        )
        
        print("\nEnhanced initialization: SUCCESS")
        print(f"Stage 1 recommended pressure: {stage_conditions[0].required_pressure_pa/1e5:.1f} bar")
        
    except Exception as e:
        print(f"\nEnhanced initialization: FAILED - {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Test 1: Direct build
    m = test_direct_build()
    
    # Test 2: Enhanced initialization
    test_enhanced_initialization()