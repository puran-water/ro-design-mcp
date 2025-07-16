"""
Membrane Parameter Fitting Utility

This module provides functions to calculate membrane permeability coefficients
(A_comp and B_comp) from manufacturer spec sheet data using WaterTAP's 
parameter fitting approach.

Based on the WaterTAP RO parameter fitting tutorial.
"""

import logging
from typing import Dict, Tuple, Optional
from pyomo.environ import (
    ConcreteModel,
    value,
    assert_optimal_termination,
    units as pyunits,
)
from pyomo.util.check_units import assert_units_consistent
from idaes.core import FlowsheetBlock
from idaes.core.util.scaling import calculate_scaling_factors, set_scaling_factor
from idaes.core.util.model_statistics import degrees_of_freedom
from watertap.property_models.NaCl_prop_pack import NaClParameterBlock
from watertap.unit_models.reverse_osmosis_0D import (
    ReverseOsmosis0D,
    ConcentrationPolarizationType,
    MassTransferCoefficient,
    PressureChangeType,
)
from watertap.core.solvers import get_solver

logger = logging.getLogger(__name__)


def calculate_membrane_permeability_from_spec(
    permeate_flow_m3_day: float,
    salt_rejection: float,
    active_area_m2: float,
    test_pressure_bar: float,
    test_temperature_c: float = 25.0,
    feed_concentration_ppm: float = 2000.0,
    feed_flow_m3_h: Optional[float] = None,
    recovery: Optional[float] = 0.15,
) -> Dict[str, float]:
    """
    Calculate A_comp and B_comp from manufacturer spec sheet data.
    
    This function uses WaterTAP's parameter fitting approach to determine
    membrane permeability coefficients from standard test conditions.
    
    Args:
        permeate_flow_m3_day: Permeate flow rate from spec sheet (m³/day)
        salt_rejection: Salt rejection fraction (e.g., 0.995 for 99.5%)
        active_area_m2: Active membrane area (m²)
        test_pressure_bar: Feed pressure during test (bar)
        test_temperature_c: Feed temperature during test (°C), default 25°C
        feed_concentration_ppm: Feed TDS concentration (mg/L), default 2000
        feed_flow_m3_h: Feed flow rate (m³/h), calculated from recovery if not provided
        recovery: Recovery fraction, default 0.15
        
    Returns:
        Dict with:
            - 'A_w': Water permeability coefficient (m/s/Pa)
            - 'B_s': Salt permeability coefficient (m/s)
            - 'permeate_concentration_ppm': Calculated permeate concentration
            
    Example:
        >>> # FilmTec BW30-400 spec sheet data
        >>> results = calculate_membrane_permeability_from_spec(
        ...     permeate_flow_m3_day=49.2,
        ...     salt_rejection=0.995,
        ...     active_area_m2=37.2,
        ...     test_pressure_bar=15.5,
        ...     feed_concentration_ppm=2000
        ... )
        >>> print(f"A_w = {results['A_w']:.2e} m/s/Pa")
        >>> print(f"B_s = {results['B_s']:.2e} m/s")
    """
    logger.info("Starting membrane parameter fitting from spec sheet data")
    
    # Convert units
    permeate_flow_kg_s = permeate_flow_m3_day * 997.0 / (24 * 3600)  # m³/day to kg/s
    test_pressure_pa = test_pressure_bar * 1e5  # bar to Pa
    feed_conc_kg_m3 = feed_concentration_ppm / 1000  # ppm to kg/m³
    
    # Calculate feed flow if not provided
    if feed_flow_m3_h is None:
        feed_flow_kg_s = permeate_flow_kg_s / recovery
    else:
        feed_flow_kg_s = feed_flow_m3_h * 997.0 / 3600  # m³/h to kg/s
    
    # Create model
    m = ConcreteModel()
    m.fs = FlowsheetBlock(dynamic=False)
    m.fs.properties = NaClParameterBlock()
    
    # Create RO unit
    m.fs.RO = ReverseOsmosis0D(
        property_package=m.fs.properties,
        has_pressure_change=True,
        pressure_change_type=PressureChangeType.fixed_per_stage,
        mass_transfer_coefficient=MassTransferCoefficient.calculated,
        concentration_polarization_type=ConcentrationPolarizationType.calculated,
    )
    
    # Fix inlet conditions
    m.fs.RO.inlet.flow_mass_phase_comp[0, 'Liq', 'NaCl'].fix(
        feed_flow_kg_s * feed_conc_kg_m3 / (1 + feed_conc_kg_m3)
    )
    m.fs.RO.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O'].fix(
        feed_flow_kg_s / (1 + feed_conc_kg_m3)
    )
    m.fs.RO.inlet.pressure[0].fix(test_pressure_pa)
    m.fs.RO.inlet.temperature[0].fix(273.15 + test_temperature_c)
    
    # Fix membrane area and module specifications
    m.fs.RO.area.fix(active_area_m2)
    m.fs.RO.permeate.pressure[0].fix(101325)  # 1 atm
    m.fs.RO.feed_side.channel_height.fix(1e-3)  # 1 mm
    m.fs.RO.feed_side.spacer_porosity.fix(0.85)  # typical value
    m.fs.RO.width.fix(active_area_m2 / 1.0)  # assume 1m length for 0D model
    m.fs.RO.deltaP.fix(-0.5e5)  # 0.5 bar pressure drop
    
    # Set initial guesses for A and B
    m.fs.RO.A_comp.fix(4.2e-12)  # initial guess
    m.fs.RO.B_comp.fix(3.5e-8)   # initial guess
    
    # Set scaling factors - following WaterTAP's approach
    m.fs.properties.set_default_scaling('flow_mass_phase_comp', 1, index=('Liq', 'H2O'))
    m.fs.properties.set_default_scaling('flow_mass_phase_comp', 1e2, index=('Liq', 'NaCl'))
    set_scaling_factor(m.fs.RO.area, 1e-2)
    
    # Set scaling for A and B as per WaterTAP reverse_osmosis_base.py
    set_scaling_factor(m.fs.RO.A_comp, 1e12)
    set_scaling_factor(m.fs.RO.B_comp, 1e8)
    
    calculate_scaling_factors(m)
    
    # Initialize
    m.fs.RO.initialize()
    
    # Check initial DOF
    assert degrees_of_freedom(m) == 0, f"Expected 0 DOF, got {degrees_of_freedom(m)}"
    
    # Create solver
    solver = get_solver()
    
    # Step 1: Solve for A_comp
    logger.info("Step 1: Solving for water permeability coefficient (A)")
    m.fs.RO.A_comp.unfix()
    m.fs.RO.mixed_permeate[0.0].flow_mass_phase_comp['Liq', 'H2O'].fix(permeate_flow_kg_s)
    
    results = solver.solve(m, tee=False)
    assert_optimal_termination(results)
    
    A_value = value(m.fs.RO.A_comp[0, 'H2O'])
    logger.info(f"Calculated A_comp = {A_value:.3e} m/s/Pa")
    
    # Step 2: Solve for B_comp
    logger.info("Step 2: Solving for salt permeability coefficient (B)")
    m.fs.RO.B_comp.unfix()
    m.fs.RO.rejection_phase_comp[0, "Liq", "NaCl"].fix(salt_rejection)
    
    results = solver.solve(m, tee=False)
    assert_optimal_termination(results)
    
    B_value = value(m.fs.RO.B_comp[0, 'NaCl'])
    permeate_conc = value(m.fs.RO.mixed_permeate[0].conc_mass_phase_comp['Liq', 'NaCl'])
    
    logger.info(f"Calculated B_comp = {B_value:.3e} m/s")
    logger.info(f"Permeate concentration = {permeate_conc:.1f} mg/L")
    
    return {
        'A_w': A_value,
        'B_s': B_value,
        'permeate_concentration_ppm': permeate_conc * 1000,
    }


