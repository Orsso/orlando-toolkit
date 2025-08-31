# Plugin Development Guide

Develop plugins to extend Orlando Toolkit's format conversion capabilities.

## Overview

Plugins enable document conversion from external formats (DOCX, PDF, Markdown) to DITA:
- Implement `DocumentHandler` interface for conversion logic
- Register UI extensions for format-specific features  
- Automatic lifecycle management and error isolation

## Plugin Architecture

```
Core Components:
├── Plugin Manager    # Discovery and lifecycle
├── Service Registry  # DocumentHandler registration  
├── UI Registry      # UI component management

Plugin Implementation:
├── BasePlugin       # Lifecycle hooks
├── DocumentHandler  # Format conversion
├── UI Extensions    # Optional UI components
└── plugin.json      # Manifest
```

## Quick Start

**Requirements:** Python 3.8+, Orlando Toolkit

**Steps:**
1. Create plugin directory with `plugin.json` manifest
2. Implement `BasePlugin` and `DocumentHandler` interfaces
3. Test with Orlando Toolkit

### Plugin Structure

```
your-plugin/
├── plugin.json              # Plugin manifest (required)
├── plugin-icon.png          # Plugin icon (recommended)
├── requirements.txt         # Plugin dependencies
├── README.md                # Plugin documentation
├── src/                     # Plugin source code
│   ├── __init__.py
│   ├── plugin.py            # Main plugin class
│   ├── services/            # DocumentHandler implementation
│   │   └── handler.py
│   ├── ui/                  # UI components (optional)
│   │   └── panels.py
│   └── utils/               # Utilities and helpers
├── tests/                   # Plugin tests
│   ├── test_plugin.py
│   └── test_handler.py
└── config/                  # Configuration templates (optional)
    └── default_config.yml
```

### Plugin Icon

**Image Requirements:**
- **File name**: `plugin-icon.png` (required name)
- **Location**: Root directory of plugin repository  
- **Size**: 128x128 pixels recommended
- **Format**: PNG with transparent background preferred
- **Max size**: 50KB for fast loading
- **Fallback**: Package emoji 📦 if missing

**Design Guidelines:**
- Use clear, recognizable symbols related to your format
- Avoid text in icons (use symbols/graphics instead)
- Ensure visibility on light and dark backgrounds
- Test icon appearance at small sizes (32x32px minimum)

**Example:** DOCX plugin might use a document icon, PDF plugin a page icon, etc.

## Plugin Manifest

### plugin.json Schema

Every plugin requires a `plugin.json` manifest file:

```json
{
  "name": "my-converter",
  "version": "1.0.0",
  "display_name": "My Format Converter",
  "description": "Convert My Format files to DITA",
  "author": "Your Name",
  "homepage": "https://github.com/yourorg/orlando-my-plugin",
  
  "orlando_version": ">=2.0.0",
  "plugin_api_version": "1.0",
  "category": "pipeline",
  
  "entry_point": "src.plugin.MyConverterPlugin",
  
  "supported_formats": [
    {
      "extension": ".myformat",
      "mime_type": "application/x-myformat",
      "description": "My Format Document"
    }
  ],
  
  "dependencies": {
    "python": ">=3.8",
    "packages": [
      "my-parser-lib>=1.0.0",
      "additional-dep>=2.0.0"
    ]
  },
  
  "provides": {
    "services": ["DocumentHandler"],
    "ui_extensions": ["MyFormatPanel"],
    "marker_providers": ["MyFormatMarkers"]
  },
  
  "ui": {
    "splash_button": {
      "text": "Import from\\nMy Format",
      "icon": "myformat-icon.png",
      "tooltip": "Convert My Format documents to DITA"
    }
  }
}
```

### Manifest Fields Reference

**Required Fields:**
- `name`: Unique plugin identifier (lowercase, hyphens allowed)
- `version`: Semantic version (major.minor.patch)
- `display_name`: Human-readable plugin name
- `description`: Brief functionality description
- `orlando_version`: Compatible Orlando Toolkit version
- `plugin_api_version`: Plugin API version
- `category`: Plugin category ("pipeline" for converters)
- `entry_point`: Python path to plugin class

**Optional Fields:**
- `author`: Plugin author name
- `homepage`: Plugin homepage URL
- `supported_formats`: List of file formats handled
- `dependencies`: Python and package requirements
- `provides`: Services and components provided
- `ui`: UI integration configuration

