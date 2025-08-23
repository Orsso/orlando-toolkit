from __future__ import annotations

from typing import Dict, List


def iter_visible_item_ids(widget: object) -> List[str]:
    order: List[str] = []
    try:
        def walk(parent: str) -> None:
            for iid in widget._tree.get_children(parent):
                order.append(iid)
                try:
                    is_open = bool(widget._tree.item(iid, "open"))
                except Exception:
                    is_open = False
                if is_open:
                    walk(iid)
        walk("")
    except Exception:
        return []
    return order


def update_marker_bar_positions(widget: object) -> None:
    try:
        bar = getattr(widget, "_marker_bar", None)
        if bar is None:
            return
        visible = iter_visible_item_ids(widget)
        total = len(visible)
        if total <= 0:
            bar.set_markers([], [])  # type: ignore[union-attr]
            if hasattr(bar, 'set_style_markers'):
                bar.set_style_markers({})  # type: ignore[union-attr]
            return
        search_pos: List[float] = []
        filter_pos: List[float] = []
        style_positions: Dict[str, List[float]] = {}

        for idx, iid in enumerate(visible):
            try:
                tags = tuple(widget._tree.item(iid, "tags") or ())
            except Exception:
                tags = ()
            normalized_pos = (idx + 0.5) / total
            if "search-match" in tags:
                search_pos.append(normalized_pos)
            if "filter-match" in tags:
                filter_pos.append(normalized_pos)
            style_name = widget._id_to_style.get(iid, "")
            if style_name and widget._style_visibility.get(style_name, False):
                style_positions.setdefault(style_name, []).append(normalized_pos)

        bar.set_markers(search_pos, filter_pos)  # type: ignore[union-attr]
        if hasattr(bar, 'set_style_markers'):
            style_markers = {}
            for style_name, positions in style_positions.items():
                color = widget._style_colors.get(style_name, "#F57C00")
                style_markers[style_name] = (positions, color)
            bar.set_style_markers(style_markers)  # type: ignore[union-attr]
    except Exception:
        pass


def throttle_marker_viewport_update(widget: object) -> None:
    try:
        first, last = widget._tree.yview()
        if getattr(widget, "_marker_bar", None) is not None:
            widget._marker_bar.set_viewport(float(first), float(last))  # type: ignore[union-attr]
    except Exception:
        pass


def on_marker_jump(widget: object, norm: float) -> None:
    try:
        visible = iter_visible_item_ids(widget)
        total = len(visible)
        if total <= 0:
            return
        idx = int(round(norm * (total - 1)))
        idx = max(0, min(total - 1, idx))
        target_id = visible[idx]
        try:
            widget._tree.see(target_id)
        except Exception:
            pass
        try:
            widget._tree.update_idletasks()
            bbox = widget._tree.bbox(target_id)
            if bbox:
                x, y, w, h = bbox
                if h > 0:
                    widget_h = max(1, int(widget._tree.winfo_height()))
                    delta_px = (y + h // 2) - (widget_h // 2)
                    rows = int(round(delta_px / float(h)))
                    if rows != 0:
                        widget._tree.yview_scroll(rows, "units")
        except Exception:
            pass
    except Exception:
        pass


def on_marker_set_viewport(widget: object, first: float) -> None:
    try:
        frac = max(0.0, min(1.0, float(first)))
        widget._tree.yview_moveto(frac)
    except Exception:
        pass


