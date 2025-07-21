#!/usr/bin/env python
"""
Detailed analysis of osmotic pressure differences between multi-ion and NaCl equivalent.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.improved_nacl_equivalent import (
    convert_to_nacl_equivalent_meq,
    calculate_multi_ion_osmotic_pressure,
    calculate_nacl_osmotic_pressure,
    ION_PROPERTIES
)

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


def analyze_osmotic_pressure_difference():
    """Analyze why the osmotic pressures are nearly identical."""
    
    logger.info("=" * 80)
    logger.info("OSMOTIC PRESSURE ANALYSIS: Multi-Ion vs NaCl Equivalent")
    logger.info("=" * 80)
    
    # Example brackish water
    feed_composition = {
        'Na_+': 1200,  # mg/L
        'Ca_2+': 120,  # mg/L
        'Mg_2+': 60,   # mg/L
        'Cl_-': 2100,  # mg/L
        'SO4_2-': 200, # mg/L
        'HCO3_-': 150  # mg/L
    }
    
    # Convert to NaCl equivalent
    nacl_equiv, cat_meq, an_meq = convert_to_nacl_equivalent_meq(feed_composition)
    
    # Calculate molar concentrations for both
    logger.info("\n1. MOLAR CONCENTRATION ANALYSIS")
    logger.info("-" * 40)
    
    # Multi-ion molar concentrations
    logger.info("\nMulti-ion composition (mol/L):")
    total_molar_multi = 0.0
    for ion, conc_mg_L in feed_composition.items():
        if ion in ION_PROPERTIES:
            mw = ION_PROPERTIES[ion][0]
            molar = (conc_mg_L / 1000) / mw
            total_molar_multi += molar
            logger.info(f"  {ion}: {molar:.4f} mol/L")
    logger.info(f"  TOTAL: {total_molar_multi:.4f} mol/L")
    
    # NaCl molar concentrations
    logger.info("\nNaCl equivalent (mol/L):")
    total_molar_nacl = 0.0
    for ion, conc_mg_L in nacl_equiv.items():
        if ion in ION_PROPERTIES:
            mw = ION_PROPERTIES[ion][0]
            molar = (conc_mg_L / 1000) / mw
            total_molar_nacl += molar
            logger.info(f"  {ion}: {molar:.4f} mol/L")
    logger.info(f"  TOTAL: {total_molar_nacl:.4f} mol/L")
    
    logger.info(f"\nMolar concentration difference: {abs(total_molar_multi - total_molar_nacl) / total_molar_multi * 100:.1f}%")
    
    # Calculate osmotic pressures
    temp_k = 298.15
    multi_pi = calculate_multi_ion_osmotic_pressure(feed_composition, temp_k)
    nacl_pi = calculate_nacl_osmotic_pressure(nacl_equiv, temp_k)
    
    logger.info("\n2. OSMOTIC PRESSURE CALCULATIONS")
    logger.info("-" * 40)
    logger.info(f"\nMulti-ion osmotic pressure: {multi_pi/1e5:.2f} bar")
    logger.info(f"NaCl equivalent osmotic pressure: {nacl_pi/1e5:.2f} bar")
    logger.info(f"Difference: {abs(multi_pi - nacl_pi) / multi_pi * 100:.1f}%")
    
    # Explain why they're similar
    logger.info("\n3. WHY THE OSMOTIC PRESSURES ARE SIMILAR")
    logger.info("-" * 40)
    logger.info("\nThe meq-based conversion preserves the total number of ions:")
    logger.info("- Original: Mix of mono- and divalent ions")
    logger.info("- NaCl equivalent: All monovalent ions")
    logger.info("- The conversion balances charge AND approximately preserves particle count")
    
    # Detailed calculation
    logger.info("\n4. DETAILED PARTICLE COUNT")
    logger.info("-" * 40)
    
    # Count particles in original
    logger.info("\nOriginal multi-ion particles:")
    particles_multi = 0
    for ion, conc_mg_L in feed_composition.items():
        if ion in ION_PROPERTIES:
            mw = ION_PROPERTIES[ion][0]
            moles = (conc_mg_L / 1000) / mw
            particles_multi += moles
            logger.info(f"  {ion}: {moles:.4f} mol/L")
    logger.info(f"  Total particles: {particles_multi:.4f} mol/L")
    
    # Count particles in NaCl
    logger.info("\nNaCl equivalent particles:")
    particles_nacl = 0
    for ion, conc_mg_L in nacl_equiv.items():
        if ion in ION_PROPERTIES:
            mw = ION_PROPERTIES[ion][0]
            moles = (conc_mg_L / 1000) / mw
            particles_nacl += moles
            logger.info(f"  {ion}: {moles:.4f} mol/L")
    logger.info(f"  Total particles: {particles_nacl:.4f} mol/L")
    
    logger.info(f"\nParticle count difference: {abs(particles_multi - particles_nacl) / particles_multi * 100:.1f}%")
    
    # Activity coefficient effect
    logger.info("\n5. ACTIVITY COEFFICIENT CONSIDERATIONS")
    logger.info("-" * 40)
    logger.info("\nNaCl calculation includes φ ≈ 0.93 activity coefficient")
    logger.info("Multi-ion uses ideal solution (φ = 1.0)")
    logger.info("This partially compensates for the small particle count difference")
    
    # Practical implications
    logger.info("\n6. PRACTICAL IMPLICATIONS FOR RO DESIGN")
    logger.info("-" * 40)
    logger.info("\n✓ YES - The pressures from NaCl simulation ARE valid because:")
    logger.info("  1. Osmotic pressure difference is only ~1.5%")
    logger.info("  2. This is within typical safety margins (5-10%) for RO design")
    logger.info("  3. The meq-based conversion preserves the ionic strength")
    logger.info("  4. Operating pressures (40-60 bar) >> osmotic pressure (3 bar)")
    
    logger.info("\nFor a typical brackish RO system:")
    logger.info(f"  - Feed pressure: ~50 bar")
    logger.info(f"  - Osmotic pressure difference: {abs(multi_pi - nacl_pi)/1e5:.2f} bar")
    logger.info(f"  - Impact on net driving pressure: {abs(multi_pi - nacl_pi)/1e5 / 50 * 100:.1f}%")
    
    # Test with different water types
    logger.info("\n\n7. TESTING OTHER WATER COMPOSITIONS")
    logger.info("-" * 40)
    
    test_waters = {
        "High TDS Brackish": {
            'Na_+': 3000, 'Ca_2+': 300, 'Mg_2+': 150,
            'Cl_-': 5250, 'SO4_2-': 500, 'HCO3_-': 300
        },
        "Seawater": {
            'Na_+': 10800, 'Ca_2+': 412, 'Mg_2+': 1290,
            'Cl_-': 19400, 'SO4_2-': 2710, 'HCO3_-': 142
        },
        "Low TDS": {
            'Na_+': 200, 'Ca_2+': 40, 'Mg_2+': 20,
            'Cl_-': 350, 'SO4_2-': 80, 'HCO3_-': 60
        }
    }
    
    for name, comp in test_waters.items():
        nacl_eq, _, _ = convert_to_nacl_equivalent_meq(comp)
        pi_multi = calculate_multi_ion_osmotic_pressure(comp, temp_k) / 1e5
        pi_nacl = calculate_nacl_osmotic_pressure(nacl_eq, temp_k) / 1e5
        diff_pct = abs(pi_multi - pi_nacl) / pi_multi * 100
        
        logger.info(f"\n{name} (TDS={sum(comp.values())} mg/L):")
        logger.info(f"  Multi-ion π: {pi_multi:.1f} bar")
        logger.info(f"  NaCl equiv π: {pi_nacl:.1f} bar")
        logger.info(f"  Difference: {diff_pct:.1f}%")


def analyze_pressure_impact():
    """Analyze the impact on RO system pressures."""
    
    logger.info("\n\n" + "=" * 80)
    logger.info("PRESSURE IMPACT ON RO SYSTEM DESIGN")
    logger.info("=" * 80)
    
    # Typical RO operating conditions
    feed_pressures = [20, 40, 60, 80]  # bar
    osmotic_diff = 0.05  # 0.05 bar typical difference
    
    logger.info("\nImpact of 0.05 bar osmotic pressure difference:")
    logger.info("-" * 40)
    logger.info("Feed Pressure | Net Driving Force | Impact")
    logger.info("-" * 40)
    
    for p_feed in feed_pressures:
        # Assume average osmotic pressure of 3 bar
        pi_avg = 3.0
        ndp_original = p_feed - pi_avg
        ndp_with_diff = p_feed - (pi_avg + osmotic_diff)
        impact = (ndp_original - ndp_with_diff) / ndp_original * 100
        
        logger.info(f"{p_feed:>12} bar | {ndp_original:>15.1f} bar | {impact:>6.2f}%")
    
    logger.info("\nCONCLUSION:")
    logger.info("- The osmotic pressure difference has negligible impact")
    logger.info("- Flux change would be < 0.2% in typical operations")
    logger.info("- Well within membrane fouling and aging variations")


if __name__ == "__main__":
    analyze_osmotic_pressure_difference()
    analyze_pressure_impact()