# -*- coding: utf-8 -*-
"""BreadcrumbWidget for navigation path display.

A compact, clickable breadcrumb widget that shows hierarchical navigation paths.
Designed for use in preview panels to show topic hierarchy.

Public API (UI-only, no business logic):
- set_path(path_items: List[BreadcrumbItem]) -> None
- clear() -> None

Callbacks:
- on_item_clicked: Optional[Callable[[str], None]]  # called with item.value

Notes:
- Widget displays items separated by ">" separators
- Last item is not clickable (current location)
- Truncates long paths with ellipsis if needed
- Pure UI component - no business logic included
"""

from __future__ import annotations

from typing import Callable, List, Optional, NamedTuple
import tkinter as tk
from tkinter import ttk


class BreadcrumbItem(NamedTuple):
    """Represents a single breadcrumb navigation item."""
    label: str  # Display text
    value: str  # Value passed to callback (e.g., topic_ref)


__all__ = ["BreadcrumbWidget", "BreadcrumbItem"]


class BreadcrumbWidget(ttk.Frame):
    """Compact breadcrumb navigation widget."""

    def __init__(
        self,
        parent: tk.Widget,
        *,
        on_item_clicked: Optional[Callable[[str], None]] = None,
        max_width: int = 400,
        link_max_chars: int = 15,
        current_max_chars: int = 20,
        separator_padx: tuple[int, int] = (2, 2),
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        
        self.on_item_clicked: Optional[Callable[[str], None]] = on_item_clicked
        self._max_width: int = max_width
        self._link_max_chars: int = link_max_chars
        self._current_max_chars: int = current_max_chars
        self._separator_padx: tuple[int, int] = separator_padx
        
        # Configure layout
        self.columnconfigure(0, weight=1)
        
        # Container for breadcrumb items with scrollable capability
        self._content_frame = ttk.Frame(self)
        self._content_frame.grid(row=0, column=0, sticky="ew")
        
        # Limit maximum width to prevent overflow
        self.configure(width=self._max_width)  # Max width constraint
        
        # Current path items
        self._path_items: List[BreadcrumbItem] = []
        self._widgets: List[tk.Widget] = []  # Track created widgets for cleanup
        self._active_tooltips: List[tk.Toplevel] = []  # Track all tooltips for cleanup

    def set_path(self, path_items: List[BreadcrumbItem]) -> None:
        """Set the breadcrumb path items."""
        self._path_items = path_items[:]  # Copy to avoid external mutations
        self._rebuild_widgets()

    def _truncate_path_if_needed(self, items: List[BreadcrumbItem]) -> List[BreadcrumbItem]:
        """Truncate path with ellipsis if too many items."""
        if len(items) <= 4:
            return items
        
        # Show first item, ellipsis, last 2 items
        ellipsis_item = BreadcrumbItem(label="...", value="")
        return [items[0], ellipsis_item] + items[-2:]

    def clear(self) -> None:
        """Clear the breadcrumb path."""
        self._cleanup_all_tooltips()
        self._path_items.clear()
        self._rebuild_widgets()

    def _rebuild_widgets(self) -> None:
        """Rebuild the breadcrumb widgets from current path items."""
        # Clear existing tooltips and widgets
        self._cleanup_all_tooltips()
        for widget in self._widgets:
            try:
                widget.destroy()
            except Exception:
                pass
        self._widgets.clear()
        
        if not self._path_items:
            return
            
        # Apply truncation for long paths
        display_items = self._truncate_path_if_needed(self._path_items)
        
        # Create widgets for each item
        for i, item in enumerate(display_items):
            # Add separator before item (except first)
            if i > 0:
                sep = ttk.Label(self._content_frame, text=">")
                sep.grid(row=0, column=len(self._widgets), padx=self._separator_padx)
                self._widgets.append(sep)
            
            # Create item widget
            is_last = (i == len(display_items) - 1)
            is_ellipsis = (item.label == "..." and not item.value)
            
            if is_ellipsis:
                # Non-clickable ellipsis
                widget = ttk.Label(
                    self._content_frame,
                    text=item.label,
                    foreground="gray"
                )
            elif is_last:
                # Last item is not clickable (current location)
                widget = ttk.Label(
                    self._content_frame,
                    text=self._truncate_text(item.label, self._current_max_chars),
                    style="Breadcrumb.Current.TLabel"
                )
                # Add tooltip if text is truncated
                if len(item.label) > self._current_max_chars:
                    self._create_tooltip(widget, item.label)
            else:
                # All non-last items are clickable (sections and topics)
                widget = ttk.Label(
                    self._content_frame,
                    text=self._truncate_text(item.label, self._link_max_chars),
                    style="Breadcrumb.Link.TLabel",
                    cursor="hand2"
                )
                # Bind click event
                widget.bind("<Button-1>", lambda e, value=item.value: self._on_item_click(value))
                
                # Add tooltip and hover effects
                if len(item.label) > self._link_max_chars:
                    self._create_tooltip_with_hover(widget, item.label)
                else:
                    widget.bind("<Enter>", lambda e, w=widget: self._on_hover_enter(w))
                    widget.bind("<Leave>", lambda e, w=widget: self._on_hover_leave(w))
            
            widget.grid(row=0, column=len(self._widgets), sticky="w")
            self._widgets.append(widget)

    def _on_item_click(self, value: str) -> None:
        """Handle breadcrumb item click."""
        callback = self.on_item_clicked
        if callable(callback):
            try:
                callback(value)
            except Exception:
                pass

    def _on_hover_enter(self, widget: tk.Widget) -> None:
        """Handle mouse enter on clickable item."""
        try:
            widget.configure(foreground="blue")
        except Exception:
            pass

    def _on_hover_leave(self, widget: tk.Widget) -> None:
        """Handle mouse leave on clickable item."""
        try:
            widget.configure(foreground="")  # Reset to default
        except Exception:
            pass

    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text with ellipsis if too long."""
        if len(text) <= max_length:
            return text
        return text[:max_length-3] + "..."

    def _create_tooltip(self, widget: tk.Widget, text: str) -> None:
        """Create a simple tooltip for the given widget."""
        def on_enter(event):
            # Create tooltip window
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.configure(background="lightyellow")
            
            # Position tooltip near cursor
            x = event.x_root + 10
            y = event.y_root + 10
            tooltip.geometry(f"+{x}+{y}")
            
            # Add text to tooltip
            label = tk.Label(
                tooltip,
                text=text,
                background="lightyellow",
                relief="solid",
                borderwidth=1,
                font=("TkDefaultFont", "8", "normal")
            )
            label.pack()
            
            # Store reference to tooltip
            widget._tooltip = tooltip
            self._active_tooltips.append(tooltip)
        
        def on_leave(event):
            # Destroy tooltip if it exists
            self._destroy_widget_tooltip(widget)
        
        def on_click(event):
            # Destroy tooltip immediately on click
            self._destroy_widget_tooltip(widget)
        
        # Bind tooltip events
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
        widget.bind("<Button-1>", on_click, add="+")  # Add to existing click handler

    def _create_tooltip_with_hover(self, widget: tk.Widget, text: str) -> None:
        """Create a tooltip with hover color effects for clickable items."""
        def on_enter(event):
            # Change color for hover effect
            self._on_hover_enter(widget)
            
            # Create tooltip window
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.configure(background="lightyellow")
            
            # Position tooltip near cursor
            x = event.x_root + 10
            y = event.y_root + 10
            tooltip.geometry(f"+{x}+{y}")
            
            # Add text to tooltip
            label = tk.Label(
                tooltip,
                text=text,
                background="lightyellow",
                relief="solid",
                borderwidth=1,
                font=("TkDefaultFont", "8", "normal")
            )
            label.pack()
            
            # Store reference to tooltip
            widget._tooltip = tooltip
            self._active_tooltips.append(tooltip)
        
        def on_leave(event):
            # Reset color
            self._on_hover_leave(widget)
            # Destroy tooltip if it exists
            self._destroy_widget_tooltip(widget)
        
        def on_click(event):
            # Reset color and destroy tooltip immediately on click
            self._on_hover_leave(widget)
            self._destroy_widget_tooltip(widget)
        
        # Bind combined events
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)
        widget.bind("<Button-1>", on_click, add="+")  # Add to existing click handler

    def _destroy_widget_tooltip(self, widget: tk.Widget) -> None:
        """Safely destroy a widget's tooltip and remove from tracking."""
        if hasattr(widget, '_tooltip'):
            try:
                tooltip = widget._tooltip
                if tooltip in self._active_tooltips:
                    self._active_tooltips.remove(tooltip)
                tooltip.destroy()
                delattr(widget, '_tooltip')
            except Exception:
                pass

    def _cleanup_all_tooltips(self) -> None:
        """Destroy all active tooltips forcefully."""
        for tooltip in self._active_tooltips[:]:  # Copy list to avoid modification during iteration
            try:
                tooltip.destroy()
            except Exception:
                pass
        self._active_tooltips.clear()