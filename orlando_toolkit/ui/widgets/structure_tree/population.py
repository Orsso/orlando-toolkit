from __future__ import annotations

from typing import Dict, List, Optional, Tuple


def populate_tree(tree: object, context: object, max_depth: int = 999) -> None:
    """Rebuild the entire tree from the given DITA context (UI-only).

    This mirrors the previous StructureTreeWidget.populate_tree implementation
    but lives as a module function to keep the widget lean.
    """
    _clear(tree)

    ditamap_root = _safe_getattr(context, "ditamap_root")
    map_root = (
        ditamap_root
        or _safe_getattr(context, "map_root")
        or _safe_getattr(context, "structure")
    )

    if ditamap_root is not None and map_root is not None:
        # Store ditamap root and precompute section numbers
        try:
            setattr(tree, "_ditamap_root", ditamap_root)
        except Exception:
            pass
        try:
            from orlando_toolkit.core.utils import calculate_section_numbers
            section_map = calculate_section_numbers(ditamap_root) or {}
        except Exception:
            section_map = {}
        try:
            setattr(tree, "_section_number_map", section_map)
        except Exception:
            pass

        traversed = False
        try:
            children = _collect_direct_children(map_root)
            for child in children:
                try:
                    _traverse_and_insert(tree, child, parent_id="", depth=1, max_depth=max_depth)
                except Exception:
                    continue
            traversed = True
        except Exception:
            traversed = False

        if traversed:
            # Apply smart default expansion only on first load
            try:
                if not hasattr(tree, '_has_been_populated'):
                    tree.expand_all()  # Full expansion on first document load
                    tree._has_been_populated = True
                tree._tree.update_idletasks()
            except Exception:
                pass
            try:
                tree._update_marker_bar_positions()  # type: ignore[attr-defined]
            except Exception:
                pass
            return

    # Fallback: flat listing under synthetic root
    try:
        setattr(tree, "_section_number_map", {})
    except Exception:
        pass
    root_label = _safe_getattr(context, "title") or "Root"
    root_ref = _safe_getattr(context, "root_ref")
    root_id = _insert_item(tree, "", root_label, topic_ref=root_ref)
    try:
        tree._tree.item(root_id, open=True)
    except Exception:
        pass

    topics = _safe_getattr(context, "topics") or _safe_getattr(context, "topic_refs") or {}
    try:
        if isinstance(topics, dict):
            count = 0
            for key, element in topics.items():
                if count >= 10000:
                    break
                label = None
                try:
                    if element is not None and hasattr(element, "find"):
                        title_el = element.find("title")
                        if title_el is not None:
                            text_val = getattr(title_el, "text", None)
                            if isinstance(text_val, str) and text_val.strip():
                                label = text_val.strip()
                except Exception:
                    label = None
                if not label:
                    label = str(key)
                ref = str(key)
                _insert_item(tree, root_id, label, topic_ref=ref)
                count += 1
        else:
            count = 0
            try:
                iterable = list(topics)
            except Exception:
                iterable = []
            for item in iterable:
                if count >= 10000:
                    break
                label, ref = _extract_label_and_ref(item)
                if isinstance(ref, str) and ref and not ref.startswith("topics/") and ref.endswith(".dita"):
                    ref = f"topics/{ref}"
                _insert_item(tree, root_id, label, topic_ref=ref)
                count += 1
    except Exception:
        pass

    # Apply smart default expansion only on first load (fallback mode)
    try:
        if not hasattr(tree, '_has_been_populated'):
            tree.expand_all()  # Full expansion on first document load
            tree._has_been_populated = True
        tree._tree.update_idletasks()
        try:
            tree.after(0, tree._tree.update_idletasks)
        except Exception:
            pass
    except Exception:
        pass

    try:
        for iid in _iter_all_item_ids(tree):
            try:
                tree._tree.see(iid)
            except Exception:
                continue
        tree._tree.update_idletasks()
    except Exception:
        pass

    try:
        tree._update_marker_bar_positions()  # type: ignore[attr-defined]
    except Exception:
        pass


# ----------------------------- Internals ------------------------------------

def _safe_getattr(obj: object, name: str) -> Optional[object]:
    try:
        return getattr(obj, name, None)
    except Exception:
        return None


def _clear(tree: object) -> None:
    try:
        tree.clear()
    except Exception:
        pass


