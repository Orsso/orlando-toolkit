# Orlando Toolkit Plugin Architecture Design

**Version**: 1.0  
**Date**: 2025-01-28  
**Status**: Draft

## Executive Summary

This document defines the comprehensive technical architecture for transforming Orlando Toolkit from a monolithic DOCX-to-DITA converter into a plugin-driven DITA reader and structure editor. The design focuses on extracting the existing DOCX conversion pipeline into a plugin while establishing a robust, extensible framework for future document format support.

**Core Principle**: Maintain simplicity (KISS), avoid duplication (DRY), and implement only necessary features (YAGNI) while enabling clean plugin extensibility.

---

## 1. Current Architecture Analysis

### 1.1 Existing System Overview

The current Orlando Toolkit follows a layered architecture:

```
┌─────────────────────────────────────────┐
│ UI Layer (app.py, ui/)                  │
│ ├── OrlandoToolkit (main application)   │
│ ├── Structure/Image/Metadata Tabs       │
│ └── Widgets & Controllers               │
├─────────────────────────────────────────┤
│ Service Layer (core/services/)          │
│ ├── ConversionService                   │
│ ├── StructureEditingService             │
│ ├── PreviewService                      │
│ └── UndoService                         │
├─────────────────────────────────────────┤
│ Core Logic (core/)                      │
│ ├── Models (DitaContext, HeadingNode)   │
│ ├── Converter (DOCX-specific)           │
│ ├── Parser (DOCX utilities)             │
│ └── Generators (DITA builders)          │
├─────────────────────────────────────────┤
│ Configuration (config/)                 │
│ └── ConfigManager (YAML-based)          │
└─────────────────────────────────────────┘
```

### 1.2 DOCX-Specific Coupling Points

**High Coupling (Requires Extraction)**:
- `orlando_toolkit/core/converter/` - Entire DOCX conversion pipeline (~2000 lines)
  - `docx_to_dita.py` - Main conversion entry point
  - `structure_builder.py` - Two-pass DOCX analysis
  - `helpers.py` - DOCX-specific formatting utilities
- `orlando_toolkit/core/parser/` - DOCX document parsing
  - `docx_utils.py` - Document traversal utilities  
  - `style_analyzer.py` - DOCX style analysis
- `orlando_toolkit/ui/widgets/heading_filter_panel.py` - DOCX heading analysis UI
- `orlando_toolkit/app.py:126` - File dialog hardcoded to `.docx`
- `requirements.txt` - python-docx dependency

**Medium Coupling (Needs Abstraction)**:
- `orlando_toolkit/core/services/conversion_service.py:43` - Direct call to `convert_docx_to_dita()`
- `orlando_toolkit/app.py:148-152` - DOCX-based metadata initialization
- Configuration files referencing DOCX-specific style mappings

**Low Coupling (Format Agnostic)**:
- Structure editing services - operate on `DitaContext`
- Preview system - works with generated DITA XML
- Image handling - generic media processing
- Undo/redo system - operates on context snapshots

### 1.3 Extension Points Analysis

**Primary Extension Points** (Already Extensible):
- `RightPanelCoordinator` - Supports dynamic panel switching (preview/filter)
- Service injection in `StructureController` - Constructor accepts service instances
- `ConfigManager` - Supports plugin-specific YAML configurations

**Secondary Extension Points** (Need Enhancement):
- Tab creation in `OrlandoToolkit.setup_main_ui()` - Currently hardcoded
- File dialog filters - Format-specific extensions
- Toolbar buttons - Currently static

### 1.4 Data Flow Architecture

```
File Selection → ConversionService.convert() → DitaContext Creation
     ↓
DitaContext → StructureEditingService → UI Updates
     ↓
Export → ConversionService.prepare_package() → ZIP Generation
```

**Plugin Integration Point**: The `ConversionService.convert()` method must become format-agnostic and delegate to plugin-provided document handlers.

---

## 2. Plugin System Architecture

### 2.1 Plugin Metadata Schema

Each plugin must provide a `plugin.json` manifest file:

