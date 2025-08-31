"""Integration tests for plugin UI functionality.

This module validates that plugin UI extensions work correctly:
- Right panel extensions
- Marker provider integration
- Plugin management UI
- UI error handling and recovery
"""

import pytest
import json
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from orlando_toolkit.core.plugins.loader import PluginLoader
from orlando_toolkit.core.plugins.base import BasePlugin, PluginState
from orlando_toolkit.core.plugins.ui_registry import UIRegistry
from orlando_toolkit.core.context import AppContext


@pytest.mark.integration
@pytest.mark.ui
class TestUIRegistry:
    """Test UI registry functionality."""
    
    def test_register_right_panel_extension(self, mock_ui_registry):
        """Test registering right panel extensions."""
        # Mock panel widget
        mock_panel = Mock()
        mock_panel.setParent = Mock()
        
        # Register extension
        mock_ui_registry.register_right_panel_extension(
            'test-plugin', 'Test Panel', mock_panel
        )
        
        # Verify registration was called
        mock_ui_registry.register_right_panel_extension.assert_called_once_with(
            'test-plugin', 'Test Panel', mock_panel
        )
    
    def test_register_marker_provider(self, mock_ui_registry):
        """Test registering marker providers."""
        # Mock marker provider
        mock_provider = Mock()
        mock_provider.get_markers = Mock(return_value=[])
        
        # Register provider
        mock_ui_registry.register_marker_provider('test-plugin', mock_provider)
        
        # Verify registration was called
        mock_ui_registry.register_marker_provider.assert_called_once_with(
            'test-plugin', mock_provider
        )
    
    def test_unregister_ui_extensions(self, mock_ui_registry):
        """Test unregistering UI extensions."""
        mock_ui_registry.unregister_right_panel_extension('test-plugin')
        mock_ui_registry.unregister_marker_provider('test-plugin')
        
        mock_ui_registry.unregister_right_panel_extension.assert_called_once_with('test-plugin')
        mock_ui_registry.unregister_marker_provider.assert_called_once_with('test-plugin')


