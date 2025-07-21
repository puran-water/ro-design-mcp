#!/usr/bin/env python3
"""
Simple test for enhanced initialization with ECO PRO-400 membrane.
"""

import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from pyomo.environ import ConcreteModel, value
from idaes.core import FlowsheetBlock
from idaes.core.util.model_statistics import degrees_of_freedom
from watertap.property_models.seawater_prop_pack import SeawaterParameterBlock
from watertap.unit_models.reverse_osmosis_base import TransportModel

from utils.test_model_builder import build_multistage_ro_flowsheet
from utils.ro_initialization import initialize_multistage_ro_enhanced
from utils.membrane_properties_handler import get_membrane_properties


def main():
    """Test ECO PRO-400 membrane with enhanced initialization."""
    
    print("\n" + "="*60)
    print("TESTING ENHANCED INITIALIZATION")
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
    print(f"Stages: {len(recoveries)}")
    
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
    
    # Set mass fractions
    mass_frac_H2O = 1 - feed_tds/1e6
    mass_frac_TDS = feed_tds/1e6
    
    feed.properties[0].flow_mass_phase_comp['Liq', 'H2O'].fix(feed_flow * mass_frac_H2O)
    feed.properties[0].flow_mass_phase_comp['Liq', 'TDS'].fix(feed_flow * mass_frac_TDS)
    
    print(f"\nDegrees of freedom: {degrees_of_freedom(m)}")
    
    try:
        # Initialize with enhanced method
        print("\nRunning enhanced initialization...")
        stage_conditions = initialize_multistage_ro_enhanced(
            m,
            stage_recoveries=recoveries,
            feed_tds_ppm=feed_tds,
            A_w=A_w,
            verbose=True
        )
        
        print("\nSUCCESS: Enhanced initialization completed!")
        
        # Check results
        print("\nVerifying results:")
        for i in range(3):
            stage_num = i + 1
            ro = getattr(m.fs, f'ro{stage_num}')
            
            # Get actual values
            feed_pressure = value(ro.feed.pressure[0])
            try:
                actual_flux = value(ro.flux_mass_phase_comp[0, 0, 'Liq', 'H2O'])
            except:
                # SD model may have different flux structure
                actual_flux = value(ro.flux_mass_phase_comp_avg[0, 'Liq', 'H2O'])
            
            recovery = value(ro.recovery_frac_mass_H2O[0])
            
            print(f"\nStage {stage_num}:")
            print(f"  Feed pressure: {feed_pressure/1e5:.1f} bar")
            print(f"  Flux: {actual_flux:.4f} kg/m²/s")
            print(f"  Recovery: {recovery:.1%}")
            print(f"  Flux within bounds: {'YES' if actual_flux < 0.03 else 'NO'}")
        
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