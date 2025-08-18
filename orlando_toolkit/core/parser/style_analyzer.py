from __future__ import annotations

"""Utility functions for analysing Word styles to infer heading hierarchy.

This module implements the same logic as Word's Navigation Pane to detect heading
styles reliably. It resolves style inheritance chains and applies heuristics to
identify custom heading styles that should appear in document structure.
"""

from typing import Dict
import re
import logging

from docx.document import Document  # type: ignore
from docx.enum.style import WD_STYLE_TYPE  # type: ignore

logger = logging.getLogger(__name__)

# Namespaces used in WordprocessingML
_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

# Numbering formats that clearly denote ordered headings (bullets are excluded)
_HEADING_NUMFMTS = {
    "decimal",
    "decimalZero",
    "upperRoman",
    "lowerRoman",
    "upperLetter",
    "lowerLetter",
    "roman",
    "alpha",
}

# Centralized heading detection patterns
_BUILTIN_HEADING_PATTERN = re.compile(r"^Heading\s+(\d+)$", re.IGNORECASE)
_GENERIC_HEADING_PATTERN = re.compile(r"\b(?:heading|titre)[ _]?(\d)\b", re.IGNORECASE)


def _is_ordered_numfmt(numfmt: str | None) -> bool:
    """Return True if *numfmt* is a numbering format typically used for ordered headings."""
    return bool(numfmt and numfmt in _HEADING_NUMFMTS)


def _detect_builtin_heading_level(style_name: str) -> int | None:
    """Detect level for built-in Word heading styles (Heading 1, Heading 2, etc.)."""
    if not style_name:
        return None
    match = _BUILTIN_HEADING_PATTERN.match(style_name)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return None


def _detect_generic_heading_level(style_name: str) -> int | None:
    """Detect level from generic heading patterns (case-insensitive)."""
    if not style_name:
        return None
    match = _GENERIC_HEADING_PATTERN.search(style_name)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return None


def build_style_heading_map(doc: Document) -> Dict[str, int]:
    """Return a mapping {style_name: heading_level} using Word Navigation Pane logic.

    This function reproduces the exact algorithm Word uses to determine which styles
    appear in the Navigation Pane. It resolves style inheritance chains and applies
    the same heuristics as Microsoft Word.

    Strategy (by priority):
    1. Explicit outline level in style definition (w:outlineLvl)
    2. Inherited outline level via style chain resolution (w:basedOn)
    3. Built-in heading styles ("Heading 1", "Heading 2", etc.)
    4. Ordered numbering format detection (decimal, roman, alpha)

    Returns:
        Dict mapping style names to heading levels (1-9), or empty dict on failure.
    """
    style_map: Dict[str, int] = {}
    
    try:
        # Build style lookup for inheritance resolution
        style_elements = {}
        for style in doc.styles:
            if style.type == WD_STYLE_TYPE.PARAGRAPH and style.name:
                try:
                    style_elements[style.name] = style._element
                except Exception:
                    continue
        
        # Process each paragraph style
        for style_name, style_el in style_elements.items():
            try:
                level = _resolve_heading_level(style_el, style_name, style_elements, doc)
                if level:
                    style_map[style_name] = level
            except Exception:
                # Never crash on individual style errors
                continue
                
    except Exception:
        # Return empty dict to allow fallback to defaults
        pass
    
    return style_map


def build_enhanced_style_map(doc: Document, use_structural_analysis: bool = True, min_following_paragraphs: int = 3) -> Dict[str, int]:
    """Enhanced style detection using structural analysis.
    
    Combines standard OpenXML detection with content pattern analysis
    to identify custom heading styles.
    
    Args:
        doc: Word document to analyze
        use_structural_analysis: Whether to analyze paragraph following patterns
        min_following_paragraphs: Minimum average following paragraphs for structural detection
        
    Returns:
        Mapping of style names to heading levels
    """
    base_map = build_style_heading_map(doc)
    logger.debug(f"Style detection: base={len(base_map)}")
    
    enhanced_map = dict(base_map)
    
    if use_structural_analysis:
        try:
            structural_styles = _analyze_structural_patterns(doc, min_following_paragraphs)
            logger.debug(f"Style detection: structural={len(structural_styles)}")
            
            for style_name, level in structural_styles.items():
                if style_name not in enhanced_map:
                    enhanced_map[style_name] = level
                    
        except Exception as e:
            logger.warning(f"Structural analysis failed: {e}")
    
    logger.debug(f"Style detection: enhanced_total={len(enhanced_map)}")
    return enhanced_map 

def _resolve_heading_level(style_el, style_name: str, style_elements: dict, doc: Document) -> int | None:
    """Resolve heading level for a style using Word's complete algorithm."""
    
    # 1. Direct outline level
    outline_vals = _xp(style_el, "./w:pPr/w:outlineLvl/@w:val")
    if outline_vals:
        try:
            return int(outline_vals[0]) + 1  # Word uses 0-8, we return 1-9
        except ValueError:
            pass
    
    # 2. Style inheritance chain resolution
    inherited_level = _resolve_style_chain(style_el, style_name, style_elements, set())
    if inherited_level:
        return inherited_level
    
    # 3. Built-in heading styles (Word's special logic)
    builtin_level = _detect_builtin_heading_level(style_name)
    if builtin_level:
        return builtin_level
    
    # 4. Numbering-based detection
    return _detect_numbering_heading(style_el, doc)


