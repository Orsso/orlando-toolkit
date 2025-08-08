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

        # 2) Convert embedded images to data URIs for portability within preview
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

      <!-- root concept/topic/topichead wrapper (namespace-agnostic) -->
      <xsl:template match="*[local-name()='concept' or local-name()='topic' or local-name()='topichead']">
        <div class="topic">
          <h2><xsl:apply-templates select="*[local-name()='title']/node()"/></h2>
          <xsl:apply-templates/>
        </div>
      </xsl:template>

      <!-- Suppress default output of title elements after we've rendered header above -->
      <xsl:template match="*[local-name()='title']"/>

      <!-- paragraphs (namespace-agnostic) -->
      <xsl:template match="*[local-name()='p']">
        <xsl:variable name="oc" select="@outputclass"/>
        <xsl:variable name="colorStyle">
          <xsl:choose>
            <xsl:when test="contains($oc,'background-red')">background-color:#ffd6d6;</xsl:when>
            <xsl:when test="contains($oc,'background-green')">background-color:#e2f4e2;</xsl:when>
            <xsl:when test="contains($oc,'red')">color:#b00000;</xsl:when>
            <xsl:when test="contains($oc,'green')">color:#116611;</xsl:when>
            <xsl:otherwise/>
          </xsl:choose>
        </xsl:variable>
        <xsl:variable name="mergedStyle">
          <xsl:if test="contains($oc,'merged-title')">text-transform:uppercase;font-weight:bold;text-decoration:underline;</xsl:if>
        </xsl:variable>
        <p>
          <xsl:attribute name="style">
            <xsl:text>margin: 8px 0; line-height: 1.4;</xsl:text>
            <xsl:value-of select="$colorStyle"/>
            <xsl:value-of select="$mergedStyle"/>
          </xsl:attribute>
          <xsl:apply-templates/>
        </p>
      </xsl:template>

      <!-- inline phrase (namespace-agnostic) maps to span with colour styles -->
      <xsl:template match="*[local-name()='ph']">
        <xsl:variable name="oc" select="@outputclass"/>
        <xsl:variable name="colorStyle">
          <xsl:choose>
            <xsl:when test="contains($oc,'background-red')">background-color:#ffd6d6;</xsl:when>
            <xsl:when test="contains($oc,'background-green')">background-color:#e2f4e2;</xsl:when>
            <xsl:when test="contains($oc,'red')">color:#b00000;</xsl:when>
            <xsl:when test="contains($oc,'green')">color:#116611;</xsl:when>
            <xsl:otherwise/>
          </xsl:choose>
        </xsl:variable>
        <span>
          <xsl:if test="$colorStyle">
            <xsl:attribute name="style"><xsl:value-of select="$colorStyle"/></xsl:attribute>
          </xsl:if>
          <xsl:apply-templates/>
        </span>
      </xsl:template>

      <!-- Avoid invalid HTML: if a paragraph contains a table, render a div wrapper instead -->
      <xsl:template match="*[local-name()='p'][.//*[local-name()='table' or local-name()='simpletable']]">
        <div style="margin:8px 0;">
          <xsl:apply-templates/>
        </div>
      </xsl:template>

      <!-- unordered list (ul/li) -->
      <xsl:template match="*[local-name()='ul']">
        <ul><xsl:apply-templates/></ul>
      </xsl:template>
      <xsl:template match="*[local-name()='li']">
        <xsl:variable name="oc" select="@outputclass"/>
        <xsl:variable name="colorStyle">
          <xsl:choose>
            <xsl:when test="contains($oc,'background-red')">background-color:#ffd6d6;</xsl:when>
            <xsl:when test="contains($oc,'background-green')">background-color:#e2f4e2;</xsl:when>
            <xsl:when test="contains($oc,'red')">color:#b00000;</xsl:when>
            <xsl:when test="contains($oc,'green')">color:#116611;</xsl:when>
            <xsl:otherwise/>
          </xsl:choose>
        </xsl:variable>
        <li>
          <xsl:attribute name="style"><xsl:value-of select="$colorStyle"/></xsl:attribute>
          <xsl:apply-templates/>
        </li>
      </xsl:template>

      <!-- table rendering (incl. simpletable), namespace-agnostic -->
      <xsl:template match="*[local-name()='table' or local-name()='simpletable']">
        <table border="1" cellpadding="4" cellspacing="0" width="100%" style="border-collapse:collapse;border:1px solid #888;font-size:90%;">
          <xsl:apply-templates/>
        </table>
      </xsl:template>
      <!-- thead/tbody wrappers when present -->
      <xsl:template match="*[local-name()='thead']">
        <thead><xsl:apply-templates/></thead>
      </xsl:template>
      <xsl:template match="*[local-name()='tbody']">
        <tbody><xsl:apply-templates/></tbody>
      </xsl:template>

      <xsl:template match="*[local-name()='row' or local-name()='strow']">
        <tr><xsl:apply-templates/></tr>
      </xsl:template>
      <xsl:template match="*[local-name()='entry' or local-name()='stentry']">
        <xsl:variable name="cw" select="ancestor::*[local-name()='tgroup']/*[local-name()='colspec'][@colname=current()/@colname]/@colwidth"/>
        <xsl:variable name="isHeader" select="boolean(ancestor::*[local-name()='thead'])"/>
        <xsl:variable name="oc" select="@outputclass"/>
        <xsl:variable name="colorStyle">
          <xsl:choose>
            <xsl:when test="contains($oc,'background-red')">background-color:#ffd6d6;</xsl:when>
            <xsl:when test="contains($oc,'background-green')">background-color:#e2f4e2;</xsl:when>
            <xsl:when test="contains($oc,'red')">color:#b00000;</xsl:when>
            <xsl:when test="contains($oc,'green')">color:#116611;</xsl:when>
            <xsl:otherwise/>
          </xsl:choose>
        </xsl:variable>
        <xsl:choose>
          <xsl:when test="$isHeader">
            <th>
              <xsl:attribute name="style">
                <xsl:text>border:1px solid #888;padding:4px;text-align:left;vertical-align:top;background:#f6f6f6;</xsl:text>
                <xsl:value-of select="$colorStyle"/>
                <xsl:if test="$cw and string-length(normalize-space($cw)) &gt; 0">
                  <xsl:text>width:</xsl:text><xsl:value-of select="$cw"/><xsl:text>;</xsl:text>
                </xsl:if>
              </xsl:attribute>
              <xsl:if test="$cw and string-length(normalize-space($cw)) &gt; 0">
                <xsl:attribute name="width"><xsl:value-of select="$cw"/></xsl:attribute>
              </xsl:if>
              <xsl:apply-templates/>
            </th>
          </xsl:when>
          <xsl:otherwise>
            <td>
              <xsl:attribute name="style">
                <xsl:text>border:1px solid #888;padding:4px;vertical-align:top;</xsl:text>
                <xsl:value-of select="$colorStyle"/>
                <xsl:if test="$cw and string-length(normalize-space($cw)) &gt; 0">
                  <xsl:text>width:</xsl:text><xsl:value-of select="$cw"/><xsl:text>;</xsl:text>
                </xsl:if>
              </xsl:attribute>
              <xsl:if test="$cw and string-length(normalize-space($cw)) &gt; 0">
                <xsl:attribute name="width"><xsl:value-of select="$cw"/></xsl:attribute>
              </xsl:if>
              <xsl:apply-templates/>
            </td>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:template>

      <!-- images -->
      <xsl:template match="*[local-name()='image']">
        <img src="{@href}" alt="image"/>
      </xsl:template>

      <!-- drop metadata elements we don't need (keep title handled above) -->
      <xsl:template match="@id|*[local-name()='topicmeta' or local-name()='critdates' or local-name()='othermeta']"/>

      <!-- Drop intermediary CALS wrapper tgroup and colspec; keep thead/tbody handled above -->
      <xsl:template match="*[local-name()='tgroup' or local-name()='colspec']">
        <xsl:apply-templates/>
      </xsl:template>
    </xsl:stylesheet>
    """

    xslt_root = ET.XML(_XSLT)  # type: ignore[arg-type]
    transform = ET.XSLT(xslt_root)  # type: ignore[call-arg]
    src = ET.fromstring(xml_str.encode())
    res = transform(src)
    html_content = str(res)
    
    # Apply inline styles directly to elements for tkhtmlview compatibility
    # tkhtmlview doesn't fully support <style> tags, so we post-process to add inline styles
    
    try:
        # Utility: transform HTML tables to div-based layout for better tkhtmlview compatibility
        # Many tkhtmlview builds do not render <table>/<tr>/<td> correctly. We convert them
        # into a nested <div> structure using inline-block cells with borders and widths.
        # Skip this conversion when a full HTML engine (tkinterweb) is likely in use by keeping
        # standard tables. Rely on caller widget to choose the renderer.
        from lxml import html as LH  # type: ignore
        
        # Simple approach: just return the HTML content with basic formatting
        # tkhtmlview will handle basic HTML tags without complex CSS
        
        # Add some basic inline styling to improve readability
        def _convert_tables_to_divs(html: str) -> str:
            try:
                doc = LH.fromstring(html)
            except Exception:
                return html

            # Iterate over all tables
            for table in doc.xpath('//table'):
                # Build div.table container
                div_table = LH.Element('div')
                div_table.set('style', 'display:block;border:1px solid #888;margin:8px 0;')

                # Gather rows (<tr>)
                rows = table.xpath('.//tr')
                for tr in rows:
                    div_row = LH.SubElement(div_table, 'div')
                    # Using nowrap to keep cells on the same line; inline-block cells wrap if too narrow
                    div_row.set('style', 'white-space:nowrap;')

                    # Cells: td or th
                    cells = tr.xpath('./td|./th')
                    for cell in cells:
                        # Extract inline width from style if present (e.g., 'width:30.5%;')
                        style_attr = cell.get('style') or ''
                        width_val = ''
                        if 'width:' in style_attr:
                            try:
                                # crude parse: find substring between 'width:' and next ';'
                                after = style_attr.split('width:', 1)[1]
                                width_val = after.split(';', 1)[0].strip()
                            except Exception:
                                width_val = ''

                        # Build cell div with borders and padding
                        cell_div = LH.SubElement(div_row, 'div')
                        base_style = 'display:inline-block;vertical-align:top;border:1px solid #888;padding:4px;margin:-1px 0 0 -1px;'
                        if width_val:
                            cell_div.set('style', base_style + f'width:{width_val};')
                        else:
                            cell_div.set('style', base_style)

                        # Move children of cell into the cell_div (preserve formatting)
                        try:
                            for child in list(cell):
                                cell.remove(child)
                                cell_div.append(child)
                            # Also carry over tail text if any
                            if cell.text and cell.text.strip():
                                # Wrap plain text in <span> to ensure it's displayed
                                span = LH.SubElement(cell_div, 'span')
                                span.text = cell.text
                                cell.text = None
                        except Exception:
                            pass

                # Replace table with div_table in the document
                try:
                    table.getparent().replace(table, div_table)
                except Exception:
                    # If replace fails, skip this table
                    continue

            try:
                return LH.tostring(doc, encoding='unicode')
            except Exception:
                return html

        styled_content = _convert_tables_to_divs(html_content)
        
        # Replace div.topic with styled div
        styled_content = styled_content.replace('<div class="topic">', 
                                              '<div style="margin-bottom: 20px;">')
        
        # Style headings with inline styles
        styled_content = styled_content.replace('<h1>', '<h1 style="color: #2c3e50; font-size: 1.6em; margin: 16px 0 8px 0;">')
        styled_content = styled_content.replace('<h2>', '<h2 style="color: #2c3e50; font-size: 1.4em; margin: 14px 0 6px 0;">')
        styled_content = styled_content.replace('<h3>', '<h3 style="color: #2c3e50; font-size: 1.2em; margin: 12px 0 4px 0;">')
        
        # Style paragraphs
        styled_content = styled_content.replace('<p>', '<p style="margin: 8px 0; line-height: 1.4;">')
        
        # Handle images - tkhtmlview doesn't support data URIs, so save images temporarily
        import re
        import tempfile
        import os
        from pathlib import Path
        
        def replace_data_uri_images(match):
            # Extract the data URI
            src_match = re.search(r'src=["\']([^"\']*)["\']', match.group(0))
            if not src_match:
                return match.group(0)
                
            data_uri = src_match.group(1)
            if not data_uri.startswith('data:'):
                return match.group(0)  # Not a data URI, keep as is
            
            try:
                # Parse data URI: data:image/png;base64,<data>
                header, data = data_uri.split(',', 1)
                mime_part = header.split(':')[1].split(';')[0]  # e.g., 'image/png'
                
                # Get file extension from mime type
                ext = mime_part.split('/')[-1] if '/' in mime_part else 'png'
                if ext == 'jpeg':
                    ext = 'jpg'
                
                # Decode base64 data
                import base64
                image_data = base64.b64decode(data)
                
                # Create temporary file for this image
                temp_dir = tempfile.gettempdir()
                preview_dir = os.path.join(temp_dir, 'orlando_preview')
                os.makedirs(preview_dir, exist_ok=True)
                
                # Generate unique filename
                import hashlib
                hash_obj = hashlib.md5(image_data)
                filename = f"img_{hash_obj.hexdigest()[:8]}.{ext}"
                filepath = os.path.join(preview_dir, filename)
                
                # Save image file
                with open(filepath, 'wb') as f:
                    f.write(image_data)
                
                # Replace data URI with file path
                new_img_tag = match.group(0).replace(data_uri, filepath)
                return new_img_tag
                
            except Exception:
                # Fallback: use placeholder if image processing fails
                alt_text = re.search(r'alt=["\']([^"\']*)["\']', match.group(0))
                alt = alt_text.group(1) if alt_text else 'Image'
                return f'<span style="background-color: #f0f0f0; padding: 4px 8px; border: 1px dashed #ccc; color: #666; font-style: italic;">[Image: {alt}]</span>'
        
        # Replace data URI images with temporary file paths
        styled_content = re.sub(r'<img[^>]*src=["\']data:[^"\']*["\'][^>]*/?>', replace_data_uri_images, styled_content)
        
        # Additional inline styling replacements
        
        return styled_content
        
    except Exception:
        # Fallback: return original content if post-processing fails
        return html_content 