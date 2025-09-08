# Plugin Development Guide

Goal: provide a single, accurate source of truth for developing Orlando Toolkit plugins. Technical and to the point.

Contents
- Concepts and layout
- Manifest (plugin.json)
- Lifecycle and AppContext
- ServiceRegistry integrations
  - DocumentHandler
  - FilterProvider
- UIRegistry integrations
  - PanelFactory
  - WorkflowLauncher
  - Capabilities and markers
- Data model notes (videos)
- Conventions and pitfalls
- Minimal examples

## Concepts and layout

A plugin is a standalone repository with a manifest and a Python package that exposes an entry point class.

Recommended structure:

plugins/
  your-plugin/
    plugin.json
    your_package/
      __init__.py
      plugin.py                 # entry point class
      services/
        handler.py             # DocumentHandler (optional)
        filter_provider.py     # FilterProvider (optional)
      ui/
        panels.py              # PanelFactory + panels (optional)
      utils/
        __init__.py

## Manifest (plugin.json)

Required
- name, version, display_name, description
- plugin_api_version: "1.0"
- orlando_version: engine compatibility (e.g., ">=1.2.0")
- category: "pipeline" if it provides conversion
- entry_point: fully-qualified class name, e.g. "your_package.plugin.YourPlugin"

Optional
- ui.splash_button: { text, icon, tooltip }
- provides: { services: [...], ui_extensions: [...], marker_providers: [...] }

## Lifecycle and AppContext

Your entry point class must inherit BasePlugin and may implement UIExtension.

class YourPlugin(BasePlugin):
    def on_load(self, app_context: AppContext) -> None: ...
    def on_activate(self) -> None: ...      # register services/UI here
    def on_deactivate(self) -> None: ...    # unregister/cleanup

Use self.app_context to access:
- service_registry: ServiceRegistry
- ui_registry: UIRegistry
- get_conversion_service(), get_structure_editing_service(), get_undo_service(), get_preview_service(), get_progress_service()
- get_current_dita_context() (read-only)
- document_source_plugin_has_capability(cap)

Avoid importing Orlando internals directly; go through AppContext and registries.

## ServiceRegistry integrations

Register in on_activate(), unregister in on_deactivate().

### DocumentHandler (conversion)
Purpose: convert source files to a DitaContext.

Interface (Protocol):
- can_handle(file_path: Path) -> bool
- convert_to_dita(file_path: Path, metadata: Dict[str, Any], progress_callback: Optional[Callable[[str], None]]) -> DitaContext
- get_supported_extensions() -> List[str]
- get_conversion_metadata_schema() -> Dict[str, Any]

Registration:
- service_registry.register_document_handler(handler, plugin_id)
- service_registry.unregister_service("DocumentHandler", plugin_id)

Notes:
- Keep can_handle() fast. Prefer extension checks; content sniffing only if cheap.
- Use progress_callback for long steps (reading, analysis, extraction).
- Don’t block the UI thread.

### FilterProvider (structure filter data)
Purpose: supply counts, occurrences, levels, and exclusion mapping for the Structure tab filter.

Interface (Protocol):
- get_counts(context) -> Dict[str, int]
- get_occurrences(context) -> Dict[str, List[Dict[str, str]]]
- get_occurrences_current(context) -> Dict[str, List[Dict[str, str]]]
- get_levels(context) -> Dict[str, Optional[int]]
- build_exclusion_map(exclusions: Dict[str, bool]) -> Dict[int, set[str]]
- estimate_unmergable(context, style_excl_map: Dict[int, set[str]]) -> int

Registration:
- service_registry.register_filter_provider(provider, plugin_id)
- service_registry.unregister_filter_provider(plugin_id)

Guidance:
- Keys are plugin-defined (opaque to core). Cache when it helps.

## UIRegistry integrations

### PanelFactory (right-side panels)
Provide UI panels for the Structure tab. The host wires button and lifecycle.

Factory methods the host may call:
- create_panel(parent, context) -> widget
- get_panel_type() -> str
- get_display_name() -> str
- get_button_emoji() -> str (emoji for toolbar button)
- get_role() -> str (use 'filter' for standardized filter panels)
- cleanup_panel(panel) -> None

Registration:
- ui_registry.register_panel_factory(panel_type, factory, plugin_id)
- ui_registry.unregister_panel_factory(panel_type, plugin_id)

### WorkflowLauncher (optional)
Let a plugin control the pre-conversion UX (file dialogs, threading, progress).

