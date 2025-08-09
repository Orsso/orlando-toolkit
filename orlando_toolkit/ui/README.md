# orlando_toolkit.ui

Tkinter widgets used by the desktop app.

Tabs
- **StructureTab** – browse/edit structure, depth/style filters, preview.
- **ImageTab** – preview + rename extracted images.
- **MetadataTab** – edit manual metadata.

Controllers & services
- `StructureController` wires UI events to services: `StructureEditingService`, `UndoService`, `PreviewService`.
- Preview uses `PreviewService` and `core/preview/xml_compiler.py` (HTML via minimal XSLT; falls back to XML/plain text). Optional `tkinterweb` can improve HTML rendering.

Widgets
- `widgets/structure_tree.py`, `widgets/search_widget.py`, `widgets/toolbar_widget.py`, `widgets/preview_panel.py` compose the Structure tab.

Links:
- Architecture: [docs/architecture_overview.md](../../docs/architecture_overview.md)
- Runtime flow: [docs/runtime_flow.md](../../docs/runtime_flow.md)
- Core layer: [orlando_toolkit/core/README.md](../core/README.md)