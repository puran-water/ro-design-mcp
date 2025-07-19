#!/usr/bin/env python3
"""
Debug DoF issue in RO model.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.mcas_builder import build_mcas_property_configuration
from utils.ro_model_builder import build_ro_model_mcas
from idaes.core.util.model_statistics import degrees_of_freedom, number_of_unused_variables
from pyomo.environ import value
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def debug_dof():
    """Debug degrees of freedom issue."""
    print("\n" + "="*60)
    print("DEBUGGING DoF ISSUE")
    print("="*60)
    
    # Simple configuration
    configuration = {
        'array_notation': '2:1',
        'feed_flow_m3h': 100,
        'stage_count': 2,
        'n_stages': 2,
        'stages': [
            {'stage_recovery': 0.5, 'stage_number': 1, 'membrane_area_m2': 260},
            {'stage_recovery': 0.4, 'stage_number': 2, 'membrane_area_m2': 260}
        ],
        'recycle_info': {
            'uses_recycle': False,
            'recycle_ratio': 0,
            'recycle_split_ratio': 0
        },
        'feed_salinity_ppm': 2000
    }
    
    # Simple ion composition
    feed_ion_composition = {
        'Na_+': 2000 * 0.393,  # ~39.3% of TDS
        'Cl_-': 2000 * 0.607,  # ~60.7% of TDS
    }
    
    # Build MCAS config
    mcas_config = build_mcas_property_configuration(
        feed_composition=feed_ion_composition,
        include_scaling_ions=True,
        include_ph_species=True
    )
    
    # Build model
    print("\nBuilding model...")
    model = build_ro_model_mcas(
        configuration,
        mcas_config,
        2000,  # feed_salinity_ppm
        25.0,  # feed_temperature_c
        "brackish"  # membrane_type
    )
    
    # Check overall model DOF
    print(f"\nOverall model DOF: {degrees_of_freedom(model)}")
    
    # Check DOF of individual units
    print("\nDOF by unit:")
    units = [
        ("fresh_feed", model.fs.fresh_feed),
        ("feed_mixer", model.fs.feed_mixer),
        ("pump1", model.fs.pump1),
        ("ro_stage1", model.fs.ro_stage1),
        ("stage_product1", model.fs.stage_product1),
        ("pump2", model.fs.pump2),
        ("ro_stage2", model.fs.ro_stage2),
        ("stage_product2", model.fs.stage_product2),
        ("recycle_split", model.fs.recycle_split),
        ("disposal_product", model.fs.disposal_product)
    ]
    
    for name, unit in units:
        dof = degrees_of_freedom(unit)
        print(f"  {name}: {dof}")
        
        # For RO units with DOF issues, check which variables are fixed
        if "ro_stage" in name and dof != 0:
            print(f"\n  Detailed analysis of {name}:")
            
            # Check if variables exist and their status
            attrs_to_check = [
                "A_comp", "B_comp", "reflect_coeff", "deltaP", 
                "area", "length", "width", "feed_side.channel_height",
                "feed_side.spacer_porosity", "permeate.pressure"
            ]
            
            for attr in attrs_to_check:
                try:
                    if "." in attr:
                        parts = attr.split(".")
                        obj = unit
                        for part in parts:
                            obj = getattr(obj, part)
                        var = obj
                    else:
                        var = getattr(unit, attr)
                    
                    if hasattr(var, "fixed"):
                        print(f"    {attr}: {'FIXED' if var.fixed else 'FREE'}")
                        if hasattr(var, "value"):
                            print(f"      Value: {value(var)}")
                    elif hasattr(var, "__getitem__"):
                        # Indexed variable
                        print(f"    {attr}: Indexed variable")
                        for idx in var:
                            if hasattr(var[idx], "fixed"):
                                print(f"      {idx}: {'FIXED' if var[idx].fixed else 'FREE'}")
                except AttributeError:
                    print(f"    {attr}: NOT FOUND")
            
            # Check unused variables
            unused = number_of_unused_variables(unit)
            print(f"\n    Number of unused variables: {unused}")

if __name__ == "__main__":
    debug_dof()