#!/usr/bin/env python3
"""
Create a summary table of RO simulation results.
"""

import json
from tabulate import tabulate

# Read the successful results
with open('workflow_test_results.json', 'r') as f:
    results = json.load(f)

# Additional calculations
for r in results:
    if r['sim_status'] == 'Success':
        # Calculate rejection rate
        r['salt_rejection'] = 1 - (r['permeate_tds'] / r['feed_tds'])
        
        # Determine pressure category
        if r.get('max_pressure_bar', 0) < 20:
            r['pressure_category'] = 'Low (<20 bar)'
        elif r.get('max_pressure_bar', 0) < 40:
            r['pressure_category'] = 'Medium (20-40 bar)'
        else:
            r['pressure_category'] = 'High (>40 bar)'

# Create summary table
print("\n" + "="*100)
print("RO DESIGN AND SIMULATION RESULTS SUMMARY")
print("="*100)
print("\nAll simulations completed successfully using NaCl feed water composition\n")

# Brackish water results
bw_results = [r for r in results if r['membrane'] == 'brackish' and r['sim_status'] == 'Success']
if bw_results:
    print("BRACKISH WATER MEMBRANE RESULTS:")
    print("-" * 100)
    
    table_data = []
    for r in bw_results:
        table_data.append([
            f"{r['feed_flow']:.0f} m³/h",
            f"{r['feed_tds']:,} ppm",
            f"{r['target_recovery']:.0%}",
            r['configuration'],
            r['n_stages'],
            f"{r['achieved_recovery']:.1%}",
            f"{r['permeate_tds']:.0f} mg/L",
            f"{r['salt_rejection']:.1%}",
            f"{r['energy_kwh_m3']:.2f} kWh/m³"
        ])
    
    headers = [
        "Feed Flow", "Feed TDS", "Target\nRecovery", "Array\nConfig", 
        "Stages", "Achieved\nRecovery", "Permeate\nTDS", "Salt\nRejection", "Energy"
    ]
    
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

# Seawater results
sw_results = [r for r in results if r['membrane'] == 'seawater' and r['sim_status'] == 'Success']
if sw_results:
    print("\nSEAWATER MEMBRANE RESULTS:")
    print("-" * 100)
    
    table_data = []
    for r in sw_results:
        table_data.append([
            f"{r['feed_flow']:.0f} m³/h",
            f"{r['feed_tds']:,} ppm",
            f"{r['target_recovery']:.0%}",
            r['configuration'],
            r['n_stages'],
            f"{r['achieved_recovery']:.1%}",
            f"{r['permeate_tds']:.0f} mg/L",
            f"{r['salt_rejection']:.1%}",
            f"{r['energy_kwh_m3']:.2f} kWh/m³"
        ])
    
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

# Key insights
print("\nKEY INSIGHTS:")
print("-" * 50)

# Energy comparison
avg_bw_energy = sum(r['energy_kwh_m3'] for r in bw_results) / len(bw_results) if bw_results else 0
avg_sw_energy = sum(r['energy_kwh_m3'] for r in sw_results) / len(sw_results) if sw_results else 0

print(f"• Average brackish water energy: {avg_bw_energy:.2f} kWh/m³")
print(f"• Average seawater energy: {avg_sw_energy:.2f} kWh/m³")
print(f"• Energy ratio (SW/BW): {avg_sw_energy/avg_bw_energy:.1f}x")

# Recovery analysis
print(f"\n• Recovery achievement:")
for r in results:
    if r['sim_status'] == 'Success':
        diff = (r['achieved_recovery'] - r['target_recovery']) * 100
        print(f"  - {r['scenario']}: {diff:+.1f}% from target")

# Membrane performance
print(f"\n• Salt rejection performance:")
print(f"  - Brackish membranes: {min(r['salt_rejection'] for r in bw_results)*100:.1f}% - {max(r['salt_rejection'] for r in bw_results)*100:.1f}%")
print(f"  - Seawater membranes: {min(r['salt_rejection'] for r in sw_results)*100:.1f}% - {max(r['salt_rejection'] for r in sw_results)*100:.1f}%")

# Stage configuration
print(f"\n• Stage configurations:")
single_stage = [r for r in results if r.get('n_stages') == 1 and r['sim_status'] == 'Success']
two_stage = [r for r in results if r.get('n_stages') == 2 and r['sim_status'] == 'Success']
print(f"  - Single stage: {len(single_stage)} scenarios (avg recovery: {sum(r['achieved_recovery'] for r in single_stage)/len(single_stage):.1%})")
print(f"  - Two stage: {len(two_stage)} scenarios (avg recovery: {sum(r['achieved_recovery'] for r in two_stage)/len(two_stage):.1%})")

print("\n" + "="*100)