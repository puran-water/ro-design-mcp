#!/usr/bin/env python3
"""
Test direct initialization bypassing TDS recalculation issues.
"""

import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(level=logging.INFO)

from pyomo.environ import ConcreteModel, value
from idaes.core import FlowsheetBlock
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.core.util.initialization import propagate_state
from watertap.property_models.seawater_prop_pack import SeawaterParameterBlock
from watertap.unit_models.reverse_osmosis_base import TransportModel

from utils.test_model_builder import build_multistage_ro_flowsheet
from utils.ro_initialization import initialize_pump_with_pressure
from utils.membrane_properties_handler import get_membrane_properties
from utils.stage_pressure_calculation import calculate_multistage_pressures


def main():
    """Test direct initialization with calculated pressures."""
    
    print("\n" + "="*60)
    print("TESTING DIRECT INITIALIZATION")
    print("="*60)
    
    # Configuration
    membrane_name = 'eco_pro_400'
    feed_tds = 1000  # ppm
    feed_flow = 5    # kg/s
    recoveries = [0.5, 0.5, 0.5]
    
    # Get membrane properties
    A_w, B_s = get_membrane_properties(membrane_name)
    membrane_props = {
        'A_comp': A_w,
        'B_comp': B_s,
        'name': 'ECO PRO-400'
    }
    
    print(f"\nMembrane: ECO PRO-400")
    print(f"A_w: {A_w:.2e} m/s/Pa")
    print(f"B_s: {B_s:.2e} m/s")
    print(f"Feed TDS: {feed_tds} ppm")
    
    # Calculate stage pressures
    print("\nCalculating stage pressures...")
    stage_conditions = calculate_multistage_pressures(
        feed_tds_ppm=feed_tds,
        stage_recoveries=recoveries,
        A_w=A_w,
        B_s=B_s,
        verbose=False
    )
    
    # Print recommended pressures
    print("\nRecommended pressures:")
    for cond in stage_conditions:
        print(f"  Stage {cond.stage_number}: {cond.recommended_pressure_bar:.1f} bar "
              f"(flux: {cond.expected_flux_kg_m2_s:.4f} kg/m²/s)")
    
    # Create model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    
    # Build flowsheet
    build_multistage_ro_flowsheet(
        m,
        prop_package=SeawaterParameterBlock,
        number_of_stages=3,
        has_recycle=False,
        membrane_props=membrane_props,
        transport_model=TransportModel.SD
    )
    
    # Set feed conditions
    feed = m.fs.feed
    feed.properties[0].temperature.fix(298.15)
    feed.properties[0].pressure.fix(101325)
    
    # Set mass fractions correctly
    mass_frac_H2O = 1 - feed_tds/1e6
    mass_frac_TDS = feed_tds/1e6
    
    feed.properties[0].flow_mass_phase_comp['Liq', 'H2O'].fix(feed_flow * mass_frac_H2O)
    feed.properties[0].flow_mass_phase_comp['Liq', 'TDS'].fix(feed_flow * mass_frac_TDS)
    
    print(f"\nFeed flows set:")
    print(f"  H2O: {feed_flow * mass_frac_H2O:.3f} kg/s")
    print(f"  TDS: {feed_flow * mass_frac_TDS:.6f} kg/s")
    print(f"  Total: {feed_flow:.3f} kg/s")
    
    print(f"\nDegrees of freedom: {degrees_of_freedom(m)}")
    
    try:
        # Initialize feed
        print("\nInitializing feed...")
        m.fs.feed.initialize()
        
        # Check feed TDS
        h2o_flow = value(feed.properties[0].flow_mass_phase_comp['Liq', 'H2O'])
        tds_flow = value(feed.properties[0].flow_mass_phase_comp['Liq', 'TDS'])
        actual_tds_ppm = (tds_flow / (h2o_flow + tds_flow)) * 1e6
        print(f"Actual feed TDS: {actual_tds_ppm:.0f} ppm")
        
        # Initialize stages with calculated pressures
        for i, cond in enumerate(stage_conditions):
            stage_num = i + 1
            print(f"\nInitializing Stage {stage_num}...")
            
            pump = getattr(m.fs, f'pump{stage_num}')
            ro = getattr(m.fs, f'ro{stage_num}')
            product = getattr(m.fs, f'permeate_product{stage_num}')
            
            # Propagate to pump
            if stage_num == 1:
                propagate_state(arc=m.fs.feed_to_pump1)
            else:
                arc_name = f'stage{stage_num-1}_to_pump{stage_num}'
                propagate_state(arc=getattr(m.fs, arc_name))
            
            # Initialize pump with calculated pressure
            print(f"  Setting pump pressure: {cond.recommended_pressure_bar:.1f} bar")
            initialize_pump_with_pressure(pump, cond.recommended_pressure_pa)
            
            # Propagate to RO
            arc_name = f'pump{stage_num}_to_ro{stage_num}'
            propagate_state(arc=getattr(m.fs, arc_name))
            
            # Fix recovery for this stage
            target_recovery = recoveries[i]
            ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'].fix(target_recovery)
            print(f"  Fixed recovery: {target_recovery:.1%}")
            
            # Initialize RO with appropriate options
            print(f"  Initializing RO unit...")
            ro.initialize(
                optarg={
                    'tol': 1e-6,
                    'max_iter': 200,
                    'linear_solver': 'ma57'
                }
            )
            
            # Check flux
            try:
                actual_flux = value(ro.flux_mass_phase_comp[0, 0, 'Liq', 'H2O'])
            except:
                actual_flux = value(ro.flux_mass_phase_comp_avg[0, 'Liq', 'H2O'])
            
            print(f"  Actual flux: {actual_flux:.4f} kg/m²/s")
            
            # Propagate to product
            arc_name = f'ro{stage_num}_perm_to_prod{stage_num}'
            if hasattr(m.fs, arc_name):
                propagate_state(arc=getattr(m.fs, arc_name))
            else:
                propagate_state(arc=m.fs.ro1_perm_to_prod)
            
            product.initialize()
        
        # Initialize concentrate product
        propagate_state(arc=m.fs.final_conc_arc)
        m.fs.concentrate_product.initialize()
        
        print("\nSUCCESS: All stages initialized!")
        
        # Report final results
        print("\nFinal Results:")
        for i in range(3):
            stage_num = i + 1
            ro = getattr(m.fs, f'ro{stage_num}')
            
            feed_pressure = value(ro.feed.pressure[0])
            try:
                actual_flux = value(ro.flux_mass_phase_comp[0, 0, 'Liq', 'H2O'])
            except:
                actual_flux = value(ro.flux_mass_phase_comp_avg[0, 'Liq', 'H2O'])
            recovery = value(ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'])
            
            print(f"\nStage {stage_num}:")
            print(f"  Feed pressure: {feed_pressure/1e5:.1f} bar")
            print(f"  Flux: {actual_flux:.4f} kg/m²/s")
            print(f"  Recovery: {recovery:.1%}")
            print(f"  Within flux bounds: {'YES' if actual_flux < 0.025 else 'NO'}")
        
        return True
        
    except Exception as e:
        print(f"\nFAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    print(f"\n{'='*60}")
    print(f"Test result: {'PASSED' if success else 'FAILED'}")
    print(f"{'='*60}")