"""Test configuration and fixtures for Orlando Toolkit plugin system tests.

This module provides shared test fixtures, mock objects, and configuration
for integration testing of the plugin architecture. All test files should
use the fixtures defined here for consistency.
"""

import pytest
import tempfile
import shutil
import logging
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from unittest.mock import Mock, MagicMock

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from orlando_toolkit.core.context import AppContext
from orlando_toolkit.core.plugins.registry import ServiceRegistry
from orlando_toolkit.core.plugins.manager import PluginManager
from orlando_toolkit.core.plugins.loader import PluginLoader
from orlando_toolkit.core.plugins.ui_registry import UIRegistry
from orlando_toolkit.core.plugins.base import BasePlugin, PluginState
from orlando_toolkit.core.plugins.metadata import PluginMetadata
from orlando_toolkit.core.plugins.interfaces import DocumentHandler
from orlando_toolkit.core.services import ConversionService
from orlando_toolkit.core.models import DitaContext

# Configure test logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


@pytest.fixture(scope="session")
def test_data_dir():
    """Provides path to test data directory."""
    return Path(__file__).parent / "fixtures" / "data"


@pytest.fixture(scope="session") 
def test_plugins_dir():
    """Provides path to test plugins directory."""
    return Path(__file__).parent / "fixtures" / "plugins"


@pytest.fixture
def temp_dir():
    """Creates a temporary directory for test operations."""
    temp_path = Path(tempfile.mkdtemp())
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def mock_service_registry():
    """Creates a fresh ServiceRegistry instance for testing."""
    return ServiceRegistry()


@pytest.fixture
def mock_ui_registry():
    """Creates a mock UIRegistry for testing."""
    ui_registry = Mock(spec=UIRegistry)
    ui_registry.register_right_panel_extension = Mock()
    ui_registry.unregister_right_panel_extension = Mock()
    ui_registry.register_marker_provider = Mock()
    ui_registry.unregister_marker_provider = Mock()
    ui_registry.get_registered_extensions = Mock(return_value=[])
    ui_registry.get_registered_marker_providers = Mock(return_value=[])
    return ui_registry


@pytest.fixture
def app_context(mock_service_registry, mock_ui_registry):
    """Creates an AppContext instance for testing."""
    return AppContext(
        service_registry=mock_service_registry,
        ui_registry=mock_ui_registry
    )


@pytest.fixture
def plugin_loader(temp_dir, mock_service_registry):
    """Creates a PluginLoader configured for testing."""
    plugins_dir = temp_dir / "plugins" 
    plugins_dir.mkdir()
    return PluginLoader([str(plugins_dir)])


@pytest.fixture
def plugin_manager(app_context, plugin_loader):
    """Creates a PluginManager for testing."""
    return PluginManager(app_context, plugin_loader)


@pytest.fixture
def conversion_service(mock_service_registry):
    """Creates a ConversionService with plugin support."""
    return ConversionService(mock_service_registry)


@pytest.fixture
def sample_plugin_metadata():
    """Provides sample plugin metadata for testing."""
    return PluginMetadata(
        name="test-plugin",
        version="1.0.0",
        display_name="Test Plugin",
        description="A test plugin for integration testing",
        author="Test Author",
        homepage="https://example.com/test-plugin",
        orlando_version=">=2.0.0",
        plugin_api_version="1.0",
        category="pipeline",
        entry_point="plugin.TestPlugin",
        supported_formats=[{
            "extension": ".test",
            "mime_type": "application/x-test",
            "description": "Test Format"
        }],
        dependencies={
            "python": ">=3.8",
            "packages": []
        },
        provides={
            "services": ["DocumentHandler"],
            "ui_extensions": [],
            "marker_providers": []
        }
    )


@pytest.fixture
def mock_document_handler():
    """Creates a mock DocumentHandler for testing."""
    handler = Mock(spec=DocumentHandler)
    handler.can_handle = Mock(return_value=True)
    handler.get_supported_extensions = Mock(return_value=['.test'])
    handler.convert_document = Mock(return_value=Mock(spec=DitaContext))
    handler.get_name = Mock(return_value="Test Handler")
    handler.get_description = Mock(return_value="Test document handler")
    return handler


