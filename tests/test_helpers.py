"""
Unit tests for utils/helpers.py functions.
"""

import pytest
import numpy as np
from utils.helpers import (
    calculate_vessel_area,
    estimate_osmotic_pressure_bar,
    calculate_brine_osmotic_pressure,
    estimate_initial_pump_pressure,
    get_pump_pressure_bounds,
    format_array_notation,
    calculate_effective_salinity,
    validate_recovery_target,
    validate_flow_rate,
    validate_salinity,
    validate_flux_parameters,
    check_mass_balance,
    convert_numpy_types
)
from utils.constants import STANDARD_ELEMENT_AREA_M2, ELEMENTS_PER_VESSEL


class TestVesselArea:
    """Tests for calculate_vessel_area function."""
    
    @pytest.mark.unit
    def test_default_vessel_area(self):
        """Test vessel area calculation with default parameters."""
        expected = STANDARD_ELEMENT_AREA_M2 * ELEMENTS_PER_VESSEL
        assert calculate_vessel_area() == expected
    
    @pytest.mark.unit
    def test_custom_vessel_area(self):
        """Test vessel area calculation with custom parameters."""
        custom_area = 40.0
        custom_elements = 6
        expected = custom_area * custom_elements
        assert calculate_vessel_area(custom_area, custom_elements) == expected


class TestOsmoticPressure:
    """Tests for osmotic pressure calculations."""
    
    @pytest.mark.unit
    @pytest.mark.parametrize("salinity,expected", [
        (1000, 0.75),
        (5000, 3.75),
        (35000, 26.25),
        (0, 0.0),
    ])
    def test_estimate_osmotic_pressure(self, salinity, expected):
        """Test osmotic pressure estimation."""
        assert estimate_osmotic_pressure_bar(salinity) == pytest.approx(expected)
    
    @pytest.mark.unit
    def test_brine_osmotic_pressure(self):
        """Test brine osmotic pressure calculation."""
        feed_salinity = 5000
        recovery = 0.75
        salt_passage = 0.01
        
        # Expected concentration factor = (1 - 0.01) / (1 - 0.75) = 3.96
        # Expected brine salinity = 5000 * 3.96 = 19800
        # Expected osmotic pressure = 19800 / 1000 * 0.75 = 14.85
        
        result = calculate_brine_osmotic_pressure(feed_salinity, recovery, salt_passage)
        assert result == pytest.approx(14.85, rel=1e-3)


class TestPumpPressure:
    """Tests for pump pressure calculations."""
    
    @pytest.mark.unit
    def test_initial_pump_pressure_brackish(self):
        """Test initial pump pressure estimation for brackish water."""
        feed_salinity = 5000
        recovery = 0.75
        
        result = estimate_initial_pump_pressure(feed_salinity, recovery)
        
        # Should be positive and within reasonable bounds
        assert result > 0
        assert result <= 82.7e5  # Max brackish pressure
    
    @pytest.mark.unit
    def test_pump_pressure_bounds(self):
        """Test pump pressure bounds."""
        lower, upper = get_pump_pressure_bounds('brackish', stage=1)
        
        assert lower == 10e5  # 10 bar
        assert upper == 65e5  # 65 bar for first stage
        
        lower2, upper2 = get_pump_pressure_bounds('brackish', stage=2)
        assert upper2 == 85e5  # 85 bar for later stages


class TestValidation:
    """Tests for validation functions."""
    
    @pytest.mark.unit
    @pytest.mark.parametrize("recovery,should_pass", [
        (0.5, True),
        (0.75, True),
        (0.99, True),
        (0.1, True),
        (0.05, False),
        (1.0, False),
        (-0.1, False),
    ])
    def test_validate_recovery(self, recovery, should_pass):
        """Test recovery validation."""
        if should_pass:
            validate_recovery_target(recovery)  # Should not raise
        else:
            with pytest.raises(ValueError):
                validate_recovery_target(recovery)
    
    @pytest.mark.unit
    @pytest.mark.parametrize("flow,should_pass", [
        (100, True),
        (0.1, True),
        (1000, True),
        (0, False),
        (-10, False),
    ])
    def test_validate_flow_rate(self, flow, should_pass):
        """Test flow rate validation."""
        if should_pass:
            validate_flow_rate(flow)  # Should not raise
        else:
            with pytest.raises(ValueError):
                validate_flow_rate(flow)
    
    @pytest.mark.unit
    @pytest.mark.parametrize("salinity,should_pass", [
        (5000, True),
        (100, True),
        (100000, True),
        (50, False),
        (150000, False),
        (-100, False),
    ])
    def test_validate_salinity(self, salinity, should_pass):
        """Test salinity validation."""
        if should_pass:
            validate_salinity(salinity)  # Should not raise
        else:
            with pytest.raises(ValueError):
                validate_salinity(salinity)


