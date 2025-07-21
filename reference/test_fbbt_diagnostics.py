#!/usr/bin/env python3
"""
Comprehensive test script for diagnosing FBBT and initialization failures in RO systems.

This script systematically tests various scenarios to identify failure patterns
and provide actionable diagnostics for fixing initialization issues.
"""

import json
import sys
import logging
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse

# IDAES and Pyomo imports
from pyomo.environ import (
    ConcreteModel, value, Var, units as pyunits,
    TransformationFactory, SolverFactory
)
from idaes.core import FlowsheetBlock
from idaes.core.util.model_statistics import degrees_of_freedom
from idaes.core.util.scaling import calculate_scaling_factors
from idaes.core.util.initialization import propagate_state
from idaes.models.unit_models import Feed, Product
import idaes.logger as idaeslog

# WaterTAP imports
from watertap.unit_models.reverse_osmosis_0D import (
    ReverseOsmosis0D,
    ConcentrationPolarizationType,
    MassTransferCoefficient,
    PressureChangeType
)
from watertap.property_models.NaCl_prop_pack import NaClParameterBlock
from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock

# Local imports
sys.path.insert(0, str(Path(__file__).parent))
from utils.ro_initialization_debug import (
    FluxDebugLogger,
    initialize_ro_unit_with_debug,
    pre_fbbt_flux_check,
    apply_flux_safe_bounds,
    diagnose_ro_flux_bounds
)
from utils.ro_initialization import (
    calculate_required_pressure,
    initialize_ro_unit_elegant,
    initialize_ro_unit_staged,
    validate_flux_bounds,
    calculate_safe_initialization_pressure
)


class TestResult:
    """Container for test results."""
    def __init__(self, test_name: str, parameters: Dict[str, Any]):
        self.test_name = test_name
        self.parameters = parameters
        self.passed = False
        self.failure_type = None
        self.error_message = None
        self.diagnostics = {}
        self.recommendations = []
        self.execution_time = 0.0
        self.flux_data = {}
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'test_name': self.test_name,
            'parameters': self.parameters,
            'passed': self.passed,
            'failure_type': self.failure_type,
            'error_message': self.error_message,
            'diagnostics': self.diagnostics,
            'recommendations': self.recommendations,
            'execution_time': self.execution_time,
            'flux_data': self.flux_data
        }


