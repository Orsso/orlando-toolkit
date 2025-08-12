from __future__ import annotations

from typing import Dict, List, Optional
import tkinter as tk
from tkinter import ttk


__all__ = ["StyleLegend"]


# Search marker color
SEARCH_COLOR = "#0098e4"

# Style color palette – exactly 5 vivid colors, all distinct on white and not blue
# so they remain distinguishable from the search marker color.
STYLE_COLORS = [
    "#FF1744",  # vivid red
    "#00C853",  # vivid green
    "#FF9100",  # bright orange
    "#9C27B0",  # purple
    "#FF00A8",  # fuchsia
]

# Collision-free color assignment for style names
class StyleColorManager:
    """Assigns stable, collision-free colors to styles."""
    
    def __init__(self):
        self._style_to_color = {}
        self._color_assignments = set()
        self._next_index = 0
    
    def assign_unique(self, style_names: List[str]) -> Dict[str, str]:
        """Assign unique colors for the provided list of styles.

        Resets internal assignments to ensure no two provided styles share
        the same color. Order is stable based on each style's hashed
        preferred index, with collision resolution by circular probing.
        """
        self.clear_assignments()
        mapping: Dict[str, str] = {}
        n = len(STYLE_COLORS)
        # Sort by preferred index then name for determinism
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
                # Should not happen with <= n styles, but keep safe
                color = STYLE_COLORS[self._next_index % n]
                self._next_index += 1
                self._style_to_color[name] = color
                mapping[name] = color
        self._color_assignments = set(mapping.values())
        return mapping

    def get_color_for_style(self, style_name: str) -> str:
        """Return a unique color for a given style name."""
        if style_name in self._style_to_color:
            return self._style_to_color[style_name]
        
        # Deterministic base on hash with collision handling
        preferred_index = hash(style_name) % len(STYLE_COLORS)
        color = STYLE_COLORS[preferred_index]
        
        # If color already taken, search the next available
        if color in self._color_assignments:
            # Search forward from preferred index
            for i in range(len(STYLE_COLORS)):
                test_index = (preferred_index + i) % len(STYLE_COLORS)
                test_color = STYLE_COLORS[test_index]
                if test_color not in self._color_assignments:
                    color = test_color
                    break
            else:
                # All assigned; reuse (edge case with >24 styles)
                color = STYLE_COLORS[self._next_index % len(STYLE_COLORS)]
                self._next_index += 1
        
        self._style_to_color[style_name] = color
        self._color_assignments.add(color)
        return color
    
    def clear_assignments(self):
        """Clear all assignments."""
        self._style_to_color.clear()
        self._color_assignments.clear()
        self._next_index = 0

# Shared global instance
_color_manager = StyleColorManager()


