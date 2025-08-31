from __future__ import annotations

"""Import functionality for various archive formats.

This package contains importers for different document archive formats
that Orlando Toolkit can work with natively, including:

- DITA packages (zipped DITA archives)
- Future importers for other structured formats

Key components:
- DitaPackageImporter: Handles zipped DITA archive import and validation
"""

from .dita_importer import DitaPackageImporter

__all__ = ["DitaPackageImporter"]