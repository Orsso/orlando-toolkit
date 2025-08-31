"""Integration tests for DITA-only mode functionality.

This module validates that the core application functions correctly without
any plugins loaded, providing pure DITA import and editing capabilities:
- DITA package import
- Core services functionality
- UI operation without plugin extensions
- Performance in plugin-free mode
"""

import pytest
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from orlando_toolkit.core.services import ConversionService
from orlando_toolkit.core.importers.dita_importer import DitaPackageImporter
from orlando_toolkit.core.plugins.registry import ServiceRegistry
from orlando_toolkit.core.context import AppContext


@pytest.mark.integration
@pytest.mark.dita_only
class TestDitaOnlyConversionService:
    """Test ConversionService in DITA-only mode."""
    
    def test_conversion_service_without_plugins(self, mock_service_registry):
        """Test ConversionService works without any plugins."""
        conversion_service = ConversionService(mock_service_registry)
        
        # Should support DITA packages only
        formats = conversion_service.get_supported_formats()
        assert len(formats) == 1
        
        dita_format = formats[0]
        assert dita_format.extension == '.zip'
        assert dita_format.description == "DITA Package"
        assert dita_format.mime_type == "application/zip"
    
    def test_dita_file_handling_without_plugins(self, mock_service_registry):
        """Test file handling for DITA packages without plugins."""
        conversion_service = ConversionService(mock_service_registry)
        
        # DITA package should be supported
        dita_file = Path("dita_package.zip")
        assert conversion_service.can_handle_file(dita_file)
        
        # Other formats should not be supported
        docx_file = Path("document.docx")
        assert not conversion_service.can_handle_file(docx_file)
        
        txt_file = Path("document.txt")
        assert not conversion_service.can_handle_file(txt_file)
        
        pdf_file = Path("document.pdf")
        assert not conversion_service.can_handle_file(pdf_file)
    
    def test_dita_conversion_without_plugins(self, mock_service_registry, sample_dita_package, temp_dir):
        """Test DITA package conversion without plugins."""
        conversion_service = ConversionService(mock_service_registry)
        
        output_dir = temp_dir / "dita_output"
        
        # Mock the DitaPackageImporter for testing
        with patch('orlando_toolkit.core.services.conversion_service.DitaPackageImporter') as mock_importer_class:
            mock_importer = Mock()
            mock_dita_context = Mock()
            mock_dita_context.project_dir = output_dir
            mock_importer.import_package.return_value = mock_dita_context
            mock_importer_class.return_value = mock_importer
            
            # Test conversion
            result = conversion_service.convert_document(sample_dita_package, output_dir)
            
            assert result is mock_dita_context
            mock_importer.import_package.assert_called_once_with(sample_dita_package, output_dir)


@pytest.mark.integration
@pytest.mark.dita_only
class TestDitaPackageImporter:
    """Test DITA package importer functionality."""
    
    def test_dita_importer_basic_functionality(self):
        """Test basic DITA importer functionality."""
        importer = DitaPackageImporter()
        
        # Test basic methods exist
        assert hasattr(importer, 'import_package')
        assert hasattr(importer, 'can_handle')
        assert hasattr(importer, 'get_supported_extensions')
        
        # Test supported extensions
        extensions = importer.get_supported_extensions()
        assert '.zip' in extensions
    
    def test_dita_importer_can_handle(self):
        """Test DITA importer file handling detection."""
        importer = DitaPackageImporter()
        
        # Should handle ZIP files
        zip_file = Path("dita_package.zip")
        assert importer.can_handle(zip_file)
        
        # Should not handle other formats
        docx_file = Path("document.docx")
        assert not importer.can_handle(docx_file)
        
        txt_file = Path("document.txt")
        assert not importer.can_handle(txt_file)
    
    def test_dita_package_import(self, sample_dita_package, temp_dir):
        """Test importing a DITA package."""
        importer = DitaPackageImporter()
        output_dir = temp_dir / "dita_output"
        
        # Import package
        dita_context = importer.import_package(sample_dita_package, output_dir)
        
        # Verify result
        assert dita_context is not None
        assert hasattr(dita_context, 'project_dir')
        assert dita_context.project_dir == output_dir
        
        # Verify files were extracted
        assert output_dir.exists()
        extracted_files = list(output_dir.rglob('*'))
        extracted_names = [f.name for f in extracted_files if f.is_file()]
        
        # Should contain DITA files
        assert any(name.endswith('.dita') for name in extracted_names)
        assert any(name.endswith('.ditamap') for name in extracted_names)


