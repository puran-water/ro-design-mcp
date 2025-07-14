# RO Design MCP Server - AI Agent System Prompt

You are an AI assistant helping to develop and maintain the RO Design MCP Server, which provides tools for reverse osmosis system design optimization using WaterTAP.

## System Overview

This MCP server provides two main tools:
1. **optimize_ro_configuration**: Generates all viable RO vessel array configurations for a given flow and recovery target
2. **simulate_ro_system**: Runs detailed WaterTAP simulations with economic analysis and optional ion-specific modeling

## Key Technical Context

### WaterTAP Integration
- Uses parameterized Jupyter notebooks for simulations (papermill)
- Supports three property packages: NaCl, Seawater, and MCAS (ion-specific)
- Notebooks located in `/notebooks/` directory
- Templates automatically selected based on configuration (standard, MCAS, or recycle)

### MCAS Property Package
- Enabled when `feed_ion_composition` is provided
- Provides ion-specific rejection rates and scaling predictions
- Requires PyNumero and IDAES extensions to be installed
- More computationally intensive than simple NaCl package

### Initialization Strategies
- **Elegant initialization** (`utils/ro_initialization.py`): Calculates required pressures based on osmotic pressure
- **Sequential initialization**: Falls back when elegant fails (common with MCAS due to FBBT issues)
- Both strategies ensure robust convergence

### Solver Configuration
- IDAES binary directory must be in PATH for ipopt access
- Automatically configured in `simulate_ro.py` before notebook execution
- Windows path: `C:\Users\[username]\AppData\Local\idaes\bin`

### Recycle Support
- Automatically enabled when `recycle_ratio > 0` in configuration
- Uses mixer/separator units for concentrate recycle
- Template: `ro_simulation_recycle_template.ipynb`

## Configuration System

The server uses YAML-based configuration files in `/config/`:
- `system_defaults.yaml`: Core parameters (element areas, flux targets, etc.)
- `economics.yaml`: Economic parameters (costs, lifetime, rates)

Environment variable overrides:
```bash
export RO_DESIGN_ELEMENT_STANDARD_AREA_M2=40.0
export RO_DESIGN_ENERGY_ELECTRICITY_COST_USD_KWH=0.10
```

## Current Development Focus

### Recently Completed
- ✅ IPOPT solver path issues resolved
- ✅ MCAS property package integration
- ✅ Elegant initialization for better convergence
- ✅ Basic recycle support in templates
- ✅ Scaling prediction and antiscalant recommendations

### Next Steps
- [ ] HTML report generation from executed notebooks
- [ ] Enhanced pump performance metrics in results
- [ ] CAPEX breakdown by equipment type
- [ ] Advanced pump optimization (LCOW minimization)

## Important Conventions

1. **Error Handling**: Always return structured error responses with status and message
2. **Mass Balance**: Verify to < 0.1% error
3. **Recovery Targeting**: Strict - must meet or exceed target (no undershooting)
4. **Flux Flexibility**: Can go below normal limits if needed for recovery
5. **Template Selection**: Automatic based on ion composition and recycle configuration

## Testing in WSL Environment

When testing from WSL with Windows Python:
```bash
# Activate Windows virtual environment from WSL
powershell.exe -Command "& '../venv312/Scripts/activate.ps1'; python script.py"
```

## Debugging Tips

1. **Solver not found**: Check IDAES extensions are installed: `idaes get-extensions`
2. **MCAS convergence**: Falls back to sequential initialization automatically
3. **High recovery**: Automatically uses recycle template when needed
4. **Mass balance errors**: Usually indicates unit connection issues in flowsheet