def _resolve_style_chain(style_el, current_name: str, style_elements: dict, visited: set) -> int | None:
    """Recursively resolve style inheritance chain to find outline level."""
    
    if current_name in visited:  # Prevent cycles
        return None
    visited.add(current_name)
    
    # Check for basedOn reference
    based_vals = _xp(style_el, "./w:basedOn/@w:val")
    if not based_vals:
        return None
        
    parent_name = based_vals[0]
    parent_el = style_elements.get(parent_name)
    if parent_el is None:
        return None
    
    # Check parent's direct outline level
    outline_vals = _xp(parent_el, "./w:pPr/w:outlineLvl/@w:val")
    if outline_vals:
        try:
            return int(outline_vals[0]) + 1
        except ValueError:
            pass
    
    # Recurse up the chain
    return _resolve_style_chain(parent_el, parent_name, style_elements, visited)


def _detect_numbering_heading(style_el, doc: Document) -> int | None:
    """Detect heading level from numbering format (ordered sequences only)."""
    
    try:
        numbering_root = doc.part.numbering_part._element
    except Exception:
        return None
    
    numId_vals = _xp(style_el, "./w:pPr/w:numPr/w:numId/@w:val")
    if not numId_vals:
        return None
        
    numId = numId_vals[0]
    ilvl_vals = _xp(style_el, "./w:pPr/w:numPr/w:ilvl/@w:val")
    ilvl = ilvl_vals[0] if ilvl_vals else "0"
    
    # Resolve numbering format
    try:
        abs_ids = numbering_root.xpath(
            f'.//w:num[@w:numId="{numId}"]/w:abstractNumId/@w:val', 
            namespaces=_NS
        )
        if not abs_ids:
            return None
            
        abs_id = abs_ids[0]
        numfmts = numbering_root.xpath(
            f'.//w:abstractNum[@w:abstractNumId="{abs_id}"]/w:lvl[@w:ilvl="{ilvl}"]/w:numFmt/@w:val',
            namespaces=_NS
        )
        
        if numfmts and _is_ordered_numfmt(numfmts[0]):
            try:
                return int(ilvl) + 1
            except ValueError:
                return 1
                
    except Exception:
        pass
        
    return None


def _xp(el, path: str):
    """Namespace-agnostic XPath helper compatible with all python-docx versions."""
    try:
        return el.xpath(path, namespaces=_NS)
    except TypeError:
        try:
            return el.xpath(path, namespaces=getattr(el, "nsmap", None))
        except Exception:
            return el.xpath(path)




def _analyze_structural_patterns(doc: Document, min_following: int = 3) -> Dict[str, int]:
    """Identify heading styles by content patterns.
    
    Styles that consistently have multiple paragraphs following them
    are likely structural/heading styles.
    """
    structural_map = {}
    
    try:
        paragraphs = list(doc.paragraphs)
        style_analysis = {}
        
        # Analyze each paragraph and count following content
        for i, para in enumerate(paragraphs):
            if not para.style or not para.style.name or not para.text.strip():
                continue
                
            style_name = para.style.name
            
            # Skip non-structural styles
            if any(skip in style_name.lower() for skip in ['normal', 'default', 'list', 'toc', 'header', 'footer']):
                continue
                
            if style_name not in style_analysis:
                style_analysis[style_name] = {
                    'count': 0,
                    'total_following': 0,
                    'examples': []
                }
            
            style_analysis[style_name]['count'] += 1
            style_analysis[style_name]['examples'].append(para.text.strip()[:30])
            
            # Count paragraphs that follow until next instance of same style
            following_count = 0
            for j in range(i + 1, min(i + 20, len(paragraphs))):
                next_para = paragraphs[j]
                
                # Stop if we hit the same style again
                if (next_para.style and next_para.style.name == style_name and 
                    next_para.text.strip()):
                    break
                    
                # Count non-empty paragraphs  
                if next_para.text.strip():
                    following_count += 1
            
            style_analysis[style_name]['total_following'] += following_count
        
        # Identify structural styles based on criteria
        for style_name, data in style_analysis.items():
            if data['count'] == 0:
                continue
                
            avg_following = data['total_following'] / data['count']
            
            # Heuristics: consistently followed by content + appears multiple times
            is_structural = (
                avg_following >= min_following and
                (data['count'] >= 2 or avg_following >= min_following * 2)
            )
            
            if is_structural:
                level = _estimate_structural_level(style_name, avg_following)
                structural_map[style_name] = level
                
                logger.debug(f"Structural style: '{style_name}' -> level {level} "
                           f"(avg {avg_following:.1f} following, {data['count']} occurrences)")
    
    except Exception as e:
        logger.debug(f"Structural analysis error: {e}")
    
    return structural_map


def _estimate_structural_level(style_name: str, avg_following: float) -> int:
    """Estimate heading level for a structural style based on name patterns and content."""
    
    # Check for explicit level indicators in style name
    level_patterns = [
        (r'\b(?:titre|title|heading)\s*(?:principal|main)\b', 1),
        (r'\b(?:partie|part|section)\b', 1), 
        (r'\b(?:chapitre|chapter)\b', 2),
        (r'\b(?:sous[-\s]*chapitre|sub[-\s]*chapter)\b', 3),
        (r'\b(?:sous[-\s]*section|sub[-\s]*section)\b', 4),
    ]
    
    for pattern, level in level_patterns:
        if re.search(pattern, style_name, re.IGNORECASE):
            return level
    
    # Fallback: estimate based on amount of following content
    # More following content suggests higher-level (lower number) heading
    if avg_following >= 15:
        return 1
    elif avg_following >= 8:
        return 2
    elif avg_following >= 4:
        return 3
    else:
        return 4 