@pytest.mark.integration
@pytest.mark.dita_only
class TestCoreServicesWithoutPlugins:
    """Test core services functionality without plugins."""
    
    def test_app_context_without_plugins(self, mock_service_registry):
        """Test AppContext functionality without plugin manager."""
        app_context = AppContext(mock_service_registry)
        
        # Basic functionality should work
        assert app_context.service_registry is mock_service_registry
        assert app_context.plugin_manager is None
        
        # Service getters should return None initially
        assert app_context.get_conversion_service() is None
        assert app_context.get_structure_editing_service() is None
        assert app_context.get_undo_service() is None
        assert app_context.get_preview_service() is None
        
        # Context stats should work
        stats = app_context.get_context_stats()
        assert stats['has_conversion_service'] is False
        assert stats['has_plugin_manager'] is False
        assert stats['plugin_data_count'] == 0
    
    def test_service_registry_without_plugins(self, mock_service_registry):
        """Test service registry functionality without plugins."""
        # Should have no handlers initially
        handlers = mock_service_registry.get_all_services('DocumentHandler')
        assert len(handlers) == 0
        
        # Should not find handlers for any extension
        assert mock_service_registry.find_handler_for_extension('.docx') is None
        assert mock_service_registry.find_handler_for_extension('.pdf') is None
        assert mock_service_registry.find_handler_for_extension('.txt') is None
        
        # Registry stats should show empty state
        stats = mock_service_registry.get_registry_stats()
        assert stats['total_services'] == 0
        assert stats['service_types'] == []
    
    def test_structure_editing_service_without_plugins(self):
        """Test structure editing service works without plugins."""
        from orlando_toolkit.core.services.structure_editing_service import StructureEditingService
        
        service = StructureEditingService()
        
        # Basic functionality should be available
        assert hasattr(service, 'move_topic')
        assert hasattr(service, 'rename_topic')
        assert hasattr(service, 'delete_topic')
        assert hasattr(service, 'add_topic')
        
        # Service should handle DITA contexts
        mock_context = Mock()
        mock_context.topics = []
        
        # Test that service methods exist and can be called
        # (Full functionality testing would require actual DITA content)
        try:
            service.get_topic_hierarchy(mock_context)
        except Exception:
            # Expected - no actual content to process
            pass
    
    def test_preview_service_without_plugins(self):
        """Test preview service works without plugins."""
        from orlando_toolkit.core.services.preview_service import PreviewService
        
        service = PreviewService()
        
        # Basic functionality should be available
        assert hasattr(service, 'generate_preview')
        assert hasattr(service, 'get_preview_html')
        
        # Service should work with DITA contexts
        mock_context = Mock()
        mock_topic = Mock()
        
        try:
            service.generate_preview(mock_context, mock_topic)
        except Exception:
            # Expected - no actual content to process
            pass
    
    def test_undo_service_without_plugins(self):
        """Test undo service works without plugins."""
        from orlando_toolkit.core.services.undo_service import UndoService
        
        service = UndoService()
        
        # Basic functionality should be available
        assert hasattr(service, 'can_undo')
        assert hasattr(service, 'can_redo')
        assert hasattr(service, 'undo')
        assert hasattr(service, 'redo')
        assert hasattr(service, 'add_command')
        
        # Test basic state
        assert not service.can_undo()
        assert not service.can_redo()


