from __future__ import annotations

"""High-level conversion service for DOCX to DITA transformation.

Entry-point for any front-end (GUI, CLI, API) that needs to transform
a Word document into a DITA package. Provides a clean, stable API for
document conversion operations.
"""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.utils import slugify

# Core conversion operations
from orlando_toolkit.core.converter import (
    convert_docx_to_dita,
    save_dita_package,
    update_image_references_and_names,
    update_topic_references_and_names,
)

logger = logging.getLogger(__name__)

__all__ = ["ConversionService"]


class ConversionService:
    """Business-logic façade with zero GUI / Tkinter dependencies."""

    def __init__(self) -> None:
        # Potential configuration injection point (not used yet)
        self.logger = logger

    # ---------------------------------------------------------------------
    # PUBLIC API
    # ---------------------------------------------------------------------
    def convert(self, docx_path: str | Path, metadata: Dict[str, Any]) -> DitaContext:
        """Convert the Word document at *docx_path* to an in-memory DitaContext."""
        docx_path = str(docx_path)
        self.logger.info("Converting DOCX → DITA: %s", docx_path)
        context = convert_docx_to_dita(docx_path, dict(metadata))
        return context

    def prepare_package(self, context: DitaContext) -> DitaContext:
        """Apply final renaming of topics and images inside *context*."""
        context = update_topic_references_and_names(context)
        context = update_image_references_and_names(context)
        return context

    def write_package(self, context: DitaContext, output_zip: str | Path, *,
                      debug_copy_dir: Optional[str | Path] = None) -> None:
        """Write *context* to *output_zip* (a ``.zip`` path).

        If *debug_copy_dir* is provided, the un-zipped folder is also copied
        there for inspection.
        """
        output_zip = Path(output_zip)
        self.logger.info("Writing DITA package → %s", output_zip)

        with tempfile.TemporaryDirectory(prefix="orlando_packager_") as tmp_dir:
            save_dita_package(context, tmp_dir)
            if debug_copy_dir:
                debug_dest = Path(debug_copy_dir)
                if debug_dest.exists():
                    shutil.rmtree(debug_dest)
                shutil.copytree(tmp_dir, debug_dest)
                self.logger.info("Debug copy written to %s", debug_dest)
            shutil.make_archive(output_zip.with_suffix(""), "zip", tmp_dir)

    # Convenience one-shot -------------------------------------------------
    def convert_and_package(
        self,
        docx_path: str | Path,
        metadata: Dict[str, Any],
        output_zip: str | Path,
        *,
        debug_copy_dir: Optional[str | Path] = None,
    ) -> Path:
        """Full pipeline: convert DOCX and immediately write a ZIP archive."""
        context = self.convert(docx_path, metadata)
        context = self.prepare_package(context)
        self.write_package(context, output_zip, debug_copy_dir=debug_copy_dir)
        return Path(output_zip) 