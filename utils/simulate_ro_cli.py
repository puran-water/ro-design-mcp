"""
Child process entrypoint for running RO simulations (v1 and v2).

Reads JSON input from stdin, runs the simulation, and writes JSON to stdout.
All logging is routed to stderr to keep stdout strictly JSON-only.

Supports both v1 (basic) and v2 (enhanced with detailed economics) APIs.
"""

import sys
import json
from typing import Any, Dict

from .logging_config import configure_mcp_logging
from .simulate_ro import run_ro_simulation
from .simulate_ro_v2 import run_ro_simulation_v2


def main() -> int:
    # Ensure logs go to stderr in the child process
    configure_mcp_logging()

    try:
        raw = sys.stdin.read()
        payload: Dict[str, Any] = json.loads(raw) if raw else {}
    except Exception as e:
        err = {"status": "error", "message": f"Invalid JSON input: {e}"}
        print(json.dumps(err), end="")
        return 1

    try:
        # Determine API version
        api_version = payload.get("api_version", "v1")
        
        # Required arguments
        configuration = payload["configuration"]
        feed_salinity_ppm = payload["feed_salinity_ppm"]
        feed_ion_composition = payload["feed_ion_composition"]
        
        # Common optional arguments
        feed_temperature_c = payload.get("feed_temperature_c", 25.0)
        membrane_type = payload.get("membrane_type", "brackish")
        
        if api_version == "v2":
            # V2 API with enhanced economic modeling
            economic_params = payload.get("economic_params")
            chemical_dosing = payload.get("chemical_dosing")
            optimization_mode = payload.get("optimization_mode", False)
            initialization_strategy = payload.get("initialization_strategy", "sequential")
            use_nacl_equivalent = payload.get("use_nacl_equivalent", False)  # Default to MCAS direct modeling
            
            results = run_ro_simulation_v2(
                configuration=configuration,
                feed_salinity_ppm=feed_salinity_ppm,
                feed_ion_composition=feed_ion_composition,
                feed_temperature_c=feed_temperature_c,
                membrane_type=membrane_type,
                economic_params=economic_params,
                chemical_dosing=chemical_dosing,
                optimization_mode=optimization_mode,
                api_version=api_version,
                initialization_strategy=initialization_strategy,
                use_nacl_equivalent=use_nacl_equivalent
            )
        else:
            # V1 API (original basic simulation)
            membrane_properties = payload.get("membrane_properties")
            optimize_pumps = payload.get("optimize_pumps", True)
            initialization_strategy = payload.get("initialization_strategy", "sequential")
            use_nacl_equivalent = payload.get("use_nacl_equivalent", False)  # Default to MCAS direct modeling
            
            results = run_ro_simulation(
                configuration=configuration,
                feed_salinity_ppm=feed_salinity_ppm,
                feed_ion_composition=feed_ion_composition,
                feed_temperature_c=feed_temperature_c,
                membrane_type=membrane_type,
                membrane_properties=membrane_properties,
                optimize_pumps=optimize_pumps,
                initialization_strategy=initialization_strategy,
                use_nacl_equivalent=use_nacl_equivalent,
            )

        print(json.dumps(results), end="")
        return 0
    except Exception as e:
        err = {"status": "error", "message": f"Simulation failed: {e}"}
        print(json.dumps(err), end="")
        return 2


if __name__ == "__main__":
    sys.exit(main())