```json
{
  "name": "docx-converter",
  "version": "1.0.0", 
  "display_name": "DOCX Converter",
  "description": "Convert Microsoft Word documents to DITA",
  "author": "Orlando Toolkit Team",
  "homepage": "https://github.com/organization/orlando-docx-plugin",
  
  "orlando_version": ">=2.0.0",
  "plugin_api_version": "1.0",
  "category": "pipeline",
  
  "entry_point": "src.plugin.DocxConverterPlugin",
  
  "supported_formats": [
    {
      "extension": ".docx",
      "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "description": "Microsoft Word Document"
    }
  ],
  
  "dependencies": {
    "python": ">=3.8",
    "packages": [
      "python-docx>=0.8.11",
      "lxml>=4.6.0"
    ]
  },
  
  "provides": {
    "services": ["DocumentHandler", "HeadingAnalysisService"],
    "ui_extensions": ["HeadingFilterPanel"],
    "config_schemas": ["docx_conversion_settings"]
  },
  
  "creates_archive": true,
  
  "ui": {
    "splash_button": {
      "text": "Import from DOCX",
      "icon": "docx-icon.png",
      "tooltip": "Convert Microsoft Word documents to DITA"
    }
  },
  
  "permissions": [
    "file_system_read",
    "network_access"
  ]
}
```

**Design Decision**: Use JSON for plugin metadata to ensure easy parsing without YAML dependency in plugin system.

### 2.2 Plugin Scope and Purpose

**Plugin Architecture Focus**: Pipeline/Conversion plugins only

**Pipeline Plugins** (`category: "pipeline"`):
- **Purpose**: Import and convert external document formats to DITA archives
- **Creates**: New DITA projects from source documents (DOCX, PDF, Markdown, etc.)
- **Integration**: Each active pipeline plugin adds a button to the splash screen
- **Examples**: DOCX Converter, PDF Converter, Markdown Converter, Web Scraper
- **Workflow**: Source file/data → Plugin conversion → New DITA archive (.zip)
- **UI Integration**: Squared button with icon on redesigned splash screen

**Design Rationale**: Focus on pipeline plugins keeps the architecture simple while enabling the core use case of importing content from various sources into DITA format. Future enhancements for tab extension plugins are out of scope for this version.

### 2.3 Plugin Discovery and Loading

**Plugin Repository Structure** (GitHub-based):
```
orlando-docx-plugin/
├── plugin.json              # Plugin manifest
├── requirements.txt          # Plugin dependencies
├── src/
│   ├── __init__.py
│   ├── plugin.py            # Main plugin class
│   ├── services/            # Plugin services
│   │   ├── __init__.py
│   │   ├── docx_handler.py  # DocumentHandler implementation
│   │   └── heading_service.py
│   └── ui/                  # Plugin UI components
│       ├── __init__.py
│       └── heading_filter.py
├── tests/                   # Plugin tests
├── docs/                    # Plugin documentation  
└── README.md
```

**Official Plugin Registry** (Hardcoded in core):
```python
OFFICIAL_PLUGINS = {
    "docx-converter": {
        "repository": "https://github.com/organization/orlando-docx-plugin",
        "branch": "main", 
        "category": "pipeline",
        "description": "Microsoft Word (.docx) to DITA conversion",
        "icon": "docx-icon.png",
        "button_text": "Import from DOCX"
    },
    "pdf-converter": {
        "repository": "https://github.com/organization/orlando-pdf-plugin",
        "branch": "main",
        "category": "pipeline", 
        "description": "PDF to DITA conversion",
        "icon": "pdf-icon.png", 
        "button_text": "Import from PDF"
    },
    "markdown-converter": {
        "repository": "https://github.com/organization/orlando-markdown-plugin",
        "branch": "main",
        "category": "pipeline",
        "description": "Markdown files to DITA conversion", 
        "icon": "markdown-icon.png",
        "button_text": "Import from Markdown"
    }
}
```

**Plugin Loading Workflow**:
1. **Discovery**: Scan `~/.orlando_toolkit/plugins/` directory for installed plugins
2. **Validation**: Verify `plugin.json` schema and compatibility
3. **Dependency Check**: Ensure required packages are available
4. **Loading**: Import plugin entry point and instantiate
5. **Registration**: Register plugin services and UI extensions
6. **Initialization**: Call plugin initialization hooks

### 2.4 Service Interface Definitions

**Converter Plugin Interface**:
```python
class DocumentHandler(ABC):
    @abstractmethod
    def can_handle(self, file_path: Path) -> bool:
        """Return True if this handler can process the file"""
        
    @abstractmethod 
    def convert_to_dita(self, file_path: Path, metadata: Dict) -> DitaContext:
        """Convert file to DitaContext and return complete DITA archive data"""
        
    @abstractmethod
    def get_supported_extensions(self) -> List[str]:
        """Return list of supported file extensions"""
        
    @abstractmethod
    def get_conversion_metadata_schema(self) -> Dict:
        """Return JSON schema for conversion-specific metadata fields"""
```


### 2.5 Plugin Lifecycle Management

