# Membrane Property Parameterization Implementation Plan

## Executive Summary

WaterTAP's default membrane properties (A = 4.2e-12 m/s/Pa = 1.512 LMH/bar) are specifically for seawater applications and are inappropriate for brackish water treatment. This causes significant errors in energy and pressure predictions. This implementation plan provides a comprehensive approach to parameterize membrane properties as MCP client inputs.

## Problem Analysis

### Current Issues
1. **Hardcoded seawater defaults**: WaterTAP uses A = 4.2e-12 m/s/Pa (1.512 LMH/bar) for all applications
2. **No BWRO/NF defaults**: WaterTAP has NO built-in defaults for brackish water or nanofiltration membranes
3. **Inappropriate for brackish water**: Brackish membranes typically have 2-3x higher permeability (3-8 LMH/bar)
4. **MCAS notebook limitation**: Current implementation ignores membrane_properties parameter

### Impact
- 2-3x overestimation of required operating pressures for brackish water
- Incorrect energy consumption predictions
- Inaccurate salt rejection modeling for different water types

## Implementation Plan

### Phase 1: Define Membrane Property Defaults

#### 1.1 Seawater RO Membranes (SWRO)
Based on industry standards (e.g., DOW FILMTEC SW30):
- **Water permeability**: A = 2.8e-13 to 4.2e-13 m/s/Pa (1.0-1.5 LMH/bar)
- **Operating pressure**: 55-70 bar
- **Overall salt rejection**: 99.5-99.75%

```python
SEAWATER_DEFAULTS = {
    "A_comp": {"H2O": 3.5e-13},  # 1.26 LMH/bar
    "B_comp": {
        "Na_+": 2.5e-8,    # ~99.3% rejection
        "Cl_-": 3.5e-8,    # ~99.0% rejection
        "Ca_2+": 5.0e-9,   # ~99.8% rejection
        "Mg_2+": 3.0e-9,   # ~99.9% rejection
        "SO4_2-": 1.0e-9,  # ~99.95% rejection
        "HCO3_-": 4.0e-8   # ~98.9% rejection
    }
}
```

#### 1.2 Brackish Water RO Membranes (BWRO)
Based on industry standards (e.g., DOW FILMTEC BW30):
- **Water permeability**: A = 8.3e-13 to 1.4e-12 m/s/Pa (3.0-5.0 LMH/bar)
- **Operating pressure**: 10-20 bar
- **Overall salt rejection**: 99.0-99.5%

```python
BRACKISH_DEFAULTS = {
    "A_comp": {"H2O": 1.1e-12},  # 4.0 LMH/bar
    "B_comp": {
        "Na_+": 7.0e-8,    # ~99.0% rejection
        "Cl_-": 1.0e-7,    # ~98.6% rejection
        "Ca_2+": 2.0e-8,   # ~99.5% rejection
        "Mg_2+": 1.5e-8,   # ~99.6% rejection
        "SO4_2-": 5.0e-9,  # ~99.8% rejection
        "HCO3_-": 1.2e-7   # ~98.3% rejection
    }
}
```

#### 1.3 Low-Pressure Brackish Membranes
Based on industry standards (e.g., DOW FILMTEC BW30LE):
- **Water permeability**: A = 1.4e-12 to 1.9e-12 m/s/Pa (5.0-7.0 LMH/bar)
- **Operating pressure**: 8-15 bar
- **Overall salt rejection**: 98.5-99.2%

```python
LOW_PRESSURE_BRACKISH_DEFAULTS = {
    "A_comp": {"H2O": 1.7e-12},  # 6.0 LMH/bar
    "B_comp": {
        "Na_+": 1.4e-7,    # ~98.0% rejection
        "Cl_-": 2.0e-7,    # ~97.1% rejection
        "Ca_2+": 4.0e-8,   # ~99.0% rejection
        "Mg_2+": 3.0e-8,   # ~99.2% rejection
        "SO4_2-": 1.0e-8,  # ~99.6% rejection
        "HCO3_-": 2.5e-7   # ~96.4% rejection
    }
}
```