## Plugin Implementation

### Base Plugin Class

All plugins must inherit from `BasePlugin`:

```python
from orlando_toolkit.core.plugins.base import BasePlugin, AppContext
from orlando_toolkit.core.plugins.interfaces import DocumentHandlerBase

class MyConverterPlugin(BasePlugin):
    """My format converter plugin."""
    
    def __init__(self, plugin_id: str, metadata: 'PluginMetadata', plugin_dir: str):
        super().__init__(plugin_id, metadata, plugin_dir)
        self._document_handler = None
    
    def get_name(self) -> str:
        """Get human-readable plugin name."""
        return "My Format Converter"
    
    def get_description(self) -> str:
        """Get plugin description."""
        return "Convert My Format documents to DITA with structure analysis"
    
    def on_activate(self) -> None:
        """Called when plugin services should be registered."""
        super().on_activate()
        
        # Create and register document handler
        from .services.handler import MyFormatDocumentHandler
        self._document_handler = MyFormatDocumentHandler()
        
        if self.app_context and hasattr(self.app_context, 'service_registry'):
            self.app_context.service_registry.register_service(
                'DocumentHandler', self._document_handler, self.plugin_id
            )
            self.log_info("Registered My Format DocumentHandler")
    
    def on_deactivate(self) -> None:
        """Called when plugin should cleanup resources."""
        super().on_deactivate()
        
        if self.app_context and self._document_handler:
            self.app_context.service_registry.unregister_service(
                'DocumentHandler', self.plugin_id
            )
            self._document_handler = None
            self.log_info("Unregistered My Format DocumentHandler")
```

### Lifecycle Hooks

**Plugin Lifecycle:**
1. **Discovery**: Plugin found and manifest validated
2. **Loading**: Plugin class instantiated
3. **on_load()**: Called with application context
4. **on_activate()**: Services registered
5. **Active**: Plugin ready for use
6. **on_deactivate()**: Services unregistered  
7. **on_unload()**: Final cleanup

**Hook Implementation:**

```python
def on_load(self, app_context: AppContext) -> None:
    """Initialize plugin with application context."""
    super().on_load(app_context)
    # Perform initialization requiring app context
    self.log_info(f"Plugin loaded: {self.get_name()}")

def on_activate(self) -> None:
    """Register services and UI components."""
    super().on_activate()
    # Register DocumentHandlers, UI components
    self.log_info("Plugin activated")

def on_deactivate(self) -> None:
    """Unregister services and cleanup resources."""
    super().on_deactivate()
    # Unregister services, cleanup resources
    self.log_info("Plugin deactivated")

def on_unload(self) -> None:
    """Final cleanup before plugin removal."""
    super().on_unload()
    # Final cleanup for garbage collection
    self.log_info("Plugin unloaded")
```

## DocumentHandler Interface

### Interface Definition

The `DocumentHandler` protocol defines the core conversion interface:

```python
from orlando_toolkit.core.plugins.interfaces import DocumentHandlerBase
from orlando_toolkit.core.models import DitaContext
from pathlib import Path
from typing import Dict, List, Any

class MyFormatDocumentHandler(DocumentHandlerBase):
    """Document handler for My Format files."""
    
    def can_handle(self, file_path: Path) -> bool:
        """Return True if this handler can process the file."""
        return file_path.suffix.lower() in ['.myformat', '.myf']
    
    def convert_to_dita(self, file_path: Path, metadata: Dict[str, Any]) -> DitaContext:
        """Convert file to DitaContext."""
        self.validate_file_exists(file_path)
        
        try:
            # Parse source document
            document = self._parse_document(file_path)
            
            # Extract structure and content
            topics = self._extract_topics(document)
            images = self._extract_images(document, file_path.parent)
            
            # Build DITA context
            context = self._build_dita_context(topics, images, metadata)
            
            self.log_info(f"Converted {file_path.name}: {len(topics)} topics, {len(images)} images")
            return context
            
        except Exception as e:
            self.log_error(f"Conversion failed: {e}")
            raise
    
    def get_supported_extensions(self) -> List[str]:
        """Return list of supported file extensions."""
        return ['.myformat', '.myf']
    
    def get_conversion_metadata_schema(self) -> Dict[str, Any]:
        """Return JSON schema for conversion metadata."""
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Document title"},
                "author": {"type": "string", "description": "Document author"},
                "extract_images": {"type": "boolean", "default": True},
                "heading_levels": {"type": "integer", "minimum": 1, "maximum": 6, "default": 6}
            }
        }
```