**Plugin States**:
- `DISCOVERED` - Plugin found but not loaded
- `LOADING` - Currently importing plugin modules
- `LOADED` - Plugin instantiated successfully
- `ACTIVE` - Plugin services registered and ready
- `ERROR` - Plugin failed to load or threw exception
- `DISABLED` - Plugin explicitly disabled by user

**Lifecycle Hooks**:
```python
class BasePlugin(ABC):
    def on_load(self, app_context: AppContext) -> None:
        """Called after plugin instantiation"""
        pass
    
    def on_activate(self) -> None:
        """Called when plugin services should be registered"""
        pass
        
    def on_deactivate(self) -> None:
        """Called when plugin should cleanup resources"""
        pass
        
    def on_unload(self) -> None:
        """Called before plugin removal"""
        pass
```

**Error Boundaries**: Plugin failures must never crash the main application. Each plugin runs within a try-catch boundary, and failures result in plugin deactivation with user notification.

### 2.6 Service Registration System

**Service Registry Pattern** (Pipeline Plugins Only):
```python
class ServiceRegistry:
    def register_document_handler(self, handler: DocumentHandler, plugin_id: str) -> None:
        """Register a document converter from a pipeline plugin"""
        
    def get_document_handlers(self) -> List[DocumentHandler]:
        """Get all registered document handlers"""
        
    def find_handler_for_file(self, file_path: Path) -> Optional[DocumentHandler]:
        """Find compatible handler for a specific file"""
```

**Pipeline Plugin Registration**:
```python
# DOCX Pipeline Plugin
class DocxConverterPlugin(BasePlugin):
    def on_activate(self) -> None:
        handler = DocxDocumentHandler()
        self.app_context.service_registry.register_document_handler(handler, self.plugin_id)
        
        # Register splash screen button
        button_config = {
            "text": "Import from\nDOCX",
            "icon": "docx-icon.png", 
            "tooltip": "Convert Microsoft Word documents to DITA"
        }
        self.app_context.ui_registry.register_splash_button(button_config, self.plugin_id)

# PDF Pipeline Plugin
class PdfConverterPlugin(BasePlugin):
    def on_activate(self) -> None:
        handler = PdfDocumentHandler()
        self.app_context.service_registry.register_document_handler(handler, self.plugin_id)
        
        button_config = {
            "text": "Import from\nPDF", 
            "icon": "pdf-icon.png",
            "tooltip": "Convert PDF documents to DITA"
        }
        self.app_context.ui_registry.register_splash_button(button_config, self.plugin_id)
```

**Design Rationale**: Simplified registration focused on document handlers and splash screen integration for pipeline plugins only.

---

## 3. Core Application Transformation

### 3.1 DITA-Only Core Definition

**Core Application Scope** (without plugins):
- **DITA Package Loader**: Import and open zipped DITA archives (.zip files)
- **Structure Editor**: Full tree manipulation, move/rename/delete operations
- **Preview System**: XML and HTML preview of DITA content  
- **Export System**: Generate DITA packages
- **Configuration Management**: User settings and plugin management

**Removed Functionality** (moved to plugins):
- Document format conversion (DOCX → DITA)
- Format-specific analysis (heading detection, style mapping)
- Format-specific UI components (HeadingFilterPanel)
- Format-specific configuration schemas

### 3.2 Generic Document Handler Interface

**Current Implementation**:
```python
# orlando_toolkit/core/services/conversion_service.py:43
def convert(self, docx_path: str | Path, metadata: Dict[str, Any]) -> DitaContext:
    context = convert_docx_to_dita(docx_path, dict(metadata))
    return context
```

**Plugin-Aware Implementation**:
```python
class ConversionService:
    def __init__(self, service_registry: ServiceRegistry):
        self.service_registry = service_registry
    
    def convert(self, file_path: str | Path, metadata: Dict[str, Any]) -> DitaContext:
        """Convert any supported file format to DitaContext using plugins"""
        file_path = Path(file_path)
        
        # Get all document handlers from plugins
        handlers = self.service_registry.get_services_by_type(DocumentHandler)
        
        # Find compatible handler
        for handler in handlers:
            if handler.can_handle(file_path):
                return handler.convert_to_dita(file_path, metadata)
        
        raise UnsupportedFormatError(f"No plugin can handle file: {file_path}")
    
    def get_supported_formats(self) -> List[FileFormat]:
        """Return all formats supported by loaded plugins"""
        formats = []
        handlers = self.service_registry.get_services_by_type(DocumentHandler)
        for handler in handlers:
            formats.extend(handler.get_supported_formats())
        return formats
```

