"""Simple test plugin for integration testing."""

from pathlib import Path
from typing import List, Dict, Any, Optional
from unittest.mock import Mock

from orlando_toolkit.core.plugins.base import BasePlugin
from orlando_toolkit.core.plugins.interfaces import DocumentHandler, ProgressCallback
from orlando_toolkit.core.models import DitaContext


class SimpleDocumentHandler(DocumentHandler):
    """Simple document handler for testing."""
    
    def can_handle(self, file_path: Path) -> bool:
        """Check if this handler can process the given file."""
        return file_path.suffix.lower() == '.simple'
    
    def get_supported_extensions(self) -> List[str]:
        """Get list of file extensions this handler supports."""
        return ['.simple']
    
    def convert_to_dita(self, file_path: Path, metadata: Dict[str, Any], 
                       progress_callback: Optional[ProgressCallback] = None) -> DitaContext:
        """Convert document to DITA format."""
        if progress_callback:
            progress_callback("Converting simple test file...")
            
        # Create mock DITA context for testing
        context = Mock(spec=DitaContext)
        context.topics = {}
        context.images = {}
        context.metadata = {
            'source_file': str(file_path),
            'conversion_type': 'simple-test',
            'plugin': 'simple-test-plugin',
            **metadata
        }
        context.ditamap_root = Mock()
        return context
    
    def get_name(self) -> str:
        """Get human-readable handler name."""
        return "Simple Test Document Handler"
    
    def get_description(self) -> str:
        """Get handler description."""
        return "Test document handler for .simple files"


class SimpleTestPlugin(BasePlugin):
    """Simple test plugin implementation."""
    
    def get_name(self) -> str:
        """Get plugin display name."""
        return "Simple Test Plugin"
    
    def get_description(self) -> str:
        """Get plugin description."""
        return "A simple plugin for integration testing"
    
    def on_activate(self) -> None:
        """Register plugin services when activated."""
        super().on_activate()
        
        # Register document handler
        handler = SimpleDocumentHandler()
        self.app_context.service_registry.register_document_handler(
            handler, self.plugin_id
        )
        
        self.log_info("Simple test plugin activated successfully")
    
    def on_deactivate(self) -> None:
        """Cleanup plugin services when deactivated."""
        super().on_deactivate()
        
        # Unregister document handler
        self.app_context.service_registry.unregister_document_handler(
            self.plugin_id
        )
        
        self.log_info("Simple test plugin deactivated")