#!/usr/bin/env python3
"""
Quick diagnostic test for immediate FBBT failure analysis.

This script provides a simple way to test specific configurations
and get detailed diagnostic information about failures.
"""

import sys
import logging
from pathlib import Path
import json
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from pyomo.environ import ConcreteModel, value, units as pyunits, TransformationFactory
from idaes.core import FlowsheetBlock
from idaes.core.util.model_diagnostics import DiagnosticsToolbox
from idaes.models.unit_models import Feed, Product
from watertap.unit_models.reverse_osmosis_0D import (
    ReverseOsmosis0D,
    ConcentrationPolarizationType,
    MassTransferCoefficient,
    PressureChangeType
)
from watertap.property_models.NaCl_prop_pack import NaClParameterBlock

from utils.ro_initialization_debug import (
    FluxDebugLogger,
    initialize_ro_unit_with_debug,
    pre_fbbt_flux_check,
    diagnose_ro_flux_bounds
)
from utils.ro_initialization import (
    calculate_required_pressure,
    calculate_osmotic_pressure,
    validate_flux_bounds
)


def run_diagnostic_test(
    A_w: float = 1.6e-11,
    B_s: float = 1e-8,
    feed_pressure_bar: float = 25,
    feed_tds_ppm: float = 1000,
    recovery: float = 0.5,
    output_file: str = None
):
    """
    Run a quick diagnostic test for a specific configuration.
    
    Args:
        A_w: Water permeability coefficient (m/s/Pa)
        B_s: Salt permeability coefficient (m/s)
        feed_pressure_bar: Feed pressure in bar
        feed_tds_ppm: Feed TDS in ppm
        recovery: Target recovery fraction
        output_file: Optional output file for results
    """
    print("="*80)
    print("RO INITIALIZATION DIAGNOSTIC TEST")
    print("="*80)
    print(f"Configuration:")
    print(f"  Membrane A_w: {A_w:.2e} m/s/Pa")
    print(f"  Membrane B_s: {B_s:.2e} m/s")
    print(f"  Feed pressure: {feed_pressure_bar} bar")
    print(f"  Feed TDS: {feed_tds_ppm} ppm")
    print(f"  Target recovery: {recovery:.1%}")
    print()
    
    # Create debug logger
    log_filename = output_file or f"diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logger = FluxDebugLogger(log_filename, console_level=logging.INFO)
    
    results = {
        'configuration': {
            'A_w': A_w,
            'B_s': B_s,
            'feed_pressure_bar': feed_pressure_bar,
            'feed_tds_ppm': feed_tds_ppm,
            'recovery': recovery
        },
        'diagnostics': {},
        'recommendations': []
    }
    
    try:
        # Step 1: Calculate expected conditions
        print("\nStep 1: Calculating expected operating conditions...")
        
        water_density = 1000  # kg/m³
        feed_pressure_pa = feed_pressure_bar * 1e5
        feed_osmotic = calculate_osmotic_pressure(feed_tds_ppm)
        
        # Calculate expected flux
        net_driving = feed_pressure_pa - 101325 - feed_osmotic
        expected_flux = A_w * water_density * net_driving
        
        print(f"  Feed osmotic pressure: {feed_osmotic/1e5:.2f} bar")
        print(f"  Net driving pressure: {net_driving/1e5:.2f} bar")
        print(f"  Expected flux: {expected_flux:.4f} kg/m²/s")
        print(f"  WaterTAP flux bounds: [0.0001, 0.03] kg/m²/s")
        
        results['diagnostics']['expected_flux'] = expected_flux
        results['diagnostics']['flux_bounds'] = [0.0001, 0.03]
        
        # Check if flux is within bounds
        flux_ok = 0.0001 <= expected_flux <= 0.03
        print(f"  Flux within bounds: {'YES' if flux_ok else 'NO'}")
        
        if not flux_ok:
            print(f"  WARNING: Expected flux exceeds bounds!")
            if expected_flux > 0.03:
                max_safe_pressure = (0.025 / (A_w * water_density)) + 101325 + feed_osmotic
                print(f"  Maximum safe pressure: {max_safe_pressure/1e5:.1f} bar")
                results['recommendations'].append(
                    f"Reduce feed pressure to max {max_safe_pressure/1e5:.1f} bar"
                )
        
        # Step 2: Build test model
        print("\nStep 2: Building test model...")
        
        m = ConcreteModel()
        m.fs = FlowsheetBlock(dynamic=False)
        
        # Property package
        m.fs.properties = NaClParameterBlock()
        
        # Units
        m.fs.feed = Feed(property_package=m.fs.properties)
        m.fs.ro = ReverseOsmosis0D(
            property_package=m.fs.properties,
            has_pressure_change=True,
            pressure_change_type=PressureChangeType.fixed_per_unit_length,
            mass_transfer_coefficient=MassTransferCoefficient.calculated,
            concentration_polarization_type=ConcentrationPolarizationType.calculated,
            transport_model='SD'
        )
        m.fs.product = Product(property_package=m.fs.properties)
        
        # Set membrane properties after unit is constructed
        # For SD model, A_comp is a scalar parameter
        m.fs.ro.A_comp.fix(A_w)
        m.fs.ro.B_comp[0, 'NaCl'].fix(B_s)  # NaCl property package uses NaCl, not TDS
        m.fs.ro.area.fix(10)  # 10 m² for testing
        
        # Set feed conditions
        feed_tds_kg_m3 = feed_tds_ppm / 1000
        nacl_mass_frac = feed_tds_kg_m3 / 1000  # Convert kg/m³ to mass fraction
        water_mass_frac = 1 - nacl_mass_frac
        total_flow = 1.0  # kg/s
        
        m.fs.feed.flow_mass_phase_comp[0, 'Liq', 'H2O'].fix(total_flow * water_mass_frac)
        m.fs.feed.flow_mass_phase_comp[0, 'Liq', 'NaCl'].fix(total_flow * nacl_mass_frac)
        m.fs.feed.temperature[0].fix(298.15)
        m.fs.feed.pressure[0].fix(feed_pressure_pa)
        
        # RO specifications
        m.fs.ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'].fix(recovery)
        m.fs.ro.deltaP[0].fix(-0.5e5)  # 0.5 bar pressure drop
        
        # Initialize feed
        m.fs.feed.initialize()
        
        print("  Model built successfully")
        
        # Step 3: Pre-FBBT check
        print("\nStep 3: Pre-FBBT flux check...")
        
        flux_safe = pre_fbbt_flux_check(m.fs.ro, A_w, logger)
        results['diagnostics']['pre_fbbt_check'] = 'passed' if flux_safe else 'failed'
        
        # Step 4: Run diagnostics toolbox
        print("\nStep 4: Running model diagnostics...")
        
        dt = DiagnosticsToolbox(m.fs.ro)
        
        # Check structural issues
        print("  Checking structural issues...")
        try:
            dt.assert_no_structural_warnings()
            print("  No structural warnings")
        except AssertionError as e:
            print(f"  Structural warnings detected: {str(e)}")
            results['diagnostics']['structural_warnings'] = str(e)
        
        # Step 5: Attempt initialization
        print("\nStep 5: Attempting initialization with debug logging...")
        
        try:
            initialize_ro_unit_with_debug(
                m.fs.ro,
                target_recovery=recovery,
                A_w=A_w,
                B_s=B_s,
                logger=logger,
                verbose=True
            )
            print("\n  Initialization SUCCEEDED!")
            results['diagnostics']['initialization'] = 'passed'
            
            # Get final flux
            final_flux = value(m.fs.ro.flux_mass_phase_comp[0, 0, 'Liq', 'H2O'])
            print(f"  Final water flux: {final_flux:.4f} kg/m²/s")
            results['diagnostics']['final_flux'] = final_flux
            
        except Exception as e:
            print(f"\n  Initialization FAILED: {str(e)}")
            results['diagnostics']['initialization'] = 'failed'
            results['diagnostics']['error'] = str(e)
            
            # Try to get more info
            print("\n  Attempting additional diagnostics...")
            try:
                diagnose_ro_flux_bounds(m.fs.ro, A_w, logger)
            except:
                print("  Additional diagnostics failed")
        
        # Step 6: Summary and recommendations
        print("\n" + "="*80)
        print("DIAGNOSTIC SUMMARY")
        print("="*80)
        
        # Summarize violations
        logger.summarize_violations()
        
        # Generate recommendations
        print("\nRECOMMENDATIONS:")
        
        if results['diagnostics'].get('initialization') == 'failed':
            if expected_flux > 0.03:
                print("1. Flux exceeds upper bound - pressure too high for membrane permeability")
                print(f"2. Reduce pressure to max {(0.025/(A_w*water_density) + 101325 + feed_osmotic)/1e5:.1f} bar")
                print("3. Or use a lower permeability membrane")
                print("4. Enable staged initialization for high permeability membranes")
            elif expected_flux < 0.0001:
                print("1. Flux below lower bound - pressure too low")
                print("2. Increase feed pressure")
            else:
                print("1. Check for numerical scaling issues")
                print("2. Try staged initialization")
                print("3. Review membrane property values")
        else:
            print("No issues detected - configuration works with standard initialization")
        
        # Save results
        results_file = Path(log_filename).with_suffix('.json')
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {results_file}")
        
    except Exception as e:
        print(f"\nDiagnostic test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()
        results['diagnostics']['exception'] = str(e)
    
    print(f"\nDetailed log saved to: {log_filename}")
    return results


def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Quick diagnostic test for RO initialization failures"
    )
    parser.add_argument('--A_w', type=float, default=1.6e-11,
                       help='Water permeability coefficient (m/s/Pa)')
    parser.add_argument('--B_s', type=float, default=1e-8,
                       help='Salt permeability coefficient (m/s)')
    parser.add_argument('--pressure', type=float, default=25,
                       help='Feed pressure (bar)')
    parser.add_argument('--tds', type=float, default=1000,
                       help='Feed TDS (ppm)')
    parser.add_argument('--recovery', type=float, default=0.5,
                       help='Target recovery fraction')
    parser.add_argument('--output', type=str,
                       help='Output file name')
    
    args = parser.parse_args()
    
    # Run diagnostic test
    run_diagnostic_test(
        A_w=args.A_w,
        B_s=args.B_s,
        feed_pressure_bar=args.pressure,
        feed_tds_ppm=args.tds,
        recovery=args.recovery,
        output_file=args.output
    )


if __name__ == "__main__":
    main()