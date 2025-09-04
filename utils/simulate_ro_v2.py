"""
Enhanced WaterTAP simulation utilities with detailed economic modeling (v2).

This module provides comprehensive RO system simulation with:
- WaterTAPCostingDetailed for full economic transparency
- Chemical consumption tracking based on actual usage
- Ancillary equipment (cartridge filters, CIP, ERD)
- Support for plant-wide optimization
"""

import os
import json
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import logging

# Import stdout redirect utilities
from .stdout_redirect import redirect_stdout_to_stderr

# Import core modules
from .mcas_builder import (
    build_mcas_property_configuration,
    get_total_dissolved_solids,
    check_electroneutrality
)
from .ro_model_builder_v2 import build_ro_model_v2  # Enhanced model builder
from .ro_solver import initialize_and_solve_mcas
from .ro_results_extractor_v2 import extract_results_v2  # Enhanced results extractor
from .constants import TYPICAL_COMPOSITIONS
from .trace_ion_handler import create_practical_simulation_composition, post_process_trace_rejection
from .economic_defaults import validate_economic_params, validate_dosing_params

logger = logging.getLogger(__name__)

# Model store for optimization mode
_model_store = {}


def run_ro_simulation_v2(
    configuration: Dict[str, Any],
    feed_salinity_ppm: float,
    feed_ion_composition: Dict[str, float],
    feed_temperature_c: float = 25.0,
    membrane_type: str = "brackish",
    economic_params: Dict[str, Any] = None,
    chemical_dosing: Dict[str, Any] = None,
    optimization_mode: bool = False,
    api_version: str = "v2",
    initialization_strategy: str = "sequential",
    use_nacl_equivalent: bool = False  # Changed default: try direct MCAS first
) -> Dict[str, Any]:
    """
    Run enhanced WaterTAP simulation with detailed economic modeling (v2).
    
    This version includes:
    - WaterTAPCostingDetailed for full transparency
    - Chemical consumption tracking
    - Ancillary equipment (filters, CIP, ERD)
    - Optimization mode support
    
    Args:
        configuration: RO configuration from optimize_ro_configuration
        feed_salinity_ppm: Feed water salinity in ppm
        feed_ion_composition: Required detailed ion composition in mg/L
        feed_temperature_c: Feed temperature in Celsius
        membrane_type: Type of membrane ("brackish" or "seawater")
        economic_params: Economic parameters (validated, with defaults applied)
        chemical_dosing: Chemical dosing parameters (validated, with defaults applied)
        optimization_mode: If True, build model for optimization without solving
        api_version: API version identifier
        initialization_strategy: Strategy for initialization
        use_nacl_equivalent: Use simplified NaCl equivalent approach
        
    Returns:
        Dict containing simulation results or model handle for optimization
    """
    logger.info(f"Starting v2 RO simulation with {membrane_type} membrane at {feed_salinity_ppm} ppm")
    
    # Validate parameters (already done in server.py, but double-check)
    if economic_params:
        validate_economic_params(economic_params)
    if chemical_dosing:
        validate_dosing_params(chemical_dosing)
    
    # Redirect stdout to stderr to prevent MCP protocol corruption
    with redirect_stdout_to_stderr():
        try:
            # Handle ion composition
            if use_nacl_equivalent:
                # Store original trace ions for post-processing
                trace_ions = feed_ion_composition.copy()
                
                # Create practical composition with NaCl equivalent
                logger.info("Creating NaCl equivalent composition for simulation")
                # For v2, use simple NaCl equivalent for now
                total_tds = sum(feed_ion_composition.values())
                practical_comp = {
                    'Na_+': total_tds * 0.393,  # Mass fraction of Na in NaCl
                    'Cl_-': total_tds * 0.607   # Mass fraction of Cl in NaCl
                }
                trace_info = {
                    "strategy": "nacl_equivalent",
                    "original_ions": feed_ion_composition,
                    "total_tds": total_tds
                }
                feed_ion_composition = practical_comp
                logger.info(f"Using practical composition: {feed_ion_composition}")
            else:
                trace_ions = None
                trace_info = None
            
            # Validate TDS
            actual_tds = get_total_dissolved_solids(feed_ion_composition)
            logger.info(f"Feed TDS: {actual_tds:.1f} mg/L (target: {feed_salinity_ppm} mg/L)")
            
            # Check electroneutrality
            is_neutral, charge_imbalance = check_electroneutrality(feed_ion_composition)
            if not is_neutral and abs(charge_imbalance) > 0.05:
                logger.warning(f"Charge imbalance: {charge_imbalance:.1%}")
            
            # Build MCAS property configuration
            mcas_config = build_mcas_property_configuration(
                feed_composition=feed_ion_composition,
                include_scaling_ions=True,
                include_ph_species=True
            )
            
            # Build enhanced RO model with v2 features
            logger.info("Building enhanced RO model with detailed costing...")
            m = build_ro_model_v2(
                configuration,
                mcas_config,
                feed_salinity_ppm,
                feed_temperature_c,
                membrane_type,
                economic_params=economic_params,
                chemical_dosing=chemical_dosing,
                membrane_properties=None,  # Use defaults from membrane_properties_handler
                optimization_mode=optimization_mode
            )
            
            if optimization_mode:
                # Store model for orchestration
                model_handle = str(uuid.uuid4())
                _model_store[model_handle] = m
                
                # Build metadata for optimization
                metadata = _build_optimization_metadata(m, configuration)
                
                logger.info(f"Model built for optimization, handle: {model_handle}")
                
                return {
                    "status": "success",
                    "model_handle": model_handle,
                    "metadata": metadata,
                    "api_version": api_version
                }
            else:
                # Normal simulation mode - initialize and solve
                logger.info("Initializing and solving enhanced model...")
                # Always optimize pumps in v2 for accurate recovery matching
                results = initialize_and_solve_mcas(m, configuration, optimize_pumps=True)
                
                if results.get("status") != "success":
                    logger.error(f"Solver failed: {results.get('message', 'Unknown error')}")
                    return {
                        "status": "error",
                        "message": results.get("message", "Solver failed"),
                        "termination_condition": results.get("termination_condition", "error"),
                        "api_version": api_version
                    }
                
                # Extract enhanced results with detailed economics
                logger.info("Extracting v2 results with detailed economics...")
                simulation_results = extract_results_v2(
                    m,
                    configuration,
                    feed_salinity_ppm,
                    feed_temperature_c,
                    feed_ion_composition,
                    membrane_type,
                    economic_params,
                    chemical_dosing
                )
                
                # Post-process trace ion rejection if using NaCl equivalent
                if use_nacl_equivalent and trace_ions:
                    # Do not overwrite full results; attach under a key
                    try:
                        trace_rejections = post_process_trace_rejection(
                            simulation_results,
                            trace_ions,
                            trace_info
                        )
                        simulation_results["trace_ion_rejection"] = trace_rejections
                        simulation_results["trace_ion_info"] = trace_info
                    except Exception as _e:
                        logger.warning(f"Trace ion post-processing failed: {_e}")
                
                # Add solver info
                simulation_results["solve_info"] = {
                    "termination_condition": results["termination_condition"],
                    "solver_message": results.get("message", "Solver completed with optimal solution")
                }
                
                simulation_results["api_version"] = api_version
                
                return simulation_results
                
        except Exception as e:
            logger.error(f"Error in v2 simulation: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": str(e),
                "api_version": api_version
            }


