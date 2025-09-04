#!/usr/bin/env python3
"""Analyze LCOW breakdown for v2."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from test_v2_api import test_v2_with_defaults

result = test_v2_with_defaults()

if result and result.get('status') == 'success':
    print('\n=== LCOW BREAKDOWN ===')
    if 'lcow' in result:
        print(f'Total LCOW: ${result["lcow"].get("total_usd_m3", 0):.3f}/m3')
        if 'breakdown' in result['lcow']:
            for key, value in result['lcow']['breakdown'].items():
                if isinstance(value, (int, float)):
                    print(f'  {key}: ${value:.3f}/m3')
                elif isinstance(value, dict):
                    print(f'  {key}:')
                    for k, v in value.items():
                        print(f'    {k}: ${v:.3f}/m3')
    
    print('\n=== CAPITAL COSTS ===')
    if 'capital_costs' in result:
        print(f'Total Capital: ${result["capital_costs"].get("total", 0):,.0f}')
        if 'breakdown' in result['capital_costs']:
            for key, value in result['capital_costs']['breakdown'].items():
                print(f'  {key}: ${value:,.0f}')
    
    print('\n=== OPERATING COSTS (Annual) ===')
    if 'operating_costs' in result:
        print(f'Total Annual Operating: ${result["operating_costs"].get("total_annual", 0):,.0f}/year')
        if 'variable' in result['operating_costs']:
            print('\nVariable costs:')
            for key, value in result['operating_costs']['variable'].items():
                print(f'  {key}: ${value:,.0f}/year')
        if 'fixed' in result['operating_costs']:
            print('\nFixed costs:')
            for key, value in result['operating_costs']['fixed'].items():
                print(f'  {key}: ${value:,.0f}/year')
    
    print('\n=== PERFORMANCE METRICS ===')
    if 'performance' in result:
        perf = result['performance']
        print(f'System recovery: {perf.get("system_recovery", 0):.1%}')
        print(f'Permeate flow: {perf.get("total_permeate_flow_m3_h", 0):.1f} m3/h')
        print(f'Feed flow: {100:.1f} m3/h')
        print(f'Specific energy: {perf.get("specific_energy_kWh_m3", 0):.2f} kWh/m3')
        print(f'Net power: {perf.get("net_power_consumption_kW", 0):.1f} kW')
    
    print('\n=== ECONOMIC PARAMETERS USED ===')
    if 'economic_parameters_used' in result:
        params = result['economic_parameters_used']
        print(f'WACC: {params.get("wacc", 0)*100:.1f}%')
        print(f'Plant lifetime: {params.get("plant_lifetime_years", 0)} years')
        print(f'Utilization: {params.get("utilization_factor", 0)*100:.0f}%')
        print(f'Electricity cost: ${params.get("electricity_cost_usd_kwh", 0):.3f}/kWh')
        
    # Calculate annual permeate production
    if 'performance' in result:
        permeate_m3h = result['performance'].get('total_permeate_flow_m3_h', 0)
        if 'economic_parameters_used' in result:
            util = result['economic_parameters_used'].get('utilization_factor', 0.9)
            annual_production = permeate_m3h * 8760 * util
            print(f'\n=== PRODUCTION ===')
            print(f'Annual production: {annual_production:,.0f} m3/year')
            
            if 'operating_costs' in result:
                opex = result['operating_costs'].get('total_annual', 0)
                opex_per_m3 = opex / annual_production if annual_production > 0 else 0
                print(f'Operating cost per m3: ${opex_per_m3:.3f}/m3')
else:
    print("Simulation failed or no results")