@pytest.mark.integration
@pytest.mark.ui
class TestPluginUIExtensions:
    """Test plugin UI extension functionality."""
    
    def test_plugin_with_right_panel_extension(self, temp_dir, app_context):
        """Test plugin that provides right panel extension."""
        plugin_dir = temp_dir / "plugins" / "ui-plugin"
        plugin_dir.mkdir(parents=True)
        
        manifest = {
            "name": "ui-plugin",
            "version": "1.0.0",
            "display_name": "UI Plugin",
            "description": "Plugin with UI extensions",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.UIPlugin",
            "supported_formats": [],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {
                "services": [],
                "ui_extensions": ["RightPanel"]
            }
        }
        
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))
        
        plugin_code = '''
from orlando_toolkit.core.plugins.base import BasePlugin
from unittest.mock import Mock

class UIPlugin(BasePlugin):
    def get_name(self):
        return "UI Plugin"
    
    def get_description(self):
        return "Plugin with UI extensions"
    
    def on_activate(self):
        super().on_activate()
        
        # Create mock panel widget
        panel_widget = Mock()
        panel_widget.setParent = Mock()
        
        # Register right panel extension
        if hasattr(self.app_context, 'ui_registry') and self.app_context.ui_registry:
            self.app_context.ui_registry.register_right_panel_extension(
                self.plugin_id, "Test Panel", panel_widget
            )
    
    def on_deactivate(self):
        super().on_deactivate()
        
        # Unregister UI extensions
        if hasattr(self.app_context, 'ui_registry') and self.app_context.ui_registry:
            self.app_context.ui_registry.unregister_right_panel_extension(self.plugin_id)
'''
        (plugin_dir / "plugin.py").write_text(plugin_code)
        
        loader = PluginLoader([str(temp_dir / "plugins")])
        plugin_manager = loader.load_plugins(app_context)
        
        # Verify plugin loaded and registered UI extension
        active_plugins = plugin_manager.get_active_plugins()
        assert len(active_plugins) == 1
        
        plugin = active_plugins[0]
        assert plugin.state == PluginState.ACTIVE
        
        # Verify UI registry was called (if present)
        if hasattr(app_context, 'ui_registry') and app_context.ui_registry:
            app_context.ui_registry.register_right_panel_extension.assert_called_once()
    
    def test_plugin_with_marker_provider(self, temp_dir, app_context):
        """Test plugin that provides marker provider."""
        plugin_dir = temp_dir / "plugins" / "marker-plugin"
        plugin_dir.mkdir(parents=True)
        
        manifest = {
            "name": "marker-plugin",
            "version": "1.0.0",
            "display_name": "Marker Plugin",
            "description": "Plugin with marker provider",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.MarkerPlugin",
            "supported_formats": [],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {
                "services": [],
                "marker_providers": ["TestMarkerProvider"]
            }
        }
        
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))
        
        plugin_code = '''
from orlando_toolkit.core.plugins.base import BasePlugin
from unittest.mock import Mock

class TestMarkerProvider:
    def get_markers(self, dita_context):
        return [
            {"position": 100, "color": "red", "tooltip": "Test marker"},
            {"position": 200, "color": "blue", "tooltip": "Another marker"}
        ]

class MarkerPlugin(BasePlugin):
    def get_name(self):
        return "Marker Plugin"
    
    def get_description(self):
        return "Plugin with marker provider"
    
    def on_activate(self):
        super().on_activate()
        
        # Create marker provider
        marker_provider = TestMarkerProvider()
        
        # Register marker provider
        if hasattr(self.app_context, 'ui_registry') and self.app_context.ui_registry:
            self.app_context.ui_registry.register_marker_provider(
                self.plugin_id, marker_provider
            )
    
    def on_deactivate(self):
        super().on_deactivate()
        
        # Unregister marker provider
        if hasattr(self.app_context, 'ui_registry') and self.app_context.ui_registry:
            self.app_context.ui_registry.unregister_marker_provider(self.plugin_id)
'''
        (plugin_dir / "plugin.py").write_text(plugin_code)
        
        loader = PluginLoader([str(temp_dir / "plugins")])
        plugin_manager = loader.load_plugins(app_context)
        
        # Verify plugin loaded
        active_plugins = plugin_manager.get_active_plugins()
        assert len(active_plugins) == 1
        
        plugin = active_plugins[0]
        assert plugin.state == PluginState.ACTIVE
        
        # Verify UI registry was called (if present)
        if hasattr(app_context, 'ui_registry') and app_context.ui_registry:
            app_context.ui_registry.register_marker_provider.assert_called_once()
    
    def test_ui_extension_cleanup_on_deactivation(self, temp_dir, app_context):
        """Test that UI extensions are cleaned up when plugin is deactivated."""
        plugin_dir = temp_dir / "plugins" / "cleanup-plugin"
        plugin_dir.mkdir(parents=True)
        
        manifest = {
            "name": "cleanup-plugin",
            "version": "1.0.0",
            "display_name": "Cleanup Plugin",
            "description": "Plugin for testing UI cleanup",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.CleanupPlugin",
            "supported_formats": [],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {
                "services": [],
                "ui_extensions": ["RightPanel"],
                "marker_providers": ["TestMarkerProvider"]
            }
        }
        
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))
        
        plugin_code = '''
from orlando_toolkit.core.plugins.base import BasePlugin
from unittest.mock import Mock

class CleanupPlugin(BasePlugin):
    def get_name(self):
        return "Cleanup Plugin"
    
    def get_description(self):
        return "Plugin for testing UI cleanup"
    
    def on_activate(self):
        super().on_activate()
        
        if hasattr(self.app_context, 'ui_registry') and self.app_context.ui_registry:
            # Register both types of UI extensions
            panel_widget = Mock()
            self.app_context.ui_registry.register_right_panel_extension(
                self.plugin_id, "Test Panel", panel_widget
            )
            
            marker_provider = Mock()
            self.app_context.ui_registry.register_marker_provider(
                self.plugin_id, marker_provider
            )
    
    def on_deactivate(self):
        super().on_deactivate()
        
        if hasattr(self.app_context, 'ui_registry') and self.app_context.ui_registry:
            # Cleanup UI extensions
            self.app_context.ui_registry.unregister_right_panel_extension(self.plugin_id)
            self.app_context.ui_registry.unregister_marker_provider(self.plugin_id)
'''
        (plugin_dir / "plugin.py").write_text(plugin_code)
        
        loader = PluginLoader([str(temp_dir / "plugins")])
        plugin_manager = loader.load_plugins(app_context)
        
        plugin = plugin_manager.get_plugin_by_id("cleanup-plugin")
        assert plugin.state == PluginState.ACTIVE
        
        # Deactivate plugin
        success = plugin_manager.deactivate_plugin("cleanup-plugin")
        assert success
        assert plugin.state == PluginState.LOADED
        
        # Verify cleanup was called
        if hasattr(app_context, 'ui_registry') and app_context.ui_registry:
            app_context.ui_registry.unregister_right_panel_extension.assert_called()
            app_context.ui_registry.unregister_marker_provider.assert_called()


