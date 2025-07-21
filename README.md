# RO Design MCP Server

A comprehensive Model Context Protocol (MCP) server for reverse osmosis (RO) system design optimization, featuring advanced vessel array configuration and detailed WaterTAP simulations with multi-component aqueous solution (MCAS) modeling.

## Features

- **Intelligent Configuration Generation**: Automatically generates all viable 1-3 stage vessel arrays for any recovery target
- **Advanced Ion Modeling**: Uses WaterTAP's MCAS property package for accurate ion-specific predictions
- **High Recovery Design**: Automatic concentrate recycle configuration for recovery targets up to 95%
- **Economic Optimization**: Integrated WaterTAP economics for CAPEX/OPEX estimation
- **Membrane Database**: Pre-configured properties for common brackish and seawater membranes
- **Scaling Prevention**: Built-in saturation index calculations (LSI, S&DSI, sulfate saturation)
- **Pressure Optimization**: Automatic pump pressure optimization to meet recovery targets
- **Detailed Reporting**: Generates comprehensive Jupyter notebooks with all design calculations

## Installation

### Prerequisites

- Python 3.10+ (3.12 recommended)
- Virtual environment (strongly recommended)
- Windows, Linux, or macOS
- Git for cloning the repository

### Quick Setup

1. **Clone the repository:**
```bash
git clone https://github.com/puran-water/ro-design-mcp.git
cd ro-design-mcp
```

2. **Create and activate a virtual environment:**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate
```

3. **Copy and configure environment variables:**
```bash
cp .env.example .env
# Edit .env with your local paths if needed
```

4. **Install all dependencies:**

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install IDAES extensions (required for optimization solvers)
idaes get-extensions --verbose
```

### Dependency Details

The server requires several specialized packages:

- **fastmcp**: MCP server framework
- **WaterTAP** (>=0.11.0): Water treatment process modeling
- **IDAES PSE** (>=2.2.0): Process systems engineering framework
- **Pyomo** (>=6.7.0): Optimization modeling
- **papermill**: Notebook execution engine
- **numpy, pandas**: Data processing
- **matplotlib, seaborn**: Visualization (for notebooks)

### Post-Installation Verification

Verify the installation:
```bash
# Check IDAES installation
idaes --version

# Test the server
python server.py
```

You should see:
```
RO Design Server running on stdio...
```

## Configuration

### Environment Variables

The server uses environment variables for configuration. Key variables:

- `LOCALAPPDATA`: Required by IDAES (auto-set if not provided)
- `PROJECT_ROOT`: Project root directory (auto-detected if not set)

See `.env.example` for all available options.

### Configuration Files

Optional YAML configuration files can be placed in the `config/` directory to override defaults for:
- Membrane properties
- Economic parameters
- Operating conditions

## Usage with Claude Desktop

