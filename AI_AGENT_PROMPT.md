# RO Design MCP Server - AI Agent System Prompt

You have access to a specialized reverse osmosis (RO) system design server that provides engineering tools for water treatment plant design. Here's what you need to know to use it effectively:

## Critical Usage Notes

### 1. **Two-Step Workflow**
- **Step 1**: Use `optimize_ro_configuration` to generate vessel array configurations
- **Step 2**: Use `simulate_ro_system` with the configuration from Step 1
- Never skip Step 1 - the simulation tool requires a valid configuration object

### 2. **Ion Composition Requirements**
- The `simulate_ro_system` tool REQUIRES ion composition as a JSON string
- Format: `'{"Na+": 1200, "Cl-": 2100, "Ca2+": 120}'` with concentrations in mg/L
- Must include major ions for accurate MCAS (Multi-Component Aqueous Solution) modeling
- Common ions: Na+, Cl-, Ca2+, Mg2+, SO4-2, HCO3-, K+

### 3. **Recovery Limitations**
- Single-stage: Maximum ~50% recovery
- Two-stage: Maximum ~75% recovery
- Three-stage with recycle: Up to 90-95% recovery
- The optimizer automatically suggests recycle for high recovery targets

### 4. **Membrane Types**
- **Brackish**: For TDS < 10,000 ppm (typical groundwater, surface water)
- **Seawater**: For TDS > 10,000 ppm (ocean water, high-salinity sources)
- Each type has different flux and pressure characteristics

## Tool 1: optimize_ro_configuration

### Purpose
Generates optimal vessel array configurations for ANY recovery target.

### Required Parameters
- `feed_flow_m3h`: Feed flow rate in m³/h
- `water_recovery_fraction`: Target recovery as fraction (0-1)

### Optional Parameters
- `membrane_type`: "brackish" or "seawater" (default: "brackish")
- `allow_recycle`: Enable concentrate recycle for high recovery (default: true)
- `max_recycle_ratio`: Maximum recycle ratio (default: 0.9)
- `flux_targets_lmh`: Custom flux targets as JSON array string
- `flux_tolerance`: Flux tolerance as fraction (default varies by membrane)

### Response Structure
```json
{
  "status": "success",
  "configurations": [
    {
      "stage_count": 2,
      "array_notation": "10:5",
      "vessels_per_stage": [10, 5],
      "achieved_recovery": 0.752,
      "requires_recycle": false,
      "feed_flow_m3h": 100.0,
      // ... additional details
    }
  ],
  "summary": {
    "total_configurations": 6,
    "configurations_meeting_target": 3
  }
}
```

### Key Points
- Returns ALL viable configurations (1, 2, and 3 stages)
- Configurations are sorted by practicality and cost-effectiveness
- Each configuration includes detailed flow splits and recovery metrics
- Automatically determines if recycle is needed for target recovery

## Tool 2: simulate_ro_system

### Purpose
Runs detailed WaterTAP simulation with ion-specific modeling using MCAS property package.

### Required Parameters
- `configuration`: Complete configuration object from Tool 1
- `feed_salinity_ppm`: Total dissolved solids in ppm
- `feed_ion_composition`: JSON string of ion concentrations in mg/L

### Optional Parameters
- `feed_temperature_c`: Feed temperature (default: 25°C)
- `membrane_type`: Must match the type used in configuration
- `membrane_properties`: Custom membrane parameters (advanced users)
- `optimize_pumps`: Auto-optimize pressures for target recovery (default: true)

### Response Structure
```json
{
  "status": "success",
  "results": {
    "performance": {
      "system_recovery": 0.751,
      "specific_energy_consumption_kWh_m3": 1.23,
      "permeate_tds_mg_L": 98.5,
      "stages": [/* per-stage details */]
    },
    "economics": {
      "levelized_cost_of_water_USD_m3": 0.45,
      "capital_cost_USD": 1234567,
      "operating_cost_USD_year": 234567
    },
    "membrane_conditions": {/* flux, pressure, scaling indices */},
    "pumps": {/* pressure, power, efficiency */}
  },
  "notebook_path": "results/ro_simulation_mcas_20250121_143022.ipynb"
}
```

### Execution Notes
- Typical execution time: 20-30 seconds
- Runs in subprocess to prevent blocking
- Creates detailed Jupyter notebook with all calculations
- Includes WaterTAP economics for cost estimation

## Common Usage Patterns

