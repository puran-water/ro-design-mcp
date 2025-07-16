#!/usr/bin/env python
"""
Extract concentration polarization data from a clean simulation.
Uses the working code without any modifications.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.simulate_ro import run_ro_simulation

def extract_cp_data():
    """Run simulation and extract CP data."""
    
    # Simple single-stage configuration to avoid multi-stage issues
    config = {
        'feed_flow_m3h': 150,
        'stage_count': 1,
        'n_stages': 1,
        'array_notation': '17',
        'target_recovery': 0.50,  # 50% recovery
        'achieved_recovery': 0.50,
        'total_membrane_area_m2': 4422.04,
        'total_vessels': 17,
        'stages': [
            {
                'stage_number': 1,
                'n_vessels': 17,
                'vessel_count': 17,
                'membrane_area_m2': 4422.04,
                'stage_recovery': 0.50
            }
        ]
    }
    
    print("="*80)
    print("EXTRACTING CONCENTRATION POLARIZATION DATA")
    print("="*80)
    print("\nConfiguration: Single stage, 17 vessels")
    print("Feed: 150 m³/h at 2700 ppm")
    print("Target recovery: 50%")
    print("Using simple NaCl property package")
    
    # Run simulation with simple property package
    print("\nRunning simulation...")
    result = run_ro_simulation(
        configuration=config,
        feed_salinity_ppm=2700,
        feed_temperature_c=25.0,
        membrane_type="brackish",
        membrane_properties=None,
        optimize_pumps=True,
        feed_ion_composition=None  # Use simple property package
    )
    
    if result.get('status') != 'success':
        print(f"\nSimulation failed: {result.get('message')}")
        if 'traceback' in result:
            print("\nTraceback:")
            print(result['traceback'])
        return None
    
    print("\nSimulation successful!")
    
    # Extract results
    print("\n" + "="*80)
    print("SIMULATION RESULTS")
    print("="*80)
    
    # Stage results
    stage_results = result.get('stage_results', [])
    if stage_results:
        stage = stage_results[0]
        print(f"\nOperating Conditions:")
        print(f"  Feed pressure: {stage.get('feed_pressure_bar', 0):.1f} bar")
        print(f"  Feed flow: {stage.get('feed_flow_m3h', 0):.1f} m³/h")
        print(f"  Permeate flow: {stage.get('permeate_flow_m3h', 0):.1f} m³/h")
        print(f"  Concentrate flow: {stage.get('concentrate_flow_m3h', 0):.1f} m³/h")
        print(f"  Feed TDS: {stage.get('feed_tds_ppm', 0):.0f} ppm")
        print(f"  Permeate TDS: {stage.get('permeate_tds_ppm', 0):.0f} ppm")
        print(f"  Concentrate TDS: {stage.get('concentrate_tds_ppm', 0):.0f} ppm")
    
    # SD parameters - this is where CP data would be
    sd_params = result.get('sd_model_parameters', {})
    if not sd_params:
        print("\nNo SD model parameters in results!")
        print("Checking what's available in the result...")
        print("\nAvailable keys in result:")
        for key in result.keys():
            print(f"  - {key}")
        return result
    
    # Extract CP data if available
    if 'stage_1' in sd_params:
        print("\n" + "="*80)
        print("CONCENTRATION POLARIZATION DATA")
        print("="*80)
        
        stage_data = sd_params['stage_1']
        
        # Osmotic pressures
        osm_data = stage_data.get('osmotic_pressures_bar', {})
        if osm_data:
            print("\nOsmotic Pressures (bar):")
            for key, value in osm_data.items():
                print(f"  {key}: {value:.3f}")
            
            # Calculate CP factor
            feed_bulk = osm_data.get('feed_bulk_average', 0)
            feed_interface = osm_data.get('feed_interface_average', 0)
            
            if feed_bulk > 0:
                cp_factor = feed_interface / feed_bulk
                print(f"\nConcentration Polarization Factor: {cp_factor:.2f}")
                
                # Estimate concentrations
                feed_tds = stage.get('feed_tds_ppm', 2700)
                interface_tds = feed_tds * cp_factor
                
                print(f"\nConcentration Analysis:")
                print(f"  Feed bulk TDS: {feed_tds:.0f} ppm")
                print(f"  Interface TDS (estimated): {interface_tds:.0f} ppm")
                print(f"  Increase: {interface_tds - feed_tds:.0f} ppm ({(cp_factor-1)*100:.0f}%)")
        
        # Driving forces
        driving = stage_data.get('driving_forces', {})
        if driving:
            print("\nDriving Forces (bar):")
            for key, value in driving.items():
                print(f"  {key}: {value:.2f}")
        
        # Flux data
        flux_data = stage_data.get('flux_analysis', {})
        if flux_data:
            print("\nFlux Analysis:")
            for key, value in flux_data.items():
                if isinstance(value, (int, float)):
                    print(f"  {key}: {value:.2f}")
    
    return result

def main():
    """Run the extraction."""
    result = extract_cp_data()
    
    if result and result.get('status') == 'success':
        print("\n" + "="*80)
        print("CONCLUSION")
        print("="*80)
        
        # Check if we got CP data
        sd_params = result.get('sd_model_parameters', {})
        if sd_params and 'stage_1' in sd_params:
            osm_data = sd_params['stage_1'].get('osmotic_pressures_bar', {})
            feed_bulk = osm_data.get('feed_bulk_average', 0)
            feed_interface = osm_data.get('feed_interface_average', 0)
            
            if feed_bulk > 0 and feed_interface > 0:
                cp_factor = feed_interface / feed_bulk
                print(f"\nACTUAL CONCENTRATION POLARIZATION FACTOR: {cp_factor:.2f}")
                
                if cp_factor > 2.0:
                    print("\nHIGH concentration polarization confirmed!")
                    print("This explains the high feed pressures.")
                elif cp_factor > 1.5:
                    print("\nMODERATE concentration polarization detected.")
                    print("This partially explains the elevated pressures.")
                else:
                    print("\nLOW concentration polarization.")
                    print("CP is NOT the main cause of high pressures.")
            else:
                print("\nCould not calculate CP factor from results.")
        else:
            print("\nNo SD parameters available to analyze CP.")
            print("The simulation may not be configured to output this data.")

if __name__ == "__main__":
    main()