### Configuration

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "ro-design": {
      "command": "python",
      "args": ["C:/path/to/ro-design-mcp/server.py"],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

### Example Conversations

**Basic RO Design:**
```
User: Design an RO system for 100 m³/h brackish water with 75% recovery

Claude: I'll design an optimal RO system for your specifications...
[Uses optimize_ro_configuration and simulate_ro_system tools]
```

**High Recovery Design:**
```
User: I need 90% recovery from 50 m³/h feed with 5000 ppm TDS

Claude: For 90% recovery, I'll design a 3-stage system with concentrate recycle...
[Automatically configures recycle for high recovery]
```

## Available Tools

### 1. optimize_ro_configuration

Generates all viable vessel array configurations for your target recovery.

**Parameters:**
- `feed_flow_m3h` (required): Feed flow rate in m³/h
- `water_recovery_fraction` (required): Target recovery (0-1)
- `membrane_type`: "brackish" or "seawater" (default: "brackish")
- `allow_recycle`: Enable concentrate recycle (default: true)
- `flux_targets_lmh`: Custom flux targets as JSON array
- `flux_tolerance`: Flux tolerance fraction

**Example:**
```python
config = await optimize_ro_configuration(
    feed_flow_m3h=100,
    water_recovery_fraction=0.75,
    membrane_type="brackish"
)
```

### 2. simulate_ro_system

Runs detailed WaterTAP simulation with MCAS ion modeling.

**Parameters:**
- `configuration` (required): Output from optimize_ro_configuration
- `feed_salinity_ppm` (required): Total dissolved solids
- `feed_ion_composition` (required): JSON string of ion concentrations (mg/L)
- `feed_temperature_c`: Temperature in Celsius (default: 25)
- `optimize_pumps`: Auto-optimize pressures (default: true)

**Example:**
```python
results = await simulate_ro_system(
    configuration=config["configurations"][0],
    feed_salinity_ppm=5000,
    feed_ion_composition='{"Na+": 1917, "Cl-": 3083}',
    feed_temperature_c=25.0
)
```

## Deployment

### Production Deployment

For production deployments, consider:
- Using a process manager (e.g., systemd, supervisor)
- Setting appropriate resource limits
- Configuring logging and monitoring
- Using environment-specific configuration files


## Technical Details

### Membrane Properties

The server includes pre-configured properties for two membrane types:

**Membrane Types:**
- **Brackish Water**: Optimized for feed TDS < 10,000 ppm
  - Water permeability: 9.63e-12 m/s/Pa
  - Salt permeability: 5.58e-08 m/s
  
- **Seawater**: Optimized for feed TDS > 10,000 ppm
  - Water permeability: 2.05e-12 m/s/Pa
  - Salt permeability: 1.61e-08 m/s

Custom membrane properties can be specified via the `membrane_properties` parameter.

### Ion Modeling (MCAS)

The server uses WaterTAP's Multi-Component Aqueous Solution (MCAS) property package for accurate predictions:

- Handles major ions: Na⁺, Ca²⁺, Mg²⁺, K⁺, Cl⁻, SO₄²⁻, HCO₃⁻
- Activity coefficient calculations
- Ion-specific rejection modeling
- Osmotic pressure accuracy

### Recovery Limitations by Configuration

| Stages | Max Recovery | Typical Application |
|--------|--------------|-------------------|
| 1      | 50%         | Low salinity, simple systems |
| 2      | 75%         | Standard brackish water |
| 3      | 85%         | High recovery without recycle |
| 3 + Recycle | 95%    | ZLD, minimal liquid discharge |

## Development

### Running Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=utils --cov-report=html

# Run specific test categories
pytest tests/test_mcp_simulation.py  # MCP integration tests
pytest tests/test_optimize_ro_integration.py  # Optimization tests
```

### Code Structure

```
ro-design-mcp/
├── server.py              # Main MCP server implementation
├── AI_AGENT_PROMPT.md     # AI agent usage instructions
├── utils/                 # Core functionality
│   ├── optimize_ro.py        # Vessel array optimization
│   ├── simulate_ro.py        # WaterTAP simulation wrapper
│   ├── ro_model_builder.py   # RO flowsheet construction
│   ├── ro_solver.py          # IPOPT solver interface
│   ├── ro_results_extractor.py # Results processing
│   ├── mcas_builder.py       # MCAS property configuration
│   └── validation.py         # Input validation
├── notebooks/             # Parameterized Jupyter templates
│   └── ro_simulation_mcas_template.ipynb
├── config/               # Default configurations
│   ├── system_defaults.yaml
│   ├── economics.yaml
│   └── chemical_properties.yaml
└── tests/                # Comprehensive test suite
```

### Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes with clear messages
4. Push to your fork and submit a Pull Request

### Code Style

- Python 3.10+ with type hints
- Clear docstrings for all functions
- Follow existing code patterns
- Add tests for new features

## Troubleshooting

### Common Issues

**"IPOPT not found"**
```bash
idaes get-extensions --verbose
```

**"Import error: watertap not found"**
```bash
pip install watertap --upgrade
```

**"Notebook execution timeout"**
- Increase timeout in .env: `NOTEBOOK_TIMEOUT=3600`
- Complex configurations may need more time

**"Invalid ion composition"**
- Ensure JSON format with double quotes
- Check ion charge balance
- Verify concentrations sum approximately to TDS


## License

MIT License - see [LICENSE](LICENSE) file for details

## Acknowledgments

- Built with [WaterTAP](https://github.com/watertap-org/watertap) - The Water Technoeconomic Assessment Platform
- Powered by [IDAES](https://github.com/IDAES/idaes-pse) - Institute for Design of Advanced Energy Systems
- MCP framework by [FastMCP](https://github.com/pyramidpy/fastmcp)
- Optimization by [Pyomo](http://www.pyomo.org/) and [IPOPT](https://coin-or.github.io/Ipopt/)