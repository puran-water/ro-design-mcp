"""
Hybrid RO simulator using literature-based calculations with WaterTAP economics.

This module provides a practical, reliable alternative to full WaterTAP simulation
by using industry-standard calculations for performance and WaterTAP only for economics.
"""

import logging
from typing import Dict, Any, Optional
from utils.stage_pressure_calculator import (
    calculate_required_feed_pressure,
    calculate_interstage_pressure_requirements
)
from utils.permeate_calculator import (
    calculate_stage_permeate_concentration,
    calculate_stage_mixed_permeate
)
from utils.membrane_properties_handler import get_membrane_properties_for_simulation

logger = logging.getLogger(__name__)


def calculate_blended_feed_composition(
    fresh_flow_m3h: float,
    fresh_comp_mg_l: dict,
    recycle_flow_m3h: float,
    recycle_comp_mg_l: dict
) -> dict:
    """
    Blend fresh feed and recycle streams using mass-weighted averaging.

    Parameters
    ----------
    fresh_flow_m3h : float
        Fresh feed flow rate (m³/h)
    fresh_comp_mg_l : dict
        Fresh feed ion composition (mg/L)
    recycle_flow_m3h : float
        Recycle stream flow rate (m³/h)
    recycle_comp_mg_l : dict
        Recycle stream ion composition (mg/L)

    Returns
    -------
    dict
        Blended feed composition (mg/L)
    """
    total_flow = fresh_flow_m3h + recycle_flow_m3h

    if total_flow < 1e-6:
        logger.error("Total flow near zero in blending calculation")
        return fresh_comp_mg_l.copy()

    blended = {}

    all_ions = set(fresh_comp_mg_l.keys()) | set(recycle_comp_mg_l.keys())
    for ion in all_ions:
        mass_fresh = fresh_flow_m3h * fresh_comp_mg_l.get(ion, 0)
        mass_recycle = recycle_flow_m3h * recycle_comp_mg_l.get(ion, 0)
        blended[ion] = (mass_fresh + mass_recycle) / total_flow

    return blended


