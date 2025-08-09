from __future__ import annotations

"""Heading analysis helpers for DITA map traversal (UI-agnostic).

This module centralizes traversal utilities used to compute heading-related
data for filters and diagnostics. It operates purely on in-memory
structures, accepts a :class:`DitaContext`, and returns plain Python
structures suitable for UI consumption.

Functions are conservative and resilient: unexpected data shapes or
environment differences lead to empty results rather than exceptions.
"""

from typing import Dict, List, Optional, Set, Tuple

from orlando_toolkit.core.models import DitaContext


def build_headings_cache(context: Optional[DitaContext]) -> Dict[str, int]:
    """Return counts of headings per style by traversing ``context.ditamap_root``.

    Style resolution priority:
      1) @data-style
      2) "Heading {data-level}" when @data-level exists
      3) fallback to "Heading"
    """
    counts: Dict[str, int] = {}

    if context is None:
        return counts

    root = getattr(context, "ditamap_root", None)
    if root is None:
        return counts

    def resolve_style(node: object) -> str:
        style = None
        try:
            if hasattr(node, "get"):
                style = node.get("data-style")
        except Exception:
            style = None
        if not style:
            level = None
            try:
                if hasattr(node, "get"):
                    level = node.get("data-level")
            except Exception:
                level = None
            if level:
                style = f"Heading {level}"
        if not style:
            style = "Heading"
        return style

    def iter_children(node: object):
        try:
            if hasattr(node, "iterchildren"):
                for child in node.iterchildren():
                    try:
                        tag = str(getattr(child, "tag", "") or "")
                    except Exception:
                        tag = ""
                    if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                        yield child
                return
        except Exception:
            pass
        try:
            if hasattr(node, "getchildren"):
                for child in node.getchildren():  # type: ignore[attr-defined]
                    try:
                        tag = str(getattr(child, "tag", "") or "")
                    except Exception:
                        tag = ""
                    if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                        yield child
                return
        except Exception:
            pass
        try:
            if hasattr(node, "findall"):
                for child in list(node.findall("./topicref")) + list(node.findall("./topichead")):
                    yield child
        except Exception:
            pass

    stack = [root]
    visited = 0
    max_nodes = 200000
    while stack and visited < max_nodes:
        node = stack.pop()
        visited += 1
        try:
            tag = str(getattr(node, "tag", "") or "")
        except Exception:
            tag = ""
        if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
            style = resolve_style(node)
            counts[style] = counts.get(style, 0) + 1
        try:
            for child in iter_children(node):
                stack.append(child)
        except Exception:
            continue

    return counts


def build_heading_occurrences(context: Optional[DitaContext]) -> Dict[str, List[Dict[str, str]]]:
    """Return mapping: style -> list of occurrences with {'title', 'href'}.

    Title resolution priority:
      1) topicmeta/navtitle text
      2) <title> text
      3) @href
      4) "Untitled"
    """
    occurrences: Dict[str, List[Dict[str, str]]] = {}
    if context is None:
        return occurrences
    root = getattr(context, "ditamap_root", None)
    if root is None:
        return occurrences

    def resolve_style(node: object) -> str:
        style = None
        try:
            if hasattr(node, "get"):
                style = node.get("data-style")
        except Exception:
            style = None
        if not style:
            level = None
            try:
                if hasattr(node, "get"):
                    level = node.get("data-level")
            except Exception:
                level = None
            if level:
                style = f"Heading {level}"
        if not style:
            style = "Heading"
        return style

    def get_text_or_none(node: object) -> Optional[str]:
        try:
            text = getattr(node, "text", None)
            if text is not None:
                return str(text).strip() or None
        except Exception:
            pass
        return None

    def find_first(node: object, path: str):
        try:
            if hasattr(node, "find"):
                return node.find(path)
        except Exception:
            return None
        return None

    def extract_title_and_href(node: object) -> Tuple[str, Optional[str]]:
        navtitle = None
        try:
            topicmeta = find_first(node, "./topicmeta")
            if topicmeta is not None:
                nav = find_first(topicmeta, "./navtitle")
                if nav is not None:
                    navtitle = get_text_or_none(nav)
        except Exception:
            navtitle = None

        title_text = None
        if not navtitle:
            try:
                tnode = find_first(node, "./title")
                if tnode is not None:
                    title_text = get_text_or_none(tnode)
            except Exception:
                title_text = None

        href_val = None
        try:
            if hasattr(node, "get"):
                href_val = node.get("href")
        except Exception:
            href_val = None

        title_final = navtitle or title_text or (href_val if href_val else "Untitled")
        return str(title_final), (str(href_val) if href_val else None)

    def iter_children(node: object):
        try:
            if hasattr(node, "iterchildren"):
                for child in node.iterchildren():
                    try:
                        tag = str(getattr(child, "tag", "") or "")
                    except Exception:
                        tag = ""
                    if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                        yield child
                return
        except Exception:
            pass
        try:
            if hasattr(node, "getchildren"):
                for child in node.getchildren():  # type: ignore[attr-defined]
                    try:
                        tag = str(getattr(child, "tag", "") or "")
                    except Exception:
                        tag = ""
                    if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                        yield child
                return
        except Exception:
            pass
        try:
            if hasattr(node, "findall"):
                for child in list(node.findall("./topicref")) + list(node.findall("./topichead")):
                    yield child
        except Exception:
            pass

    stack = [root]
    visited = 0
    max_nodes = 200000
    while stack and visited < max_nodes:
        node = stack.pop()
        visited += 1
        try:
            tag = str(getattr(node, "tag", "") or "")
        except Exception:
            tag = ""
        if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
            style = resolve_style(node)
            title, href = extract_title_and_href(node)
            item = {"title": title}
            if href:
                item["href"] = href
            occurrences.setdefault(style, []).append(item)
        try:
            for child in iter_children(node):
                stack.append(child)
        except Exception:
            continue

    return occurrences