Interface:
- get_display_name() -> str
- launch(app_context, app_ui) -> None

Registration:
- ui_registry.register_workflow_launcher(plugin_id, launcher)
- ui_registry.unregister_workflow_launcher(plugin_id)

Responsibilities:
- Show dialogs, start background work, then call app_ui.on_conversion_success(context) on completion.
- On error, revert UI state and show a message.

### Capabilities and markers

Capabilities let the host toggle UI affordances per source plugin.
- ui_registry.register_plugin_capability(plugin_id, "heading_filter" | "style_toggle" | "video_preview" | "filter_panel" | ...)
- app_context.document_source_plugin_has_capability(capability) -> bool

Markers (optional visualization in scrollbars, etc.) are provided via a MarkerProvider implementation and registered with ui_registry.register_marker_provider(...).

## Data model notes (videos)

DitaContext supports videos alongside images:
- context.videos: Dict[str, bytes]
- Packaging: by default, the core packager persists images. If your plugin needs videos in the ZIP, either map them into `context.images` or add a packaging step that writes videos to `DATA/media/`.
- UI Media tab supports preview when a video-capable plugin is the source.

Populate videos in your DocumentHandler if applicable.

## Conventions and pitfalls

Conventions
- Register in on_activate(); unregister in on_deactivate().
- Keep long-running work off the UI thread; use a workflow launcher if you own the UX.
- Use get_role() == 'filter' for standardized filter panels.
- Keep filter logic in FilterProvider; keep UI thin.

Pitfalls
- Forgetting to unregister services/components on deactivate.
- Missing 'filter' role → panel not wired to filter flow.
- Doing blocking work in the UI thread.
- Using images for Structure tab buttons (use emoji characters instead).

## Minimal examples

Entry point skeleton

from orlando_toolkit.core.plugins.base import BasePlugin

class MyPlugin(BasePlugin):
    def on_activate(self) -> None:
        # Register services/UI here
        ...
    def on_deactivate(self) -> None:
        # Clean up registrations here
        ...

DocumentHandler

from pathlib import Path
from typing import Any, Dict, List, Optional
from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.plugins.interfaces import DocumentHandler

class MyHandler(DocumentHandler):
    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in {'.ext'}
    def convert_to_dita(self, file_path: Path, metadata: Dict[str, Any], progress_callback: Optional[callable] = None) -> DitaContext:
        if progress_callback:
            progress_callback('Parsing input...')
        ctx = DitaContext()
        # populate ctx.ditamap_root, ctx.topics, ctx.images/videos, ctx.metadata
        return ctx
    def get_supported_extensions(self) -> List[str]:
        return ['.ext']
    def get_conversion_metadata_schema(self) -> Dict[str, Any]:
        return { 'type': 'object', 'properties': {} }

FilterProvider

from typing import Dict, List, Optional
from orlando_toolkit.core.plugins.interfaces import FilterProvider

class MyFilterProvider(FilterProvider):
    def get_counts(self, context) -> Dict[str, int]:
        return { 'GroupA': 12 }
    def get_occurrences(self, context) -> Dict[str, List[Dict[str, str]]]:
        return { 'GroupA': [{ 'href': 'topic.dita#id' }] }
    def get_occurrences_current(self, context) -> Dict[str, List[Dict[str, str]]]:
        return {}
    def get_levels(self, context) -> Dict[str, Optional[int]]:
        return { 'GroupA': 1 }
    def build_exclusion_map(self, exclusions: Dict[str, bool]):
        return { 1: { k for k, v in exclusions.items() if v } }
    def estimate_unmergable(self, context, style_excl_map):
        return 0

PanelFactory (filter role)

class MyFilterPanelFactory:
    def create_panel(self, parent, context=None):
        # return a Tk widget
        ...
    def get_panel_type(self) -> str:
        return 'my_filter'
    def get_display_name(self) -> str:
        return 'My Filter'
    def get_button_emoji(self) -> str:
        return '🧩'
    def get_role(self) -> str:
        return 'filter'
    def cleanup_panel(self, panel) -> None:
        try:
            panel.destroy()
        except Exception:
            pass

WorkflowLauncher (optional)

class MyWorkflowLauncher:
    def get_display_name(self) -> str:
        return 'My Custom Workflow'
    def launch(self, app_context, app_ui) -> None:
        # open dialogs, start background thread, then app_ui.on_conversion_success(context)
        ...

