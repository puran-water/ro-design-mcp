# Changelog

All notable changes to the RO Design MCP Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2025-09-08

### Added
- **Intelligent search strategies** for configuration optimization:
  - Binary search for single-stage configurations with >100 vessels
  - Geometric progression search for multi-stage configurations
  - Pre-validation to detect and warn about large vessel counts
- **Scale-aware optimization** that automatically adapts to flow magnitude
- Support for extremely large flows (up to 10,000+ m³/h) without hanging

### Fixed
- Configuration tool hanging on large flows (>1000 m³/h)
- Performance issues when vessel count exceeds 500 per stage
- Timeout issues with brute-force vessel iteration

### Changed
- Configuration search algorithm from O(n) to O(log n) for large vessel counts
- Added adaptive thresholds: standard (<100 vessels), optimized (100-1000), ultra-optimized (>1000)

### Performance Improvements
- Large flow (6250 m³/h) configuration: From timeout/hang to <5 seconds
- Medium flow (1000 m³/h) configuration: From 30+ seconds to <5 seconds
- Maintains <1 second performance for small flows (<500 m³/h)

## [2.1.0] - 2025-09-04

### Added
- Full multi-ion tracking for all 12+ species modeled by MCAS
- Physical constraint bounds to prevent unrealistic solutions:
  - Pump pressure limits: 10-83 bar
  - Water flux bounds: 1e-6 to 3e-2 kg/m²/s  
  - Solute flux bounds: 0 to 1e-3 kg/m²/s
  - Concentration limits: up to 100 g/L
- Ion-specific rejection reporting for all modeled species
- Comprehensive technical documentation

### Fixed
- Concentrate recycle systems producing physically impossible results (452 bar, 99.95% recovery)
- Results extractor now reports all ions from `model.fs.properties.solute_set`
- NaCl equivalent override removed from server.py and CLI

### Changed
- Default behavior: `use_nacl_equivalent=False` for direct MCAS modeling
- Results extractor enhanced to iterate over all solutes dynamically
- Recovery matching accuracy improved to ±2%

### Technical Implementation
- Modified `utils/ro_model_builder_v2.py`: Added comprehensive physical bounds
- Modified `utils/ro_results_extractor_v2.py`: Dynamic ion extraction from solute_set
- Modified `server.py`: Removed hardcoded NaCl equivalent overrides
- Modified `utils/simulate_ro_cli.py`: Changed default to MCAS direct modeling

## [2.0.0] - 2025-09-03

### Added
- V2 API with WaterTAPCostingDetailed framework
- Enhanced economic modeling with transparent CAPEX/OPEX breakdown
- Chemical consumption tracking (antiscalant, CIP chemicals)
- Ancillary equipment costing (cartridge filters, CIP systems, ERD)
- Support for optimization mode (model handle generation)

### Changed
- Migrated from WaterTAPCosting to WaterTAPCostingDetailed
- Enhanced economic parameter configuration
- Improved granularity of cost reporting

## [1.2.0] - 2025-09-03

### Added
- Full support for multi-component ionic compositions including divalent ions (Ca²⁺, Mg²⁺, SO₄²⁻)
- Two-stage initialization strategy for improved numerical stability
- Automatic detection of available geometry variables based on configuration
- Enhanced documentation for FBBT robustness improvements

### Changed
- Switched from `MassTransferCoefficient.calculated` to `MassTransferCoefficient.fixed` for better stability
- Updated water flux lower bounds from 1e-4 to 1e-6 kg/m²/s for less restrictive operation
- Fixed mass transfer coefficient K at 2e-5 m/s for all solutes at boundary positions
- Membrane geometry now uses lumped model approach (length = 1.016m per element)
- Channel height fixed at 7.9e-4 m (31 mil) standard feed spacer

### Fixed
- Resolved FBBT (Feasibility-Based Bounds Tightening) failures with multi-component feeds
- Fixed division by zero errors in concentration polarization equations
- Corrected configuration conflicts between CP type and mass transfer coefficient
- Fixed AttributeError when accessing channel_height and spacer_porosity
- Resolved flux variable location issues (main unit vs feed_side)

### Technical Details
- Concentration polarization equations now protected against unbounded intervals
- Mass transfer coefficient bounds properly enforced at [1e-5, 3e-4] m/s range
- Two-stage solver simplified to use constraint deactivation/reactivation only
- Configuration parameters cannot be changed after model build (as per WaterTAP design)

## [1.1.0] - 2025-08-15

### Added
- Initial MCP server implementation
- Support for 1-3 stage RO configurations
- Concentrate recycle for high recovery operations
- WaterTAP integration with MCAS property package
- Economic analysis with LCOW calculations

### Features
- Automatic vessel array optimization
- Flux-based design methodology
- Pressure optimization for recovery targets
- Detailed Jupyter notebook reporting

## [1.0.0] - 2025-07-01

### Added
- Initial release of RO Design MCP Server
- Basic optimization functionality
- NaCl-only simulations
- Single and two-stage configurations