# orlando_toolkit.core

Core processing layer used by all front-end interfaces.

- `models/` – dataclasses like `DitaContext` and `HeadingNode` that travel through the pipeline.
- `parser/` – low-level helpers to walk a Word document and extract styles/blocks/images.
- `converter/` – two-pass DOCX → DITA logic and packaging helpers (`save_dita_package`, renamers).
- `generators/` – XML builders (tables, lists) so the converter stays readable.
- `preview/` – read-only XML/HTML preview utilities (minimal XSLT + temp image materialization).
- `services/` – high-level APIs:
  - `ConversionService` (convert, prepare, write ZIP)
  - `PreviewService` (XML/HTML preview)
  - `UndoService` (immutable snapshots for undo/redo)
- `merge.py` – unified depth/style merge helpers used for structure filtering.
- `utils.py` – helpers (slugify, XML save, ID generation, section numbering… ).

## Conversion

- Pass 1: `converter/structure_builder.build_document_structure()` builds a hierarchy of `HeadingNode` using `parser/style_analyzer` and block iteration.
- Pass 2: `determine_node_roles()` marks nodes as section vs module.
- Generation: `generate_dita_from_structure()` produces a DITA map with `topichead` for sections, concept topics for modules, and fills `DitaContext`.

## Editing & packaging

- `StructureEditingService` performs safe in-memory edits (move up/down, rename, delete, depth/style filtering).
- `UndoService` stores full-context snapshots and restores them for undo/redo.
- `ConversionService.prepare_package()` applies unified merge (`merge.merge_topics_unified`), prunes empties, then renames topics/images.
- `ConversionService.write_package()` writes `DATA/` and zips it.

Links:
- Architecture: [docs/architecture_overview.md](../../docs/architecture_overview.md)
- Runtime flow: [docs/runtime_flow.md](../../docs/runtime_flow.md)