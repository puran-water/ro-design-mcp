"""
Tests for RO simulation functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from utils.simulate_ro import (
    run_ro_simulation,
    calculate_lcow,
    estimate_capital_cost,
    extract_notebook_results
)


class TestSimulateRO:
    """Tests for simulation utilities."""
    
    @pytest.mark.unit
    def test_calculate_lcow(self):
        """Test LCOW calculation."""
        # Test case: $10M capital, $500k/year OPEX, 1M m³/year production
        lcow = calculate_lcow(
            capital_cost=10_000_000,
            annual_opex=500_000,
            annual_production_m3=1_000_000,
            discount_rate=0.08,
            plant_lifetime_years=20
        )
        
        # CRF = 0.08 * (1.08)^20 / ((1.08)^20 - 1) ≈ 0.1019
        # Annual capital = 10M * 0.1019 ≈ 1.019M
        # Total annual = 1.019M + 0.5M = 1.519M
        # LCOW = 1.519M / 1M = $1.519/m³
        assert 1.4 < lcow < 1.6
    
    @pytest.mark.unit
    def test_estimate_capital_cost(self):
        """Test capital cost estimation."""
        # Test with 5000 m² membrane area and 500 kW power
        capital = estimate_capital_cost(
            total_membrane_area_m2=5000,
            total_power_kw=500,
            membrane_cost_per_m2=30,
            power_cost_per_kw=1000,
            indirect_cost_factor=2.5
        )
        
        # Direct = (5000 * 30) + (500 * 1000) = 150k + 500k = 650k
        # Total = 650k * 2.5 = 1.625M
        assert capital == 1_625_000
    
    @pytest.mark.unit
    @patch('utils.simulate_ro.pm.execute_notebook')
    @patch('utils.simulate_ro.extract_notebook_results')
    def test_run_ro_simulation_success(self, mock_extract, mock_execute):
        """Test successful simulation run."""
        # Mock configuration
        config = {
            "array_notation": "10:5",
            "feed_flow_m3h": 100,
            "stages": [
                {"stage_number": 1, "membrane_area_m2": 2602},
                {"stage_number": 2, "membrane_area_m2": 1301}
            ]
        }
        
        # Mock successful execution
        mock_execute.return_value = None
        mock_extract.return_value = {
            "status": "success",
            "performance": {"total_recovery": 0.75},
            "economics": {"total_power_kw": 150},
            "stage_results": [],
            "mass_balance": {}
        }
        
        # Run simulation
        results = run_ro_simulation(
            configuration=config,
            feed_salinity_ppm=5000,
            feed_temperature_c=25.0
        )
        
        assert results["status"] == "success"
        assert results["performance"]["total_recovery"] == 0.75
        assert mock_execute.called
        assert mock_extract.called
    
    @pytest.mark.unit
    @patch('utils.simulate_ro.pm.execute_notebook')
    def test_run_ro_simulation_notebook_error(self, mock_execute):
        """Test handling of notebook execution error."""
        # Mock configuration
        config = {
            "array_notation": "10:5",
            "stages": []
        }
        
        # Mock execution error
        mock_execute.side_effect = Exception("Notebook execution failed")
        
        # Run simulation
        results = run_ro_simulation(
            configuration=config,
            feed_salinity_ppm=5000
        )
        
        assert results["status"] == "error"
        assert "failed" in results["message"].lower()
    
    @pytest.mark.unit
    def test_extract_notebook_results_json_output(self):
        """Test extracting results from notebook with JSON output."""
        # Create mock notebook structure
        mock_cell = MagicMock()
        mock_cell.cell_type = 'code'
        mock_cell.metadata = {'tags': ['results']}
        
        mock_output = MagicMock()
        mock_output.output_type = 'execute_result'
        mock_output.data = {
            'application/json': '{"status": "success", "performance": {"recovery": 0.75}}'
        }
        mock_cell.outputs = [mock_output]
        
        mock_nb = MagicMock()
        mock_nb.cells = [mock_cell]
        
        # Mock nbformat.read
        with patch('nbformat.read', return_value=mock_nb):
            with patch('builtins.open', MagicMock()):
                results = extract_notebook_results("dummy_path.ipynb")
        
        assert results["status"] == "success"
        assert results["performance"]["recovery"] == 0.75
    
    @pytest.mark.unit
    def test_extract_notebook_results_error(self):
        """Test extracting error from notebook."""
        # Create mock notebook with error
        mock_cell = MagicMock()
        mock_cell.cell_type = 'code'
        
        mock_output = MagicMock()
        mock_output.output_type = 'error'
        mock_output.ename = 'ValueError'
        mock_output.evalue = 'Invalid input'
        mock_cell.outputs = [mock_output]
        
        mock_nb = MagicMock()
        mock_nb.cells = [mock_cell]
        
        # Mock nbformat.read
        with patch('nbformat.read', return_value=mock_nb):
            with patch('builtins.open', MagicMock()):
                results = extract_notebook_results("dummy_path.ipynb")
        
        assert results["status"] == "error"
        assert "ValueError" in results["message"]
        assert "Invalid input" in results["message"]


class TestSimulateROIntegration:
    """Integration tests for simulation tool."""
    
    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires WaterTAP installation")
    def test_full_simulation_workflow(self):
        """Test complete simulation workflow with real notebook."""
        # This test would run with actual WaterTAP installed
        config = {
            "stage_count": 2,
            "array_notation": "10:5",
            "total_vessels": 15,
            "total_membrane_area_m2": 3903,
            "feed_flow_m3h": 100,
            "stages": [
                {
                    "stage_number": 1,
                    "n_vessels": 10,
                    "membrane_area_m2": 2602,
                    "stage_recovery": 0.45
                },
                {
                    "stage_number": 2,
                    "n_vessels": 5,
                    "membrane_area_m2": 1301,
                    "stage_recovery": 0.545
                }
            ]
        }
        
        results = run_ro_simulation(
            configuration=config,
            feed_salinity_ppm=5000,
            feed_temperature_c=25.0,
            membrane_type="brackish"
        )
        
        # Would check actual results if WaterTAP was available
        assert results is not None