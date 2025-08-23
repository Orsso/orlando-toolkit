from __future__ import annotations

from typing import List


def apply_marker_image(widget: object, item_id: str) -> None:
    try:
        tags = tuple(widget._tree.item(item_id, "tags") or ())
        has_search = ("search-match" in tags)
        is_section = ("section" in tags)

        style_name = widget._id_to_style.get(item_id, "")
        has_style_marker = (not is_section and style_name and widget._style_visibility.get(style_name, False))

        child_style_colors: List[str] = []
        if is_section:
            is_open = bool(widget._tree.item(item_id, "open"))
            if not is_open:
                child_styles = collect_child_styles(widget, item_id)
                child_style_colors = [widget._style_colors.get(s, "#F57C00") for s in child_styles]

        if child_style_colors:
            marker_img = create_stacked_marker(widget, child_style_colors, has_search)
            widget._tree.item(item_id, image=marker_img)
        elif has_search and has_style_marker:
            style_color = widget._style_colors.get(style_name, "#F57C00")
            marker_img = get_combined_marker(widget, True, style_color)
            widget._tree.item(item_id, image=marker_img)
        elif has_search:
            if getattr(widget, "_marker_search", None) is not None:
                widget._tree.item(item_id, image=widget._marker_search)
            else:
                widget._tree.item(item_id, image=widget._marker_none)
        elif has_style_marker:
            style_color = widget._style_colors.get(style_name, "#F57C00")
            marker_img = get_combined_marker(widget, False, style_color)
            widget._tree.item(item_id, image=marker_img)
        else:
            widget._tree.item(item_id, image=widget._marker_none)
    except Exception:
        pass


def get_combined_marker(widget: object, has_search: bool, style_color: str):
    cache_key = f"search_{has_search}_style_{style_color}"
    if cache_key not in widget._style_markers:
        marker_w, marker_h = widget._marker_w, widget._marker_h
        img = widget._create_empty_marker(marker_w, marker_h)
        radius = 4
        cy = marker_h // 2
        left_cx = 4
        right_cx = marker_w - 5
        if has_search:
            _draw_arrow_on_image(widget, img, left_cx, cy, 10, "#0098e4")
        if style_color:
            _draw_circle_on_image(widget, img, right_cx, cy, radius, style_color)
        widget._style_markers[cache_key] = img
    return widget._style_markers[cache_key]


def collect_child_styles(widget: object, item_id: str) -> List[str]:
    child_styles = set()
    try:
        def walk_children(parent_id: str) -> None:
            for child_id in widget._tree.get_children(parent_id):
                child_style = widget._id_to_style.get(child_id)
                if child_style and widget._style_visibility.get(child_style, False):
                    child_styles.add(child_style)
                walk_children(child_id)
        walk_children(item_id)
    except Exception:
        pass
    return list(child_styles)


def create_stacked_marker(widget: object, style_colors: List[str], has_search: bool = False):
    colors_key = "_".join(sorted(style_colors))
    cache_key = f"stacked_search_{has_search}_colors_{colors_key}"
    if cache_key not in widget._style_markers:
        marker_w, marker_h = widget._marker_w, widget._marker_h
        img = widget._create_empty_marker(marker_w, marker_h)
        if has_search:
            _draw_arrow_on_image(widget, img, 4, marker_h // 2, 10, "#0098e4")
        if style_colors:
            num = min(len(style_colors), 5)
            if num == 1:
                cx, cy = marker_w - 5, marker_h // 2
                r = 4
                _draw_circle_on_image(widget, img, cx, cy, r + 1, "#FFFFFF")
                _draw_circle_on_image(widget, img, cx, cy, r, style_colors[0])
            elif num == 2:
                cx = marker_w - 5
                cy1, cy2 = marker_h // 2 - 3, marker_h // 2 + 3
                r = 4
                for cy, color in [(cy1, style_colors[0]), (cy2, style_colors[1])]:
                    _draw_circle_on_image(widget, img, cx, cy, r + 1, "#FFFFFF")
                    _draw_circle_on_image(widget, img, cx, cy, r, color)
            elif num == 3:
                base_cx, base_cy = marker_w - 5, marker_h // 2
                r = 3
                positions = [(base_cx, base_cy - 4), (base_cx - 3, base_cy + 2), (base_cx + 3, base_cy + 2)]
                for (cx, cy), color in zip(positions, style_colors[:3]):
                    _draw_circle_on_image(widget, img, cx, cy, r + 1, "#FFFFFF")
                    _draw_circle_on_image(widget, img, cx, cy, r, color)
            elif num == 4:
                base_cx, base_cy = marker_w - 5, marker_h // 2
                r = 3
                off = 3
                positions = [(base_cx, base_cy - off), (base_cx - off, base_cy), (base_cx + off, base_cy), (base_cx, base_cy + off)]
                for (cx, cy), color in zip(positions, style_colors[:4]):
                    _draw_circle_on_image(widget, img, cx, cy, r + 1, "#FFFFFF")
                    _draw_circle_on_image(widget, img, cx, cy, r, color)
            else:
                base_cx, base_cy = marker_w - 5, marker_h // 2
                r = 2
                _draw_circle_on_image(widget, img, base_cx, base_cy, r + 1, "#FFFFFF")
                _draw_circle_on_image(widget, img, base_cx, base_cy, r, style_colors[0])
                off = 4
                positions = [(base_cx, base_cy - off), (base_cx - off, base_cy), (base_cx + off, base_cy), (base_cx, base_cy + off)]
                for (cx, cy), color in zip(positions, style_colors[1:5]):
                    _draw_circle_on_image(widget, img, cx, cy, r + 1, "#FFFFFF")
                    _draw_circle_on_image(widget, img, cx, cy, r, color)
        widget._style_markers[cache_key] = img
    return widget._style_markers[cache_key]


def _draw_circle_on_image(widget: object, img, cx: int, cy: int, radius: int, color: str) -> None:
    try:
        from orlando_toolkit.ui.common.graphics import draw_circle_on_image
        draw_circle_on_image(img, cx, cy, radius, color)
    except Exception:
        pass


def _draw_arrow_on_image(widget: object, img, cx: int, cy: int, size: int, color: str) -> None:
    try:
        from orlando_toolkit.ui.common.graphics import draw_arrow_on_image, draw_arrow_border
        draw_arrow_on_image(img, cx, cy, size, color)
        draw_arrow_border(img, cx, cy, size, "#FFFFFF")
    except Exception:
        pass


