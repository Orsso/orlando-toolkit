from __future__ import annotations

from typing import Any


def apply_selection_tags(tree_widget: Any) -> None:
    """Apply/remove selection tags and keep highlight tag ordering stable.

    Expects `tree_widget` to expose:
      - _tree (ttk.Treeview)
      - _iter_all_item_ids() -> list[str]
      - _apply_marker_image(item_id: str) -> None
    """
    try:
        tree = getattr(tree_widget, "_tree", None)
        if tree is None:
            return
        selected_ids = set(tree.selection())
        for item_id in tree_widget._iter_all_item_ids():
            try:
                tags = list(tree.item(item_id, "tags") or ())
                has_selected = "selected-row" in tags
                if item_id in selected_ids:
                    if not has_selected and ("section" not in tags):
                        tags.append("selected-row")
                    has_search = "search-match" in tags
                    has_filter = "filter-match" in tags
                    if has_search:
                        tags = [t for t in tags if t != "search-match"]
                    if has_filter:
                        tags = [t for t in tags if t != "filter-match"]
                    if ("selected-row" not in tags) and ("section" not in tags):
                        tags.append("selected-row")
                    if has_search or has_filter:
                        if "selected-highlight" not in tags:
                            tags.append("selected-highlight")
                    else:
                        tags = [t for t in tags if t != "selected-highlight"]
                    if has_search:
                        tags.append("search-match")
                    if has_filter:
                        tags.append("filter-match")
                    tree.item(item_id, tags=tuple(tags))
                    tree_widget._apply_marker_image(item_id)
                else:
                    if has_selected:
                        tags = [t for t in tags if t not in ("selected-row", "selected-highlight")]
                        tree.item(item_id, tags=tuple(tags))
                    tree_widget._apply_marker_image(item_id)
            except Exception:
                continue
    except Exception:
        pass


