"""
Economic default values for RO system simulation.

All defaults are aligned with WaterTAP standard values and examples.
References:
- WaterTAPCostingBlockData defaults
- WaterTAP RO and pretreatment examples
- Ion exchange and chemical costs from WaterTAP case studies
"""

from typing import Dict, Any


def get_default_economic_params(membrane_type: str = "brackish") -> Dict[str, Any]:
    """
    Get WaterTAP-aligned default economic parameters.
    
    Args:
        membrane_type: Type of membrane ("brackish" or "seawater")
        
    Returns:
        Dictionary of economic parameters with WaterTAP defaults
    """
    return {
        # Core WaterTAP costing defaults
        "wacc": 0.093,  # Weighted Average Cost of Capital (9.3%)
        "plant_lifetime_years": 30,  # WaterTAP default
        "utilization_factor": 0.9,  # 90% plant uptime
        "electricity_cost_usd_kwh": 0.07,  # WaterTAP default
        
        # Membrane economics (WaterTAP RO defaults)
        "membrane_replacement_factor": 0.2,  # 20% per year replacement
        "membrane_cost_brackish_usd_m2": 30,  # Standard RO membrane
        "membrane_cost_seawater_usd_m2": 75,  # High-pressure RO membrane
        
        # Chemical costs ($/kg) from WaterTAP examples
        "acid_HCl_cost_usd_kg": 0.17,  # 37% HCl solution
        "base_NaOH_cost_usd_kg": 0.59,  # 30% NaOH solution  
        "antiscalant_cost_usd_kg": 2.50,  # Typical specialty chemical
        "cip_surfactant_cost_usd_kg": 3.00,  # CIP surfactant
        "cip_acid_cost_usd_kg": 0.17,  # CIP acid (same as HCl)
        "cip_base_cost_usd_kg": 0.59,  # CIP caustic (same as NaOH)
        
        # Pump costs (WaterTAP defaults)
        "high_pressure_pump_cost_usd_W": 1.908,  # High-pressure pump
        "low_pressure_pump_cost_usd_Lps": 889,  # Low-pressure pump ($/L/s)
        
        # Energy Recovery Device costs
        "pressure_exchanger_cost_usd_m3h": 535,  # Pressure exchanger ERD
        "erd_efficiency": 0.95,  # Modern pressure exchanger efficiency
        
        # Equipment inclusion flags
        "include_cartridge_filters": False,  # Temporarily disabled - ZO subtype issues
        "include_cip_system": False,  # Temporarily disabled for core testing
        "auto_include_erd": True,  # Auto-include for high pressure
        "erd_pressure_threshold_bar": 45,  # Threshold for ERD inclusion
        
        # Cartridge filter costs
        "cartridge_filter_cost_usd_m3h": 100,  # Estimated from typical systems
        
        # CIP system costs
        "cip_capital_cost_usd_m2": 50,  # CIP system per m² membrane
        
        # WaterTAPCostingDetailed percentages
        "land_cost_percent_FCI": 0.0015,  # 0.15% of FCI
        "working_capital_percent_FCI": 0.05,  # 5% of FCI
        "salaries_percent_FCI": 0.001,  # 0.1% of FCI per year
        "benefit_percent_of_salary": 0.9,  # 90% of salaries
        "maintenance_costs_percent_FCI": 0.008,  # 0.8% of FCI per year
        "laboratory_fees_percent_FCI": 0.003,  # 0.3% of FCI per year
        "insurance_and_taxes_percent_FCI": 0.002,  # 0.2% of FCI per year
    }


def get_default_chemical_dosing() -> Dict[str, Any]:
    """
    Get WaterTAP-aligned default chemical dosing parameters.
    
    Returns:
        Dictionary of chemical dosing parameters
    """
    return {
        # Antiscalant dosing (from WaterTAP seawater RO example)
        "antiscalant_dose_mg_L": 5.0,  # mg/L of feed
        
        # pH adjustment (user-specified, no default dosing)
        "acid_dose_kg_m3": 0,  # kg acid per m³ water
        "base_dose_kg_m3": 0,  # kg base per m³ water
        
        # CIP parameters
        "cip_frequency_per_year": 4,  # Quarterly cleaning
        "cip_dose_kg_per_m2": 0.5,  # kg chemical per m² membrane per CIP
        "cip_surfactant_fraction": 0.7,  # 70% surfactant
        "cip_acid_fraction": 0.2,  # 20% acid
        "cip_base_fraction": 0.1,  # 10% caustic
        
        # Optional pretreatment chemicals (typically zero for RO-only)
        "ferric_chloride_dose_mg_L": 0,  # For coagulation if needed
        "lime_dose_mg_L": 0,  # For post-treatment if needed
    }