**Redesigned Splash Screen Layout**:
```python
# orlando_toolkit/app.py (modified)
def create_home_screen(self) -> None:
    """Create redesigned splash screen with squared buttons and icons"""
    # Adjust window size for new layout
    self.root.geometry("800x600")
    
    # Smaller logo to accommodate more buttons
    try:
        logo_path = Path(__file__).resolve().parent.parent / "assets" / "app_icon.png"
        if logo_path.exists():
            logo_img = tk.PhotoImage(file=logo_path)
            # Scale logo to smaller size (e.g., 120px height instead of 180px)
            logo_img = logo_img.subsample(2, 2)  # Make logo smaller
            logo_lbl = ttk.Label(self.home_center, image=logo_img)
            logo_lbl.image = logo_img
            logo_lbl.pack(pady=(0, 20))
    except Exception:
        pass
    
    # Title (keep existing)
    ttk.Label(self.home_center, text="Orlando Toolkit", 
              font=("Trebuchet MS", 24, "bold"), foreground="#0098e4").pack(pady=15)
    
    # Button grid container
    button_frame = ttk.Frame(self.home_center)
    button_frame.pack(pady=20)
    
    # Core functionality button (squared)
    self.create_squared_button(
        button_frame, 
        text="Open DITA\nProject", 
        icon="dita-icon.png",
        command=self.open_dita_project,
        row=0, column=0
    )
    
    # Plugin management button (squared)
    self.create_squared_button(
        button_frame,
        text="Manage\nPlugins",
        icon="plugin-icon.png", 
        command=self.show_plugin_management,
        row=0, column=1
    )
    
    # Dynamic plugin buttons (squared, added by active pipeline plugins)
    self.create_plugin_buttons(button_frame, start_row=1)

def create_squared_button(self, parent, text, icon, command, row, column):
    """Create a squared button with icon and text"""
    button_size = 120  # Square button size
    
    # Create button frame
    btn_frame = ttk.Frame(parent)
    btn_frame.grid(row=row, column=column, padx=10, pady=10)
    
    # Try to load icon
    icon_image = None
    try:
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "icons" / icon
        if icon_path.exists():
            icon_image = tk.PhotoImage(file=icon_path)
            # Scale icon to fit in button (e.g., 48x48)
            icon_image = icon_image.subsample(2, 2)
    except Exception:
        pass
    
    # Create button with icon and text
    btn = ttk.Button(
        btn_frame,
        text=text,
        image=icon_image,
        compound="top",  # Icon above text
        command=command,
        width=15  # Character width for consistent sizing
    )
    btn.pack()
    
    # Store image reference to prevent garbage collection
    if icon_image:
        btn.image = icon_image

def create_plugin_buttons(self, parent, start_row):
    """Create squared buttons for active pipeline plugins"""
    active_plugins = self.plugin_manager.get_active_pipeline_plugins()
    
    col = 0
    row = start_row
    for plugin in active_plugins:
        if col >= 3:  # Max 3 buttons per row
            col = 0
            row += 1
            
        plugin_config = plugin.get_splash_button_config()
        self.create_squared_button(
            parent,
            text=plugin_config.get("text", "Import"),
            icon=plugin_config.get("icon", "default-plugin-icon.png"),
            command=lambda p=plugin: self.launch_plugin_workflow(p),
            row=row, column=col
        )
        col += 1
```

### 3.3 DITA File Handling

**New Core Capability**:

**DITA Package Importer**:
```python
class DitaPackageImporter:
    def import_package(self, zip_path: Path) -> DitaContext:
        """Import zipped DITA package and load all topics and resources"""
        # Extract ZIP archive to temporary directory
        # Parse .ditamap file to build structure
        # Load all referenced .dita topics
        # Import media files and build DitaContext
        pass
```

**File Format Support**:
- `.zip` files - Complete DITA packages (primary format)
- Plugin-provided formats - Via DocumentHandler interface for conversion workflows

---

## 4. UI Extension System Design

### 4.1 Extension Point Specification

**Primary Extension Points**:

1. **Right Panel Extensions** (Structure Tab):
   - Current: `preview` and `filter` panels
   - Plugin Extension: Additional panel types registered by plugins
   - Integration: `RightPanelCoordinator.set_active(kind)` where `kind` can be plugin-provided

2. **Application Tabs**:
   - Current: Structure, Images, Metadata tabs
   - Plugin Extension: Additional top-level tabs
   - Integration: Plugin-provided tab classes registered during startup

3. **Toolbar Extensions**:
   - Current: Move up/down buttons
   - Plugin Extension: Additional action buttons
   - Integration: Plugin-provided button definitions

