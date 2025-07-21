# Flux Validation Implementation for RO Simulation Templates

## Overview

This document describes the comprehensive flux validation system implemented to prevent FBBT (Feasibility-Based Bound Tightening) infeasibility errors when simulating high-permeability reverse osmosis membranes in WaterTAP.

## Problem Statement

### Root Cause
WaterTAP enforces strict bounds on water flux through RO membranes: (0.0001, 0.03) kg/m²/s. When using high-permeability membranes like ECO PRO-400 (A_w = 1.60e-11 m/s/Pa), standard operating pressures (e.g., 30 bar) would result in flux values exceeding the upper bound:

```
flux = A_w × ρ_water × ΔP
flux = 1.60e-11 × 1000 × 30e5 = 0.048 kg/m²/s > 0.03 kg/m²/s
```

This caused FBBT infeasibility errors during initialization:
```
Detected an infeasible constraint during FBBT: fs.ro_stage1.eq_flux_mass[0.0,0.0,Liq,H2O]
```

### Affected Membranes
- **ECO PRO-400**: A_w = 1.60e-11 m/s/Pa (66% higher than baseline)
- **CR100 PRO-400**: A_w = 1.06e-11 m/s/Pa (10% higher than baseline)
- **BW30-400**: A_w = 9.63e-12 m/s/Pa (baseline - not affected)

## Solution Implementation

### 1. Core Functions Modified

#### `calculate_required_pressure()` in `utils/ro_initialization.py`
Added flux-aware pressure capping logic:

```python
# CRITICAL: Check flux bounds to prevent FBBT infeasibility
# WaterTAP flux bounds: (0.0001, 0.03) kg/m²/s
# Use 83% of upper bound for safety margin
max_flux = 0.025  # kg/m²/s (83% of 0.03)
water_density = 1000  # kg/m³

# Calculate maximum allowable pressure based on flux limit
# flux = A_w * density * (P_feed - P_perm - π_net)
# Solving for P_feed: P_feed = flux/(A_w * density) + P_perm + π_net
max_pressure_from_flux = (max_flux / (A_w * water_density)) + permeate_pressure + avg_osmotic

# Apply flux-based pressure cap
if required_pressure > max_pressure_from_flux:
    logger.warning(
        f"Capping pressure to respect flux bounds:\n"
        f"  Original pressure: {required_pressure/1e5:.1f} bar\n"
        f"  Max flux: {max_flux:.3f} kg/m²/s\n"
        f"  Capped pressure: {max_pressure_from_flux/1e5:.1f} bar"
    )
    required_pressure = max_pressure_from_flux
```

#### `validate_flux_bounds()` - New Helper Function
Added to `utils/ro_initialization.py` to validate pressure choices:

```python
def validate_flux_bounds(
    A_w: float,
    pressure: float,
    permeate_pressure: float = 101325,
    osmotic_pressure: float = 0,
    max_flux: float = 0.025  # 83% of WaterTAP limit for safety
) -> tuple[bool, float]:
    """
    Validate that a given pressure will not exceed flux bounds.
    
    Returns:
        Tuple of (is_valid, expected_flux)
    """
    water_density = 1000  # kg/m³
    net_driving = pressure - permeate_pressure - osmotic_pressure
    
    if net_driving <= 0:
        return False, 0.0
    
    expected_flux = A_w * water_density * net_driving
    is_valid = expected_flux <= max_flux
    
    return is_valid, expected_flux
```

### 2. Template Updates

All six RO simulation templates were updated with flux validation:

#### Standard Templates
- `ro_simulation_template.ipynb`
- `ro_simulation_simple_template.ipynb`

#### MCAS Templates  
- `ro_simulation_mcas_template.ipynb`
- `ro_simulation_mcas_simple_template.ipynb`

#### Recycle Templates
- `ro_simulation_recycle_template.ipynb`
- `ro_simulation_mcas_recycle_template.ipynb`

### 3. Key Changes in Each Template

#### A. Initialization Functions
Updated to accept and use membrane A_w parameter:

```python
def initialize_and_solve_elegant(m, config_data, A_w, optimize_pumps=False):
    """Initialize with flux validation."""
    # ... existing code ...
    
    # Calculate required pressure using flux-aware function
    required_pressure = calculate_required_pressure(
        current_tds_ppm,
        target_recovery,
        permeate_pressure=101325,
        min_driving_pressure=min_driving,
        pressure_drop=0.5e5,
        A_w=A_w  # Pass actual membrane A_w
    )
```

#### B. Flux Diagnostics
Added diagnostic output to show expected flux at different pressures:

```python
# Flux diagnostics
print("\n=== Flux Diagnostics ===")
print(f"Membrane A_w = {A_w:.2e} m/s/Pa")
print(f"WaterTAP flux bounds: (0.0001, 0.03) kg/m²/s")

for pressure_bar in [15, 20, 30, 40]:
    pressure_pa = pressure_bar * 1e5
    expected_flux = A_w * 1000 * pressure_pa
    print(f"At {pressure_bar} bar: Expected flux ~{expected_flux:.3f} kg/m²/s")
```

#### C. Flux-Aware Pump Bounds
When optimizing pumps, set pressure bounds based on flux limits:

```python
# Calculate osmotic pressures
feed_osm = calculate_osmotic_pressure(current_tds_ppm)
conc_osm = calculate_osmotic_pressure(calculate_concentrate_tds(current_tds_ppm, target_recovery))
avg_osm = (feed_osm + conc_osm) / 2

# Maximum pressure based on flux limit
max_flux = 0.025  # 83% of WaterTAP limit for safety
water_density = 1000  # kg/m³
max_pressure_from_flux = (max_flux / (A_w * water_density)) + 101325 + avg_osm

# Unfix and set bounds
pump.outlet.pressure[0].unfix()
pump.outlet.pressure[0].setlb(5e5)   # 5 bar minimum
pump.outlet.pressure[0].setub(min(max_pressure_from_flux, 80e5))  # Flux-aware maximum
```

#### D. Flux Verification
After solving, verify actual flux values:

```python
# Verify flux after solving
flux_h2o = value(ro.flux_mass_phase_comp[0, 0, 'Liq', 'H2O'])
print(f"Water flux: {flux_h2o:.4f} kg/m²/s (limit: 0.025)")
```

### 4. Multi-Stage Considerations

For multi-stage systems, the `initialize_multistage_ro_elegant()` function was updated to:
- Track cumulative TDS concentration through stages
- Apply flux-aware pressure calculations for each stage
- Reduce safety factors if they would violate flux bounds

```python
# Check if safety factor would exceed flux bounds
test_pressure = required_pressure * safety_factor
# ... calculate max_pressure_from_flux ...

if test_pressure > max_pressure_from_flux:
    # Reduce safety factor to stay within flux bounds
    safe_safety_factor = max_pressure_from_flux / required_pressure
    logger.info(f"Reducing safety factor from {safety_factor:.2f} to {safe_safety_factor:.2f}")
    required_pressure *= safe_safety_factor
else:
    required_pressure = test_pressure
```

## Test Results

### Flux Capping Verification
Testing confirmed proper flux capping for different membrane types:

| Membrane | A_w (m/s/Pa) | Uncapped Pressure | Capped Pressure | Resulting Flux |
|----------|--------------|-------------------|-----------------|----------------|
| BW30-400 | 9.63e-12 | 18.6 bar | 18.6 bar | 0.0169 kg/m²/s |
| ECO PRO-400 | 1.60e-11 | ~30 bar | 16.1 bar | 0.0242 kg/m²/s |
| CR100 PRO-400 | 1.06e-11 | 18.2 bar | 18.2 bar | 0.0182 kg/m²/s |

### Pressure vs Flux Relationship
Maximum operating pressures before hitting flux limit (0.025 kg/m²/s):
- **BW30-400**: ~28 bar
- **ECO PRO-400**: ~17 bar  
- **CR100 PRO-400**: ~25 bar

## Benefits

1. **Prevents FBBT Errors**: High-permeability membranes now initialize successfully
2. **Maintains Physical Validity**: Ensures flux stays within WaterTAP's bounds
3. **Transparent to Users**: Automatic pressure capping with informative warnings
4. **Optimization Compatible**: Flux bounds are respected during pump optimization
5. **Safety Margin**: Uses 83% of upper bound (0.025 vs 0.03) for robustness

## Usage Notes

1. **Membrane Properties**: Always pass correct A_w values to initialization functions
2. **Pressure Warnings**: Monitor logs for pressure capping warnings
3. **Stage Design**: High-permeability membranes may require more stages to achieve target recovery
4. **Energy Implications**: Flux-limited operation may increase specific energy consumption

## Future Enhancements

1. **Dynamic Safety Factor**: Adjust safety margin based on operating conditions
2. **Flux-Based Optimization**: Add flux as an explicit optimization variable
3. **Stage-Specific Limits**: Allow different flux limits for different stages
4. **Membrane Fouling**: Account for flux decline over time

## Conclusion

The flux validation system successfully prevents FBBT infeasibility errors while maintaining physically realistic operating conditions. All RO simulation templates now support the full range of membrane permeabilities available in the system, including high-permeability membranes like ECO PRO-400.