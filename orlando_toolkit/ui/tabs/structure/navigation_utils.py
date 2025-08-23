from __future__ import annotations

from typing import Optional


def predict_merge_target_href_for_ref(context: object, tree: object, topic_ref: str) -> Optional[str]:
    """Best-effort prediction of the href that will receive a merged topic.

    Mirrors core merge behavior heuristics:
    - If the selected ref remains after merge, prefer it (content-bearing ancestor)
    - Else, nearest ancestor topicref with href
    - Else, previous sibling topicref with href
    - Else, first topicref under nearest topichead
    """
    if not isinstance(topic_ref, str) or not topic_ref:
        return None
    try:
        # If the item currently exists, assume it may survive
        try:
            if hasattr(tree, 'find_item_by_ref') and tree.find_item_by_ref(topic_ref):  # type: ignore[attr-defined]
                return topic_ref
        except Exception:
            pass

        root = getattr(context, 'ditamap_root', None)
        if root is None:
            return None

        # Locate the topicref element by href
        try:
            tref = root.find(f".//topicref[@href='{topic_ref}']")
        except Exception:
            tref = None
        if tref is None:
            return None

        # Prefer nearest ancestor content-bearing topicref
        probe = tref.getparent()
        while probe is not None:
            try:
                if getattr(probe, 'tag', None) == 'topicref' and probe.get('href'):
                    return probe.get('href')
            except Exception:
                break
            probe = probe.getparent()

        parent = tref.getparent()
        if parent is None:
            return None
        siblings = list(parent)
        try:
            idx = siblings.index(tref)
        except ValueError:
            idx = -1
        if idx > 0:
            for i in range(idx - 1, -1, -1):
                sib = siblings[i]
                if getattr(sib, 'tag', None) != 'topicref':
                    continue
                href = sib.get('href') or ''
                if href:
                    return href

        # Fallback: first topicref under nearest topichead
        probe = parent
        while probe is not None and getattr(probe, 'tag', None) != 'topichead':
            probe = probe.getparent()
        if probe is not None and getattr(probe, 'tag', None) == 'topichead':
            for ch in list(probe):
                if getattr(ch, 'tag', None) == 'topicref' and ch.get('href'):
                    return ch.get('href')
        return None
    except Exception:
        return None


def find_first_topic_href_in_section(context: object, section_nav_id: str) -> Optional[str]:
    """Given a nav_id like 'section_<id(node)>', find first child topicref href."""
    try:
        if not isinstance(section_nav_id, str) or not section_nav_id.startswith('section_'):
            return None
        section_mem_id = section_nav_id.replace('section_', '')
        root = getattr(context, 'ditamap_root', None)
        if root is None:
            return None
        for node in root.iter():
            try:
                if str(id(node)) == section_mem_id and node.tag == 'topichead':
                    first_topic = node.find(".//topicref[@href]")
                    if first_topic is not None:
                        href = first_topic.get('href', '')
                        return href or None
                    break
            except Exception:
                continue
        return None
    except Exception:
        return None


