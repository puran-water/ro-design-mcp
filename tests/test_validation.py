"""
Tests for input validation utilities.
"""

import pytest
from utils.validation import (
    validate_membrane_type,
    validate_recycle_parameters,
    parse_flux_targets,
    validate_flux_tolerance,
    validate_optimize_ro_inputs
)


class TestValidateMembranType:
    """Tests for membrane type validation."""
    
    @pytest.mark.unit
    def test_valid_membrane_types(self):
        """Test valid membrane types."""
        # Should not raise
        validate_membrane_type("brackish")
        validate_membrane_type("seawater")
    
    @pytest.mark.unit
    def test_invalid_membrane_type(self):
        """Test invalid membrane type."""
        with pytest.raises(ValueError, match="Invalid membrane_type"):
            validate_membrane_type("ultrafiltration")
        
        with pytest.raises(ValueError, match="Must be one of"):
            validate_membrane_type("nanofiltration")


class TestValidateRecycleParameters:
    """Tests for recycle parameter validation."""
    
    @pytest.mark.unit
    def test_valid_recycle_parameters(self):
        """Test valid recycle parameters."""
        # Should not raise
        validate_recycle_parameters(True, 0.5)
        validate_recycle_parameters(False, 0.0)
        validate_recycle_parameters(True, 1.0)
    
    @pytest.mark.unit
    def test_invalid_allow_recycle_type(self):
        """Test invalid allow_recycle type."""
        with pytest.raises(ValueError, match="allow_recycle must be boolean"):
            validate_recycle_parameters("yes", 0.5)
        
        with pytest.raises(ValueError, match="allow_recycle must be boolean"):
            validate_recycle_parameters(1, 0.5)
    
    @pytest.mark.unit
    def test_invalid_max_recycle_ratio_type(self):
        """Test invalid max_recycle_ratio type."""
        with pytest.raises(ValueError, match="max_recycle_ratio must be a number"):
            validate_recycle_parameters(True, "0.5")
        
        with pytest.raises(ValueError, match="max_recycle_ratio must be a number"):
            validate_recycle_parameters(True, None)
    
    @pytest.mark.unit
    def test_invalid_max_recycle_ratio_range(self):
        """Test max_recycle_ratio out of range."""
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            validate_recycle_parameters(True, -0.1)
        
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            validate_recycle_parameters(True, 1.1)


class TestParseFluxTargets:
    """Tests for flux target parsing."""
    
    @pytest.mark.unit
    def test_parse_none(self):
        """Test parsing None returns None."""
        assert parse_flux_targets(None) is None
    
    @pytest.mark.unit
    def test_parse_single_number_string(self):
        """Test parsing single number as string."""
        assert parse_flux_targets("20") == 20.0
        assert parse_flux_targets("18.5") == 18.5
        assert parse_flux_targets("25.0") == 25.0
    
    @pytest.mark.unit
    def test_parse_json_single_number(self):
        """Test parsing JSON single number."""
        assert parse_flux_targets("20.0") == 20.0
        assert parse_flux_targets("15") == 15.0
    
    @pytest.mark.unit
    def test_parse_json_array(self):
        """Test parsing JSON array."""
        assert parse_flux_targets("[20, 18, 15]") == [20.0, 18.0, 15.0]
        assert parse_flux_targets("[22.5, 18.5, 14.5]") == [22.5, 18.5, 14.5]
        assert parse_flux_targets("[25]") == [25.0]
    
    @pytest.mark.unit
    def test_parse_invalid_format(self):
        """Test parsing invalid formats."""
        with pytest.raises(ValueError, match="Invalid flux_targets_lmh format"):
            parse_flux_targets("abc")
        
        with pytest.raises(ValueError, match="Invalid flux_targets_lmh format"):
            parse_flux_targets("{20, 18, 15}")
        
        with pytest.raises(ValueError, match="Invalid flux_targets_lmh format"):
            parse_flux_targets("20, 18, 15")
    
    @pytest.mark.unit
    def test_parse_empty_array(self):
        """Test parsing empty array."""
        with pytest.raises(ValueError, match="Flux targets array cannot be empty"):
            parse_flux_targets("[]")
    
    @pytest.mark.unit
    def test_parse_negative_values(self):
        """Test parsing negative values."""
        with pytest.raises(ValueError, match="All flux targets must be positive"):
            parse_flux_targets("[-20, 18, 15]")
        
        with pytest.raises(ValueError, match="All flux targets must be positive"):
            parse_flux_targets("[20, 0, 15]")
    
    @pytest.mark.unit
    def test_parse_invalid_json_type(self):
        """Test parsing invalid JSON types."""
        with pytest.raises(ValueError, match="must be a number or array"):
            parse_flux_targets('{"flux": 20}')
        
        with pytest.raises(ValueError, match="must be a number or array"):
            parse_flux_targets('"string_value"')


