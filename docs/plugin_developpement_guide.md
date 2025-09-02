# Orlando Toolkit — Plugin Development Guide (Concise)

This document lists all plugin integration points and how to use them.

Contents
- Plugin Layout
- Manifest (plugin.json)
- Entry Point and Lifecycle
- AppContext (safe access)
- ServiceRegistry integrations
  - DocumentHandler (conversion)
  - FilterProvider (structure filter data)
  - Marker Providers (scrollbar markers)
- UIRegistry integrations
  - PanelFactory (Structure tab panels)
  - WorkflowLauncher (custom conversion flows)
  - Plugin Capabilities
  - Buttons and Emoji
  - Panel roles (filter)
- Video Support in DitaContext
- Common Patterns and Pitfalls
- Minimal Examples

## Plugin Layout

Recommended structure:

plugins/
  your-plugin/
    plugin.json
    your_package/
      __init__.py
      plugin.py                # entry point class
      services/
        handler.py            # DocumentHandler (optional)
        filter_provider.py    # FilterProvider (optional)
      ui/
        panels.py             # PanelFactory + panels (optional)

## Manifest (plugin.json)

Required fields:
- name: short identifier
- version: semantic version
- display_name: human-readable name
- description
- plugin_api_version: "1.0"
- orlando_version: engine compatibility (e.g. ">=2.0.0")
- category: "pipeline" (if it provides conversion)
- entry_point: fully-qualified class path, e.g. "your_package.plugin.YourPlugin"

Optional:
- ui.splash_button: { text, tooltip }

## Entry Point and Lifecycle

Extend BasePlugin:

class YourPlugin(BasePlugin):
    def on_activate(self) -> None:
        # Register services and UI
        ...

    def on_deactivate(self) -> None:
        # Unregister what you registered
        ...

Access the application via self.app_context. Avoid importing internal app modules directly.

## AppContext — Safe Access

Key accessors:
- service_registry: ServiceRegistry
- ui_registry: UIRegistry
- get_conversion_service(), get_structure_editing_service(), get_undo_service(), get_preview_service()
- get_current_dita_context() (read-only)

Use AppContext for registration and discovery. Keep logic inside your plugin.

## ServiceRegistry Integrations

Register during on_activate; unregister during on_deactivate.

### DocumentHandler (conversion)

Purpose: Convert source files into a DitaContext.
Register: service_registry.register_document_handler(handler, plugin_id)
Unregister: service_registry.unregister_service("DocumentHandler", plugin_id)

Implement (Protocol):
- can_handle(file_path) -> bool
- convert_to_dita(file_path, metadata, progress_callback) -> DitaContext
- get_supported_extensions() -> List[str]
- get_conversion_metadata_schema() -> Dict[str, Any]

Guidance:
- Use progress_callback for long work.
- Offload heavy tasks off the UI thread.

### FilterProvider (structure filter data)

Purpose: Provide “group keys” and counts/occurrences/levels for the Structure tab filter.
Register: service_registry.register_filter_provider(provider, plugin_id)
Unregister: service_registry.unregister_filter_provider(plugin_id)

Implement (Protocol):
- get_counts(context) -> Dict[str, int]
- get_occurrences(context) -> Dict[str, List[Dict[str, str]]]
- get_occurrences_current(context) -> Dict[str, List[Dict[str, str]]]
- get_levels(context) -> Dict[str, Optional[int]]
- estimate_unmergable(context, style_excl_map: Dict[int, Set[str]]) -> int
- build_exclusion_map(exclusions: Dict[str, bool]) -> Dict[int, Set[str]] (optional)

Notes:
- Keys are plugin-defined strings (opaque to core).
- Keep these methods fast. Cache when sensible.

### Marker Providers (scrollbar markers)

Provide custom markers for the structure tree. Keep optional and light.

## UIRegistry Integrations

### PanelFactory (Structure tab panels)

Purpose: Provide right-side panels. The host wires button + lifecycle.

PanelFactory methods the host may call if present:
- create_panel(parent, context) -> tk.Widget
- get_panel_type() -> str
- get_display_name() -> str
- get_button_emoji() -> str (emoji for Structure tab button)
- get_role() -> str ('filter' for standardized filter panels)
- cleanup_panel(panel) -> None

Register: ui_registry.register_panel_factory(panel_type, factory, plugin_id)
Unregister: ui_registry.unregister_panel_factory(panel_type, plugin_id)

Panel roles:
- 'filter': host routes via unified filter flow. Your panel receives:
  - on_close()
  - on_apply(exclusions: Dict[str, bool])
  - on_toggle_style(style: str, visible: bool)
- (others/omitted): generic plugin panel.

### WorkflowLauncher (custom conversion flows)

Purpose: Take complete control of the conversion workflow (file selection, progress UI, threading).
Register: ui_registry.register_workflow_launcher(plugin_id, launcher)
Unregister: ui_registry.unregister_workflow_launcher(plugin_id)

Implement (Protocol):
- get_display_name() -> str
- launch(app_context, app_ui) -> None

Usage:
- Called from splash screen buttons or plugin-specific entry points
- Plugin handles entire conversion flow (file dialogs, progress, threading)
- Must call app_ui.on_conversion_success(context) when complete
- Handle errors with app_ui._hide_loading_spinner() + messagebox

### Plugin Capabilities

Purpose: Declare UI capabilities for conditional feature activation.
Register: ui_registry.register_plugin_capability(plugin_id, capability)
Unregister: ui_registry.unregister_plugin_capability(plugin_id, capability)

