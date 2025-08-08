# orlando_toolkit.ui

Tkinter widgets used by the desktop app.

Tabs
* **MetadataTab** – edit manual metadata.
* **ImageTab** – preview + rename extracted images.
* **StructureTab** – browse/edit structure, depth/style filters, preview.

`custom_widgets.py` provides reusable frames (toggle, thumbnail).

This layer contains only presentation code; processing happens in services (`ConversionService`, `StructureEditingService`, `PreviewService`).