def build_style_levels(context: Optional[DitaContext]) -> Dict[str, Optional[int]]:
    """Return mapping style -> level (int) when derivable, else None.

    Style resolution mirrors other helpers: prefer @data-style; else derive from
    @data-level; fallback "Heading" -> None.
    """
    result: Dict[str, Optional[int]] = {}
    if context is None:
        return result
    root = getattr(context, "ditamap_root", None)
    if root is None:
        return result

    def resolve_style_and_level(node: object) -> Tuple[str, Optional[int]]:
        style = None
        level: Optional[int] = None
        try:
            if hasattr(node, "get"):
                style = node.get("data-style")
        except Exception:
            style = None
        try:
            if hasattr(node, "get"):
                lv = node.get("data-level")
                level = int(lv) if lv is not None else None
        except Exception:
            level = None
        if not style and isinstance(level, int):
            style = f"Heading {level}"
        if not style:
            style = "Heading"
        return style, level

    stack = [root]
    visited = 0
    max_nodes = 200000
    while stack and visited < max_nodes:
        node = stack.pop()
        visited += 1
        try:
            tag = str(getattr(node, "tag", "") or "")
        except Exception:
            tag = ""
        if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
            style, level = resolve_style_and_level(node)
            result.setdefault(style, level)
        try:
            if hasattr(node, "iterchildren"):
                for child in node.iterchildren():
                    try:
                        ctag = str(getattr(child, "tag", "") or "")
                    except Exception:
                        ctag = ""
                    if ctag.endswith("topicref") or ctag.endswith("topichead") or ctag in {"topicref", "topichead"}:
                        stack.append(child)
                continue
        except Exception:
            pass
        try:
            if hasattr(node, "getchildren"):
                for child in node.getchildren():  # type: ignore[attr-defined]
                    try:
                        ctag = str(getattr(child, "tag", "") or "")
                    except Exception:
                        ctag = ""
                    if ctag.endswith("topicref") or ctag.endswith("topichead") or ctag in {"topicref", "topichead"}:
                        stack.append(child)
                continue
        except Exception:
            pass
        try:
            if hasattr(node, "findall"):
                for child in list(node.findall("./topicref")) + list(node.findall("./topichead")):
                    stack.append(child)
        except Exception:
            pass
    return result


def count_unmergable_for_styles(
    context: Optional[DitaContext], style_excl_map: Dict[int, Set[str]]
) -> int:
    """Return count of nodes matching excluded (level, style) without a merge parent.

    A node is unmergable when it has no ancestor topicref/topichead (direct child of map root).
    """
    if context is None or getattr(context, "ditamap_root", None) is None:
        return 0
    root = getattr(context, "ditamap_root")

    def node_style_level(n: object) -> Tuple[str, int]:
        level = 1
        style = "Heading"
        lv = None
        try:
            if hasattr(n, "get"):
                lv = n.get("data-level")
                if lv is not None:
                    level = int(lv)
        except Exception:
            pass
        try:
            if hasattr(n, "get"):
                st = n.get("data-style")
                if st:
                    style = st
                elif lv is not None:
                    style = f"Heading {level}"
        except Exception:
            pass
        return style, level

    def has_merge_parent(n: object) -> bool:
        try:
            parent = getattr(n, "getparent", lambda: None)()
            while parent is not None:
                tag = str(getattr(parent, "tag", "") or "")
                if tag in ("topicref", "topichead") or tag.endswith("topicref") or tag.endswith("topichead"):
                    return True
                parent = getattr(parent, "getparent", lambda: None)()
        except Exception:
            return False
        return False

    unmergable = 0
    stack = [root]
    visited = 0
    max_nodes = 200000
    while stack and visited < max_nodes:
        node = stack.pop()
        visited += 1
        try:
            tag = str(getattr(node, "tag", "") or "")
        except Exception:
            tag = ""
        if tag in ("topicref", "topichead") or tag.endswith("topicref") or tag.endswith("topichead"):
            style, level = node_style_level(node)
            if level in style_excl_map and style in style_excl_map[level]:
                if not has_merge_parent(node):
                    unmergable += 1
        try:
            if hasattr(node, "iterchildren"):
                for child in node.iterchildren():
                    stack.append(child)
                continue
        except Exception:
            pass
        try:
            if hasattr(node, "getchildren"):
                for child in node.getchildren():  # type: ignore[attr-defined]
                    stack.append(child)
                continue
        except Exception:
            pass
        try:
            if hasattr(node, "findall"):
                for child in list(node.findall("./topicref")) + list(node.findall("./topichead")):
                    stack.append(child)
        except Exception:
            pass
    return unmergable


