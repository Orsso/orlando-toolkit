# orlando_toolkit.core

Core processing layer used by all front-end interfaces.

What lives here?

* `models.py` – dataclasses like `DitaContext` that travel through the pipeline.
* `parser/` – low-level helpers to walk a Word document and pull out stuff.
* `converter/` – core DOCX ➜ DITA logic (pure functions, no I/O).
* `generators/` – small XML builders (tables etc.) so the converter stays readable.
* `services/` – high-level API (`ConversionService`) that the GUI / CLI call into.
* `utils.py` – misc. helpers (slugify, XML save, colour mapping…).

Core modules should remain **I/O-free** and unit-testable; filesystem operations belong in `services`. 