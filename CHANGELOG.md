# Changelog

All notable changes to the RO Design MCP Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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