### Implementation Guidelines

**File Validation:**
- Always call `self.validate_file_exists(file_path)` first
- Check file format validity beyond just extension
- Handle corrupted or invalid files gracefully

**Error Handling:**
- Use descriptive error messages
- Log errors with `self.log_error()`
- Raise appropriate exceptions for different failure types
- Don't suppress exceptions - let the plugin system handle them

**Performance:**
- `can_handle()` should be fast (file extension check)
- Use lazy loading for expensive operations
- Consider memory usage for large documents
- Implement progress reporting for long operations

**DITA Context Creation:**
- Follow DITA standards for topic structure
- Generate valid DITAMAP with proper hierarchy
- Handle image references correctly
- Include all necessary metadata

### Conversion Implementation Example

```python
def _parse_document(self, file_path: Path) -> 'MyFormatDocument':
    """Parse My Format document."""
    import my_format_parser
    
    try:
        with open(file_path, 'rb') as f:
            document = my_format_parser.parse(f)
        return document
    except Exception as e:
        raise ValueError(f"Failed to parse {file_path.name}: {e}")

def _extract_topics(self, document: 'MyFormatDocument') -> List['Topic']:
    """Extract topics from parsed document."""
    topics = []
    
    # Analyze document structure
    for section in document.sections:
        topic = self._create_topic(section)
        topics.append(topic)
    
    return topics

def _build_dita_context(self, topics: List['Topic'], images: List['Image'], 
                       metadata: Dict[str, Any]) -> DitaContext:
    """Build DITA context from extracted content."""
    from orlando_toolkit.core.models import DitaContext, Topic, TopicRef
    
    # Create DITA topics
    dita_topics = []
    for topic in topics:
        dita_topic = Topic(
            id=topic.id,
            title=topic.title,
            content=topic.content,
            topic_type="concept"  # or "task", "reference"
        )
        dita_topics.append(dita_topic)
    
    # Create topic references for DITAMAP
    topic_refs = [TopicRef(href=f"{topic.id}.dita") for topic in dita_topics]
    
    # Build DITA context
    context = DitaContext(
        title=metadata.get('title', 'Converted Document'),
        topics=dita_topics,
        topic_refs=topic_refs,
        images=images,
        metadata=metadata
    )
    
    return context
```

## UI Extensions

### Panel Factory System

Create UI panels that integrate with the right panel system:

```python
from orlando_toolkit.core.plugins.ui_registry import PanelFactory
import tkinter as tk
from tkinter import ttk

class MyFormatPanelFactory:
    """Factory for creating My Format UI panels."""
    
    def create_panel(self, parent: tk.Widget, context: Any) -> tk.Widget:
        """Create and return a panel instance."""
        return MyFormatPanel(parent, context)
    
    def get_panel_type(self) -> str:
        """Return unique identifier for this panel type."""
        return "myformat_analysis"
    
    def get_display_name(self) -> str:
        """Return human-readable display name."""
        return "My Format Analysis"
    
    def cleanup_panel(self, panel: tk.Widget) -> None:
        """Clean up resources when panel is no longer needed."""
        if hasattr(panel, 'cleanup'):
            panel.cleanup()

class MyFormatPanel(ttk.Frame):
    """Analysis panel for My Format documents."""
    
    def __init__(self, parent: tk.Widget, context: Any):
        super().__init__(parent)
        self.context = context
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup panel UI components."""
        ttk.Label(self, text="My Format Analysis").pack(pady=5)
        
        # Add your UI components here
        self.analysis_text = tk.Text(self, height=10, wrap=tk.WORD)
        self.analysis_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Control buttons
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(button_frame, text="Analyze", command=self.perform_analysis).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Clear", command=self.clear_analysis).pack(side=tk.LEFT, padx=5)
    
    def perform_analysis(self):
        """Perform document analysis."""
        # Implement your analysis logic
        results = "Analysis results will appear here..."
        self.analysis_text.delete(1.0, tk.END)
        self.analysis_text.insert(tk.END, results)
    
    def clear_analysis(self):
        """Clear analysis results."""
        self.analysis_text.delete(1.0, tk.END)
    
    def cleanup(self):
        """Cleanup resources."""
        # Cleanup any resources used by the panel
        pass
```

