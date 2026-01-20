# RO Design MCP Server

[![MCP](https://img.shields.io/badge/MCP-1.0-blue)](https://modelcontextprotocol.io)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org)
[![WaterTAP](https://img.shields.io/badge/WaterTAP-0.12.0-green)](https://watertap.org)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production-success)](https://github.com/puran-water/ro-design-mcp)

Model Context Protocol server for reverse osmosis system design optimization and simulation using WaterTAP.


> **⚠️ DEVELOPMENT STATUS: This project is under active development and is not yet production-ready. APIs, interfaces, and functionality may change without notice. Use at your own risk for evaluation and testing purposes only. Not recommended for production deployments.**

## Overview

This MCP server provides three primary tools for RO system design:

1. **optimize_ro_configuration**: Generates vessel array configurations for specified recovery targets
2. **simulate_ro_system_v2**: Performs detailed WaterTAP simulations with economic analysis
3. **get_ro_defaults**: Returns default economic and chemical dosing parameters

## Technical Capabilities

### Membrane Catalog (NEW v2.0)
- **67 manufacturer-specific membrane models** from FilmTec/DuPont catalog
- Models include BW30_PRO_400, BW30XFRLE_400, SW30HRLE_440, and many more
- **Ion-specific rejection modeling** based on diffusivity and charge effects
- Temperature-corrected permeability using Arrhenius equations
- Feed spacer profiles for accurate hydraulic modeling

### Configuration Optimization
- Generates all viable 1-3 stage vessel array configurations
- Supports specific membrane models (not just generic "brackish"/"seawater")
- Automatic concentrate recycle calculation for high recovery (up to 95%)
- Flux balancing across stages with configurable tolerance
- Minimum concentrate flow constraints per vessel type
- Intelligent search algorithms for large-scale systems

### Simulation Engine (Hybrid Approach)
- **Literature-based performance calculations** using proven RO design equations
- **WaterTAP costing integration** for economic analysis via mock unit models
- Multi-component ion tracking (13+ species via PHREEQC)
- Stage-wise mass balance and pressure calculations
- Pump power calculations from feed pressure and flow
- Thermodynamically-rigorous concentrate chemistry via PHREEQC

### Economic Analysis
- WaterTAPCostingDetailed framework integration
- Component-level CAPEX tracking (pumps, membranes, ERD)
- Operating cost breakdown (energy, chemicals, maintenance)
- Levelized cost of water (LCOW) calculation

### Recent Improvements (v2.3 - 2025-09-22)
- **Enhanced PHREEQC Integration**:
  - Uses PHREEQC REACTION for thermodynamically-accurate concentrate chemistry
  - Models pH shifts, CO2 degassing, and ion speciation during concentration
  - Tracks pH-dependent silica solubility via saturation indices (not fixed mg/L)
  - Removed all algebraic fallbacks - ensures thermodynamic rigor
- **pH Optimization Module**:
  - New `pHRecoveryOptimizer` class for finding optimal pH to achieve target recovery
  - Calculates chemical doses (NaOH, HCl, H2SO4) for pH adjustment
  - Compares different pH adjustment chemicals with cost analysis
- **Dynamic Chemical Dosing**:
  - New `ChemicalDosingCalculator` for antiscalant and CIP chemical calculations
  - Severity-based dosing recommendations
  - Product-specific recommendations (SUEZ, Nalco, Avista)
- **Sustainable Recovery Calculations**:
  - Maximum recovery based on mineral saturation limits
  - Antiscalant-aware SI thresholds
  - Safety margin recommendations
- **Previous v2.2 Features**:
  - Water Chemistry Validation: Centralized ion composition handling (DRY principle)
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
- `membrane_model` (string): Specific membrane model (e.g., "BW30_PRO_400", "SW30HRLE_440")
- `allow_recycle` (bool, optional): Allow concentrate recycle for high recovery
- `max_recycle_ratio` (float, optional): Maximum recycle ratio (0-1)
- `flux_targets_lmh` (string, optional): JSON array of per-stage flux targets
- `flux_tolerance` (float, optional): Flux tolerance fraction
- `feed_ion_composition` (string, optional): JSON object of ion concentrations in mg/L
- `feed_temperature_c` (float, optional): Feed temperature in Celsius (default 25°C)
- `feed_ph` (float, optional): Feed pH value (default 7.5)

Returns: Array of configurations with vessel counts, flows, recovery metrics, and sustainable recovery calculations based on scaling limits.

#### simulate_ro_system_v2
Performs WaterTAP simulation with economic analysis.

Parameters:
- `configuration` (object): Output from optimize_ro_configuration
- `feed_salinity_ppm` (float): Feed water salinity in ppm
- `feed_ion_composition` (string): JSON object of ion concentrations in mg/L
- `membrane_model` (string): Specific membrane model (must match configuration)
- `feed_temperature_c` (float, optional): Feed temperature in Celsius (default 25°C)
- `economic_params` (object, optional): Economic parameters
- `chemical_dosing` (object, optional): Chemical dosing parameters

Returns: Comprehensive simulation results including performance, economics, and ion tracking.

## API Version History

### v2.3 (Current - 2025-09-22)
- **Enhanced PHREEQC Integration**: Full thermodynamic modeling with REACTION blocks
- **pH Optimization**: New module for pH-based recovery optimization
- **Dynamic Chemical Dosing**: Intelligent antiscalant and pH adjustment calculations
- **Silica SI Tracking**: pH-dependent silica solubility via saturation indices
- **No Fallbacks**: Removed algebraic approximations - pure thermodynamic calculations

### v2.2 (2025-09-21)
- **PHREEQC Integration**: Thermodynamic scaling predictions with PhreeqPython
- **Sustainable Recovery**: Maximum recovery calculations based on scaling limits
- **Antiscalant Modeling**: Proper supersaturation limits for different antiscalant scenarios
- **Water Chemistry Validation**: Centralized ion composition validation and parsing

### v2.0 (2025-09-19)
- **Membrane Catalog System**: 67 manufacturer-specific membrane models
- **Ion-Specific B Values**: Physically-based rejection modeling per ion
- **Removed v1 API**: Only simulate_ro_system_v2 available
- **Hybrid Simulator**: Literature-based performance + WaterTAP costing
- Temperature corrections and spacer profiles
- Multi-ion tracking via PHREEQC (13+ species)
- WaterTAPCostingDetailed for transparent economics
- Removed full WaterTAP flowsheet simulator (non-functional)

### v1.0 (Deprecated)
- Generic "brackish" and "seawater" membrane types only
- Basic WaterTAPCosting
- Simple NaCl-based rejection modeling

## Technical Implementation

### Core Modules

#### Configuration Optimizer (`utils/optimize_ro.py`)
- Implements vessel array generation logic
- Handles flux balancing and recovery calculations
- Manages concentrate recycle for high recovery

#### Hybrid RO Simulator (`utils/hybrid_ro_simulator.py`)
- Literature-based performance calculations (Film Theory Model)
- Stage-wise pressure drop and osmotic pressure calculations
- Ion-specific rejection using Stokes radius and charge
- Integrates WaterTAP costing via lightweight mock units

#### Mock Units for Costing (`utils/mock_units_for_costing.py`)
- Lightweight UnitModelBlockData classes for WaterTAP integration
- MockPump, MockRO, MockChemicalAddition, MockStorageTank, MockCartridgeFilter
- Calls WaterTAP's native costing methods without full flowsheet simulation

#### PHREEQC Integration (`utils/phreeqc_client.py`)
- Thermodynamically-accurate concentrate chemistry via REACTION blocks
- pH tracking, CO2 degassing, ion speciation during concentration
- Saturation index calculations for scaling prediction
- Maximum sustainable recovery determination

#### pH Recovery Optimizer (`utils/ph_recovery_optimizer.py`)
- Finds optimal pH to achieve target recovery
- Chemical dose calculations (NaOH, HCl, H2SO4)
- Cost-benefit analysis of pH adjustment strategies

### Key Technical Decisions

#### Hybrid Simulator Approach
- Uses proven literature-based equations for RO performance
- Avoids full WaterTAP flowsheet simulation (convergence issues)
- Integrates WaterTAP costing for economic accuracy
- More robust and faster than full thermodynamic simulation

#### PHREEQC for Chemistry
- Thermodynamically-rigorous concentrate chemistry
- Accurate pH tracking and ion speciation
- Scaling prediction via saturation indices
- Superior to algebraic approximations

## Supported Ions

Currently tracked via PHREEQC and hybrid simulator:
- Cations: Na⁺, Ca²⁺, Mg²⁺, K⁺, Sr²⁺, Ba²⁺
- Anions: Cl⁻, SO₄²⁻, HCO₃⁻, CO₃²⁻, F⁻
- Neutral: SiO₂ (as amorphous silica)

Future enhancements:
- B(OH)₃ (boric acid, neutral species)
- NO₃⁻ (nitrate)

## Performance Characteristics

### Typical Execution Times (Hybrid Simulator)
- Configuration optimization:
  - Small flows (< 500 m³/h): < 1 second
  - Large flows (1000-10000 m³/h): 2-5 seconds using intelligent search
- Single-stage simulation: 0.5-1.0 seconds
- Multi-stage simulation: 0.8-1.5 seconds
- With PHREEQC chemistry: Additional 0.2-0.5 seconds
- **10-30x faster** than full WaterTAP flowsheet simulation

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

#### Configuration Not Meeting Target Recovery
- Symptom: Target recovery not achieved in any configuration
- Solution: Check if target exceeds sustainable recovery (scaling limits). Use pH optimization or lower recovery target.

#### High LCOW Values
- Symptom: LCOW appears unrealistically high
- Solution: Verify feed salinity and economic parameters. Check membrane_model is appropriate for application (BW vs SW).

#### Missing Ion Data in Results
- Symptom: Ion concentrations not in simulation output
- Solution: Ensure feed_ion_composition is provided as JSON string in simulate_ro_system_v2

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