class StyleLegend(ttk.Frame):
    """Compact legend widget for currently used markers.

    Dynamically shows:
    - Search marker (blue) when search is active
    - Style markers (various colors) for toggled styles
    """

    def __init__(self, parent: tk.Widget, **kwargs) -> None:
        super().__init__(parent, **kwargs)
        
        # Internal state
        self._search_active = False
        self._active_styles: Dict[str, bool] = {}
        
        # Horizontal layout with spacing – use grid for compatibility
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        
        self._inner_frame = ttk.Frame(self)
        self._inner_frame.grid(row=0, column=0, sticky="w", padx=4, pady=2)
        
        # Container for markers directly (no "Legend:" title)
        self._markers_frame = ttk.Frame(self._inner_frame)
        self._markers_frame.grid(row=0, column=0)
        
        # Cache for PhotoImages to avoid garbage collection
        self._marker_images: Dict[str, tk.PhotoImage] = {}
        
        # Currently displayed widgets
        self._current_widgets: List[tk.Widget] = []
        
    def update_legend(self, search_active: bool = False, active_styles: Optional[Dict[str, bool]] = None) -> None:
        """Update the legend according to current marker state.

        Parameters
        ----------
        search_active : bool
            True when search is active
        active_styles : Dict[str, bool], optional
            Mapping style -> toggle state
        """
        self._search_active = search_active
        self._active_styles = dict(active_styles or {})
        
        # Remove existing marker widgets
        for widget in self._current_widgets:
            try:
                widget.destroy()
            except Exception:
                pass
        self._current_widgets.clear()
        
        # Create new markers
        has_items = False
        
        # Search marker (arrow instead of circle)
        if self._search_active:
            self._add_search_marker_item("Search", SEARCH_COLOR)
            has_items = True
            
        # Style markers
        active_style_names = [name for name, active in self._active_styles.items() if active]
        for style_name in sorted(active_style_names):
            color = self._get_style_color(style_name)
            self._add_marker_item(style_name, color)
            has_items = True
            
        # Control visibility via grid instead of pack
        if has_items:
            # The legend is already gridded in StructureTab; nothing to do
            pass
        else:
            # Hide the legend by removing markers only; keep the frame present
            pass
            
    def _add_marker_item(self, label: str, color: str) -> None:
        """Add one legend item (colored marker + label)."""
        col = len(self._current_widgets) // 3  # 3 widgets par item
        
        container = ttk.Frame(self._markers_frame)
        container.grid(row=0, column=col, padx=(0, 12))
        
        # Create the circular marker
        marker = self._create_marker(color)
        marker_label = ttk.Label(container, image=marker)
        marker_label.grid(row=0, column=0, padx=(0, 4))
        
        # Text label
        text_label = ttk.Label(container, text=label, font=("", 9))
        text_label.grid(row=0, column=1)
        
        self._current_widgets.extend([container, marker_label, text_label])

    def _add_search_marker_item(self, label: str, color: str) -> None:
        """Add a search legend item with arrow marker."""
        col = len(self._current_widgets) // 3  # 3 widgets per item
        
        container = ttk.Frame(self._markers_frame)
        container.grid(row=0, column=col, padx=(0, 12))
        
        # Create the arrow marker for search
        marker = self._create_arrow_marker(color)
        marker_label = ttk.Label(container, image=marker)
        marker_label.grid(row=0, column=0, padx=(0, 4))
        
        # Text label
        text_label = ttk.Label(container, text=label, font=("", 9))
        text_label.grid(row=0, column=1)
        
        self._current_widgets.extend([container, marker_label, text_label])
        
    def _create_marker(self, color: str) -> tk.PhotoImage:
        """Create a circular marker image for the given color."""
        # Use cache if possible
        if color in self._marker_images:
            return self._marker_images[color]
            
        # Create a new marker
        size = 12
        img = tk.PhotoImage(width=size, height=size)
        
        # Draw a filled circle
        center = size // 2
        radius = 4
        try:
            for y in range(size):
                for x in range(size):
                    dx = x - center
                    dy = y - center
                    if dx * dx + dy * dy <= radius * radius:
                        img.put(color, (x, y))
        except Exception:
            # Fallback: colored rectangle
            try:
                img.put(color, to=(2, 2, size-2, size-2))
            except Exception:
                pass
                
        self._marker_images[color] = img
        return img

    def _create_arrow_marker(self, color: str) -> tk.PhotoImage:
        """Create a thick arrow marker for search legend - matches tree widget style."""
        # Use cache with arrow prefix to distinguish from circles
        cache_key = f"arrow_{color}"
        if cache_key in self._marker_images:
            return self._marker_images[cache_key]
            
        # Create arrow marker matching the tree widget style
        size = 16  # Larger than circles for visibility
        img = tk.PhotoImage(width=size, height=size)
        
        # Draw thick arrow centered in the marker space
        cx, cy = size // 2, size // 2
        arrow_size = 12  # Same size as in tree widget
        
        try:
            # Draw thick arrow body
            body_width = arrow_size - 4
            body_thickness = 3
            
            # Thick horizontal body
            for y_offset in range(-body_thickness // 2, body_thickness // 2 + 1):
                for x in range(cx - body_width // 2, cx + body_width // 2):
                    y_pos = cy + y_offset
                    if 0 <= x < size and 0 <= y_pos < size:
                        img.put(color, (x, y_pos))
            
            # Large triangle head
            head_size = arrow_size // 2 + 1
            head_start_x = cx + body_width // 2 - 2
            
            for i in range(head_size):
                x_pos = head_start_x + i
                y_range = head_size - i
                
                for y_offset in range(-y_range, y_range + 1):
                    y_pos = cy + y_offset
                    if 0 <= x_pos < size and 0 <= y_pos < size:
                        img.put(color, (x_pos, y_pos))
                        
            # Add white border for contrast like in tree widget
            self._add_arrow_border(img, cx, cy, arrow_size, "#FFFFFF", size)
            
        except Exception:
            # Fallback to simple rectangle if arrow fails
            try:
                img.put(color, to=(2, 2, size-2, size-2))
            except Exception:
                pass
                
        self._marker_images[cache_key] = img
        return img
        
    def _add_arrow_border(self, img: tk.PhotoImage, cx: int, cy: int, arrow_size: int, 
                         border_color: str, img_size: int) -> None:
        """Add white border around arrow for better visibility."""
        try:
            body_width = arrow_size - 4
            body_thickness = 3
            head_size = arrow_size // 2 + 1
            head_start_x = cx + body_width // 2 - 2
            
            # Border around body
            border_y_top = cy - body_thickness // 2 - 1
            border_y_bottom = cy + body_thickness // 2 + 1
            
            for x in range(cx - body_width // 2 - 1, cx + body_width // 2 + 1):
                if 0 <= x < img_size:
                    if 0 <= border_y_top < img_size:
                        img.put(border_color, (x, border_y_top))
                    if 0 <= border_y_bottom < img_size:
                        img.put(border_color, (x, border_y_bottom))
            
            # Border around arrow head
            for i in range(head_size + 1):
                x_pos = head_start_x + i
                y_range = head_size - i + 1
                
                y_top_border = cy - y_range
                y_bottom_border = cy + y_range
                
                if 0 <= x_pos < img_size:
                    if 0 <= y_top_border < img_size:
                        img.put(border_color, (x_pos, y_top_border))
                    if 0 <= y_bottom_border < img_size:
                        img.put(border_color, (x_pos, y_bottom_border))
                        
        except Exception:
            pass
        
    def _get_style_color(self, style_name: str) -> str:
        """Return the color assigned to a style (collision-free assignment)."""
        return _color_manager.get_color_for_style(style_name)
        
    def get_style_color(self, style_name: str) -> str:
        """Public API to get the color for a style."""
        return self._get_style_color(style_name)