# Pre-calculated values for common membranes from literature and spec sheets
MEMBRANE_DATABASE = {
    # Literature values from MDPI Water 2019, 11(1), 152
    'bw30_400': {
        'manufacturer': 'Dow FilmTec',
        'type': 'brackish',
        'A_w': 9.63e-12,  # m/s/Pa
        'B_s': 5.58e-8,   # m/s
        'source': 'MDPI Water 2019, 11(1), 152',
        'test_conditions': {
            'pressure_bar': 15.5,
            'temperature_c': 25,
            'feed_ppm': 2000,
            'recovery': 0.15,
        },
        'performance': {
            'permeate_flow_m3_day': 49.2,
            'salt_rejection': 0.995,
            'active_area_m2': 37.2,
        }
    },
    'eco_pro_400': {
        'manufacturer': 'Dow FilmTec',
        'type': 'brackish',
        'A_w': 1.60e-11,  # m/s/Pa
        'B_s': 4.24e-8,   # m/s
        'source': 'MDPI Water 2019, 11(1), 152',
        'test_conditions': {
            'pressure_bar': 10.3,
            'temperature_c': 25,
            'feed_ppm': 2000,
            'recovery': 0.15,
        },
        'performance': {
            'permeate_flow_m3_day': 49.2,
            'salt_rejection': 0.97,
            'active_area_m2': 37.2,
        }
    },
    'cr100_pro_400': {
        'manufacturer': 'Dow FilmTec',
        'type': 'brackish',
        'A_w': 1.06e-11,  # m/s/Pa
        'B_s': 4.16e-8,   # m/s
        'source': 'MDPI Water 2019, 11(1), 152',
        'test_conditions': {
            'pressure_bar': 15.5,
            'temperature_c': 25,
            'feed_ppm': 2000,
            'recovery': 0.15,
        },
        'performance': {
            'permeate_flow_m3_day': 62.8,
            'salt_rejection': 0.98,
            'active_area_m2': 37.2,
        }
    }
}