### Marker Provider System

Create custom markers for the scrollbar marker system:

```python
from orlando_toolkit.core.plugins.marker_providers import MarkerProviderBase
from typing import Dict, Any

class MyFormatMarkerProvider(MarkerProviderBase):
    """Marker provider for My Format-specific markers."""
    
    def __init__(self):
        super().__init__(
            marker_type_id="myformat_markers",
            display_name="My Format Markers",
            priority=320  # Plugin marker priority
        )
        self._marker_config = {}
    
    def should_show_marker(self, item_data: Dict[str, Any]) -> bool:
        """Return True if marker should be shown for this item."""
        if not self._enabled:
            return False
        
        # Check if item has My Format-specific attributes
        format_info = item_data.get('format_info')
        if not format_info:
            return False
        
        # Show marker for items with specific characteristics
        return format_info.get('needs_attention', False)
    
    def get_marker_color(self, item_data: Dict[str, Any]) -> str:
        """Return hex color for this item's marker."""
        format_info = item_data.get('format_info', {})
        severity = format_info.get('severity', 'info')
        
        color_map = {
            'error': '#FF1744',    # Red
            'warning': '#FF9100',  # Orange
            'info': '#2196F3',     # Blue
        }
        
        return color_map.get(severity, '#808080')  # Default gray
```

### UI Registration

Register UI components in your plugin's activation method:

```python
def on_activate(self) -> None:
    """Register services and UI components."""
    super().on_activate()
    
    # Register DocumentHandler
    self._document_handler = MyFormatDocumentHandler()
    self.app_context.service_registry.register_service(
        'DocumentHandler', self._document_handler, self.plugin_id
    )
    
    # Register UI extensions if UI registry is available
    if hasattr(self.app_context, 'ui_registry'):
        try:
            # Register panel factory
            panel_factory = MyFormatPanelFactory()
            self.app_context.ui_registry.register_panel_factory(
                self.plugin_id, panel_factory
            )
            
            # Register marker provider
            marker_provider = MyFormatMarkerProvider()
            self.app_context.ui_registry.register_marker_provider(
                self.plugin_id, marker_provider
            )
            
            self.log_info("Registered UI extensions")
            
        except Exception as e:
            self.log_warning(f"Failed to register UI extensions: {e}")
```

## Testing

### Unit Testing

Create comprehensive tests for your plugin:

```python
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.services.handler import MyFormatDocumentHandler
from orlando_toolkit.core.models import DitaContext

class TestMyFormatDocumentHandler(unittest.TestCase):
    """Test cases for My Format document handler."""
    
    def setUp(self):
        self.handler = MyFormatDocumentHandler()
    
    def test_can_handle_supported_extensions(self):
        """Test file extension detection."""
        self.assertTrue(self.handler.can_handle(Path("test.myformat")))
        self.assertTrue(self.handler.can_handle(Path("test.myf")))
        self.assertFalse(self.handler.can_handle(Path("test.docx")))
        self.assertFalse(self.handler.can_handle(Path("test.txt")))
    
    def test_get_supported_extensions(self):
        """Test supported extensions list."""
        extensions = self.handler.get_supported_extensions()
        self.assertIn('.myformat', extensions)
        self.assertIn('.myf', extensions)
    
    @patch('src.services.handler.my_format_parser')
    def test_convert_to_dita_success(self, mock_parser):
        """Test successful document conversion."""
        # Setup mock
        mock_document = Mock()
        mock_parser.parse.return_value = mock_document
        
        # Test conversion
        test_file = Path("test_files/sample.myformat")
        metadata = {"title": "Test Document"}
        
        with patch.object(self.handler, 'validate_file_exists'):
            with patch.object(self.handler, '_parse_document', return_value=mock_document):
                with patch.object(self.handler, '_extract_topics', return_value=[]):
                    with patch.object(self.handler, '_extract_images', return_value=[]):
                        with patch.object(self.handler, '_build_dita_context') as mock_build:
                            mock_context = Mock(spec=DitaContext)
                            mock_build.return_value = mock_context
                            
                            result = self.handler.convert_to_dita(test_file, metadata)
                            
                            self.assertEqual(result, mock_context)
                            mock_build.assert_called_once()
    
    def test_conversion_metadata_schema(self):
        """Test metadata schema definition."""
        schema = self.handler.get_conversion_metadata_schema()
        
        self.assertIn("type", schema)
        self.assertEqual(schema["type"], "object")
        self.assertIn("properties", schema)
        
        properties = schema["properties"]
        self.assertIn("title", properties)
        self.assertIn("author", properties)

if __name__ == '__main__':
    unittest.main()
```

