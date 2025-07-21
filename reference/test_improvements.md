# Test Plan for RO Simulation Improvements

## Issues to Address

1. **Recovery Mismatch**: Simulation returns 91.2% instead of configured 95%
2. **Low Pressures**: 18-20 bar instead of expected ~30-40 bar for high recovery
3. **Ion Tracking**: Need ion-specific mass balances with recycle
4. **Parameter Bug**: `feed_salinity_ppm` not passed correctly to recycle template

## Improvements Made

### 1. Created Unified Template (`ro_simulation_unified_template.ipynb`)
- Supports both MCAS (ion tracking) and recycle in one template
- Uses SD transport model for proper flux calculations
- Implements pump optimization when `optimize_pumps=True`
- Adds both stage recovery AND overall recovery constraints
- Fixes parameter passing issues

### 2. Key Features of Unified Template

#### Pump Optimization Logic
```python
if optimize_pumps:
    # Unfix pump pressures
    for i in range(1, config_data['stage_count'] + 1):
        pump = getattr(m.fs, f"pump{i}")
        pump.outlet.pressure[0].unfix()
        pump.outlet.pressure[0].setlb(5e5)   # 5 bar min
        pump.outlet.pressure[0].setub(80e5)  # 80 bar max
    
    # Add stage recovery constraints
    for i in range(1, config_data['stage_count'] + 1):
        ro = getattr(m.fs, f"ro_stage{i}")
        target_recovery = config_data['stages'][i-1].get('stage_recovery', 0.5)
        
        setattr(m.fs, f"recovery_constraint_stage{i}",
            Constraint(
                expr=ro.recovery_mass_phase_comp[0, 'Liq', 'H2O'] == target_recovery
            )
        )
    
    # Add overall system recovery constraint (fresh feed basis)
    target_overall = config_data.get('achieved_recovery', 0.95)
    
    fresh_water_flow = m.fs.fresh_feed.outlet.flow_mass_phase_comp[0, 'Liq', 'H2O']
    total_perm_flow = sum(
        getattr(m.fs, f"stage_product{i}").inlet.flow_mass_phase_comp[0, 'Liq', 'H2O']
        for i in range(1, config_data['stage_count'] + 1)
    )
    
    m.fs.overall_recovery_constraint = Constraint(
        expr=total_perm_flow == target_overall * fresh_water_flow
    )
```

#### Pressure Initialization
```python
# Estimate required pressure based on recovery and TDS
conc_tds = feed_tds / (1 - stage_recovery)
osmotic_pressure = conc_tds * 0.7 / 1000 * 1e5  # Pa
required_pressure = osmotic_pressure + 10e5  # Add driving pressure

# Initialize pump
pump.outlet.pressure.fix(required_pressure)
```

#### Ion-Specific Tracking with MCAS
```python
if use_mcas:
    # Set ion flows
    for comp in mcas_config['solute_list']:
        conc_mg_l = ion_composition_mg_l[comp]
        ion_flow_kg_s = conc_mg_l * fresh_feed_flow_m3_s / 1000
        feed_state.flow_mass_phase_comp[0, 'Liq', comp].fix(ion_flow_kg_s)
```

### 3. Updated `simulate_ro.py`
- Now selects unified template when ions or recycle are present
- Falls back to separate templates if unified not available

## Expected Results

### Configuration
- Array: 25:12 (2-stage)
- Target recovery: 95%
- Fresh feed: 150 m³/h
- Feed TDS: 2000 ppm
- Recycle ratio: 22.9%

### Expected Simulation Results
1. **Recovery**: 95.0% (matching configuration)
2. **Stage 1 Pressure**: ~25-30 bar
   - Concentrate TDS: ~4200 ppm
   - Osmotic pressure: ~29 bar
3. **Stage 2 Pressure**: ~35-40 bar
   - Concentrate TDS: ~40,000 ppm
   - Osmotic pressure: ~28 bar
4. **Ion Tracking**:
   - Na+: 786.3 mg/L in feed
   - Cl-: 1213.7 mg/L in feed
   - Higher concentrations in recycle stream

## Test Commands

To test the improvements, run:

```python
# Configuration from optimize_ro tool
config = {
    "stage_count": 2,
    "array_notation": "25:12",
    "achieved_recovery": 0.9499751195980167,
    "stages": [...],
    "recycle_info": {...},
    "feed_flow_m3h": 150
}

# Call simulate_ro_system with ion composition
result = simulate_ro_system(
    configuration=config,
    feed_salinity_ppm=2000,
    feed_temperature_c=25,
    membrane_type="brackish",
    feed_ion_composition='{"Na+": 786.3, "Cl-": 1213.7}'
)
```

## Verification Checklist

- [ ] Recovery matches target (95% ± 0.1%)
- [ ] Stage pressures scale with TDS
- [ ] Stage 2 pressure > Stage 1 pressure
- [ ] Pressures are realistic (>30 bar for high recovery)
- [ ] Ion concentrations reported for each stream
- [ ] Recycle increases effective feed TDS
- [ ] Mass balance closes (< 0.1% error)
- [ ] No parameter passing errors