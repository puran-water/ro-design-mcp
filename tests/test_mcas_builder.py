"""Tests for MCAS property package builder."""

import pytest
from utils.mcas_builder import (
    check_electroneutrality,
    adjust_for_electroneutrality,
    build_mcas_from_ions,
    build_mcas_property_configuration,
    convert_to_molar_basis,
    calculate_ionic_strength,
    estimate_solution_density,
    get_total_dissolved_solids,
    ION_DATA
)


class TestElectroneutrality:
    """Test charge balance functions."""
    
    def test_neutral_solution(self):
        """Test detection of electroneutral solution."""
        # NaCl solution
        composition = {
            "Na+": 100,  # mg/L
            "Cl-": 154.3  # mg/L (stoichiometric)
        }
        is_neutral, imbalance = check_electroneutrality(composition)
        assert is_neutral
        assert imbalance < 0.01
    
    def test_charged_solution(self):
        """Test detection of charged solution."""
        # Excess Na+
        composition = {
            "Na+": 200,  # mg/L
            "Cl-": 154.3  # mg/L
        }
        is_neutral, imbalance = check_electroneutrality(composition)
        assert not is_neutral
        assert imbalance > 0.1
    
    def test_complex_solution(self):
        """Test complex multi-ion solution."""
        composition = {
            "Na+": 1000,
            "Ca2+": 100,
            "Mg2+": 50,
            "Cl-": 1800,
            "SO4-2": 96,
            "HCO3-": 61
        }
        is_neutral, imbalance = check_electroneutrality(composition, tolerance=0.05)
        # Should be approximately neutral
        assert imbalance < 0.05


class TestChargeAdjustment:
    """Test charge balance adjustment."""
    
    def test_adjust_with_chloride(self):
        """Test adjustment using Cl- for cation excess."""
        composition = {
            "Na+": 200,
            "Ca2+": 50,
            "SO4-2": 48  # Not enough anions
        }
        
        adjusted = adjust_for_electroneutrality(composition, adjustment_ion="Cl-")
        
        # Should have added Cl-
        assert "Cl-" in adjusted
        assert adjusted["Cl-"] > 0
        
        # Check if now neutral
        is_neutral, _ = check_electroneutrality(adjusted)
        assert is_neutral
    
    def test_adjust_with_sodium(self):
        """Test adjustment using Na+ for anion excess."""
        composition = {
            "Ca2+": 40,
            "Cl-": 200,
            "SO4-2": 96
        }
        
        adjusted = adjust_for_electroneutrality(composition, adjustment_ion="Na+")
        
        # Should have added Na+
        assert adjusted["Na+"] > 0
        
        # Check if now neutral
        is_neutral, _ = check_electroneutrality(adjusted)
        assert is_neutral
    
    def test_already_neutral(self):
        """Test that neutral solution is not adjusted."""
        composition = {
            "Na+": 100,
            "Cl-": 154.3
        }
        
        adjusted = adjust_for_electroneutrality(composition)
        
        # Should be unchanged
        assert adjusted["Na+"] == composition["Na+"]
        assert adjusted["Cl-"] == composition["Cl-"]


