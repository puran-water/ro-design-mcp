"""
Modal deployment configuration for RO Design MCP Server.

This file shows how to deploy the RO Design MCP Server on Modal.
"""

import modal
import os

# Create a Modal stub
stub = modal.Stub("ro-design-mcp")

# Define the Docker image with all dependencies
image = (
    modal.Image.debian_slim()
    .apt_install(["build-essential", "gfortran", "libopenblas-dev", "liblapack-dev"])
    .pip_install_from_requirements("requirements.txt")
    .run_commands(
        # Initialize IDAES and download solvers
        "idaes get-extensions",
        # Create necessary directories
        "mkdir -p /tmp/localappdata/idaes",
        "mkdir -p /tmp/pyomo/lib"
    )
)

# Environment variables for the Modal deployment
env_vars = {
    "LOCALAPPDATA": "/tmp/localappdata",
    "IDAES_DATA": "/tmp/localappdata/idaes",
    "PYOMO_LIB_PATH": "/tmp/pyomo/lib",
    "PROJECT_ROOT": "/app",
    "JUPYTER_PLATFORM_DIRS": "1",
    # Add configuration overrides if needed
    "RO_DESIGN_OPERATING_PLANT_AVAILABILITY": "0.9",
    "RO_DESIGN_ENERGY_ELECTRICITY_COST_USD_KWH": "0.07",
}

@stub.function(
    image=image,
    secrets=[modal.Secret.from_name("ro-design-secrets")],  # Optional: for API keys, etc.
    env=env_vars,
    cpu=2.0,  # Adjust based on needs
    memory=4096,  # 4GB RAM
    timeout=600,  # 10 minute timeout
)
def run_ro_optimization(
    feed_flow_m3h: float,
    water_recovery_fraction: float,
    membrane_type: str = "brackish",
    **kwargs
):
    """
    Run RO optimization on Modal.
    
    This function wraps the optimize_ro_configuration tool.
    """
    from server import optimize_ro_configuration
    import asyncio
    
    # Run the async function
    result = asyncio.run(optimize_ro_configuration(
        feed_flow_m3h=feed_flow_m3h,
        water_recovery_fraction=water_recovery_fraction,
        membrane_type=membrane_type,
        **kwargs
    ))
    
    return result

@stub.function(
    image=image,
    secrets=[modal.Secret.from_name("ro-design-secrets")],
    env=env_vars,
    cpu=4.0,  # More CPU for simulation
    memory=8192,  # 8GB RAM
    timeout=1800,  # 30 minute timeout
)
def run_ro_simulation(configuration: dict, **kwargs):
    """
    Run WaterTAP simulation on Modal.
    
    This function wraps the simulate_ro_system tool.
    """
    from server import simulate_ro_system
    import asyncio
    
    # Run the async function
    result = asyncio.run(simulate_ro_system(
        configuration=configuration,
        **kwargs
    ))
    
    return result

# Web endpoint for the optimization service
@stub.web_endpoint(method="POST")
def optimize_endpoint(request: dict):
    """
    HTTP endpoint for RO optimization.
    
    Example request:
    {
        "feed_flow_m3h": 100,
        "water_recovery_fraction": 0.75,
        "membrane_type": "brackish"
    }
    """
    return run_ro_optimization.remote(**request)

# Example of how to use the Modal functions
if __name__ == "__main__":
    # Deploy to Modal
    with stub.run():
        # Example optimization
        result = run_ro_optimization.remote(
            feed_flow_m3h=100,
            water_recovery_fraction=0.75,
            membrane_type="brackish"
        )
        print(f"Optimization result: {result}")
        
        # Example simulation (would need a valid configuration)
        # sim_result = run_ro_simulation.remote(
        #     configuration=result["configurations"][0],
        #     feed_salinity_ppm=5000,
        #     feed_ion_composition='{"Na+": 1200, "Cl-": 2100, "Ca2+": 120}',
        #     feed_temperature_c=25.0
        # )