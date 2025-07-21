"""
Tests for configuration management system.
"""

import pytest
import os
import tempfile
from pathlib import Path
import yaml

from utils.config import ConfigLoader, get_config, set_config, load_config


class TestConfigLoader:
    """Tests for ConfigLoader class."""
    
    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary config directory with test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir)
            
            # Create test config files
            config1 = {
                'test': {
                    'value1': 42,
                    'nested': {
                        'value2': 'hello'
                    }
                },
                'list_value': [1, 2, 3]
            }
            
            config2 = {
                'test': {
                    'value3': 3.14,
                    'nested': {
                        'value4': 'world'
                    }
                },
                'another_value': True
            }
            
            with open(config_dir / 'config1.yaml', 'w') as f:
                yaml.dump(config1, f)
            
            with open(config_dir / 'config2.yaml', 'w') as f:
                yaml.dump(config2, f)
            
            yield config_dir
    
    @pytest.mark.unit
    def test_config_loading(self, temp_config_dir):
        """Test basic configuration loading."""
        loader = ConfigLoader(temp_config_dir)
        config = loader.load()
        
        # Check that configs were merged
        assert config['test']['value1'] == 42
        assert config['test']['value3'] == 3.14
        assert config['test']['nested']['value2'] == 'hello'
        assert config['test']['nested']['value4'] == 'world'
        assert config['list_value'] == [1, 2, 3]
        assert config['another_value'] is True
    
    @pytest.mark.unit
    def test_get_with_dot_notation(self, temp_config_dir):
        """Test getting values with dot notation."""
        loader = ConfigLoader(temp_config_dir)
        loader.load()
        
        assert loader.get('test.value1') == 42
        assert loader.get('test.nested.value2') == 'hello'
        assert loader.get('list_value') == [1, 2, 3]
        assert loader.get('nonexistent', 'default') == 'default'
    
    @pytest.mark.unit
    def test_set_with_dot_notation(self, temp_config_dir):
        """Test setting values with dot notation."""
        loader = ConfigLoader(temp_config_dir)
        loader.load()
        
        # Set existing value
        loader.set('test.value1', 100)
        assert loader.get('test.value1') == 100
        
        # Set new nested value
        loader.set('new.nested.value', 'test')
        assert loader.get('new.nested.value') == 'test'
    
    @pytest.mark.unit
    def test_environment_overrides(self, temp_config_dir, monkeypatch):
        """Test environment variable overrides."""
        # Set environment variables
        monkeypatch.setenv('RO_DESIGN_TEST_VALUE1', '99')
        monkeypatch.setenv('RO_DESIGN_TEST_NESTED_VALUE2', 'env_override')
        monkeypatch.setenv('RO_DESIGN_NEW_FLOAT', '2.718')
        monkeypatch.setenv('RO_DESIGN_NEW_BOOL', 'true')
        
        loader = ConfigLoader(temp_config_dir)
        config = loader.load()
        
        # Check overrides
        assert config['test']['value1'] == 99
        assert config['test']['nested']['value2'] == 'env_override'
        assert config['new']['float'] == 2.718
        assert config['new']['bool'] is True
    
    @pytest.mark.unit
    def test_deep_merge(self, temp_config_dir):
        """Test deep dictionary merging."""
        loader = ConfigLoader(temp_config_dir)
        
        dict1 = {
            'a': 1,
            'b': {'c': 2, 'd': 3},
            'e': [1, 2]
        }
        
        dict2 = {
            'a': 10,
            'b': {'d': 30, 'f': 4},
            'g': 5
        }
        
        result = loader._deep_merge(dict1, dict2)
        
        assert result['a'] == 10  # Overwritten
        assert result['b']['c'] == 2  # Preserved
        assert result['b']['d'] == 30  # Overwritten
        assert result['b']['f'] == 4  # Added
        assert result['e'] == [1, 2]  # Preserved
        assert result['g'] == 5  # Added


class TestConfigIntegration:
    """Integration tests for configuration with actual config files."""
    
    @pytest.mark.integration
    def test_default_config_loading(self):
        """Test loading the actual default configuration."""
        # This will load from the real config/ directory
        config = load_config()
        
        # Check some expected values
        assert 'element' in config
        assert config['element']['standard_area_m2'] == 37.16
        assert config['element']['elements_per_vessel'] == 7
        
        assert 'membrane_properties' in config
        assert 'brackish' in config['membrane_properties']
        assert 'seawater' in config['membrane_properties']
    
    @pytest.mark.integration
    def test_config_usage_in_constants(self):
        """Test that constants module properly uses config."""
        from utils import constants
        
        # These should load from config
        assert constants.STANDARD_ELEMENT_AREA_M2 == 37.16
        assert constants.ELEMENTS_PER_VESSEL == 7
        assert constants.DEFAULT_FLUX_TOLERANCE == 0.1
        assert constants.MAX_STAGES == 3
    
    @pytest.mark.integration
    def test_membrane_properties_structure(self):
        """Test membrane properties configuration structure."""
        config = load_config()
        
        # Check brackish water properties
        brackish = config['membrane_properties']['brackish']
        assert 'A_w' in brackish
        assert 'B_s' in brackish
        assert 'max_pressure' in brackish
        assert 'pressure_drop' in brackish
        assert 'stage1' in brackish['pressure_drop']
        
        # Check that values are reasonable
        assert 1e-12 < brackish['A_w'] < 1e-11
        assert 1e-8 < brackish['B_s'] < 1e-7
        assert brackish['max_pressure'] > 50e5  # > 50 bar