#### 1.4 Nanofiltration Membranes (NF)
Based on industry data:
- **Water permeability**: A = 2.8e-12 to 4.2e-12 m/s/Pa (10-15 LMH/bar)
- **Operating pressure**: 5-10 bar
- **Selective rejection**: High for divalent ions, moderate for monovalent

```python
NANOFILTRATION_DEFAULTS = {
    "A_comp": {"H2O": 3.5e-12},  # 12.6 LMH/bar
    "B_comp": {
        "Na_+": 1.0e-6,    # ~70% rejection
        "Cl_-": 1.0e-6,    # ~70% rejection
        "Ca_2+": 1.0e-7,   # ~90% rejection
        "Mg_2+": 1.0e-7,   # ~90% rejection
        "SO4_2-": 5.0e-8,  # ~93% rejection
        "HCO3_-": 8.0e-7   # ~75% rejection
    }
}
```

### Phase 2: Membrane Property API Design

#### 2.1 MCP Client Input Structure
```python
membrane_properties = {
    "membrane_type": "brackish",  # Required: "seawater", "brackish", "low_pressure_brackish", "nanofiltration", "custom"
    "A_comp": {  # Optional: override water permeability
        "H2O": 1.25e-12  # m/s/Pa
    },
    "B_comp": {  # Optional: override ion permeabilities
        "Na_+": 8.0e-8,   # m/s
        "Cl_-": 1.1e-7,   # m/s
        "Ca_2+": 2.5e-8,  # m/s
        "Mg_2+": 2.0e-8,  # m/s
        "SO4_2-": 6.0e-9, # m/s
        "HCO3_-": 1.5e-7  # m/s
    }
}
```

#### 2.2 Validation Logic
```python
def validate_membrane_properties(membrane_properties, feed_ion_composition):
    """Validate membrane properties input."""
    valid_types = ["seawater", "brackish", "low_pressure_brackish", "nanofiltration", "custom"]
    
    if "membrane_type" not in membrane_properties:
        raise ValueError("membrane_type is required")
    
    if membrane_properties["membrane_type"] not in valid_types:
        raise ValueError(f"Invalid membrane_type. Must be one of {valid_types}")
    
    # For custom type, require full specification
    if membrane_properties["membrane_type"] == "custom":
        if "A_comp" not in membrane_properties or "H2O" not in membrane_properties["A_comp"]:
            raise ValueError("Water permeability (A_comp['H2O']) required for custom membrane")
        
        if "B_comp" not in membrane_properties:
            raise ValueError("Ion permeabilities (B_comp) required for custom membrane")
        
        # Check all feed ions have B values
        for ion in feed_ion_composition:
            if ion not in membrane_properties["B_comp"]:
                raise ValueError(f"B value missing for ion {ion}")
    
    return True
```

### Phase 3: Modify MCAS Notebook Implementation

