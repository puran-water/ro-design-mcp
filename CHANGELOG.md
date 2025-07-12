# Changelog

All notable changes to the RO Design MCP Server will be documented in this file.

## [2.0.0] - 2025-01-12

### Added
- Multi-configuration output: Returns ALL viable stage configurations (1, 2, 3 stages) instead of single "best" option
- Concentrate flow margin reporting: Each stage reports margin above minimum required flow
- Enhanced recycle optimization: Explores all stage options for high recovery scenarios
- Comprehensive test suite for multi-configuration scenarios
- Detailed technical documentation in README

### Changed
- **BREAKING**: Tool now returns multiple configurations for economic comparison instead of single configuration
- Recovery tolerance: Now strictly enforces meeting target recovery (no undershooting allowed)
- Flux tolerance: Can go below target flux if necessary to meet recovery requirements
- Recycle algorithm: Fixed to store all viable configurations during iterations
- Deduplication: Simplified to keep best configuration per stage count

### Fixed
- Recycle optimization convergence logic that was preventing multiple stage options
- Single-stage configuration detection for lower recovery targets
- Duplicate configuration removal in recycle scenarios
- Recovery targeting to reject configurations below target

### Technical Details
- Modified `try_without_recycle()` to return list of all viable configurations
- Updated `optimize_with_recycle()` to collect configurations from all iterations
- Changed `try_with_recycle_inner()` to return multiple stage options
- Improved convergence logic to control iterations without limiting configuration storage
- Added concentrate margin calculations to server response formatting

## [1.0.0] - 2025-01-11

### Initial Release
- Basic RO vessel array optimization
- Single configuration output with scoring system
- Support for brackish and seawater membranes
- Concentrate recycle for high recovery
- Custom flux targets and tolerance
- MCP server implementation