### Integration Testing

Test plugin integration with Orlando Toolkit:

```python
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from src.plugin import MyConverterPlugin
from orlando_toolkit.core.plugins.metadata import PluginMetadata
from orlando_toolkit.core.plugins.base import AppContext

class TestMyConverterPluginIntegration(unittest.TestCase):
    """Integration tests for My Converter plugin."""
    
    def setUp(self):
        # Create mock metadata
        self.metadata = Mock(spec=PluginMetadata)
        self.metadata.name = "my-converter"
        self.metadata.version = "1.0.0"
        
        # Create plugin instance
        self.plugin = MyConverterPlugin(
            plugin_id="my-converter",
            metadata=self.metadata,
            plugin_dir="/path/to/plugin"
        )
    
    def test_plugin_lifecycle(self):
        """Test complete plugin lifecycle."""
        # Mock app context
        mock_service_registry = Mock()
        app_context = Mock(spec=AppContext)
        app_context.service_registry = mock_service_registry
        
        # Test loading
        self.plugin.on_load(app_context)
        self.assertEqual(self.plugin.app_context, app_context)
        
        # Test activation
        self.plugin.on_activate()
        mock_service_registry.register_service.assert_called_once()
        
        # Test deactivation
        self.plugin.on_deactivate()
        mock_service_registry.unregister_service.assert_called_once()
        
        # Test unloading
        self.plugin.on_unload()
    
    def test_service_registration(self):
        """Test service registration process."""
        mock_service_registry = Mock()
        app_context = Mock(spec=AppContext)
        app_context.service_registry = mock_service_registry
        
        self.plugin.on_load(app_context)
        self.plugin.on_activate()
        
        # Verify DocumentHandler registration
        mock_service_registry.register_service.assert_called_with(
            'DocumentHandler', unittest.mock.ANY, 'my-converter'
        )
```

### Test Data

Create test files for comprehensive testing:

```
tests/
├── test_plugin.py
├── test_handler.py
├── fixtures/
│   ├── sample.myformat           # Valid test document
│   ├── corrupted.myformat        # Corrupted file for error testing
│   ├── empty.myformat           # Empty file test case
│   └── complex.myformat         # Complex document with images
└── expected_results/
    ├── sample_topics.json       # Expected topic extraction results
    └── sample_dita_context.json # Expected DITA context
```

## Best Practices

### Error Handling

**Graceful Degradation:**
- Handle missing dependencies gracefully
- Provide fallback behavior when possible
- Use specific exception types for different error cases
- Log errors with sufficient context for debugging

```python
try:
    import optional_dependency
    OPTIONAL_FEATURE_AVAILABLE = True
except ImportError:
    OPTIONAL_FEATURE_AVAILABLE = False
    logger.warning("Optional dependency not available, advanced features disabled")

def enhanced_conversion(self, file_path: Path) -> DitaContext:
    """Conversion with optional enhancements."""
    try:
        if OPTIONAL_FEATURE_AVAILABLE:
            return self._enhanced_convert(file_path)
        else:
            return self._basic_convert(file_path)
    except Exception as e:
        self.log_error(f"Conversion failed: {e}")
        raise
```

### Performance Optimization

**Memory Management:**
- Process large documents in chunks
- Use generators for large data sets
- Clean up resources properly
- Monitor memory usage during development

**Lazy Loading:**
- Load expensive resources only when needed
- Cache computation results where appropriate
- Use efficient data structures

```python
def __init__(self):
    super().__init__()
    self._parser = None  # Lazy initialization
    self._cache = {}     # Result cache

@property
def parser(self):
    """Lazy-loaded parser instance."""
    if self._parser is None:
        self._parser = self._create_parser()
    return self._parser

def get_document_info(self, file_path: Path) -> Dict[str, Any]:
    """Get document info with caching."""
    cache_key = str(file_path)
    
    if cache_key not in self._cache:
        self._cache[cache_key] = self._analyze_document(file_path)
    
    return self._cache[cache_key]
```

### Security Considerations

**File Handling:**
- Validate file paths and prevent directory traversal
- Check file sizes to prevent resource exhaustion
- Sanitize file contents before processing
- Use temporary directories for intermediate files

