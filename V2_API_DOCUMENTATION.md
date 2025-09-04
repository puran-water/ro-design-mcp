# RO Design MCP Server - V2 API Documentation

## Overview

The V2 API represents a significant enhancement to the RO Design MCP Server, transforming it into a showcase implementation for WaterTAP-based process unit servers. This version implements comprehensive economic modeling with full transparency, detailed chemical consumption tracking, and support for plant-wide optimization.

## Key Enhancements in V2

### 1. WaterTAPCostingDetailed Framework
- Replaces basic `WaterTAPCosting` with `WaterTAPCostingDetailed`
- Provides granular breakdown of capital and operating costs
- Tracks individual equipment costs with proper categorization
- Supports detailed LCOW component analysis

### 2. Chemical Consumption Tracking
- Tracks actual chemical usage based on process conditions
- No heuristic $/m³ approximations
- Includes:
  - Antiscalant dosing (mg/L)
  - CIP chemical consumption (kg/m²/cleaning)
  - pH adjustment chemicals (if needed)

### 3. Ancillary Equipment
- **Cartridge Filters**: Zero-order pretreatment model
- **CIP System**: Clean-in-place with frequency and chemical tracking
- **Energy Recovery Device (ERD)**: Auto-included for high-pressure systems
- **Translator Blocks**: Bridge between ZO and MCAS property packages

### 4. Plant-Wide Optimization Support
- Returns model handles for orchestration
- Exposes metadata for decision variables and ports
- Compatible with multi-server Pyomo optimization

## API Endpoints

### `simulate_ro_system_v2`

Enhanced simulation with detailed economic modeling.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `configuration` | Dict | Yes | RO configuration from optimize_ro_configuration |
| `feed_salinity_ppm` | float | Yes | Feed water salinity in ppm |
| `feed_ion_composition` | str (JSON) | Yes | Ion concentrations in mg/L |
| `feed_temperature_c` | float | No | Feed temperature (default: 25°C) |
| `membrane_type` | str | No | "brackish" or "seawater" (default: "brackish") |
| `economic_params` | Dict | No | Economic parameters (uses WaterTAP defaults if not provided) |
| `chemical_dosing` | Dict | No | Chemical dosing parameters (uses defaults if not provided) |
| `optimization_mode` | bool | No | If True, returns model handle instead of results |

#### Economic Parameters (with WaterTAP defaults)

```python
{
    "wacc": 0.093,                          # Weighted average cost of capital
    "plant_lifetime_years": 30,             # Plant operational lifetime
    "utilization_factor": 0.9,              # Capacity utilization
    "electricity_cost_usd_kwh": 0.07,       # Electricity cost
    "membrane_cost_brackish_usd_m2": 30,    # Brackish water membrane cost
    "membrane_cost_seawater_usd_m2": 75,    # Seawater membrane cost
    "membrane_replacement_factor": 0.2,      # Annual replacement rate
    "acid_HCl_cost_usd_kg": 0.17,          # HCl cost (37% solution)
    "base_NaOH_cost_usd_kg": 0.59,         # NaOH cost (30% solution)
    "antiscalant_cost_usd_kg": 2.50,       # Antiscalant cost
    "cip_surfactant_cost_usd_kg": 3.00,    # CIP chemical cost
    "land_cost_percent_FCI": 0.0015,       # Land as % of fixed capital
    "working_capital_percent_FCI": 0.05,    # Working capital as % of FCI
    "salaries_percent_FCI": 0.001,         # Salaries as % of FCI
    "benefit_percent_of_salary": 0.9,       # Benefits multiplier
    "maintenance_costs_percent_FCI": 0.008, # Maintenance as % of FCI
    "laboratory_fees_percent_FCI": 0.003,   # Lab fees as % of FCI
    "insurance_and_taxes_percent_FCI": 0.002, # Insurance/taxes as % of FCI
    "include_cartridge_filters": False,     # Include pretreatment
    "include_cip_system": False,           # Include CIP system
    "auto_include_erd": True,              # Auto-add ERD for high pressure
    "erd_efficiency": 0.95,                # ERD efficiency
    "erd_pressure_threshold_bar": 45,      # Pressure threshold for ERD
    "cip_capital_cost_usd_m2": 50          # CIP capital cost per m² membrane
}
```

#### Chemical Dosing Parameters (with defaults)

```python
{
    "antiscalant_dose_mg_L": 3.0,          # Antiscalant dose
    "acid_dose_mg_L": 0.0,                 # Acid dose for pH adjustment
    "base_dose_mg_L": 0.0,                 # Base dose for pH adjustment
    "cip_dose_kg_per_m2": 0.1,            # CIP chemical per m² membrane
    "cip_frequency_per_year": 6            # CIP cleanings per year
}
```

#### Response Structure (Normal Mode)

```python
{
    "status": "success",
    "api_version": "v2",
    "performance": {
        "system_recovery": 0.75,
        "total_permeate_flow_m3_h": 75.0,
        "total_permeate_tds_mg_l": 250.0,
        "specific_energy_kWh_m3": 1.2,
        "total_power_consumption_kW": 90.0
    },
    "economics": {
        "lcow_usd_m3": 0.85,
        "total_capital_cost_usd": 1500000,
        "annual_operating_cost_usd_year": 250000,
        "specific_energy_consumption_kWh_m3": 1.2,
        "capital_breakdown": {
            "membrane_costs": 450000,
            "pump_costs": 300000,
            "pretreatment_costs": 50000,
            "erd_costs": 200000,
            "indirect_costs": 500000
        },
        "operating_breakdown": {
            "electricity_cost": 120000,
            "membrane_replacement": 90000,
            "chemical_costs": 15000,
            "fixed_operating_costs": 25000
        },
        "lcow_breakdown": {
            "capital_contribution": 0.35,
            "electricity_contribution": 0.30,
            "membrane_replacement_contribution": 0.15,
            "chemical_contribution": 0.05,
            "fixed_cost_contribution": 0.15
        }
    },
    "chemical_consumption": {
        "antiscalant": {
            "annual_consumption_kg": 2000,
            "annual_cost_usd": 5000,
            "dose_mg_L": 3.0
        },
        "cip_chemicals": {
            "annual_consumption_kg": 600,
            "annual_cost_usd": 1800,
            "cleanings_per_year": 6
        }
    },
    "stage_results": [...],  // Detailed stage-by-stage results
    "mass_balance": {...},   // Mass balance verification
    "ion_tracking": {...}    // Ion-specific rejection and concentration
}
```

