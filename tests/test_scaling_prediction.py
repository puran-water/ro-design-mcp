"""Tests for scaling prediction utilities."""

import pytest
import numpy as np
from utils.scaling_prediction import (
    calculate_activity_coefficient,
    calculate_saturation_index_simple,
    predict_scaling_simple,
    get_scaling_tendency,
    get_scaling_severity,
    recommend_antiscalant,
    REAKTORO_AVAILABLE
)


class TestActivityCoefficient:
    """Test activity coefficient calculations."""
    
    def test_zero_ionic_strength(self):
        """Test activity coefficient at zero ionic strength."""
        gamma = calculate_activity_coefficient(1, 0.0)
        assert gamma == 1.0
    
    def test_monovalent_ion(self):
        """Test activity coefficient for monovalent ion."""
        # Na+ at I = 0.1 mol/L
        gamma = calculate_activity_coefficient(1, 0.1)
        assert 0.7 < gamma < 0.9
    
    def test_divalent_ion(self):
        """Test activity coefficient for divalent ion."""
        # Ca2+ at I = 0.1 mol/L
        gamma = calculate_activity_coefficient(2, 0.1)
        assert 0.3 < gamma < 0.6
    
    def test_high_ionic_strength(self):
        """Test at high ionic strength."""
        gamma = calculate_activity_coefficient(1, 0.5)
        assert gamma < 0.8


class TestSaturationIndex:
    """Test saturation index calculations."""
    
    def test_calcite_undersaturated(self):
        """Test undersaturated calcite."""
        activities = {
            "Ca2+": 1e-4,  # mol/L
            "CO3-2": 1e-5
        }
        SI = calculate_saturation_index_simple(activities, "CaCO3")
        assert SI < 0
    
    def test_calcite_supersaturated(self):
        """Test supersaturated calcite."""
        activities = {
            "Ca2+": 1e-2,
            "CO3-2": 1e-3
        }
        SI = calculate_saturation_index_simple(activities, "CaCO3")
        assert SI > 0
    
    def test_gypsum_equilibrium(self):
        """Test gypsum near equilibrium."""
        # Ksp for gypsum ~ 4.93e-5
        activities = {
            "Ca2+": 7e-3,
            "SO4-2": 7e-3
        }
        SI = calculate_saturation_index_simple(activities, "CaSO4")
        assert abs(SI) < 0.1
    
    def test_unknown_mineral(self):
        """Test unknown mineral returns NaN."""
        activities = {"Ca2+": 1e-3}
        SI = calculate_saturation_index_simple(activities, "UnknownMineral")
        assert np.isnan(SI)


class TestScalingPrediction:
    """Test complete scaling prediction."""
    
    def test_typical_brackish_water(self):
        """Test scaling prediction for typical brackish water."""
        composition = {
            "Ca2+": 120,    # mg/L
            "Mg2+": 50,
            "Na+": 800,
            "HCO3-": 200,
            "SO4-2": 300,
            "Cl-": 1400
        }
        
        results = predict_scaling_simple(
            composition,
            ionic_strength=0.05,
            temperature_c=25,
            ph=7.8
        )
        
        assert "CaCO3" in results
        assert "CaSO4" in results
        assert "saturation_index" in results["CaCO3"]
        assert "scaling_tendency" in results["CaCO3"]
        assert "severity" in results["CaCO3"]
    
    def test_high_hardness_water(self):
        """Test high hardness water with scaling risk."""
        composition = {
            "Ca2+": 400,
            "Mg2+": 150,
            "HCO3-": 300,
            "SO4-2": 500
        }
        
        results = predict_scaling_simple(
            composition,
            ionic_strength=0.08,
            temperature_c=30,
            ph=8.2
        )
        
        # Should show high calcite scaling risk
        assert results["CaCO3"]["saturation_index"] > 0.5
        assert "High" in results["CaCO3"]["scaling_tendency"]
    
    def test_silica_scaling(self):
        """Test silica scaling prediction."""
        composition = {
            "SiO3-2": 150,  # High silica
            "Ca2+": 50,
            "Mg2+": 20
        }
        
        results = predict_scaling_simple(
            composition,
            ionic_strength=0.02,
            temperature_c=25,
            ph=7.5
        )
        
        assert "SiO2" in results


