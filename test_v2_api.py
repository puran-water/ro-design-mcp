#!/usr/bin/env python3
"""
Test script for v2 API with enhanced economic modeling.

This script tests the new simulate_ro_system_v2 endpoint with:
- WaterTAPCostingDetailed
- Chemical consumption tracking
- Ancillary equipment (cartridge filters, CIP)
- Comprehensive economic breakdown
"""

import asyncio
import json
import logging
from pathlib import Path

# Add parent directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent))

# Import the actual functions, not the decorated MCP tools
from utils.optimize_ro import optimize_vessel_array_configuration as optimize_ro_configuration
from utils.simulate_ro_v2 import run_ro_simulation_v2
from utils.economic_defaults import get_default_economic_params, get_default_chemical_dosing

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_v2_with_defaults():
    """Test v2 API using default economic parameters."""
    logger.info("=" * 60)
    logger.info("TEST 1: V2 API with default parameters")
    logger.info("=" * 60)
    
    # First optimize configuration
    configs = optimize_ro_configuration(
        feed_flow_m3h=100,
        target_recovery=0.75,
        feed_salinity_ppm=4000,
        membrane_type="brackish"
    )
    
    if not configs or len(configs) == 0:
        logger.error("No viable configurations found")
        return
    
    # Pick first configuration
    ro_config = configs[0]
    logger.info(f"Testing configuration: {ro_config['array_notation']}")
    
    # Test with ion composition
    ion_composition = {
        "Na_+": 1200,
        "Ca_2+": 120,
        "Mg_2+": 60,
        "Cl_-": 2100,
        "SO4_2-": 200,
        "HCO3_-": 150
    }
    
    # Get default parameters
    economic_params = get_default_economic_params("brackish")
    chemical_dosing = get_default_chemical_dosing()
    
    # Run v2 simulation with defaults
    result = run_ro_simulation_v2(
        configuration=ro_config,
        feed_salinity_ppm=4000,
        feed_ion_composition=ion_composition,
        feed_temperature_c=25.0,
        membrane_type="brackish",
        economic_params=economic_params,
        chemical_dosing=chemical_dosing
    )
    
    if result["status"] == "success":
        logger.info("V2 simulation successful!")
        logger.info(f"LCOW: ${result['economics']['lcow_usd_m3']:.3f}/m3")
        logger.info(f"Capital cost: ${result['economics']['total_capital_cost_usd']:,.0f}")
        logger.info(f"Operating cost: ${result['economics']['annual_operating_cost_usd_year']:,.0f}/year")
        
        if "capital_breakdown" in result["economics"]:
            logger.info("\nCapital cost breakdown:")
            for key, value in result["economics"]["capital_breakdown"].items():
                logger.info(f"  {key}: ${value:,.0f}")
        
        if "operating_breakdown" in result["economics"]:
            logger.info("\nOperating cost breakdown:")
            for key, value in result["economics"]["operating_breakdown"].items():
                logger.info(f"  {key}: ${value:,.0f}/year")
    else:
        logger.error(f"V2 simulation failed: {result.get('message', 'Unknown error')}")
    
    return result


