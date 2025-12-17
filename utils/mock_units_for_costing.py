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
from pyomo.common.config import ConfigValue
from idaes.core import UnitModelBlockData, declare_process_block_class
from idaes.core.util.misc import StrEnum
from watertap.costing.unit_models.pump import cost_pump, PumpType
from watertap.costing.unit_models.reverse_osmosis import cost_reverse_osmosis
from watertap.core.zero_order_base import ZeroOrderBaseData
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


@declare_process_block_class("MockChemicalAddition")
class MockChemicalAdditionData(UnitModelBlockData):
    """
    Mock chemical addition unit for costing without full zero-order model.

    Provides minimal attributes needed by WaterTAP's cost_chemical_addition method.
    """

    CONFIG = UnitModelBlockData.CONFIG()
    CONFIG.declare("process_subtype", ConfigValue(default="default"))

    def build(self):
        """Build the mock chemical addition model."""
        super().build()

        tset = self.flowsheet().time
        self._tech_type = "chemical_addition"

        self.properties = Block(tset)
        for t in tset:
            self.properties[t].flow_vol = Var(
                initialize=0.028,
                units=pyunits.m**3/pyunits.s,
                doc="Feed flow rate"
            )

        self.chemical_dosage = Var(
            tset,
            initialize=5.0,
            units=pyunits.mg/pyunits.L,
            doc="Chemical dose"
        )

        self.solution_density = Var(
            initialize=1000.0,
            units=pyunits.kg/pyunits.m**3,
            doc="Solution density"
        )

        self.ratio_in_solution = Var(
            initialize=1.0,
            doc="Ratio of chemical in solution"
        )

        self.chemical_flow_vol = Var(
            tset,
            initialize=0.0001,
            units=pyunits.m**3/pyunits.s,
            doc="Chemical volumetric flow"
        )

    def set_inputs(self, flow_m3h, dose_mg_L, solution_ratio=1.0):
        """
        Set inputs from hybrid simulator results.

        Args:
            flow_m3h: Feed flow rate in m3/h
            dose_mg_L: Chemical dose in mg/L
            solution_ratio: Fraction of chemical in solution (default 1.0 for 100%)
        """
        flow_m3s = flow_m3h / 3600.0

        for t in self.flowsheet().time:
            self.properties[t].flow_vol.fix(flow_m3s)
            self.chemical_dosage[t].fix(dose_mg_L)

        self.ratio_in_solution.fix(solution_ratio)
        self.solution_density.fix(1000.0)

        chem_flow_m3s = (flow_m3s * dose_mg_L / 1000.0) / (solution_ratio * 1000.0)
        for t in self.flowsheet().time:
            self.chemical_flow_vol[t].fix(chem_flow_m3s)

        logger.debug(f"Mock chemical addition set to {dose_mg_L:.1f} mg/L at {flow_m3h:.1f} m3/h")

    @property
    def default_costing_method(self):
        """Return WaterTAP's native cost_chemical_addition method."""
        from watertap.unit_models.zero_order.chemical_addition_zo import ChemicalAdditionZOData
        return ChemicalAdditionZOData.cost_chemical_addition


@declare_process_block_class("MockStorageTank")
class MockStorageTankData(UnitModelBlockData):
    """
    Mock storage tank unit for costing without full zero-order model.

    Provides minimal attributes needed by WaterTAP's cost_storage_tank method.
    """

    def build(self):
        """Build the mock storage tank model."""
        super().build()

        self._tech_type = "storage_tank"

        self.tank_volume = Var(
            initialize=10.0,
            units=pyunits.m**3,
            doc="Tank volume"
        )

    def set_volume(self, volume_m3):
        """
        Set tank volume from sizing calculations.

        Args:
            volume_m3: Tank volume in m3
        """
        self.tank_volume.fix(volume_m3)
        logger.debug(f"Mock storage tank set to {volume_m3:.2f} m3")

    @property
    def default_costing_method(self):
        """Return WaterTAP's native cost_storage_tank method."""
        from watertap.unit_models.zero_order.storage_tank_zo import StorageTankZOData
        return StorageTankZOData.cost_storage_tank


