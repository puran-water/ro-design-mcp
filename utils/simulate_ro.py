"""
WaterTAP simulation utilities for RO systems.

This module provides direct execution of WaterTAP simulations without
relying on Jupyter notebooks, making the system more robust and maintainable.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
import logging

# Import stdout redirect utilities
from .stdout_redirect import redirect_stdout_to_stderr

# Import our core modules
from .mcas_builder import (
    build_mcas_property_configuration,
    get_total_dissolved_solids,
    check_electroneutrality
)
from .ro_model_builder import build_ro_model_mcas
from .ro_solver import initialize_and_solve_mcas
from .ro_results_extractor import extract_results_mcas
from .constants import TYPICAL_COMPOSITIONS
from .trace_ion_handler import create_practical_simulation_composition, post_process_trace_rejection

logger = logging.getLogger(__name__)


def _prepare_ion_composition(
    feed_ion_composition: Optional[Dict[str, float]],
    feed_salinity_ppm: float,
    membrane_type: str
) -> Dict[str, float]:
    """
    Prepare and validate ion composition for simulation.
    
    Args:
        feed_ion_composition: Optional detailed ion composition in mg/L
        feed_salinity_ppm: Target feed salinity in ppm
        membrane_type: Type of membrane ("brackish" or "seawater")
        
    Returns:
        Dict[str, float]: Validated ion composition in mg/L
        
    Raises:
        ValueError: If composition is invalid
    """
    if feed_ion_composition is None:
        # Use typical composition scaled to target salinity
        logger.info(f"No ion composition provided, using typical {membrane_type} water composition")
        typical = TYPICAL_COMPOSITIONS.get(membrane_type, TYPICAL_COMPOSITIONS["brackish"])
        typical_tds = sum(typical.values())
        scale_factor = feed_salinity_ppm / typical_tds
        
        composition = {
            ion: conc * scale_factor 
            for ion, conc in typical.items()
        }
    else:
        composition = feed_ion_composition.copy()
    
    # Validate composition
    actual_tds = get_total_dissolved_solids(composition)
    logger.info(f"Ion composition TDS: {actual_tds:.0f} mg/L (target: {feed_salinity_ppm:.0f} ppm)")
    
    # Check for significant mismatch
    if feed_salinity_ppm > 0 and abs(actual_tds - feed_salinity_ppm) / feed_salinity_ppm > 0.05:
        logger.warning(
            f"Ion composition TDS ({actual_tds:.0f} mg/L) differs from "
            f"stated salinity ({feed_salinity_ppm:.0f} ppm) by more than 5%"
        )
    
    # Check electroneutrality
    is_neutral, imbalance = check_electroneutrality(composition)
    if not is_neutral:
        logger.warning(f"Charge imbalance of {imbalance:.1%}")
        if abs(imbalance) > 0.05:  # More than 5% imbalance
            logger.warning("Large charge imbalance may cause convergence issues")
    
    return composition


def run_ro_simulation(
    configuration: Dict[str, Any],
    feed_salinity_ppm: float,
    feed_ion_composition: Dict[str, float],
    feed_temperature_c: float = 25.0,
    membrane_type: str = "brackish",
    membrane_properties: Optional[Dict[str, float]] = None,
    optimize_pumps: bool = True,
    initialization_strategy: str = "sequential",
    use_nacl_equivalent: bool = True  # New parameter for simplified approach
) -> Dict[str, Any]:
    """
    Run WaterTAP simulation for RO system configuration.
    
    This is a direct implementation that doesn't rely on Jupyter notebooks,
    making it more robust and maintainable.
    
    Args:
        configuration: RO configuration from optimize_ro_configuration
        feed_salinity_ppm: Feed water salinity in ppm
        feed_ion_composition: Required detailed ion composition in mg/L
        feed_temperature_c: Feed temperature in Celsius
        membrane_type: Type of membrane ("brackish" or "seawater")
        membrane_properties: Optional custom membrane properties
        optimize_pumps: Whether to optimize pump pressures
        initialization_strategy: Strategy for model initialization
        
    Returns:
        Dictionary containing simulation results with keys:
        - status: "success" or "error"
        - message: Description of outcome
        - performance: System performance metrics
        - economics: Economic metrics
        - stage_results: Per-stage results
        - mass_balance: Mass balance information
        - ion_tracking: Ion-specific results
        - model: The solved Pyomo model (if successful)
    """
    try:
        logger.info(f"Starting RO simulation for {configuration['array_notation']} array")
        
        # Log progress for debugging/monitoring
        logger.info("[PROGRESS 5%] Preparing ion composition...")
        
        # Step 1: Prepare and validate ion composition
        logger.info("Preparing ion composition...")
        try:
            ion_composition = _prepare_ion_composition(
                feed_ion_composition,
                feed_salinity_ppm,
                membrane_type
            )
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to prepare ion composition: {str(e)}",
                "performance": {},
                "economics": {},
                "stage_results": [],
                "mass_balance": {}
            }
        
        # Step 1.5: Convert to NaCl equivalent if requested (avoids FBBT errors)
        original_composition = ion_composition.copy()
        trace_ions = {}
        strategy = "original"
        
        if use_nacl_equivalent and len(ion_composition) > 2:
            logger.info("Converting multi-ion composition to NaCl equivalent for simulation...")
            total_tds = sum(ion_composition.values())
            simulation_composition = {
                'Na_+': total_tds * 0.393,  # Mass fraction of Na in NaCl
                'Cl_-': total_tds * 0.607   # Mass fraction of Cl in NaCl
            }
            trace_ions = ion_composition  # Store all original ions for post-processing
            strategy = "nacl_equivalent"
            logger.info(f"Using NaCl equivalent with TDS = {total_tds:.0f} mg/L")
        else:
            # Try trace ion handling for non-NaCl approach
            logger.info("Checking for trace ions...")
            simulation_composition, trace_ions, strategy = create_practical_simulation_composition(
                ion_composition
            )
            
            if trace_ions:
                logger.info(f"Trace ion handling strategy: {strategy}")
                logger.info(f"Trace ions identified: {list(trace_ions.keys())}")
        
        # Step 2: Build MCAS property configuration
        logger.info("[PROGRESS 10%] Building MCAS property configuration...")
        try:
            mcas_config = build_mcas_property_configuration(
                feed_composition=simulation_composition,  # Use modified composition
                include_scaling_ions=True,
                include_ph_species=True
            )
            logger.info(f"MCAS configuration created with {len(mcas_config['solute_list'])} solutes")
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to build MCAS configuration: {str(e)}",
                "performance": {},
                "economics": {},
                "stage_results": [],
                "mass_balance": {}
            }
        
        # Step 3: Build the model
        logger.info("[PROGRESS 15%] Building WaterTAP RO model...")
        try:
            # Redirect stdout during model building to prevent MCP protocol corruption
            with redirect_stdout_to_stderr():
                model = build_ro_model_mcas(
                    configuration,
                    mcas_config,
                    feed_salinity_ppm,
                    feed_temperature_c,
                    membrane_type,
                    membrane_properties
                )
            logger.info("Model structure created successfully")
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to build model: {str(e)}",
                "performance": {},
                "economics": {},
                "stage_results": [],
                "mass_balance": {}
            }
        
        # Step 4: Initialize and solve
        logger.info(f"[PROGRESS 25%] Initializing RO model (optimize_pumps={optimize_pumps})...")
        try:
            # Redirect stdout during solving to prevent MCP protocol corruption
            with redirect_stdout_to_stderr():
                solve_results = initialize_and_solve_mcas(
                    model, 
                    configuration, 
                    optimize_pumps
                )
            
            if solve_results["status"] != "success":
                logger.error(f"Model solving failed: {solve_results.get('message', 'Unknown error')}")
                return {
                    "status": "error",
                    "message": solve_results.get("message", "Model solving failed"),
                    "performance": {},
                    "economics": {},
                    "stage_results": [],
                    "mass_balance": {},
                    "solver_details": solve_results
                }
            
            logger.info("Model solved successfully!")
            
        except Exception as e:
            import traceback
            logger.error(f"Detailed error during initialization/solving: {traceback.format_exc()}")
            return {
                "status": "error",
                "message": f"Failed during initialization/solving: {str(e)}",
                "performance": {},
                "economics": {},
                "stage_results": [],
                "mass_balance": {}
            }
        
        # Step 5: Extract results
        logger.info("Extracting results...")
        try:
            # Redirect stdout during results extraction to prevent MCP protocol corruption
            with redirect_stdout_to_stderr():
                results = extract_results_mcas(solve_results["model"], configuration)
            
            # Add solve information
            results["solve_info"] = {
                "termination_condition": solve_results.get("termination_condition", "unknown"),
                "solver_message": solve_results.get("message", "")
            }
            
            # Don't include model in results - causes serialization issues
            
            # Post-process trace ion results if needed
            if trace_ions:
                logger.info("Post-processing trace ion rejection...")
                
                # Get rejection from main results
                if results["stage_results"] and "ion_rejection" in results["stage_results"][0]:
                    # Use actual rejection for the lumped component as basis
                    lumped_rejection = results["stage_results"][0]["ion_rejection"].get("Na_+", 0.95)
                else:
                    lumped_rejection = 0.95
                
                # Estimate trace ion rejections
                trace_rejections = post_process_trace_rejection(
                    results, trace_ions, lumped_rejection
                )
                
                # Add to results
                results["trace_ion_info"] = {
                    "handling_strategy": strategy,
                    "trace_ions": trace_ions,
                    "estimated_rejections": trace_rejections
                }
                
                # Update stage results with trace ion rejections
                for stage in results.get("stage_results", []):
                    if "ion_rejection" in stage:
                        stage["ion_rejection"].update(trace_rejections)
            
            # Log summary
            logger.info(f"Simulation completed successfully!")
            logger.info(f"System recovery: {results['performance']['system_recovery']:.1%}")
            logger.info(f"Permeate TDS: {results['performance']['total_permeate_tds_mg_l']:.0f} mg/L")
            logger.info(f"Specific energy: {results['performance']['specific_energy_kWh_m3']:.2f} kWh/m³")
            
            return results
            
        except Exception as e:
            # If extraction fails but model solved, still return partial results
            logger.error(f"Failed to extract results: {str(e)}")
            return {
                "status": "partial",
                "message": f"Model solved but result extraction failed: {str(e)}",
                "performance": {},
                "economics": {},
                "stage_results": [],
                "mass_balance": {}
            }
        
    except Exception as e:
        logger.error(f"Unexpected error in run_ro_simulation: {str(e)}")
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "performance": {},
            "economics": {},
            "stage_results": [],
            "mass_balance": {}
        }


def calculate_lcow(
    capital_cost: float,
    annual_opex: float,
    annual_production_m3: float,
    discount_rate: float = 0.08,
    plant_lifetime_years: int = 20
) -> float:
    """
    Calculate Levelized Cost of Water (LCOW).
    
    Args:
        capital_cost: Total capital investment ($)
        annual_opex: Annual operating expenses ($/year)
        annual_production_m3: Annual water production (m³/year)
        discount_rate: Discount rate (fraction)
        plant_lifetime_years: Plant lifetime (years)
        
    Returns:
        LCOW in $/m³
    """
    # Calculate capital recovery factor
    crf = (discount_rate * (1 + discount_rate)**plant_lifetime_years) / \
          ((1 + discount_rate)**plant_lifetime_years - 1)
    
    # Annualized capital cost
    annual_capital = capital_cost * crf
    
    # Total annual cost
    total_annual_cost = annual_capital + annual_opex
    
    # LCOW
    if annual_production_m3 > 0:
        lcow = total_annual_cost / annual_production_m3
    else:
        logger.warning("Annual production is zero, cannot calculate LCOW")
        lcow = float('inf')  # Return infinity for zero production
    
    return lcow


def estimate_capital_cost(
    total_membrane_area_m2: float,
    total_power_kw: float,
    membrane_cost_per_m2: Optional[float] = None,
    power_cost_per_kw: Optional[float] = None,
    indirect_cost_factor: Optional[float] = None
) -> float:
    """
    Estimate capital cost for RO system.
    
    Args:
        total_membrane_area_m2: Total membrane area
        total_power_kw: Total installed power
        membrane_cost_per_m2: Membrane cost ($/m²), defaults to config value
        power_cost_per_kw: Power equipment cost ($/kW), defaults to config value
        indirect_cost_factor: Multiplier for indirect costs, defaults to config value
        
    Returns:
        Total capital cost ($)
    """
    # Import config utilities
    from .config import get_config
    
    # Use config values if not provided
    if membrane_cost_per_m2 is None:
        membrane_cost_per_m2 = get_config('capital.membrane_cost_usd_m2', 30.0)
    if power_cost_per_kw is None:
        power_cost_per_kw = get_config('capital.power_equipment_cost_usd_kw', 1000.0)
    if indirect_cost_factor is None:
        indirect_cost_factor = get_config('capital.indirect_cost_factor', 2.5)
    
    # Direct costs
    membrane_cost = total_membrane_area_m2 * membrane_cost_per_m2
    power_equipment_cost = total_power_kw * power_cost_per_kw
    
    direct_cost = membrane_cost + power_equipment_cost
    
    # Total installed cost
    total_cost = direct_cost * indirect_cost_factor
    
    return total_cost