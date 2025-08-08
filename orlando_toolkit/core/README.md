# orlando_toolkit.core

Core processing layer used by all front-end interfaces.

- `models/` – dataclasses like `DitaContext` and `HeadingNode` that travel through the pipeline.
- `parser/` – low-level helpers to walk a Word document and extract images/blocks.
- `converter/` – core DOCX ➜ DITA logic and packaging helpers (`save_dita_package`, renamers).
- `generators/` – XML builders (tables, lists) so the converter stays readable.
- `preview/` – read-only XML/HTML preview utilities.
- `services/` – high-level API (`ConversionService`) used by the GUI.
- `merge.py` – depth/style-based merge helpers used for structure filtering.
- `utils.py` – misc. helpers (slugify, XML save, colour mapping…).

Core conversion and merge logic are **I/O-free** and unit-testable; filesystem write operations are performed by `services.ConversionService.write_package()` using `converter.save_dita_package`.