**Dependency Management:**
- Pin dependency versions for reproducible builds
- Use virtual environments for isolation
- Audit dependencies for security vulnerabilities
- Minimize external dependencies where possible

### Code Organization

**Modular Design:**
- Separate concerns into focused modules
- Use dependency injection for testability
- Follow SOLID principles
- Keep interfaces simple and focused

**Documentation:**
- Document all public interfaces
- Provide usage examples
- Include troubleshooting guides
- Keep documentation up to date with code changes

## Deployment

### Plugin Packaging

**Directory Structure:**
```
my-converter-plugin/
├── plugin.json
├── README.md
├── requirements.txt
├── src/
└── tests/
```

**Installation Methods:**
1. **GitHub Repository Import**: Primary distribution method via Plugin Management window
2. **Local Development**: Install from directory for testing and development
3. **Package Installation**: Future support for pip/package managers

### Distribution

**Plugin Repository Distribution:**
- Host plugin as standalone GitHub repository
- Structure repository with `plugin.json`, `requirements.txt`, and complete source code
- Include comprehensive README with installation instructions
- Tag releases with semantic versioning for update management
- Users install via GitHub repository URL in Plugin Management window

**Repository Structure:**
```
https://github.com/organization/orlando-my-plugin/
├── plugin.json           # Plugin manifest
├── requirements.txt      # Dependencies  
├── README.md            # Installation and usage docs
├── src/                 # Plugin source code
└── tests/               # Plugin tests
```

**Plugin Distribution Workflow:**
1. Developer creates standalone GitHub repository
2. Repository contains complete plugin package
3. Users discover plugin via documentation or community
4. Users import via GitHub URL in Orlando Toolkit Plugin Management
5. Plugin Manager downloads, installs, and activates plugin automatically

### Version Management

**Semantic Versioning:**
- MAJOR: Breaking changes to plugin API
- MINOR: New features, backward compatible
- PATCH: Bug fixes, backward compatible

**Compatibility:**
- Test with multiple Orlando Toolkit versions
- Specify version requirements in plugin.json
- Handle API changes gracefully
- Provide migration guides for breaking changes

## API Reference

### Core Interfaces

**BasePlugin Methods:**
- `get_name() -> str`: Human-readable plugin name
- `get_description() -> str`: Plugin functionality description
- `on_load(app_context)`: Initialize with application context
- `on_activate()`: Register services and components
- `on_deactivate()`: Unregister services and cleanup
- `on_unload()`: Final cleanup before removal

**DocumentHandler Protocol:**
- `can_handle(file_path) -> bool`: File format detection
- `convert_to_dita(file_path, metadata) -> DitaContext`: Main conversion
- `get_supported_extensions() -> List[str]`: Supported file extensions
- `get_conversion_metadata_schema() -> Dict`: Metadata schema

**UI Extension Points:**
- `PanelFactory`: Create UI panels for right panel system
- `MarkerProvider`: Provide scrollbar markers for visualization
- `UIRegistry`: Register and manage UI components

### Data Models

**FileFormat:**
- `extension: str`: File extension with dot
- `mime_type: str`: MIME type identifier
- `description: str`: Human-readable format name
- `plugin_id: str`: Plugin that handles this format

**DitaContext:**
- `title: str`: Document title
- `topics: List[Topic]`: DITA topics
- `topic_refs: List[TopicRef]`: DITAMAP topic references
- `images: List[Image]`: Document images
- `metadata: Dict[str, Any]`: Additional metadata

## Example: Complete Plugin Implementation

Here's a complete minimal plugin implementation:

**plugin.json:**
```json
{
  "name": "simple-txt-converter",
  "version": "1.0.0",
  "display_name": "Simple Text Converter",
  "description": "Convert plain text files to DITA",
  "orlando_version": ">=2.0.0",
  "plugin_api_version": "1.0",
  "category": "pipeline",
  "entry_point": "src.plugin.SimpleTextConverterPlugin",
  "supported_formats": [
    {
      "extension": ".txt",
      "mime_type": "text/plain",
      "description": "Plain Text File"
    }
  ]
}
```

