from __future__ import annotations

"""Low-level DOCX utilities shared by the converter.

Extracted from the original *docx_to_dita_converter.py* to allow unit‐testing
and reuse without GUI dependencies.
"""

from typing import Dict, Generator
import io
import logging

from PIL import Image
from docx.document import Document as _Document  # type: ignore
from docx.oxml.table import CT_Tbl  # type: ignore
from docx.oxml.text.paragraph import CT_P  # type: ignore
from docx.table import _Cell, Table  # type: ignore
from docx.text.paragraph import Paragraph  # type: ignore

from orlando_toolkit.core.models import DitaContext

logger = logging.getLogger(__name__)

__all__ = [
    "iter_block_items",
    "extract_images_to_context",
]


# ---------------------------------------------------------------------------
# iter_block_items – recursive traversal
# ---------------------------------------------------------------------------

def iter_block_items(parent: _Document | _Cell) -> Generator[Paragraph | Table, None, None]:
    """Yield *Paragraph* and *Table* objects in document order (recursive).

    Mirrors the behaviour previously embedded in the converter, but is now
    available as a standalone helper for tests or other tooling stages.
    """

    if isinstance(parent, _Document):
        root_elm = parent.element.body
        parent_obj = parent  # _Document for Paragraph/Table constructors
    elif isinstance(parent, _Cell):
        root_elm = parent._tc
        parent_obj = parent  # _Cell
    else:
        raise ValueError("Unsupported parent type for iter_block_items")

    def _walk(element):
        for child in element.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, parent_obj)
            elif isinstance(child, CT_Tbl):
                yield Table(child, parent_obj)
            else:
                # Recurse into unknown containers (e.g., w:sdt, w:txbxContent)
                yield from _walk(child)

    yield from _walk(root_elm)


# ---------------------------------------------------------------------------
# Image extraction
# ---------------------------------------------------------------------------

def extract_images_to_context(doc: _Document, context: DitaContext) -> Dict[str, str]:
    """Populate *context.images* with image bytes and return rid→filename map."""

    image_map_rid: Dict[str, str] = {}
    image_counter = 1
    for rel_id, rel in doc.part.rels.items():
        if "image" in rel.target_ref:
            image_data = rel.target_part.blob
            try:
                img = Image.open(io.BytesIO(image_data))

                # Convert everything to PNG for uniformity (fixes WMF issues)
                png_buf = io.BytesIO()
                # Ensure RGB(A) mode for safer conversion
                if img.mode in ("P", "RGBA", "LA"):
                    img = img.convert("RGBA")
                else:
                    img = img.convert("RGB")

                img.save(png_buf, format="PNG")
                png_bytes = png_buf.getvalue()

                image_filename = f"image_{image_counter}.png"
                context.images[image_filename] = png_bytes
                image_map_rid[rel_id] = image_filename
                image_counter += 1
            except Exception as exc:
                # Fallback: keep original bytes/format if Pillow cannot read (e.g., unsupported WMF)
                logger.warning("Image conversion to PNG failed – keeping original: %s", exc)
                ext = rel.target_ref.split('.')[-1].lower()
                image_filename = f"image_{image_counter}.{ext}"
                context.images[image_filename] = image_data
                image_map_rid[rel_id] = image_filename
                image_counter += 1
    return image_map_rid 