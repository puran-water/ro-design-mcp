"""
Enhanced results extraction utilities for v2 RO simulations.

This module extracts comprehensive economic and performance results including:
- Detailed capital cost breakdown (direct + indirect)
- Operating cost breakdown (fixed + variable)  
- Chemical consumption tracking
- LCOW component breakdown
- Energy metrics with ERD recovery
"""

from typing import Dict, Any, Optional
import logging
from pyomo.environ import value

from .logging_config import get_configured_logger

logger = get_configured_logger(__name__)


def extract_results_v2(
    model,
    configuration: Dict[str, Any],
    feed_salinity_ppm: float,
    feed_temperature_c: float,
    feed_ion_composition: Dict[str, float],
    membrane_type: str,
    economic_params: Dict[str, Any] = None,
    chemical_dosing: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Extract comprehensive v2 results from solved RO model.
    
    Includes:
    - Performance metrics (recovery, TDS, flux, etc.)
    - Detailed capital costs breakdown
    - Operating costs breakdown (fixed + variable)
    - Chemical consumption tracking
    - LCOW with component breakdown
    - Energy metrics including ERD recovery
    
    Args:
        model: Solved Pyomo model
        configuration: RO configuration
        feed_salinity_ppm: Feed salinity
        feed_temperature_c: Feed temperature
        feed_ion_composition: Feed ion composition
        membrane_type: Membrane type
        economic_params: Economic parameters used
        chemical_dosing: Chemical dosing parameters used
        
    Returns:
        Dict with comprehensive v2 results
    """
    results = {
        "status": "success",
        "configuration": configuration,
        "has_recycle": configuration.get("recycle_ratio", 0) > 0,
        "performance": {},
        "stage_results": [],
        "ion_tracking": {},
        "mass_balance": {},
        "capital_costs": {},
        "operating_costs": {},
        "lcow": {},
        "chemical_consumption": {},
        "energy_metrics": {},
        "economic_parameters_used": economic_params
    }
    
    n_stages = configuration.get('n_stages', configuration.get('stage_count', 1))
    
    try:
        logger.info("[v2-results] Starting results extraction...")
        # Extract performance metrics
        results["performance"] = _extract_performance_metrics(model, n_stages)
        logger.info("[v2-results] Performance metrics extracted")
        
        # Extract stage-level results  
        results["stage_results"] = _extract_stage_results(model, n_stages)
        logger.info("[v2-results] Stage results extracted")
        
        # Extract ion tracking
        results["ion_tracking"] = _extract_ion_tracking(model, n_stages, feed_ion_composition)
        logger.info("[v2-results] Ion tracking extracted")
        
        # Extract mass balance
        results["mass_balance"] = _extract_mass_balance(model, n_stages)
        logger.info("[v2-results] Mass balance extracted")
        
        # Extract detailed economics if available
        if hasattr(model.fs, "costing"):
            results["capital_costs"] = _extract_capital_costs(model, n_stages, economic_params)
            logger.info("[v2-results] Capital costs extracted")
            results["operating_costs"] = _extract_operating_costs(model, n_stages, economic_params)
            logger.info("[v2-results] Operating costs extracted")
            results["lcow"] = _extract_lcow_breakdown(model)
            logger.info("[v2-results] LCOW extracted")
            results["energy_metrics"] = _extract_energy_metrics(model, n_stages)
            logger.info("[v2-results] Energy metrics extracted")
            
            if chemical_dosing:
                results["chemical_consumption"] = _extract_chemical_consumption(
                    model, chemical_dosing, economic_params
                )
                logger.info("[v2-results] Chemical consumption extracted")
        
        # Add v1-compatible economics summary for backward compatibility
        if "lcow" in results and "capital_costs" in results and "operating_costs" in results:
            results["economics"] = {
                "lcow_usd_m3": results["lcow"].get("total_usd_m3", 0),
                "total_capital_cost_usd": results["capital_costs"].get("total", 0),
                "annual_operating_cost_usd_year": results["operating_costs"].get("total_annual", 0)
            }
            # Add specific energy if available
            if "energy_metrics" in results:
                results["economics"]["specific_energy_kWh_m3"] = results["energy_metrics"].get("specific_energy_kWh_m3", 0)
        
        logger.info("V2 results extraction completed successfully")
        
    except Exception as e:
        logger.error(f"Error extracting v2 results: {str(e)}", exc_info=True)
        results["status"] = "error"
        results["error"] = str(e)
    
    return results


def _extract_performance_metrics(model, n_stages):
    """Extract overall system performance metrics."""
    
    # Calculate total flows
    # MCAS doesn't have flow_mass - sum component flows
    feed_flow = sum(value(model.fs.fresh_feed.properties[0].flow_mass_phase_comp['Liq', comp])
                    for comp in model.fs.properties.component_list)
    
    total_perm_flow = sum(
        sum(value(getattr(model.fs, f"ro_stage{i}").mixed_permeate[0].flow_mass_phase_comp['Liq', comp])
            for comp in model.fs.properties.component_list)
        for i in range(1, n_stages + 1)
    )
    
    # Prefer volumetric expression if available; otherwise, approximate with density
    try:
        if hasattr(model.fs, "total_permeate_flow_vol"):
            total_perm_flow_m3h = value(model.fs.total_permeate_flow_vol) * 3600
        else:
            total_perm_flow_m3h = total_perm_flow * 3.6  # approximate assuming 1000 kg/m3
    except Exception:
        total_perm_flow_m3h = total_perm_flow * 3.6
    
    # System recovery
    system_recovery = total_perm_flow / feed_flow if feed_flow > 0 else 0
    
    # Permeate TDS (weighted average)
    total_perm_tds = 0
    for i in range(1, n_stages + 1):
        ro = getattr(model.fs, f"ro_stage{i}")
        stage_perm_flow = sum(value(ro.mixed_permeate[0].flow_mass_phase_comp['Liq', comp])
                              for comp in model.fs.properties.component_list)
        # Sum only solutes for TDS (exclude H2O)
        stage_perm_tds = sum(
            value(ro.mixed_permeate[0].conc_mass_phase_comp['Liq', ion]) * 1000
            for ion in model.fs.properties.solute_set
        )
        total_perm_tds += stage_perm_tds * stage_perm_flow
    
    avg_perm_tds = total_perm_tds / total_perm_flow if total_perm_flow > 0 else 0
    
    # Total electrical power consumption from pumps (kW)
    total_power_kW = sum(
        value(getattr(model.fs, f"pump{i}").work_mechanical[0]) / 1000
        for i in range(1, n_stages + 1)
    )
    
    # ERD hydraulic transfer power (informational only; not electricity)
    erd_hydraulic_kW = 0
    if hasattr(model.fs, "erd"):
        try:
            erd_hydraulic_kW = max(0.0, value(model.fs.erd.feed_side.work[0]) / 1000)
        except Exception:
            erd_hydraulic_kW = 0
    
    # Net electrical power is pumps only (no ERD electricity generation)
    net_power_kW = total_power_kW
    
    # Specific energy consumption: prefer WaterTAP costing SEC if available
    if hasattr(model.fs, "costing") and hasattr(model.fs.costing, "specific_energy_consumption"):
        try:
            specific_energy = value(model.fs.costing.specific_energy_consumption)
        except Exception:
            specific_energy = net_power_kW / total_perm_flow_m3h if total_perm_flow_m3h > 0 else 0
    else:
        specific_energy = net_power_kW / total_perm_flow_m3h if total_perm_flow_m3h > 0 else 0
    
    return {
        "system_recovery": system_recovery,
        "total_permeate_flow_m3_h": total_perm_flow_m3h,
        "total_permeate_tds_mg_l": avg_perm_tds,
        "total_power_consumption_kW": total_power_kW,
        "erd_recovery_kW": erd_hydraulic_kW,
        "net_power_consumption_kW": net_power_kW,
        "specific_energy_kWh_m3": specific_energy
    }


def _extract_stage_results(model, n_stages):
    """Extract detailed results for each RO stage."""
    
    stage_results = []
    
    for i in range(1, n_stages + 1):
        ro = getattr(model.fs, f"ro_stage{i}")
        pump = getattr(model.fs, f"pump{i}")
        
        # Stage flows - MCAS requires summing component flows
        feed_flow = sum(value(ro.inlet.flow_mass_phase_comp[0, 'Liq', comp])
                       for comp in model.fs.properties.component_list)
        perm_flow = sum(value(ro.mixed_permeate[0].flow_mass_phase_comp['Liq', comp])
                       for comp in model.fs.properties.component_list)
        conc_flow = sum(value(ro.retentate.flow_mass_phase_comp[0, 'Liq', comp])
                       for comp in model.fs.properties.component_list)
        
        # Recovery
        recovery = perm_flow / feed_flow if feed_flow > 0 else 0
        
        # Pressures
        feed_pressure = value(ro.inlet.pressure[0]) / 1e5  # Pa to bar
        conc_pressure = value(ro.retentate.pressure[0]) / 1e5
        # Permeate pressure can be a scalar Var on the mixed_permeate block
        try:
            perm_pressure = value(ro.mixed_permeate[0].pressure) / 1e5
        except Exception:
            # Fallback to permeate port pressure if mixed_permeate not available
            perm_pressure = value(ro.permeate.pressure[0]) / 1e5
        
        # Pump power
        pump_power = value(pump.work_mechanical[0]) / 1000  # W to kW
        
        # Ion data for all modeled solutes
        ion_data = {}
        for ion in model.fs.properties.solute_set:
            try:
                feed_c = value(ro.feed_side.properties_in[0].conc_mass_phase_comp['Liq', ion]) * 1000
            except Exception:
                feed_c = 0.0
            try:
                perm_c = value(ro.mixed_permeate[0].conc_mass_phase_comp['Liq', ion]) * 1000
            except Exception:
                # Fallback to permeate port if mixed_permeate not available
                try:
                    perm_c = value(ro.permeate.conc_mass_phase_comp[0, 'Liq', ion]) * 1000
                except Exception:
                    perm_c = 0.0
            try:
                conc_c = value(ro.feed_side.properties_out[0].conc_mass_phase_comp['Liq', ion]) * 1000
            except Exception:
                conc_c = 0.0

            rej = (1 - perm_c / feed_c) if feed_c > 0 else 0.0
            ion_data[ion] = {
                "feed_mg_l": feed_c,
                "permeate_mg_l": perm_c,
                "concentrate_mg_l": conc_c,
                "rejection": rej,
            }
        
        stage_results.append({
            "stage": i,
            "recovery": recovery,
            "feed_flow_kg_s": feed_flow,
            "permeate_flow_kg_s": perm_flow,
            "concentrate_flow_kg_s": conc_flow,
            "feed_pressure_bar": feed_pressure,
            "concentrate_pressure_bar": conc_pressure,
            "permeate_pressure_bar": perm_pressure,
            "pump_power_kW": pump_power,
            "membrane_area_m2": value(ro.area),
            "ion_data": ion_data
        })
    
    return stage_results


def _extract_ion_tracking(model, n_stages, feed_ion_composition):
    """Extract ion mass balance and overall rejection."""
    
    ion_tracking = {}
    
    # Track all modeled solutes
    for ion in model.fs.properties.solute_set:
        # Fresh feed concentration: prefer model state if available, else fall back to input
        try:
            fresh_feed_conc = value(
                model.fs.fresh_feed.properties[0].conc_mass_phase_comp['Liq', ion]
            ) * 1000
        except Exception:
            fresh_feed_conc = feed_ion_composition.get(ion, 0)

        # Combined permeate concentration (flow-weighted)
        total_perm_flow = 0.0
        total_perm_mass = 0.0
        for i in range(1, n_stages + 1):
            ro = getattr(model.fs, f"ro_stage{i}")
            stage_perm_flow = sum(
                value(ro.mixed_permeate[0].flow_mass_phase_comp['Liq', comp])
                for comp in model.fs.properties.component_list
            )
            try:
                stage_perm_conc = value(
                    ro.mixed_permeate[0].conc_mass_phase_comp['Liq', ion]
                ) * 1000
            except Exception:
                try:
                    stage_perm_conc = value(ro.permeate.conc_mass_phase_comp[0, 'Liq', ion]) * 1000
                except Exception:
                    stage_perm_conc = 0.0

            total_perm_flow += stage_perm_flow
            total_perm_mass += stage_perm_flow * stage_perm_conc

        avg_perm_conc = total_perm_mass / total_perm_flow if total_perm_flow > 0 else 0.0

        # Disposal concentration (from final stage or recycle split)
        if hasattr(model.fs, "disposal_product"):
            try:
                disposal_conc = value(
                    model.fs.disposal_product.properties[0].conc_mass_phase_comp['Liq', ion]
                ) * 1000
            except Exception:
                disposal_conc = 0.0
        else:
            # Use final stage concentrate
            final_ro = getattr(model.fs, f"ro_stage{n_stages}")
            try:
                disposal_conc = value(
                    final_ro.feed_side.properties_out[0].conc_mass_phase_comp['Liq', ion]
                ) * 1000
            except Exception:
                disposal_conc = 0.0

        # Overall rejection
        overall_rejection = (1 - avg_perm_conc / fresh_feed_conc) if fresh_feed_conc > 0 else 0.0

        ion_tracking[ion] = {
            "fresh_feed_mg_l": fresh_feed_conc,
            "combined_permeate_mg_l": avg_perm_conc,
            "disposal_mg_l": disposal_conc,
            "overall_rejection": overall_rejection,
        }
    
    return ion_tracking


def _extract_mass_balance(model, n_stages):
    """Extract mass balance verification."""
    
    # Total feed
    # MCAS doesn't have flow_mass - sum component flows
    feed_flow = sum(value(model.fs.fresh_feed.properties[0].flow_mass_phase_comp['Liq', comp])
                    for comp in model.fs.properties.component_list)
    
    # Total permeate
    total_perm_flow = sum(
        sum(value(getattr(model.fs, f"ro_stage{i}").mixed_permeate[0].flow_mass_phase_comp['Liq', comp])
            for comp in model.fs.properties.component_list)
        for i in range(1, n_stages + 1)
    )
    
    # Total disposal/concentrate - MCAS requires summing component flows
    if hasattr(model.fs, "disposal_product"):
        disposal_flow = sum(value(model.fs.disposal_product.properties[0].flow_mass_phase_comp['Liq', comp])
                           for comp in model.fs.properties.component_list)
    else:
        final_ro = getattr(model.fs, f"ro_stage{n_stages}")
        disposal_flow = sum(value(final_ro.retentate.flow_mass_phase_comp[0, 'Liq', comp])
                           for comp in model.fs.properties.component_list)
    
    # Mass balance error
    mass_balance_error = abs(feed_flow - total_perm_flow - disposal_flow)
    mass_balance_ok = mass_balance_error < 1e-6
    
    return {
        "feed_flow_kg_s": feed_flow,
        "total_permeate_flow_kg_s": total_perm_flow,
        "disposal_flow_kg_s": disposal_flow,
        "mass_balance_error": mass_balance_error,
        "mass_balance_ok": mass_balance_ok
    }


def _extract_capital_costs(model, n_stages, economic_params):
    """Extract detailed capital cost breakdown."""
    
    capital_costs = {
        "direct": {
            "pumps": {},
            "ro_membranes": {},
            "erd": 0,
            "cartridge_filters": 0,
            "chemical_dosing": 0,
            "cip_system": 0
        },
        "indirect": {},
        "total": 0
    }
    
    # Pump costs
    for i in range(1, n_stages + 1):
        pump = getattr(model.fs, f"pump{i}")
        if hasattr(pump, "costing") and hasattr(pump.costing, "capital_cost"):
            capital_costs["direct"]["pumps"][f"pump{i}"] = value(pump.costing.capital_cost)
    
    # RO membrane costs
    for i in range(1, n_stages + 1):
        ro = getattr(model.fs, f"ro_stage{i}")
        if hasattr(ro, "costing") and hasattr(ro.costing, "capital_cost"):
            capital_costs["direct"]["ro_membranes"][f"stage{i}"] = value(ro.costing.capital_cost)
    
    # ERD cost
    if hasattr(model.fs, "erd") and hasattr(model.fs.erd, "costing"):
        capital_costs["direct"]["erd"] = value(model.fs.erd.costing.capital_cost)
    
    # Pretreatment costs
    if hasattr(model.fs, "cartridge_filter") and hasattr(model.fs.cartridge_filter, "costing"):
        capital_costs["direct"]["cartridge_filters"] = value(model.fs.cartridge_filter.costing.capital_cost)
    
    if hasattr(model.fs, "antiscalant_addition") and hasattr(model.fs.antiscalant_addition, "costing"):
        capital_costs["direct"]["chemical_dosing"] = value(model.fs.antiscalant_addition.costing.capital_cost)
    
    # CIP system cost
    if hasattr(model.fs, "cip_system"):
        capital_costs["direct"]["cip_system"] = value(model.fs.cip_system.capital_cost_total)
    
    # Indirect costs (if using WaterTAPCostingDetailed)
    if hasattr(model.fs.costing, "land_cost"):
        capital_costs["indirect"]["land"] = value(model.fs.costing.land_cost)
        capital_costs["indirect"]["working_capital"] = value(model.fs.costing.working_capital)
    
    # Total capital cost from WaterTAPCostingDetailed
    if hasattr(model.fs.costing, "total_capital_cost"):
        capital_costs["total"] = value(model.fs.costing.total_capital_cost)
    
    # Add pretreatment and CIP costs that aren't included in WaterTAPCostingDetailed total
    additional_capex = 0
    
    # Add CIP system cost if present
    if capital_costs["direct"]["cip_system"] > 0:
        additional_capex += capital_costs["direct"]["cip_system"]
        
    # Add pretreatment capex if using cartridge filters
    if economic_params.get("include_cartridge_filters", False):
        feed_flow_m3h = economic_params.get("feed_flow_m3h", 100)
        cf_unit_cost = economic_params.get("cartridge_filter_cost_usd_m3h", 100)
        estimated_cf_capex = feed_flow_m3h * cf_unit_cost
        capital_costs["direct"]["cartridge_filters"] = estimated_cf_capex
        additional_capex += estimated_cf_capex
    
    # Add ERD capital if it was manually calculated
    if hasattr(model.fs, "erd") and hasattr(model.fs.erd, "capital_cost"):
        erd_capex = value(model.fs.erd.capital_cost)
        capital_costs["direct"]["erd"] = erd_capex
        additional_capex += erd_capex

    # Update total to include additional capex
    capital_costs["total"] += additional_capex
    
    return capital_costs


def _extract_operating_costs(model, n_stages, economic_params):
    """Extract detailed operating cost breakdown."""
    
    operating_costs = {
        "fixed": {},
        "variable": {},
        "total_annual": 0
    }
    
    # Fixed operating costs (if using WaterTAPCostingDetailed)
    if hasattr(model.fs.costing, "salary_cost"):
        operating_costs["fixed"]["salaries"] = value(model.fs.costing.salary_cost)
        operating_costs["fixed"]["benefits"] = value(model.fs.costing.benefits_cost)
        operating_costs["fixed"]["maintenance"] = value(model.fs.costing.maintenance_cost)
        operating_costs["fixed"]["laboratory"] = value(model.fs.costing.laboratory_cost)
        operating_costs["fixed"]["insurance_taxes"] = value(model.fs.costing.insurance_and_taxes_cost)
    
    # Membrane replacement cost
    membrane_replacement_total = 0
    for i in range(1, n_stages + 1):
        ro = getattr(model.fs, f"ro_stage{i}")
        if hasattr(ro, "costing") and hasattr(ro.costing, "fixed_operating_cost"):
            membrane_replacement_total += value(ro.costing.fixed_operating_cost)
    operating_costs["fixed"]["membrane_replacement"] = membrane_replacement_total
    
    # Variable operating costs
    if hasattr(model.fs.costing, "aggregate_flow_costs"):
        flow_costs = dict(getattr(model.fs.costing, "aggregate_flow_costs", {}))
        
        # Electricity
        if "electricity" in flow_costs:
            operating_costs["variable"]["electricity"] = value(flow_costs["electricity"])
        
        # Chemicals
        if "antiscalant" in flow_costs:
            operating_costs["variable"]["antiscalant"] = value(flow_costs["antiscalant"])
        
        if "cip_chemical" in flow_costs:
            operating_costs["variable"]["cip_chemicals"] = value(flow_costs["cip_chemical"])
    
    # Total operating cost
    if hasattr(model.fs.costing, "total_operating_cost"):
        operating_costs["total_annual"] = value(model.fs.costing.total_operating_cost)
    
    return operating_costs


def _extract_lcow_breakdown(model):
    """Extract LCOW with component breakdown."""
    
    lcow = {
        "total_usd_m3": 0,
        "breakdown": {}
    }
    
    if hasattr(model.fs.costing, "LCOW"):
        lcow["total_usd_m3"] = value(model.fs.costing.LCOW)
    
    # Component breakdown (if available)
    if hasattr(model.fs.costing, "LCOW_capital"):
        lcow["breakdown"]["capital"] = value(model.fs.costing.LCOW_capital)
    
    if hasattr(model.fs.costing, "LCOW_fixed"):
        lcow["breakdown"]["fixed_opex"] = value(model.fs.costing.LCOW_fixed)
    
    if hasattr(model.fs.costing, "LCOW_variable"):
        lcow["breakdown"]["variable_opex"] = value(model.fs.costing.LCOW_variable)
    
    # Detailed variable OPEX breakdown
    if hasattr(model.fs.costing, "LCOW_aggregate_variable_opex"):
        lcow["breakdown"]["variable_details"] = {}
        try:
            for flow_type, lcow_value in model.fs.costing.LCOW_aggregate_variable_opex.items():
                lcow["breakdown"]["variable_details"][flow_type] = value(lcow_value)
        except Exception:
            pass
    
    return lcow


def _extract_chemical_consumption(model, chemical_dosing, economic_params):
    """Extract annual chemical consumption."""
    
    consumption = {}
    
    # Get utilization factor
    utilization = value(model.fs.costing.utilization_factor) if hasattr(model.fs.costing, "utilization_factor") else 0.9
    
    # Antiscalant consumption
    if hasattr(model.fs, "antiscalant_flow_kg_s"):
        antiscalant_kg_s = value(model.fs.antiscalant_flow_kg_s)
        consumption["antiscalant_kg_year"] = antiscalant_kg_s * 365 * 24 * 3600 * utilization
    
    # CIP chemicals
    if hasattr(model.fs, "cip_system"):
        consumption["cip_chemicals_kg_year"] = value(model.fs.cip_system.chemical_consumption_kg_year)
        
        # Break down by type if fractions are provided
        if chemical_dosing:
            total_cip = consumption["cip_chemicals_kg_year"]
            consumption["cip_surfactant_kg_year"] = total_cip * chemical_dosing.get("cip_surfactant_fraction", 0.7)
            consumption["cip_acid_kg_year"] = total_cip * chemical_dosing.get("cip_acid_fraction", 0.2)
            consumption["cip_base_kg_year"] = total_cip * chemical_dosing.get("cip_base_fraction", 0.1)
    
    return consumption


def _extract_energy_metrics(model, n_stages):
    """Extract detailed energy metrics."""
    
    metrics = {
        "pump_power_breakdown": {},
        "total_pump_power_kW": 0,
        "erd_recovery_power_kW": 0,
        "net_power_kW": 0,
        "specific_energy_kWh_m3": 0
    }
    
    # Pump power breakdown
    for i in range(1, n_stages + 1):
        pump = getattr(model.fs, f"pump{i}")
        pump_power = value(pump.work_mechanical[0]) / 1000  # W to kW
        metrics["pump_power_breakdown"][f"pump{i}"] = pump_power
        metrics["total_pump_power_kW"] += pump_power
    
    # ERD hydraulic transfer (informational)
    if hasattr(model.fs, "erd"):
        try:
            metrics["erd_recovery_power_kW"] = max(0.0, value(model.fs.erd.feed_side.work[0]) / 1000)
        except Exception:
            metrics["erd_recovery_power_kW"] = 0
        try:
            metrics["erd_recovery_efficiency"] = value(model.fs.erd.efficiency_pressure_exchanger[0])
        except Exception:
            pass
    
    # Net electrical power (pumps only)
    metrics["net_power_kW"] = metrics["total_pump_power_kW"]
    
    # Specific energy
    if hasattr(model.fs.costing, "specific_energy_consumption"):
        metrics["specific_energy_kWh_m3"] = value(model.fs.costing.specific_energy_consumption)
    
    return metrics
