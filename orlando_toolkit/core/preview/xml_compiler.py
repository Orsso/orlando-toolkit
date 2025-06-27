from __future__ import annotations

"""Utilities for on-the-fly XML preview of topic fragments.

This module is **read-only** and has *no* GUI dependencies.  It relies only on
``lxml`` and the public :class:`orlando_toolkit.core.models.DitaContext` API so
that it can be reused in tests, CLI tools or future features.
"""

from copy import deepcopy
from typing import Optional
from lxml import etree as ET  # type: ignore

if False:  # TYPE_CHECKING pragma
    from orlando_toolkit.core.models import DitaContext  # noqa: F401

__all__ = [
    "get_raw_topic_xml",
    "render_html_preview",
]


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

    # Embed images as data URIs so the HTML preview can show them
    try:
        tree = ET.fromstring(xml_str.encode())

        import base64, mimetypes
        from pathlib import Path

        for img in tree.findall('.//image'):
            href = img.get('href', '')
            fname = Path(href).name
            if fname in getattr(ctx, 'images', {}):
                blob = ctx.images[fname]  # type: ignore[attr-defined]
                b64 = base64.b64encode(blob).decode()
                mime, _ = mimetypes.guess_type(fname)
                mime = mime or 'image/png'
                img.set('href', f'data:{mime};base64,{b64}')

        xml_str = ET.tostring(tree, encoding='unicode')
    except Exception:
        # Fallback: leave hrefs untouched
        pass

    # Basic XSLT (hard-coded) – converts p, ul/li, table, image
    _XSLT = """
    <xsl:stylesheet version="1.0"
        xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
      <xsl:output method="html" indent="yes"/>

      <!-- Copy everything by default -->
      <xsl:template match="@*|node()">
        <xsl:copy>
          <xsl:apply-templates select="@*|node()"/>
        </xsl:copy>
      </xsl:template>

      <!-- root concept/ topichead wrapper -->
      <xsl:template match="concept|topichead">
        <div class="topic">
          <h2><xsl:value-of select="title"/></h2>
          <xsl:apply-templates/>
        </div>
      </xsl:template>

      <!-- paragraphs -->
      <xsl:template match="p">
        <p><xsl:apply-templates/></p>
      </xsl:template>

      <!-- unordered list (ul/li) -->
      <xsl:template match="ul">
        <ul><xsl:apply-templates/></ul>
      </xsl:template>
      <xsl:template match="li">
        <li><xsl:apply-templates/></li>
      </xsl:template>

      <!-- table rendering (incl. simpletable) -->
      <xsl:template match="table|simpletable">
        <table style="border-collapse:collapse;width:100%;border:1px solid #888;font-size:90%;">
          <xsl:apply-templates/>
        </table>
      </xsl:template>
      <xsl:template match="row|strow">
        <tr><xsl:apply-templates/></tr>
      </xsl:template>
      <xsl:template match="entry|stentry">
        <td style="border:1px solid #888;padding:4px;vertical-align:top;">
          <xsl:apply-templates/>
        </td>
      </xsl:template>

      <!-- images -->
      <xsl:template match="image">
        <img src="{@href}" alt="image"/>
      </xsl:template>

      <!-- drop metadata elements we don't need -->
      <xsl:template match="@id|title|topicmeta|critdates|othermeta"/>

      <!-- Drop intermediary CALS wrappers -->
      <xsl:template match="tgroup|thead|tbody|colspec">
        <xsl:apply-templates/>
      </xsl:template>
    </xsl:stylesheet>
    """

    xslt_root = ET.XML(_XSLT)  # type: ignore[arg-type]
    transform = ET.XSLT(xslt_root)  # type: ignore[call-arg]
    src = ET.fromstring(xml_str.encode())
    res = transform(src)
    html = str(res)
    return html 