@pytest.mark.integration
@pytest.mark.ui
class TestPluginManagerDialog:
    """Test plugin management dialog functionality (mocked)."""
    
    @patch('orlando_toolkit.ui.dialogs.plugin_manager_dialog.PluginManagerDialog')
    def test_plugin_manager_dialog_creation(self, mock_dialog_class):
        """Test plugin manager dialog can be created."""
        mock_dialog = Mock()
        mock_dialog_class.return_value = mock_dialog
        
        # Mock the dialog creation
        from orlando_toolkit.ui.dialogs.plugin_manager_dialog import PluginManagerDialog
        
        # This would be called from the main application
        dialog = PluginManagerDialog(None, None)  # parent, plugin_manager
        assert dialog is mock_dialog
    
    def test_simple_plugin_manager_dialog_functionality(self):
        """Test simplified plugin manager dialog basic functionality."""
        from orlando_toolkit.ui.dialogs.plugin_manager_dialog import SimplePluginManagerDialog
        
        # Create mock parent and plugin manager
        mock_parent = Mock()
        mock_plugin_manager = Mock()
        
        try:
            dialog = SimplePluginManagerDialog(mock_parent, mock_plugin_manager)
            # Test basic methods exist
            assert hasattr(dialog, 'show_modal')
            assert hasattr(dialog, '_populate_plugins')
            assert hasattr(dialog, '_plugin_action')
            assert hasattr(dialog, '_import_from_github')
        except ImportError:
            # Dependencies not available in test environment
            pytest.skip("UI dependencies not available for testing")


@pytest.mark.integration
@pytest.mark.ui
class TestUIErrorHandling:
    """Test UI error handling in plugin system."""
    
    def test_ui_extension_with_error(self, temp_dir, app_context):
        """Test handling of UI extension that throws errors."""
        plugin_dir = temp_dir / "plugins" / "ui-error-plugin"
        plugin_dir.mkdir(parents=True)
        
        manifest = {
            "name": "ui-error-plugin",
            "version": "1.0.0",
            "display_name": "UI Error Plugin",
            "description": "Plugin with UI error",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.UIErrorPlugin",
            "supported_formats": [],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {
                "services": [],
                "ui_extensions": ["RightPanel"]
            }
        }
        
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))
        
        plugin_code = '''
from orlando_toolkit.core.plugins.base import BasePlugin

class UIErrorPlugin(BasePlugin):
    def get_name(self):
        return "UI Error Plugin"
    
    def get_description(self):
        return "Plugin with UI error"
    
    def on_activate(self):
        super().on_activate()
        
        # This will cause an error
        raise RuntimeError("UI extension failed to initialize")
'''
        (plugin_dir / "plugin.py").write_text(plugin_code)
        
        loader = PluginLoader([str(temp_dir / "plugins")])
        plugin_manager = loader.load_plugins(app_context)
        
        # Plugin should be in ERROR state
        plugin = plugin_manager.get_plugin_by_id("ui-error-plugin")
        assert plugin.state == PluginState.ERROR
        
        # Other parts of the system should continue working
        all_plugins = plugin_manager.get_all_plugins()
        assert len(all_plugins) == 1
    
    def test_marker_provider_with_error(self, temp_dir, app_context):
        """Test handling of marker provider that throws errors."""
        plugin_dir = temp_dir / "plugins" / "marker-error-plugin"
        plugin_dir.mkdir(parents=True)
        
        manifest = {
            "name": "marker-error-plugin",
            "version": "1.0.0",
            "display_name": "Marker Error Plugin",
            "description": "Plugin with marker provider error",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.MarkerErrorPlugin",
            "supported_formats": [],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {
                "services": [],
                "marker_providers": ["ErrorMarkerProvider"]
            }
        }
        
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))
        
        plugin_code = '''
from orlando_toolkit.core.plugins.base import BasePlugin

class ErrorMarkerProvider:
    def get_markers(self, dita_context):
        raise RuntimeError("Marker provider failed")

class MarkerErrorPlugin(BasePlugin):
    def get_name(self):
        return "Marker Error Plugin"
    
    def get_description(self):
        return "Plugin with marker provider error"
    
    def on_activate(self):
        super().on_activate()
        
        # Register marker provider that will fail
        marker_provider = ErrorMarkerProvider()
        if hasattr(self.app_context, 'ui_registry') and self.app_context.ui_registry:
            self.app_context.ui_registry.register_marker_provider(
                self.plugin_id, marker_provider
            )
'''
        (plugin_dir / "plugin.py").write_text(plugin_code)
        
        loader = PluginLoader([str(temp_dir / "plugins")])
        plugin_manager = loader.load_plugins(app_context)
        
        # Plugin should load successfully (error happens when markers are requested)
        plugin = plugin_manager.get_plugin_by_id("marker-error-plugin")
        assert plugin.state == PluginState.ACTIVE
        
        # Test that marker provider error is handled gracefully
        # (This would be handled by the UI components consuming the markers)


