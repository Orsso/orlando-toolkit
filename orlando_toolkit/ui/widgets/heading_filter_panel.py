from __future__ import annotations

from typing import Callable, Dict, List, Optional

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

# Import to retrieve style colors
try:
    from orlando_toolkit.ui.widgets.style_legend import STYLE_COLORS
except ImportError:
    # Fallback when the module is not available – keep a synchronized final palette
    STYLE_COLORS = [
        "#E53E3E", "#38A169", "#FF6B35", "#805AD5", "#D4AF37", "#228B22",
        "#FF8C00", "#B22222", "#9400D3", "#32CD32", "#8B0000", "#FF4500",
        "#2E8B57", "#B8860B", "#8B4513", "#CD853F", "#8FBC8F", "#A0522D",
        "#2F4F4F", "#8B008B", "#556B2F", "#800000", "#483D8B"
    ]


__all__ = ["HeadingFilterPanel"]


class HeadingFilterPanel(ttk.Frame):
    """Non-modal panel to manage heading style filters grouped by level.

    Public API:
    - set_data(headings_count, occurrences_by_style, style_levels, current_exclusions)
    - update_status(text)

    Callbacks:
    - on_close(): called when the Close button is clicked
    - on_apply(exclusions: Dict[str, bool]): called when Apply is clicked
    - on_toggle_style(style: str, visible: bool): called when a style visibility toggle is clicked
    """

    def __init__(
        self,
        parent: tk.Widget,
        *,
        on_close: Optional[Callable[[], None]] = None,
        on_apply: Optional[Callable[[Dict[str, bool]], None]] = None,
        on_toggle_style: Optional[Callable[[str, bool], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)

        self.on_close = on_close
        self.on_apply = on_apply
        self.on_toggle_style = on_toggle_style

        # Data state
        self._headings_count: Dict[str, int] = {}
        self._occurrences: Dict[str, List[Dict[str, str]]] = {}
        self._style_levels: Dict[str, Optional[int]] = {}
        self._exclusions: Dict[str, bool] = {}
        self._vars_by_style: Dict[str, tk.BooleanVar] = {}
        self._toggle_vars_by_style: Dict[str, tk.BooleanVar] = {}
        self._labels_by_style: Dict[str, ttk.Label] = {}
        self._occ_labels_by_style: Dict[str, ttk.Label] = {}
        # Holds clickable pictogram widgets (labels) per style
        self._toggle_buttons_by_style: Dict[str, tk.Widget] = {}
        self._style_visibility: Dict[str, bool] = {}

        # Styles for hover/selection feedback (best-effort, safe across themes)
        try:
            style = ttk.Style()
            # Base label style for filter rows (inherits from default theme)
            style.configure("HeadingFilter.Row.TLabel")
            # Hover visually distinct; use foreground emphasis and slight background tint when supported
            style.configure("HeadingFilter.Hover.TLabel", foreground="#0098e4")
            style.map(
                "HeadingFilter.Hover.TLabel",
                foreground=[("active", "#0078b3")],
            )
            # Selected style: stronger emphasis (match tree style marker orange)
            style.configure("HeadingFilter.Selected.TLabel", foreground="#F57C00")
            try:
                # Bold font may not exist on all platforms; ignore failures
                style.configure("HeadingFilter.Selected.TLabel", font=("", 9, "bold"))
            except Exception:
                pass
        except Exception:
            pass

        # Layout
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # Header row with actions
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 2))
        header.columnconfigure(0, weight=1)

        ttk.Label(
            header,
            text="Heading Filter",
            style="HeadingFilter.Title.TLabel",
            anchor="center",
            justify="center",
        ).grid(row=0, column=0, sticky="ew")

        # Status label (warnings/info)
        self._status_var = tk.StringVar(value="")
        self._status = ttk.Label(self, textvariable=self._status_var)
        self._status.grid(row=1, column=0, sticky="ew", padx=6, pady=(0, 4))

        # Notebook to group by levels
        self._notebook = ttk.Notebook(self)
        self._notebook.grid(row=2, column=0, sticky="nsew", padx=6, pady=(0, 6))

        # Internal per-tab widgets: level -> (canvas, inner_frame)
        self._level_frames: Dict[str, ttk.Frame] = {}
        self._level_canvases: Dict[str, tk.Canvas] = {}
        self._level_inners: Dict[str, ttk.Frame] = {}

    # --- Public API ---

    def set_data(
        self,
        headings_count: Dict[str, int],
        occurrences_by_style: Dict[str, List[Dict[str, str]]],
        style_levels: Dict[str, Optional[int]],
        current_exclusions: Dict[str, bool],
    ) -> None:
        self._headings_count = dict(headings_count or {})
        self._occurrences = dict(occurrences_by_style or {})
        self._style_levels = dict(style_levels or {})
        self._exclusions = dict(current_exclusions or {})
        self._vars_by_style.clear()
        self._toggle_vars_by_style.clear()
        self._labels_by_style.clear()
        self._occ_labels_by_style.clear()
        self._toggle_buttons_by_style.clear()
        self._populate_tabs()

    def update_status(self, text: str) -> None:
        try:
            self._status_var.set(text or "")
        except Exception:
            pass

    def clear_selection(self) -> None:
        """Clear any selected style and refresh visual styling.

        Retained for compatibility with callers in `structure_tab.py`.
        """
        pass

    def toggle_style_visibility(self, style: str, visible: bool) -> None:
        """Programmatically toggle the visibility of a given style.

        Parameters
        ----------
        style : str
            The style name
        visible : bool
            True to show, False to hide
        """
        try:
            if style in self._toggle_vars_by_style:
                self._toggle_vars_by_style[style].set(visible)
                self._style_visibility[style] = visible
                self._update_toggle_button_style(style)
        except Exception:
            pass
            
    def get_visible_styles(self) -> Dict[str, bool]:
        """Return the current visibility state for all styles."""
        return dict(self._style_visibility)

    # --- UI construction helpers ---

    def _populate_tabs(self) -> None:
        # Clear existing tabs
        try:
            for tab_id in self._notebook.tabs():
                self._notebook.forget(tab_id)
        except Exception:
            pass
        # Reset level mappings
        try:
            self._level_frames.clear()
            self._level_canvases.clear()
            self._level_inners.clear()
        except Exception:
            pass

        # Group styles by levels
        grouped: Dict[str, List[str]] = {}
        for style in sorted(set(self._headings_count.keys()) | set(self._occurrences.keys()) | set(self._style_levels.keys())):
            lvl = self._style_levels.get(style)
            key = f"Level {lvl}" if isinstance(lvl, int) else "Other"
            grouped.setdefault(key, []).append(style)

        # Build each tab
        for level_key in sorted(grouped.keys(), key=lambda k: (k != "Other", int(k.split(" ")[-1]) if k != "Other" else 0)):
            frame = ttk.Frame(self._notebook)
            frame.columnconfigure(0, weight=1)
            frame.rowconfigure(0, weight=1)
            self._notebook.add(frame, text=level_key)
            self._level_frames[level_key] = frame

            # Scrollable list area (improved spacing)
            container = ttk.Frame(frame, borderwidth=1, relief="solid")
            container.grid(row=0, column=0, sticky="nsew", padx=6, pady=4)
            canvas = tk.Canvas(container, highlightthickness=0)
            vsb = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
            inner = ttk.Frame(canvas)
            inner.bind("<Configure>", lambda e, c=canvas: c.configure(scrollregion=c.bbox("all")))
            window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

            def on_canvas_configure(event: tk.Event, c=canvas, wid=window_id):
                try:
                    c.itemconfig(wid, width=event.width)
                except Exception:
                    pass
            canvas.bind("<Configure>", on_canvas_configure)
            canvas.configure(yscrollcommand=vsb.set)

            canvas.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            container.columnconfigure(0, weight=1)
            container.rowconfigure(0, weight=1)

            # Store per-level widgets
            try:
                self._level_canvases[level_key] = canvas
                self._level_inners[level_key] = inner
            except Exception:
                pass

            # Remove column headers inside the list per request

            # Rows
            styles = grouped[level_key]
            # Start at row 0 since we removed the list headers
            for i, style in enumerate(styles, start=0):
                excluded_default = bool(self._exclusions.get(style, False))
                var = tk.BooleanVar(value=excluded_default)
                self._vars_by_style[style] = var

                # Toggle variable for style visibility
                toggle_var = tk.BooleanVar(value=self._style_visibility.get(style, False))
                self._toggle_vars_by_style[style] = toggle_var

                # Widgets per row
                chk = ttk.Checkbutton(inner, variable=var, command=lambda s=style: self._on_checkbox_toggled(s))
                
                # Toggle button using an eye icon that adopts the style color when enabled
                try:
                    toggle_btn = self._create_toggle_button(inner, style, toggle_var)
                    self._toggle_buttons_by_style[style] = toggle_btn
                except Exception:
                    # Fallback: simple text button if image creation fails
                    toggle_btn = ttk.Button(
                        inner,
                        text="👁",
                        width=4,
                        command=lambda s=style: self._on_toggle_clicked(s)
                    )
                    self._toggle_buttons_by_style[style] = toggle_btn
                
                # Center style name in its column
                lbl_style = ttk.Label(inner, text=str(style), anchor="center", style="HeadingFilter.Row.TLabel", justify="center")
                occ = int(self._headings_count.get(style, 0))
                lbl_occ = ttk.Label(inner, text=str(occ), width=8, anchor="e", style="HeadingFilter.Row.TLabel")

                # Keep references for styling
                self._labels_by_style[style] = lbl_style
                self._occ_labels_by_style[style] = lbl_occ

                # Auto-apply when exclusion variable changes
                try:
                    var.trace_add("write", lambda *_args, s=style: self._on_var_changed(s))
                except Exception:
                    pass

                # Auto-toggle when visibility variable changes
                try:
                    toggle_var.trace_add("write", lambda *_args, s=style: self._on_toggle_var_changed(s))
                except Exception:
                    pass

                chk.grid(row=i, column=0, sticky="w", padx=(8, 0), pady=4)
                toggle_btn.grid(row=i, column=1, sticky="w", padx=(12, 0), pady=2)
                lbl_style.grid(row=i, column=2, sticky="ew", padx=(12, 8), pady=2)
                lbl_occ.grid(row=i, column=3, sticky="e", padx=(8, 8), pady=2)

            # Configure column weights once after all rows
            try:
                inner.columnconfigure(0, weight=0)
                inner.columnconfigure(1, weight=0)
                inner.columnconfigure(2, weight=1)
                inner.columnconfigure(3, weight=0)
            except Exception:
                pass

        # Select the first tab by default
        try:
            if self._notebook.tabs():
                self._notebook.select(self._notebook.tabs()[0])
        except Exception:
            pass

    def _create_toggle_button(self, parent: tk.Widget, style: str, toggle_var: tk.BooleanVar) -> tk.Widget:
        """Create a clickable pictogram (not a button) with an eye icon.

        The eye's iris adopts the style color when enabled; otherwise it shows a
        neutral gray. Images are stored on the button instance to avoid garbage
        collection.
        """
        try:
            # Resolve the style color
            color = self._get_style_color(style)
            # Use the same pictogram as the Preview panel: Unicode eye character
            lbl = tk.Label(parent, text="👁", cursor="hand2")
            # Enlarge the pictogram to improve readability
            try:
                # Prefer an emoji-capable font when available
                icon_font = tkfont.Font(family="Segoe UI Emoji", size=14)
                lbl.configure(font=icon_font)
            except Exception:
                try:
                    base = tkfont.nametofont("TkDefaultFont")
                    base_size = int(base.cget("size")) if isinstance(base.cget("size"), int) else 10
                    lbl.configure(font=tkfont.Font(family=base.cget("family"), size=max(12, base_size + 3)))
                except Exception:
                    pass
            lbl.bind("<Button-1>", lambda _e: self._on_toggle_clicked(style))
            # Colors for state update
            lbl.active_color = color  # type: ignore[attr-defined]
            lbl.inactive_color = "#B3B3B3"  # type: ignore[attr-defined]
            self._update_toggle_button_style(style, lbl)
            return lbl
        except Exception as e:
            # Fallback: simple text label if image creation fails
            lbl = tk.Label(parent, text="👁", cursor="hand2")
            try:
                icon_font = tkfont.Font(family="Segoe UI Emoji", size=14)
                lbl.configure(font=icon_font)
            except Exception:
                pass
            lbl.bind("<Button-1>", lambda _e: self._on_toggle_clicked(style))
            self._update_toggle_button_style(style, lbl)
            return lbl
        
    def _get_style_color(self, style: str) -> str:
        """Get the color assigned to a given style name."""
        try:
            from orlando_toolkit.ui.widgets.style_legend import _color_manager
            return _color_manager.get_color_for_style(style)
        except ImportError:
            # Fallback to the legacy method if import fails
            color_index = hash(style) % len(STYLE_COLORS)
            return STYLE_COLORS[color_index]
        
    def _create_eye_icon(self, iris_color: str) -> tk.PhotoImage:
        """Create a small eye pictogram as a PhotoImage.

        The icon consists of a gray outline and a filled circular iris whose
        color is provided by `iris_color`.
        """
        width, height = 20, 14
        img = tk.PhotoImage(width=width, height=height)

        cx, cy = width // 2, height // 2
        rx, ry = width // 2 - 1, height // 2 - 1
        outline = "#444444"

        # Draw elliptical outline (thicker ring for better visibility)
        try:
            ring = 0.26  # increased thickness of the ring around the ellipse
            inner = 1.0 - ring
            outer = 1.0 + ring
            for y in range(height):
                for x in range(width):
                    dx = (x - cx) / float(rx)
                    dy = (y - cy) / float(ry)
                    d = dx * dx + dy * dy
                    if inner <= d <= outer:
                        img.put(outline, (x, y))
        except Exception:
            # If math drawing fails, fall back to a simple rectangle
            try:
                img.put(outline, to=(0, 0, width-1, 1))
                img.put(outline, to=(0, height-2, width-1, height-1))
                img.put(outline, to=(0, 0, 1, height-1))
                img.put(outline, to=(width-2, 0, width-1, height-1))
            except Exception:
                pass

        # Draw iris as a filled circle in the center
        try:
            r = max(3, min(rx, ry) // 2 + 2)
            r2 = r * r
            for y in range(max(0, cy - r), min(height, cy + r + 1)):
                dy = y - cy
                for x in range(max(0, cx - r), min(width, cx + r + 1)):
                    dx = x - cx
                    if dx * dx + dy * dy <= r2:
                        img.put(iris_color, (x, y))
        except Exception:
            pass

        return img
        
    def _update_toggle_button_style(self, style: str, button: Optional[tk.Widget] = None) -> None:
        """Update the toggle button visual to match the current state.

        When active, the eye icon uses the style color; otherwise, a neutral
        gray eye is shown.
        """
        if button is None:
            button = self._toggle_buttons_by_style.get(style)
        if button is None:
            return
            
        try:
            is_active = self._style_visibility.get(style, False)
            # Case 1: image-based toggle
            active_img = getattr(button, "active_image", None)
            inactive_img = getattr(button, "inactive_image", None)
            if active_img is not None and inactive_img is not None:
                button.configure(image=(active_img if is_active else inactive_img))
                return

            # Case 2: label-based icon using font glyph (same pictogram as Preview panel)
            if isinstance(button, tk.Label):
                active_color = getattr(button, "active_color", "#000000")
                inactive_color = getattr(button, "inactive_color", "#B3B3B3")
                button.configure(fg=(active_color if is_active else inactive_color))
                return

            # Case 3: canvas-based vector eye
            if isinstance(button, tk.Canvas):
                iris_id = getattr(button, "iris_id", None)
                if iris_id is not None:
                    active_color = getattr(button, "active_color", "#000000")
                    inactive_color = getattr(button, "inactive_color", "#B3B3B3")
                    button.itemconfig(iris_id, fill=(active_color if is_active else inactive_color))
                return
        except Exception:
            pass

    # --- Actions ---

    def _on_apply(self) -> None:
        """Auto-apply exclusion changes to callback."""
        try:
            for style, var in self._vars_by_style.items():
                self._exclusions[style] = bool(var.get())
        except Exception:
            pass
        if callable(self.on_apply):
            self.on_apply(dict(self._exclusions))

    # --- Internal interaction handlers ---

    def _on_toggle_clicked(self, style: str) -> None:
        """Handle click on a toggle button."""
        try:
            # Invert current state
            current_state = self._style_visibility.get(style, False)
            new_state = not current_state
            
            # Update state and associated variable
            self._style_visibility[style] = new_state
            if style in self._toggle_vars_by_style:
                self._toggle_vars_by_style[style].set(new_state)
            
            # Update button visuals
            self._update_toggle_button_style(style)
            
            # Trigger callback to controller
            if callable(self.on_toggle_style):
                self.on_toggle_style(style, new_state)
        except Exception:
            pass

    def _on_toggle_var_changed(self, style: str) -> None:
        """Handle changes to the toggle variable (programmatic or via UI)."""
        try:
            var = self._toggle_vars_by_style.get(style)
            if var is not None:
                new_state = bool(var.get())
                self._style_visibility[style] = new_state
                self._update_toggle_button_style(style)
                
                # Trigger callback to controller
                if callable(self.on_toggle_style):
                    self.on_toggle_style(style, new_state)
        except Exception:
            pass

    def _on_checkbox_toggled(self, style: str) -> None:
        # Sync internal map and auto-apply
        try:
            var = self._vars_by_style.get(style)
            if var is not None:
                self._exclusions[style] = bool(var.get())
        except Exception:
            pass
        self._on_apply()

    def _on_var_changed(self, style: str) -> None:
        # Same as toggle handler, but invoked when var changes programmatically as well
        try:
            var = self._vars_by_style.get(style)
            if var is not None:
                self._exclusions[style] = bool(var.get())
        except Exception:
            pass
        self._on_apply()



