"""
Mock unit models for WaterTAP costing without full thermodynamics.

This module provides lightweight unit models that inherit from UnitModelBlockData
to satisfy WaterTAP's costing framework requirements while avoiding the complexity
and convergence issues of full thermodynamic models.

Based on expert analysis: UnitModelCostingBlock requires parent to inherit from
UnitModelBlockData, and costing methods expect specific attributes like
work_mechanical[t] for pumps and area for RO units.
"""

from functools import partial
from pyomo.environ import Var, Block, units as pyunits, value
from idaes.core import UnitModelBlockData, declare_process_block_class
from watertap.costing.unit_models.pump import cost_pump, PumpType
from watertap.costing.unit_models.reverse_osmosis import cost_reverse_osmosis
import logging

logger = logging.getLogger(__name__)


@declare_process_block_class("MockPump")
class MockPumpData(UnitModelBlockData):
    """
    Mock pump unit model for costing without fluid dynamics.

    This lightweight model provides only the work_mechanical variable
    needed by WaterTAP's pump costing methods, without requiring
    convergence of mass/energy balances.
    """

    def build(self):
        """Build the mock pump model with required variables."""
        super().build()

        # WaterTAP costing expects work_mechanical indexed by time
        tset = self.flowsheet().time

        # Create work_mechanical variable (in Watts as expected by costing)
        self.work_mechanical = Var(
            tset,
            initialize=1000.0,
            units=pyunits.W,
            doc="Mechanical work from hybrid calculations"
        )

        # Create mock control_volume for low pressure pumps
        # WaterTAP's cost_low_pressure_pump expects control_volume.properties_in[t].flow_vol
        self.control_volume = Block()
        self.control_volume.properties_in = Block(tset)

        for t in tset:
            self.control_volume.properties_in[t].flow_vol = Var(
                initialize=0.028,  # ~100 m³/h in m³/s
                units=pyunits.m**3/pyunits.s,
                doc="Volumetric flow rate for costing"
            )

        # Store pump type for costing
        self._pump_type = "high_pressure"  # Default

    def set_power(self, power_kw, pump_type="high_pressure", flow_m3h=100):
        """
        Set pump power from hybrid simulator calculations.

        Args:
            power_kw: Pump power in kW from hybrid calculations
            pump_type: "high_pressure" or "low_pressure" for costing
            flow_m3h: Flow rate in m3/h for pump sizing
        """
        # Convert kW to W and fix for all time points
        power_w = power_kw * 1000.0
        # Convert m3/h to m3/s for control_volume
        flow_m3s = flow_m3h / 3600.0

        for t in self.flowsheet().time:
            self.work_mechanical[t].fix(power_w)
            self.control_volume.properties_in[t].flow_vol.fix(flow_m3s)

        self._pump_type = pump_type
        logger.debug(f"Mock pump set to {power_kw:.1f} kW ({pump_type}, {flow_m3h:.1f} m3/h)")

    @property
    def default_costing_method(self):
        """Return the appropriate costing method for this pump."""
        # Use standard WaterTAP cost_pump for both types
        # Set cost_electricity_flow=False since we only want CAPEX
        if self._pump_type == "high_pressure":
            return partial(cost_pump, pump_type=PumpType.high_pressure, cost_electricity_flow=False)
        else:
            return partial(cost_pump, pump_type=PumpType.low_pressure, cost_electricity_flow=False)


@declare_process_block_class("MockRO")
class MockROData(UnitModelBlockData):
    """
    Mock RO unit model for costing without mass transfer calculations.

    This lightweight model provides only the membrane area variable
    needed by WaterTAP's RO costing methods, without requiring
    solution of complex transport equations.
    """

    def build(self):
        """Build the mock RO model with required variables."""
        super().build()

        # Create area variable (in m² as expected by costing)
        self.area = Var(
            initialize=100.0,
            units=pyunits.m**2,
            doc="Membrane area from configuration"
        )

        # Store RO type for costing
        self._ro_type = "standard"  # Default

    def set_area(self, area_m2, ro_type="standard"):
        """
        Set membrane area from configuration.

        Args:
            area_m2: Membrane area in m² from configuration
            ro_type: RO type for costing ("standard" or "high_pressure")
        """
        self.area.fix(area_m2)
        self._ro_type = ro_type
        logger.debug(f"Mock RO set to {area_m2:.1f} m² ({ro_type})")

    @property
    def default_costing_method(self):
        """Return the appropriate costing method for this RO unit."""
        # Import here to avoid circular dependencies
        from watertap.costing.unit_models.reverse_osmosis import ROType

        if self._ro_type == "high_pressure":
            ro_type_enum = ROType.high_pressure
        else:
            ro_type_enum = ROType.standard

        # Return partial function with RO type preset
        return partial(cost_reverse_osmosis, ro_type=ro_type_enum)


def create_mock_pump_costed(
    flowsheet,
    name,
    power_kw,
    pressure_bar,
    costing_block,
    flow_m3h=100
):
    """
    Helper function to create and cost a mock pump in one step.

    Args:
        flowsheet: Pyomo flowsheet block to add pump to
        name: Name for the pump unit
        power_kw: Pump power in kW
        pressure_bar: Operating pressure to determine pump type
        costing_block: WaterTAPCostingDetailed block

    Returns:
        The created and costed mock pump
    """
    from idaes.core import UnitModelCostingBlock

    # Create mock pump
    pump = MockPump()
    setattr(flowsheet, name, pump)

    # Determine pump type based on pressure
    pump_type = "high_pressure" if pressure_bar >= 20 else "low_pressure"

    # Set power with flow for low pressure pump costing
    pump.set_power(power_kw, pump_type, flow_m3h)

    # Add costing
    pump.costing = UnitModelCostingBlock(
        flowsheet_costing_block=costing_block
    )

    logger.info(f"Created mock {pump_type} pump '{name}' with {power_kw:.1f} kW")

    return pump


def create_mock_ro_costed(
    flowsheet,
    name,
    area_m2,
    pressure_bar,
    costing_block
):
    """
    Helper function to create and cost a mock RO unit in one step.

    Args:
        flowsheet: Pyomo flowsheet block to add RO to
        name: Name for the RO unit
        area_m2: Membrane area in m²
        pressure_bar: Operating pressure to determine RO type
        costing_block: WaterTAPCostingDetailed block

    Returns:
        The created and costed mock RO unit
    """
    from idaes.core import UnitModelCostingBlock

    # Create mock RO
    ro = MockRO()
    setattr(flowsheet, name, ro)

    # Determine RO type based on pressure
    ro_type = "high_pressure" if pressure_bar >= 45 else "standard"

    # Set area
    ro.set_area(area_m2, ro_type)

    # Add costing
    ro.costing = UnitModelCostingBlock(
        flowsheet_costing_block=costing_block
    )

    logger.info(f"Created mock {ro_type} RO '{name}' with {area_m2:.1f} m²")

    return ro