#### 3.1 Update build_ro_model_mcas Function
```python
def build_ro_model_mcas(config_data, mcas_config, feed_temperature_c, membrane_properties):
    """
    Build WaterTAP RO model with custom membrane properties.
    
    Args:
        config_data: RO configuration dictionary
        mcas_config: MCAS property package configuration
        feed_temperature_c: Feed temperature in Celsius
        membrane_properties: Membrane property specification
    """
    # Import membrane defaults
    from membrane_defaults import (
        SEAWATER_DEFAULTS,
        BRACKISH_DEFAULTS,
        LOW_PRESSURE_BRACKISH_DEFAULTS,
        NANOFILTRATION_DEFAULTS
    )
    
    # Select appropriate defaults
    membrane_type = membrane_properties.get('membrane_type', 'brackish')
    
    default_map = {
        'seawater': SEAWATER_DEFAULTS,
        'brackish': BRACKISH_DEFAULTS,
        'low_pressure_brackish': LOW_PRESSURE_BRACKISH_DEFAULTS,
        'nanofiltration': NANOFILTRATION_DEFAULTS,
        'custom': {"A_comp": {"H2O": 1.1e-12}, "B_comp": {}}
    }
    
    defaults = default_map.get(membrane_type, BRACKISH_DEFAULTS)
    
    # Build model (existing code)
    m = ConcreteModel()
    # ... model construction ...
    
    # Apply membrane properties to each stage
    for i in range(1, n_stages + 1):
        ro = getattr(m.fs, f"ro_stage{i}")
        
        # Set water permeability
        A_value = membrane_properties.get('A_comp', {}).get('H2O', defaults['A_comp']['H2O'])
        ro.A_comp[0, 'H2O'].fix(A_value)
        
        # Set ion permeabilities
        for comp in mcas_config['solute_list']:
            # Use custom value if provided, otherwise use default
            B_value = membrane_properties.get('B_comp', {}).get(
                comp, 
                defaults['B_comp'].get(comp, 7.0e-8)  # Fallback for unknown ions
            )
            ro.B_comp[0, comp].fix(B_value)
        
        # Log membrane properties for debugging
        print(f"Stage {i} membrane properties:")
        print(f"  A (H2O) = {A_value:.2e} m/s/Pa ({A_value * 3.6e9:.2f} LMH/bar)")
        for comp in mcas_config['solute_list']:
            print(f"  B ({comp}) = {value(ro.B_comp[0, comp]):.2e} m/s")
    
    return m
```

#### 3.2 Update Papermill Parameters
Add membrane_properties to the notebook parameters cell:
```python
# Parameters
feed_salinity_ppm = 2700
feed_temperature_c = 25.0
configuration = {}
feed_ion_composition = {}
membrane_properties = {
    "membrane_type": "brackish",
    "A_comp": {},
    "B_comp": {}
}
```

### Phase 4: B Value Calculation from Rejection

For converting rejection percentages to B values:

```python
def rejection_to_B_value(rejection_percent, A_value, typical_conditions):
    """
    Convert ion rejection percentage to B value.
    
    Based on: Rejection = 1 - (B/A) × (1/ΔP_net)
    
    Args:
        rejection_percent: Ion rejection percentage (0-100)
        A_value: Water permeability (m/s/Pa)
        typical_conditions: Dict with typical operating pressure and osmotic pressure
    
    Returns:
        B value in m/s
    """
    rejection_fraction = rejection_percent / 100.0
    delta_p_net = (typical_conditions['pressure'] - typical_conditions['osmotic']) * 1e5  # bar to Pa
    
    # B = A × (1 - rejection) × ΔP_net
    B_value = A_value * (1 - rejection_fraction) * delta_p_net
    
    return B_value
```

### Phase 5: Testing and Validation

#### 5.1 Test Cases
1. **Default membrane types**: Test all four default types
2. **Custom properties**: Test with user-specified A and B values
3. **Partial overrides**: Test membrane_type with partial property overrides
4. **Edge cases**: Test extreme permeability values

#### 5.2 Validation Metrics
- Compare simulated pressures with industry benchmarks
- Verify salt rejection matches specified B values
- Check energy consumption aligns with membrane type

### Phase 6: Documentation

#### 6.1 User Guide
Create comprehensive documentation including:
- Membrane type selection guidelines
- Typical A and B value ranges
- Ion rejection to B value conversion
- Troubleshooting common issues

#### 6.2 API Documentation
Document all parameters, validation rules, and expected outputs

## Implementation Timeline

1. **Week 1**: Implement membrane defaults and validation logic
2. **Week 2**: Modify MCAS notebook to accept membrane properties
3. **Week 3**: Testing and validation with different membrane types
4. **Week 4**: Documentation and user guide creation

## Expected Benefits

1. **Accurate simulations**: Pressure predictions within 10% of actual for all water types
2. **Flexibility**: Support for any commercial membrane through custom properties
3. **Energy optimization**: Accurate energy consumption predictions
4. **Design confidence**: Reliable basis for equipment sizing and CAPEX estimation

## Conclusion

This implementation plan addresses the critical need for membrane property parameterization in the MCP server. By providing appropriate defaults for different membrane types and allowing custom specifications, the system will deliver accurate simulations for seawater, brackish water, and specialized applications.