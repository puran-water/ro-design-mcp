# RO Design MCP Server

An STDIO MCP server for reverse osmosis (RO) system design optimization. This server provides tools for determining optimal vessel array configurations and running WaterTAP simulations for RO systems.

## Features

### Tool 1: `optimize_ro_configuration`
- **Multi-Configuration Output**: Returns ALL viable stage configurations (1, 2, and 3 stages) for economic comparison
- **Comprehensive Design**: Each configuration represents different CAPEX/OPEX tradeoffs
- Generates optimal RO vessel array configurations based on flow and recovery targets
- Supports both brackish water and seawater applications
- Handles high recovery scenarios with concentrate recycle
- Uses industry-standard flux and concentrate flow constraints
- Returns detailed stage-by-stage design parameters including concentrate flow margins
- **Strict Recovery Targeting**: Only returns configurations that meet or exceed target recovery (no undershooting)
- **Flexible Flux Control**: Allows flux below tolerance if necessary to meet recovery (global optimization only)
- **Robust Flux Parameters**: Supports custom flux targets and tolerances with comprehensive validation
- **Multiple Input Formats**: Accepts flux targets as simple numbers ("20") or JSON arrays ("[22, 18, 15]")

### Tool 2: `simulate_ro_system`
- Runs WaterTAP simulations for detailed performance analysis
- Calculates LCOW (Levelized Cost of Water)
- Provides energy consumption metrics
- Performs mass balance verification
- Stage-by-stage pressure and TDS predictions
- Economic analysis including CAPEX and OPEX
- Optional pump pressure optimization
- **MCAS Property Package Support**: Ion-specific modeling for detailed water chemistry
- **Scaling Prediction**: Saturation indices for common minerals (CaCO₃, CaSO₄, etc.)
- **Antiscalant Recommendations**: Dosage and product suggestions based on scaling risk

## Key Improvements (v2.0)

### Multi-Configuration Approach
The server now returns ALL viable configurations instead of selecting a single "best" option:
- Different stage counts have different CAPEX/OPEX tradeoffs
- 1-stage: Lowest CAPEX but limited recovery (~57% max)
- 2-stage: Moderate CAPEX, suitable for 60-85% recovery
- 3-stage: Higher CAPEX but can achieve >90% recovery
- Recycle options: Lower CAPEX but higher OPEX (pumping costs)

### Enhanced Features
- **Recovery Tolerance**: Zero tolerance for undershooting target recovery
- **Flux Flexibility**: Can go below flux tolerance if needed to meet recovery
- **Concentrate Margins**: Reports margin above minimum flow for each stage
- **Recycle Optimization**: Explores all stage options for high recovery cases

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd ro-design-mcp

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Running the Server

```bash
python server.py
```

### Example Tool Usage

```python
# Basic configuration for 75% recovery - returns multiple options
result = await optimize_ro_configuration(
    feed_flow_m3h=100,
    water_recovery_fraction=0.75,
    membrane_type="brackish"
)
# Returns: 2-stage configurations with/without minimal recycle

# High recovery with concentrate recycle - returns all viable options
result = await optimize_ro_configuration(
    feed_flow_m3h=150,
    water_recovery_fraction=0.96,
    membrane_type="brackish",
    allow_recycle=True,
    max_recycle_ratio=0.9
)
# Returns: 2-stage and 3-stage configurations with different recycle ratios

# Custom flux targets (as JSON string)
result = await optimize_ro_configuration(
    feed_flow_m3h=100,
    water_recovery_fraction=0.75,
    membrane_type="brackish",
    flux_targets_lmh="[22, 18, 15]",  # Per-stage targets
    flux_tolerance=0.15  # ±15%
)

# Single flux target for all stages
result = await optimize_ro_configuration(
    feed_flow_m3h=100,
    water_recovery_fraction=0.50,
    flux_targets_lmh="20",  # Applied to all stages
    flux_tolerance=0.1  # ±10%
)

# Run simulation on selected configuration
config = result["configurations"][0]  # Select first configuration
sim_result = await simulate_ro_system(
    configuration=config,
    feed_salinity_ppm=5000,
    feed_temperature_c=25.0,
    membrane_type="brackish",
    optimize_pumps=False
)

# Run simulation with ion-specific modeling (MCAS)
sim_result = await simulate_ro_system(
    configuration=config,
    feed_salinity_ppm=2000,
    feed_temperature_c=25.0,
    membrane_type="brackish",
    feed_ion_composition='{"Na+": 786, "Cl-": 1214}',  # Ion-specific composition
    optimize_pumps=False
)
```

### Response Format

Each configuration in the response includes:
```json
{
  "stage_count": 2,
  "array_notation": "12:5",
  "total_vessels": 17,
  "total_membrane_area_m2": 4422.04,
  "achieved_recovery": 0.76,
  "recovery_error": 0.01,
  "stages": [
    {
      "stage_number": 1,
      "vessel_count": 12,
      "membrane_area_m2": 3121.44,
      "design_flux_lmh": 17.8,
      "flux_ratio": 0.99,
      "concentrate_per_vessel_m3h": 3.7,
      "min_concentrate_required_m3h": 3.5,
      "concentrate_margin_m3h": 0.2,
      "concentrate_margin_percent": 5.7
    }
  ],
  "recycle_info": {
    "uses_recycle": false
  }
}
```

## Design Principles