class TestMCASBuilder:
    """Test MCAS configuration building."""
    
    def test_build_simple_mcas(self):
        """Test building MCAS config from simple composition."""
        composition = {
            "Na+": 1000,
            "Cl-": 1543,
            "Ca2+": 100,
            "SO4-2": 240
        }
        
        config, balanced = build_mcas_from_ions(composition)
        
        # Check structure
        assert "components" in config
        assert "H2O" in config["components"]
        assert "Na+" in config["components"]
        assert "phases" in config
        assert "Liq" in config["phases"]
        
        # Check if composition was balanced
        is_neutral, _ = check_electroneutrality(balanced)
        assert is_neutral
    
    def test_build_full_configuration(self):
        """Test building complete MCAS configuration."""
        composition = {
            "Na+": 1200,
            "Ca2+": 120,
            "Mg2+": 60,
            "Cl-": 2100,
            "SO4-2": 200,
            "HCO3-": 150
        }
        
        config = build_mcas_property_configuration(
            composition,
            include_scaling_ions=True,
            include_ph_species=True
        )
        
        # Check all required sections
        assert "components" in config
        assert "component_data" in config
        assert "activity_coefficient_model" in config
        assert "scaling_ions" in config
        assert "ph_species" in config
        
        # Check component data
        for ion in composition:
            if composition[ion] > 0:
                assert ion in config["component_data"]
                assert "molecular_weight" in config["component_data"][ion]
                assert "charge" in config["component_data"][ion]
                assert "diffusivity" in config["component_data"][ion]
        
        # Check scaling ion groups
        assert "calcium_carbonate" in config["scaling_ions"]
        assert "Ca2+" in config["scaling_ions"]["calcium_carbonate"]


class TestUtilityFunctions:
    """Test utility calculation functions."""
    
    def test_molar_conversion(self):
        """Test mg/L to mol/L conversion."""
        composition = {
            "Na+": 230,  # mg/L, ~0.01 mol/L
            "Cl-": 355   # mg/L, ~0.01 mol/L
        }
        
        molar = convert_to_molar_basis(composition)
        
        assert abs(molar["Na+"] - 0.01) < 0.001
        assert abs(molar["Cl-"] - 0.01) < 0.001
    
    def test_ionic_strength(self):
        """Test ionic strength calculation."""
        # NaCl solution
        composition = {
            "Na+": 2300,  # ~0.1 mol/L
            "Cl-": 3550   # ~0.1 mol/L
        }
        
        I = calculate_ionic_strength(composition)
        
        # For 1:1 electrolyte, I = concentration
        assert abs(I - 0.1) < 0.01
        
        # CaCl2 solution
        composition2 = {
            "Ca2+": 4000,  # ~0.1 mol/L
            "Cl-": 7100    # ~0.2 mol/L
        }
        
        I2 = calculate_ionic_strength(composition2)
        
        # For CaCl2: I = 0.5 * (0.1 * 4 + 0.2 * 1) = 0.3
        assert abs(I2 - 0.3) < 0.03
    
    def test_tds_calculation(self):
        """Test TDS calculation."""
        composition = {
            "Na+": 1000,
            "Cl-": 1500,
            "Ca2+": 100,
            "SO4-2": 200
        }
        
        tds = get_total_dissolved_solids(composition)
        assert tds == 2800
    
    def test_density_estimation(self):
        """Test solution density estimation."""
        # Pure water
        density = estimate_solution_density(0, 25)
        assert abs(density - 997) < 1
        
        # Seawater-like
        density_sw = estimate_solution_density(35000, 25)
        assert density_sw > 1020
        assert density_sw < 1030


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_unknown_ion(self):
        """Test handling of unknown ions."""
        composition = {
            "Na+": 100,
            "UnknownIon": 50,
            "Cl-": 154
        }
        
        # Should handle gracefully
        is_neutral, _ = check_electroneutrality(composition)
        # Will ignore unknown ion
    
    def test_zero_concentration(self):
        """Test handling of zero concentrations."""
        composition = {
            "Na+": 100,
            "K+": 0,  # Zero concentration
            "Cl-": 154
        }
        
        config, _ = build_mcas_from_ions(composition)
        
        # K+ should not be in components
        assert "K+" not in config["components"]
    
    def test_wrong_adjustment_ion(self):
        """Test error when using wrong type of adjustment ion."""
        composition = {
            "Na+": 200,  # Cation excess
            "Cl-": 100
        }
        
        # Try to adjust with another cation (should fail)
        with pytest.raises(ValueError, match="Cannot use"):
            adjust_for_electroneutrality(composition, adjustment_ion="K+")