class TestValidateFluxTolerance:
    """Tests for flux tolerance validation."""
    
    @pytest.mark.unit
    def test_valid_flux_tolerance(self):
        """Test valid flux tolerance values."""
        # Should not raise
        validate_flux_tolerance(None)
        validate_flux_tolerance(0.1)
        validate_flux_tolerance(0.0)
        validate_flux_tolerance(1.0)
        validate_flux_tolerance(0.15)
    
    @pytest.mark.unit
    def test_invalid_flux_tolerance_type(self):
        """Test invalid flux tolerance type."""
        with pytest.raises(ValueError, match="flux_tolerance must be a number"):
            validate_flux_tolerance("0.1")
        
        with pytest.raises(ValueError, match="flux_tolerance must be a number"):
            validate_flux_tolerance([0.1])
    
    @pytest.mark.unit
    def test_invalid_flux_tolerance_range(self):
        """Test flux tolerance out of range."""
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            validate_flux_tolerance(-0.1)
        
        with pytest.raises(ValueError, match="must be between 0 and 1"):
            validate_flux_tolerance(1.1)


class TestValidateOptimizeRoInputs:
    """Tests for complete input validation."""
    
    @pytest.mark.unit
    def test_valid_inputs_minimal(self):
        """Test validation with minimal inputs."""
        parsed_flux, flux_tol = validate_optimize_ro_inputs(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.75
        )
        assert parsed_flux is None
        assert flux_tol is None
    
    @pytest.mark.unit
    def test_valid_inputs_complete(self):
        """Test validation with all inputs."""
        parsed_flux, flux_tol = validate_optimize_ro_inputs(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.75,
            membrane_type="seawater",
            allow_recycle=True,
            max_recycle_ratio=0.8,
            flux_targets_lmh="[22, 18, 15]",
            flux_tolerance=0.15
        )
        assert parsed_flux == [22.0, 18.0, 15.0]
        assert flux_tol == 0.15
    
    @pytest.mark.unit
    def test_invalid_feed_flow(self):
        """Test invalid feed flow."""
        with pytest.raises(ValueError, match="feed_flow_m3h"):
            validate_optimize_ro_inputs(
                feed_flow_m3h=-10.0,
                water_recovery_fraction=0.75
            )
    
    @pytest.mark.unit
    def test_invalid_recovery(self):
        """Test invalid recovery."""
        with pytest.raises(ValueError, match="Recovery"):
            validate_optimize_ro_inputs(
                feed_flow_m3h=100.0,
                water_recovery_fraction=1.5
            )
    
    @pytest.mark.unit
    def test_cascading_validations(self):
        """Test that all validations are performed."""
        # Test membrane type validation
        with pytest.raises(ValueError, match="Invalid membrane_type"):
            validate_optimize_ro_inputs(
                feed_flow_m3h=100.0,
                water_recovery_fraction=0.75,
                membrane_type="invalid"
            )
        
        # Test recycle validation
        with pytest.raises(ValueError, match="allow_recycle must be boolean"):
            validate_optimize_ro_inputs(
                feed_flow_m3h=100.0,
                water_recovery_fraction=0.75,
                allow_recycle="yes"
            )
        
        # Test flux validation
        with pytest.raises(ValueError, match="Invalid flux_targets_lmh format"):
            validate_optimize_ro_inputs(
                feed_flow_m3h=100.0,
                water_recovery_fraction=0.75,
                flux_targets_lmh="invalid"
            )