class TestScalingInterpretation:
    """Test scaling tendency interpretation."""
    
    def test_scaling_tendency_categories(self):
        """Test all scaling tendency categories."""
        assert "No scaling" in get_scaling_tendency(-1.0)
        assert "Low" in get_scaling_tendency(-0.3)
        assert "Moderate" in get_scaling_tendency(0.2)
        assert "High" in get_scaling_tendency(0.7)
        assert "Severe" in get_scaling_tendency(1.5)
    
    def test_scaling_severity_range(self):
        """Test scaling severity scores."""
        assert get_scaling_severity(-0.5) == 0.0
        assert 0 < get_scaling_severity(0.3) < 0.5
        assert 0.5 <= get_scaling_severity(0.7) < 0.8
        assert get_scaling_severity(2.0) <= 1.0


class TestAntiscalantRecommendation:
    """Test antiscalant recommendations."""
    
    def test_no_scaling_risk(self):
        """Test when no antiscalant needed."""
        scaling_results = {
            "CaCO3": {"severity": 0.1},
            "CaSO4": {"severity": 0.2}
        }
        
        rec = recommend_antiscalant(scaling_results)
        assert rec["antiscalant_type"] == "None required"
        assert rec["dosage_ppm"] == 0
    
    def test_carbonate_scaling(self):
        """Test carbonate scaling recommendation."""
        scaling_results = {
            "CaCO3": {"severity": 0.7},
            "CaSO4": {"severity": 0.3}
        }
        
        rec = recommend_antiscalant(scaling_results)
        assert rec["primary_concern"] == "CaCO3"
        assert "polyacrylic" in rec["antiscalant_type"].lower()
        assert rec["dosage_ppm"] > 2
        assert len(rec["specific_products"]) > 0
    
    def test_sulfate_scaling(self):
        """Test sulfate scaling recommendation."""
        scaling_results = {
            "CaCO3": {"severity": 0.2},
            "BaSO4": {"severity": 0.8}
        }
        
        rec = recommend_antiscalant(scaling_results)
        assert rec["primary_concern"] == "BaSO4"
        assert "phosphonate" in rec["antiscalant_type"].lower()
        assert rec["dosage_ppm"] > 3
    
    def test_silica_scaling(self):
        """Test silica scaling recommendation."""
        scaling_results = {
            "SiO2": {"severity": 0.9},
            "CaCO3": {"severity": 0.4}
        }
        
        rec = recommend_antiscalant(scaling_results)
        assert rec["primary_concern"] == "SiO2"
        assert "silica" in rec["antiscalant_type"].lower()
        assert rec["dosage_ppm"] > 5


class TestTemperatureEffects:
    """Test temperature effects on scaling."""
    
    def test_temperature_correction(self):
        """Test temperature effects on calcite solubility."""
        activities = {
            "Ca2+": 5e-3,
            "CO3-2": 1e-4
        }
        
        # Calcite is less soluble at higher temperature
        SI_25 = calculate_saturation_index_simple(activities, "CaCO3", 25)
        SI_40 = calculate_saturation_index_simple(activities, "CaCO3", 40)
        
        # Higher temperature should give higher SI (more supersaturated)
        assert SI_40 > SI_25


@pytest.mark.skipif(not REAKTORO_AVAILABLE, reason="Reaktoro not installed")
class TestReaktoroIntegration:
    """Test Reaktoro integration if available."""
    
    def test_reaktoro_vs_simple(self):
        """Compare Reaktoro and simple calculations."""
        from utils.scaling_prediction import predict_scaling_reaktoro
        
        composition = {
            "Ca2+": 100,
            "HCO3-": 200,
            "SO4-2": 150
        }
        
        # Both methods should give similar trends
        simple_results = predict_scaling_simple(
            composition,
            ionic_strength=0.02,
            temperature_c=25,
            ph=7.5
        )
        
        reaktoro_results = predict_scaling_reaktoro(
            composition,
            temperature_c=25,
            pressure_bar=1.0,
            ph=7.5
        )
        
        # Check that both identify same minerals
        assert "CaCO3" in simple_results
        assert "CaCO3" in reaktoro_results