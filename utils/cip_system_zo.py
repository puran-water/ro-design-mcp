"""
CIP (Clean-In-Place) System Zero-Order Model for RO Systems.

This module provides a WaterTAP-compatible zero-order model for CIP systems
that sizes equipment based on the largest stage (industry standard practice).
"""

import pyomo.environ as pyo
from pyomo.environ import units as pyunits
from idaes.core import declare_process_block_class
from idaes.core.util.exceptions import ConfigurationError
from watertap.core import build_pt, ZeroOrderBaseData
import logging

logger = logging.getLogger(__name__)


@declare_process_block_class("CIPSystemZO")
class CIPSystemZOData(ZeroOrderBaseData):
    """
    Zero-order model for CIP system sizing and costing.

    Sizes based on the LARGEST stage since CIP is performed stage-by-stage.
    Uses industry-standard sizing correlations from FilmTec manual.
    """

    CONFIG = ZeroOrderBaseData.CONFIG()

    def build(self):
        """Build the CIP system model with proper sizing."""
        super().build()

        self._tech_type = "cip_system"

        # Build pass-through (no transformation of main flow)
        build_pt(self)

        # CIP system sizing parameters
        self.n_vessels_largest_stage = pyo.Param(
            initialize=4,
            mutable=True,
            doc="Number of vessels in the largest stage"
        )

        self.vessel_diameter_inch = pyo.Param(
            initialize=8.0,
            mutable=True,
            doc="Vessel diameter in inches"
        )

        self.elements_per_vessel = pyo.Param(
            initialize=7,
            mutable=True,
            doc="Number of elements per vessel"
        )

        self.cip_frequency_per_year = pyo.Param(
            initialize=4,
            mutable=True,
            doc="Number of CIP cleanings per year"
        )

        # CIP system sizing variables
        self.cip_tank_volume = pyo.Var(
            initialize=1.0,
            bounds=(0, None),
            units=pyunits.m**3,
            doc="CIP tank volume in m³"
        )

        self.cip_pump_flow = pyo.Var(
            initialize=0.01,
            bounds=(0, None),
            units=pyunits.m**3/pyunits.s,
            doc="CIP pump flow rate in m³/s"
        )

        self.cip_pump_pressure = pyo.Var(
            initialize=3e5,
            bounds=(1.5e5, 4e5),
            units=pyunits.Pa,
            doc="CIP pump discharge pressure in Pa"
        )

        self.cip_pump_work = pyo.Var(
            initialize=1000,
            bounds=(0, None),
            units=pyunits.W,
            doc="CIP pump mechanical work in W"
        )

        # Performance variables for reporting
        self._perf_var_dict["CIP Tank Volume"] = self.cip_tank_volume
        self._perf_var_dict["CIP Pump Flow"] = self.cip_pump_flow
        self._perf_var_dict["CIP Pump Pressure"] = self.cip_pump_pressure

        # Constraints for sizing
        @self.Constraint(doc="CIP tank volume sizing")
        def cip_tank_volume_constraint(b):
            # Industry-standard: ~52 gallons per 8" vessel with 6 elements
            # Scale for different vessel sizes and element counts
            vessel_volume_gal = 52 * (b.elements_per_vessel / 6) * ((b.vessel_diameter_inch / 8) ** 2)
            total_volume_gal = vessel_volume_gal * b.n_vessels_largest_stage * 1.2  # +20% for piping
            # Convert to m³ (1 gal = 0.00378541 m³)
            return b.cip_tank_volume == total_volume_gal * 0.00378541

        @self.Constraint(doc="CIP pump flow sizing")
        def cip_pump_flow_constraint(b):
            # 8" vessels: 30-45 gpm per vessel (use 37.5 gpm average)
            # Scale for vessel diameter
            gpm_per_vessel = 37.5 * ((b.vessel_diameter_inch / 8) ** 2)
            total_flow_gpm = gpm_per_vessel * b.n_vessels_largest_stage
            # Convert to m³/s (1 gpm = 6.30902e-5 m³/s)
            return b.cip_pump_flow == total_flow_gpm * 6.30902e-5

        @self.Constraint(doc="CIP pump work calculation")
        def cip_pump_work_constraint(b):
            pump_efficiency = 0.75  # Typical centrifugal pump
            return b.cip_pump_work == (
                b.cip_pump_flow * b.cip_pump_pressure / pump_efficiency
            )

        # Fix the CIP pump pressure at typical value
        self.cip_pump_pressure.fix(3e5)  # 3 bar

        # Log sizing info
        n_vessels = pyo.value(self.n_vessels_largest_stage)
        vessel_dia = pyo.value(self.vessel_diameter_inch)
        n_elements = pyo.value(self.elements_per_vessel)

        vessel_volume_gal = 52 * (n_elements / 6) * ((vessel_dia / 8) ** 2)
        total_volume_gal = vessel_volume_gal * n_vessels * 1.2
        total_flow_gpm = 37.5 * ((vessel_dia / 8) ** 2) * n_vessels

        logger.info(f"CIP System sized for {n_vessels} vessels in largest stage:")
        logger.info(f"  Tank volume: {total_volume_gal:.0f} gal ({total_volume_gal * 0.00378541:.1f} m³)")
        logger.info(f"  Pump flow: {total_flow_gpm:.0f} gpm ({total_flow_gpm * 6.30902e-5:.4f} m³/s)")
        logger.info(f"  Pump pressure: 3 bar")

    @property
    def default_costing_method(self):
        """Return the default costing method for CIP systems."""
        return self.cost_cip_system

    @staticmethod
    def cost_cip_system(blk, number_of_parallel_units=1):
        """
        Cost the CIP system using WaterTAP's framework.

        Uses power law costing for tank and pump based on industry data.
        """
        from watertap.costing.util import make_capital_cost_var

        # Create capital cost variable
        make_capital_cost_var(blk)

        # Tank costing using power law: Cost = A * Volume^B
        # For PP/FRP tanks: ~$5000/m³ at 1 m³, scaling exponent 0.7
        A_tank = 5000  # $/m³ at 1 m³
        B_tank = 0.7   # Scaling exponent

        tank_volume = pyo.value(blk.unit_model.cip_tank_volume)
        tank_cost = A_tank * tank_volume ** B_tank

        # Pump costing - low pressure pump
        # WaterTAP uses 889 $/L/s for low-pressure pumps
        # Convert our flow from m³/s to L/s
        flow_Lps = pyo.value(blk.unit_model.cip_pump_flow) * 1000
        pump_cost = 889 * flow_Lps

        # Additional equipment (cartridge filter, heater, piping, valves)
        # Industry standard: 30-40% of tank+pump cost
        auxiliary_factor = 1.35

        # Total capital cost
        total_capital = (tank_cost + pump_cost) * auxiliary_factor * number_of_parallel_units

        blk.capital_cost_constraint = pyo.Constraint(
            expr=blk.capital_cost == total_capital
        )

        # Operating costs - CIP chemicals
        # Based on frequency and tank volume
        cleanings_per_year = pyo.value(blk.unit_model.cip_frequency_per_year)
        tank_volume_L = pyo.value(blk.unit_model.cip_tank_volume) * 1000

        # Typical CIP: 1% acid, 1% base solutions
        # Alternating acid/base cleanings
        acid_cleanings = cleanings_per_year / 2
        base_cleanings = cleanings_per_year / 2

        # Chemical consumption (kg/year)
        acid_concentration = 0.01  # 1% solution
        base_concentration = 0.01  # 1% solution

        acid_kg_year = acid_cleanings * tank_volume_L * acid_concentration
        base_kg_year = base_cleanings * tank_volume_L * base_concentration

        # Convert to kg/s for flow registration
        acid_kg_s = acid_kg_year / (365 * 24 * 3600)
        base_kg_s = base_kg_year / (365 * 24 * 3600)

        # Store chemical consumption for reporting (don't register flows yet)
        # The flows will be handled by the model builder if chemicals are configured
        blk.cip_acid_consumption_kg_year = pyo.Param(
            initialize=acid_kg_year,
            mutable=True,
            doc="Annual acid consumption (kg/year)"
        )

        blk.cip_base_consumption_kg_year = pyo.Param(
            initialize=base_kg_year,
            mutable=True,
            doc="Annual base consumption (kg/year)"
        )

        # Register pump electricity only
        if hasattr(blk.config, 'flowsheet_costing_block'):
            try:
                blk.config.flowsheet_costing_block.cost_flow(
                    blk.unit_model.cip_pump_work,
                    "electricity"
                )
            except:
                # Electricity might not be registered yet
                pass

        logger.info(f"CIP System Costing:")
        logger.info(f"  Tank cost: ${tank_cost:,.0f}")
        logger.info(f"  Pump cost: ${pump_cost:,.0f}")
        logger.info(f"  Total capital: ${total_capital:,.0f}")
        logger.info(f"  Acid usage: {acid_kg_year:.0f} kg/year")
        logger.info(f"  Base usage: {base_kg_year:.0f} kg/year")