### 4.2 Right Panel Plugin Integration

**Current RightPanelCoordinator Enhancement**:
```python
class RightPanelCoordinator:
    def __init__(self, ..., plugin_registry: PluginRegistry):
        self.plugin_registry = plugin_registry
        self._plugin_panels: Dict[str, Any] = {}
    
    def set_active(self, kind: str) -> None:
        """Enhanced to support plugin panels"""
        if kind in ["preview", "filter"]:
            # Handle built-in panels (existing logic)
            pass
        else:
            # Handle plugin-provided panels
            self._activate_plugin_panel(kind)
    
    def _activate_plugin_panel(self, kind: str) -> None:
        """Create and activate plugin-provided panel"""
        if kind not in self._plugin_panels:
            # Get panel factory from plugin registry
            factory = self.plugin_registry.get_panel_factory(kind)
            if factory:
                self._plugin_panels[kind] = factory(self._container)
        
        # Show plugin panel
        panel = self._plugin_panels[kind]
        panel.grid(row=0, column=0, sticky="nsew")
```

**Plugin Panel Registration**:
```python
class UIExtension(ABC):
    @abstractmethod
    def get_panel_factories(self) -> Dict[str, Callable]:
        """Return panel factories for right panel integration"""
        return {
            "custom_filter": self.create_custom_filter_panel,
            "analysis_view": self.create_analysis_panel
        }
```

### 4.3 Plugin Management UI

**Location**: Accessible from the splash screen via a "Manage Plugins" squared button

**Plugin Management Window Layout**:

1. **Left Panel - Available Plugins**:
   - **Official Plugins Section**: List of hardcoded official plugins (DOCX, PDF, Markdown converters)
   - **Custom Plugins Section**: User-imported plugins via GitHub repository URL
   - **Add Custom Plugin**: Input field for GitHub repository URL with "Import" button
   - Status indicators for each plugin (Not Installed, Installed, Active, Error)

2. **Right Panel - Plugin Details**:
   - Plugin name, version, description
   - Repository URL and documentation links
   - Installation status and error messages
   - Dependencies list and status
   - Install/Uninstall/Activate/Deactivate buttons

3. **Bottom Action Bar**:
   - "Close" button to return to splash screen
   - "Refresh" button to check for plugin updates

**Plugin Import Workflow**:
```python
def import_custom_plugin(self, repo_url: str) -> None:
    """Import plugin from GitHub repository URL"""
    # Validate GitHub URL format
    if not self._is_valid_github_url(repo_url):
        show_error("Invalid GitHub repository URL")
        return
    
    # Download and validate plugin
    try:
        plugin_data = self.plugin_downloader.download_from_github(repo_url)
        
        # Validate plugin.json schema
        if not self._validate_plugin_manifest(plugin_data):
            show_error("Invalid plugin manifest")
            return
            
        # Check for category = "pipeline"
        if plugin_data.get("category") != "pipeline":
            show_error("Only pipeline plugins are supported")
            return
            
        # Install plugin
        self.plugin_installer.install(plugin_data)
        self.refresh_plugin_list()
        
    except Exception as e:
        show_error(f"Failed to import plugin: {e}")
```

**Integration**: Plugin management opens as modal dialog from splash screen, blocking main application until closed.

### 4.4 Event System Design

**Plugin Communication Bus**:
```python
class EventBus:
    def subscribe(self, event_type: str, handler: Callable, plugin_id: str) -> None:
        """Subscribe to application events"""
        
    def publish(self, event: Event) -> None:
        """Publish event to subscribers"""
        
    def unsubscribe(self, plugin_id: str) -> None:
        """Remove all subscriptions for a plugin"""
```

**Event Types**:
- `document_loaded` - New DitaContext created
- `structure_changed` - Document structure modified
- `plugin_activated` - Plugin became active
- `plugin_deactivated` - Plugin was deactivated

**Design Rationale**: Event-driven architecture enables loose coupling between plugins and core application while supporting plugin coordination.

---

## 5. DOCX Plugin Extraction Specification

### 5.1 Plugin Boundary Definition

**Components Moving to DOCX Plugin**:

1. **Core Conversion Logic**:
   - `orlando_toolkit/core/converter/docx_to_dita.py` → `src/services/docx_handler.py`
   - `orlando_toolkit/core/converter/structure_builder.py` → `src/services/structure_analyzer.py`
   - `orlando_toolkit/core/converter/helpers.py` → `src/services/formatting_helpers.py`