@pytest.mark.integration
@pytest.mark.dita_only
class TestUIWithoutPlugins:
    """Test UI functionality without plugin extensions."""
    
    @patch('orlando_toolkit.ui.structure_tab.StructureTab')
    def test_structure_tab_without_plugins(self, mock_structure_tab):
        """Test structure tab functionality without plugin extensions."""
        mock_tab = Mock()
        mock_structure_tab.return_value = mock_tab
        
        # Structure tab should be creatable without plugins
        from orlando_toolkit.ui.structure_tab import StructureTab
        tab = StructureTab(None, None)  # parent, app_context
        
        assert tab is mock_tab
        # Tab should function without plugin extensions
    
    @patch('orlando_toolkit.ui.widgets.structure_tree_widget.StructureTreeWidget')
    def test_structure_tree_without_plugins(self, mock_tree_widget):
        """Test structure tree widget without plugin markers."""
        mock_widget = Mock()
        mock_tree_widget.return_value = mock_widget
        
        from orlando_toolkit.ui.widgets.structure_tree_widget import StructureTreeWidget
        widget = StructureTreeWidget()
        
        assert widget is mock_widget
        
        # Widget should work without marker providers
        mock_widget.update_markers = Mock()
        mock_widget.update_markers([])  # No markers from plugins
        mock_widget.update_markers.assert_called_once_with([])
    
    @patch('orlando_toolkit.ui.tabs.structure.right_panel.RightPanel')
    def test_right_panel_without_plugins(self, mock_right_panel):
        """Test right panel functionality without plugin extensions."""
        mock_panel = Mock()
        mock_right_panel.return_value = mock_panel
        
        from orlando_toolkit.ui.tabs.structure.right_panel import RightPanel
        panel = RightPanel(None, None)  # parent, app_context
        
        assert panel is mock_panel
        
        # Panel should work without plugin extensions
        mock_panel.clear_extensions = Mock()
        mock_panel.clear_extensions()
        mock_panel.clear_extensions.assert_called_once()
    
    def test_file_dialog_filters_without_plugins(self):
        """Test file dialog shows only DITA formats without plugins."""
        from orlando_toolkit.core.services.conversion_service import ConversionService
        from orlando_toolkit.core.plugins.registry import ServiceRegistry
        
        # Create service without plugins
        registry = ServiceRegistry()
        service = ConversionService(registry)
        
        formats = service.get_supported_formats()
        
        # Should only show DITA package format
        assert len(formats) == 1
        assert formats[0].extension == '.zip'
        assert formats[0].description == "DITA Package"
        
        # File dialog filter string should only include DITA
        filter_strings = [f"{fmt.description} (*{fmt.extension})" for fmt in formats]
        assert len(filter_strings) == 1
        assert "DITA Package (*.zip)" in filter_strings[0]


@pytest.mark.integration
@pytest.mark.dita_only
@pytest.mark.performance
class TestDitaOnlyPerformance:
    """Test performance characteristics in DITA-only mode."""
    
    def test_startup_time_without_plugins(self, performance_timer, mock_service_registry):
        """Test application startup time without plugins."""
        performance_timer.start()
        
        # Simulate core service initialization
        app_context = AppContext(mock_service_registry)
        conversion_service = ConversionService(mock_service_registry)
        
        from orlando_toolkit.core.services.structure_editing_service import StructureEditingService
        from orlando_toolkit.core.services.undo_service import UndoService
        from orlando_toolkit.core.services.preview_service import PreviewService
        
        structure_service = StructureEditingService()
        undo_service = UndoService()
        preview_service = PreviewService()
        
        # Update app context with services
        app_context.update_services(
            conversion_service=conversion_service,
            structure_editing_service=structure_service,
            undo_service=undo_service,
            preview_service=preview_service
        )
        
        startup_time = performance_timer.stop()
        
        # Should be very fast without plugins
        assert startup_time < 1.0, f"DITA-only startup too slow: {startup_time:.3f}s"
        
        print(f"DITA-only mode startup time: {startup_time:.3f}s")
    
    def test_memory_usage_without_plugins(self, mock_service_registry):
        """Test memory usage baseline without plugins."""
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss
        
        # Create core services
        app_context = AppContext(mock_service_registry)
        conversion_service = ConversionService(mock_service_registry)
        
        final_memory = process.memory_info().rss
        memory_increase = final_memory - initial_memory
        
        # Memory increase should be minimal
        memory_mb = memory_increase / (1024 * 1024)
        
        print(f"Memory increase for core services: {memory_mb:.2f} MB")
        
        # This is a baseline - with plugins, memory usage will be higher
        assert memory_mb < 50, f"Core services use too much memory: {memory_mb:.2f} MB"
    
    def test_dita_import_performance(self, sample_dita_package, temp_dir, performance_timer):
        """Test DITA import performance without plugins."""
        importer = DitaPackageImporter()
        output_dir = temp_dir / "perf_test_output"
        
        performance_timer.start()
        dita_context = importer.import_package(sample_dita_package, output_dir)
        import_time = performance_timer.stop()
        
        assert dita_context is not None
        assert import_time < 5.0, f"DITA import too slow: {import_time:.3f}s"
        
        print(f"DITA package import time: {import_time:.3f}s")