def test_v2_with_custom_economics():
    """Test v2 API with custom economic parameters."""
    logger.info("=" * 60)
    logger.info("TEST 2: V2 API with custom economic parameters")
    logger.info("=" * 60)
    
    # Get defaults as starting point
    economic_params = get_default_economic_params("seawater")
    chemical_dosing = get_default_chemical_dosing()
    
    # Customize some parameters
    economic_params["electricity_cost_usd_kwh"] = 0.10  # Higher electricity cost
    economic_params["wacc"] = 0.12  # Higher discount rate
    economic_params["include_cartridge_filters"] = True
    economic_params["include_cip_system"] = True
    economic_params["auto_include_erd"] = True
    
    chemical_dosing["antiscalant_dose_mg_L"] = 5.0
    chemical_dosing["cip_frequency_per_year"] = 4
    
    # Optimize for seawater (use higher recovery that's achievable)
    configs = optimize_ro_configuration(
        feed_flow_m3h=50,
        target_recovery=0.50,  # 50% is more typical for seawater
        feed_salinity_ppm=35000,
        membrane_type="seawater"
    )
    
    if not configs or len(configs) == 0:
        logger.error("No viable seawater configurations found")
        return
    
    ro_config = configs[0]
    logger.info(f"Testing seawater configuration: {ro_config['array_notation']}")
    
    # Seawater ion composition
    ion_composition = {
        "Na_+": 10800,
        "Mg_2+": 1290,
        "Ca_2+": 410,
        "K_+": 390,
        "Cl_-": 19400,
        "SO4_2-": 2710,
        "HCO3_-": 142
    }
    
    # Run v2 simulation with custom parameters
    result = run_ro_simulation_v2(
        configuration=ro_config,
        feed_salinity_ppm=35000,
        feed_ion_composition=ion_composition,
        feed_temperature_c=20.0,
        membrane_type="seawater",
        economic_params=economic_params,
        chemical_dosing=chemical_dosing
    )
    
    if result["status"] == "success":
        logger.info("V2 seawater simulation successful!")
        logger.info(f"LCOW: ${result['economics']['lcow_usd_m3']:.3f}/m3")
        logger.info(f"Specific energy: {result['performance']['specific_energy_kWh_m3']:.2f} kWh/m3")
        
        if "chemical_consumption" in result:
            logger.info("\nChemical consumption:")
            for chemical, amount in result["chemical_consumption"].items():
                # The consumption dict has flat keys like "antiscalant_kg_year"
                logger.info(f"  {chemical}: {amount:.0f} kg/year")
    else:
        logger.error(f"V2 seawater simulation failed: {result.get('message', 'Unknown error')}")
    
    return result


def test_v2_optimization_mode():
    """Test v2 API in optimization mode (returns model handle)."""
    logger.info("=" * 60)
    logger.info("TEST 3: V2 API in optimization mode")
    logger.info("=" * 60)
    
    # Get configuration
    configs = optimize_ro_configuration(
        feed_flow_m3h=200,
        target_recovery=0.80,
        feed_salinity_ppm=5500,
        membrane_type="brackish"
    )
    
    if not configs or len(configs) == 0:
        logger.error("No viable configurations found for optimization")
        return
    
    ro_config = configs[0]
    
    # Ion composition
    ion_composition = {
        "Na_+": 2000,
        "Cl_-": 3000,
        "SO4_2-": 500
    }
    
    # Get defaults
    economic_params = get_default_economic_params("brackish")
    chemical_dosing = get_default_chemical_dosing()
    
    # Run in optimization mode
    result = run_ro_simulation_v2(
        configuration=ro_config,
        feed_salinity_ppm=5500,
        feed_ion_composition=ion_composition,
        feed_temperature_c=25.0,
        membrane_type="brackish",
        economic_params=economic_params,
        chemical_dosing=chemical_dosing,
        optimization_mode=True  # Enable optimization mode
    )
    
    if result["status"] == "success":
        logger.info("V2 optimization mode successful!")
        logger.info(f"Model handle: {result['model_handle']}")
        logger.info(f"API version: {result['api_version']}")
        
        if "metadata" in result:
            logger.info("\nModel metadata:")
            logger.info(f"  Inputs: {list(result['metadata'].get('inputs', {}).keys())}")
            logger.info(f"  Decision vars: {list(result['metadata'].get('decision_vars', {}).keys())}")
            logger.info(f"  Outputs: {list(result['metadata'].get('outputs', {}).keys())}")
            logger.info(f"  Ports: {list(result['metadata'].get('ports', {}).keys())}")
    else:
        logger.error(f"V2 optimization mode failed: {result.get('message', 'Unknown error')}")
    
    return result


def main():
    """Run all tests."""
    try:
        # Test 1: Defaults
        result1 = test_v2_with_defaults()
        
        # Test 2: Custom economics
        result2 = test_v2_with_custom_economics()
        
        # Test 3: Optimization mode
        result3 = test_v2_optimization_mode()
        
        # Summary
        logger.info("=" * 60)
        logger.info("TEST SUMMARY")
        logger.info("=" * 60)
        
        tests = [
            ("V2 with defaults", result1),
            ("V2 with custom economics", result2),
            ("V2 optimization mode", result3)
        ]
        
        for name, result in tests:
            if result and result.get("status") == "success":
                logger.info(f"✓ {name}: PASSED")
            else:
                logger.info(f"✗ {name}: FAILED")
        
    except Exception as e:
        logger.error(f"Test suite failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()