Common capabilities:
- "heading_filter": Plugin provides heading-based filtering
- "style_toggle": Plugin supports style-based toggles
- "video_preview": Plugin can display video previews
- "filter_panel": Plugin provides filter panels

Usage:
- Host checks capabilities via app_context.document_source_plugin_has_capability(capability)
- Enables conditional UI features based on source plugin capabilities

### Buttons and Emoji

- Provide get_button_emoji() for the panel's button; tooltip uses get_display_name().
- Structure tab buttons use emojis only (no images).
- Toggle behavior:
  - Preview: toggles preview <-> none
  - Plugin panel: toggles panel <-> none

## Video Support in DitaContext

Purpose: Store and manage video files alongside images in DITA packages.

Video storage:
- DitaContext.videos: Dict[str, bytes] - Similar to images storage
- Videos are saved to DATA/media/ during package creation (alongside images)
- UI supports video preview and download via MediaTab

Plugin usage:
- Populate context.videos in DocumentHandler.convert_to_dita()
- Videos persist through package save/load cycles
- Use standard media references in DITA content: <object data="../media/video.mp4"/>

Example:
```python
def convert_to_dita(self, file_path: Path, metadata: Dict[str, Any], progress_callback=None) -> DitaContext:
    context = DitaContext()
    
    # Add video file
    video_data = file_path.read_bytes()
    context.videos[file_path.name] = video_data
    
    # Reference in DITA content
    # <object data="../media/my_video.mp4" type="video/mp4"/>
    
    return context
```

## Common Patterns and Pitfalls

Patterns
- Register in on_activate; unregister in on_deactivate.
- Use get_role() == 'filter' for filter panels so host wiring is automatic.
- Keep business logic (counts/levels/etc.) in FilterProvider.
- Prefer non-blocking UI (thread off heavy work).

Pitfalls
- Missing get_role('filter') → filter panel not wired to filter flow.
- No FilterProvider → panel shows empty/partial data.
- Doing long work in UI thread → jank.
- Using images for Structure tab buttons → ignored; use emoji.
- Forgetting to unregister → stale references on deactivate.

## Minimal Examples

### Entry point (skeleton)

from orlando_toolkit.core.plugins.base import BasePlugin

class MyPlugin(BasePlugin):
    def on_activate(self) -> None:
        pass

    def on_deactivate(self) -> None:
        pass

### DocumentHandler

from pathlib import Path
from typing import Any, Dict, List
from orlando_toolkit.core.plugins.interfaces import DocumentHandler

class MyHandler(DocumentHandler):
    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() == '.ext'

    def convert_to_dita(self, file_path: Path, metadata: Dict[str, Any], progress_callback=None):
        ...  # return DitaContext

    def get_supported_extensions(self) -> List[str]:
        return ['.ext']

    def get_conversion_metadata_schema(self) -> Dict[str, Any]:
        return { 'type': 'object', 'properties': {} }

### FilterProvider

from typing import Dict, List, Optional, Set
from orlando_toolkit.core.plugins.interfaces import FilterProvider

class MyFilterProvider(FilterProvider):
    def get_counts(self, context) -> Dict[str, int]:
        return { 'GroupA': 12 }
    def get_occurrences(self, context) -> Dict[str, List[Dict[str, str]]]:
        return { 'GroupA': [{'href': 'topic.dita#id'}] }
    def get_occurrences_current(self, context) -> Dict[str, List[Dict[str, str]]]:
        return {}
    def get_levels(self, context) -> Dict[str, Optional[int]]:
        return { 'GroupA': 1 }
    def estimate_unmergable(self, context, style_excl_map: Dict[int, Set[str]]) -> int:
        return 0
    def build_exclusion_map(self, exclusions: Dict[str, bool]) -> Dict[int, Set[str]]:
        return { 1: { k for k, ex in exclusions.items() if ex } }

### PanelFactory (filter)

import tkinter as tk
from tkinter import ttk

class MyFilterPanelFactory:
    def create_panel(self, parent: tk.Widget, context):
        return MyFilterPanel(parent)
    def get_panel_type(self) -> str:
        return 'my_filter'
    def get_display_name(self) -> str:
        return 'My Filter'
    def get_button_emoji(self) -> str:
        return '🧩'
    def get_role(self) -> str:
        return 'filter'
    def cleanup_panel(self, panel: tk.Widget) -> None:
        try: panel.destroy()
        except Exception: pass

class MyFilterPanel(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        ttk.Label(self, text='My Filter').pack()
        # Host passes: on_close, on_apply(exclusions), on_toggle_style(style, visible)

### WorkflowLauncher

from orlando_toolkit.core.plugins.interfaces import WorkflowLauncher
import threading
from tkinter import filedialog, messagebox

class MyWorkflowLauncher(WorkflowLauncher):
    def get_display_name(self) -> str:
        return "My Custom Workflow"
    
    def launch(self, app_context: Any, app_ui: Any) -> None:
        # Show file dialog
        files = filedialog.askopenfilenames(filetypes=[("My Files", "*.ext")])
        if not files:
            return
        
        # Start progress UI
        app_ui._show_loading_spinner("Converting Files", "")
        app_ui._disable_all_ui_elements()
        
        # Run conversion in background thread
        def work():
            try:
                context = self._convert_files(files)
                # Success: hand off to host UI thread
                app_ui.root.after(0, app_ui.on_conversion_success, context)
            except Exception as e:
                # Error: cleanup and show message
                def fail():
                    app_ui._hide_loading_spinner()
                    app_ui._enable_all_ui_elements()
                    messagebox.showerror("Error", str(e))
                app_ui.root.after(0, fail)
        
        threading.Thread(target=work, daemon=True).start()