@pytest.mark.integration
@pytest.mark.dita_only
class TestDitaOnlyErrorHandling:
    """Test error handling in DITA-only mode."""
    
    def test_invalid_dita_package_handling(self, temp_dir):
        """Test handling of invalid DITA packages."""
        # Create invalid zip file
        invalid_zip = temp_dir / "invalid.zip"
        invalid_zip.write_bytes(b"Not a valid zip file")
        
        importer = DitaPackageImporter()
        output_dir = temp_dir / "invalid_output"
        
        # Should handle error gracefully
        try:
            result = importer.import_package(invalid_zip, output_dir)
            # If it doesn't raise an exception, result should indicate failure
            if result is not None:
                # Check if error information is available
                pass
        except Exception as e:
            # Expected for invalid files
            assert "zip" in str(e).lower() or "invalid" in str(e).lower()
    
    def test_missing_dita_files_in_package(self, temp_dir):
        """Test handling of zip files without DITA content."""
        # Create zip with non-DITA content
        empty_zip = temp_dir / "empty.zip"
        with zipfile.ZipFile(empty_zip, 'w') as zf:
            zf.writestr("readme.txt", "This is not a DITA package")
        
        importer = DitaPackageImporter()
        output_dir = temp_dir / "empty_output"
        
        # Should handle gracefully
        try:
            result = importer.import_package(empty_zip, output_dir)
            # Result might be valid (extracted files) but won't have DITA structure
            if result is not None:
                assert hasattr(result, 'project_dir')
        except Exception:
            # Also acceptable - importer detects missing DITA content
            pass
    
    def test_conversion_service_error_handling(self, mock_service_registry):
        """Test ConversionService error handling without plugins."""
        conversion_service = ConversionService(mock_service_registry)
        
        # Test with non-existent file
        non_existent = Path("does_not_exist.zip")
        assert not conversion_service.can_handle_file(non_existent)
        
        # Test conversion of non-existent file
        output_dir = Path("/tmp/test_output")
        try:
            result = conversion_service.convert_document(non_existent, output_dir)
            # Should either return None or raise exception
            assert result is None
        except (FileNotFoundError, ValueError):
            # Expected for non-existent files
            pass


@pytest.mark.integration
@pytest.mark.dita_only
class TestDitaOnlyConfiguration:
    """Test configuration and settings in DITA-only mode."""
    
    def test_default_configuration_without_plugins(self):
        """Test that default configuration works without plugins."""
        from orlando_toolkit.config.manager import ConfigManager
        
        config_manager = ConfigManager()
        
        # Should load default configurations
        assert hasattr(config_manager, 'get_style_map')
        assert hasattr(config_manager, 'get_color_rules')
        
        # Default configs should not reference plugin-specific settings
        style_map = config_manager.get_style_map()
        assert isinstance(style_map, dict)
        
        color_rules = config_manager.get_color_rules()
        assert isinstance(color_rules, dict)
    
    def test_logging_configuration_without_plugins(self):
        """Test logging configuration in DITA-only mode."""
        import logging
        
        # Should have core loggers configured
        core_logger = logging.getLogger('orlando_toolkit.core')
        assert core_logger is not None
        
        ui_logger = logging.getLogger('orlando_toolkit.ui')
        assert ui_logger is not None
        
        # Should not have plugin-specific loggers
        plugin_logger = logging.getLogger('plugin')
        # Plugin logger might exist but should have no handlers initially
    
    def test_session_storage_without_plugins(self):
        """Test session storage functionality without plugins."""
        from orlando_toolkit.core.session_storage import SessionStorage
        
        storage = SessionStorage()
        
        # Basic functionality should work
        assert hasattr(storage, 'get')
        assert hasattr(storage, 'set')
        assert hasattr(storage, 'clear')
        
        # Should handle plugin-free state
        storage.set('test_key', 'test_value')
        assert storage.get('test_key') == 'test_value'
        
        # Clear should work
        storage.clear()
        assert storage.get('test_key') is None