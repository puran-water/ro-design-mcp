# Membrane Properties Update Summary

## Overview
Updated all RO simulation templates to use the `get_membrane_properties` function instead of hardcoded membrane properties, ensuring that membrane selection actually affects simulation results.

## Changes Made

### 1. Standard RO Template (`ro_simulation_template.ipynb`)
- Added import for `get_membrane_properties`
- Added logging to show which membrane properties are being applied
- Updated to use `ro.area.fix()` instead of trying to set length/width
- Replaced hardcoded A_w and B_s values with dynamic values from handler

### 2. MCAS Template (`ro_simulation_mcas_template.ipynb`)
- Added import for `get_membrane_properties`
- Replaced hardcoded A_w value (4.2e-12) with dynamic value from handler
- Added B_s scaling for ion-specific permeabilities
- Added comprehensive logging of membrane properties
- Changed from SKK to SD transport model for consistency

### 3. MCAS Simple Template (`ro_simulation_mcas_simple_template.ipynb`)
- Added import for `get_membrane_properties`
- Replaced hardcoded membrane properties with dynamic values
- Added B_s scaling for ion-specific permeabilities
- Added membrane property logging

### 4. MCAS Recycle Template (`ro_simulation_mcas_recycle_template.ipynb`)
- Added import for `get_membrane_properties`
- Updated `build_ro_model_mcas_with_recycle` function to use dynamic properties
- Added B_s scaling for ion-specific permeabilities
- Added membrane property logging
- Changed from SKK to SD transport model

## Key Technical Details

### Membrane Properties Available
The system now supports the following membrane types with literature-based properties:

1. **BW30-400** (Standard brackish water membrane)
   - A_w = 9.63e-12 m/s/Pa
   - B_s = 5.58e-08 m/s

2. **ECO PRO-400** (High permeability membrane)
   - A_w = 1.60e-11 m/s/Pa (66% higher than BW30-400)
   - B_s = 4.24e-08 m/s
   - Allows ~30% higher flux or lower pressure operation

3. **CR100 PRO-400** (Chemical resistant membrane)
   - A_w = 1.06e-11 m/s/Pa (10% higher than BW30-400)
   - B_s = 4.16e-08 m/s
   - Tolerates pH 1-13 and chlorine exposure

### Ion-Specific Permeability Scaling
For MCAS templates, ion-specific B values are scaled based on the membrane's overall salt permeability:
```python
default_b_nacl = 3.5e-8
b_scale_factor = B_s / default_b_nacl

# Apply scaling to different ion groups
if comp in ['Na+', 'Cl-']:
    B_comp = 3.5e-8 * b_scale_factor
elif comp in ['Ca2+', 'Mg2+', 'SO4-2']:
    B_comp = 1.5e-8 * b_scale_factor  # Higher rejection
else:
    B_comp = 2.5e-8 * b_scale_factor
```

## Testing Results

1. **Membrane Properties Handler**: Confirmed to return different A_w and B_s values for each membrane type
2. **Notebook Execution**: All templates now log membrane properties and apply them correctly
3. **Expected Impact**: Different membranes should now produce different:
   - Operating pressures (higher permeability = lower pressure)
   - Energy consumption
   - Salt rejection (different B_s values)

## Usage Examples

```python
# Using standard brackish membrane
result = await simulate_ro_system(
    configuration=config,
    feed_salinity_ppm=5000,
    membrane_type="bw30_400"
)

# Using high-efficiency ECO membrane
result = await simulate_ro_system(
    configuration=config,
    feed_salinity_ppm=5000,
    membrane_type="eco_pro_400"  # 66% higher permeability
)

# Using custom membrane properties
result = await simulate_ro_system(
    configuration=config,
    feed_salinity_ppm=5000,
    membrane_properties='{"A_w": 2.0e-11, "B_s": 3.0e-8}'
)
```

## Next Steps

1. Run full integration tests with actual solver to verify energy/pressure differences
2. Consider adding more membrane types based on user needs
3. Update documentation with membrane selection guidance