class FBBTTestSuite:
    """Test suite for FBBT and initialization diagnostics."""
    
    def __init__(self, output_dir: str = "test_results", debug: bool = True):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.debug = debug
        self.results = []
        
        # Configure logging
        self.logger = logging.getLogger("fbbt_test")
        self.logger.setLevel(logging.DEBUG if debug else logging.INFO)
        
        # File handler
        log_file = self.output_dir / f"test_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        fh = logging.FileHandler(log_file)
        fh.setLevel(logging.DEBUG)
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)
        
        self.logger.info(f"Test suite initialized. Output directory: {self.output_dir}")
        
    def create_test_scenarios(self) -> List[Dict[str, Any]]:
        """Create comprehensive test scenarios."""
        scenarios = []
        
        # Membrane permeabilities to test (m/s/Pa)
        A_w_values = [
            9.63e-12,   # BW30-400 (standard)
            1.2e-11,    # Medium-high permeability
            1.6e-11,    # ECO PRO-400 (high)
            2.0e-11,    # Very high permeability
        ]
        
        # Pressure values to test (bar)
        pressure_values = [10, 20, 30, 40, 50]
        
        # TDS values to test (ppm)
        tds_values = [100, 1000, 5000, 10000, 35000]
        
        # Recovery values to test
        recovery_values = [0.1, 0.3, 0.5, 0.7, 0.9]
        
        # Test 1: Basic permeability sweep at standard conditions
        for A_w in A_w_values:
            scenarios.append({
                'name': f'basic_permeability_A_w_{A_w:.2e}',
                'A_w': A_w,
                'B_s': 1e-8,
                'feed_pressure': 25,  # bar
                'feed_tds': 1000,     # ppm
                'recovery': 0.5,
                'test_type': 'permeability_sweep'
            })
        
        # Test 2: Pressure sweep for high permeability membrane
        for pressure in pressure_values:
            scenarios.append({
                'name': f'pressure_sweep_{pressure}bar',
                'A_w': 1.6e-11,  # High permeability
                'B_s': 1e-8,
                'feed_pressure': pressure,
                'feed_tds': 1000,
                'recovery': 0.5,
                'test_type': 'pressure_sweep'
            })
        
        # Test 3: TDS sweep
        for tds in tds_values:
            scenarios.append({
                'name': f'tds_sweep_{tds}ppm',
                'A_w': 1.6e-11,
                'B_s': 1e-8,
                'feed_pressure': 25,
                'feed_tds': tds,
                'recovery': 0.5,
                'test_type': 'tds_sweep'
            })
        
        # Test 4: Recovery sweep
        for recovery in recovery_values:
            scenarios.append({
                'name': f'recovery_sweep_{recovery:.1f}',
                'A_w': 1.6e-11,
                'B_s': 1e-8,
                'feed_pressure': 25,
                'feed_tds': 1000,
                'recovery': recovery,
                'test_type': 'recovery_sweep'
            })
        
        # Test 5: Edge cases
        edge_cases = [
            {
                'name': 'edge_high_perm_high_pressure',
                'A_w': 2.0e-11,
                'B_s': 1e-8,
                'feed_pressure': 50,
                'feed_tds': 100,
                'recovery': 0.5,
                'test_type': 'edge_case'
            },
            {
                'name': 'edge_high_perm_high_tds',
                'A_w': 1.6e-11,
                'B_s': 1e-8,
                'feed_pressure': 40,
                'feed_tds': 35000,
                'recovery': 0.3,
                'test_type': 'edge_case'
            },
            {
                'name': 'edge_low_perm_high_recovery',
                'A_w': 9.63e-12,
                'B_s': 1e-8,
                'feed_pressure': 50,
                'feed_tds': 1000,
                'recovery': 0.9,
                'test_type': 'edge_case'
            }
        ]
        scenarios.extend(edge_cases)
        
        return scenarios
    
    def build_test_model(self, scenario: Dict[str, Any]) -> ConcreteModel:
        """Build a minimal test model for a scenario."""
        m = ConcreteModel()
        m.fs = FlowsheetBlock(dynamic=False)
        
        # Use standard NaCl property package for simplicity
        m.fs.properties = NaClParameterBlock()
        
        # Create feed
        m.fs.feed = Feed(property_package=m.fs.properties)
        
        # Create RO unit with SD model
        m.fs.ro = ReverseOsmosis0D(
            property_package=m.fs.properties,
            has_pressure_change=True,
            pressure_change_type=PressureChangeType.fixed_per_unit_length,
            mass_transfer_coefficient=MassTransferCoefficient.calculated,
            concentration_polarization_type=ConcentrationPolarizationType.calculated,
            transport_model='SD'  # Use SD model as in templates
        )
        
        # Create product
        m.fs.product = Product(property_package=m.fs.properties)
        
        # Set membrane properties
        A_w = scenario['A_w']
        B_s = scenario['B_s']
        
        # For SD model, A_comp is a scalar parameter
        m.fs.ro.A_comp.fix(A_w)
        m.fs.ro.B_comp[0, 'NaCl'].fix(B_s)
        
        # Set membrane area (10 m² for testing)
        m.fs.ro.area.set_value(10)
        
        # Set operating conditions
        feed_pressure_pa = scenario['feed_pressure'] * 1e5  # Convert bar to Pa
        feed_tds_kg_m3 = scenario['feed_tds'] / 1000  # Convert ppm to kg/m³
        
        # Calculate component flows (1 kg/s total feed)
        total_flow = 1.0  # kg/s
        water_mass_frac = 1 - (feed_tds_kg_m3 / 1000)
        
        m.fs.feed.flow_mass_phase_comp[0, 'Liq', 'H2O'].fix(total_flow * water_mass_frac)
        m.fs.feed.flow_mass_phase_comp[0, 'Liq', 'NaCl'].fix(total_flow * (1 - water_mass_frac))
        m.fs.feed.temperature[0].fix(298.15)
        m.fs.feed.pressure[0].fix(feed_pressure_pa)
        
        # Fix RO conditions
        m.fs.ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'].fix(scenario['recovery'])
        m.fs.ro.deltaP[0].fix(-0.5e5)  # 0.5 bar pressure drop
        
        # Initialize feed
        m.fs.feed.initialize()
        
        return m
    
    def run_single_test(self, scenario: Dict[str, Any]) -> TestResult:
        """Run a single test scenario."""
        result = TestResult(scenario['name'], scenario)
        start_time = datetime.now()
        
        self.logger.info(f"\nRunning test: {scenario['name']}")
        self.logger.info(f"Parameters: A_w={scenario['A_w']:.2e}, P={scenario['feed_pressure']}bar, "
                        f"TDS={scenario['feed_tds']}ppm, Rec={scenario['recovery']}")
        
        try:
            # Build model
            model = self.build_test_model(scenario)
            
            # Create debug logger for this test
            debug_logger = FluxDebugLogger(
                filename=str(self.output_dir / f"flux_debug_{scenario['name']}.log"),
                console_level=logging.WARNING
            )
            
            # Pre-FBBT check
            flux_ok = pre_fbbt_flux_check(model.fs.ro, scenario['A_w'], debug_logger)
            result.diagnostics['pre_fbbt_flux_ok'] = flux_ok
            
            if not flux_ok:
                self.logger.warning("Pre-FBBT check failed - flux bounds will be violated")
            
            # Test 1: Standard elegant initialization
            try:
                self.logger.debug("Testing elegant initialization...")
                initialize_ro_unit_elegant(
                    model.fs.ro,
                    target_recovery=scenario['recovery'],
                    verbose=False,
                    debug_logger=debug_logger
                )
                result.diagnostics['elegant_init'] = 'passed'
                self.logger.info("Elegant initialization: PASSED")
            except Exception as e:
                result.diagnostics['elegant_init'] = 'failed'
                result.diagnostics['elegant_init_error'] = str(e)
                self.logger.warning(f"Elegant initialization failed: {str(e)}")
                
                # Test 2: Try staged initialization
                try:
                    self.logger.debug("Testing staged initialization...")
                    # Reset model
                    model = self.build_test_model(scenario)
                    initialize_ro_unit_staged(
                        model.fs.ro,
                        A_w=scenario['A_w'],
                        B_s=scenario['B_s'],
                        target_recovery=scenario['recovery'],
                        verbose=False,
                        debug_logger=debug_logger
                    )
                    result.diagnostics['staged_init'] = 'passed'
                    self.logger.info("Staged initialization: PASSED")
                except Exception as e2:
                    result.diagnostics['staged_init'] = 'failed'
                    result.diagnostics['staged_init_error'] = str(e2)
                    self.logger.warning(f"Staged initialization also failed: {str(e2)}")
                    
                    # Both failed - this is a hard failure
                    result.passed = False
                    result.failure_type = 'initialization_failed'
                    result.error_message = str(e)
            
            # If at least one initialization worked, test is passed
            if result.diagnostics.get('elegant_init') == 'passed' or \
               result.diagnostics.get('staged_init') == 'passed':
                result.passed = True
                
                # Diagnose final state
                diagnose_ro_flux_bounds(model.fs.ro, scenario['A_w'], debug_logger)
                
                # Extract flux data
                try:
                    flux_h2o = value(model.fs.ro.flux_mass_phase_comp[0, 0, 'Liq', 'H2O'])
                    result.flux_data['final_flux'] = flux_h2o
                    result.flux_data['flux_margin'] = (0.03 - flux_h2o) / 0.03 * 100  # % margin from upper bound
                except:
                    pass
            
            # Analyze debug logger results
            result.diagnostics['flux_violations'] = len(debug_logger.bounds_violations)
            if debug_logger.bounds_violations:
                result.diagnostics['max_violation_flux'] = max(
                    v['flux'] for v in debug_logger.bounds_violations
                )
            
            # Generate recommendations
            self._generate_recommendations(result, scenario, debug_logger)
            
        except Exception as e:
            self.logger.error(f"Test failed with exception: {str(e)}")
            self.logger.debug(traceback.format_exc())
            result.passed = False
            result.failure_type = 'exception'
            result.error_message = str(e)
            result.diagnostics['traceback'] = traceback.format_exc()
        
        # Record execution time
        result.execution_time = (datetime.now() - start_time).total_seconds()
        
        return result
    
    def _generate_recommendations(self, result: TestResult, scenario: Dict[str, Any], 
                                 debug_logger: FluxDebugLogger) -> None:
        """Generate actionable recommendations based on test results."""
        
        # If test passed with elegant init, no recommendations needed
        if result.diagnostics.get('elegant_init') == 'passed':
            result.recommendations.append("No changes needed - standard initialization works")
            return
        
        # If only staged init worked
        if result.diagnostics.get('staged_init') == 'passed':
            result.recommendations.append("Use staged initialization for this membrane")
            result.recommendations.append(f"Set A_w threshold to {scenario['A_w']:.2e} m/s/Pa")
        
        # If pre-FBBT check failed
        if not result.diagnostics.get('pre_fbbt_flux_ok', True):
            # Calculate maximum safe pressure
            water_density = 1000
            max_flux = 0.025  # 83% of upper bound
            A_w = scenario['A_w']
            
            # Approximate osmotic pressure
            feed_osmotic = 0.7 * (scenario['feed_tds'] / 1000) * 1e5
            max_pressure = (max_flux / (A_w * water_density)) + 101325 + feed_osmotic
            max_pressure_bar = max_pressure / 1e5
            
            result.recommendations.append(f"Reduce feed pressure to max {max_pressure_bar:.1f} bar")
            result.recommendations.append("Consider using a lower permeability membrane")
            result.recommendations.append("Enable flux-safe bounds in initialization")
        
        # If flux violations occurred
        if result.diagnostics.get('flux_violations', 0) > 0:
            max_violation = result.diagnostics.get('max_violation_flux', 0)
            result.recommendations.append(f"Maximum flux violation: {max_violation:.4f} kg/m²/s")
            result.recommendations.append("Implement flux capping in pressure calculations")
        
        # Recovery-specific recommendations
        if scenario['recovery'] > 0.7:
            result.recommendations.append("High recovery may require multi-stage design")
            result.recommendations.append("Consider lower recovery in first stage")
        
        # TDS-specific recommendations
        if scenario['feed_tds'] > 10000:
            result.recommendations.append("High TDS requires careful pressure management")
            result.recommendations.append("Consider pretreatment to reduce TDS")
    
    def run_test_suite(self, scenarios: Optional[List[Dict[str, Any]]] = None,
                      parallel: bool = False, max_workers: int = 4) -> None:
        """Run the complete test suite."""
        if scenarios is None:
            scenarios = self.create_test_scenarios()
        
        self.logger.info(f"Starting test suite with {len(scenarios)} scenarios")
        
        if parallel and len(scenarios) > 1:
            # Run tests in parallel
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                future_to_scenario = {
                    executor.submit(self.run_single_test, scenario): scenario
                    for scenario in scenarios
                }
                
                for future in as_completed(future_to_scenario):
                    scenario = future_to_scenario[future]
                    try:
                        result = future.result()
                        self.results.append(result)
                        self._log_result(result)
                    except Exception as e:
                        self.logger.error(f"Test {scenario['name']} failed: {str(e)}")
        else:
            # Run tests sequentially
            for scenario in scenarios:
                result = self.run_single_test(scenario)
                self.results.append(result)
                self._log_result(result)
    
    def _log_result(self, result: TestResult) -> None:
        """Log individual test result."""
        status = "PASSED" if result.passed else "FAILED"
        self.logger.info(f"Test {result.test_name}: {status} ({result.execution_time:.2f}s)")
        
        if not result.passed:
            self.logger.info(f"  Failure type: {result.failure_type}")
            self.logger.info(f"  Error: {result.error_message}")
        
        if result.recommendations:
            self.logger.info("  Recommendations:")
            for rec in result.recommendations:
                self.logger.info(f"    - {rec}")
    
    def generate_report(self) -> None:
        """Generate comprehensive test report."""
        if not self.results:
            self.logger.warning("No test results to report")
            return
        
        # Create summary DataFrame
        summary_data = []
        for result in self.results:
            summary_data.append({
                'Test': result.test_name,
                'A_w': result.parameters['A_w'],
                'Pressure': result.parameters['feed_pressure'],
                'TDS': result.parameters['feed_tds'],
                'Recovery': result.parameters['recovery'],
                'Passed': result.passed,
                'Failure Type': result.failure_type,
                'Elegant Init': result.diagnostics.get('elegant_init', 'not_tested'),
                'Staged Init': result.diagnostics.get('staged_init', 'not_tested'),
                'Flux Violations': result.diagnostics.get('flux_violations', 0),
                'Time (s)': result.execution_time
            })
        
        df_summary = pd.DataFrame(summary_data)
        
        # Save summary to CSV
        summary_file = self.output_dir / 'test_summary.csv'
        df_summary.to_csv(summary_file, index=False)
        self.logger.info(f"Summary saved to {summary_file}")
        
        # Generate detailed report
        report_file = self.output_dir / 'test_report.md'
        with open(report_file, 'w') as f:
            f.write("# FBBT Initialization Test Report\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # Overall statistics
            total_tests = len(self.results)
            passed_tests = sum(1 for r in self.results if r.passed)
            pass_rate = passed_tests / total_tests * 100
            
            f.write("## Summary\n\n")
            f.write(f"- Total tests: {total_tests}\n")
            f.write(f"- Passed: {passed_tests}\n")
            f.write(f"- Failed: {total_tests - passed_tests}\n")
            f.write(f"- Pass rate: {pass_rate:.1f}%\n\n")
            
            # Failure analysis
            f.write("## Failure Analysis\n\n")
            
            # Group by failure type
            failure_types = {}
            for result in self.results:
                if not result.passed:
                    ft = result.failure_type or 'unknown'
                    if ft not in failure_types:
                        failure_types[ft] = []
                    failure_types[ft].append(result)
            
            for ft, failed_results in failure_types.items():
                f.write(f"### {ft} ({len(failed_results)} cases)\n\n")
                for result in failed_results[:3]:  # Show first 3 examples
                    f.write(f"- **{result.test_name}**\n")
                    f.write(f"  - Parameters: A_w={result.parameters['A_w']:.2e}, "
                           f"P={result.parameters['feed_pressure']}bar\n")
                    f.write(f"  - Error: {result.error_message}\n")
                    if result.recommendations:
                        f.write("  - Recommendations:\n")
                        for rec in result.recommendations[:2]:
                            f.write(f"    - {rec}\n")
                f.write("\n")
            
            # Success patterns
            f.write("## Success Patterns\n\n")
            
            # Analyze which configurations always work
            always_work = []
            sometimes_work = []
            never_work = []
            
            # Group by A_w value
            a_w_groups = {}
            for result in self.results:
                a_w = result.parameters['A_w']
                if a_w not in a_w_groups:
                    a_w_groups[a_w] = []
                a_w_groups[a_w].append(result)
            
            for a_w, results in sorted(a_w_groups.items()):
                passed = sum(1 for r in results if r.passed)
                total = len(results)
                pass_rate = passed / total * 100
                
                f.write(f"### A_w = {a_w:.2e} m/s/Pa\n")
                f.write(f"- Pass rate: {pass_rate:.1f}% ({passed}/{total})\n")
                
                if pass_rate == 100:
                    f.write("- Status: Always works with standard initialization\n")
                elif pass_rate > 0:
                    f.write("- Status: Sometimes works, may need staged initialization\n")
                    # Find conditions that work
                    working_conditions = [r for r in results if r.passed]
                    if working_conditions:
                        max_pressure = max(r.parameters['feed_pressure'] for r in working_conditions)
                        f.write(f"- Max working pressure: {max_pressure} bar\n")
                else:
                    f.write("- Status: Always fails, needs special handling\n")
                f.write("\n")
            
            # Recommendations summary
            f.write("## General Recommendations\n\n")
            
            # Collect all unique recommendations
            all_recommendations = set()
            for result in self.results:
                all_recommendations.update(result.recommendations)
            
            # Group and prioritize recommendations
            pressure_recs = [r for r in all_recommendations if 'pressure' in r.lower()]
            membrane_recs = [r for r in all_recommendations if 'membrane' in r.lower()]
            init_recs = [r for r in all_recommendations if 'initialization' in r.lower()]
            other_recs = [r for r in all_recommendations 
                         if r not in pressure_recs + membrane_recs + init_recs]
            
            if pressure_recs:
                f.write("### Pressure Management\n")
                for rec in sorted(pressure_recs)[:5]:
                    f.write(f"- {rec}\n")
                f.write("\n")
            
            if membrane_recs:
                f.write("### Membrane Selection\n")
                for rec in sorted(membrane_recs)[:5]:
                    f.write(f"- {rec}\n")
                f.write("\n")
            
            if init_recs:
                f.write("### Initialization Strategy\n")
                for rec in sorted(init_recs)[:5]:
                    f.write(f"- {rec}\n")
                f.write("\n")
        
        self.logger.info(f"Detailed report saved to {report_file}")
        
        # Save full results as JSON
        results_file = self.output_dir / 'test_results.json'
        with open(results_file, 'w') as f:
            json.dump([r.to_dict() for r in self.results], f, indent=2)
        self.logger.info(f"Full results saved to {results_file}")
    
    def plot_failure_boundaries(self) -> None:
        """Create visualization of failure boundaries."""
        try:
            import matplotlib.pyplot as plt
            import seaborn as sns
            
            # Create DataFrame for plotting
            plot_data = []
            for result in self.results:
                plot_data.append({
                    'A_w': result.parameters['A_w'],
                    'Pressure': result.parameters['feed_pressure'],
                    'TDS': result.parameters['feed_tds'],
                    'Recovery': result.parameters['recovery'],
                    'Passed': 1 if result.passed else 0,
                    'Init_Method': 'Elegant' if result.diagnostics.get('elegant_init') == 'passed' 
                                  else ('Staged' if result.diagnostics.get('staged_init') == 'passed'
                                       else 'Failed')
                })
            
            df_plot = pd.DataFrame(plot_data)
            
            # Create figure with subplots
            fig, axes = plt.subplots(2, 2, figsize=(12, 10))
            fig.suptitle('FBBT Initialization Test Results', fontsize=16)
            
            # Plot 1: Pressure vs A_w
            ax = axes[0, 0]
            for init_method in ['Elegant', 'Staged', 'Failed']:
                data = df_plot[df_plot['Init_Method'] == init_method]
                if not data.empty:
                    ax.scatter(data['A_w'] * 1e12, data['Pressure'], 
                             label=init_method, alpha=0.7, s=100)
            ax.set_xlabel('A_w (x10⁻¹² m/s/Pa)')
            ax.set_ylabel('Pressure (bar)')
            ax.set_title('Initialization Success by Membrane Permeability')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            # Plot 2: Pass rate by A_w
            ax = axes[0, 1]
            a_w_pass_rates = df_plot.groupby('A_w')['Passed'].agg(['mean', 'count'])
            ax.bar(range(len(a_w_pass_rates)), a_w_pass_rates['mean'] * 100,
                   tick_label=[f"{a_w*1e12:.1f}" for a_w in a_w_pass_rates.index])
            ax.set_xlabel('A_w (x10⁻¹² m/s/Pa)')
            ax.set_ylabel('Pass Rate (%)')
            ax.set_title('Pass Rate by Membrane Permeability')
            ax.set_ylim(0, 105)
            
            # Add count labels
            for i, (_, row) in enumerate(a_w_pass_rates.iterrows()):
                ax.text(i, row['mean'] * 100 + 2, f"n={row['count']}", 
                       ha='center', va='bottom')
            
            # Plot 3: Heatmap of pass/fail
            ax = axes[1, 0]
            pivot_data = df_plot.pivot_table(
                values='Passed', 
                index='Pressure', 
                columns='A_w',
                aggfunc='mean'
            )
            sns.heatmap(pivot_data, annot=True, fmt='.0%', cmap='RdYlGn',
                       ax=ax, cbar_kws={'label': 'Pass Rate'})
            ax.set_xlabel('A_w (m/s/Pa)')
            ax.set_ylabel('Pressure (bar)')
            ax.set_title('Pass Rate Heatmap')
            
            # Plot 4: Failure type distribution
            ax = axes[1, 1]
            failure_counts = {}
            for result in self.results:
                if not result.passed:
                    ft = result.failure_type or 'unknown'
                    failure_counts[ft] = failure_counts.get(ft, 0) + 1
            
            if failure_counts:
                ax.pie(failure_counts.values(), labels=failure_counts.keys(),
                      autopct='%1.1f%%', startangle=90)
                ax.set_title('Failure Type Distribution')
            else:
                ax.text(0.5, 0.5, 'No Failures', ha='center', va='center',
                       transform=ax.transAxes, fontsize=20)
                ax.set_xlim(-1, 1)
                ax.set_ylim(-1, 1)
            
            plt.tight_layout()
            
            # Save figure
            plot_file = self.output_dir / 'test_results_visualization.png'
            plt.savefig(plot_file, dpi=300, bbox_inches='tight')
            plt.close()
            
            self.logger.info(f"Visualization saved to {plot_file}")
            
        except ImportError:
            self.logger.warning("Matplotlib not available, skipping visualization")


def main():
    """Main function for running tests."""
    parser = argparse.ArgumentParser(
        description="Diagnose FBBT and initialization failures in RO systems"
    )
    parser.add_argument(
        '--test-suite',
        choices=['basic', 'full', 'custom'],
        default='basic',
        help='Test suite to run'
    )
    parser.add_argument(
        '--parallel',
        action='store_true',
        help='Run tests in parallel'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=4,
        help='Number of parallel workers'
    )
    parser.add_argument(
        '--output-dir',
        default='test_results',
        help='Output directory for results'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--scenarios',
        type=str,
        help='JSON file with custom test scenarios'
    )
    
    args = parser.parse_args()
    
    # Create test suite
    test_suite = FBBTTestSuite(output_dir=args.output_dir, debug=args.debug)
    
    # Load scenarios
    if args.scenarios:
        with open(args.scenarios, 'r') as f:
            scenarios = json.load(f)
    elif args.test_suite == 'basic':
        # Create a subset of scenarios for quick testing
        all_scenarios = test_suite.create_test_scenarios()
        scenarios = [s for s in all_scenarios if s['test_type'] == 'permeability_sweep']
    elif args.test_suite == 'full':
        scenarios = test_suite.create_test_scenarios()
    else:
        scenarios = []
    
    if not scenarios:
        print("No test scenarios defined. Use --scenarios or --test-suite option.")
        return
    
    # Run tests
    print(f"Running {len(scenarios)} test scenarios...")
    test_suite.run_test_suite(
        scenarios=scenarios,
        parallel=args.parallel,
        max_workers=args.workers
    )
    
    # Generate report
    print("\nGenerating test report...")
    test_suite.generate_report()
    test_suite.plot_failure_boundaries()
    
    # Print summary
    total = len(test_suite.results)
    passed = sum(1 for r in test_suite.results if r.passed)
    print(f"\nTest Summary:")
    print(f"  Total tests: {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {total - passed}")
    print(f"  Pass rate: {passed/total*100:.1f}%")
    print(f"\nResults saved to: {test_suite.output_dir}")


if __name__ == "__main__":
    main()