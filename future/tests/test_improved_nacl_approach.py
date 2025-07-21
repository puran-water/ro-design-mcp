#!/usr/bin/env python
"""
Test the improved NaCl equivalent approach with milliequivalent conversion.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.simulate_ro import run_ro_simulation
from utils.improved_nacl_equivalent import (
    convert_to_nacl_equivalent_meq,
    calculate_multi_ion_osmotic_pressure,
    calculate_nacl_osmotic_pressure
)

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def test_improved_approach():
    """Test the improved NaCl equivalent approach with brackish water example."""
    
    logger.info("=" * 80)
    logger.info("TESTING IMPROVED NaCl EQUIVALENT APPROACH")
    logger.info("=" * 80)
    
    # Example brackish water composition from document
    feed_composition = {
        'Na_+': 1200,  # mg/L
        'Ca_2+': 120,  # mg/L
        'Mg_2+': 60,   # mg/L
        'Cl_-': 2100,  # mg/L
        'SO4_2-': 200, # mg/L
        'HCO3_-': 150  # mg/L
    }
    
    total_tds = sum(feed_composition.values())
    logger.info(f"\nFeed water composition (TDS = {total_tds} mg/L):")
    for ion, conc in feed_composition.items():
        logger.info(f"  {ion}: {conc} mg/L")
    
    # Test milliequivalent conversion
    logger.info("\n" + "-" * 40)
    logger.info("STEP 1: Milliequivalent Conversion")
    logger.info("-" * 40)
    
    nacl_equiv, cation_meq, anion_meq = convert_to_nacl_equivalent_meq(feed_composition)
    
    logger.info(f"\nCharge balance check:")
    logger.info(f"  Cation meq/L: {cation_meq:.1f}")
    logger.info(f"  Anion meq/L: {anion_meq:.1f}")
    logger.info(f"  Imbalance: {abs(cation_meq - anion_meq) / (cation_meq + anion_meq) * 100:.1f}%")
    
    logger.info(f"\nNaCl equivalent composition:")
    logger.info(f"  Na+: {nacl_equiv['Na_+']:.0f} mg/L")
    logger.info(f"  Cl-: {nacl_equiv['Cl_-']:.0f} mg/L")
    logger.info(f"  Total: {sum(nacl_equiv.values()):.0f} mg/L")
    
    # Test osmotic pressure calculations
    logger.info("\n" + "-" * 40)
    logger.info("STEP 2: Osmotic Pressure Comparison")
    logger.info("-" * 40)
    
    temp_k = 298.15  # 25°C
    multi_ion_pi = calculate_multi_ion_osmotic_pressure(feed_composition, temp_k)
    nacl_pi = calculate_nacl_osmotic_pressure(nacl_equiv, temp_k)
    
    logger.info(f"\nOsmotic pressures:")
    logger.info(f"  Multi-ion: {multi_ion_pi/1e5:.2f} bar")
    logger.info(f"  NaCl equivalent: {nacl_pi/1e5:.2f} bar")
    logger.info(f"  Difference: {(multi_ion_pi - nacl_pi) / nacl_pi * 100:.1f}%")
    
    # Run RO simulation
    logger.info("\n" + "-" * 40)
    logger.info("STEP 3: RO Simulation")
    logger.info("-" * 40)
    
    config = {
        "array_notation": "2:1",
        "stages": [
            {"vessels_in_parallel": 2, "vessels_in_series": 3},
            {"vessels_in_parallel": 1, "vessels_in_series": 3}
        ],
        "feed_flow_m3h": 100.0,
        "achieved_recovery": 0.75,
        "total_vessels": 9,
        "has_recycle": False
    }
    
    logger.info(f"\nRunning simulation with improved NaCl equivalent approach...")
    logger.info(f"  Configuration: {config['array_notation']}")
    logger.info(f"  Feed flow: {config['feed_flow_m3h']} m³/h")
    logger.info(f"  Target recovery: {config['achieved_recovery']*100}%")
    
    try:
        result = run_ro_simulation(
            configuration=config,
            feed_salinity_ppm=total_tds,
            feed_ion_composition=feed_composition,
            feed_temperature_c=25.0,
            membrane_type="brackish",
            optimize_pumps=True,
            use_nacl_equivalent=True  # Use improved approach
        )
        
        if result['status'] == 'success':
            logger.info("\n✓ Simulation completed successfully!")
            
            # Display performance results
            perf = result['performance']
            logger.info(f"\nSystem Performance:")
            logger.info(f"  Recovery: {perf['system_recovery']:.1%}")
            logger.info(f"  NaCl rejection: {perf['salt_rejection']:.1%}")
            logger.info(f"  Specific energy: {perf['specific_energy_kWh_m3']:.2f} kWh/m³")
            
            # Check if multi-ion results are available
            if 'multi_ion_info' in result:
                logger.info("\n" + "-" * 40)
                logger.info("STEP 4: Multi-Ion Post-Processing Results")
                logger.info("-" * 40)
                
                multi_ion = result['multi_ion_info']
                logger.info(f"\nIon-specific rejections:")
                for ion, rejection in multi_ion['ion_rejections'].items():
                    logger.info(f"  {ion}: {rejection:.1%}")
                
                logger.info(f"\nPermeate composition:")
                for ion, conc in multi_ion['permeate_composition'].items():
                    logger.info(f"  {ion}: {conc:.1f} mg/L")
                
                logger.info(f"\nPermeate TDS comparison:")
                nacl_tds = perf.get('total_permeate_tds_mg_l', 0)
                multi_ion_tds = sum(multi_ion['permeate_composition'].values())
                logger.info(f"  NaCl-based: {nacl_tds:.0f} mg/L")
                logger.info(f"  Multi-ion: {multi_ion_tds:.0f} mg/L")
                logger.info(f"  Difference: {abs(multi_ion_tds - nacl_tds) / nacl_tds * 100:.1f}%")
                
            else:
                logger.warning("\nMulti-ion post-processing results not found in output")
                
        else:
            logger.error(f"\n✗ Simulation failed: {result['message']}")
            
    except Exception as e:
        logger.error(f"\n✗ Exception during simulation: {str(e)}")
        import traceback
        traceback.print_exc()
    
    # Compare with simple mass fraction approach
    logger.info("\n" + "=" * 80)
    logger.info("COMPARISON WITH SIMPLE MASS FRACTION APPROACH")
    logger.info("=" * 80)
    
    # Simple approach (current)
    simple_nacl = {
        'Na_+': total_tds * 0.393,
        'Cl_-': total_tds * 0.607
    }
    
    logger.info(f"\nSimple mass fraction approach:")
    logger.info(f"  Na+: {simple_nacl['Na_+']:.0f} mg/L")
    logger.info(f"  Cl-: {simple_nacl['Cl_-']:.0f} mg/L")
    
    logger.info(f"\nImproved milliequivalent approach:")
    logger.info(f"  Na+: {nacl_equiv['Na_+']:.0f} mg/L")
    logger.info(f"  Cl-: {nacl_equiv['Cl_-']:.0f} mg/L")
    
    logger.info(f"\nDifferences:")
    logger.info(f"  Na+ difference: {(nacl_equiv['Na_+'] - simple_nacl['Na_+']) / simple_nacl['Na_+'] * 100:.1f}%")
    logger.info(f"  Cl- difference: {(nacl_equiv['Cl_-'] - simple_nacl['Cl_-']) / simple_nacl['Cl_-'] * 100:.1f}%")


def test_edge_cases():
    """Test edge cases for the improved approach."""
    
    logger.info("\n" + "=" * 80)
    logger.info("TESTING EDGE CASES")
    logger.info("=" * 80)
    
    # Test 1: Highly imbalanced composition
    logger.info("\nTest 1: Highly cation-rich water")
    imbalanced = {
        'Na_+': 2000,
        'Ca_2+': 500,
        'Cl_-': 1000  # Much less than needed for balance
    }
    
    nacl_equiv, cat_meq, an_meq = convert_to_nacl_equivalent_meq(imbalanced)
    logger.info(f"  Original imbalance: {(cat_meq - an_meq) / (cat_meq + an_meq) * 100:.1f}%")
    logger.info(f"  Balanced NaCl: Na+ = {nacl_equiv['Na_+']:.0f}, Cl- = {nacl_equiv['Cl_-']:.0f} mg/L")
    
    # Test 2: Very dilute water
    logger.info("\nTest 2: Very dilute water")
    dilute = {
        'Na_+': 10,
        'Cl_-': 15
    }
    
    nacl_equiv, cat_meq, an_meq = convert_to_nacl_equivalent_meq(dilute)
    logger.info(f"  Total TDS: {sum(dilute.values())} mg/L")
    logger.info(f"  Balanced NaCl: {sum(nacl_equiv.values()):.1f} mg/L")


if __name__ == "__main__":
    # Run main test
    test_improved_approach()
    
    # Run edge case tests
    test_edge_cases()
    
    logger.info("\n" + "=" * 80)
    logger.info("TEST COMPLETED")
    logger.info("=" * 80)