class TestFluxParameters:
    """Tests for flux parameter validation and normalization."""
    
    @pytest.mark.unit
    def test_default_flux_parameters(self):
        """Test flux parameter validation with defaults."""
        targets, tolerance = validate_flux_parameters(None, None)
        
        assert len(targets) == 3
        assert targets == [18, 15, 12]
        assert tolerance == 0.1
    
    @pytest.mark.unit
    def test_single_flux_target(self):
        """Test single flux target normalization."""
        targets, tolerance = validate_flux_parameters(20.0, None)
        
        assert len(targets) == 3
        assert all(t == 20.0 for t in targets)
        assert tolerance == 0.1
    
    @pytest.mark.unit
    def test_list_flux_targets(self):
        """Test list flux targets."""
        input_targets = [24, 20, 16]
        targets, tolerance = validate_flux_parameters(input_targets, 0.15)
        
        assert targets == input_targets
        assert tolerance == 0.15
    
    @pytest.mark.unit
    def test_invalid_flux_parameters(self):
        """Test invalid flux parameters."""
        # Negative flux
        with pytest.raises(ValueError):
            validate_flux_parameters(-5.0, None)
        
        # Empty list
        with pytest.raises(ValueError):
            validate_flux_parameters([], None)
        
        # Invalid tolerance
        with pytest.raises(ValueError):
            validate_flux_parameters(None, -0.1)
        
        with pytest.raises(ValueError):
            validate_flux_parameters(None, 1.5)


class TestUtilityFunctions:
    """Tests for other utility functions."""
    
    @pytest.mark.unit
    def test_format_array_notation(self):
        """Test vessel array notation formatting."""
        assert format_array_notation([12, 5]) == "12:5"
        assert format_array_notation([17, 8, 3]) == "17:8:3"
        assert format_array_notation([10]) == "10"
    
    @pytest.mark.unit
    def test_calculate_effective_salinity(self):
        """Test effective salinity calculation with recycle."""
        fresh_flow = 100
        fresh_salinity = 5000
        recycle_flow = 20
        brine_salinity = 20000
        
        # Expected: (100 * 5000 + 20 * 20000) / 120 = 7500
        result = calculate_effective_salinity(
            fresh_flow, fresh_salinity, recycle_flow, brine_salinity
        )
        assert result == pytest.approx(7500)
    
    @pytest.mark.unit
    def test_check_mass_balance(self):
        """Test mass balance checking."""
        # Balanced case
        balanced, error = check_mass_balance(100, 75, 25)
        assert balanced is True
        assert error < 0.01
        
        # Unbalanced case
        unbalanced, error = check_mass_balance(100, 75, 20)
        assert unbalanced is False
        assert error == pytest.approx(5.0)
    
    @pytest.mark.unit
    def test_convert_numpy_types(self):
        """Test numpy type conversion."""
        # Test various numpy types
        test_data = {
            'int': np.int64(42),
            'float': np.float64(3.14),
            'bool': np.bool_(True),
            'array': np.array([1, 2, 3]),
            'nested': {
                'value': np.float32(2.71)
            },
            'list': [np.int32(1), np.int32(2)],
            'regular': 'string'
        }
        
        result = convert_numpy_types(test_data)
        
        assert isinstance(result['int'], int)
        assert isinstance(result['float'], float)
        assert isinstance(result['bool'], bool)
        assert isinstance(result['array'], list)
        assert isinstance(result['nested']['value'], float)
        assert all(isinstance(x, int) for x in result['list'])
        assert result['regular'] == 'string'