def simulate_ro_hybrid(
    configuration: dict,
    feed_composition_mg_l: dict,
    temperature_c: float = 25,
    use_interstage_boost: bool = False
) -> dict:
    """
    Hybrid RO simulation using practical calculations + WaterTAP economics.

    This function orchestrates stage-by-stage calculations using:
    - Literature-based pressure and flow calculations
    - Log-mean concentration for permeate quality
    - Reject osmotic pressure for feed pressure
    - WaterTAP only for economic calculations
    - Iterative solution for recycle configurations

    Parameters
    ----------
    configuration : dict
        Output from optimize_ro_configuration containing:
        - stages: List of stage configurations
        - membrane_model: Membrane model name
        - total_membrane_area_m2: Total membrane area
        - total_permeate_flow_m3h: Total permeate flow
        - recycle_ratio: Recycle fraction (if recycle used)
        - recycle_flow_m3h: Recycle flow rate (if recycle used)
        - system_feed_flow_m3h: Fresh feed flow (if recycle used)
    feed_composition_mg_l : dict
        Fresh feed ion composition (mg/L)
    temperature_c : float
        Operating temperature (°C)
    use_interstage_boost : bool
        Whether to use interstage boosting (separate pump per stage)

    Returns
    -------
    dict
        Simulation results including performance, power, and economics
    """
    # Get membrane properties
    membrane_model = configuration['membrane_model']
    membrane_props = get_membrane_properties_for_simulation(membrane_model)

    # Initialize results
    results = {
        'stages': [],
        'system_performance': {},
        'power_consumption': {},
        'economics': {},
        'configuration': configuration
    }

    # Check for recycle configuration
    has_recycle = configuration.get('recycle_ratio', 0) > 0
    recycle_convergence = {
        'has_recycle': has_recycle,
        'iterations': 0,
        'converged': True,
        'final_tolerance': 0.0,
        'blended_feed_tds_mg_l': sum(feed_composition_mg_l.values())
    }

    # For recycle cases, solve iteratively for steady-state composition
    if has_recycle:
        logger.info("Recycle configuration detected - solving for steady-state composition")

        # Extract recycle parameters
        fresh_flow = configuration.get('system_feed_flow_m3h', configuration['stages'][0]['feed_flow_m3h'])
        recycle_flow = configuration['recycle_flow_m3h']
        disposal_flow = configuration['stages'][-1]['concentrate_flow_m3h'] - recycle_flow

        # Safeguards: check for invalid recycle configuration
        if recycle_flow < 0:
            logger.error(f"Negative recycle flow: {recycle_flow:.2f} m³/h. Invalid configuration!")
            recycle_convergence['converged'] = False
            recycle_convergence['error'] = 'Negative recycle flow'

        if disposal_flow < 0.1:
            logger.error(f"Disposal flow too low: {disposal_flow:.2f} m³/h. Recycle ratio too high!")
            recycle_convergence['converged'] = False
            recycle_convergence['error'] = 'Disposal flow near zero'

        # Initialize recycle composition estimate (3x fresh feed concentration)
        recycle_comp = {ion: conc * 3.0 for ion, conc in feed_composition_mg_l.items()}

        # Iterative solution
        max_iterations = 20
        tolerance = 0.001

        for iteration in range(max_iterations):
            # Calculate blended feed composition
            blended_feed_comp = calculate_blended_feed_composition(
                fresh_flow_m3h=fresh_flow,
                fresh_comp_mg_l=feed_composition_mg_l,
                recycle_flow_m3h=recycle_flow,
                recycle_comp_mg_l=recycle_comp
            )

            # Store for first stage
            stage_1_feed_comp = blended_feed_comp

            # Run stage calculations (logic moved to helper)
            stage_results_temp = _calculate_stages(
                configuration=configuration,
                initial_feed_comp=stage_1_feed_comp,
                membrane_props=membrane_props,
                temperature_c=temperature_c,
                use_interstage_boost=use_interstage_boost
            )

            # Get final stage reject composition
            new_recycle_comp = stage_results_temp['stages'][-1]['reject_composition']

            # Check convergence (hybrid relative + absolute tolerance)
            max_rel_change = 0.0
            max_abs_change = 0.0
            concentration_floor = 1.0
            absolute_tolerance = 1.0

            all_ions = set(recycle_comp.keys()) | set(new_recycle_comp.keys())
            for ion in all_ions:
                old_val = recycle_comp.get(ion, 0.0)
                new_val = new_recycle_comp.get(ion, 0.0)

                abs_change = abs(new_val - old_val)
                max_abs_change = max(max_abs_change, abs_change)

                denominator = max(old_val, concentration_floor)
                rel_change = abs_change / denominator
                max_rel_change = max(max_rel_change, rel_change)

            converged = (max_rel_change < tolerance and max_abs_change < absolute_tolerance)

            logger.debug(
                f"Recycle iteration {iteration + 1}: "
                f"max_rel_change={max_rel_change:.6f}, max_abs_change={max_abs_change:.2f} mg/L"
            )

            # Update convergence tracking
            recycle_convergence['iterations'] = iteration + 1
            recycle_convergence['final_tolerance'] = max_rel_change
            recycle_convergence['final_absolute_change'] = max_abs_change
            recycle_convergence['blended_feed_tds_mg_l'] = sum(blended_feed_comp.values())

            # Check convergence
            if converged:
                logger.info(f"Recycle converged in {iteration + 1} iterations")
                recycle_convergence['converged'] = True
                # Use converged results
                results['stages'] = stage_results_temp['stages']
                stage_permeate_flows = stage_results_temp['stage_permeate_flows']
                stage_permeate_comps = stage_results_temp['stage_permeate_comps']
                total_power_kw = stage_results_temp['total_power_kw']
                break

            # Update for next iteration
            recycle_comp = new_recycle_comp

        else:
            # Max iterations reached without convergence
            logger.warning(f"Recycle did not converge in {max_iterations} iterations. Final tolerance: {max_rel_change:.6f}")
            recycle_convergence['converged'] = False
            # Still use final results but flag as non-converged
            results['stages'] = stage_results_temp['stages']
            stage_permeate_flows = stage_results_temp['stage_permeate_flows']
            stage_permeate_comps = stage_results_temp['stage_permeate_comps']
            total_power_kw = stage_results_temp['total_power_kw']

        # Store convergence info
        results['recycle_convergence'] = recycle_convergence

    else:
        # No recycle - single pass calculation
        stage_1_feed_comp = feed_composition_mg_l.copy()
        stage_results = _calculate_stages(
            configuration=configuration,
            initial_feed_comp=stage_1_feed_comp,
            membrane_props=membrane_props,
            temperature_c=temperature_c,
            use_interstage_boost=use_interstage_boost
        )
        results['stages'] = stage_results['stages']
        stage_permeate_flows = stage_results['stage_permeate_flows']
        stage_permeate_comps = stage_results['stage_permeate_comps']
        total_power_kw = stage_results['total_power_kw']
        results['recycle_convergence'] = recycle_convergence

    # Calculate mixed permeate quality
    mixed_permeate = calculate_stage_mixed_permeate(
        stage_permeate_flows,
        stage_permeate_comps
    )

    # System performance summary
    # For recycle cases, use the original fresh feed flow (before recycle)
    # This is stored in configuration['system_feed_flow_m3h'] if recycle is used
    system_feed_flow = configuration.get('system_feed_flow_m3h',
                                         configuration['stages'][0]['feed_flow_m3h'])

    results['system_performance'] = {
        'total_permeate_flow_m3h': sum(stage_permeate_flows),
        'system_recovery': sum(stage_permeate_flows) / system_feed_flow,
        'mixed_permeate_tds_mg_l': sum(mixed_permeate.values()),
        'mixed_permeate_composition': mixed_permeate,
        'final_reject_tds_mg_l': results['stages'][-1]['reject_tds_mg_l'],
        'final_reject_flow_m3h': results['stages'][-1]['concentrate_flow_m3h']
    }

    # Power consumption summary
    results['power_consumption'] = {
        'total_pump_power_kw': total_power_kw,
        'specific_energy_kwh_m3': total_power_kw / sum(stage_permeate_flows),
        'stage_breakdown': [s['pump_power_kw'] for s in results['stages']]
    }

    # Calculate economics using WaterTAP with mock units
    try:
        # Get feed flow from first stage
        feed_flow_m3h = configuration['stages'][0]['feed_flow_m3h']

        economics = calculate_watertap_economics(
            membrane_area_m2=configuration['total_membrane_area_m2'],
            pump_power_kw=total_power_kw,
            permeate_flow_m3h=sum(stage_permeate_flows),
            feed_pressure_bar=results['stages'][0]['feed_pressure_bar'],
            feed_flow_m3h=feed_flow_m3h
        )
        results['economics'] = economics
        logger.info("Successfully integrated WaterTAP economics with hybrid simulation")
    except Exception as e:
        logger.error(f"Economics calculation failed: {e}")
        results['economics'] = {
            'error': str(e),
            'message': 'Economics calculation failed, performance results still valid',
            'method': 'Failed - check logs'
        }

    return results


