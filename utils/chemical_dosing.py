"""
Chemical dosing calculations for RO systems.

This module handles dynamic chemical dosing including:
- Antiscalant dosing based on scaling potential
- pH adjustment chemicals
- CIP chemical requirements
"""

import logging
from typing import Dict, Optional, List, Any
import numpy as np
from .phreeqc_client import PhreeqcROClient
from .scaling_prediction import get_scaling_severity

logger = logging.getLogger(__name__)


class ChemicalDosingCalculator:
    """Calculate chemical dosing for RO systems."""

    def __init__(self):
        """Initialize with PHREEQC client."""
        self.client = PhreeqcROClient()

    def calculate_antiscalant_dose(
        self,
        scaling_indices: Dict[str, float],
        feed_flow_m3h: float,
        membrane_type: str = 'BW',
        product: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate dynamic antiscalant dose based on scaling potential.

        Args:
            scaling_indices: Saturation indices from PHREEQC
            feed_flow_m3h: Feed flow rate in m3/h
            membrane_type: 'BW' for brackish or 'SW' for seawater
            product: Specific antiscalant product name

        Returns:
            Dict containing:
                - base_dose_mg_L: Base antiscalant dose
                - adjusted_dose_mg_L: Adjusted dose based on scaling
                - daily_consumption_kg: Daily chemical consumption
                - annual_cost_USD: Annual chemical cost
                - dosing_pump_settings: Pump configuration
        """
        # Find highest scaling severity
        max_severity = 0
        critical_scalant = None

        for mineral, si in scaling_indices.items():
            severity = get_scaling_severity(si)
            if severity > max_severity:
                max_severity = severity
                critical_scalant = mineral

        # Base dose by membrane type
        if membrane_type == 'SW':
            base_dose = 3.0  # mg/L - seawater typically needs less
        else:
            base_dose = 5.0  # mg/L - brackish water base dose

        # Adjust based on severity (0-1 scale)
        if max_severity < 0.3:
            dose_multiplier = 0.6  # Low scaling risk
        elif max_severity < 0.5:
            dose_multiplier = 1.0  # Moderate risk
        elif max_severity < 0.8:
            dose_multiplier = 1.5  # High risk
        else:
            dose_multiplier = 2.0  # Severe risk

        # Product-specific adjustments
        product_factors = {
            'Nalco PermaTreat PC-191': 1.0,
            'SUEZ Hypersperse MDC220': 0.9,  # More effective, needs less
            'Avista Vitec 3000': 1.1,
            'Generic': 1.2
        }

        product_factor = product_factors.get(product, 1.0) if product else 1.0

        # Calculate final dose
        adjusted_dose = base_dose * dose_multiplier * product_factor

        # Cap at maximum recommended dose
        max_dose = 10.0 if membrane_type == 'BW' else 8.0
        adjusted_dose = min(adjusted_dose, max_dose)

        # Calculate consumption
        daily_consumption_kg = adjusted_dose * feed_flow_m3h * 24 / 1000
        annual_consumption_kg = daily_consumption_kg * 365

        # Estimate cost (USD/kg)
        chemical_cost = 3.5  # Typical antiscalant cost
        annual_cost = annual_consumption_kg * chemical_cost

        # Dosing pump settings
        pump_capacity_Lh = feed_flow_m3h * adjusted_dose / 1000  # L/h of neat chemical
        pump_stroke_rate = min(pump_capacity_Lh / 0.1, 100)  # Assume 0.1 L/stroke max

        return {
            'base_dose_mg_L': base_dose,
            'adjusted_dose_mg_L': adjusted_dose,
            'dose_multiplier': dose_multiplier,
            'critical_scalant': critical_scalant,
            'max_severity_score': max_severity,
            'daily_consumption_kg': daily_consumption_kg,
            'annual_consumption_kg': annual_consumption_kg,
            'annual_cost_USD': annual_cost,
            'dosing_pump_settings': {
                'flow_rate_Lh': pump_capacity_Lh,
                'stroke_rate_percent': pump_stroke_rate,
                'injection_point': 'Before cartridge filters',
                'dilution_ratio': '1:10 recommended'
            }
        }

    def calculate_pH_adjustment_dose(
        self,
        feed_composition: Dict[str, float],
        current_pH: float,
        target_pH: float,
        feed_flow_m3h: float,
        chemical: str = 'auto'
    ) -> Dict[str, Any]:
        """
        Calculate pH adjustment chemical dose using PHREEQC.

        Args:
            feed_composition: Feed water composition in mg/L
            current_pH: Current feed pH
            target_pH: Target pH
            feed_flow_m3h: Feed flow rate
            chemical: Chemical to use ('NaOH', 'HCl', 'H2SO4', 'auto')

        Returns:
            Chemical dosing information
        """
        if abs(target_pH - current_pH) < 0.1:
            return {
                'chemical_type': 'None',
                'dose_mg_L': 0,
                'daily_consumption_kg': 0,
                'annual_cost_USD': 0
            }

        # Auto-select chemical
        if chemical == 'auto':
            if target_pH > current_pH:
                chemical = 'NaOH'
            else:
                # Choose based on sulfate levels
                sulfate = feed_composition.get('SO4-2', 0)
                chemical = 'H2SO4' if sulfate < 250 else 'HCl'

        # Calculate alkalinity for buffering estimation
        alkalinity = feed_composition.get('HCO3-', 0) + \
                    feed_composition.get('CO3-2', 0) * 60/61

        # Estimate buffering capacity (simplified)
        # Full implementation would use PHREEQC titration
        buffer_capacity = 0.5 + alkalinity / 100  # mmol/L/pH unit

        pH_change = abs(target_pH - current_pH)
        moles_per_L = pH_change * buffer_capacity / 1000

        # Calculate dose based on chemical
        chemical_doses = {
            'NaOH': {
                'dose_mg_L': moles_per_L * 40000,
                'mw': 40,
                'cost_per_kg': 0.35,
                'concentration': 0.5  # 50% solution typical
            },
            'HCl': {
                'dose_mg_L': moles_per_L * 36500,
                'mw': 36.5,
                'cost_per_kg': 0.20,
                'concentration': 0.32  # 32% solution typical
            },
            'H2SO4': {
                'dose_mg_L': moles_per_L * 49000,  # Provides 2 H+
                'mw': 98,
                'cost_per_kg': 0.10,
                'concentration': 0.93  # 93% solution typical
            },
            'Ca(OH)2': {
                'dose_mg_L': moles_per_L * 37000,  # Provides 2 OH-
                'mw': 74,
                'cost_per_kg': 0.15,
                'concentration': 1.0  # Dry powder
            }
        }

        chem_data = chemical_doses.get(chemical, chemical_doses['NaOH'])

        dose_mg_L = chem_data['dose_mg_L']

        # Calculate consumption
        daily_kg = dose_mg_L * feed_flow_m3h * 24 / 1000
        annual_kg = daily_kg * 365

        # Calculate solution volume needed
        solution_volume_Lh = dose_mg_L * feed_flow_m3h / (chem_data['concentration'] * 1000)

        return {
            'chemical_type': chemical,
            'dose_mg_L': dose_mg_L,
            'dose_as_product_mg_L': dose_mg_L / chem_data['concentration'],
            'daily_consumption_kg': daily_kg,
            'annual_consumption_kg': annual_kg,
            'annual_cost_USD': annual_kg * chem_data['cost_per_kg'],
            'dosing_pump_settings': {
                'flow_rate_Lh': solution_volume_Lh,
                'concentration_percent': chem_data['concentration'] * 100,
                'injection_point': 'After media filters' if target_pH > current_pH else 'Before media filters'
            },
            'safety_considerations': self._get_safety_notes(chemical)
        }

    def calculate_cip_chemicals(
        self,
        membrane_area_m2: float,
        cip_frequency_per_year: int,
        cip_type: str = 'standard',
        membrane_type: str = 'BW'
    ) -> Dict[str, Any]:
        """
        Calculate CIP chemical requirements.

        Args:
            membrane_area_m2: Total membrane area
            cip_frequency_per_year: Number of CIPs per year
            cip_type: 'standard', 'enhanced', 'gentle'
            membrane_type: 'BW' or 'SW'

        Returns:
            CIP chemical requirements and costs
        """
        # CIP volume calculation (40-60 L per 8" vessel typical)
        # Assume average 50 L per 7 m2 of membrane
        cip_volume_L = membrane_area_m2 * 50 / 7

        # Chemical concentrations by CIP type
        cip_protocols = {
            'standard': {
                'alkaline': {
                    'NaOH_percent': 0.1,  # 0.1% NaOH
                    'EDTA_percent': 0.1,   # Chelating agent
                    'SDS_percent': 0.025,  # Surfactant
                    'temperature_C': 35,
                    'duration_min': 60,
                    'pH': 11.5
                },
                'acidic': {
                    'citric_acid_percent': 2.0,
                    'temperature_C': 35,
                    'duration_min': 60,
                    'pH': 3.5
                }
            },
            'enhanced': {
                'alkaline': {
                    'NaOH_percent': 0.2,
                    'EDTA_percent': 0.2,
                    'SDS_percent': 0.05,
                    'temperature_C': 40,
                    'duration_min': 90,
                    'pH': 12.0
                },
                'acidic': {
                    'citric_acid_percent': 3.0,
                    'HCl_percent': 0.2,
                    'temperature_C': 40,
                    'duration_min': 90,
                    'pH': 2.5
                }
            },
            'gentle': {
                'alkaline': {
                    'NaOH_percent': 0.05,
                    'EDTA_percent': 0.05,
                    'temperature_C': 30,
                    'duration_min': 45,
                    'pH': 10.5
                },
                'acidic': {
                    'citric_acid_percent': 1.0,
                    'temperature_C': 30,
                    'duration_min': 45,
                    'pH': 4.0
                }
            }
        }

        protocol = cip_protocols[cip_type]

        # Calculate chemical consumption per CIP
        chemicals_per_cip = {}

        # Alkaline cleaning chemicals
        alk = protocol['alkaline']
        chemicals_per_cip['NaOH'] = cip_volume_L * alk.get('NaOH_percent', 0) / 100
        chemicals_per_cip['EDTA'] = cip_volume_L * alk.get('EDTA_percent', 0) / 100
        chemicals_per_cip['SDS'] = cip_volume_L * alk.get('SDS_percent', 0) / 100

        # Acidic cleaning chemicals
        acid = protocol['acidic']
        chemicals_per_cip['citric_acid'] = cip_volume_L * acid.get('citric_acid_percent', 0) / 100
        chemicals_per_cip['HCl'] = cip_volume_L * acid.get('HCl_percent', 0) / 100

        # Annual consumption
        annual_consumption = {
            chem: amount * cip_frequency_per_year
            for chem, amount in chemicals_per_cip.items()
        }

        # Chemical costs (USD/kg)
        chemical_costs = {
            'NaOH': 0.35,
            'EDTA': 2.50,
            'SDS': 1.20,
            'citric_acid': 0.80,
            'HCl': 0.20
        }

        # Calculate annual costs
        annual_costs = {
            chem: annual_consumption[chem] * chemical_costs.get(chem, 1.0)
            for chem in annual_consumption
        }

        total_annual_cost = sum(annual_costs.values())

        # CIP system requirements
        cip_tank_volume = cip_volume_L * 1.2  # 20% safety margin
        heating_power_kW = cip_volume_L * 4.2 * 15 / (60 * 60)  # Heat from 20 to 35°C in 1 hour

        return {
            'cip_volume_L': cip_volume_L,
            'cip_frequency_per_year': cip_frequency_per_year,
            'chemicals_per_cip_kg': chemicals_per_cip,
            'annual_consumption_kg': annual_consumption,
            'annual_costs_USD': annual_costs,
            'total_annual_cost_USD': total_annual_cost,
            'cip_protocol': protocol,
            'system_requirements': {
                'tank_volume_L': cip_tank_volume,
                'heating_power_kW': heating_power_kW,
                'pump_flow_m3h': cip_volume_L / 1000 * 2,  # 2 turnovers per hour
                'pump_pressure_bar': 3,  # Low pressure for CIP
            },
            'waste_disposal': {
                'volume_per_cip_L': cip_volume_L * 1.5,  # Include rinse water
                'annual_waste_L': cip_volume_L * 1.5 * cip_frequency_per_year,
                'neutralization_required': True,
                'typical_disposal_cost_USD_m3': 5.0
            }
        }

    def calculate_total_chemical_costs(
        self,
        antiscalant_dose_mg_L: float,
        pH_adjustment_dose_mg_L: float,
        feed_flow_m3h: float,
        membrane_area_m2: float,
        cip_frequency_per_year: int,
        operating_hours_per_year: float = 8760
    ) -> Dict[str, Any]:
        """
        Calculate total chemical costs for RO system.

        Args:
            antiscalant_dose_mg_L: Antiscalant dose
            pH_adjustment_dose_mg_L: pH adjustment chemical dose
            feed_flow_m3h: Feed flow rate
            membrane_area_m2: Total membrane area
            cip_frequency_per_year: CIP frequency
            operating_hours_per_year: Annual operating hours

        Returns:
            Total chemical costs breakdown
        """
        # Annual water production
        annual_production_m3 = feed_flow_m3h * operating_hours_per_year

        # Antiscalant costs
        antiscalant_kg = antiscalant_dose_mg_L * annual_production_m3 / 1000
        antiscalant_cost = antiscalant_kg * 3.5  # USD/kg

        # pH adjustment costs
        pH_chemical_kg = pH_adjustment_dose_mg_L * annual_production_m3 / 1000
        pH_cost = pH_chemical_kg * 0.25  # Average cost

        # CIP costs
        cip_result = self.calculate_cip_chemicals(
            membrane_area_m2, cip_frequency_per_year
        )
        cip_cost = cip_result['total_annual_cost_USD']

        # Other chemicals (biocide, dechlorination, etc.)
        other_chemicals_cost = annual_production_m3 * 0.002  # USD/m3 estimate

        # Total costs
        total_annual_cost = antiscalant_cost + pH_cost + cip_cost + other_chemicals_cost
        specific_cost_USD_m3 = total_annual_cost / annual_production_m3

        return {
            'annual_costs_USD': {
                'antiscalant': antiscalant_cost,
                'pH_adjustment': pH_cost,
                'cip_chemicals': cip_cost,
                'other_chemicals': other_chemicals_cost,
                'total': total_annual_cost
            },
            'specific_cost_USD_m3': specific_cost_USD_m3,
            'cost_breakdown_percent': {
                'antiscalant': antiscalant_cost / total_annual_cost * 100,
                'pH_adjustment': pH_cost / total_annual_cost * 100,
                'cip_chemicals': cip_cost / total_annual_cost * 100,
                'other_chemicals': other_chemicals_cost / total_annual_cost * 100
            },
            'annual_consumption_kg': {
                'antiscalant': antiscalant_kg,
                'pH_chemical': pH_chemical_kg,
                'cip_chemicals': sum(cip_result['annual_consumption_kg'].values())
            }
        }

    def _get_safety_notes(self, chemical: str) -> List[str]:
        """Get safety notes for chemical handling."""
        safety_notes = {
            'NaOH': [
                'Highly caustic - use PPE',
                'Store in ventilated area',
                'Incompatible with acids',
                'Eye wash station required'
            ],
            'HCl': [
                'Corrosive - use acid-resistant materials',
                'Fuming - ensure ventilation',
                'Store separately from bases',
                'Spill kit required'
            ],
            'H2SO4': [
                'Concentrated acid - extreme caution',
                'Always add acid to water',
                'Heat generated during dilution',
                'Secondary containment required'
            ],
            'Ca(OH)2': [
                'Dust hazard - use respirator',
                'Slurry preparation needed',
                'Can cause scaling if overdosed'
            ]
        }
        return safety_notes.get(chemical, ['Follow SDS guidelines'])