"""Integration tests for the core plugin system functionality.

This module validates that all plugin system components work together correctly:
- Plugin discovery and loading
- Service registration and resolution
- Plugin lifecycle management
- Error handling and recovery
- Performance characteristics
"""

import pytest
import time
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import Mock, patch

from orlando_toolkit.core.plugins.loader import PluginLoader
from orlando_toolkit.core.plugins.registry import ServiceRegistry
from orlando_toolkit.core.plugins.manager import PluginManager
from orlando_toolkit.core.plugins.base import BasePlugin, PluginState
from orlando_toolkit.core.plugins.metadata import PluginMetadata
from orlando_toolkit.core.plugins.exceptions import PluginError
from orlando_toolkit.core.context import AppContext
from orlando_toolkit.core.services import ConversionService


@pytest.mark.integration
class TestPluginDiscovery:
    """Test plugin discovery functionality."""
    
    def test_discover_no_plugins(self, plugin_loader):
        """Test discovery when no plugins are present."""
        plugin_infos = plugin_loader.discover_plugins()
        assert len(plugin_infos) == 0
    
    def test_discover_valid_plugin(self, temp_dir):
        """Test discovery of valid plugin."""
        # Create test plugin
        plugin_dir = temp_dir / "plugins" / "test-plugin"
        plugin_dir.mkdir(parents=True)
        
        # Create plugin manifest
        manifest = {
            "name": "test-plugin",
            "version": "1.0.0",
            "display_name": "Test Plugin",
            "description": "Test plugin for integration testing",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.TestPlugin",
            "supported_formats": [{
                "extension": ".test",
                "mime_type": "application/x-test",
                "description": "Test Format"
            }],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {"services": ["DocumentHandler"]}
        }
        
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))
        
        # Create plugin module
        plugin_code = '''
from orlando_toolkit.core.plugins.base import BasePlugin

class TestPlugin(BasePlugin):
    def get_name(self):
        return "Test Plugin"
    
    def get_description(self):
        return "Test plugin for integration testing"
'''
        (plugin_dir / "plugin.py").write_text(plugin_code)
        
        # Test discovery with patched plugins directory
        loader = PluginLoader(ServiceRegistry())
        loader._plugins_dir = temp_dir / "plugins"
        plugin_infos = loader.discover_plugins()
        
        assert len(plugin_infos) == 1
        info = plugin_infos[0]
        assert info.metadata.name == "test-plugin"
        assert info.metadata.version == "1.0.0"
        assert info.metadata.display_name == "Test Plugin"
        assert len(info.metadata.supported_formats) == 1
        assert info.metadata.supported_formats[0]["extension"] == ".test"
    
    def test_discover_invalid_manifest(self, temp_dir):
        """Test discovery with invalid manifest."""
        plugin_dir = temp_dir / "plugins" / "invalid-plugin"
        plugin_dir.mkdir(parents=True)
        
        # Create invalid manifest (missing required fields)
        manifest = {"name": "invalid-plugin"}
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
        
        loader = PluginLoader(ServiceRegistry())
        loader._plugins_dir = temp_dir / "plugins"
        plugin_infos = loader.discover_plugins()
        
        # Should skip invalid plugin
        assert len(plugin_infos) == 0
    
    def test_discover_multiple_plugins(self, temp_dir):
        """Test discovery of multiple valid plugins."""
        plugins_dir = temp_dir / "plugins"
        
        for i in range(3):
            plugin_dir = plugins_dir / f"test-plugin-{i}"
            plugin_dir.mkdir(parents=True)
            
            manifest = {
                "name": f"test-plugin-{i}",
                "version": "1.0.0",
                "display_name": f"Test Plugin {i}",
                "description": f"Test plugin {i}",
                "author": "Test Author",
                "orlando_version": ">=2.0.0",
                "plugin_api_version": "1.0",
                "category": "pipeline",
                "entry_point": f"plugin.TestPlugin{i}",
                "supported_formats": [],
                "dependencies": {"python": ">=3.8", "packages": []},
                "provides": {"services": []}
            }
            
            (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))
            
            plugin_code = f'''
from orlando_toolkit.core.plugins.base import BasePlugin

class TestPlugin{i}(BasePlugin):
    def get_name(self):
        return "Test Plugin {i}"
    
    def get_description(self):
        return "Test plugin {i}"
'''
            (plugin_dir / "plugin.py").write_text(plugin_code)
        
        loader = PluginLoader(ServiceRegistry())
        loader._plugins_dir = plugins_dir
        plugin_infos = loader.discover_plugins()
        
        assert len(plugin_infos) == 3
        names = [info.metadata.name for info in plugin_infos]
        assert "test-plugin-0" in names
        assert "test-plugin-1" in names
        assert "test-plugin-2" in names


