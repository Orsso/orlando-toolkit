# orlando_toolkit.ui

[![Back to Main README](https://img.shields.io/badge/←%20Back%20to-README-blue)](../../README.md)
[![Documentation Index](https://img.shields.io/badge/←%20Docs-Index-green)](../../docs/README.md)

**Tkinter widgets and user interface components for the desktop application.**

## Overview

The UI module contains all user interface components, controllers, and widgets that make up the Orlando Toolkit desktop application.

Tabs
- **StructureTab** – browse/edit structure, depth/style filters, preview.
- **MediaTab** – preview images and videos; rename media assets.
- **MetadataTab** – edit manual metadata.

Controllers & services
- `StructureController` wires UI events to services: `StructureEditingService`, `UndoService`, `PreviewService`.
- Preview uses `PreviewService` and `core/preview/xml_compiler.py` (HTML via minimal XSLT; falls back to XML/plain text). Optional `tkinterweb` can improve HTML rendering.

Widgets
- `widgets/structure_tree_widget.py`, `widgets/search_widget.py`, `widgets/toolbar_widget.py`, `widgets/preview_panel.py` compose the Structure tab.

Links:
- Architecture: [docs/architecture_overview.md](../../docs/architecture_overview.md)
- Runtime flow: [docs/runtime_flow.md](../../docs/runtime_flow.md)
- Core layer: [orlando_toolkit/core/README.md](../core/README.md)