2. **DOCX Parsing Utilities**:
   - `orlando_toolkit/core/parser/docx_utils.py` → `src/utils/docx_parser.py`
   - `orlando_toolkit/core/parser/style_analyzer.py` → `src/services/style_analyzer.py`

3. **UI Components**:
   - `orlando_toolkit/ui/widgets/heading_filter_panel.py` → `src/ui/heading_filter.py`

4. **Dependencies**:
   - `python-docx` requirement moves to plugin `requirements.txt`
   - DOCX-specific configuration schemas

**Components Remaining in Core**:
- Generic DITA generation utilities (`orlando_toolkit/core/generators/`)
- DitaContext model and utilities
- Generic service interfaces
- File I/O and packaging utilities

### 5.2 Service Extraction Mapping

**DocumentHandler Implementation**:
```python
# src/services/docx_handler.py
class DocxDocumentHandler(DocumentHandler):
    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == '.docx'
    
    def convert_to_dita(self, file_path: Path, metadata: Dict) -> DitaContext:
        # Migrated logic from convert_docx_to_dita()
        return self._convert_docx_internal(file_path, metadata)
    
    def get_supported_extensions(self) -> List[str]:
        return ['.docx']
```

**Plugin Service Registration**:
```python
# src/plugin.py
class DocxConverterPlugin(BasePlugin):
    def on_activate(self) -> None:
        # Register document handler
        handler = DocxDocumentHandler()
        self.app_context.service_registry.register_service(
            'DocumentHandler', handler, self.plugin_id
        )
        
        # Register UI extensions
        self.app_context.ui_registry.register_panel_factory(
            'heading_filter', self._create_heading_filter_panel
        )
```

### 5.3 Configuration Integration

**Plugin-Specific Configuration**:
```yaml
# ~/.orlando_toolkit/plugins/docx-converter.yml
docx_conversion:
  enable_structural_style_inference: true
  min_following_paragraphs: 3
  
heading_filter:
  max_active_styles: 5
  default_exclusions: []
```

**Integration with Core ConfigManager**:
- Plugin configurations stored in separate files
- Loaded automatically when plugin activates
- Accessible via `plugin.get_config(section_name)`

---

## 6. Distribution & Management System

### 6.1 GitHub Repository Integration

**Plugin Download Workflow**:
1. **Repository Access**: Use GitHub API or direct ZIP download from repository
2. **Version Resolution**: Download from specified branch (default: `main`)
3. **Local Installation**: Extract to `~/.orlando_toolkit/plugins/{plugin-name}/`
4. **Dependency Installation**: Run `pip install -r requirements.txt` using the same standalone Python environment used by `install.bat`
5. **Validation**: Verify plugin.json schema and compatibility

**Installation Directory Structure**:
```
~/.orlando_toolkit/
├── config.yml                           # User configuration
├── plugins/
│   ├── docx-converter/                   # Installed plugin
│   │   ├── plugin.json
│   │   ├── requirements.txt
│   │   ├── src/
│   │   └── ...
│   └── pdf-converter/                    # Another plugin
│       ├── plugin.json
│       └── ...
└── plugin-configs/
    ├── docx-converter.yml               # Plugin-specific config
    └── pdf-converter.yml
```

### 6.2 Version Management Strategy

**Compatibility Matrix**:
- Plugin API Version: Semantic versioning for plugin interface changes
- Orlando Version: Minimum required Orlando Toolkit version
- Plugin Version: Individual plugin versioning

**Update Detection**:
- Check GitHub repository for new releases/commits
- Compare with installed plugin version
- Notify user of available updates

**Rollback Strategy**:
- Keep previous plugin version during updates
- Allow rollback to previous version if new version fails
- Automatic fallback on plugin load errors

### 6.3 Installation Security

**Validation Steps**:
1. **Schema Validation**: Verify plugin.json against expected schema
2. **Permission Check**: Ensure plugin requests only necessary permissions
3. **Dependency Scan**: Check for known vulnerable dependencies
4. **Code Signature**: (Future enhancement) Verify plugin authenticity

**Sandboxing** (Minimal for v1.0):
- Plugin code runs in same Python process (no process isolation)
- File system access limited to plugin directory and user documents
- Network access allowed for official plugins only

---

## 7. Data Flow & State Management

### 7.1 Plugin Data Integration

**DitaContext Extension**:
```python
# Existing structure
class DitaContext:
    def __init__(self, metadata: Dict[str, Any] = None):
        self.metadata = metadata or {}
        # ... existing fields
        
        # Plugin data storage (namespaced)
        self.plugin_data: Dict[str, Dict[str, Any]] = {}
```