@pytest.mark.integration
class TestPluginLoading:
    """Test plugin loading and instantiation."""
    
    def test_load_simple_plugin(self, temp_dir, app_context):
        """Test loading a simple plugin without services."""
        plugin_dir = temp_dir / "plugins" / "simple-plugin"
        plugin_dir.mkdir(parents=True)
        
        manifest = {
            "name": "simple-plugin",
            "version": "1.0.0",
            "display_name": "Simple Plugin",
            "description": "Simple test plugin",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.SimplePlugin",
            "supported_formats": [],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {"services": []}
        }
        
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))
        
        plugin_code = '''
from orlando_toolkit.core.plugins.base import BasePlugin

class SimplePlugin(BasePlugin):
    def get_name(self):
        return "Simple Plugin"
    
    def get_description(self):
        return "Simple test plugin"
'''
        (plugin_dir / "plugin.py").write_text(plugin_code)
        
        loader = PluginLoader([str(temp_dir / "plugins")])
        plugin_manager = loader.load_plugins(app_context)
        
        # Check plugin loaded successfully
        active_plugins = plugin_manager.get_active_plugins()
        assert len(active_plugins) == 1
        
        plugin = active_plugins[0]
        assert plugin.metadata.name == "simple-plugin"
        assert plugin.state == PluginState.ACTIVE
        assert plugin.get_name() == "Simple Plugin"
    
    def test_load_plugin_with_document_handler(self, temp_dir, app_context):
        """Test loading plugin that registers a document handler."""
        plugin_dir = temp_dir / "plugins" / "handler-plugin"
        plugin_dir.mkdir(parents=True)
        
        manifest = {
            "name": "handler-plugin",
            "version": "1.0.0",
            "display_name": "Handler Plugin",
            "description": "Plugin with document handler",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.HandlerPlugin",
            "supported_formats": [{
                "extension": ".handler",
                "mime_type": "application/x-handler",
                "description": "Handler Format"
            }],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {"services": ["DocumentHandler"]}
        }
        
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))
        
        plugin_code = '''
from orlando_toolkit.core.plugins.base import BasePlugin
from orlando_toolkit.core.plugins.interfaces import DocumentHandler
from orlando_toolkit.core.models import DitaContext
from pathlib import Path
from unittest.mock import Mock

class TestDocumentHandler(DocumentHandler):
    def can_handle(self, file_path):
        return file_path.suffix == '.handler'
    
    def get_supported_extensions(self):
        return ['.handler']
    
    def convert_document(self, file_path, destination_dir):
        context = Mock(spec=DitaContext)
        context.project_dir = destination_dir
        return context
    
    def get_name(self):
        return "Test Handler"
    
    def get_description(self):
        return "Test document handler"

class HandlerPlugin(BasePlugin):
    def get_name(self):
        return "Handler Plugin"
    
    def get_description(self):
        return "Plugin with document handler"
    
    def on_activate(self):
        super().on_activate()
        handler = TestDocumentHandler()
        self.app_context.service_registry.register_service(
            'DocumentHandler', handler, self.plugin_id
        )
'''
        (plugin_dir / "plugin.py").write_text(plugin_code)
        
        loader = PluginLoader([str(temp_dir / "plugins")])
        plugin_manager = loader.load_plugins(app_context)
        
        # Check plugin loaded and handler registered
        active_plugins = plugin_manager.get_active_plugins()
        assert len(active_plugins) == 1
        
        # Check handler is registered
        handler = app_context.service_registry.find_handler_for_extension('.handler')
        assert handler is not None
        assert handler.get_name() == "Test Handler"
        assert handler.can_handle(Path("test.handler"))
    
    def test_load_plugin_with_error(self, temp_dir, app_context):
        """Test loading plugin that throws an error."""
        plugin_dir = temp_dir / "plugins" / "error-plugin"
        plugin_dir.mkdir(parents=True)
        
        manifest = {
            "name": "error-plugin",
            "version": "1.0.0",
            "display_name": "Error Plugin",
            "description": "Plugin that throws error",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.ErrorPlugin",
            "supported_formats": [],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {"services": []}
        }
        
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))
        
        plugin_code = '''
from orlando_toolkit.core.plugins.base import BasePlugin

class ErrorPlugin(BasePlugin):
    def get_name(self):
        return "Error Plugin"
    
    def get_description(self):
        return "Plugin that throws error"
    
    def on_activate(self):
        super().on_activate()
        raise RuntimeError("Test error in plugin activation")
'''
        (plugin_dir / "plugin.py").write_text(plugin_code)
        
        loader = PluginLoader([str(temp_dir / "plugins")])
        plugin_manager = loader.load_plugins(app_context)
        
        # Plugin should be in ERROR state
        all_plugins = plugin_manager.get_all_plugins()
        assert len(all_plugins) == 1
        
        plugin = all_plugins[0]
        assert plugin.state == PluginState.ERROR
        assert plugin.metadata.name == "error-plugin"


