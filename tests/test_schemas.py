"""
Tests for Pydantic schemas.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from utils.schemas import (
    SCHEMA_VERSION_CONTEXT,
    SCHEMA_VERSION_INPUT,
    SCHEMA_VERSION_MANIFEST,
    SCHEMA_VERSION_RESULTS,
    ArtifactFile,
    ArtifactManifest,
    EconomicResults,
    FeedComposition,
    IonRejection,
    MassBalance,
    MembraneProperties,
    OptimizationInput,
    OptimizationResult,
    PerformanceMetrics,
    RecycleInfo,
    ROConfiguration,
    ROSimulationInput,
    ROSimulationResults,
    RunContext,
    SimulationOptions,
    SolveStatus,
    StageConfiguration,
    StageResult,
)


class TestInputSchemas:
    """Test input-related schemas."""
    
    def test_feed_composition(self):
        """Test FeedComposition model."""
        # Valid composition
        feed = FeedComposition(
            salinity_ppm=5000,
            ion_composition_mg_l={"Na+": 1500, "Cl-": 2400},
            temperature_c=25.0
        )
        assert feed.salinity_ppm == 5000
        assert feed.ion_composition_mg_l["Na+"] == 1500
        assert feed.temperature_c == 25.0
        
        # Default temperature
        feed2 = FeedComposition(
            salinity_ppm=35000,
            ion_composition_mg_l={"Na+": 10000, "Cl-": 19000}
        )
        assert feed2.temperature_c == 25.0
    
    def test_stage_configuration(self):
        """Test StageConfiguration model."""
        stage = StageConfiguration(
            stage_number=1,
            feed_flow_m3h=100,
            n_vessels=6,
            vessel_count=6,
            membrane_area_m2=245.4,
            stage_recovery=0.5
        )
        assert stage.stage_number == 1
        assert stage.n_vessels == 6
        assert stage.elements_per_vessel == 7  # Default value
        
        # Test validation - stage number must be 1-3
        with pytest.raises(ValidationError):
            StageConfiguration(
                stage_number=4,
                feed_flow_m3h=100,
                n_vessels=1,
                vessel_count=1,
                membrane_area_m2=40.9,
                stage_recovery=0.5
            )
    
    def test_recycle_info(self):
        """Test RecycleInfo model."""
        # No recycle
        recycle = RecycleInfo(uses_recycle=False)
        assert not recycle.uses_recycle
        assert recycle.recycle_ratio is None
        
        # With recycle
        recycle2 = RecycleInfo(
            uses_recycle=True,
            recycle_ratio=0.5,
            recycle_flow_m3h=50.0
        )
        assert recycle2.uses_recycle
        assert recycle2.recycle_ratio == 0.5
    
    def test_ro_configuration(self):
        """Test ROConfiguration model."""
        stage1 = StageConfiguration(
            stage_number=1,
            feed_flow_m3h=100,
            n_vessels=6,
            vessel_count=6,
            membrane_area_m2=245.4,
            stage_recovery=0.5
        )
        recycle = RecycleInfo(uses_recycle=False)
        
        config = ROConfiguration(
            n_stages=1,
            stages=[stage1],
            recycle_info=recycle
        )
        assert config.n_stages == 1
        assert len(config.stages) == 1
        assert not config.recycle_info.uses_recycle
    
    def test_membrane_properties(self):
        """Test MembraneProperties model."""
        # All properties optional
        props = MembraneProperties()
        assert props.water_permeability_m_s_pa is None
        
        # With values
        props2 = MembraneProperties(
            water_permeability_m_s_pa=4.2e-12,
            salt_permeability_m_s=3.5e-8
        )
        assert props2.water_permeability_m_s_pa == 4.2e-12
        assert props2.salt_permeability_m_s == 3.5e-8
    
    def test_simulation_options(self):
        """Test SimulationOptions model."""
        # Defaults
        opts = SimulationOptions()
        assert opts.optimize_pumps is True
        assert opts.timeout_seconds == 120
        assert opts.solver == "ipopt"
        assert opts.tolerance == 1e-6
        
        # Custom values
        opts2 = SimulationOptions(
            optimize_pumps=False,
            timeout_seconds=300,
            solver="gurobi",
            tolerance=1e-8
        )
        assert not opts2.optimize_pumps
        assert opts2.timeout_seconds == 300
    
    def test_ro_simulation_input(self):
        """Test complete ROSimulationInput model."""
        # Build complete input
        stage1 = StageConfiguration(
            stage_number=1,
            feed_flow_m3h=100,
            n_vessels=6,
            vessel_count=6,
            membrane_area_m2=245.4,
            stage_recovery=0.5
        )
        
        config = ROConfiguration(
            n_stages=1,
            stages=[stage1],
            recycle_info=RecycleInfo(uses_recycle=False)
        )
        
        feed = FeedComposition(
            salinity_ppm=5000,
            ion_composition_mg_l={"Na+": 1500, "Cl-": 2400}
        )
        
        sim_input = ROSimulationInput(
            configuration=config,
            feed=feed,
            membrane_type="brackish"
        )
        
        assert sim_input.schema_version == SCHEMA_VERSION_INPUT
        assert sim_input.membrane_type == "brackish"
        assert sim_input.options.optimize_pumps is True  # Default


class TestOutputSchemas:
    """Test output-related schemas."""
    
    def test_solve_status(self):
        """Test SolveStatus model."""
        status = SolveStatus(
            success=True,
            termination_condition="optimal",
            solver_message="Solved to optimality",
            iterations=42,
            solve_time_seconds=3.14
        )
        assert status.success is True
        assert status.iterations == 42
    
    def test_performance_metrics(self):
        """Test PerformanceMetrics model."""
        metrics = PerformanceMetrics(
            system_recovery=0.75,
            total_permeate_flow_m3h=75.0,
            total_permeate_tds_mg_l=150.0,
            total_power_consumption_kw=45.5,
            specific_energy_kwh_m3=0.61
        )
        assert metrics.system_recovery == 0.75
        assert metrics.specific_energy_kwh_m3 == 0.61
    
    def test_ion_rejection(self):
        """Test IonRejection model."""
        rejection = IonRejection(
            feed_mg_l=1500.0,
            permeate_mg_l=30.0,
            concentrate_mg_l=6000.0,
            rejection=0.98
        )
        assert rejection.rejection == 0.98
        assert rejection.feed_mg_l == 1500.0
    
    def test_stage_result(self):
        """Test StageResult model."""
        ion_data = {
            "Na+": IonRejection(
                feed_mg_l=1500.0,
                permeate_mg_l=30.0,
                concentrate_mg_l=6000.0,
                rejection=0.98
            )
        }
        
        stage = StageResult(
            stage=1,
            recovery=0.5,
            feed_flow_kg_s=27.78,
            permeate_flow_kg_s=13.89,
            concentrate_flow_kg_s=13.89,
            feed_pressure_bar=15.0,
            concentrate_pressure_bar=14.5,
            permeate_pressure_bar=0.0,
            pump_power_kw=45.5,
            ion_data=ion_data
        )
        assert stage.stage == 1
        assert stage.recovery == 0.5
        assert stage.pump_power_kw == 45.5
    
    def test_economic_results(self):
        """Test EconomicResults model."""
        economics = EconomicResults(
            capital_cost_usd=1000000,
            operating_cost_usd_year=50000,
            lcow_usd_m3=0.45,
            specific_energy_consumption_kwh_m3=0.61,
            electricity_cost_usd_year=30000,
            maintenance_cost_usd_year=10000,
            membrane_replacement_cost_usd_year=10000,
            individual_unit_costs={"pumps": 50000, "vessels": 100000},
            annual_production_m3=657000
        )
        assert economics.lcow_usd_m3 == 0.45
        assert economics.capital_cost_usd == 1000000
    
    def test_ro_simulation_results(self):
        """Test complete ROSimulationResults model."""
        solve_info = SolveStatus(
            success=True,
            termination_condition="optimal"
        )
        
        performance = PerformanceMetrics(
            system_recovery=0.75,
            total_permeate_flow_m3h=75.0,
            total_permeate_tds_mg_l=150.0,
            total_power_consumption_kw=45.5,
            specific_energy_kwh_m3=0.61
        )
        
        economics = EconomicResults(
            capital_cost_usd=1000000,
            operating_cost_usd_year=50000,
            lcow_usd_m3=0.45,
            specific_energy_consumption_kwh_m3=0.61,
            electricity_cost_usd_year=30000,
            maintenance_cost_usd_year=10000,
            membrane_replacement_cost_usd_year=10000,
            individual_unit_costs={},
            annual_production_m3=657000
        )
        
        mass_balance = MassBalance(
            mass_balance_error=1e-6,
            mass_balance_ok=True
        )
        
        results = ROSimulationResults(
            schema_version=SCHEMA_VERSION_RESULTS,
            status="success",
            solve_info=solve_info,
            performance=performance,
            stage_results=[],
            economics=economics,
            mass_balance=mass_balance,
            ion_analysis={},
            artifact_dir="artifacts/test_run_123"
        )
        
        assert results.status == "success"
        assert results.schema_version == SCHEMA_VERSION_RESULTS
        assert len(results.warnings) == 0  # Default empty list


class TestArtifactSchemas:
    """Test artifact-related schemas."""
    
    def test_run_context(self):
        """Test RunContext model."""
        context = RunContext(
            schema_version=SCHEMA_VERSION_CONTEXT,
            created_at=datetime.now(timezone.utc),
            run_id="test_run_123",
            tool_name="test_tool",
            python_version="3.11.0",
            platform="Linux-5.15.0",
            os="Linux",
            git={"commit": "abc123", "branch": "main", "dirty": False},
            packages={"pyomo": "6.7.0", "watertap": "0.11.0"}
        )
        assert context.run_id == "test_run_123"
        assert context.tool_name == "test_tool"
        assert isinstance(context.created_at, datetime)
    
    def test_artifact_file(self):
        """Test ArtifactFile model."""
        file = ArtifactFile(
            filename="input.json",
            path="artifacts/run123/input.json",
            sha256="abcd1234" * 8,  # 64 chars
            size_bytes=1024,
            created_at=datetime.now(timezone.utc)
        )
        assert file.filename == "input.json"
        assert file.size_bytes == 1024
    
    def test_artifact_manifest(self):
        """Test ArtifactManifest model."""
        files = [
            ArtifactFile(
                filename="input.json",
                path="artifacts/run123/input.json",
                sha256="abcd1234" * 8,
                size_bytes=1024,
                created_at=datetime.now(timezone.utc)
            ),
            ArtifactFile(
                filename="results.json",
                path="artifacts/run123/results.json",
                sha256="efgh5678" * 8,
                size_bytes=2048,
                created_at=datetime.now(timezone.utc)
            )
        ]
        
        manifest = ArtifactManifest(
            schema_version=SCHEMA_VERSION_MANIFEST,
            run_id="test_run_123",
            tool_name="test_tool",
            created_at=datetime.now(timezone.utc),
            input_schema_version=SCHEMA_VERSION_INPUT,
            results_schema_version=SCHEMA_VERSION_RESULTS,
            context_schema_version=SCHEMA_VERSION_CONTEXT,
            files=files,
            total_size_bytes=3072
        )
        
        assert manifest.run_id == "test_run_123"
        assert len(manifest.files) == 2
        assert manifest.total_size_bytes == 3072


class TestOptimizationSchemas:
    """Test optimization-related schemas."""
    
    def test_optimization_input(self):
        """Test OptimizationInput model."""
        opt_input = OptimizationInput(
            feed_flow_m3h=100.0,
            water_recovery_fraction=0.75,
            membrane_type="brackish"
        )
        assert opt_input.feed_flow_m3h == 100.0
        assert opt_input.allow_recycle is True  # Default
        assert opt_input.max_recycle_ratio == 0.9  # Default
        
        # With custom values
        opt_input2 = OptimizationInput(
            feed_flow_m3h=200.0,
            water_recovery_fraction=0.85,
            membrane_type="seawater",
            allow_recycle=False,
            flux_targets_lmh=[22.0, 18.0, 15.0],
            flux_tolerance=0.15
        )
        assert not opt_input2.allow_recycle
        assert len(opt_input2.flux_targets_lmh) == 3
    
    def test_optimization_result(self):
        """Test OptimizationResult model."""
        result = OptimizationResult(
            status="success",
            configurations=[
                {"n_stages": 1, "vessels": [6]},
                {"n_stages": 2, "vessels": [4, 2]}
            ],
            summary={"total_configs": 2, "best_recovery": 0.76}
        )
        assert result.status == "success"
        assert len(result.configurations) == 2
        
        # Test validation - status must be success or error
        with pytest.raises(ValidationError):
            OptimizationResult(
                status="invalid_status",
                configurations=[],
                summary={}
            )


class TestSchemaVersions:
    """Test schema version constants."""
    
    def test_version_formats(self):
        """Test that version strings follow semantic versioning."""
        import re
        semver_pattern = r'^\d+\.\d+\.\d+$'
        
        assert re.match(semver_pattern, SCHEMA_VERSION_INPUT)
        assert re.match(semver_pattern, SCHEMA_VERSION_RESULTS)
        assert re.match(semver_pattern, SCHEMA_VERSION_CONTEXT)
        assert re.match(semver_pattern, SCHEMA_VERSION_MANIFEST)
    
    def test_version_consistency(self):
        """Test that version strings are used consistently in models."""
        # Create models with default versions
        sim_input = ROSimulationInput(
            configuration=ROConfiguration(
                n_stages=1,
                stages=[StageConfiguration(
                    stage_number=1,
                    feed_flow_m3h=100,
                    n_vessels=6,
                    vessel_count=6,
                    membrane_area_m2=245.4,
                    stage_recovery=0.5
                )],
                recycle_info=RecycleInfo(uses_recycle=False)
            ),
            feed=FeedComposition(
                salinity_ppm=5000,
                ion_composition_mg_l={"Na+": 1500, "Cl-": 2400}
            )
        )
        assert sim_input.schema_version == SCHEMA_VERSION_INPUT
        
        context = RunContext(
            created_at=datetime.now(timezone.utc),
            run_id="test",
            tool_name="test",
            python_version="3.11",
            platform="Linux",
            os="Linux",
            git={},
            packages={}
        )
        assert context.schema_version == SCHEMA_VERSION_CONTEXT


if __name__ == "__main__":
    pytest.main([__file__, "-v"])