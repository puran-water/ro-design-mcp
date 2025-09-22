"""
pH Parameter Sweep Utility for RO Systems.

Provides comprehensive parameter sweep functionality for pH optimization,
using WaterTAP's parameter sweep utilities for systematic analysis.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List, Tuple
import logging
from datetime import datetime
import json

# Note: This implementation doesn't depend on WaterTAP's parameter sweep
# It provides its own comprehensive sweep functionality
from .ph_recovery_optimizer import pHRecoveryOptimizer
from .logging_config import get_configured_logger

logger = get_configured_logger(__name__)


class pHParameterSweep:
    """
    Comprehensive pH parameter sweep for RO system optimization.

    Features:
    - Sweep pH and recovery combinations
    - Calculate chemical costs for each scenario
    - Generate optimization tables
    - Export results in multiple formats
    """

    def __init__(self, ph_optimizer: Optional[pHRecoveryOptimizer] = None):
        """Initialize pH parameter sweep utility."""
        self.ph_optimizer = ph_optimizer or pHRecoveryOptimizer()
        self.chemical_costs = {
            'NaOH': 0.35,    # $/kg for 50% solution
            'HCl': 0.17,     # $/kg for 37% solution
            'H2SO4': 0.10    # $/kg for 98% solution
        }

    def run_comprehensive_sweep(
        self,
        feed_flow_m3h: float,
        ion_composition: Dict[str, float],
        temperature_c: float = 25.0,
        ph_range: Tuple[float, float] = (6.0, 10.5),
        ph_step: float = 0.5,
        recovery_range: Tuple[float, float] = (0.60, 0.90),
        recovery_step: float = 0.05,
        use_antiscalant: bool = True
    ) -> pd.DataFrame:
        """
        Run comprehensive pH-recovery parameter sweep.

        Args:
            feed_flow_m3h: Feed flow rate in m³/h
            ion_composition: Ion concentrations in mg/L
            temperature_c: Feed temperature in °C
            ph_range: pH range to sweep (min, max)
            ph_step: pH increment
            recovery_range: Recovery range to sweep (min, max)
            recovery_step: Recovery increment
            use_antiscalant: Whether to assume antiscalant use

        Returns:
            DataFrame with sweep results
        """

        logger.info(f"Starting pH-recovery parameter sweep...")
        logger.info(f"  pH range: {ph_range[0]:.1f} to {ph_range[1]:.1f} (step {ph_step:.1f})")
        logger.info(f"  Recovery range: {recovery_range[0]:.1%} to {recovery_range[1]:.1%} (step {recovery_step:.2%})")

        # Generate parameter combinations
        ph_values = np.arange(ph_range[0], ph_range[1] + ph_step/2, ph_step)
        recovery_values = np.arange(recovery_range[0], recovery_range[1] + recovery_step/2, recovery_step)

        results = []
        total_runs = len(ph_values) * len(recovery_values)
        run_count = 0

        for target_ph in ph_values:
            for target_recovery in recovery_values:
                run_count += 1
                if run_count % 10 == 0:
                    logger.info(f"  Progress: {run_count}/{total_runs} combinations evaluated...")

                try:
                    # Test recovery at specific pH
                    result = self.ph_optimizer.test_recovery_at_pH(
                        feed_composition=ion_composition,
                        target_recovery=target_recovery,
                        target_ph=target_ph,
                        temperature_c=temperature_c,
                        use_antiscalant=use_antiscalant
                    )

                    # Calculate annual chemical consumption
                    chemical_kg_year = 0
                    annual_chemical_cost = 0

                    if result['chemical_dose_mg_L'] > 0:
                        # kg/year = (mg/L) * (m³/h) * (8760 h/year) * (1 kg/1e6 mg) * (1000 L/m³)
                        chemical_kg_year = result['chemical_dose_mg_L'] * feed_flow_m3h * 8760 / 1000
                        annual_chemical_cost = chemical_kg_year * self.chemical_costs.get(
                            result['chemical_type'], 0.20
                        )

                    # Store results
                    results.append({
                        'Target_pH': target_ph,
                        'Target_Recovery': target_recovery,
                        'Achievable': result['achievable'],
                        'Max_Recovery': result.get('max_recovery', target_recovery),
                        'Chemical_Type': result.get('chemical_type', 'None'),
                        'Dose_mg_L': result.get('chemical_dose_mg_L', 0),
                        'Chemical_kg_year': chemical_kg_year,
                        'Annual_Cost_USD': annual_chemical_cost,
                        'Limiting_Factor': result.get('limiting_factor', ''),
                        'Critical_SI': result.get('critical_saturation_index', {})
                    })

                except Exception as e:
                    logger.warning(f"Failed at pH {target_ph:.1f}, recovery {target_recovery:.1%}: {e}")
                    results.append({
                        'Target_pH': target_ph,
                        'Target_Recovery': target_recovery,
                        'Achievable': False,
                        'Error': str(e)
                    })

        # Convert to DataFrame
        df = pd.DataFrame(results)

        logger.info(f"Sweep completed: {len(df)} combinations evaluated")
        logger.info(f"  Achievable scenarios: {df['Achievable'].sum()}")
        logger.info(f"  Failed scenarios: {(~df['Achievable']).sum()}")

        return df

    def find_optimal_pH(
        self,
        df_sweep: pd.DataFrame,
        target_recovery: float,
        tolerance: float = 0.02
    ) -> Dict[str, Any]:
        """
        Find optimal pH for target recovery from sweep results.

        Args:
            df_sweep: DataFrame from run_comprehensive_sweep
            target_recovery: Desired recovery fraction
            tolerance: Recovery tolerance (±)

        Returns:
            Optimal pH configuration
        """

        # Filter achievable scenarios within tolerance
        achievable = df_sweep[
            (df_sweep['Achievable']) &
            (df_sweep['Max_Recovery'] >= target_recovery - tolerance) &
            (df_sweep['Max_Recovery'] <= target_recovery + tolerance)
        ]

        if achievable.empty:
            # Find closest achievable recovery
            achievable = df_sweep[df_sweep['Achievable']]
            if not achievable.empty:
                closest = achievable.iloc[(achievable['Max_Recovery'] - target_recovery).abs().argsort()[:1]]
                return {
                    'found': False,
                    'message': f"Target recovery {target_recovery:.1%} not achievable",
                    'closest_recovery': float(closest['Max_Recovery'].iloc[0]),
                    'recommended_pH': float(closest['Target_pH'].iloc[0]),
                    'annual_cost': float(closest['Annual_Cost_USD'].iloc[0])
                }
            else:
                return {
                    'found': False,
                    'message': "No achievable scenarios found"
                }

        # Find minimum cost option
        optimal = achievable.loc[achievable['Annual_Cost_USD'].idxmin()]

        return {
            'found': True,
            'optimal_pH': float(optimal['Target_pH']),
            'recovery': float(optimal['Max_Recovery']),
            'chemical': optimal['Chemical_Type'],
            'dose_mg_L': float(optimal['Dose_mg_L']),
            'annual_cost_USD': float(optimal['Annual_Cost_USD']),
            'chemical_kg_year': float(optimal['Chemical_kg_year'])
        }

    def generate_optimization_table(
        self,
        df_sweep: pd.DataFrame,
        recovery_targets: List[float]
    ) -> pd.DataFrame:
        """
        Generate optimization table for specific recovery targets.

        Args:
            df_sweep: DataFrame from run_comprehensive_sweep
            recovery_targets: List of target recoveries

        Returns:
            DataFrame with optimal pH for each target
        """

        optimization_results = []

        for target in recovery_targets:
            optimal = self.find_optimal_pH(df_sweep, target)

            if optimal['found']:
                optimization_results.append({
                    'Target_Recovery_%': target * 100,
                    'Optimal_pH': optimal['optimal_pH'],
                    'Chemical': optimal['chemical'],
                    'Dose_mg/L': optimal['dose_mg_L'],
                    'Annual_Cost_USD': optimal['annual_cost_USD'],
                    'Status': 'Optimal'
                })
            else:
                optimization_results.append({
                    'Target_Recovery_%': target * 100,
                    'Status': optimal.get('message', 'Not achievable'),
                    'Recommended_Recovery_%': optimal.get('closest_recovery', 0) * 100 if 'closest_recovery' in optimal else None
                })

        return pd.DataFrame(optimization_results)

    def export_results(
        self,
        df_sweep: pd.DataFrame,
        output_prefix: str = "ph_sweep"
    ) -> Dict[str, str]:
        """
        Export sweep results to multiple formats.

        Args:
            df_sweep: DataFrame with sweep results
            output_prefix: Prefix for output files

        Returns:
            Dictionary of created file paths
        """

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        files = {}

        # CSV export
        csv_path = f"{output_prefix}_{timestamp}.csv"
        df_sweep.to_csv(csv_path, index=False)
        files['csv'] = csv_path
        logger.info(f"Exported CSV: {csv_path}")

        # Excel export with formatting
        try:
            excel_path = f"{output_prefix}_{timestamp}.xlsx"
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                df_sweep.to_excel(writer, sheet_name='Sweep_Results', index=False)

                # Add pivot table sheet
                pivot = df_sweep.pivot_table(
                    values='Annual_Cost_USD',
                    index='Target_Recovery',
                    columns='Target_pH',
                    aggfunc='first'
                )
                pivot.to_excel(writer, sheet_name='Cost_Matrix')

            files['excel'] = excel_path
            logger.info(f"Exported Excel: {excel_path}")
        except ImportError:
            logger.warning("openpyxl not available, skipping Excel export")

        # JSON export for programmatic use
        json_path = f"{output_prefix}_{timestamp}.json"
        df_sweep.to_json(json_path, orient='records', indent=2)
        files['json'] = json_path
        logger.info(f"Exported JSON: {json_path}")

        return files

    def visualize_sweep_heatmap(
        self,
        df_sweep: pd.DataFrame,
        value_column: str = 'Annual_Cost_USD'
    ) -> str:
        """
        Create ASCII heatmap of sweep results for CLI display.

        Args:
            df_sweep: DataFrame with sweep results
            value_column: Column to visualize

        Returns:
            ASCII heatmap string
        """

        # Pivot for heatmap
        pivot = df_sweep.pivot_table(
            values=value_column,
            index='Target_Recovery',
            columns='Target_pH',
            aggfunc='first'
        )

        # Create ASCII visualization
        output = []
        output.append(f"\n{value_column} Heatmap")
        output.append("=" * 60)

        # Header
        header = "Recovery\\pH  "
        for ph in pivot.columns:
            header += f"{ph:6.1f}"
        output.append(header)
        output.append("-" * 60)

        # Data rows
        for recovery in pivot.index:
            row = f"{recovery:8.1%}    "
            for ph in pivot.columns:
                value = pivot.loc[recovery, ph]
                if pd.isna(value):
                    row += "     -"
                elif value_column == 'Annual_Cost_USD':
                    row += f"{value:6.0f}" if value < 99999 else " >100k"
                else:
                    row += f"{value:6.1f}"
            output.append(row)

        output.append("=" * 60)
        return "\n".join(output)


# Convenience function for direct use
def run_ph_recovery_sweep(
    feed_flow_m3h: float,
    ion_composition: Dict[str, float],
    temperature_c: float = 25.0,
    target_recovery: Optional[float] = None,
    export: bool = True
) -> Dict[str, Any]:
    """
    Run pH-recovery parameter sweep with automatic optimization.

    Args:
        feed_flow_m3h: Feed flow rate in m³/h
        ion_composition: Ion concentrations in mg/L
        temperature_c: Feed temperature in °C
        target_recovery: Optional specific recovery target
        export: Whether to export results to files

    Returns:
        Dictionary with sweep results and recommendations
    """

    sweep = pHParameterSweep()

    # Run comprehensive sweep
    df_results = sweep.run_comprehensive_sweep(
        feed_flow_m3h=feed_flow_m3h,
        ion_composition=ion_composition,
        temperature_c=temperature_c
    )

    result = {
        'sweep_data': df_results,
        'summary': {
            'total_scenarios': len(df_results),
            'achievable': df_results['Achievable'].sum(),
            'max_recovery': df_results['Max_Recovery'].max(),
            'min_cost_scenario': df_results.loc[df_results['Annual_Cost_USD'].idxmin()].to_dict()
                if df_results['Achievable'].any() else None
        }
    }

    # Find optimal for specific target
    if target_recovery:
        optimal = sweep.find_optimal_pH(df_results, target_recovery)
        result['optimal_for_target'] = optimal

    # Generate optimization table for common targets
    common_targets = [0.70, 0.75, 0.80, 0.85, 0.90]
    result['optimization_table'] = sweep.generate_optimization_table(
        df_results,
        common_targets
    )

    # Export if requested
    if export:
        result['exported_files'] = sweep.export_results(df_results)

    # Add visualization
    result['heatmap'] = sweep.visualize_sweep_heatmap(df_results)

    return result