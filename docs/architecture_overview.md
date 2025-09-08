## Orlando Toolkit — Architecture Overview

---

- UI overview: see `orlando_toolkit/app.py` and `orlando_toolkit/ui/`
- Core processing: see `orlando_toolkit/core/` and its [README](../orlando_toolkit/core/README.md)
- Plugin architecture: see [Plugin Development Guide](PLUGIN_DEVELOPMENT_GUIDE.md)
- Configuration: see `orlando_toolkit/config/` and its [README](../orlando_toolkit/config/README.md)
- End-to-end runtime: see [Runtime Flow](runtime_flow.md)

---

## 1. High-level architecture

```mermaid
flowchart TD
  subgraph UI
    A1["Tkinter app<br/>run.py → OrlandoToolkit"]
    A2["Tabs & Widgets<br/>ui/ (Structure, Media, Metadata)"]
    A3["Controller<br/>StructureController"]
  end
  subgraph Core
    B1["Services<br/>ConversionService<br/>PreviewService<br/>UndoService"]
    B2["Plugin System<br/>ServiceRegistry<br/>DocumentHandlers"]
    B3["Models & Utils<br/>DitaContext, HeadingNode<br/>merge.py, utils.py"]
  end
  subgraph Config
    C1["Config Manager<br/>YAML + user overrides"]
  end

  A1 --> A2 --> A3 --> B1
  B1 --> B2
  B1 --> B3
  B1 --> C1
```

Key properties:
- UI is a thin layer. Business logic lives in services (`core/services/`).
- Plugin-based conversion operates in-memory until packaging.
- Configuration is optional and layered: packaged defaults + user overrides; safe fallbacks when YAML isn’t available.

---

## 2. Code layout

```
orlando_toolkit/
  app.py                 # Tk-based app, home → summary → main tabs
  core/
    models/              # DitaContext, HeadingNode
    plugins/             # Plugin architecture (base, interfaces, registry)
    services/            # ConversionService, PreviewService, UndoService
    importers/           # DITA archive import
    preview/             # Raw XML + HTML preview (XSLT, temp images)
    merge.py             # Unified depth/style merge for structure filtering
    utils.py             # Save XML, slugify, ID helpers, etc.
  config/
    manager.py           # YAML loader + user overrides
  ui/
    controllers/         # `StructureController`
    widgets/             # Structure tree, search, toolbar, preview panel…
    *_tab.py             # Structure / Media / Metadata tabs
```

Related sub-docs:
- Core details: [orlando_toolkit/core/README.md](../orlando_toolkit/core/README.md)
- UI details: [orlando_toolkit/ui/README.md](../orlando_toolkit/ui/README.md)
- Config details: [orlando_toolkit/config/README.md](../orlando_toolkit/config/README.md)

---

## 3. Runtime workflow

Summary of the primary flow (see the full sequence in [Runtime Flow](runtime_flow.md)):
- `run.py` sets up logging, theme, icon, and instantiates `OrlandoToolkit`.
- User selects a document → `ConversionService.convert()` uses plugins to build an in-memory `DitaContext`.
- The app shows a post-conversion summary on the home screen with counts and inline metadata editing.
- User continues to the main tabs: Structure, Media, Metadata.
- On Export, `ConversionService.prepare_package()` applies unified depth/style filtering and renaming; then `write_package()` saves a `DATA/` tree and zips it.

Notes:
- Structure filtering in the UI uses `StructureEditingService.apply_depth_limit()` under the controller, with undo snapshots via `UndoService`.
- Preview goes through `PreviewService` and `core/preview/xml_compiler.py` (minimal XSLT, temp files for images). Optional `tkinterweb` enables richer HTML; falls back to readable XML/text.

---

## 4. Plugin-based conversion

Document conversion through plugin system:
- Plugin discovery: `ServiceRegistry` finds compatible `DocumentHandler` for file type
- Document parsing: Plugin extracts content, media, and metadata from source format  
- DITA generation: Plugin converts to `DitaContext` with topics, media, and structure
- UI integration: via `UIRegistry` (panel factories, marker providers, workflow launchers) and per-plugin capabilities (e.g., heading_filter, video_preview)

---

## 5. Services and editing

- `ConversionService`
  - `convert(path, metadata)` → `DitaContext`
  - `prepare_package(ctx)` → apply unified depth/style merge (`merge.merge_topics_unified`), prune empties, rename topics/images.
  - `write_package(ctx, output_zip)` → `DATA/` layout and ZIP.
- `PreviewService` → raw XML and HTML preview through `preview/xml_compiler.py`.
- `UndoService` → immutable snapshots of the full `DitaContext` for undo/redo.
- `StructureEditingService` (used via `StructureController`) → move up/down, rename, delete, apply depth/style filters.

Models:
- `DitaContext` now includes helpers to save/restore original structure to make depth filtering reversible in-session.

---

## 6. Configuration

`ConfigManager` loads packaged defaults and merges `~/.orlando_toolkit/*.yml` when present. Safe fallbacks apply if PyYAML is missing.

Available sections and current state:
- `preview_styles`, `style_map`, `image_naming`, `logging` → loaded if provided by the user; otherwise empty defaults.

See [orlando_toolkit/config/README.md](../orlando_toolkit/config/README.md).

---

## 7. Packaging and resources

- No DTDs are embedded. Files declare standard PUBLIC identifiers (e.g., `map.dtd`, `concept.dtd`) and rely on the target toolchain’s catalog.
- Output layout:
  - `DATA/topics/` — generated topics
  - `DATA/media/` — extracted images
  - `DATA/<manual_code>.ditamap` — root map

---

## 8. Build & distribution

- Windows executable: `build.py` (PyInstaller, windowed).
- From source: `python run.py` after installing `requirements.txt`.

---

## 9. Links

- Runtime flow: [docs/runtime_flow.md](runtime_flow.md)
- Core guide: [orlando_toolkit/core/README.md](../orlando_toolkit/core/README.md)
- UI guide: [orlando_toolkit/ui/README.md](../orlando_toolkit/ui/README.md)
- Config guide: [orlando_toolkit/config/README.md](../orlando_toolkit/config/README.md)