@declare_process_block_class("MockCartridgeFilter")
class MockCartridgeFilterData(UnitModelBlockData):
    """
    Mock cartridge filter unit for costing without full zero-order model.

    Provides minimal attributes needed by WaterTAP's power-law flow costing.
    Uses WaterTAP's default costing (reads from cartridge_filtration.yaml).
    """

    def build(self):
        """Build the mock cartridge filter model."""
        super().build()

        tset = self.flowsheet().time
        self._tech_type = "cartridge_filtration"

        self.properties = Block(tset)
        for t in tset:
            self.properties[t].flow_vol = Var(
                initialize=0.028,
                units=pyunits.m**3/pyunits.s,
                doc="Flow rate"
            )

    def set_flow(self, flow_m3h):
        """
        Set flow rate from system design.

        Args:
            flow_m3h: Flow rate in m3/h
        """
        flow_m3s = flow_m3h / 3600.0
        for t in self.flowsheet().time:
            self.properties[t].flow_vol.fix(flow_m3s)
        logger.debug(f"Mock cartridge filter set to {flow_m3h:.1f} m3/h")


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
    pump = MockPump()  # noqa: F821 - created by @declare_process_block_class
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
    ro = MockRO()  # noqa: F821 - created by @declare_process_block_class
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


def create_mock_chemical_addition_costed(
    flowsheet,
    name,
    flow_m3h,
    dose_mg_L,
    costing_block,
    chemical_type="default",
    solution_ratio=1.0
):
    """
    Helper function to create and cost a mock chemical addition unit.

    Args:
        flowsheet: Pyomo flowsheet block
        name: Name for the chemical addition unit
        flow_m3h: Feed flow rate in m3/h
        dose_mg_L: Chemical dose in mg/L
        costing_block: WaterTAPCostingDetailed block
        chemical_type: Type of chemical (for process_subtype)
        solution_ratio: Fraction of chemical in solution

    Returns:
        The created and costed mock chemical addition unit
    """
    from idaes.core import UnitModelCostingBlock

    chem = MockChemicalAddition()  # noqa: F821 - created by @declare_process_block_class
    chem.config.process_subtype = chemical_type
    setattr(flowsheet, name, chem)

    chem.set_inputs(flow_m3h, dose_mg_L, solution_ratio)

    chem.costing = UnitModelCostingBlock(
        flowsheet_costing_block=costing_block
    )

    logger.info(f"Created mock chemical addition '{name}' with {dose_mg_L:.1f} mg/L dose")

    return chem


def create_mock_storage_tank_costed(
    flowsheet,
    name,
    volume_m3,
    costing_block
):
    """
    Helper function to create and cost a mock storage tank.

    Args:
        flowsheet: Pyomo flowsheet block
        name: Name for the storage tank
        volume_m3: Tank volume in m3
        costing_block: WaterTAPCostingDetailed block

    Returns:
        The created and costed mock storage tank
    """
    from idaes.core import UnitModelCostingBlock

    tank = MockStorageTank()  # noqa: F821 - created by @declare_process_block_class
    setattr(flowsheet, name, tank)

    tank.set_volume(volume_m3)

    tank.costing = UnitModelCostingBlock(
        flowsheet_costing_block=costing_block
    )

    logger.info(f"Created mock storage tank '{name}' with {volume_m3:.2f} m3")

    return tank


def create_mock_cartridge_filter_costed(
    flowsheet,
    name,
    flow_m3h,
    costing_block
):
    """
    Helper function to create and cost a mock cartridge filter.

    Args:
        flowsheet: Pyomo flowsheet block
        name: Name for the cartridge filter
        flow_m3h: Flow rate in m3/h
        costing_block: WaterTAPCostingDetailed block

    Returns:
        The created and costed mock cartridge filter
    """
    from idaes.core import UnitModelCostingBlock

    filter_unit = MockCartridgeFilter()  # noqa: F821 - created by @declare_process_block_class
    setattr(flowsheet, name, filter_unit)

    filter_unit.set_flow(flow_m3h)

    filter_unit.costing = UnitModelCostingBlock(
        flowsheet_costing_block=costing_block
    )

    logger.info(f"Created mock cartridge filter '{name}' with {flow_m3h:.1f} m3/h")

    return filter_unit