def apply_economic_defaults(user_params: Dict[str, Any] = None, 
                           membrane_type: str = "brackish") -> Dict[str, Any]:
    """
    Apply defaults to user-provided economic parameters.
    
    Args:
        user_params: User-provided parameters (overrides defaults)
        membrane_type: Type of membrane system
        
    Returns:
        Complete economic parameters with defaults applied
    """
    defaults = get_default_economic_params(membrane_type)
    if user_params is None:
        return defaults
    
    # Merge user parameters with defaults
    return {**defaults, **user_params}


def apply_dosing_defaults(user_dosing: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Apply defaults to user-provided chemical dosing parameters.
    
    Args:
        user_dosing: User-provided dosing parameters (overrides defaults)
        
    Returns:
        Complete dosing parameters with defaults applied
    """
    defaults = get_default_chemical_dosing()
    if user_dosing is None:
        return defaults
    
    # Merge user parameters with defaults
    return {**defaults, **user_dosing}


def validate_economic_params(params: Dict[str, Any]) -> None:
    """
    Validate economic parameters are within reasonable ranges.
    
    Args:
        params: Economic parameters to validate
        
    Raises:
        ValueError: If parameters are outside reasonable ranges
    """
    # Validate WACC
    if not 0 < params["wacc"] < 0.3:
        raise ValueError(f"WACC {params['wacc']} outside reasonable range (0-30%)")
    
    # Validate plant lifetime
    if not 5 <= params["plant_lifetime_years"] <= 50:
        raise ValueError(f"Plant lifetime {params['plant_lifetime_years']} outside range (5-50 years)")
    
    # Validate utilization factor
    if not 0.5 <= params["utilization_factor"] <= 1.0:
        raise ValueError(f"Utilization {params['utilization_factor']} outside range (0.5-1.0)")
    
    # Validate electricity cost
    if not 0 < params["electricity_cost_usd_kwh"] < 1.0:
        raise ValueError(f"Electricity cost ${params['electricity_cost_usd_kwh']}/kWh unrealistic")
    
    # Validate membrane replacement
    if not 0 < params["membrane_replacement_factor"] <= 1.0:
        raise ValueError(f"Membrane replacement {params['membrane_replacement_factor']} outside range (0-1)")
    
    # Validate ERD efficiency
    if params.get("auto_include_erd") and not 0.8 <= params["erd_efficiency"] <= 0.98:
        raise ValueError(f"ERD efficiency {params['erd_efficiency']} outside range (0.8-0.98)")


def validate_dosing_params(params: Dict[str, Any]) -> None:
    """
    Validate chemical dosing parameters are within reasonable ranges.
    
    Args:
        params: Dosing parameters to validate
        
    Raises:
        ValueError: If parameters are outside reasonable ranges
    """
    # Validate antiscalant dose
    if not 0 <= params["antiscalant_dose_mg_L"] <= 20:
        raise ValueError(f"Antiscalant dose {params['antiscalant_dose_mg_L']} mg/L outside range (0-20)")
    
    # Validate CIP frequency
    if not 1 <= params["cip_frequency_per_year"] <= 12:
        raise ValueError(f"CIP frequency {params['cip_frequency_per_year']}/year outside range (1-12)")
    
    # Validate CIP dose
    if not 0 < params["cip_dose_kg_per_m2"] <= 2.0:
        raise ValueError(f"CIP dose {params['cip_dose_kg_per_m2']} kg/m² outside range (0-2)")
    
    # Validate CIP chemical fractions sum to 1
    total_fraction = (params["cip_surfactant_fraction"] + 
                     params["cip_acid_fraction"] + 
                     params["cip_base_fraction"])
    if not 0.99 <= total_fraction <= 1.01:  # Allow small rounding error
        raise ValueError(f"CIP chemical fractions sum to {total_fraction}, should be 1.0")