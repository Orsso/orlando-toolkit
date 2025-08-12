from __future__ import annotations

"""Low-level DOCX utilities shared by the converter.

Extracted from the original *docx_to_dita_converter.py* to allow unit‐testing
and reuse without GUI dependencies.
"""

from typing import Dict, Generator
import io
import logging
import requests
from urllib.parse import urlparse

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

def download_external_image(url: str) -> tuple[bytes, str] | None:
    """Download external image and return (data, extension) or None if failed."""
    try:
        response = requests.get(url, timeout=10, headers={'User-Agent': 'Orlando-Toolkit'})
        response.raise_for_status()
        
        # Try to get extension from URL or Content-Type
        parsed_url = urlparse(url)
        ext = parsed_url.path.split('.')[-1].lower() if '.' in parsed_url.path else ''
        
        if not ext:
            content_type = response.headers.get('content-type', '').lower()
            if 'jpeg' in content_type or 'jpg' in content_type:
                ext = 'jpg'
            elif 'png' in content_type:
                ext = 'png'
            elif 'gif' in content_type:
                ext = 'gif'
            elif 'webp' in content_type:
                ext = 'webp'
            else:
                ext = 'jpg'  # Default fallback
                
        return response.content, ext
        
    except Exception as e:
        domain = url.split('/')[2] if len(url.split('/')) > 2 else 'unknown'
        logger.debug(f"Failed to download external image from {domain}: {e}")
        return None


def extract_images_to_context(doc: _Document, context: DitaContext) -> Dict[str, str]:
    """Populate *context.images* with image bytes and return rid→filename map."""
    
    # First, collect all relationship data for quick lookup
    rel_data: Dict[str, tuple[bytes, str]] = {}
    for rel_id, rel in doc.part.rels.items():
        if "image" in rel.target_ref:
            if rel.is_external:
                # Handle external image (download it)
                domain = rel.target_ref.split('/')[2] if len(rel.target_ref.split('/')) > 2 else 'unknown'
                logger.info(f"Downloading external image from {domain}...")
                result = download_external_image(rel.target_ref)
                if result:
                    image_data, ext = result
                    rel_data[rel_id] = (image_data, ext)
                else:
                    logger.debug(f"Skipping external image that couldn't be downloaded: {rel.target_ref}")
            else:
                # Handle embedded image (existing logic)
                image_data = rel.target_part.blob
                ext = rel.target_ref.split('.')[-1].lower()
                rel_data[rel_id] = (image_data, ext)
    
    # Now walk through document in order to collect image relationship IDs as they appear
    image_map_rid: Dict[str, str] = {}
    image_counter = 1
    processed_rids = set()
    
    # Walk through document content in order
    for block in iter_block_items(doc):
        if isinstance(block, Paragraph):
            for run in block.runs:
                r_ids = run.element.xpath(".//@r:embed")
                for r_id in r_ids:
                    if r_id in rel_data and r_id not in processed_rids:
                        processed_rids.add(r_id)
                        image_data, ext = rel_data[r_id]
                        
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
                            image_map_rid[r_id] = image_filename
                            image_counter += 1
                        except Exception as exc:
                            # Fallback: keep original bytes/format if Pillow cannot read (e.g., unsupported WMF)
                            logger.debug("Image conversion to PNG failed – keeping original: %s", exc)
                            image_filename = f"image_{image_counter}.{ext}"
                            context.images[image_filename] = image_data
                            image_map_rid[r_id] = image_filename
                            image_counter += 1
                            
        # Handle images in table cells
        elif isinstance(block, Table):
            for row in block.rows:
                for cell in row.cells:
                    for cell_block in iter_block_items(cell):
                        if isinstance(cell_block, Paragraph):
                            for run in cell_block.runs:
                                r_ids = run.element.xpath(".//@r:embed")
                                for r_id in r_ids:
                                    if r_id in rel_data and r_id not in processed_rids:
                                        processed_rids.add(r_id)
                                        image_data, ext = rel_data[r_id]
                                        
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
                                            image_map_rid[r_id] = image_filename
                                            image_counter += 1
                                        except Exception as exc:
                                            # Fallback: keep original bytes/format if Pillow cannot read (e.g., unsupported WMF)
                                            logger.debug("Image conversion to PNG failed – keeping original: %s", exc)
                                            image_filename = f"image_{image_counter}.{ext}"
                                            context.images[image_filename] = image_data
                                            image_map_rid[r_id] = image_filename
                                            image_counter += 1
    
    return image_map_rid 