**src/plugin.py:**
```python
from orlando_toolkit.core.plugins.base import BasePlugin
from .services.handler import TextDocumentHandler

class SimpleTextConverterPlugin(BasePlugin):
    def __init__(self, plugin_id: str, metadata, plugin_dir: str):
        super().__init__(plugin_id, metadata, plugin_dir)
        self._document_handler = None
    
    def get_name(self) -> str:
        return "Simple Text Converter"
    
    def get_description(self) -> str:
        return "Convert plain text files to DITA topics"
    
    def on_activate(self) -> None:
        super().on_activate()
        self._document_handler = TextDocumentHandler()
        
        if self.app_context:
            self.app_context.service_registry.register_service(
                'DocumentHandler', self._document_handler, self.plugin_id
            )
    
    def on_deactivate(self) -> None:
        super().on_deactivate()
        
        if self.app_context and self._document_handler:
            self.app_context.service_registry.unregister_service(
                'DocumentHandler', self.plugin_id
            )
            self._document_handler = None
```

**src/services/handler.py:**
```python
from orlando_toolkit.core.plugins.interfaces import DocumentHandlerBase
from orlando_toolkit.core.models import DitaContext, Topic, TopicRef
from pathlib import Path
from typing import Dict, List, Any

class TextDocumentHandler(DocumentHandlerBase):
    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == '.txt'
    
    def convert_to_dita(self, file_path: Path, metadata: Dict[str, Any]) -> DitaContext:
        self.validate_file_exists(file_path)
        
        # Read text file
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Create single topic
        topic = Topic(
            id=file_path.stem,
            title=metadata.get('title', file_path.stem),
            content=f"<p>{content}</p>",
            topic_type="concept"
        )
        
        topic_ref = TopicRef(href=f"{topic.id}.dita")
        
        return DitaContext(
            title=topic.title,
            topics=[topic],
            topic_refs=[topic_ref],
            images=[],
            metadata=metadata
        )
    
    def get_supported_extensions(self) -> List[str]:
        return ['.txt']
    
    def get_conversion_metadata_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Document title"}
            }
        }
```

This example demonstrates a complete, functional plugin that converts plain text files to DITA format.

## Troubleshooting

### Common Issues

**Plugin Not Loading:**
- Verify plugin.json syntax and required fields
- Check Python path in entry_point
- Ensure all dependencies are installed
- Review Orlando Toolkit logs for error messages

**Service Registration Errors:**
- Verify app_context is available in activation
- Check service registry method signatures
- Ensure unique service registration keys
- Handle registration errors gracefully

**UI Extension Issues:**
- Verify UI registry availability
- Check panel factory implementation
- Test UI components independently
- Handle missing UI dependencies

**Conversion Failures:**
- Validate input files thoroughly
- Check for missing dependencies
- Handle edge cases and error conditions
- Provide informative error messages

### Debugging Techniques

**Logging:**
- Use plugin logger: `self.log_info()`, `self.log_error()`
- Enable debug logging in Orlando Toolkit
- Add detailed logging to conversion logic
- Log plugin lifecycle events

**Testing:**
- Create comprehensive unit tests
- Test with variety of input files
- Mock external dependencies
- Test error conditions and edge cases

**Development Tools:**
- Use Python debugger for step-through debugging
- Profile plugin performance with large files
- Monitor memory usage during conversion
- Use static analysis tools (pylint, mypy)

## Related Documentation

- **Main Application**: [Orlando Toolkit README](../README.md) - Application overview and getting started
- **DOCX Plugin**: [orlando-docx-plugin](https://github.com/organization/orlando-docx-plugin) - Reference implementation example
- **Architecture Overview**: [Architecture Documentation](architecture_overview.md) - Core system architecture
- **Runtime Flow**: [Runtime Flow](runtime_flow.md) - Application execution flow
- **Configuration**: [Configuration Guide](../orlando_toolkit/config/README.md) - System configuration

## Quick Reference

- **Plugin Template**: Use the complete example in this guide as a starting template
- **DOCX Plugin**: Study [orlando-docx-plugin](https://github.com/organization/orlando-docx-plugin) as a reference implementation
- **Test Examples**: See `tests/fixtures/plugins/` for testing patterns
- **Core Interfaces**: Located in `orlando_toolkit/core/plugins/interfaces.py`
- **Plugin Base**: Inherit from `orlando_toolkit/core/plugins/base.BasePlugin`

This comprehensive guide covers all aspects of plugin development for Orlando Toolkit. Use the DOCX plugin as a reference implementation and follow the patterns established in the core plugin system.