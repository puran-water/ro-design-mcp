# RO Design MCP Server

An STDIO MCP (Model Context Protocol) server for reverse osmosis (RO) system design optimization using WaterTAP.

## Features

- **Optimal RO Configuration**: Generate optimal vessel array configurations for any recovery target
- **WaterTAP Simulation**: Run detailed simulations with ion-specific modeling
- **Multi-stage Support**: Handles 1-3 stage configurations with automatic recycle for high recovery
- **Economic Analysis**: Provides LCOW, energy consumption, and capital cost estimates

## Installation

### Prerequisites

- Python 3.12+
- Virtual environment (recommended)
- Windows, Linux, or macOS

### Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/ro-design-mcp.git
cd ro-design-mcp
```

2. Copy the environment template and update paths:
```bash
cp .env.example .env
# Edit .env with your local paths
```

3. Install dependencies:

**Windows (PowerShell):**
```powershell
.\install.ps1
```

**Windows (Command Prompt):**
```batch
install.bat
```

**Linux/macOS:**
```bash
pip install -r requirements.txt
idaes get-extensions
```

## Configuration

### Environment Variables

The server uses environment variables for configuration. Key variables:

- `LOCALAPPDATA`: Required by IDAES (auto-set if not provided)
- `PROJECT_ROOT`: Project root directory (auto-detected if not set)
- `VENV_PATH`: Virtual environment path (for installation scripts)

See `.env.example` for all available options.

### Configuration Files

Optional YAML configuration files can be placed in the `config/` directory to override defaults for:
- Membrane properties
- Economic parameters
- Operating conditions

## Usage

### Running the Server

```bash
python server.py
```

The server provides two main tools:

1. **optimize_ro_configuration**: Generate optimal vessel arrays
2. **simulate_ro_system**: Run WaterTAP simulations

### Example Usage

```python
# Tool 1: Get optimal configurations
result = await optimize_ro_configuration(
    feed_flow_m3h=100,
    water_recovery_fraction=0.75,
    membrane_type="brackish"
)

# Tool 2: Run detailed simulation
sim_result = await simulate_ro_system(
    configuration=result["configurations"][0],
    feed_salinity_ppm=5000,
    feed_ion_composition='{"Na+": 1200, "Cl-": 2100, "Ca2+": 120}',
    feed_temperature_c=25.0
)
```

## Deployment

### Modal Deployment

For serverless deployment using Modal:

1. Install Modal: `pip install modal`
2. Set up Modal authentication: `modal token new`
3. Deploy using `modal_config.py`:

```bash
modal deploy modal_config.py
```

See `modal_config.py` for endpoint examples and configuration.

### Docker Deployment

A Dockerfile is available for containerized deployment (coming soon).

## Development

### Running Tests

```bash
pytest tests/
```

### Code Structure

```
ro-design-mcp/
├── server.py              # Main MCP server
├── utils/                 # Core utilities
│   ├── ro_model_builder.py   # RO model construction
│   ├── ro_solver.py          # Initialization and solving
│   ├── ro_results_extractor.py # Results extraction
│   └── ...
├── notebooks/             # Jupyter notebook templates
├── config/               # Configuration files
└── tests/                # Test suite
```

## License

[Your License Here]

## Acknowledgments

Built with [WaterTAP](https://github.com/watertap-org/watertap) and [IDAES](https://github.com/IDAES/idaes-pse).