def _calculate_stages(
    configuration: dict,
    initial_feed_comp: dict,
    membrane_props: dict,
    temperature_c: float,
    use_interstage_boost: bool
) -> dict:
    """
    Helper function to calculate all stages given an initial feed composition.

    Parameters
    ----------
    configuration : dict
        Stage configuration
    initial_feed_comp : dict
        Feed composition to first stage (may be blended if recycle)
    membrane_props : dict
        Membrane properties
    temperature_c : float
        Operating temperature
    use_interstage_boost : bool
        Whether to use interstage boosting

    Returns
    -------
    dict
        Stage results, permeate flows/comps, and total power
    """
    results = {
        'stages': [],
    }

    # Track flows and compositions through stages
    current_feed_comp = initial_feed_comp.copy()
    stage_permeate_flows = []
    stage_permeate_comps = []
    total_power_kw = 0

    # Process each stage
    for i, stage_config in enumerate(configuration['stages']):
        stage_num = i + 1
        logger.info(f"Processing Stage {stage_num}")

        # Calculate stage pressure requirements
        pressure_result = calculate_required_feed_pressure(
            stage_config,
            current_feed_comp,  # Feed TO THIS STAGE
            membrane_props,
            temperature_c
        )

        # Calculate stage permeate and reject
        permeate_comp, reject_comp = calculate_stage_permeate_concentration(
            current_feed_comp,
            stage_config['stage_recovery'],
            membrane_props,
            temperature_c
        )

        # Calculate pump power for this stage
        if use_interstage_boost or i == 0:
            # Each stage has its own pump or it's the first stage
            stage_power_kw = calculate_pump_power(
                flow_m3h=stage_config['feed_flow_m3h'],
                pressure_bar=pressure_result['feed_pressure_bar'],
                efficiency=get_pump_efficiency(pressure_result['feed_pressure_bar'])
            )
        else:
            # Only pressure boost needed (differential)
            prev_pressure = results['stages'][-1]['feed_pressure_bar']
            delta_pressure = pressure_result['feed_pressure_bar'] - prev_pressure
            if delta_pressure > 0:
                stage_power_kw = calculate_pump_power(
                    flow_m3h=stage_config['feed_flow_m3h'],
                    pressure_bar=delta_pressure,
                    efficiency=get_pump_efficiency(delta_pressure)
                )
            else:
                stage_power_kw = 0

        total_power_kw += stage_power_kw

        # Store stage results
        stage_result = {
            'stage_number': stage_num,
            'feed_flow_m3h': stage_config['feed_flow_m3h'],
            'permeate_flow_m3h': stage_config['permeate_flow_m3h'],
            'concentrate_flow_m3h': stage_config['concentrate_flow_m3h'],
            'stage_recovery': stage_config['stage_recovery'],
            'feed_pressure_bar': pressure_result['feed_pressure_bar'],
            'pressure_components': pressure_result['components'],
            'feed_tds_mg_l': sum(current_feed_comp.values()),
            'permeate_tds_mg_l': sum(permeate_comp.values()),
            'reject_tds_mg_l': sum(reject_comp.values()),
            'pump_power_kw': stage_power_kw,
            'permeate_composition': permeate_comp,
            'reject_composition': reject_comp
        }
        results['stages'].append(stage_result)

        # Track for mixed permeate calculation
        stage_permeate_flows.append(stage_config['permeate_flow_m3h'])
        stage_permeate_comps.append(permeate_comp)

        # Update feed for next stage
        current_feed_comp = reject_comp

    # Return stage results for further processing
    results['stage_permeate_flows'] = stage_permeate_flows
    results['stage_permeate_comps'] = stage_permeate_comps
    results['total_power_kw'] = total_power_kw

    return results