@pytest.mark.integration
class TestServiceRegistry:
    """Test service registry functionality."""
    
    def test_register_and_find_document_handler(self, mock_service_registry, mock_document_handler):
        """Test registering and finding document handlers."""
        # Register handler
        mock_service_registry.register_document_handler(mock_document_handler, 'test-plugin')
        
        # Find by file
        test_file = Path('test.test')
        handler = mock_service_registry.find_handler_for_file(test_file)
        assert handler is mock_document_handler
        
        # Get all handlers
        handlers = mock_service_registry.get_document_handlers()
        assert len(handlers) == 1
        assert handlers[0] is mock_document_handler
    
    def test_unregister_service(self, mock_service_registry, mock_document_handler):
        """Test unregistering services."""
        # Register handler
        mock_service_registry.register_document_handler(mock_document_handler, 'test-plugin')
        test_file = Path('test.test')
        assert mock_service_registry.find_handler_for_file(test_file) is mock_document_handler
        
        # Unregister
        mock_service_registry.unregister_document_handler('test-plugin')
        assert mock_service_registry.find_handler_for_file(test_file) is None
    
    def test_multiple_handlers_for_extension(self, mock_service_registry):
        """Test multiple handlers for same extension."""
        handler1 = Mock()
        handler1.can_handle = Mock(return_value=True)
        handler1.get_supported_extensions = Mock(return_value=['.test'])
        
        handler2 = Mock()
        handler2.can_handle = Mock(return_value=True)
        handler2.get_supported_extensions = Mock(return_value=['.test'])
        
        mock_service_registry.register_document_handler(handler1, 'plugin1')
        mock_service_registry.register_document_handler(handler2, 'plugin2')
        
        # Should return a handler
        test_file = Path('test.test')
        found_handler = mock_service_registry.find_handler_for_file(test_file)
        assert found_handler in [handler1, handler2]  # Either one is acceptable
        
        # Should have both handlers
        all_handlers = mock_service_registry.get_document_handlers()
        assert len(all_handlers) == 2


