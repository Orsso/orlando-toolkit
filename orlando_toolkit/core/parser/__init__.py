from __future__ import annotations

"""Word-processing parser helpers.

Currently provides DOCX traversal and image extraction utilities used by the
conversion pipeline.
"""

from .docx_utils import iter_block_items, extract_images_to_context  # noqa: F401
from .style_analyzer import build_style_heading_map  # noqa: F401

__all__: list[str] = [
    "iter_block_items",
    "extract_images_to_context",
    "build_style_heading_map",
] 