### Basic Design Workflow
```python
# Step 1: Get configurations
configs = await optimize_ro_configuration(
    feed_flow_m3h=100,
    water_recovery_fraction=0.75,
    membrane_type="brackish"
)

# Step 2: Simulate the best configuration
best_config = configs["configurations"][0]
results = await simulate_ro_system(
    configuration=best_config,
    feed_salinity_ppm=5000,
    feed_ion_composition='{"Na+": 1917, "Cl-": 3083}',  # Approximate NaCl
    feed_temperature_c=25.0
)
```

### High Recovery Design (>75%)
```python
# Request high recovery with recycle enabled
configs = await optimize_ro_configuration(
    feed_flow_m3h=50,
    water_recovery_fraction=0.90,  # 90% recovery
    allow_recycle=True,
    membrane_type="brackish"
)
# The optimizer will automatically configure 3 stages with recycle
```

### Custom Flux Targets
```python
# Specify per-stage flux targets for conservative design
configs = await optimize_ro_configuration(
    feed_flow_m3h=100,
    water_recovery_fraction=0.75,
    flux_targets_lmh="[18, 15, 12]",  # Decreasing flux by stage
    flux_tolerance=0.10  # ±10% tolerance
)
```

## Ion Composition Guidelines

### Typical Ion Compositions (mg/L)

**Brackish Water (TDS ~5000 ppm)**
```json
{
  "Na+": 1200,
  "Ca2+": 120,
  "Mg2+": 60,
  "K+": 20,
  "Cl-": 2100,
  "SO4-2": 200,
  "HCO3-": 150
}
```

**Seawater (TDS ~35000 ppm)**
```json
{
  "Na+": 10780,
  "Ca2+": 412,
  "Mg2+": 1280,
  "K+": 399,
  "Cl-": 19350,
  "SO4-2": 2710,
  "HCO3-": 142
}
```

### Simplified Compositions
For preliminary designs, you can use simplified compositions:
- **NaCl equivalent**: `{"Na+": 0.393 * TDS, "Cl-": 0.607 * TDS}`
- **Typical groundwater**: Scale the brackish water example to match TDS

## Interpreting Results

### Performance Metrics
- **System Recovery**: Should match target within ±1%
- **Specific Energy**: 
  - Brackish: 0.5-2.0 kWh/m³
  - Seawater: 2.5-4.0 kWh/m³
- **Permeate Quality**: Typically <500 mg/L TDS

### Economics (WaterTAP-based)
- **LCOW**: Levelized cost includes CAPEX and OPEX
- **Capital Cost**: Based on EPA cost curves
- **Operating Cost**: Energy, chemicals, membrane replacement

### Scaling Indicators
- **Langelier Saturation Index (LSI)**: <2.0 recommended
- **Stiff-Davis Index (SDI)**: <1.3 recommended
- **Calcium Sulfate Saturation**: <100% recommended

## Common Issues and Solutions

### "No configuration achieved target recovery"
- Enable recycle: `allow_recycle=True`
- Reduce flux targets for more staging flexibility
- Consider if target recovery is realistic for water quality

### "Invalid ion composition"
- Ensure JSON format is correct (double quotes for keys)
- All concentrations must be positive numbers
- Ion charge must balance (handled automatically by MCAS)

### "Simulation timeout"
- Complex configurations may take longer
- Check if configuration is reasonable (not too many vessels)
- Timeout is set to 30 minutes but most complete in <1 minute

## Advanced Features

### Membrane Property Customization
```python
membrane_properties = {
    "water_permeability_coefficient": 4.2e-12,  # m/s-Pa
    "salt_permeability_coefficient": 3.5e-8     # m/s
}
```

### Optimization Control
- `optimize_pumps=True`: Automatically adjusts pressures
- `optimize_pumps=False`: Uses pressure estimates from configuration

### Multi-Stage Pressure Management
The system automatically handles:
- Booster pumps between stages
- Pressure drop through vessels
- Optimal pressure distribution for energy efficiency

## Best Practices

1. **Always validate ion composition totals approximately match TDS**
2. **Start with standard configurations before customizing**
3. **Check scaling indices in results to avoid membrane fouling**
4. **Use notebook outputs for detailed troubleshooting**
5. **Consider energy-recovery devices (ERD) for seawater applications**

Remember: This server implements AWWA/AMTA design standards and uses the scientifically rigorous WaterTAP framework with IDAES optimization capabilities.