def calculate_pump_power(
    flow_m3h: float,
    pressure_bar: float,
    efficiency: float = 0.75
) -> float:
    """
    Calculate pump power requirement.

    Parameters
    ----------
    flow_m3h : float
        Flow rate (m³/h)
    pressure_bar : float
        Pressure rise (bar)
    efficiency : float
        Pump efficiency (0-1)

    Returns
    -------
    float
        Power requirement (kW)
    """
    # Convert to SI units
    flow_m3s = flow_m3h / 3600
    pressure_pa = pressure_bar * 1e5

    # Hydraulic power
    hydraulic_power_w = flow_m3s * pressure_pa

    # Actual power with efficiency
    power_w = hydraulic_power_w / efficiency

    return power_w / 1000  # Convert to kW


def get_pump_efficiency(pressure_bar: float) -> float:
    """
    Estimate pump efficiency based on pressure.

    Higher pressure pumps typically have better efficiency.

    Parameters
    ----------
    pressure_bar : float
        Operating pressure (bar)

    Returns
    -------
    float
        Estimated efficiency (0-1)
    """
    if pressure_bar < 10:
        # Low pressure pump
        return 0.65
    elif pressure_bar < 40:
        # Medium pressure pump
        return 0.75
    else:
        # High pressure pump (seawater)
        return 0.80


