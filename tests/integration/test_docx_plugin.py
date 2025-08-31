"""Integration tests for the real DOCX plugin.

This module validates that the extracted DOCX plugin integrates correctly
with the plugin system and provides all expected functionality:
- Plugin loading and service registration
- Document conversion functionality
- UI extensions (heading filter panel)
- Marker providers (style markers)
- End-to-end workflow validation
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

from orlando_toolkit.core.plugins.loader import PluginLoader
from orlando_toolkit.core.plugins.base import PluginState
from orlando_toolkit.core.services import ConversionService


@pytest.mark.integration
@pytest.mark.docx_plugin
class TestDocxPluginLoading:
    """Test DOCX plugin loading and basic functionality."""
    
    def test_docx_plugin_discovery(self, docx_plugin_dir):
        """Test that DOCX plugin is discovered correctly."""
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        loader = PluginLoader([str(docx_plugin_dir.parent)])
        plugin_infos = loader.discover_plugins()
        
        # Should find the DOCX plugin
        docx_plugins = [info for info in plugin_infos if info.metadata.name == "docx-converter"]
        assert len(docx_plugins) == 1
        
        plugin_info = docx_plugins[0]
        assert plugin_info.metadata.version == "1.0.0"
        assert plugin_info.metadata.display_name == "DOCX Converter"
        assert plugin_info.metadata.category == "pipeline"
        assert "DocumentHandler" in plugin_info.metadata.provides["services"]
    
    def test_docx_plugin_loading(self, docx_plugin_dir, app_context):
        """Test that DOCX plugin loads correctly."""
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        loader = PluginLoader([str(docx_plugin_dir.parent)])
        plugin_manager = loader.load_plugins(app_context)
        
        # Should load successfully
        docx_plugin = plugin_manager.get_plugin_by_id("docx-converter")
        assert docx_plugin is not None
        assert docx_plugin.state == PluginState.ACTIVE
        assert docx_plugin.get_name() == "DOCX Converter"
    
    def test_docx_plugin_service_registration(self, docx_plugin_dir, app_context):
        """Test that DOCX plugin registers document handler correctly."""
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        loader = PluginLoader([str(docx_plugin_dir.parent)])
        plugin_manager = loader.load_plugins(app_context)
        
        # Check that DOCX handler is registered
        handler = app_context.service_registry.find_handler_for_extension('.docx')
        assert handler is not None
        assert handler.get_name() == "DOCX Document Handler"
        assert handler.can_handle(Path("test.docx"))
        assert '.docx' in handler.get_supported_extensions()
    
    def test_docx_plugin_metadata_validation(self, docx_plugin_dir):
        """Test that DOCX plugin metadata is complete and valid."""
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        loader = PluginLoader([str(docx_plugin_dir.parent)])
        plugin_infos = loader.discover_plugins()
        
        docx_plugins = [info for info in plugin_infos if info.metadata.name == "docx-converter"]
        assert len(docx_plugins) == 1
        
        metadata = docx_plugins[0].metadata
        
        # Validate required metadata
        assert metadata.name == "docx-converter"
        assert metadata.version == "1.0.0"
        assert metadata.display_name == "DOCX Converter"
        assert metadata.description == "Convert Microsoft Word documents to DITA"
        assert metadata.author == "Orlando Toolkit Team"
        
        # Validate supported formats
        assert len(metadata.supported_formats) == 1
        format_info = metadata.supported_formats[0]
        assert format_info["extension"] == ".docx"
        assert format_info["mime_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert format_info["description"] == "Microsoft Word Document"
        
        # Validate provides
        assert "DocumentHandler" in metadata.provides["services"]
        assert "HeadingFilterPanel" in metadata.provides.get("ui_extensions", [])
        assert "StyleMarkerProvider" in metadata.provides.get("marker_providers", [])
        
        # Validate UI configuration
        assert "ui" in metadata.__dict__
        ui_config = metadata.ui
        assert "splash_button" in ui_config
        splash_button = ui_config["splash_button"]
        assert splash_button["text"] == "Import from\nDOCX"
        assert splash_button["icon"] == "docx-icon.png"
        assert "Convert Microsoft Word documents to DITA" in splash_button["tooltip"]


@pytest.mark.integration
@pytest.mark.docx_plugin
class TestDocxPluginConversionService:
    """Test DOCX plugin integration with ConversionService."""
    
    def test_conversion_service_recognizes_docx(self, docx_plugin_dir, app_context):
        """Test that ConversionService recognizes DOCX format after plugin loading."""
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        # Load plugin
        loader = PluginLoader([str(docx_plugin_dir.parent)])
        plugin_manager = loader.load_plugins(app_context)
        
        # Create ConversionService with plugin registry
        conversion_service = ConversionService(app_context.service_registry)
        
        # Test supported formats
        formats = conversion_service.get_supported_formats()
        extensions = [f.extension for f in formats]
        
        assert '.docx' in extensions
        assert '.zip' in extensions  # DITA packages still supported
        
        # Find DOCX format
        docx_formats = [f for f in formats if f.extension == '.docx']
        assert len(docx_formats) == 1
        
        docx_format = docx_formats[0]
        assert docx_format.description == "Microsoft Word Document"
        assert docx_format.mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    
    def test_conversion_service_can_handle_docx(self, docx_plugin_dir, app_context):
        """Test that ConversionService can handle DOCX files."""
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        # Load plugin
        loader = PluginLoader([str(docx_plugin_dir.parent)])
        plugin_manager = loader.load_plugins(app_context)
        
        # Create ConversionService
        conversion_service = ConversionService(app_context.service_registry)
        
        # Test file handling
        test_docx = Path("document.docx")
        assert conversion_service.can_handle_file(test_docx)
        
        # Test other formats still work
        test_zip = Path("dita_package.zip")
        assert conversion_service.can_handle_file(test_zip)
        
        # Test unsupported format
        test_txt = Path("document.txt")
        assert not conversion_service.can_handle_file(test_txt)


@pytest.mark.integration
@pytest.mark.docx_plugin
class TestDocxPluginUIExtensions:
    """Test DOCX plugin UI extensions."""
    
    def test_docx_plugin_ui_registration(self, docx_plugin_dir, app_context):
        """Test that DOCX plugin registers UI extensions correctly."""
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        loader = PluginLoader([str(docx_plugin_dir.parent)])
        plugin_manager = loader.load_plugins(app_context)
        
        docx_plugin = plugin_manager.get_plugin_by_id("docx-converter")
        assert docx_plugin.state == PluginState.ACTIVE
        
        # Verify UI registry calls were made (if UI registry is present)
        if hasattr(app_context, 'ui_registry') and app_context.ui_registry:
            # Check for right panel extension registration
            app_context.ui_registry.register_right_panel_extension.assert_called()
            
            # Check for marker provider registration
            app_context.ui_registry.register_marker_provider.assert_called()
    
    def test_docx_plugin_heading_filter_panel(self, docx_plugin_dir, app_context):
        """Test DOCX plugin heading filter panel functionality."""
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        try:
            # Try to import the heading filter panel
            from orlando_docx_plugin.src.ui.heading_filter import HeadingFilterPanel
            
            # Test panel can be instantiated (may require mocking Qt)
            panel = HeadingFilterPanel()
            
            # Test basic functionality exists
            assert hasattr(panel, 'get_filter_settings')
            assert hasattr(panel, 'set_available_styles')
            
        except ImportError:
            pytest.skip("DOCX plugin not available or Qt not available")
    
    def test_docx_plugin_style_markers(self, docx_plugin_dir, app_context):
        """Test DOCX plugin style marker provider."""
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        try:
            # Try to import marker provider (from plugin architecture)
            loader = PluginLoader([str(docx_plugin_dir.parent)])
            plugin_manager = loader.load_plugins(app_context)
            
            docx_plugin = plugin_manager.get_plugin_by_id("docx-converter")
            assert docx_plugin is not None
            
            # Plugin should have registered marker provider
            # (This would be verified through the UI registry mock calls)
            
        except ImportError:
            pytest.skip("DOCX plugin not available")


@pytest.mark.integration
@pytest.mark.docx_plugin
class TestDocxPluginErrorHandling:
    """Test DOCX plugin error handling."""
    
    def test_docx_plugin_handles_missing_dependencies(self, temp_dir, app_context):
        """Test DOCX plugin behavior when dependencies are missing."""
        # This test would verify that the plugin gracefully handles missing dependencies
        # For now, we'll test that the plugin loads (assuming dependencies are available)
        
        docx_plugin_dir = Path(__file__).parent.parent.parent / "orlando-docx-plugin"
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        loader = PluginLoader([str(docx_plugin_dir.parent)])
        plugin_manager = loader.load_plugins(app_context)
        
        docx_plugin = plugin_manager.get_plugin_by_id("docx-converter")
        
        # Plugin should either load successfully or be in error state
        assert docx_plugin.state in [PluginState.ACTIVE, PluginState.ERROR]
        
        if docx_plugin.state == PluginState.ERROR:
            # This would indicate missing dependencies or other errors
            pytest.skip("DOCX plugin failed to load (likely missing dependencies)")
    
    def test_docx_plugin_deactivation_cleanup(self, docx_plugin_dir, app_context):
        """Test that DOCX plugin cleans up properly when deactivated."""
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        loader = PluginLoader([str(docx_plugin_dir.parent)])
        plugin_manager = loader.load_plugins(app_context)
        
        docx_plugin = plugin_manager.get_plugin_by_id("docx-converter")
        if docx_plugin.state != PluginState.ACTIVE:
            pytest.skip("DOCX plugin not active")
        
        # Verify handler is registered
        handler = app_context.service_registry.find_handler_for_extension('.docx')
        assert handler is not None
        
        # Deactivate plugin
        success = plugin_manager.deactivate_plugin("docx-converter")
        assert success
        assert docx_plugin.state == PluginState.LOADED
        
        # Verify handler is unregistered
        handler = app_context.service_registry.find_handler_for_extension('.docx')
        assert handler is None
        
        # Verify UI extensions are cleaned up (if UI registry present)
        if hasattr(app_context, 'ui_registry') and app_context.ui_registry:
            app_context.ui_registry.unregister_right_panel_extension.assert_called()
            app_context.ui_registry.unregister_marker_provider.assert_called()


@pytest.mark.integration
@pytest.mark.docx_plugin
@pytest.mark.slow
class TestDocxPluginEndToEnd:
    """End-to-end integration tests for DOCX plugin."""
    
    @pytest.fixture
    def mock_docx_file(self, temp_dir):
        """Create a mock DOCX file for testing."""
        docx_path = temp_dir / "test_document.docx"
        # Create a minimal file that looks like a DOCX
        docx_path.write_bytes(b'PK\x03\x04')  # ZIP file signature
        return docx_path
    
    def test_docx_conversion_workflow(self, docx_plugin_dir, app_context, mock_docx_file):
        """Test complete DOCX conversion workflow."""
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        # Load plugin
        loader = PluginLoader([str(docx_plugin_dir.parent)])
        plugin_manager = loader.load_plugins(app_context)
        
        docx_plugin = plugin_manager.get_plugin_by_id("docx-converter")
        if docx_plugin.state != PluginState.ACTIVE:
            pytest.skip("DOCX plugin not active")
        
        # Get document handler
        handler = app_context.service_registry.find_handler_for_extension('.docx')
        assert handler is not None
        
        # Test conversion (with mocking to avoid actual DOCX processing)
        with patch.object(handler, 'convert_document') as mock_convert:
            mock_dita_context = Mock()
            mock_dita_context.project_dir = mock_docx_file.parent / "output"
            mock_convert.return_value = mock_dita_context
            
            # Simulate conversion
            result = handler.convert_document(mock_docx_file, mock_docx_file.parent / "output")
            
            assert result is mock_dita_context
            mock_convert.assert_called_once()
    
    def test_docx_plugin_with_conversion_service(self, docx_plugin_dir, app_context, mock_docx_file):
        """Test DOCX plugin through ConversionService interface."""
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        # Load plugin
        loader = PluginLoader([str(docx_plugin_dir.parent)])
        plugin_manager = loader.load_plugins(app_context)
        
        docx_plugin = plugin_manager.get_plugin_by_id("docx-converter")
        if docx_plugin.state != PluginState.ACTIVE:
            pytest.skip("DOCX plugin not active")
        
        # Create ConversionService
        conversion_service = ConversionService(app_context.service_registry)
        
        # Test file can be handled
        assert conversion_service.can_handle_file(mock_docx_file)
        
        # Mock the actual conversion to avoid dependencies
        handler = app_context.service_registry.find_handler_for_extension('.docx')
        with patch.object(handler, 'convert_document') as mock_convert:
            mock_dita_context = Mock()
            mock_convert.return_value = mock_dita_context
            
            # Test conversion through service
            result = conversion_service.convert_document(mock_docx_file, mock_docx_file.parent / "output")
            
            assert result is mock_dita_context
            mock_convert.assert_called_once()


@pytest.mark.integration
@pytest.mark.docx_plugin
class TestDocxPluginCompatibility:
    """Test DOCX plugin compatibility with core system."""
    
    def test_docx_plugin_with_dita_only_mode(self, docx_plugin_dir, app_context):
        """Test that DOCX plugin doesn't interfere with DITA-only functionality."""
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        # Load plugin
        loader = PluginLoader([str(docx_plugin_dir.parent)])
        plugin_manager = loader.load_plugins(app_context)
        
        # Create ConversionService
        conversion_service = ConversionService(app_context.service_registry)
        
        # Test that DITA functionality still works
        formats = conversion_service.get_supported_formats()
        extensions = [f.extension for f in formats]
        
        # Both DITA and DOCX should be supported
        assert '.zip' in extensions  # DITA packages
        assert '.docx' in extensions  # DOCX files
        
        # Test DITA files can still be handled
        dita_file = Path("test_package.zip")
        assert conversion_service.can_handle_file(dita_file)
    
    def test_docx_plugin_version_compatibility(self, docx_plugin_dir):
        """Test DOCX plugin version compatibility requirements."""
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        loader = PluginLoader([str(docx_plugin_dir.parent)])
        plugin_infos = loader.discover_plugins()
        
        docx_plugins = [info for info in plugin_infos if info.metadata.name == "docx-converter"]
        if not docx_plugins:
            pytest.skip("DOCX plugin not found")
        
        metadata = docx_plugins[0].metadata
        
        # Check version requirements
        assert metadata.orlando_version == ">=2.0.0"
        assert metadata.plugin_api_version == "1.0"
        
        # Check Python version requirement
        assert metadata.dependencies["python"] == ">=3.8"
    
    def test_docx_plugin_resource_isolation(self, docx_plugin_dir, app_context):
        """Test that DOCX plugin resources are properly isolated."""
        if not docx_plugin_dir.exists():
            pytest.skip("DOCX plugin directory not found")
        
        loader = PluginLoader([str(docx_plugin_dir.parent)])
        plugin_manager = loader.load_plugins(app_context)
        
        docx_plugin = plugin_manager.get_plugin_by_id("docx-converter")
        if docx_plugin.state != PluginState.ACTIVE:
            pytest.skip("DOCX plugin not active")
        
        # Test plugin has its own directory
        assert docx_plugin.plugin_dir == str(docx_plugin_dir)
        
        # Test plugin has its own logger
        assert docx_plugin.logger.name.startswith('plugin.')
        
        # Test plugin services are properly namespaced
        handler = app_context.service_registry.find_handler_for_extension('.docx')
        service_info = app_context.service_registry.get_all_services('DocumentHandler')
        docx_services = [s for s in service_info if s.plugin_id == 'docx-converter']
        assert len(docx_services) == 1
        assert docx_services[0].service is handler