**Plugin Data Access**:
```python
# Plugin can store/retrieve data
context.plugin_data['docx-converter'] = {
    'original_styles': style_mapping,
    'heading_analysis': analysis_results
}

# Access pattern for UI components
docx_data = context.plugin_data.get('docx-converter', {})
styles = docx_data.get('original_styles', [])
```

**Undo System Integration**:
- `UndoService` snapshots include `plugin_data`
- Plugin state changes trigger undo point creation
- Cross-plugin state changes handled atomically

### 7.2 Event-Driven State Updates

**State Change Propagation**:
1. Plugin modifies DitaContext
2. Plugin publishes `structure_changed` event
3. UI components subscribe and refresh
4. Other plugins can react to changes

**Event Flow Example**:
```
DOCX Plugin loads document → document_loaded event
    ↓
HeadingFilterPanel subscribes → Updates filter options
    ↓
User applies filter → structure_changed event
    ↓
Preview Panel subscribes → Refreshes preview
    ↓
Structure Tree subscribes → Updates highlighting
```

---

## 8. Implementation Constraints & Guidelines

### 8.1 KISS (Keep It Simple, Stupid) Principles

**Simplicity Requirements**:
- Plugin system adds minimal complexity to core application
- Plugin development requires minimal boilerplate code
- Installation process is single-click for official plugins
- Error messages are clear and actionable

**Complexity Boundaries**:
- No complex plugin dependency resolution (plugins are self-contained)
- No plugin-to-plugin communication beyond event system
- No plugin versioning conflicts (each plugin manages own dependencies)
- No advanced security sandboxing (trust-based model for v1.0)

### 8.2 DRY (Don't Repeat Yourself) Patterns

**Code Reuse Strategies**:
- Common UI components remain in core (buttons, dialogs, layouts)
- Shared DITA utilities stay in core (XML generation, validation)
- Plugin base classes provide common functionality
- Configuration parsing utilities shared across plugins

**Anti-Pattern Prevention**:
- Plugins must not duplicate core DITA processing logic
- UI extension points prevent custom widget reimplementation
- Service registry prevents duplicate service implementations

### 8.3 YAGNI (You Aren't Gonna Need It) Compliance

**Minimal Viable Features**:
- Plugin system supports only necessary extension points (right panels, document handlers)
- No advanced plugin marketplace or rating system
- No plugin sandboxing beyond basic file system restrictions
- No plugin hot-reloading (requires application restart)

**Deferred Features**:
- Plugin-to-plugin dependency management
- Plugin performance monitoring and profiling
- Advanced plugin security and code signing
- Plugin development IDE integration

### 8.4 Development Standards

**Plugin Development Guidelines**:
- Use type hints for all plugin interfaces
- Follow existing code style and conventions
- Include comprehensive error handling
- Provide user-friendly error messages
- Document all public plugin APIs

**Testing Requirements**:
- Plugin interfaces must be testable in isolation
- Core application must work without any plugins installed
- Plugin failures must not crash main application
- All extension points must have fallback behavior

---

## 9. Risk Analysis & Mitigation

### 9.1 Technical Risks

**Risk: Plugin Loading Failures**
- *Impact*: Application startup failure or reduced functionality
- *Mitigation*: Robust error handling, graceful degradation, safe mode startup
- *Detection*: Plugin validation during loading, health checks

**Risk: Plugin Performance Impact**
- *Impact*: Slow application startup, UI responsiveness issues
- *Mitigation*: Lazy plugin loading, performance monitoring, plugin timeouts
- *Detection*: Startup time measurement, user experience testing

**Risk: Plugin Compatibility Breaking**
- *Impact*: Plugins stop working after core updates
- *Mitigation*: Semantic versioning, compatibility matrix, plugin API stability
- *Detection*: Automated compatibility testing, plugin certification process

**Risk: Memory Leaks from Plugins**
- *Impact*: Application becomes unstable over time
- *Mitigation*: Plugin lifecycle management, resource cleanup hooks
- *Detection*: Memory profiling, long-running tests

### 9.2 Migration Challenges

**Challenge: DOCX Feature Parity**
- *Risk*: Plugin lacks functionality of integrated version
- *Mitigation*: Comprehensive feature mapping, thorough testing
- *Validation*: Side-by-side comparison testing

**Challenge: User Workflow Disruption**
- *Risk*: Users must install plugins for existing functionality
- *Mitigation*: Automatic DOCX plugin installation, clear migration guide
- *Validation*: User acceptance testing

**Challenge: Configuration Migration**
- *Risk*: Existing user configurations become invalid
- *Mitigation*: Configuration migration scripts, backward compatibility
- *Validation*: Test with real user configuration files