def _build_optimization_metadata(model, configuration):
    """
    Build metadata dictionary for optimization mode.
    
    Args:
        model: Pyomo model
        configuration: RO configuration
        
    Returns:
        Dict with inputs, decision_vars, outputs, and ports
    """
    from pyomo.environ import value
    
    n_stages = configuration.get("n_stages", configuration.get("stage_count", 1))
    
    metadata = {
        "inputs": {},
        "decision_vars": {},
        "outputs": {},
        "ports": {},
        "configuration": configuration
    }
    
    # Extract input specifications
    metadata["inputs"] = {
        "feed_flow": {
            "pyomo_path": "fs.fresh_feed.outlet",
            "value": sum(value(model.fs.fresh_feed.properties[0].flow_mass_phase_comp['Liq', comp]) 
                        for comp in model.fs.properties.component_list),
            "units": "kg/s",
            "bounds": [0.1, 1000]
        },
        "feed_pressure": {
            "pyomo_path": "fs.pump1.outlet.pressure[0]",
            "value": value(model.fs.pump1.outlet.pressure[0]),
            "units": "Pa",
            "bounds": [101325, 10000000]
        }
    }
    
    # Extract decision variables
    for i in range(1, n_stages + 1):
        ro = getattr(model.fs, f"ro_stage{i}")
        pump = getattr(model.fs, f"pump{i}")
        
        metadata["decision_vars"][f"stage{i}_area"] = {
            "pyomo_path": f"fs.ro_stage{i}.area",
            "value": value(ro.area),
            "units": "m2",
            "bounds": [10, 10000]
        }
        
        metadata["decision_vars"][f"pump{i}_pressure"] = {
            "pyomo_path": f"fs.pump{i}.outlet.pressure[0]",
            "value": value(pump.outlet.pressure[0]),
            "units": "Pa",
            "bounds": [101325, 10000000]
        }
    
    # Extract outputs
    metadata["outputs"] = {
        "lcow": {
            "pyomo_path": "fs.costing.LCOW",
            "units": "$/m3"
        },
        "specific_energy": {
            "pyomo_path": "fs.costing.specific_energy_consumption",
            "units": "kWh/m3"
        },
        "total_capital_cost": {
            "pyomo_path": "fs.costing.total_capital_cost",
            "units": "$"
        },
        "total_operating_cost": {
            "pyomo_path": "fs.costing.total_operating_cost",
            "units": "$/year"
        }
    }
    
    # Extract port information (v2 uses fresh_feed and product/disposal blocks)
    metadata["ports"] = {
        "feed_inlet": "fs.fresh_feed.inlet",
        "permeate_outlet": "fs.product.inlet",
        "brine_outlet": "fs.disposal.inlet"
    }
    
    return metadata


def get_model_by_handle(model_handle: str):
    """
    Retrieve a model by its handle (for optimization orchestration).
    
    Args:
        model_handle: UUID handle for the model
        
    Returns:
        Pyomo model or None if not found
    """
    return _model_store.get(model_handle)


def clear_model_store():
    """Clear all stored models to free memory."""
    global _model_store
    _model_store = {}
    logger.info("Model store cleared")
