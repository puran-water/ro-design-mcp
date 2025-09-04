#!/usr/bin/env python3
"""
Test script to verify multi-ion MCAS simulation fix.

This script tests whether the initialization order fix resolves FBBT errors
when simulating complex ion compositions without NaCl equivalent conversion.
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.optimize_ro import optimize_vessel_array_configuration
from utils.simulate_ro import run_ro_simulation

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def test_multi_ion_direct():
    """Test direct multi-ion simulation without NaCl equivalent."""
    
    logger.info("=" * 70)
    logger.info("TEST: Direct Multi-Ion MCAS Simulation (v1 with fix)")
    logger.info("=" * 70)
    
    # Step 1: Get configuration
    configs = optimize_vessel_array_configuration(
        feed_flow_m3h=50,
        target_recovery=0.75,
        feed_salinity_ppm=5000,
        membrane_type="brackish"
    )
    
    if not configs:
        logger.error("No configurations found")
        return None
    
    config = configs[0]
    logger.info(f"Using configuration: {config['array_notation']}")
    
    # Step 2: Complex ion composition (6 major ions + traces)
    ion_composition = {
        "Na_+": 1200,     # Major cation
        "Ca_2+": 150,     # Hardness - divalent
        "Mg_2+": 80,      # Hardness - divalent  
        "K_+": 50,        # Minor cation
        "Cl_-": 2100,     # Major anion
        "SO4_2-": 400,    # Sulfate - divalent
        "HCO3_-": 200,    # Alkalinity
        "Sr_2+": 8,       # Trace - scaling concern
        "Ba_2+": 0.5,     # Trace - BaSO4 scaling
        "F_-": 2          # Trace - fluoride
    }
    
    logger.info(f"Testing with {len(ion_composition)} ions (including traces)")
    logger.info(f"Total TDS: {sum(ion_composition.values()):.1f} mg/L")
    
    # Step 3: Run simulation WITHOUT NaCl equivalent
    logger.info("\n--- Testing DIRECT MCAS modeling (use_nacl_equivalent=False) ---")
    
    try:
        result = run_ro_simulation(
            configuration=config,
            feed_salinity_ppm=5000,
            feed_ion_composition=ion_composition,
            feed_temperature_c=25.0,
            membrane_type="brackish",
            use_nacl_equivalent=False  # Force direct MCAS modeling
        )
        
        if result["status"] == "success":
            logger.info("SUCCESS! Multi-ion simulation completed without NaCl conversion")
            logger.info(f"Recovery achieved: {result['performance']['system_recovery']:.1%}")
            logger.info(f"Permeate TDS: {result['performance']['permeate_tds_mg_l']:.1f} mg/L")
            logger.info(f"Specific energy: {result['performance']['specific_energy_kWh_m3']:.2f} kWh/m3")
            
            # Check ion tracking
            if "ion_tracking" in result:
                logger.info("\nIon-specific rejection:")
                for ion, data in result["ion_tracking"].items():
                    if isinstance(data, dict) and "rejection" in data:
                        logger.info(f"  {ion}: {data['rejection']:.1%}")
            
            return result
        else:
            logger.error(f"FAILED: {result.get('message', 'Unknown error')}")
            return result
            
    except Exception as e:
        logger.error(f"Exception during simulation: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def test_nacl_fallback():
    """Test that NaCl equivalent still works as fallback."""
    
    logger.info("\n" + "=" * 70)
    logger.info("TEST: NaCl Equivalent Fallback (should always work)")
    logger.info("=" * 70)
    
    # Same configuration as above
    configs = optimize_vessel_array_configuration(
        feed_flow_m3h=50,
        target_recovery=0.75,
        feed_salinity_ppm=5000,
        membrane_type="brackish"
    )
    
    config = configs[0]
    
    # Same ion composition
    ion_composition = {
        "Na_+": 1200,
        "Ca_2+": 150,
        "Mg_2+": 80,
        "K_+": 50,
        "Cl_-": 2100,
        "SO4_2-": 400,
        "HCO3_-": 200,
        "Sr_2+": 8,
        "Ba_2+": 0.5,
        "F_-": 2
    }
    
    logger.info("Testing with NaCl equivalent conversion (use_nacl_equivalent=True)")
    
    try:
        result = run_ro_simulation(
            configuration=config,
            feed_salinity_ppm=5000,
            feed_ion_composition=ion_composition,
            feed_temperature_c=25.0,
            membrane_type="brackish",
            use_nacl_equivalent=True  # Use NaCl equivalent
        )
        
        if result["status"] == "success":
            logger.info("SUCCESS! NaCl equivalent simulation completed")
            logger.info(f"Recovery achieved: {result['performance']['system_recovery']:.1%}")
            logger.info(f"Permeate TDS: {result['performance']['permeate_tds_mg_l']:.1f} mg/L")
            return result
        else:
            logger.error(f"FAILED: {result.get('message', 'Unknown error')}")
            return result
            
    except Exception as e:
        logger.error(f"Exception during simulation: {str(e)}")
        return None


def main():
    """Run all tests."""
    
    logger.info("Testing Multi-Ion MCAS Simulation Fix")
    logger.info("This verifies that moving calculate_scaling_factors() after pump")
    logger.info("initialization resolves FBBT constraint violations.\n")
    
    # Test 1: Direct multi-ion (should work with fix)
    result_direct = test_multi_ion_direct()
    
    # Test 2: NaCl fallback (should always work)
    result_nacl = test_nacl_fallback()
    
    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("TEST SUMMARY")
    logger.info("=" * 70)
    
    if result_direct and result_direct.get("status") == "success":
        logger.info("✓ Direct multi-ion MCAS: PASSED")
        logger.info("  The initialization order fix works!")
    else:
        logger.info("✗ Direct multi-ion MCAS: FAILED")
        logger.info("  Issue not fully resolved, may need additional fixes")
    
    if result_nacl and result_nacl.get("status") == "success":
        logger.info("✓ NaCl equivalent fallback: PASSED")
    else:
        logger.info("✗ NaCl equivalent fallback: FAILED")
        logger.info("  Unexpected - this should always work")
    
    # Compare results if both succeeded
    if (result_direct and result_direct.get("status") == "success" and
        result_nacl and result_nacl.get("status") == "success"):
        
        logger.info("\nComparison:")
        direct_recovery = result_direct["performance"]["system_recovery"]
        nacl_recovery = result_nacl["performance"]["system_recovery"]
        logger.info(f"  Recovery: Direct={direct_recovery:.3f}, NaCl={nacl_recovery:.3f}")
        
        direct_tds = result_direct["performance"]["permeate_tds_mg_l"]
        nacl_tds = result_nacl["performance"]["permeate_tds_mg_l"]
        logger.info(f"  Permeate TDS: Direct={direct_tds:.1f}, NaCl={nacl_tds:.1f}")
        
        if abs(direct_recovery - nacl_recovery) < 0.05:
            logger.info("  Results are similar (< 5% difference)")
        else:
            logger.info("  Results differ significantly")


if __name__ == "__main__":
    main()