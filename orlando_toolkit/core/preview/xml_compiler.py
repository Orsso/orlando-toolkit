from __future__ import annotations

"""Utilities for on-the-fly XML preview of topic fragments.

This module is **read-only** and has *no* GUI dependencies.  It relies only on
``lxml`` and the public :class:`orlando_toolkit.core.models.DitaContext` API so
that it can be reused in tests, CLI tools or future features.
"""

from typing import Optional, TYPE_CHECKING
from lxml import etree as ET  # type: ignore
import os
from orlando_toolkit.config import ConfigManager

if TYPE_CHECKING:  # pragma: no cover - for type checkers only
    from orlando_toolkit.core.models import DitaContext  # noqa: F401

__all__ = [
    "get_raw_topic_xml",
    "render_html_preview",
]




def _load_xslt_template_with_colors() -> str:
    """Load XSLT template and inject dynamic color mappings from config."""
    # Get path to template file
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    template_path = os.path.join(template_dir, 'dita_to_html.xslt')
    
    with open(template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()
    
    # Generate XSLT color mappings
    color_mappings_xslt = _generate_color_mappings_xslt()
    
    # Inject color mappings into template
    return template_content.replace('<!-- COLOR_MAPPINGS_PLACEHOLDER -->', color_mappings_xslt)


def _generate_color_mappings_xslt() -> str:
    """Generate XSLT when clauses for color mappings from config only."""
    config_manager = ConfigManager()
    color_rules = config_manager.get_color_rules() or {}
    
    # Get CSS styles from config
    css_styles = color_rules.get("css_styles", {})
    
    # Generate XSLT when clauses directly from config
    xslt_lines = []
    for outputclass, css_style in css_styles.items():
        xslt_lines.append(f'            <xsl:when test="contains($outputclass,\'{outputclass}\')">{css_style}</xsl:when>')
    
    return '\n'.join(xslt_lines)






# ---------------------------------------------------------------------------
# RAW topic extractor
# ---------------------------------------------------------------------------


def get_raw_topic_xml(ctx: "DitaContext", tref: ET.Element, *, pretty: bool = True) -> str:  # noqa: D401
    """Return the full topic XML linked by *tref* (body content)."""

    href = tref.get("href")
    if href and href.startswith("topics/"):
        topic_fname = href.split("/")[-1]
        topic_el = ctx.topics.get(topic_fname)
        if topic_el is not None:
            xml_bytes = ET.tostring(topic_el, pretty_print=pretty, encoding="utf-8")
            return xml_bytes.decode("utf-8")

    # Structural heading only – return minimal representation
    title_el = tref.find("topicmeta/navtitle")
    title_txt = title_el.text if title_el is not None else "(untitled)"
    temp = ET.Element("topichead")
    ET.SubElement(temp, "title").text = title_txt
    return ET.tostring(temp, pretty_print=pretty, encoding="unicode")


# ---------------------------------------------------------------------------
# Raw topic + HTML renderer
# ---------------------------------------------------------------------------

def render_html_preview(ctx: "DitaContext", tref: ET.Element, *, pretty: bool = True) -> str:  # noqa: D401
    """Return simple HTML preview for the selected heading/topic.

    Uses an internal minimal XSLT transform so we avoid external
    dependencies and keep the codebase self-contained.
    """

    xml_str = get_raw_topic_xml(ctx, tref, pretty=False)

    # Ensure images resolve in HTML preview by materializing them to temp files
    # and updating hrefs to file URIs (works reliably with tkinterweb).
    try:
        tree = ET.fromstring(xml_str.encode())

        import mimetypes
        import hashlib
        from pathlib import Path
        from orlando_toolkit.core.session_storage import get_session_storage

        # 1) Ensure merged-title paragraphs render in uppercase even in limited HTML engines
        def _uppercase_text_nodes(el: ET.Element) -> None:
            try:
                if el.text:
                    el.text = el.text.upper()
            except Exception:
                pass
            for child in list(el):
                _uppercase_text_nodes(child)
                try:
                    if child.tail:
                        child.tail = child.tail.upper()
                except Exception:
                    pass

        try:
            for p in tree.xpath(".//p[contains(@outputclass, 'merged-title')]"):
                _uppercase_text_nodes(p)
        except Exception:
            pass

        # 2) Convert embedded images to session temp files and point to file URIs
        for img in tree.findall('.//image'):
            href = img.get('href', '')
            fname = Path(href).name
            if fname in getattr(ctx, 'images', {}):
                blob = ctx.images[fname]  # type: ignore[attr-defined]
                mime, _ = mimetypes.guess_type(fname)
                mime = mime or 'image/png'
                # Stable name per content hash
                h = hashlib.md5(blob).hexdigest()[:12]
                ext = (mime.split('/')[-1] if '/' in mime else 'png')
                if ext == 'jpeg':
                    ext = 'jpg'
                storage = get_session_storage()
                out_path = storage.ensure_image_written(f"img_{h}.{ext}", blob)
                img.set('href', out_path.as_uri())

        xml_str = ET.tostring(tree, encoding='unicode')
    except Exception:
        # Fallback: leave hrefs untouched
        pass

    # Load and prepare XSLT with dynamic color mappings
    xslt_content = _load_xslt_template_with_colors()

    xslt_root = ET.XML(xslt_content.encode())  # type: ignore[arg-type]
    transform = ET.XSLT(xslt_root)  # type: ignore[call-arg]
    src = ET.fromstring(xml_str.encode())
    res = transform(src)
    html_content = str(res)
    return html_content