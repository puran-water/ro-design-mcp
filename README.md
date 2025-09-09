# RO Design MCP Server

[![MCP](https://img.shields.io/badge/MCP-1.0-blue)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org)
[![WaterTAP](https://img.shields.io/badge/WaterTAP-0.12.0-green)](https://watertap.org)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production-success)](https://github.com/puran-water/ro-design-mcp)

Model Context Protocol server for reverse osmosis system design optimization and simulation using WaterTAP.

## Overview

This MCP server provides two primary tools for RO system design:

1. **optimize_ro_configuration**: Generates vessel array configurations for specified recovery targets
2. **simulate_ro_system_v2**: Performs detailed WaterTAP simulations with economic analysis

## Technical Capabilities

### Configuration Optimization
- Generates all viable 1-3 stage vessel array configurations
- Automatic concentrate recycle calculation for high recovery (up to 95%)
- Flux balancing across stages with configurable tolerance
- Minimum concentrate flow constraints per vessel type
- Intelligent search algorithms for large-scale systems

### Simulation Engine
- WaterTAP-based process modeling with MCAS property package
- Multi-component ion tracking (13+ species supported)
- Stage-wise mass balance and pressure calculations
- Pump pressure optimization for recovery matching
- Physical constraint enforcement (pressure, flux, concentration limits)
- Seawater-specific initialization and constraint handling

### Economic Analysis
- WaterTAPCostingDetailed framework integration
- Component-level CAPEX tracking (pumps, membranes, ERD)
- Operating cost breakdown (energy, chemicals, maintenance)
- Levelized cost of water (LCOW) calculation

### Recent Improvements (v2.1)
- Enhanced seawater simulation with system-level recovery constraints
- Improved flux bound relaxation for high-TDS feeds
- Progressive initialization fallback for challenging conditions
- Optimized solute recovery parameters for MCAS charge balance

## Installation

### Requirements
- Python 3.10+ (3.12 tested)
- Virtual environment
- Git

### Setup
```bash
git clone https://github.com/puran-water/ro-design-mcp.git
cd ro-design-mcp
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration
```bash
cp .env.example .env
# Edit .env to set local paths
```

## MCP Server Usage

### Starting the Server
```bash
python server.py
```

The server listens on stdio for MCP protocol messages.

### Available Tools

#### optimize_ro_configuration
Generates vessel array configurations for target recovery.

Parameters:
- `feed_flow_m3h` (float): Feed flow rate in m³/h
- `water_recovery_fraction` (float): Target recovery (0-1)
- `membrane_type` (string): "brackish" or "seawater"
- `flux_targets_lmh` (string, optional): JSON array of per-stage flux targets
- `flux_tolerance` (float, optional): Flux tolerance fraction

Returns: Array of configurations with vessel counts, flows, and recovery metrics.

#### simulate_ro_system_v2
Performs WaterTAP simulation with economic analysis.

Parameters:
- `configuration` (object): Output from optimize_ro_configuration
- `feed_salinity_ppm` (float): Feed water salinity in ppm
- `feed_ion_composition` (string): JSON object of ion concentrations in mg/L
- `feed_temperature_c` (float): Feed temperature in Celsius
- `membrane_type` (string): "brackish" or "seawater"
- `economic_params` (object, optional): Economic parameters
- `chemical_dosing` (object, optional): Chemical dosing parameters

Returns: Comprehensive simulation results including performance, economics, and ion tracking.

## API Version History

### v2 (Current)
- Direct MCAS multi-ion modeling (13+ species)
- WaterTAPCostingDetailed for transparent economics
- Physical constraint bounds to prevent unrealistic solutions
- Full ion-specific rejection tracking
- Concentrate recycle system fixes

### v1 (Deprecated)
- Basic WaterTAPCosting
- Limited to NaCl equivalent modeling
- No physical constraint enforcement

## Technical Implementation

### Core Modules

#### Configuration Optimizer (`utils/optimize_ro.py`)
- Implements vessel array generation logic
- Handles flux balancing and recovery calculations
- Manages concentrate recycle for high recovery

#### Model Builder (`utils/ro_model_builder_v2.py`)
- Constructs WaterTAP flowsheets
- Applies physical constraints:
  - Pump pressure: 10-83 bar
  - Water flux: 1e-6 to 3e-2 kg/m²/s
  - Solute flux: 0 to 1e-3 kg/m²/s
  - Concentration: up to 100 g/L

#### MCAS Builder (`utils/mcas_builder.py`)
- Configures multi-component property package
- Defines ion properties (MW, charge, diffusivity)
- Handles electroneutrality checking

#### Solver (`utils/ro_solver.py`)
- Sequential initialization strategy
- Pump pressure optimization
- Scaling factor application after NDP establishment

#### Results Extractor (`utils/ro_results_extractor_v2.py`)
- Extracts all modeled ion concentrations
- Calculates stage-wise and overall rejections
- Computes economic metrics

### Key Technical Fixes

#### FBBT Error Resolution
- Moved `calculate_scaling_factors()` to after pump initialization
- Ensures positive Net Driving Pressure before constraint checking

#### Recycle System Stabilization
- Added physical bounds to prevent solver exploring unrealistic space
- Fixed recycle flow initialization
- Proper mixing block configuration

#### Multi-Ion Tracking
- Results extractor iterates over `model.fs.properties.solute_set`
- Reports all ions modeled by MCAS, not just Na⁺/Cl⁻

## Supported Ions

Currently modeled by MCAS:
- Cations: Na⁺, Ca²⁺, Mg²⁺, K⁺, Sr²⁺, Ba²⁺
- Anions: Cl⁻, SO₄²⁻, HCO₃⁻, CO₃²⁻, NO₃⁻, F⁻

Pending implementation:
- B(OH)₃ (boric acid, neutral species)

## Performance Characteristics

### Typical Execution Times
- Configuration optimization: 
  - Small flows (< 500 m³/h): < 1 second
  - Large flows (1000-10000 m³/h): 2-5 seconds using intelligent search
- Single-stage simulation: 10-15 seconds
- Multi-stage simulation: 15-50 seconds
- Complex ion chemistry: Additional 5-10 seconds

### Configuration Tool Improvements (v1.1)
- **Intelligent Search Strategies**: Binary search for single-stage, geometric progression for multi-stage
- **Scale-Aware Optimization**: Automatically detects and handles large vessel counts (>100)
- **Performance**: Handles flows up to 10,000+ m³/h without hanging
- **Pre-validation**: Warns when configurations may require >500 vessels per stage

### Recovery Accuracy
- Configuration to simulation matching: ±2%
- Pump optimization convergence: < 0.5% error

### Rejection Ranges
- Divalent ions: 98-99.9%
- Monovalent ions: 94-99%
- Neutral species (boron): 40-60%

## Troubleshooting

### Common Issues

#### FBBT Constraint Violations
- Symptom: "Detected an infeasible constraint during FBBT"
- Solution: Ensure scaling factors applied after pump initialization

#### Unrealistic Recycle Results
- Symptom: Pressures > 100 bar, recovery > 99%
- Solution: Verify physical bounds are applied in model builder

#### Missing Ion Data
- Symptom: Only Na⁺/Cl⁻ in results
- Solution: Ensure v2 API is used and results extractor updated

## Development

### Running Tests
```bash
pytest tests/
```

### Logging
Set environment variable:
```bash
export LOGLEVEL=DEBUG
```

### Artifact Storage
Simulation artifacts stored in `artifacts/` directory with run IDs.

## Dependencies

Core dependencies:
- `watertap==0.12.0` - Process modeling framework
- `pyomo==6.7.0` - Optimization modeling
- `idaes-pse==2.2.0` - Process systems engineering
- `ipopt` - Nonlinear optimization solver

See `requirements.txt` for complete list.

## License

MIT License - See LICENSE file for details.

## Support

Report issues at: https://github.com/puran-water/ro-design-mcp/issues