def get_membrane_properties(membrane_model: str) -> Dict[str, float]:
    """
    Get membrane properties from the database.
    
    Args:
        membrane_model: Membrane model identifier (e.g., 'bw30_400')
        
    Returns:
        Dict with A_w and B_s values
        
    Raises:
        KeyError: If membrane model not found in database
    """
    if membrane_model not in MEMBRANE_DATABASE:
        available = ', '.join(MEMBRANE_DATABASE.keys())
        raise KeyError(
            f"Membrane model '{membrane_model}' not found. "
            f"Available models: {available}"
        )
    
    membrane = MEMBRANE_DATABASE[membrane_model]
    return {
        'A_w': membrane['A_w'],
        'B_s': membrane['B_s'],
    }


def calculate_from_spec_sheet(
    membrane_model: str,
    spec_data: Optional[Dict] = None
) -> Dict[str, float]:
    """
    Calculate membrane properties from spec sheet data.
    
    If membrane is in database, returns stored values.
    Otherwise, calculates from provided spec data.
    
    Args:
        membrane_model: Membrane identifier
        spec_data: Optional spec sheet data to override or for new membranes
        
    Returns:
        Dict with A_w and B_s values
    """
    # Check if we have pre-calculated values
    if membrane_model in MEMBRANE_DATABASE and spec_data is None:
        logger.info(f"Using pre-calculated values for {membrane_model}")
        return get_membrane_properties(membrane_model)
    
    # Calculate from spec data
    if spec_data is None:
        if membrane_model in MEMBRANE_DATABASE:
            # Use stored spec data to recalculate
            membrane = MEMBRANE_DATABASE[membrane_model]
            spec_data = membrane['performance']
            spec_data.update(membrane['test_conditions'])
        else:
            raise ValueError(
                f"No spec data provided for unknown membrane '{membrane_model}'"
            )
    
    logger.info(f"Calculating parameters for {membrane_model} from spec data")
    return calculate_membrane_permeability_from_spec(**spec_data)