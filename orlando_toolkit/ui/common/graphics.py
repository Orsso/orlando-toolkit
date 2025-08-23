from __future__ import annotations

import tkinter as tk


def draw_circle_on_image(img: tk.PhotoImage, cx: int, cy: int, radius: int, color: str) -> None:
    try:
        r2 = radius * radius
        for y in range(max(0, cy - radius), min(img.height(), cy + radius + 1)):
            dy = y - cy
            for x in range(max(0, cx - radius), min(img.width(), cx + radius + 1)):
                dx = x - cx
                if dx * dx + dy * dy <= r2:
                    img.put(color, (x, y))
    except Exception:
        pass


def draw_arrow_on_image(img: tk.PhotoImage, cx: int, cy: int, size: int, color: str) -> None:
    try:
        arrow_width = size
        body_width = arrow_width - 4
        body_thickness = 3
        for y_offset in range(-body_thickness // 2, body_thickness // 2 + 1):
            for x in range(cx - body_width // 2, cx + body_width // 2):
                y_pos = cy + y_offset
                if 0 <= x < img.width() and 0 <= y_pos < img.height():
                    img.put(color, (x, y_pos))
        head_size = arrow_width // 2 + 1
        head_start_x = cx + body_width // 2 - 2
        for i in range(head_size):
            x_pos = head_start_x + i
            y_range = head_size - i
            for y_offset in range(-y_range, y_range + 1):
                y_pos = cy + y_offset
                if 0 <= x_pos < img.width() and 0 <= y_pos < img.height():
                    img.put(color, (x_pos, y_pos))
    except Exception:
        pass


def draw_arrow_border(img: tk.PhotoImage, cx: int, cy: int, size: int, border_color: str) -> None:
    try:
        arrow_width = size
        body_width = arrow_width - 4
        body_thickness = 3
        head_size = arrow_width // 2 + 1
        head_start_x = cx + body_width // 2 - 2
        border_y_top = cy - body_thickness // 2 - 1
        border_y_bottom = cy + body_thickness // 2 + 1
        for x in range(cx - body_width // 2 - 1, cx + body_width // 2 + 1):
            if 0 <= x < img.width():
                if 0 <= border_y_top < img.height():
                    img.put(border_color, (x, border_y_top))
                if 0 <= border_y_bottom < img.height():
                    img.put(border_color, (x, border_y_bottom))
        for i in range(head_size + 1):
            x_pos = head_start_x + i
            y_range = head_size - i + 1
            y_top_border = cy - y_range
            y_bottom_border = cy + y_range
            if 0 <= x_pos < img.width():
                if 0 <= y_top_border < img.height():
                    img.put(border_color, (x_pos, y_top_border))
                if 0 <= y_bottom_border < img.height():
                    img.put(border_color, (x_pos, y_bottom_border))
    except Exception:
        pass