def calculate_watertap_economics(
    membrane_area_m2: float,
    pump_power_kw: float,
    permeate_flow_m3h: float,
    feed_pressure_bar: float,
    feed_flow_m3h: float = None
) -> dict:
    """
    Calculate CAPEX using WaterTAP costing correlations with mock units.

    This function uses WaterTAP's sophisticated capital cost correlations
    but calculates operating costs using simple methods. This is suitable
    for integration into larger treatment train cost models where LCOW
    is calculated at the system level.

    Parameters
    ----------
    membrane_area_m2 : float
        Total membrane area
    pump_power_kw : float
        Total pump power
    permeate_flow_m3h : float
        Permeate production rate
    feed_pressure_bar : float
        Feed pressure (to determine pump type)
    feed_flow_m3h : float, optional
        Feed flow rate (for pump sizing)

    Returns
    -------
    dict
        Economic results with WaterTAP CAPEX and simple OPEX estimates
    """
    try:
        from pyomo.environ import ConcreteModel, value
        from idaes.core import FlowsheetBlock
        from watertap.costing import WaterTAPCostingDetailed
        from utils.mock_units_for_costing import create_mock_pump_costed, create_mock_ro_costed

        # Create model with flowsheet
        m = ConcreteModel()
        m.fs = FlowsheetBlock(dynamic=False)

        # Add WaterTAP costing package
        m.fs.costing = WaterTAPCostingDetailed()

        # Determine flow for pump sizing
        flow_for_pump = feed_flow_m3h if feed_flow_m3h else permeate_flow_m3h / 0.75

        # Create and cost mock pump
        pump = create_mock_pump_costed(
            flowsheet=m.fs,
            name='feed_pump',
            power_kw=pump_power_kw,
            pressure_bar=feed_pressure_bar,
            costing_block=m.fs.costing,
            flow_m3h=flow_for_pump
        )

        # Create and cost mock RO unit
        ro = create_mock_ro_costed(
            flowsheet=m.fs,
            name='ro_unit',
            area_m2=membrane_area_m2,
            pressure_bar=feed_pressure_bar,
            costing_block=m.fs.costing
        )

        # Evaluate capital cost constraints to get actual values
        # WaterTAP creates constraints (capital_cost - cost_expr = 0) but doesn't solve
        # We extract the cost expression (args[1]) and negate it to get actual cost
        if hasattr(pump.costing, 'capital_cost_constraint'):
            constraint_expr = pump.costing.capital_cost_constraint.body
            # Constraint is: capital_cost - (TIC * cost * quantity) = 0
            # args[1] is the negative cost expression, so negate it
            if len(constraint_expr.args) >= 2:
                pump_capex = -value(constraint_expr.args[1])
                pump.costing.capital_cost.fix(pump_capex)
                logger.debug(f"Pump CAPEX from constraint: ${pump_capex:,.0f}")
            else:
                pump_capex = value(pump.costing.capital_cost)
        else:
            pump_capex = value(pump.costing.capital_cost)

        if hasattr(ro.costing, 'capital_cost_constraint'):
            constraint_expr = ro.costing.capital_cost_constraint.body
            if len(constraint_expr.args) >= 2:
                membrane_capex = -value(constraint_expr.args[1])
                ro.costing.capital_cost.fix(membrane_capex)
                logger.debug(f"RO CAPEX from constraint: ${membrane_capex:,.0f}")
            else:
                membrane_capex = value(ro.costing.capital_cost)
        else:
            membrane_capex = value(ro.costing.capital_cost)

        # Aggregate capital costs (no LCOW calculation needed)
        m.fs.costing.cost_process()

        # Extract CAPEX - sum individual costs since total_capital_cost needs solving
        total_capex = pump_capex + membrane_capex

        # Calculate simple OPEX from hybrid results
        annual_hours = 8760 * 0.9  # 90% utilization
        electricity_cost = pump_power_kw * 0.07 * annual_hours  # $0.07/kWh

        # Membrane replacement - use WaterTAP if available
        if hasattr(ro.costing, 'fixed_operating_cost'):
            membrane_replacement = value(ro.costing.fixed_operating_cost)
        else:
            membrane_replacement = membrane_area_m2 * 30 * 0.2  # $30/m² * 20%/year

        maintenance = total_capex * 0.03  # 3% of capital
        annual_opex = electricity_cost + membrane_replacement + maintenance

        # Simple LCOW for reference (not from WaterTAP)
        annual_production = permeate_flow_m3h * annual_hours
        annualization_factor = 0.1  # ~10% for 15 year life at 7% interest
        simple_lcow = (total_capex * annualization_factor + annual_opex) / annual_production

        economics = {
            'capital_cost_usd': total_capex,
            'pump_capital_cost_usd': pump_capex,
            'membrane_capital_cost_usd': membrane_capex,
            'annual_operating_cost_usd': annual_opex,
            'annual_electricity_cost_usd': electricity_cost,
            'annual_membrane_replacement_usd': membrane_replacement,
            'annual_maintenance_usd': maintenance,
            'simple_lcow_usd_m3': simple_lcow,  # For reference only
            'method': 'WaterTAP CAPEX + Simple OPEX'
        }

        logger.info(
            f"WaterTAP CAPEX: Pump=${pump_capex:,.0f}, "
            f"Membrane=${membrane_capex:,.0f}, Total=${total_capex:,.0f}"
        )

        return economics

    except ImportError as e:
        logger.warning(f"WaterTAP not available, using fallback economics: {e}")
        return calculate_simple_economics(
            membrane_area_m2, pump_power_kw, permeate_flow_m3h
        )
    except Exception as e:
        logger.error(f"WaterTAP CAPEX calculation failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return calculate_simple_economics(
            membrane_area_m2, pump_power_kw, permeate_flow_m3h
        )