#### Response Structure (Optimization Mode)

```python
{
    "status": "success",
    "api_version": "v2",
    "model_handle": "uuid-string",
    "metadata": {
        "inputs": {
            "feed_flow": {"pyomo_path": "fs.feed.outlet.flow_mass[0]", ...},
            "feed_pressure": {"pyomo_path": "fs.pump1.outlet.pressure[0]", ...}
        },
        "decision_vars": {
            "stage1_area": {"pyomo_path": "fs.ro_stage1.area", ...},
            "pump1_pressure": {"pyomo_path": "fs.pump1.outlet.pressure[0]", ...}
        },
        "outputs": {
            "lcow": {"pyomo_path": "fs.costing.LCOW", "units": "$/m3"},
            "specific_energy": {"pyomo_path": "fs.costing.specific_energy_consumption", ...}
        },
        "ports": {
            "feed_inlet": "fs.feed.inlet",
            "permeate_outlet": "fs.product.inlet",
            "brine_outlet": "fs.disposal.inlet"
        }
    }
}
```

### `get_ro_defaults`

Returns default economic and chemical dosing parameters aligned with WaterTAP standards.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `membrane_type` | str | No | "brackish" or "seawater" (default: "brackish") |

#### Response

```python
{
    "economic_params": {...},  # Full economic parameter dictionary
    "chemical_dosing": {...}   # Full chemical dosing dictionary
}
```

## Usage Examples

### Example 1: Basic V2 Simulation with Defaults

```python
# Get optimized configuration
config = await optimize_ro_configuration(
    feed_flow_m3h=100,
    water_recovery_fraction=0.75,
    membrane_type="brackish"
)

# Run v2 simulation with defaults
result = await simulate_ro_system_v2(
    configuration=config["configurations"][0],
    feed_salinity_ppm=4000,
    feed_ion_composition='{"Na_+": 1200, "Cl_-": 2100, "Ca_2+": 120}',
    feed_temperature_c=25.0,
    membrane_type="brackish"
)

print(f"LCOW: ${result['economics']['lcow_usd_m3']:.3f}/m³")
```

### Example 2: Custom Economics with Ancillary Equipment

```python
# Get defaults and customize
defaults = await get_ro_defaults(membrane_type="seawater")
economic_params = defaults["economic_params"]
economic_params["electricity_cost_usd_kwh"] = 0.10
economic_params["include_cartridge_filters"] = True
economic_params["include_cip_system"] = True

chemical_dosing = defaults["chemical_dosing"]
chemical_dosing["antiscalant_dose_mg_L"] = 5.0

# Run simulation
result = await simulate_ro_system_v2(
    configuration=config,
    feed_salinity_ppm=35000,
    feed_ion_composition=seawater_composition,
    economic_params=economic_params,
    chemical_dosing=chemical_dosing
)
```

### Example 3: Optimization Mode for Plant-Wide Integration

```python
# Build model for optimization
result = await simulate_ro_system_v2(
    configuration=config,
    feed_salinity_ppm=5000,
    feed_ion_composition=ion_comp,
    economic_params=economic_params,
    optimization_mode=True  # Returns model handle
)

model_handle = result["model_handle"]
# Use handle for plant-wide optimization across multiple MCP servers
```

## Migration from V1

The V2 API is accessed through new endpoints while V1 remains available:
- Use `simulate_ro_system_v2` instead of `simulate_ro_system`
- Economic parameters are now explicit and customizable
- Chemical tracking provides actual consumption, not estimates
- Results include comprehensive cost breakdowns

## Technical Implementation Details

### Model Building (`ro_model_builder_v2.py`)
- Implements `WaterTAPCostingDetailed` for transparency
- Adds ZO pretreatment units with proper database connection
- Includes Translator blocks for property package bridging
- Configures ERD with automatic detection logic
- Implements CIP system as custom block with expressions

### Results Extraction (`ro_results_extractor_v2.py`)
- Extracts detailed capital cost breakdown by equipment type
- Calculates operating costs with component tracking
- Provides LCOW breakdown showing contribution of each cost element
- Tracks chemical consumption in physical units (kg/year)

### Economic Defaults (`economic_defaults.py`)
- Centralized source of truth for all default values
- Aligned with WaterTAP standard assumptions
- Prevents hidden defaults in code
- Supports membrane-type-specific defaults

## Future Enhancements

1. **Advanced Optimization Features**
   - Multi-objective optimization support
   - Uncertainty quantification
   - Sensitivity analysis tools

2. **Additional Unit Operations**
   - Boron removal (second pass RO)
   - Remineralization
   - Advanced pretreatment options

3. **Integration Features**
   - Standard interfaces for plant-wide optimization
   - Event-based simulation for dynamic operation
   - Digital twin capabilities

## Support

For issues or questions about the V2 API:
- GitHub Issues: https://github.com/anthropics/claude-code/issues
- Documentation: https://docs.anthropic.com/en/docs/claude-code/