@pytest.mark.integration
class TestPluginManager:
    """Test plugin manager functionality."""
    
    def test_get_plugin_by_id(self, temp_dir, app_context):
        """Test retrieving plugin by ID."""
        plugin_dir = temp_dir / "plugins" / "test-plugin"
        plugin_dir.mkdir(parents=True)
        
        manifest = {
            "name": "test-plugin",
            "version": "1.0.0",
            "display_name": "Test Plugin",
            "description": "Test plugin",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.TestPlugin",
            "supported_formats": [],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {"services": []}
        }
        
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))
        
        plugin_code = '''
from orlando_toolkit.core.plugins.base import BasePlugin

class TestPlugin(BasePlugin):
    def get_name(self):
        return "Test Plugin"
    
    def get_description(self):
        return "Test plugin"
'''
        (plugin_dir / "plugin.py").write_text(plugin_code)
        
        loader = PluginLoader([str(temp_dir / "plugins")])
        plugin_manager = loader.load_plugins(app_context)
        
        # Test get by ID
        plugin = plugin_manager.get_plugin_by_id("test-plugin")
        assert plugin is not None
        assert plugin.metadata.name == "test-plugin"
        
        # Test non-existent plugin
        non_existent = plugin_manager.get_plugin_by_id("non-existent")
        assert non_existent is None
    
    def test_plugin_activation_deactivation(self, temp_dir, app_context):
        """Test manual plugin activation and deactivation."""
        plugin_dir = temp_dir / "plugins" / "toggle-plugin"
        plugin_dir.mkdir(parents=True)
        
        manifest = {
            "name": "toggle-plugin",
            "version": "1.0.0",
            "display_name": "Toggle Plugin",
            "description": "Plugin for testing activation/deactivation",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.TogglePlugin",
            "supported_formats": [],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {"services": []}
        }
        
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))
        
        plugin_code = '''
from orlando_toolkit.core.plugins.base import BasePlugin

class TogglePlugin(BasePlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.activate_count = 0
        self.deactivate_count = 0
    
    def get_name(self):
        return "Toggle Plugin"
    
    def get_description(self):
        return "Plugin for testing activation/deactivation"
    
    def on_activate(self):
        super().on_activate()
        self.activate_count += 1
    
    def on_deactivate(self):
        super().on_deactivate()
        self.deactivate_count += 1
'''
        (plugin_dir / "plugin.py").write_text(plugin_code)
        
        loader = PluginLoader([str(temp_dir / "plugins")])
        plugin_manager = loader.load_plugins(app_context)
        
        plugin = plugin_manager.get_plugin_by_id("toggle-plugin")
        assert plugin.state == PluginState.ACTIVE
        assert plugin.activate_count == 1
        assert plugin.deactivate_count == 0
        
        # Deactivate
        success = plugin_manager.deactivate_plugin("toggle-plugin")
        assert success
        assert plugin.state == PluginState.LOADED
        assert plugin.deactivate_count == 1
        
        # Reactivate
        success = plugin_manager.activate_plugin("toggle-plugin")
        assert success
        assert plugin.state == PluginState.ACTIVE
        assert plugin.activate_count == 2


