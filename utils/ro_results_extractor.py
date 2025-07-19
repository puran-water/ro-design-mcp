"""
RO simulation results extraction and analysis utilities.

This module provides functions to extract comprehensive results from solved
WaterTAP RO models, including performance metrics, ion tracking, and scaling predictions.
"""

from typing import Dict, Any, Tuple
import logging
from pyomo.environ import value

logger = logging.getLogger(__name__)


def extract_results_mcas(model, config_data):
    """
    Extract comprehensive results from solved MCAS RO model with recycle support.
    
    Tracks ion-specific rejections, scaling potential, and mass balance.
    """
    m = model
    n_stages = config_data.get('n_stages', config_data.get('stage_count', 1))
    
    # Check for recycle
    recycle_info = config_data.get('recycle_info', {})
    has_recycle = recycle_info.get('uses_recycle', False)
    
    results = {
        "status": "success",
        "configuration": config_data,
        "has_recycle": has_recycle,
        "performance": {},
        "stage_results": [],
        "ion_tracking": {},
        "mass_balance": {},
        "economics": {}
    }
    
    # Extract stage-wise results
    total_perm_flow = 0
    total_power = 0
    
    for i in range(1, n_stages + 1):
        pump = getattr(m.fs, f"pump{i}")
        ro = getattr(m.fs, f"ro_stage{i}")
        
        # Flow rates
        feed_h2o = value(ro.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
        perm_h2o = value(ro.permeate.flow_mass_phase_comp[0, 'Liq', 'H2O'])
        conc_h2o = value(ro.retentate.flow_mass_phase_comp[0, 'Liq', 'H2O'])
        
        # Recovery
        recovery = perm_h2o / feed_h2o if feed_h2o > 0 else 0
        
        # Pressures
        feed_pressure = value(ro.inlet.pressure[0]) / 1e5
        conc_pressure = value(ro.retentate.pressure[0]) / 1e5
        perm_pressure = value(ro.permeate.pressure[0]) / 1e5
        
        # Power
        pump_power = value(pump.work_mechanical[0])
        
        # Ion concentrations and rejections
        ion_data = {}
        for comp in m.fs.properties.solute_set:
            feed_ion = value(ro.inlet.flow_mass_phase_comp[0, 'Liq', comp])
            perm_ion = value(ro.permeate.flow_mass_phase_comp[0, 'Liq', comp])
            conc_ion = value(ro.retentate.flow_mass_phase_comp[0, 'Liq', comp])
            
            # Calculate concentrations (mg/L)
            feed_conc = feed_ion / (feed_h2o + sum(
                value(ro.inlet.flow_mass_phase_comp[0, 'Liq', c]) 
                for c in m.fs.properties.solute_set
            )) * 1e6 if feed_h2o > 0 else 0
            
            perm_conc = perm_ion / (perm_h2o + sum(
                value(ro.permeate.flow_mass_phase_comp[0, 'Liq', c]) 
                for c in m.fs.properties.solute_set
            )) * 1e6 if perm_h2o > 0 else 0
            
            conc_conc = conc_ion / (conc_h2o + sum(
                value(ro.retentate.flow_mass_phase_comp[0, 'Liq', c]) 
                for c in m.fs.properties.solute_set
            )) * 1e6 if conc_h2o > 0 else 0
            
            # Rejection
            rejection = 1 - (perm_conc / feed_conc) if feed_conc > 0 else 0
            
            ion_data[comp] = {
                "feed_mg_l": feed_conc,
                "permeate_mg_l": perm_conc,
                "concentrate_mg_l": conc_conc,
                "rejection": rejection,
                "feed_flow_kg_s": feed_ion,
                "permeate_flow_kg_s": perm_ion,
                "concentrate_flow_kg_s": conc_ion
            }
        
        # Stage results
        stage_result = {
            "stage": i,
            "recovery": recovery,
            "feed_flow_kg_s": feed_h2o + sum(
                value(ro.inlet.flow_mass_phase_comp[0, 'Liq', c]) 
                for c in m.fs.properties.solute_set
            ),
            "permeate_flow_kg_s": perm_h2o + sum(
                value(ro.permeate.flow_mass_phase_comp[0, 'Liq', c]) 
                for c in m.fs.properties.solute_set
            ),
            "concentrate_flow_kg_s": conc_h2o + sum(
                value(ro.retentate.flow_mass_phase_comp[0, 'Liq', c]) 
                for c in m.fs.properties.solute_set
            ),
            "feed_pressure_bar": feed_pressure,
            "concentrate_pressure_bar": conc_pressure,
            "permeate_pressure_bar": perm_pressure,
            "pump_power_kW": abs(pump_power) / 1000,
            "ion_data": ion_data
        }
        
        results["stage_results"].append(stage_result)
        
        total_perm_flow += perm_h2o
        total_power += abs(pump_power)
    
    # Overall performance metrics
    # Get feed block - handle both fresh_feed and feed naming
    # Check if fresh_feed exists and handle Reference if present
    if hasattr(m.fs, "fresh_feed"):
        # Check if it's a Reference (indexed block)
        feed_block = m.fs.fresh_feed
        if hasattr(feed_block, "__getitem__"):
            # It's a Reference, access with [None]
            feed_block = feed_block[None]
    elif hasattr(m.fs, "feed"):
        feed_block = m.fs.feed
    else:
        raise ValueError("No feed block found in flowsheet (expected fresh_feed or feed)")
    
    if has_recycle:
        # For recycle systems, use fresh feed flow
        fresh_h2o = value(feed_block.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
        fresh_tds = sum(
            value(feed_block.outlet.flow_mass_phase_comp[0, 'Liq', c])
            for c in m.fs.properties.solute_set
        )
        fresh_total = fresh_h2o + fresh_tds
        
        # Disposal flow (actual concentrate)
        disposal_h2o = value(m.fs.disposal_product.inlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
        disposal_tds = sum(
            value(m.fs.disposal_product.inlet.flow_mass_phase_comp[0, 'Liq', c])
            for c in m.fs.properties.solute_set
        )
        
        system_recovery = total_perm_flow / fresh_h2o if fresh_h2o > 0 else 0
    else:
        # Standard system
        feed_h2o = value(feed_block.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
        feed_tds = sum(
            value(feed_block.outlet.flow_mass_phase_comp[0, 'Liq', c])
            for c in m.fs.properties.solute_set
        )
        fresh_total = feed_h2o + feed_tds
        
        system_recovery = total_perm_flow / feed_h2o if feed_h2o > 0 else 0
    
    # Calculate overall TDS
    total_perm_tds = 0
    for i in range(1, n_stages + 1):
        ro = getattr(m.fs, f"ro_stage{i}")
        for comp in m.fs.properties.solute_set:
            total_perm_tds += value(ro.permeate.flow_mass_phase_comp[0, 'Liq', comp])
    
    perm_tds_mg_l = total_perm_tds / total_perm_flow * 1e6 if total_perm_flow > 0 else 0
    
    # Overall ion tracking
    overall_ions = {}
    for comp in m.fs.properties.solute_set:
        # Fresh feed
        fresh_ion = value(feed_block.outlet.flow_mass_phase_comp[0, 'Liq', comp])
        fresh_conc = fresh_ion / fresh_total * 1e6 if fresh_total > 0 else 0
        
        # Total permeate
        perm_ion = sum(
            value(getattr(m.fs, f"ro_stage{i}").permeate.flow_mass_phase_comp[0, 'Liq', comp])
            for i in range(1, n_stages + 1)
        )
        perm_conc = perm_ion / (total_perm_flow + total_perm_tds) * 1e6 if total_perm_flow > 0 else 0
        
        # Disposal or concentrate
        if has_recycle:
            disposal_ion = value(m.fs.disposal_product.inlet.flow_mass_phase_comp[0, 'Liq', comp])
            disposal_conc = disposal_ion / (disposal_h2o + disposal_tds) * 1e6 if disposal_h2o > 0 else 0
        else:
            final_ro = getattr(m.fs, f"ro_stage{n_stages}")
            conc_ion = value(final_ro.retentate.flow_mass_phase_comp[0, 'Liq', comp])
            conc_h2o = value(final_ro.retentate.flow_mass_phase_comp[0, 'Liq', 'H2O'])
            conc_tds = sum(
                value(final_ro.retentate.flow_mass_phase_comp[0, 'Liq', c])
                for c in m.fs.properties.solute_set
            )
            disposal_conc = conc_ion / (conc_h2o + conc_tds) * 1e6 if conc_h2o > 0 else 0
        
        # Overall rejection
        overall_rejection = 1 - (perm_conc / fresh_conc) if fresh_conc > 0 else 0
        
        overall_ions[comp] = {
            "fresh_feed_mg_l": fresh_conc,
            "combined_permeate_mg_l": perm_conc,
            "disposal_mg_l": disposal_conc,
            "overall_rejection": overall_rejection
        }
    
    results["ion_tracking"] = overall_ions
    
    # Recycle-specific metrics
    if has_recycle:
        # Effective feed composition (after mixing with recycle)
        effective_ions = {}
        mixed_h2o = value(m.fs.feed_mixer.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O'])
        mixed_tds = sum(
            value(m.fs.feed_mixer.outlet.flow_mass_phase_comp[0, 'Liq', c])
            for c in m.fs.properties.solute_set
        )
        mixed_total = mixed_h2o + mixed_tds
        
        for comp in m.fs.properties.solute_set:
            mixed_ion = value(m.fs.feed_mixer.outlet.flow_mass_phase_comp[0, 'Liq', comp])
            mixed_conc = mixed_ion / mixed_total * 1e6 if mixed_total > 0 else 0
            
            # Accumulation factor
            fresh_conc = overall_ions[comp]["fresh_feed_mg_l"]
            accumulation = mixed_conc / fresh_conc if fresh_conc > 0 else 1
            
            effective_ions[comp] = {
                "effective_feed_mg_l": mixed_conc,
                "accumulation_factor": accumulation
            }
        
        results["recycle_metrics"] = {
            "recycle_split_ratio": value(m.fs.recycle_split.split_fraction[0, "recycle"]),
            "recycle_flow_kg_s": value(m.fs.recycle_split.recycle.flow_mass_phase_comp[0, 'Liq', 'H2O']),
            "disposal_flow_kg_s": disposal_h2o,
            "effective_ion_composition": effective_ions
        }
    
    # Performance summary
    results["performance"] = {
        "system_recovery": system_recovery,
        "total_permeate_flow_m3_h": total_perm_flow * 3.6,  # kg/s to m³/h
        "total_permeate_tds_mg_l": perm_tds_mg_l,
        "total_power_consumption_kW": total_power / 1000,
        # Specific energy calculation:
        # total_power is in W, convert to kW by /1000
        # total_perm_flow is in kg/s, convert to m³/h by *3.6 (assuming density ~1000 kg/m³)
        # kWh/m³ = kW / (m³/h)
        "specific_energy_kWh_m3": (total_power / 1000) / (total_perm_flow * 3.6) if total_perm_flow > 0 else 0
    }
    
    # Mass balance check
    if has_recycle:
        # Fresh in = permeate out + disposal out
        fresh_in = fresh_h2o + fresh_tds
        perm_out = total_perm_flow + total_perm_tds
        disposal_out = disposal_h2o + disposal_tds
        
        mass_balance_error = abs(fresh_in - perm_out - disposal_out) / fresh_in if fresh_in > 0 else 0
    else:
        # Feed in = permeate out + concentrate out
        feed_in = fresh_total
        perm_out = total_perm_flow + total_perm_tds
        final_ro = getattr(m.fs, f"ro_stage{n_stages}")
        conc_out = sum(
            value(final_ro.retentate.flow_mass_phase_comp[0, 'Liq', c])
            for c in ['H2O'] + list(m.fs.properties.solute_set)
        )
        
        mass_balance_error = abs(feed_in - perm_out - conc_out) / feed_in if feed_in > 0 else 0
    
    results["mass_balance"] = {
        "mass_balance_error": mass_balance_error,
        "mass_balance_ok": mass_balance_error < 0.001
    }
    
    # Economics placeholder
    results["economics"] = {
        "capital_cost_usd": 0,  # Would need costing correlations
        "operating_cost_usd_year": 0,
        "lcow_usd_m3": 0
    }
    
    return results


def predict_scaling_potential(m, stage_num):
    """
    Predict scaling potential using concentrate composition.
    
    Args:
        m: WaterTAP model
        stage_num: Stage number to analyze
    
    Returns:
        Tuple of (scaling_results, antiscalant_recommendation)
    """
    ro = getattr(m.fs, f"ro_stage{stage_num}")
    conc_state = ro.retentate
    
    # Extract ion concentrations in mg/L
    conc_ions_mg_l = {}
    total_flow_kg_s = 0
    
    for comp in m.fs.properties.component_list:
        if comp != "H2O":
            # Get mass flow directly (already in mass basis)
            comp_flow_kg_s = value(conc_state.flow_mass_phase_comp[0, 'Liq', comp])
            conc_ions_mg_l[comp] = comp_flow_kg_s  # Will convert to mg/L later
        else:
            water_flow_kg_s = value(conc_state.flow_mass_phase_comp[0, 'Liq', 'H2O'])
            total_flow_kg_s += water_flow_kg_s
    
    # Convert to mg/L
    total_flow_m3_s = total_flow_kg_s / 1000  # Approximate density 1000 kg/m³
    if total_flow_m3_s > 0:
        for ion in conc_ions_mg_l:
            # kg/s / (m³/s) * 1e6 mg/kg = mg/L
            conc_ions_mg_l[ion] = conc_ions_mg_l[ion] / total_flow_m3_s * 1e6
    
    # Simple scaling assessment based on common scaling compounds
    scaling_results = {}
    
    # Calcium carbonate scaling (simplified)
    if 'Ca2+' in conc_ions_mg_l and 'HCO3-' in conc_ions_mg_l:
        ca_mol_l = conc_ions_mg_l.get('Ca2+', 0) / 40080  # mg/L to mol/L
        hco3_mol_l = conc_ions_mg_l.get('HCO3-', 0) / 61020  # mg/L to mol/L
        # Very simplified Langelier Saturation Index approximation
        lsi_approx = 0.5 * (ca_mol_l * hco3_mol_l * 1e6) - 1.0
        scaling_results['CaCO3'] = {
            'saturation_index': lsi_approx,
            'scaling_tendency': 'High' if lsi_approx > 0.5 else 'Medium' if lsi_approx > 0 else 'Low'
        }
    
    # Calcium sulfate scaling
    if 'Ca2+' in conc_ions_mg_l and 'SO4-2' in conc_ions_mg_l:
        ca_mg_l = conc_ions_mg_l.get('Ca2+', 0)
        so4_mg_l = conc_ions_mg_l.get('SO4-2', 0)
        # Simple check against typical solubility
        if (ca_mg_l * so4_mg_l) > 500000:  # Simplified threshold
            scaling_results['CaSO4'] = {
                'saturation_index': 1.0,
                'scaling_tendency': 'High'
            }
        else:
            scaling_results['CaSO4'] = {
                'saturation_index': -0.5,
                'scaling_tendency': 'Low'
            }
    
    # Antiscalant recommendation (simplified)
    antiscalant_rec = {
        'antiscalant_type': 'None required',
        'dosage_ppm': 0,
        'primary_concern': 'None'
    }
    
    # Check if any scaling risk exists
    high_risk_scales = [k for k, v in scaling_results.items() 
                        if v.get('scaling_tendency') == 'High']
    
    if high_risk_scales:
        if 'CaCO3' in high_risk_scales:
            antiscalant_rec = {
                'antiscalant_type': 'Phosphonate-based',
                'dosage_ppm': 3.0,
                'primary_concern': 'Calcium carbonate',
                'specific_products': ['FLOCON 260', 'Vitec 3000']
            }
        elif 'CaSO4' in high_risk_scales:
            antiscalant_rec = {
                'antiscalant_type': 'Polyacrylate-based',
                'dosage_ppm': 2.5,
                'primary_concern': 'Calcium sulfate',
                'specific_products': ['FLOCON 100', 'Vitec 2000']
            }
    
    return scaling_results, antiscalant_rec