def _collect_direct_children(node: object) -> List[object]:
    children: List[object] = []
    try:
        if hasattr(node, "iterchildren"):
            for child in node.iterchildren():
                try:
                    tag = str(getattr(child, "tag", "") or "")
                except Exception:
                    tag = ""
                if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                    children.append(child)
        elif hasattr(node, "getchildren"):
            for child in node.getchildren():  # type: ignore[attr-defined]
                try:
                    tag = str(getattr(child, "tag", "") or "")
                except Exception:
                    tag = ""
                if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                    children.append(child)
        else:
            try:
                if hasattr(node, "findall"):
                    children.extend(list(node.findall("./topicref")))
                    children.extend(list(node.findall("./topichead")))
            except Exception:
                pass
    except Exception:
        children = []
    return children


def _insert_item(tree: object, parent: str, text: str, topic_ref: Optional[str], tags: Optional[Tuple[str, ...]] = None) -> str:
    safe_text = text if isinstance(text, str) and text else "Untitled"
    try:
        if isinstance(safe_text, str):
            safe_text = " ".join(safe_text.split())
    except Exception:
        pass
    item_id = tree._tree.insert(parent, "end", text=safe_text, image=getattr(tree, "_marker_none", ""), tags=(tags or ()))
    if topic_ref is not None:
        try:
            tree._id_to_ref[item_id] = topic_ref
            if topic_ref not in tree._ref_to_id:
                tree._ref_to_id[topic_ref] = item_id
        except Exception:
            pass
    return item_id


def _traverse_and_insert(tree: object, node: object, parent_id: str, depth: int, max_depth: int) -> None:
    if depth > max_depth:
        return

    def resolve_style(n: object) -> Optional[str]:
        try:
            if hasattr(n, "get"):
                style = n.get("data-style")
            else:
                style = None
        except Exception:
            style = None
        if style:
            return style
        try:
            if hasattr(n, "get"):
                level = n.get("data-level")
            else:
                level = None
        except Exception:
            level = None
        if level:
            return f"Heading {level}"
        return None

    try:
        is_element = hasattr(node, "tag")
    except Exception:
        is_element = False

    if is_element:
        try:
            tag_name = str(getattr(node, "tag", "") or "")
        except Exception:
            tag_name = ""

        if tag_name.endswith("topicref") or tag_name.endswith("topichead") or tag_name in {"topicref", "topichead"}:
            style = resolve_style(node) or "Heading"
            try:
                if getattr(tree, "_style_exclusions", {}).get(style, False):
                    return
            except Exception:
                pass

        label = "Item"
        try:
            text_val = None
            try:
                if hasattr(node, "find"):
                    navtitle_el = node.find("topicmeta/navtitle")
                    if navtitle_el is not None:
                        text_val = getattr(navtitle_el, "text", None)
            except Exception:
                pass
            if not text_val:
                try:
                    title_el = node.find("title") if hasattr(node, "find") else None
                    if title_el is not None:
                        text_val = getattr(title_el, "text", None)
                except Exception:
                    pass
            if isinstance(text_val, str) and text_val.strip():
                label = text_val.strip()
            else:
                try:
                    navtitle_attr = node.get("navtitle") if hasattr(node, "get") else None
                    if isinstance(navtitle_attr, str) and navtitle_attr.strip():
                        label = navtitle_attr.strip()
                except Exception:
                    pass
        except Exception:
            label = "Item"

        if tag_name.endswith("topicref") or tag_name in {"topicref"}:
            ref = None
            try:
                href_val = node.get("href") if hasattr(node, "get") else None
                if isinstance(href_val, str) and href_val.strip():
                    ref = href_val.strip()
            except Exception:
                ref = None
        else:
            ref = None

        is_section_node = (tag_name.endswith("topichead") or tag_name == "topichead")
        current_id = _insert_item(
            tree,
            parent_id,
            _with_section_number(label, tree, node, tag_name),
            ref,
            tags=(("section",) if is_section_node else None),
        )

        try:
            exp_style = None
            try:
                if hasattr(node, "get"):
                    exp_style = node.get("data-style")
            except Exception:
                exp_style = None
            if exp_style:
                node_style = str(exp_style)
            else:
                level_attr = None
                try:
                    if hasattr(node, "get"):
                        level_attr = node.get("data-level")
                except Exception:
                    level_attr = None
                node_style = f"Heading {level_attr}" if level_attr else (resolve_style(node) or "Heading")
            if isinstance(node_style, str) and node_style:
                tree._id_to_style[current_id] = node_style  # type: ignore[attr-defined]
        except Exception:
            pass

        children = _collect_direct_children(node)
        for child in children:
            try:
                _traverse_and_insert(tree, child, current_id, depth + 1, max_depth)
            except Exception:
                continue
        return

    # Generic branch
    label = (
        _safe_getattr(node, "title")
        or _safe_getattr(node, "label")
        or _safe_getattr(node, "name")
        or "Item"
    )
    try:
        if isinstance(label, str):
            label = " ".join(label.split())
    except Exception:
        pass
    ref = _safe_getattr(node, "ref") or _safe_getattr(node, "topic_ref")
    current_id = _insert_item(tree, parent_id, label, ref)

    children = (
        _safe_getattr(node, "children")
        or _safe_getattr(node, "topics")
        or _safe_getattr(node, "items")
        or []
    )
    try:
        iterable = list(children.values()) if isinstance(children, dict) else list(children)
    except Exception:
        iterable = []
    for child in iterable:
        try:
            _traverse_and_insert(tree, child, current_id, depth + 1, max_depth)
        except Exception:
            continue