@pytest.mark.integration
@pytest.mark.performance
class TestPluginPerformance:
    """Test plugin system performance characteristics."""
    
    def test_plugin_loading_performance(self, temp_dir, app_context, performance_timer):
        """Test that plugin loading doesn't significantly impact performance."""
        # Create multiple test plugins
        plugins_dir = temp_dir / "plugins"
        plugin_count = 5
        
        for i in range(plugin_count):
            plugin_dir = plugins_dir / f"perf-plugin-{i}"
            plugin_dir.mkdir(parents=True)
            
            manifest = {
                "name": f"perf-plugin-{i}",
                "version": "1.0.0",
                "display_name": f"Performance Plugin {i}",
                "description": f"Performance test plugin {i}",
                "author": "Test Author",
                "orlando_version": ">=2.0.0",
                "plugin_api_version": "1.0",
                "category": "pipeline",
                "entry_point": f"plugin.PerfPlugin{i}",
                "supported_formats": [],
                "dependencies": {"python": ">=3.8", "packages": []},
                "provides": {"services": []}
            }
            
            (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))
            
            plugin_code = f'''
from orlando_toolkit.core.plugins.base import BasePlugin

class PerfPlugin{i}(BasePlugin):
    def get_name(self):
        return "Performance Plugin {i}"
    
    def get_description(self):
        return "Performance test plugin {i}"
'''
            (plugin_dir / "plugin.py").write_text(plugin_code)
        
        # Measure loading time
        performance_timer.start()
        loader = PluginLoader([str(plugins_dir)])
        plugin_manager = loader.load_plugins(app_context)
        loading_time = performance_timer.stop()
        
        # Verify all plugins loaded
        active_plugins = plugin_manager.get_active_plugins()
        assert len(active_plugins) == plugin_count
        
        # Performance assertion: should load in reasonable time
        # (This is a reasonable threshold - adjust if needed)
        assert loading_time < 5.0, f"Plugin loading took too long: {loading_time:.3f}s"
        
        # Log performance metrics
        print(f"Loaded {plugin_count} plugins in {loading_time:.3f}s")
        print(f"Average per plugin: {loading_time/plugin_count:.3f}s")
    
    def test_service_lookup_performance(self, mock_service_registry, performance_timer):
        """Test service lookup performance with many registered services."""
        # Register many handlers
        handler_count = 100
        for i in range(handler_count):
            handler = Mock()
            handler.can_handle = Mock(return_value=False)
            handler.get_supported_extensions = Mock(return_value=[f'.ext{i}'])
            mock_service_registry.register_document_handler(handler, f'plugin{i}')
        
        # Register one handler that matches
        matching_handler = Mock()
        matching_handler.can_handle = Mock(return_value=True)
        matching_handler.get_supported_extensions = Mock(return_value=['.target'])
        mock_service_registry.register_document_handler(matching_handler, 'target-plugin')
        
        # Measure lookup time
        performance_timer.start()
        for _ in range(10):  # Multiple lookups
            test_file = Path('test.target')
            handler = mock_service_registry.find_handler_for_file(test_file)
            assert handler is matching_handler
        lookup_time = performance_timer.stop()
        
        # Performance assertion
        assert lookup_time < 1.0, f"Service lookup took too long: {lookup_time:.3f}s"
        
        print(f"10 lookups with {handler_count + 1} handlers took {lookup_time:.3f}s")


@pytest.mark.integration
class TestErrorHandling:
    """Test plugin system error handling and recovery."""
    
    def test_plugin_with_import_error(self, temp_dir, app_context):
        """Test handling of plugin with import errors."""
        plugin_dir = temp_dir / "plugins" / "import-error-plugin"
        plugin_dir.mkdir(parents=True)
        
        manifest = {
            "name": "import-error-plugin",
            "version": "1.0.0",
            "display_name": "Import Error Plugin",
            "description": "Plugin with import error",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.ImportErrorPlugin",
            "supported_formats": [],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {"services": []}
        }
        
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))
        
        plugin_code = '''
import non_existent_module  # This will cause ImportError

from orlando_toolkit.core.plugins.base import BasePlugin

class ImportErrorPlugin(BasePlugin):
    def get_name(self):
        return "Import Error Plugin"
    
    def get_description(self):
        return "Plugin with import error"
'''
        (plugin_dir / "plugin.py").write_text(plugin_code)
        
        loader = PluginLoader([str(temp_dir / "plugins")])
        plugin_manager = loader.load_plugins(app_context)
        
        # Plugin should be in ERROR state
        all_plugins = plugin_manager.get_all_plugins()
        assert len(all_plugins) == 1
        
        plugin = all_plugins[0]
        assert plugin.state == PluginState.ERROR
    
    def test_plugin_system_isolation(self, temp_dir, app_context):
        """Test that plugin errors don't affect other plugins."""
        plugins_dir = temp_dir / "plugins"
        
        # Create good plugin
        good_plugin_dir = plugins_dir / "good-plugin"
        good_plugin_dir.mkdir(parents=True)
        
        good_manifest = {
            "name": "good-plugin",
            "version": "1.0.0",
            "display_name": "Good Plugin",
            "description": "Working plugin",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.GoodPlugin",
            "supported_formats": [],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {"services": []}
        }
        
        (good_plugin_dir / "plugin.json").write_text(json.dumps(good_manifest, indent=2))
        
        good_plugin_code = '''
from orlando_toolkit.core.plugins.base import BasePlugin

class GoodPlugin(BasePlugin):
    def get_name(self):
        return "Good Plugin"
    
    def get_description(self):
        return "Working plugin"
'''
        (good_plugin_dir / "plugin.py").write_text(good_plugin_code)
        
        # Create bad plugin
        bad_plugin_dir = plugins_dir / "bad-plugin"
        bad_plugin_dir.mkdir(parents=True)
        
        bad_manifest = {
            "name": "bad-plugin",
            "version": "1.0.0",
            "display_name": "Bad Plugin",
            "description": "Broken plugin",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.BadPlugin",
            "supported_formats": [],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {"services": []}
        }
        
        (bad_plugin_dir / "plugin.json").write_text(json.dumps(bad_manifest, indent=2))
        
        bad_plugin_code = '''
from orlando_toolkit.core.plugins.base import BasePlugin

class BadPlugin(BasePlugin):
    def get_name(self):
        return "Bad Plugin"
    
    def get_description(self):
        return "Broken plugin"
    
    def on_activate(self):
        super().on_activate()
        raise RuntimeError("This plugin always fails")
'''
        (bad_plugin_dir / "plugin.py").write_text(bad_plugin_code)
        
        loader = PluginLoader([str(plugins_dir)])
        plugin_manager = loader.load_plugins(app_context)
        
        all_plugins = plugin_manager.get_all_plugins()
        assert len(all_plugins) == 2
        
        # Good plugin should be active
        good_plugin = plugin_manager.get_plugin_by_id("good-plugin")
        assert good_plugin.state == PluginState.ACTIVE
        
        # Bad plugin should be in error state
        bad_plugin = plugin_manager.get_plugin_by_id("bad-plugin")
        assert bad_plugin.state == PluginState.ERROR
        
        # Good plugin should still work
        active_plugins = plugin_manager.get_active_plugins()
        assert len(active_plugins) == 1
        assert active_plugins[0] is good_plugin


