from __future__ import annotations

from typing import Dict, List


STYLE_COLORS: List[str] = [
    "#FF1744",  # vivid red
    "#00C853",  # vivid green
    "#FF9100",  # bright orange
    "#9C27B0",  # purple
    "#FF00A8",  # fuchsia
]


class StyleColorManager:
    """Assigns stable, collision-free colors to styles."""

    def __init__(self) -> None:
        self._style_to_color: Dict[str, str] = {}
        self._color_assignments: set[str] = set()
        self._next_index: int = 0

    def assign_unique(self, style_names: List[str]) -> Dict[str, str]:
        self.clear_assignments()
        mapping: Dict[str, str] = {}
        n = len(STYLE_COLORS)

        def pref_idx(name: str) -> int:
            try:
                return hash(name) % n
            except Exception:
                return 0

        ordered = sorted(style_names or [], key=lambda s: (pref_idx(s), s))
        used: set[int] = set()
        for name in ordered:
            start = pref_idx(name)
            idx = start
            for _ in range(n):
                if idx not in used:
                    used.add(idx)
                    color = STYLE_COLORS[idx]
                    self._style_to_color[name] = color
                    mapping[name] = color
                    break
                idx = (idx + 1) % n
            else:
                color = STYLE_COLORS[self._next_index % n]
                self._next_index += 1
                self._style_to_color[name] = color
                mapping[name] = color
        self._color_assignments = set(mapping.values())
        return mapping

    def get_color_for_style(self, style_name: str) -> str:
        if style_name in self._style_to_color:
            return self._style_to_color[style_name]
        preferred_index = hash(style_name) % len(STYLE_COLORS)
        color = STYLE_COLORS[preferred_index]
        if color in self._color_assignments:
            for i in range(len(STYLE_COLORS)):
                test_index = (preferred_index + i) % len(STYLE_COLORS)
                test_color = STYLE_COLORS[test_index]
                if test_color not in self._color_assignments:
                    color = test_color
                    break
            else:
                color = STYLE_COLORS[self._next_index % len(STYLE_COLORS)]
                self._next_index += 1
        self._style_to_color[style_name] = color
        self._color_assignments.add(color)
        return color

    def clear_assignments(self) -> None:
        self._style_to_color.clear()
        self._color_assignments.clear()
        self._next_index = 0


_color_manager = StyleColorManager()


