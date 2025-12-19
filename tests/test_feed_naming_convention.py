"""
Test both feed naming conventions in RO model builders and solvers.

This module verifies that both 'fresh_feed' (new convention) and 'feed' 
(legacy convention) are properly handled throughout the codebase.
"""

import pytest
from pyomo.environ import ConcreteModel, value
from idaes.core import FlowsheetBlock
from watertap.property_models.multicomp_aq_sol_prop_pack import MCASParameterBlock, MaterialFlowBasis
from watertap.unit_models.pressure_changer import Pump
from watertap.unit_models.reverse_osmosis_0D import ReverseOsmosis0D
from idaes.models.unit_models import Feed, Product, Mixer, Separator
from pyomo.network import Arc
from pyomo.environ import TransformationFactory

from utils.ro_solver import initialize_and_solve_mcas
from utils.mcas_builder import build_mcas_property_configuration
from utils.constants import TYPICAL_COMPOSITIONS


class TestFeedNamingConvention:
    """Test both fresh_feed and feed naming conventions."""
    
    @pytest.fixture
    def mcas_config(self):
        """Create MCAS configuration for testing."""
        feed_composition = TYPICAL_COMPOSITIONS['brackish']
        return build_mcas_property_configuration(
            feed_composition=feed_composition,
            include_scaling_ions=True,
            include_ph_species=False
        )
    
    @pytest.fixture
    def base_config(self):
        """Base configuration for RO system."""
        return {
            'feed_flow_m3h': 100,
            'n_stages': 1,
            'stage_count': 1,
            'stages': [{
                'stage_recovery': 0.5,
                'membrane_area_m2': 260.16,
                'n_vessels': 1
            }]
        }
    
    def create_model_with_feed_name(self, feed_name, mcas_config, has_recycle=False):
        """Create a minimal RO model with specified feed naming."""
        m = ConcreteModel()
        m.fs = FlowsheetBlock(dynamic=False)
        
        # Create property package
        mcas_params = {
            'solute_list': mcas_config['solute_list'],
            'mw_data': mcas_config['mw_data'],
            'material_flow_basis': MaterialFlowBasis.mass,
        }
        m.fs.properties = MCASParameterBlock(**mcas_params)
        
        # Create feed with specified name
        if feed_name == 'fresh_feed':
            m.fs.fresh_feed = Feed(property_package=m.fs.properties)
        else:  # 'feed'
            m.fs.feed = Feed(property_package=m.fs.properties)
        
        # Create basic RO system
        m.fs.pump1 = Pump(property_package=m.fs.properties)
        m.fs.ro_stage1 = ReverseOsmosis0D(
            property_package=m.fs.properties,
            has_pressure_change=True
        )
        m.fs.stage_product1 = Product(property_package=m.fs.properties)
        
        if has_recycle:
            # Add recycle components
            m.fs.recycle_split = Separator(
                property_package=m.fs.properties,
                outlet_list=["disposal", "recycle"]
            )
            m.fs.feed_mixer = Mixer(
                property_package=m.fs.properties,
                inlet_list=["fresh", "recycle"]
            )
            m.fs.disposal_product = Product(property_package=m.fs.properties)
            
            # Connect with arcs based on feed name
            if feed_name == 'fresh_feed':
                m.fs.fresh_to_mixer = Arc(
                    source=m.fs.fresh_feed.outlet,
                    destination=m.fs.feed_mixer.fresh
                )
            else:
                m.fs.fresh_to_mixer = Arc(
                    source=m.fs.feed.outlet,
                    destination=m.fs.feed_mixer.fresh
                )
            
            m.fs.mixer_to_pump1 = Arc(
                source=m.fs.feed_mixer.outlet,
                destination=m.fs.pump1.inlet
            )
        else:
            # Direct connection based on feed name
            if feed_name == 'fresh_feed':
                m.fs.fresh_feed_to_pump1 = Arc(
                    source=m.fs.fresh_feed.outlet,
                    destination=m.fs.pump1.inlet
                )
            else:
                m.fs.feed_to_pump1 = Arc(
                    source=m.fs.feed.outlet,
                    destination=m.fs.pump1.inlet
                )
        
        # Common connections
        m.fs.pump1_to_ro_stage1 = Arc(
            source=m.fs.pump1.outlet,
            destination=m.fs.ro_stage1.inlet
        )
        m.fs.ro_stage1_perm_to_prod = Arc(
            source=m.fs.ro_stage1.permeate,
            destination=m.fs.stage_product1.inlet
        )
        
        if has_recycle:
            m.fs.final_conc_to_split = Arc(
                source=m.fs.ro_stage1.retentate,
                destination=m.fs.recycle_split.inlet
            )
            m.fs.split_to_disposal = Arc(
                source=m.fs.recycle_split.disposal,
                destination=m.fs.disposal_product.inlet
            )
            m.fs.split_to_recycle = Arc(
                source=m.fs.recycle_split.recycle,
                destination=m.fs.feed_mixer.recycle
            )
        else:
            m.fs.concentrate_product = Product(property_package=m.fs.properties)
            m.fs.final_conc_arc = Arc(
                source=m.fs.ro_stage1.retentate,
                destination=m.fs.concentrate_product.inlet
            )
        
        # Apply arcs
        TransformationFactory("network.expand_arcs").apply_to(m)
        
        # Set minimal properties for testing
        self._set_minimal_properties(m, feed_name, mcas_config, has_recycle)
        
        return m
    
    def _set_minimal_properties(self, m, feed_name, mcas_config, has_recycle):
        """Set minimal properties needed for initialization."""
        # Get feed block
        if feed_name == 'fresh_feed':
            feed_state = m.fs.fresh_feed.outlet
        else:
            feed_state = m.fs.feed.outlet
        
        # Set feed conditions
        feed_state.temperature.fix(298.15)
        feed_state.pressure.fix(101325)
        
        # Set minimal flows
        feed_flow_m3_s = 100 / 3600  # m³/s
        water_flow_kg_s = feed_flow_m3_s * 1000 * 0.97  # 97% water
        feed_state.flow_mass_phase_comp[0, 'Liq', 'H2O'].fix(water_flow_kg_s)
        
        # Set minimal ion flows
        for comp in mcas_config['solute_list']:
            feed_state.flow_mass_phase_comp[0, 'Liq', comp].fix(0.001)  # kg/s
        
        # Set RO properties
        m.fs.ro_stage1.A_comp.fix(4.2e-12)
        for comp in mcas_config['solute_list']:
            m.fs.ro_stage1.B_comp[0, comp].fix(3.5e-8)
        m.fs.ro_stage1.area.fix(260.16)
        m.fs.ro_stage1.width.fix(5.0)
        m.fs.ro_stage1.feed_side.channel_height.fix(0.001)
        m.fs.ro_stage1.feed_side.spacer_porosity.fix(0.85)
        m.fs.ro_stage1.permeate.pressure[0].fix(101325)
        m.fs.ro_stage1.deltaP.fix(-0.5e5)
        
        # Set pump efficiency
        m.fs.pump1.efficiency_pump.fix(0.8)
        
        # Set recycle split if present
        if has_recycle:
            m.fs.recycle_split.split_fraction[0, "recycle"].fix(0.5)
            m.fs.recycle_split.split_fraction[0, "disposal"].fix(0.5)
    
    def test_fresh_feed_convention_no_recycle(self, mcas_config, base_config):
        """Test model with fresh_feed naming (new convention) without recycle."""
        m = self.create_model_with_feed_name('fresh_feed', mcas_config, has_recycle=False)
        
        # Verify model can be initialized
        result = initialize_and_solve_mcas(m, base_config, optimize_pumps=False)
        
        assert result['status'] == 'success'
        assert hasattr(m.fs, 'fresh_feed')
        assert hasattr(m.fs, 'fresh_feed_to_pump1')
    
    def test_feed_convention_no_recycle(self, mcas_config, base_config):
        """Test model with feed naming (legacy convention) without recycle."""
        m = self.create_model_with_feed_name('feed', mcas_config, has_recycle=False)
        
        # Verify model can be initialized
        result = initialize_and_solve_mcas(m, base_config, optimize_pumps=False)
        
        assert result['status'] == 'success'
        assert hasattr(m.fs, 'feed')
        assert hasattr(m.fs, 'feed_to_pump1')
    
    def test_fresh_feed_convention_with_recycle(self, mcas_config, base_config):
        """Test model with fresh_feed naming (new convention) with recycle."""
        config_with_recycle = base_config.copy()
        config_with_recycle['recycle_info'] = {
            'uses_recycle': True,
            'recycle_ratio': 0.2,
            'recycle_split_ratio': 0.5
        }
        
        m = self.create_model_with_feed_name('fresh_feed', mcas_config, has_recycle=True)
        
        # Verify model can be initialized
        result = initialize_and_solve_mcas(m, config_with_recycle, optimize_pumps=False)
        
        assert result['status'] == 'success'
        assert hasattr(m.fs, 'fresh_feed')
        assert hasattr(m.fs, 'fresh_to_mixer')
    
    def test_feed_convention_with_recycle(self, mcas_config, base_config):
        """Test model with feed naming (legacy convention) with recycle."""
        config_with_recycle = base_config.copy()
        config_with_recycle['recycle_info'] = {
            'uses_recycle': True,
            'recycle_ratio': 0.2,
            'recycle_split_ratio': 0.5
        }
        
        m = self.create_model_with_feed_name('feed', mcas_config, has_recycle=True)
        
        # Verify model can be initialized
        result = initialize_and_solve_mcas(m, config_with_recycle, optimize_pumps=False)
        
        assert result['status'] == 'success'
        assert hasattr(m.fs, 'feed')
        assert hasattr(m.fs, 'fresh_to_mixer')
    
    def test_arc_naming_flexibility(self, mcas_config, base_config):
        """Test that solver handles both arc naming conventions."""
        m = ConcreteModel()
        m.fs = FlowsheetBlock(dynamic=False)
        
        # Create property package
        mcas_params = {
            'solute_list': mcas_config['solute_list'],
            'mw_data': mcas_config['mw_data'],
            'material_flow_basis': MaterialFlowBasis.mass,
        }
        m.fs.properties = MCASParameterBlock(**mcas_params)
        
        # Create components
        m.fs.fresh_feed = Feed(property_package=m.fs.properties)
        m.fs.pump1 = Pump(property_package=m.fs.properties)
        m.fs.pump2 = Pump(property_package=m.fs.properties)
        m.fs.ro_stage1 = ReverseOsmosis0D(property_package=m.fs.properties)
        m.fs.ro_stage2 = ReverseOsmosis0D(property_package=m.fs.properties)
        m.fs.stage_product1 = Product(property_package=m.fs.properties)
        m.fs.stage_product2 = Product(property_package=m.fs.properties)
        m.fs.concentrate_product = Product(property_package=m.fs.properties)
        
        # Mix arc naming conventions
        m.fs.fresh_feed_to_pump1 = Arc(source=m.fs.fresh_feed.outlet, destination=m.fs.pump1.inlet)
        m.fs.pump1_to_ro_stage1 = Arc(source=m.fs.pump1.outlet, destination=m.fs.ro_stage1.inlet)  # New style
        m.fs.ro_stage1_perm_to_prod = Arc(source=m.fs.ro_stage1.permeate, destination=m.fs.stage_product1.inlet)
        m.fs.ro_stage1_to_pump2 = Arc(source=m.fs.ro_stage1.retentate, destination=m.fs.pump2.inlet)
        m.fs.pump2_to_ro2 = Arc(source=m.fs.pump2.outlet, destination=m.fs.ro_stage2.inlet)  # Old style
        m.fs.ro2_perm_to_prod2 = Arc(source=m.fs.ro_stage2.permeate, destination=m.fs.stage_product2.inlet)  # Old style
        m.fs.final_conc_arc = Arc(source=m.fs.ro_stage2.retentate, destination=m.fs.concentrate_product.inlet)
        
        TransformationFactory("network.expand_arcs").apply_to(m)
        
        # Set properties
        self._set_minimal_properties(m, 'fresh_feed', mcas_config, has_recycle=False)
        m.fs.ro_stage2.A_comp.fix(4.2e-12)
        for comp in mcas_config['solute_list']:
            m.fs.ro_stage2.B_comp[0, comp].fix(3.5e-8)
        m.fs.ro_stage2.area.fix(260.16)
        m.fs.ro_stage2.width.fix(5.0)
        m.fs.ro_stage2.feed_side.channel_height.fix(0.001)
        m.fs.ro_stage2.feed_side.spacer_porosity.fix(0.85)
        m.fs.ro_stage2.permeate.pressure[0].fix(101325)
        m.fs.ro_stage2.deltaP.fix(-0.5e5)
        m.fs.pump2.efficiency_pump.fix(0.8)
        
        # Test with 2 stages
        config_2stage = base_config.copy()
        config_2stage['n_stages'] = 2
        config_2stage['stage_count'] = 2
        config_2stage['stages'] = [
            {'stage_recovery': 0.5, 'membrane_area_m2': 260.16, 'n_vessels': 1},
            {'stage_recovery': 0.5, 'membrane_area_m2': 260.16, 'n_vessels': 1}
        ]
        
        # Should handle mixed arc naming
        result = initialize_and_solve_mcas(m, config_2stage, optimize_pumps=False)
        assert result['status'] == 'success'


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])