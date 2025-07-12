  ⎿ RO Design MCP Server Implementation Plan (Final Revision)

    Overview

    Create an STDIO MCP server that provides two main tools for RO system design:
    1. optimize_ro_configuration: Generates optimal RO vessel array configurations based on flow and recovery only
    2. simulate_ro_system: Runs WaterTAP simulations with economic analysis using the configuration, water quality,
     and membrane type

    Both tools will return JSON for LLM interpretation and generate human-readable Jupyter notebooks via papermill.

    Project Structure

    ro-design-mcp/
    ├── server.py                    # Main MCP server using FastMCP
    ├── pyproject.toml              # Package configuration
    ├── requirements.txt            # Dependencies
    ├── README.md                   # Documentation
    ├── tools/
    │   ├── __init__.py
    │   ├── optimize_ro_configuration.py    # Tool 1: RO configuration
    │   └── simulate_ro_system.py          # Tool 2: WaterTAP simulation
    ├── utils/
    │   ├── __init__.py
    │   ├── constants.py            # RO-specific constants
    │   ├── helpers.py              # Shared utility functions
    │   ├── notebook_runner.py      # Papermill execution wrapper
    │   ├── unit_converter.py       # Optional unit conversion
    │   └── validators.py           # Input validation functions
    ├── notebooks/
    │   ├── ro_configuration_report.ipynb   # Template for config results
    │   └── ro_simulation_report.ipynb      # Template for simulation results
    ├── tests/
    │   ├── __init__.py
    │   ├── test_optimization.py    # Unit tests for optimization
    │   ├── test_simulation.py      # Unit tests for simulation
    │   └── test_integration.py     # End-to-end tests
    └── examples/
        ├── basic_ro_design.py      # Example usage
        └── high_recovery_design.py # Advanced example

    Implementation Details

    Phase 1: Core Server and Configuration Tool

    1. Extract optimization logic from notebook:
      - optimize_vessel_array_configuration function with mass balance fixes
      - Support for non-recycle (< 85%) and recycle (≥ 85%) cases
      - Multi-configuration analysis (1, 2, 3-stage options)
    2. Create Tool 1 interface (FINAL CORRECTION):
    def optimize_ro_configuration(
        feed_flow_m3h: float,
        target_recovery: float,
        # Optional parameters for fine-tuning
        return_all_configurations: bool = False,
        stage_flux_targets_lmh: List[float] = None,  # Default: [18, 15, 12]
        min_concentrate_flow_per_vessel_m3h: List[float] = None,  # Default: [3.5, 3.8, 4.0]
        element_area_m2: float = 37.16,  # 400 ft²
        elements_per_vessel: int = 7,
        max_stages: int = 3,
        allow_recycle: bool = True,
        max_recycle_ratio: float = 0.9,
        tolerance: float = 0.02,  # 2% recovery tolerance
        generate_report: bool = True
    ) -> str:
        """
        Generate optimal RO vessel array configuration(s) based solely on
        hydraulic constraints (flow and recovery).

        Returns JSON with:
        - Vessel array configuration (stages × vessels notation)
        - Stage-by-stage breakdown
        - Mass balance verification
        - Recycle details (if applicable)
        - Report file path (if generated)
        """
    3. Implement notebook report generation:
      - Use papermill to execute parameterized notebook
      - Include vessel array diagrams
      - Mass balance tables for recycle cases
      - Comparison table for multi-configuration results
      - Convert to HTML/PDF with nbconvert/quarto

    Phase 2: WaterTAP Simulation Tool

    1. Extract simulation logic:
      - Model building functions
      - Transport model selection based on membrane type
      - Economic analysis (CAPEX, OPEX, LCOW)
    2. Create Tool 2 interface (WITH MEMBRANE TYPE):
    def simulate_ro_system(
        ro_configuration: dict,  # From Tool 1 or user-provided
        feed_water_quality: dict,  # TDS/ion concentrations
        membrane_type: str = "brackish",  # NOW HERE - affects transport model
        temperature: float = 298.15,  # K
        feed_pressure: float = 101325,  # Pa
        has_energy_recovery: bool = False,
        erd_efficiency: float = 0.8,
        economic_parameters: dict = None,  # Optional custom costs
        generate_report: bool = True
    ) -> str:
        """
        Simulate RO system with WaterTAP and perform economic analysis.

        membrane_type determines transport model:
        - "brackish": SKK model with brackish water parameters
        - "seawater": Modified parameters for SWRO
        - "nanofiltration": Different transport model

        feed_water_quality should include:
        - tds_mg_L or individual ion concentrations
        - pH (optional)
        - temperature (can override parameter)

        Returns JSON with:
        - Stage operating pressures
        - Pump power requirements
        - Permeate water quality
        - Recovery verification
        - Economic analysis (CAPEX, OPEX, LCOW)
        - Report file path (if generated)
        """
    3. Implement comprehensive reporting:
      - System diagram with pressures and flows
      - Stage-by-stage performance metrics
      - Water quality improvement
      - Economic breakdown (pie charts)
      - Sensitivity analysis graphs

    Phase 3: Integration and Enhancement

    1. Add unit conversion support:
    # Support various units in inputs
    feed_flow="1000 GPM"  # Converts to m³/h
    temperature="77 degF"  # Converts to K
    pressure="200 psi"    # Converts to Pa
    2. Implement intelligent defaults:
      - Common membrane properties database
      - Typical flux and concentrate constraints
      - Standard economic parameters
    3. Add validation and error handling:
      - Physical constraint checking
      - Convergence monitoring
      - Helpful error messages

    Technical Considerations

    Dependencies

    [project]
    dependencies = [
        "mcp>=0.5.0",
        "watertap>=0.12.0",
        "pyomo>=6.5",
        "idaes-pse>=2.0",
        "papermill>=2.4.0",
        "nbconvert>=7.0",
        "pandas>=2.0",
        "numpy>=1.24",
        "matplotlib>=3.7",
        "plotly>=5.0",
        "pint>=0.20"
    ]

    Key Design Decisions

    1. Separation of Concerns: Tool 1 handles hydraulic design only, Tool 2 handles process simulation
    2. Flexibility: Users can provide their own configurations to Tool 2
    3. Reporting: Both tools generate detailed reports for documentation
    4. Extensibility: Easy to add new membrane types or economic models

    Usage Examples

    Example 1: Complete Design Workflow

    # Step 1: Get optimal configuration based on flow/recovery
    config_result = optimize_ro_configuration(
        feed_flow_m3h=100,
        target_recovery=0.75
    )
    config = json.loads(config_result)

    # Step 2: Simulate with specific membrane and water quality
    sim_result = simulate_ro_system(
        ro_configuration=config["configuration"],
        feed_water_quality={
            "tds_mg_L": 5000,
            "temperature_K": 298.15,
            "na_mg_L": 1500,
            "cl_mg_L": 2500,
            "ca_mg_L": 400,
            "so4_mg_L": 600
        },
        membrane_type="brackish"  # Specifies SKK parameters
    )

    Example 2: High Recovery Multi-Configuration Analysis

    # Get all viable configurations
    configs_result = optimize_ro_configuration(
        feed_flow_m3h=100,
        target_recovery=0.90,
        return_all_configurations=True
    )

    # Simulate each with specific membrane type
    all_configs = json.loads(configs_result)
    for config in all_configs["viable_configurations"]:
        sim_result = simulate_ro_system(
            ro_configuration=config,
            feed_water_quality={"tds_mg_L": 5000},
            membrane_type="brackish"  # Could also test "seawater" membranes
        )
        # Compare LCOW across configurations

    Example 3: Direct Simulation with Known Configuration

    # Skip Tool 1 if configuration is known
    custom_config = {
        "n_stages": 2,
        "stages": [
            {"stage_number": 1, "n_vessels": 20, ...},
            {"stage_number": 2, "n_vessels": 10, ...}
        ]
    }

    result = simulate_ro_system(
        ro_configuration=custom_config,
        feed_water_quality={"tds_mg_L": 35000},
        membrane_type="seawater"  # SWRO membrane parameters
    )

    Testing Strategy

    1. Unit Tests:
      - Optimization algorithm correctness
      - Mass balance verification
      - Unit conversion accuracy
    2. Integration Tests:
      - MCP server communication
      - Tool chaining (Tool 1 → Tool 2)
      - Report generation
    3. Validation Tests:
      - Compare with notebook results
      - Known RO plant designs
      - Literature benchmarks

    Future Extensions

    1. Additional Tools:
      - design_pretreatment: Size pretreatment based on feed water
      - optimize_energy_recovery: ERD selection and sizing
      - analyze_fouling: Fouling prediction and cleaning schedules
    2. Advanced Features:
      - Multi-objective optimization
      - Uncertainty analysis
      - Dynamic simulation
      - Integration with SCADA systems
    3. Membrane Database:
      - Extensive membrane property database
      - Manufacturer-specific models
      - Fouling characteristics

    Next Steps

    1. Set up project structure in ro-design-mcp/ directory
    2. Extract optimization functions from notebook into modular form
    3. Create basic MCP server with Tool 1
    4. Develop notebook report templates
    5. Test Tool 1 with all recovery scenarios from our testing
    6. Extract WaterTAP simulation logic for Tool 2
    7. Implement membrane-specific transport models
    8. Add comprehensive documentation and examples