### 9.3 Failure Scenarios & Recovery

**Scenario: Plugin Download Failure**
- *Recovery*: Offline mode, cached plugin versions, manual installation guide
- *User Experience*: Clear error messages, alternative installation methods

**Scenario: Plugin Dependency Conflicts**
- *Recovery*: Plugin isolation, virtual environments, dependency pinning
- *User Experience*: Dependency conflict detection and resolution guidance

**Scenario: Plugin Corruption or Malfunction**
- *Recovery*: Plugin disable/uninstall, safe mode startup, plugin repair
- *User Experience*: Automatic error detection, one-click plugin repair

---

## 10. Success Criteria & Validation

### 10.1 Functional Requirements

✅ **Core Application Functionality**:
- Application starts and functions without any plugins installed
- DITA files can be opened, edited, and exported
- All existing structure editing features work identically

✅ **Plugin System Functionality**:
- DOCX plugin provides 100% feature parity with current integrated version
- Plugin installation is intuitive and works reliably
- Plugin failures are gracefully handled without crashing main application

✅ **Performance Requirements**:
- Plugin loading adds < 2 seconds to application startup time
- UI responsiveness is not impacted by plugin presence
- Memory usage increase < 20% with plugins loaded

### 10.2 Technical Validation

✅ **Architecture Validation**:
- Plugin interfaces are well-defined and stable
- Core application is properly decoupled from format-specific logic
- Plugin system follows KISS, DRY, and YAGNI principles

✅ **Integration Validation**:
- Multiple plugins can coexist without conflicts
- Plugin UI extensions integrate seamlessly with core UI
- Configuration system handles plugin settings correctly

✅ **Quality Validation**:
- Comprehensive test coverage for plugin interfaces
- Error handling covers all identified failure scenarios
- Documentation is complete and accurate for plugin development

### 10.3 User Experience Validation

✅ **Installation Experience**:
- Plugin installation requires minimal user technical knowledge
- Clear feedback provided during installation process
- Installation errors are actionable and clearly explained

✅ **Operational Experience**:
- Plugin functionality is discoverable within the application
- Plugin status and health is visible to users
- Plugin management operations are intuitive

---

## 11. Implementation Roadmap

### 11.1 Phase 1: Foundation (Estimated: 4-6 weeks)
1. **Plugin System Core** - Service registry, plugin loader, lifecycle management
2. **Plugin Interfaces** - DocumentHandler, UIExtension, base plugin classes
3. **Core Application Updates** - Generic ConversionService, plugin-aware file dialogs
4. **Configuration Integration** - Plugin config support in ConfigManager

### 11.2 Phase 2: DOCX Plugin (Estimated: 3-4 weeks)
1. **Plugin Creation** - Extract DOCX conversion logic into plugin structure
2. **Service Implementation** - DocumentHandler for DOCX format
3. **UI Migration** - Move HeadingFilterPanel to plugin
4. **Integration Testing** - Ensure feature parity with current version

### 11.3 Phase 3: Management System (Estimated: 2-3 weeks)
1. **GitHub Integration** - Plugin download and installation from repositories
2. **Plugin Management UI** - Installation, removal, status management interface
3. **Update System** - Version checking and plugin updates
4. **Documentation** - Plugin development guide, API documentation

### 11.4 Phase 4: Validation & Polish (Estimated: 2-3 weeks)
1. **Comprehensive Testing** - Integration tests, performance testing, error scenarios
2. **User Experience Testing** - Installation flows, error handling, documentation
3. **Performance Optimization** - Plugin loading optimization, memory usage analysis
4. **Documentation Completion** - User guides, technical documentation, migration notes

**Total Estimated Timeline: 11-16 weeks**

---

## Conclusion

This design document provides a comprehensive technical specification for transforming Orlando Toolkit into a plugin-driven architecture. The design maintains the principles of simplicity, avoid duplication, and implement only necessary features while enabling clean extensibility for future document format support.

The plugin system is designed to be:
- **Simple**: Minimal complexity, clear interfaces, easy plugin development
- **Robust**: Comprehensive error handling, graceful degradation, safe failure modes
- **Extensible**: Well-defined extension points, stable plugin APIs
- **Maintainable**: Clean separation of concerns, consistent patterns, thorough documentation

Implementation should proceed according to the defined phases, with each phase providing measurable progress toward the overall architectural transformation.

---

**Document Status**: This design document should be reviewed and approved before implementation begins. Any architectural questions or ambiguities should be resolved through stakeholder consultation following the NO ASSUMPTION policy.