def _with_section_number(label: str, tree: object, node: object, tag_name: str) -> str:
    if tag_name.endswith("topicref") or tag_name.endswith("topichead") or tag_name in {"topicref", "topichead"}:
        try:
            val = _calculate_section_number(tree, node)
        except Exception:
            val = "0"
        if val and val != "0":
            return f"{val}. {label}"
    return label


def _calculate_section_number(tree: object, node: object) -> str:
    try:
        ditamap_root = getattr(tree, "_ditamap_root", None)
        if ditamap_root is None:
            return "0"
        section_map = getattr(tree, "_section_number_map", {}) or {}
        if section_map:
            val = section_map.get(node)
            if isinstance(val, str):
                return val
        # Fallback walk
        counters: List[int] = []
        current = node
        while current is not None:
            parent = getattr(current, 'getparent', lambda: None)()
            if parent is None or parent == ditamap_root:
                siblings: List[object] = []
                try:
                    if hasattr(ditamap_root, "iterchildren"):
                        for child in ditamap_root.iterchildren():
                            tag = str(getattr(child, "tag", "") or "")
                            if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                                siblings.append(child)
                    elif hasattr(ditamap_root, "getchildren"):
                        for child in ditamap_root.getchildren():
                            tag = str(getattr(child, "tag", "") or "")
                            if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                                siblings.append(child)
                except Exception:
                    siblings = []
                position = 1
                for i, sibling in enumerate(siblings, 1):
                    if sibling == current:
                        position = i
                        break
                counters.insert(0, position)
                break
            else:
                siblings = []
                try:
                    if hasattr(parent, "iterchildren"):
                        for child in parent.iterchildren():
                            tag = str(getattr(child, "tag", "") or "")
                            if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                                siblings.append(child)
                    elif hasattr(parent, "getchildren"):
                        for child in parent.getchildren():
                            tag = str(getattr(child, "tag", "") or "")
                            if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                                siblings.append(child)
                except Exception:
                    siblings = []
                position = 1
                for i, sibling in enumerate(siblings, 1):
                    if sibling == current:
                        position = i
                        break
                counters.insert(0, position)
                current = parent
        if counters:
            return ".".join(str(c) for c in counters)
        return "0"
    except Exception:
        return "0"


def _extract_label_and_ref(item: object) -> Tuple[str, Optional[str]]:
    try:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            label = item[0]
            ref = item[1]
            return (str(label) if label is not None else "Item", str(ref) if ref is not None else None)
        if isinstance(item, dict):
            label = item.get("title") or item.get("label") or item.get("name") or "Item"
            ref = item.get("ref") or item.get("topic_ref")
            return (str(label), str(ref) if ref is not None else None)
        label = (
            _safe_getattr(item, "title")
            or _safe_getattr(item, "label")
            or _safe_getattr(item, "name")
            or "Item"
        )
        ref = _safe_getattr(item, "ref") or _safe_getattr(item, "topic_ref")
        return (str(label), str(ref) if ref is not None else None)
    except Exception:
        return ("Item", None)


def _iter_all_item_ids(tree: object) -> List[str]:
    result: List[str] = []
    try:
        def walk(parent: str) -> None:
            for cid in tree._tree.get_children(parent):
                result.append(cid)
                walk(cid)
        walk("")
    except Exception:
        pass
    return result


