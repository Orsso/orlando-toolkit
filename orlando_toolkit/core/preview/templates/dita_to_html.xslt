<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="html" indent="yes"/>

  <!-- Shared color resolution template -->
  <xsl:template name="resolve-color-style">
    <xsl:param name="outputclass"/>
    <xsl:choose>
      <!-- COLOR_MAPPINGS_PLACEHOLDER -->
      <xsl:otherwise/>
    </xsl:choose>
  </xsl:template>

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
      <xsl:call-template name="resolve-color-style">
        <xsl:with-param name="outputclass" select="$oc"/>
      </xsl:call-template>
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

  <!-- xref (namespace-agnostic) to HTML anchor -->
  <xsl:template match="*[local-name()='xref']">
    <xsl:variable name="href" select="@href"/>
    <xsl:variable name="scope" select="@scope"/>
    <a>
      <xsl:attribute name="href"><xsl:value-of select="$href"/></xsl:attribute>
      <!-- Open external links in new tab/window to avoid navigating inside preview -->
      <xsl:if test="$scope='external' or starts-with($href,'http://') or starts-with($href,'https://')">
        <xsl:attribute name="target">_blank</xsl:attribute>
        <xsl:attribute name="rel">noopener noreferrer</xsl:attribute>
      </xsl:if>
      <xsl:apply-templates/>
    </a>
  </xsl:template>

  <!-- inline phrase (namespace-agnostic) maps to span with colour styles -->
  <xsl:template match="*[local-name()='ph']">
    <xsl:variable name="oc" select="@outputclass"/>
    <xsl:variable name="colorStyle">
      <xsl:call-template name="resolve-color-style">
        <xsl:with-param name="outputclass" select="$oc"/>
      </xsl:call-template>
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
      <xsl:call-template name="resolve-color-style">
        <xsl:with-param name="outputclass" select="$oc"/>
      </xsl:call-template>
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
    <!-- Column width from matching colspec when single-column cell -->
    <xsl:variable name="cw" select="ancestor::*[local-name()='tgroup']/*[local-name()='colspec'][@colname=current()/@colname]/@colwidth"/>
    <!-- Header detection: thead OR row marked as header-row via outputclass -->
    <xsl:variable name="isHeader" select="boolean(ancestor::*[local-name()='thead']) or boolean(ancestor::*[local-name()='row'][contains(@outputclass,'header-row')])"/>
    <xsl:variable name="oc" select="@outputclass"/>
    <xsl:variable name="colorStyle">
      <xsl:call-template name="resolve-color-style">
        <xsl:with-param name="outputclass" select="$oc"/>
      </xsl:call-template>
    </xsl:variable>
    <!-- Compute HTML spans from CALS attributes -->
    <xsl:variable name="rowspan">
      <xsl:choose>
        <xsl:when test="@morerows"><xsl:value-of select="number(@morerows) + 1"/></xsl:when>
        <xsl:otherwise>1</xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <xsl:variable name="colspan">
      <xsl:choose>
        <xsl:when test="@namest and @nameend">
          <xsl:value-of select="number(substring-after(@nameend,'column-')) - number(substring-after(@namest,'column-')) + 1"/>
        </xsl:when>
        <xsl:otherwise>1</xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <!-- Map DITA @valign to CSS vertical-align -->
    <xsl:variable name="vAlign">
      <xsl:choose>
        <xsl:when test="@valign='middle'">middle</xsl:when>
        <xsl:when test="@valign='bottom'">bottom</xsl:when>
        <xsl:otherwise>top</xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <xsl:choose>
      <xsl:when test="$isHeader">
        <th>
          <!-- Apply spans when greater than 1 -->
          <xsl:if test="$rowspan &gt; 1"><xsl:attribute name="rowspan"><xsl:value-of select="$rowspan"/></xsl:attribute></xsl:if>
          <xsl:if test="$colspan &gt; 1"><xsl:attribute name="colspan"><xsl:value-of select="$colspan"/></xsl:attribute></xsl:if>
          <xsl:attribute name="style">
            <xsl:text>border:1px solid #888;padding:4px;text-align:left;background:#f6f6f6;vertical-align:</xsl:text><xsl:value-of select="$vAlign"/><xsl:text>;</xsl:text>
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
          <!-- Apply spans when greater than 1 -->
          <xsl:if test="$rowspan &gt; 1"><xsl:attribute name="rowspan"><xsl:value-of select="$rowspan"/></xsl:attribute></xsl:if>
          <xsl:if test="$colspan &gt; 1"><xsl:attribute name="colspan"><xsl:value-of select="$colspan"/></xsl:attribute></xsl:if>
          <xsl:attribute name="style">
            <xsl:text>border:1px solid #888;padding:4px;vertical-align:</xsl:text><xsl:value-of select="$vAlign"/><xsl:text>;</xsl:text>
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