### Flux Constraints (LMH)
- **Default targets:** [18, 15, 12] LMH for stages 1, 2, 3
- **Default tolerance:** ±10% of target
- **Flexibility:** Can go below tolerance if needed to meet recovery (global optimization only)
- **Custom flux parameters:**
  - `flux_targets_lmh`: Accepts simple numbers ("20") or JSON arrays ("[22, 18, 15]")
  - `flux_tolerance`: Fraction (0.1 = ±10%)
- **Input validation:** Comprehensive error checking for format and value ranges
- **Emergency limits:** Can reduce flux to 70% of target if required for recovery targeting

### Recovery Guidelines
- Single stage: Up to ~57% recovery (limited by flux)
- Two stages: 60-85% recovery
- Three stages: 75-95% recovery
- With recycle: Can achieve >90% recovery

### Concentrate Flow Constraints
- Minimum concentrate flow per vessel:
  - Stage 1: 3.5 m³/h
  - Stage 2: 3.8 m³/h
  - Stage 3: 4.0 m³/h
- Reports margin above minimum for design verification

## Technical Details

### Optimization Algorithm
1. **Phase 1:** Maximize recovery per stage with full flux flexibility
2. **Phase 2:** Global flux optimization to minimize deviation from targets
3. **Recycle optimization:** Explores all stage configurations

### Multi-Configuration Logic
- Tests 1, 2, and 3 stage configurations for every scenario
- No artificial stage boundaries or scoring
- Returns all configurations that meet recovery target
- Deduplicates by stage count, keeping best recovery match
- Allows downstream economic analysis to select optimal configuration

### Mass Balance
- System boundary: Fresh feed = Permeate + Disposal
- RO unit boundary: Effective feed = Permeate + Final concentrate
- Recycle split: Final concentrate = Recycle + Disposal

### Recovery Targeting
- Strict enforcement: Must meet or exceed target recovery
- No tolerance for undershooting
- Allows flux below normal limits if necessary
- Global optimization to achieve precise recovery

## Configuration

The server uses a flexible YAML-based configuration system:

### Configuration Files
- `config/system_defaults.yaml` - Core system parameters
- `config/economics.yaml` - Economic analysis parameters

### Environment Variable Overrides
Any configuration value can be overridden via environment variables:
```bash
# Override standard element area
export RO_DESIGN_ELEMENT_STANDARD_AREA_M2=40.0

# Override electricity cost
export RO_DESIGN_ENERGY_ELECTRICITY_COST_USD_KWH=0.10

# Override flux tolerance
export RO_DESIGN_TOLERANCES_FLUX_TOLERANCE=0.15
```

### Accessing Configuration in Code
```python
from utils.config import get_config

# Get a configuration value with fallback
flux_tolerance = get_config('tolerances.flux_tolerance', 0.1)

# Load entire configuration
from utils.config import load_config
config = load_config()

## Development Status

### Completed Features
- [x] Tool 1: Configuration optimization
- [x] Multi-configuration output (all viable stage options)
- [x] Concentrate recycle for high recovery
- [x] Mass balance verification
- [x] Custom flux targets and tolerance
- [x] Strict recovery target validation
- [x] Concentrate flow margin reporting
- [x] Enhanced recycle optimization
- [x] Tool 2: WaterTAP simulation structure
- [x] Comprehensive test suite with pytest
- [x] Configuration management system (YAML)
- [x] Input validation and error handling
- [x] Response formatting utilities
- [x] GitHub Actions CI/CD pipeline
- [x] Full WaterTAP integration with Jupyter notebooks
- [x] MCAS property package for ion speciation
- [x] Scaling prediction and antiscalant recommendations
- [x] Elegant initialization strategy for RO models
- [x] Basic recycle support in notebook templates
- [x] IDAES/ipopt solver path configuration

### In Progress
- [ ] Advanced pump optimization (LCOW minimization)
- [ ] HTML report generation from notebooks
- [ ] Additional pump performance metrics
- [ ] Equipment costing breakdowns

## Testing and CI/CD

The project includes a comprehensive test suite using pytest with automated CI/CD via GitHub Actions:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test categories
pytest -m unit          # Unit tests only
pytest -m integration   # Integration tests
pytest -m optimization  # Optimization algorithm tests

# Run specific test files
pytest tests/test_helpers.py
pytest tests/test_optimize_ro_integration.py

# Test MCP client compatibility
python test_non_recycle_config.py
```

### MCP Client Compatibility

When using with MCP clients, be aware of these requirements:

1. **Configuration Format**: The notebook templates support both field naming conventions:
   - `membrane_area_m2` (original format)
   - `area_m2` (MCP server format)
   - `vessel_count` or `n_vessels`

2. **IDAES Extensions**: Required for solver access (ipopt):
   ```bash
   # Install IDAES extensions (includes ipopt solver)
   idaes get-extensions
   ```
   The server automatically configures solver paths for notebook execution.

3. **MCAS Property Package**: For ion-specific modeling:
   - Requires PyNumero installation (see installation section)
   - Automatically selected when `feed_ion_composition` is provided
   - Provides detailed ion rejection and scaling predictions

4. **High Recovery with Recycle**: 
   - Recovery targets above ~85% may use recycle configurations
   - The recycle template is automatically selected when needed
   - Supports mixer/separator units for concentrate recycle

### Test Coverage
- Unit tests for all helper functions
- Validation and response formatting tests
- Integration tests for the MCP tools
- Optimization algorithm behavior tests
- Configuration management tests
- Simulation utility tests

### Continuous Integration
The project uses GitHub Actions for automated testing:
- Tests run automatically on every push and pull request
- Python 3.9, 3.10, 3.11, and 3.12 are tested
- Test results are reported in pull requests
- See `.github/workflows/test.yml` for configuration

## License

MIT License