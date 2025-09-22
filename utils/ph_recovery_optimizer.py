"""
pH Recovery Optimizer using PHREEQC.

This module finds optimal pH for achieving target recovery in RO systems
using PHREEQC's thermodynamic capabilities.
"""

import logging
from typing import Dict, Optional, List, Tuple, Any
import numpy as np
from .phreeqc_client import PhreeqcROClient

logger = logging.getLogger(__name__)


class pHRecoveryOptimizer:
    """Optimize pH for maximum recovery using PHREEQC."""

    def __init__(self):
        """Initialize the optimizer with PHREEQC client."""
        self.client = PhreeqcROClient()

    def find_pH_for_target_recovery(
        self,
        feed_composition: Dict[str, float],
        target_recovery: float,
        temperature_c: float = 25.0,
        use_antiscalant: bool = True,
        pH_range: Tuple[float, float] = (6.0, 10.0),
        pH_step: float = 0.5
    ) -> Dict[str, Any]:
        """
        Find optimal pH to achieve target recovery.

        Args:
            feed_composition: Feed water ion concentrations in mg/L
            target_recovery: Target recovery fraction (0-1)
            temperature_c: Temperature in Celsius
            use_antiscalant: Whether antiscalant is used
            pH_range: pH search range (min, max)
            pH_step: pH increment for search

        Returns:
            Dict containing:
                - achievable: Whether target recovery is achievable
                - optimal_pH: pH that achieves target with minimum chemical
                - chemical_type: Type of chemical needed (NaOH, HCl, H2SO4)
                - chemical_dose_mg_L: Required chemical dose
                - limiting_factor: What limits recovery at optimal pH
                - pH_scan_results: Results at each pH tested
        """
        results = []

        # Define SI limits based on antiscalant use
        if use_antiscalant:
            si_limits = {
                'Calcite': 1.8,
                'Aragonite': 1.8,
                'Gypsum': np.log10(2.3),
                'Anhydrite': np.log10(2.3),
                'Barite': 0.0,
                'Celestite': np.log10(1.15),
                'Fluorite': 0.0,
                'SiO2(a)': 0.0,
                'Chalcedony': -0.2,
                'Quartz': -0.5,
                'Brucite': 0.5,
            }
        else:
            si_limits = {
                'Calcite': 0.5,
                'Aragonite': 0.5,
                'Gypsum': 0.0,
                'Anhydrite': 0.0,
                'Barite': -0.3,
                'Celestite': -0.3,
                'Fluorite': -0.3,
                'SiO2(a)': -0.3,
                'Chalcedony': -0.5,
                'Quartz': -0.7,
                'Brucite': 0.0,
            }

        # Get baseline pH and composition
        baseline_result = self.client.calculate_scaling_potential(
            feed_composition, 0.0, temperature_c, pH_range[0]
        )
        baseline_pH = baseline_result.get('actual_ph', pH_range[0])

        logger.info(f"Baseline feed pH: {baseline_pH:.2f}")
        logger.info(f"Target recovery: {target_recovery*100:.1f}%")

        # Test pH values in range
        for test_pH in np.arange(pH_range[0], pH_range[1] + pH_step, pH_step):
            # Calculate scaling at this pH and target recovery
            # Using maintain_pH to keep pH constant during concentration
            scaling_result = self.client.calculate_scaling_potential(
                feed_composition,
                target_recovery,
                temperature_c,
                test_pH,
                maintain_pH=True  # Critical: maintain pH during concentration
            )

            # Check if all SI limits are met
            achievable = True
            limiting_factor = None
            max_si_violation = 0

            for mineral, si in scaling_result['saturation_indices'].items():
                if mineral in si_limits:
                    if si > si_limits[mineral]:
                        achievable = False
                        violation = si - si_limits[mineral]
                        if violation > max_si_violation:
                            max_si_violation = violation
                            limiting_factor = f"{mineral} (SI: {si:.2f} > limit: {si_limits[mineral]:.2f})"

            # Calculate chemical requirement
            chemical_type, dose_mg_L = self._calculate_chemical_dose(
                baseline_pH, test_pH, feed_composition, temperature_c
            )

            results.append({
                'pH': test_pH,
                'achievable': achievable,
                'chemical_type': chemical_type,
                'chemical_dose_mg_L': dose_mg_L,
                'limiting_factor': limiting_factor,
                'max_si_violation': max_si_violation,
                'saturation_indices': scaling_result['saturation_indices']
            })

            logger.debug(f"pH {test_pH:.1f}: {'OK' if achievable else 'FAIL'} "
                        f"({chemical_type}: {dose_mg_L:.1f} mg/L) - {limiting_factor}")

        # Find optimal pH (achievable with minimum chemical dose)
        achievable_results = [r for r in results if r['achievable']]

        if not achievable_results:
            # Target recovery not achievable in pH range
            # Find the pH with minimum SI violation
            best_fail = min(results, key=lambda x: x['max_si_violation'])
            return {
                'achievable': False,
                'optimal_pH': best_fail['pH'],
                'chemical_type': best_fail['chemical_type'],
                'chemical_dose_mg_L': best_fail['chemical_dose_mg_L'],
                'limiting_factor': best_fail['limiting_factor'],
                'max_achievable_recovery': self._find_max_recovery_at_pH(
                    feed_composition, best_fail['pH'], temperature_c, use_antiscalant
                ),
                'pH_scan_results': results
            }

        # Find optimal among achievable (minimum chemical use)
        optimal = min(achievable_results, key=lambda x: abs(x['chemical_dose_mg_L']))

        return {
            'achievable': True,
            'optimal_pH': optimal['pH'],
            'chemical_type': optimal['chemical_type'],
            'chemical_dose_mg_L': optimal['chemical_dose_mg_L'],
            'limiting_factor': optimal['limiting_factor'],
            'saturation_indices': optimal['saturation_indices'],
            'pH_scan_results': results
        }

    def _calculate_chemical_dose(
        self,
        current_pH: float,
        target_pH: float,
        feed_composition: Dict[str, float],
        temperature_c: float
    ) -> Tuple[str, float]:
        """
        Calculate chemical dose required for pH adjustment.

        Args:
            current_pH: Current feed pH
            target_pH: Target pH
            feed_composition: Feed water composition
            temperature_c: Temperature

        Returns:
            Tuple of (chemical_type, dose_mg_L)
        """
        if abs(target_pH - current_pH) < 0.1:
            return ("None", 0.0)

        # Estimate based on typical buffering capacity
        # This is simplified - full implementation would use PHREEQC titration
        alkalinity_mg_L = feed_composition.get('HCO3-', 0) + \
                          feed_composition.get('CO3-2', 0) * 60/61

        # Buffer capacity estimation (mmol/L/pH unit)
        buffer_capacity = 0.5 + alkalinity_mg_L / 100  # Simplified

        pH_change = target_pH - current_pH

        if pH_change > 0:
            # Need to increase pH - use NaOH
            moles_needed = abs(pH_change) * buffer_capacity / 1000  # mol/L
            dose_mg_L = moles_needed * 40000  # NaOH MW = 40 g/mol
            return ("NaOH", dose_mg_L)
        else:
            # Need to decrease pH - compare HCl vs H2SO4
            moles_needed = abs(pH_change) * buffer_capacity / 1000  # mol/L

            # Check if sulfate addition is acceptable
            current_sulfate = feed_composition.get('SO4-2', 0)

            if current_sulfate < 250:  # If low sulfate, H2SO4 is option
                # H2SO4 provides 2 H+ per molecule
                dose_mg_L_h2so4 = moles_needed * 98000 / 2  # H2SO4 MW = 98 g/mol
                dose_mg_L_hcl = moles_needed * 36500  # HCl MW = 36.5 g/mol

                if dose_mg_L_h2so4 < dose_mg_L_hcl * 0.7:  # H2SO4 more economical
                    return ("H2SO4", dose_mg_L_h2so4)
                else:
                    return ("HCl", dose_mg_L_hcl)
            else:
                # High sulfate - use HCl only
                dose_mg_L = moles_needed * 36500
                return ("HCl", dose_mg_L)

    def _find_max_recovery_at_pH(
        self,
        feed_composition: Dict[str, float],
        pH: float,
        temperature_c: float,
        use_antiscalant: bool
    ) -> float:
        """
        Find maximum achievable recovery at a specific pH.

        Args:
            feed_composition: Feed water composition
            pH: Fixed pH value
            temperature_c: Temperature
            use_antiscalant: Whether antiscalant is used

        Returns:
            Maximum recovery fraction
        """
        # This would use binary search similar to find_maximum_recovery
        # but with pH held constant
        # For now, return estimate
        result = self.client.find_maximum_recovery(
            feed_composition,
            temperature_c,
            pH,
            use_antiscalant
        )
        return result['maximum_recovery']

    def compare_pH_chemicals(
        self,
        feed_composition: Dict[str, float],
        target_recovery: float,
        temperature_c: float = 25.0,
        use_antiscalant: bool = True
    ) -> Dict[str, Any]:
        """
        Compare different pH adjustment chemicals.

        Args:
            feed_composition: Feed water composition
            target_recovery: Target recovery
            temperature_c: Temperature
            use_antiscalant: Whether antiscalant is used

        Returns:
            Comparison of chemical options
        """
        # Get optimal pH first
        optimal_result = self.find_pH_for_target_recovery(
            feed_composition, target_recovery, temperature_c, use_antiscalant
        )

        if not optimal_result['achievable']:
            return {
                'achievable': False,
                'message': f"Target recovery {target_recovery*100:.1f}% not achievable",
                'max_achievable': optimal_result.get('max_achievable_recovery', 0) * 100
            }

        optimal_pH = optimal_result['optimal_pH']

        # Get baseline pH
        baseline_result = self.client.calculate_scaling_potential(
            feed_composition, 0.0, temperature_c, 7.5
        )
        baseline_pH = baseline_result.get('actual_ph', 7.5)

        chemicals_compared = {}

        if optimal_pH > baseline_pH:
            # Compare base options
            for chemical in ['NaOH', 'Ca(OH)2', 'Na2CO3']:
                dose = self._estimate_dose_for_chemical(
                    chemical, baseline_pH, optimal_pH, feed_composition
                )
                cost = self._estimate_chemical_cost(chemical, dose)
                chemicals_compared[chemical] = {
                    'dose_mg_L': dose,
                    'cost_USD_m3': cost,
                    'pros': self._get_chemical_pros(chemical),
                    'cons': self._get_chemical_cons(chemical)
                }
        else:
            # Compare acid options
            for chemical in ['HCl', 'H2SO4', 'CO2']:
                dose = self._estimate_dose_for_chemical(
                    chemical, baseline_pH, optimal_pH, feed_composition
                )
                cost = self._estimate_chemical_cost(chemical, dose)
                chemicals_compared[chemical] = {
                    'dose_mg_L': dose,
                    'cost_USD_m3': cost,
                    'pros': self._get_chemical_pros(chemical),
                    'cons': self._get_chemical_cons(chemical)
                }

        return {
            'achievable': True,
            'optimal_pH': optimal_pH,
            'baseline_pH': baseline_pH,
            'chemicals_compared': chemicals_compared,
            'recommendation': min(chemicals_compared.items(),
                                key=lambda x: x[1]['cost_USD_m3'])[0]
        }

    def _estimate_dose_for_chemical(
        self,
        chemical: str,
        current_pH: float,
        target_pH: float,
        feed_composition: Dict[str, float]
    ) -> float:
        """Estimate dose for specific chemical."""
        # Simplified estimation
        alkalinity = feed_composition.get('HCO3-', 0)
        buffer_capacity = 0.5 + alkalinity / 100
        pH_change = abs(target_pH - current_pH)
        moles_needed = pH_change * buffer_capacity / 1000

        doses = {
            'NaOH': moles_needed * 40000,
            'Ca(OH)2': moles_needed * 74000 / 2,
            'Na2CO3': moles_needed * 106000,
            'HCl': moles_needed * 36500,
            'H2SO4': moles_needed * 98000 / 2,
            'CO2': moles_needed * 44000
        }
        return doses.get(chemical, 0)

    def _estimate_chemical_cost(self, chemical: str, dose_mg_L: float) -> float:
        """Estimate chemical cost in USD/m3."""
        # Typical chemical costs (USD/kg)
        costs = {
            'NaOH': 0.35,
            'Ca(OH)2': 0.15,
            'Na2CO3': 0.25,
            'HCl': 0.20,
            'H2SO4': 0.10,
            'CO2': 0.30
        }
        cost_per_kg = costs.get(chemical, 0.25)
        return dose_mg_L * cost_per_kg / 1000

    def _get_chemical_pros(self, chemical: str) -> List[str]:
        """Get advantages of chemical."""
        pros = {
            'NaOH': ['Fast acting', 'Precise control', 'No calcium added'],
            'Ca(OH)2': ['Low cost', 'Adds beneficial calcium'],
            'Na2CO3': ['Stable', 'Adds alkalinity buffer'],
            'HCl': ['Fast acting', 'No sulfate addition'],
            'H2SO4': ['Very low cost', 'Concentrated'],
            'CO2': ['No dissolved solids added', 'Easy to control']
        }
        return pros.get(chemical, [])

    def _get_chemical_cons(self, chemical: str) -> List[str]:
        """Get disadvantages of chemical."""
        cons = {
            'NaOH': ['Higher cost', 'Adds sodium'],
            'Ca(OH)2': ['Can increase scaling', 'Slower dissolution'],
            'Na2CO3': ['Adds sodium', 'Can affect scaling'],
            'HCl': ['Corrosive', 'Adds chloride'],
            'H2SO4': ['Adds sulfate', 'Can promote gypsum scaling'],
            'CO2': ['Requires special equipment', 'pH limited to ~6']
        }
        return cons.get(chemical, [])