def calculate_simple_economics(
    membrane_area_m2: float,
    pump_power_kw: float,
    permeate_flow_m3h: float
) -> dict:
    """
    Simple economics calculation as fallback.

    Parameters
    ----------
    membrane_area_m2 : float
        Total membrane area
    pump_power_kw : float
        Total pump power
    permeate_flow_m3h : float
        Permeate production rate

    Returns
    -------
    dict
        Simple economic estimates
    """
    # Capital costs (rough estimates)
    membrane_cost = membrane_area_m2 * 60  # $60/m²
    pump_cost = pump_power_kw * 500  # $500/kW
    other_costs = (membrane_cost + pump_cost) * 1.5  # 150% for other equipment
    total_capital = membrane_cost + pump_cost + other_costs

    # Operating costs
    annual_hours = 8760 * 0.9  # 90% availability
    electricity_cost = pump_power_kw * 0.07 * annual_hours  # $0.07/kWh
    membrane_replacement = membrane_area_m2 * 30 * 0.2  # 20% per year
    maintenance = total_capital * 0.03  # 3% of capital
    annual_operating = electricity_cost + membrane_replacement + maintenance

    # LCOW calculation (simplified)
    annual_production = permeate_flow_m3h * annual_hours
    annualization_factor = 0.1  # ~10% for 15 year life at 7% interest
    annual_capital = total_capital * annualization_factor
    lcow = (annual_capital + annual_operating) / annual_production

    return {
        'capital_cost_usd': total_capital,
        'annual_operating_cost_usd': annual_operating,
        'lcow_usd_m3': lcow,
        'specific_energy_cost_usd_m3': electricity_cost / annual_production,
        'membrane_replacement_usd_year': membrane_replacement
    }