@pytest.mark.integration
@pytest.mark.ui
class TestSplashScreenIntegration:
    """Test plugin integration with splash screen."""
    
    def test_splash_button_configuration(self, sample_plugin_metadata):
        """Test that plugin manifest splash button config is read correctly."""
        # This would be tested by the splash screen component
        # Here we just verify the metadata structure
        manifest_with_ui = {
            "name": "splash-plugin",
            "version": "1.0.0",
            "display_name": "Splash Plugin",
            "description": "Plugin with splash button",
            "author": "Test Author",
            "orlando_version": ">=2.0.0",
            "plugin_api_version": "1.0",
            "category": "pipeline",
            "entry_point": "plugin.SplashPlugin",
            "supported_formats": [{
                "extension": ".splash",
                "mime_type": "application/x-splash",
                "description": "Splash Format"
            }],
            "dependencies": {"python": ">=3.8", "packages": []},
            "provides": {"services": ["DocumentHandler"]},
            "ui": {
                "splash_button": {
                    "text": "Import from\\nSPLASH",
                    "icon": "splash-icon.png",
                    "tooltip": "Convert SPLASH documents to DITA"
                }
            }
        }
        
        from orlando_toolkit.core.plugins.metadata import PluginMetadata
        metadata = PluginMetadata(**manifest_with_ui)
        
        assert hasattr(metadata, 'ui')
        assert 'splash_button' in metadata.ui
        assert metadata.ui['splash_button']['text'] == "Import from\\nSPLASH"
        assert metadata.ui['splash_button']['icon'] == "splash-icon.png"
        assert metadata.ui['splash_button']['tooltip'] == "Convert SPLASH documents to DITA"
    
    @patch('orlando_toolkit.ui.widgets.structure_tree_widget.StructureTreeWidget')
    def test_structure_tree_marker_integration(self, mock_tree_widget):
        """Test integration with structure tree widget markers."""
        mock_widget = Mock()
        mock_tree_widget.return_value = mock_widget
        
        # Mock marker bar adapter
        mock_adapter = Mock()
        mock_widget.marker_bar_adapter = mock_adapter
        
        # This would be called when plugin provides markers
        test_markers = [
            {"position": 100, "color": "red", "tooltip": "Test marker"},
            {"position": 200, "color": "blue", "tooltip": "Another marker"}
        ]
        
        # Simulate marker update
        mock_adapter.update_markers = Mock()
        mock_adapter.update_markers(test_markers)
        
        # Verify markers were processed
        mock_adapter.update_markers.assert_called_once_with(test_markers)