@pytest.mark.integration
class TestConversionServiceIntegration:
    """Test integration between plugin system and ConversionService."""
    
    def test_conversion_service_with_plugins(self, temp_dir, app_context):
        """Test ConversionService recognizes plugin-provided handlers."""
        plugin_dir = temp_dir / "plugins" / "converter-plugin"
        plugin_dir.mkdir(parents=True)
        
        manifest = {
            "name": "converter-plugin",
            "version": "1.0.0",
            "display_name": "Converter Plugin",
            "description": "Plugin with document converter",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.ConverterPlugin",
            "supported_formats": [{
                "extension": ".conv",
                "mime_type": "application/x-conv",
                "description": "Converter Format"
            }],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {"services": ["DocumentHandler"]}
        }
        
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))
        
        plugin_code = '''
from orlando_toolkit.core.plugins.base import BasePlugin
from orlando_toolkit.core.plugins.interfaces import DocumentHandler
from orlando_toolkit.core.models import DitaContext
from pathlib import Path
from unittest.mock import Mock

class TestConverter(DocumentHandler):
    def can_handle(self, file_path):
        return file_path.suffix == '.conv'
    
    def get_supported_extensions(self):
        return ['.conv']
    
    def convert_document(self, file_path, destination_dir):
        context = Mock(spec=DitaContext)
        context.project_dir = destination_dir
        return context
    
    def get_name(self):
        return "Test Converter"
    
    def get_description(self):
        return "Test document converter"

class ConverterPlugin(BasePlugin):
    def get_name(self):
        return "Converter Plugin"
    
    def get_description(self):
        return "Plugin with document converter"
    
    def on_activate(self):
        super().on_activate()
        converter = TestConverter()
        self.app_context.service_registry.register_service(
            'DocumentHandler', converter, self.plugin_id
        )
'''
        (plugin_dir / "plugin.py").write_text(plugin_code)
        
        loader = PluginLoader([str(temp_dir / "plugins")])
        plugin_manager = loader.load_plugins(app_context)
        
        # Create ConversionService with plugin registry
        conversion_service = ConversionService(app_context.service_registry)
        
        # Test supported formats includes plugin format
        formats = conversion_service.get_supported_formats()
        extensions = [f.extension for f in formats]
        assert '.conv' in extensions
        
        # Test can handle plugin format
        test_file = Path("test.conv")
        assert conversion_service.can_handle_file(test_file)
        
        # Test DITA-only formats still supported
        assert '.zip' in extensions  # DITA package format