class MockPlugin(BasePlugin):
    """Mock plugin implementation for testing."""
    
    def __init__(self, plugin_id: str, metadata: PluginMetadata, plugin_dir: str):
        super().__init__(plugin_id, metadata, plugin_dir)
        self.on_load_called = False
        self.on_activate_called = False
        self.on_deactivate_called = False
        self.on_unload_called = False
        self.document_handler = None
        
    def get_name(self) -> str:
        return self.metadata.display_name
        
    def get_description(self) -> str:
        return self.metadata.description
        
    def on_load(self, app_context):
        super().on_load(app_context)
        self.on_load_called = True
        
    def on_activate(self):
        super().on_activate()
        self.on_activate_called = True
        
        # Register a mock document handler
        if self.app_context:
            from tests.conftest import MockDocumentHandler
            self.document_handler = MockDocumentHandler()
            self.app_context.service_registry.register_document_handler(
                self.document_handler, 
                self.plugin_id
            )
            
    def on_deactivate(self):
        super().on_deactivate()
        self.on_deactivate_called = True
        
        # Unregister services
        if self.app_context and self.document_handler:
            self.app_context.service_registry.unregister_document_handler(
                self.plugin_id
            )
            
    def on_unload(self):
        super().on_unload()
        self.on_unload_called = True


class MockDocumentHandler(DocumentHandler):
    """Mock DocumentHandler implementation for testing."""
    
    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix == '.test'
        
    def get_supported_extensions(self) -> List[str]:
        return ['.test']
        
    def convert_document(self, file_path: Path, destination_dir: Path) -> DitaContext:
        # Create minimal mock DitaContext
        context = Mock(spec=DitaContext)
        context.project_dir = destination_dir
        context.topics = []
        context.maps = []
        return context
        
    def get_name(self) -> str:
        return "Mock Document Handler"
        
    def get_description(self) -> str:
        return "Mock handler for testing"


@pytest.fixture
def mock_plugin_class():
    """Provides the MockPlugin class for testing."""
    return MockPlugin


@pytest.fixture
def performance_timer():
    """Provides a simple performance timer for testing."""
    class PerformanceTimer:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            
        def start(self):
            self.start_time = time.time()
            
        def stop(self):
            self.end_time = time.time()
            return self.elapsed()
            
        def elapsed(self):
            if self.start_time is None:
                return 0.0
            end = self.end_time or time.time()
            return end - self.start_time
            
    return PerformanceTimer


@pytest.fixture
def docx_plugin_dir():
    """Provides path to the real DOCX plugin directory."""
    return Path(__file__).parent.parent / "orlando-docx-plugin"


@pytest.fixture
def sample_dita_package(test_data_dir):
    """Creates a sample DITA package for testing."""
    package_dir = test_data_dir / "sample_dita_package"
    package_dir.mkdir(parents=True, exist_ok=True)
    
    # Create sample DITA files
    topic_content = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="sample_topic">
    <title>Sample Topic</title>
    <body>
        <p>This is a sample DITA topic for testing.</p>
    </body>
</topic>'''
    
    map_content = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">
<map>
    <title>Sample Map</title>
    <topicref href="sample_topic.dita"/>
</map>'''
    
    (package_dir / "sample_topic.dita").write_text(topic_content, encoding='utf-8')
    (package_dir / "sample_map.ditamap").write_text(map_content, encoding='utf-8')
    
    # Create zip package
    import zipfile
    zip_path = test_data_dir / "sample_dita_package.zip"
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for file_path in package_dir.rglob('*'):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(package_dir))
                
    return zip_path


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset any singleton instances between tests."""
    yield
    # Clear any cached instances that might interfere with tests
    import orlando_toolkit.core.plugins.loader as loader_module
    if hasattr(loader_module, '_user_plugins_dir'):
        delattr(loader_module, '_user_plugins_dir')


# Test markers
pytest.mark.integration = pytest.mark.integration
pytest.mark.performance = pytest.mark.performance
pytest.mark.ui = pytest.mark.ui
pytest.mark.docx_plugin = pytest.mark.docx_plugin
pytest.mark.dita_only = pytest.mark.dita_only