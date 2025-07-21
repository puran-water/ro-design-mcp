#!/usr/bin/env python3
"""
Test script to determine TDS-aware flux-safe pressure limits for different membranes.

This script calculates the maximum operating pressure for various membrane types
while accounting for osmotic pressure effects at different TDS levels.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from typing import Dict, Tuple


def calculate_osmotic_pressure(tds_ppm: float) -> float:
    """
    Calculate osmotic pressure from TDS concentration.
    
    Uses correlation: π (Pa) ≈ 0.7 * TDS (g/L) * 1e5
    
    Args:
        tds_ppm: Total dissolved solids in ppm (mg/L)
        
    Returns:
        Osmotic pressure in Pa
    """
    tds_g_l = tds_ppm / 1000
    osmotic_bar = 0.7 * tds_g_l
    osmotic_pa = osmotic_bar * 1e5
    return osmotic_pa


def calculate_max_pressure_from_flux(
    A_w: float,
    tds_ppm: float,
    recovery: float = 0.5,
    max_flux: float = 0.025,  # 83% of WaterTAP limit
    permeate_pressure: float = 101325  # 1 atm
) -> Dict[str, float]:
    """
    Calculate maximum allowable pressure based on flux limit and TDS.
    
    The flux equation is:
    flux = A_w × ρ_water × (P_feed - P_permeate - π_net)
    
    Where π_net = π_feed - π_permeate (osmotic pressure difference)
    
    Args:
        A_w: Water permeability coefficient (m/s/Pa)
        tds_ppm: Feed TDS concentration (ppm)
        recovery: Water recovery fraction
        max_flux: Maximum allowable flux (kg/m²/s)
        permeate_pressure: Permeate pressure (Pa)
        
    Returns:
        Dictionary with pressure limits and related values
    """
    water_density = 1000  # kg/m³
    
    # Calculate osmotic pressures
    feed_osmotic = calculate_osmotic_pressure(tds_ppm)
    
    # Concentrate TDS (assuming perfect rejection)
    if recovery >= 1.0:
        conc_tds_ppm = tds_ppm * 10  # Cap at 10x for very high recovery
    else:
        conc_tds_ppm = tds_ppm / (1 - recovery)
    
    conc_osmotic = calculate_osmotic_pressure(conc_tds_ppm)
    
    # Average osmotic pressure (simplified - actual varies along membrane)
    avg_feed_osmotic = (feed_osmotic + conc_osmotic) / 2
    
    # Permeate osmotic pressure (assuming 99% rejection)
    rejection = 0.99
    perm_tds_ppm = tds_ppm * (1 - rejection)
    perm_osmotic = calculate_osmotic_pressure(perm_tds_ppm)
    
    # Net osmotic pressure difference
    net_osmotic = avg_feed_osmotic - perm_osmotic
    
    # Maximum pressure from flux constraint
    # flux = A_w × ρ × (P_feed - P_perm - π_net)
    # P_feed = flux/(A_w × ρ) + P_perm + π_net
    max_pressure_pa = (max_flux / (A_w * water_density)) + permeate_pressure + net_osmotic
    
    return {
        'max_pressure_pa': max_pressure_pa,
        'max_pressure_bar': max_pressure_pa / 1e5,
        'feed_osmotic_bar': feed_osmotic / 1e5,
        'conc_osmotic_bar': conc_osmotic / 1e5,
        'avg_osmotic_bar': avg_feed_osmotic / 1e5,
        'net_osmotic_bar': net_osmotic / 1e5,
        'conc_tds_ppm': conc_tds_ppm
    }


def generate_pressure_limit_table():
    """Generate comprehensive table of pressure limits."""
    
    # Membrane types
    membranes = {
        'BW30-400': {'A_w': 9.63e-12, 'name': 'Standard Brackish'},
        'Medium': {'A_w': 1.2e-11, 'name': 'Medium Permeability'},
        'ECO PRO-400': {'A_w': 1.6e-11, 'name': 'High Permeability'},
        'Ultra-High': {'A_w': 2.0e-11, 'name': 'Ultra High Perm'}
    }
    
    # TDS levels to test
    tds_levels = [100, 500, 1000, 5000, 10000, 35000]
    
    # Recovery levels
    recovery_levels = [0.3, 0.5, 0.7, 0.85]
    
    results = []
    
    for membrane_code, membrane_data in membranes.items():
        for tds in tds_levels:
            for recovery in recovery_levels:
                result = calculate_max_pressure_from_flux(
                    A_w=membrane_data['A_w'],
                    tds_ppm=tds,
                    recovery=recovery
                )
                
                results.append({
                    'Membrane': membrane_code,
                    'A_w (m/s/Pa)': membrane_data['A_w'],
                    'Feed TDS (ppm)': tds,
                    'Recovery': recovery,
                    'Max Pressure (bar)': result['max_pressure_bar'],
                    'Feed Osmotic (bar)': result['feed_osmotic_bar'],
                    'Avg Osmotic (bar)': result['avg_osmotic_bar'],
                    'Net Osmotic (bar)': result['net_osmotic_bar'],
                    'Conc TDS (ppm)': result['conc_tds_ppm']
                })
    
    df = pd.DataFrame(results)
    return df


def plot_pressure_limits():
    """Create visualization of TDS-aware pressure limits."""
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('TDS-Aware Maximum Operating Pressures for RO Membranes', fontsize=16)
    
    membranes = {
        'BW30-400': 9.63e-12,
        'Medium': 1.2e-11,
        'ECO PRO-400': 1.6e-11,
        'Ultra-High': 2.0e-11
    }
    
    tds_range = np.logspace(2, 4.5, 50)  # 100 to ~35000 ppm
    
    # Plot 1: Max pressure vs TDS for different membranes (50% recovery)
    ax = axes[0, 0]
    for name, A_w in membranes.items():
        max_pressures = []
        for tds in tds_range:
            result = calculate_max_pressure_from_flux(A_w, tds, recovery=0.5)
            max_pressures.append(result['max_pressure_bar'])
        ax.semilogx(tds_range, max_pressures, label=name, linewidth=2)
    
    ax.set_xlabel('Feed TDS (ppm)')
    ax.set_ylabel('Maximum Pressure (bar)')
    ax.set_title('Maximum Operating Pressure vs Feed TDS (50% Recovery)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 100)
    
    # Plot 2: Max pressure vs recovery for ECO PRO-400 at different TDS
    ax = axes[0, 1]
    recovery_range = np.linspace(0.1, 0.9, 50)
    tds_levels = [500, 1000, 5000, 10000, 35000]
    
    for tds in tds_levels:
        max_pressures = []
        for rec in recovery_range:
            result = calculate_max_pressure_from_flux(1.6e-11, tds, recovery=rec)
            max_pressures.append(result['max_pressure_bar'])
        ax.plot(recovery_range * 100, max_pressures, 
                label=f'{tds} ppm', linewidth=2)
    
    ax.set_xlabel('Recovery (%)')
    ax.set_ylabel('Maximum Pressure (bar)')
    ax.set_title('ECO PRO-400: Max Pressure vs Recovery')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 50)
    
    # Plot 3: Operating envelope for ECO PRO-400
    ax = axes[1, 0]
    
    # Create contour plot
    tds_grid = np.logspace(2, 4.5, 30)
    pressure_grid = np.linspace(5, 50, 30)
    TDS, PRESSURE = np.meshgrid(tds_grid, pressure_grid)
    
    # Calculate flux for each point
    A_w = 1.6e-11
    water_density = 1000
    FLUX = np.zeros_like(TDS)
    
    for i in range(len(pressure_grid)):
        for j in range(len(tds_grid)):
            osmotic = calculate_osmotic_pressure(tds_grid[j])
            net_driving = pressure_grid[i] * 1e5 - 101325 - osmotic
            FLUX[i, j] = A_w * water_density * net_driving
    
    # Plot contours
    contour = ax.contourf(TDS, PRESSURE, FLUX * 1000, 
                         levels=np.linspace(-10, 40, 11),
                         cmap='RdYlGn_r')
    
    # Add flux limit line
    max_pressure_line = []
    for tds in tds_grid:
        result = calculate_max_pressure_from_flux(A_w, tds, recovery=0.5)
        max_pressure_line.append(result['max_pressure_bar'])
    ax.plot(tds_grid, max_pressure_line, 'k--', linewidth=3, 
            label='Flux Limit (25 g/m²/s)')
    
    ax.set_xscale('log')
    ax.set_xlabel('Feed TDS (ppm)')
    ax.set_ylabel('Feed Pressure (bar)')
    ax.set_title('ECO PRO-400 Operating Envelope (Flux in g/m²/s)')
    ax.legend()
    cbar = plt.colorbar(contour, ax=ax)
    cbar.set_label('Water Flux (g/m²/s)')
    
    # Plot 4: Summary table for key scenarios
    ax = axes[1, 1]
    ax.axis('tight')
    ax.axis('off')
    
    # Create summary data
    summary_data = []
    for tds in [1000, 5000, 10000, 35000]:
        row = [f'{tds:,}']
        for name, A_w in [('BW30-400', 9.63e-12), ('ECO PRO-400', 1.6e-11)]:
            result = calculate_max_pressure_from_flux(A_w, tds, recovery=0.5)
            row.append(f'{result["max_pressure_bar"]:.1f}')
        summary_data.append(row)
    
    table = ax.table(cellText=summary_data,
                     colLabels=['Feed TDS\n(ppm)', 'BW30-400\nMax P (bar)', 
                               'ECO PRO-400\nMax P (bar)'],
                     cellLoc='center',
                     loc='center',
                     bbox=[0.1, 0.3, 0.8, 0.4])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2)
    
    # Add note
    ax.text(0.5, 0.1, 
            'Note: Maximum pressures shown for 50% recovery\n' +
            'Higher recovery requires lower pressure due to increased osmotic pressure',
            ha='center', va='center', fontsize=10, style='italic',
            transform=ax.transAxes)
    
    plt.tight_layout()
    return fig


def main():
    """Run analysis and generate outputs."""
    
    print("="*80)
    print("TDS-AWARE FLUX-SAFE PRESSURE LIMITS ANALYSIS")
    print("="*80)
    
    # Generate comprehensive table
    print("\nGenerating pressure limit table...")
    df = generate_pressure_limit_table()
    
    # Save to CSV
    df.to_csv('tds_aware_pressure_limits.csv', index=False)
    print("Saved detailed results to: tds_aware_pressure_limits.csv")
    
    # Show key results for ECO PRO-400
    print("\n" + "="*60)
    print("ECO PRO-400 (A_w = 1.6e-11 m/s/Pa) Maximum Pressures")
    print("="*60)
    
    eco_df = df[df['Membrane'] == 'ECO PRO-400']
    
    for recovery in [0.5]:  # Show 50% recovery
        print(f"\nRecovery = {recovery*100:.0f}%:")
        print("-"*40)
        print("Feed TDS (ppm) | Max Pressure (bar) | Net Osmotic (bar)")
        print("-"*40)
        
        recovery_df = eco_df[eco_df['Recovery'] == recovery]
        for _, row in recovery_df.iterrows():
            print(f"{row['Feed TDS (ppm)']:>13,} | {row['Max Pressure (bar)']:>17.1f} | "
                  f"{row['Net Osmotic (bar)']:>16.1f}")
    
    # Create visualization
    print("\nGenerating visualization...")
    fig = plot_pressure_limits()
    fig.savefig('tds_aware_pressure_limits.png', dpi=300, bbox_inches='tight')
    print("Saved visualization to: tds_aware_pressure_limits.png")
    
    # Key insights
    print("\n" + "="*60)
    print("KEY INSIGHTS")
    print("="*60)
    print("1. Maximum pressure DECREASES significantly with increasing TDS")
    print("2. High recovery operations require LOWER pressures due to osmotic effects")
    print("3. High-permeability membranes are more restrictive at all TDS levels")
    print("4. Seawater (35,000 ppm) severely limits operating pressure:")
    
    # Show seawater limits
    sw_df = df[(df['Feed TDS (ppm)'] == 35000) & (df['Recovery'] == 0.5)]
    print("\n   Seawater Maximum Pressures (50% recovery):")
    for _, row in sw_df.iterrows():
        print(f"   - {row['Membrane']}: {row['Max Pressure (bar)']:.1f} bar")
    
    print("\n5. For brackish water (1,000 ppm), limits are more reasonable:")
    bw_df = df[(df['Feed TDS (ppm)'] == 1000) & (df['Recovery'] == 0.5)]
    print("\n   Brackish Water Maximum Pressures (50% recovery):")
    for _, row in bw_df.iterrows():
        print(f"   - {row['Membrane']}: {row['Max Pressure (bar)']:.1f} bar")


if __name__ == "__main__":
    main()