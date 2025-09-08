# orlando_toolkit.core

Core processing layer used by all front-end interfaces.

- `models/` – dataclasses like `DitaContext` and `HeadingNode` that travel through the pipeline (DitaContext includes images and videos stores).
- `importers/` – DITA archive import functionality.
- `package_utils.py` – packaging helpers for DITA output (`save_dita_package`, renamers).
- `preview/` – read-only XML/HTML preview utilities (minimal XSLT + temp image materialization).
- `plugins/` – plugin architecture for extensible format conversion:
  - `base.py` – BasePlugin class and lifecycle management
  - `interfaces.py` – DocumentHandler and UI extension protocols
  - `registry.py` – Service registry for plugin services
  - `ui_registry.py` – UI component registry for plugin extensions
  - `marker_providers.py` – Scrollbar marker system for plugins
- `services/` – high-level APIs:
  - `ConversionService` (convert, prepare, write ZIP)
  - `StructureEditingService` (structure edits, depth/style filtering)
  - `PreviewService` (XML/HTML preview)
  - `UndoService` (immutable snapshots for undo/redo)
  - `HeadingAnalysisService` (derive effective depth, structure signals)
  - `ProgressService` (UI progress callbacks)
- `merge.py` – unified depth/style merge helpers used for structure filtering.
- `utils.py` – helpers (slugify, XML save, ID generation, section numbering… ).

## Plugin-Based Conversion

Document conversion through the plugin architecture:
- Plugin discovery via `ServiceRegistry` finds compatible handlers for file types
- Plugins implement `DocumentHandler.convert_to_dita()` to populate `DitaContext`
- Core services coordinate conversion workflow and UI integration

## Editing & packaging

- `StructureEditingService` performs safe in-memory edits (move up/down, rename, delete, depth/style filtering).
- `UndoService` stores full-context snapshots and restores them for undo/redo.
- `ConversionService.prepare_package()` applies unified merge (`merge.merge_topics_unified`), prunes empties, then renames topics/images.
- `ConversionService.write_package()` writes `DATA/` and zips it.

Links:
- Architecture: [docs/architecture_overview.md](../../docs/architecture_overview.md)
- Runtime flow: [docs/runtime_flow.md](../../docs/runtime_flow.md)
- Plugin development: [docs/PLUGIN_DEVELOPMENT_GUIDE.md](../../docs/PLUGIN_DEVELOPMENT_GUIDE.md)
- Plugin examples: see `tests/fixtures/plugins/` directory