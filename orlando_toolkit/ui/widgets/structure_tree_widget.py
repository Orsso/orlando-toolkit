from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from typing import List, Optional, Callable, Dict, Tuple, Any
from orlando_toolkit.ui.widgets.structure_tree import population as _pop

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.ui.widgets.scroll_marker_bar import ScrollMarkerBar
from orlando_toolkit.ui.widgets.structure_tree import markers as _markers
from orlando_toolkit.ui.widgets.structure_tree import marker_bar_adapter as _bar


class StructureTreeWidget(ttk.Frame):
    """Tkinter widget that encapsulates a Treeview for presenting a DITA structure.

    This widget focuses solely on UI presentation concerns: rendering a tree,
    providing selection/activation hooks, and basic population helpers. It does
    not perform business logic, I/O, or reach into services/controllers.

    Callbacks:
        - on_selection_changed: Invoked when selection changes (via <<TreeviewSelect>>).
          Receives a list of selected topic_ref strings (best-effort; unknown items omitted).
        - on_item_activated: Invoked on double-click (<Double-1>). Receives a single
          activated topic_ref string, if known, else None.
        - on_context_menu: Invoked on right click (<Button-3>). Receives the Tk event
          and a list of currently selected topic_ref strings (unknown items omitted).

    Notes
    -----
    - Internally maps Treeview item IDs to topic_ref strings. Selection APIs operate
      on topic_ref values for presentation-level decoupling.
    - Population is best-effort and resilient to incomplete context. The tree is rebuilt
      on each call to populate_tree.
    - UI-only: no service or controller imports. No logging or I/O.
    """

    def __init__(
        self,
        master: "tk.Widget",
        *,
        on_selection_changed: Optional[Callable[[List[str]], None]] = None,
        on_item_activated: Optional[Callable[[Optional[str]], None]] = None,
        on_context_menu: Optional[Callable[[tk.Event, List[str]], None]] = None,
    ) -> None:
        """Initialize the StructureTreeWidget.

        Parameters
        ----------
        master : tk.Widget
            Parent widget.
        on_selection_changed : Optional[Callable[[List[str]], None]], optional
            Callback invoked when selection changes. Receives a list of selected
            topic_ref strings (unknown items omitted).
        on_item_activated : Optional[Callable[[Optional[str]], None]], optional
            Callback invoked on item activation (double-click). Receives the
            activated topic_ref string if known, else None.
        on_context_menu : Optional[Callable[[tk.Event, List[str]], None]], optional
            Callback invoked on context menu (right-click). Receives the event
            and a list of currently selected topic_ref strings.
        """
        super().__init__(master)
        self._on_selection_changed = on_selection_changed
        self._on_item_activated = on_item_activated
        self._on_context_menu = on_context_menu

        # Configure a custom Treeview style to match Heading Filter (no bg change, blue text)
        try:
            style = ttk.Style(self)
            # Create a dedicated style so we don't affect other Treeviews
            style_name = "Orlando.Treeview"
            # Store style objects for later dynamic adjustment
            self._style = style  # type: ignore[assignment]
            self._style_name = style_name  # type: ignore[assignment]
            # Determine default row background to use when selection has no highlight
            try:
                default_bg = style.lookup("Treeview", "fieldbackground") or style.lookup("Treeview", "background") or ""
            except Exception:
                default_bg = ""
            self._default_row_bg = default_bg  # type: ignore[assignment]
            # Initial map: keep background stable; set selected foreground to blue
            style.map(
                style_name,
                background=[('selected', default_bg), ('!focus selected', default_bg)],
                foreground=[('selected', '#0098e4'), ('!focus selected', '#0098e4')],
            )
        except Exception:
            style_name = "Treeview"

        # Tree and scrollbar
        # Provide a non-zero default row height to improve bbox availability in headless tests
        self._tree = ttk.Treeview(self, show="tree", selectmode="extended", style=style_name, height=12)
        self._vsb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        # Proxy yscroll updates so we can update the marker bar viewport too
        self._tree.configure(yscrollcommand=self._on_tree_yscroll)

        self._tree.grid(row=0, column=0, sticky="nsew")
        # Marker bar placed to the left of the scrollbar (non-stretching)
        try:
            self._marker_bar = ScrollMarkerBar(self, width=16, on_jump=lambda n: _bar.on_marker_jump(self, n), on_set_viewport=lambda f: _bar.on_marker_set_viewport(self, f))
            self._marker_bar.grid(row=0, column=1, sticky="ns")
        except Exception:
            self._marker_bar = None  # type: ignore[assignment]
        # Scrollbar at the far right
        self._vsb.grid(row=0, column=2, sticky="ns")

        self.columnconfigure(0, weight=1)  # tree
        self.columnconfigure(1, weight=0)  # marker bar
        self.columnconfigure(2, weight=0)  # scrollbar
        self.rowconfigure(0, weight=1)

        # Overlayed expand/collapse controls inside the tree area (no extra row)
        try:
            overlay = ttk.Frame(self._tree)
            btn_expand = ttk.Button(overlay, text="+", width=2, command=self.expand_all)
            btn_collapse = ttk.Button(overlay, text="-", width=2, command=self.collapse_all)
            btn_expand.grid(row=0, column=0, padx=(0, 2))
            btn_collapse.grid(row=0, column=1)
            try:
                from orlando_toolkit.ui.custom_widgets import Tooltip  # local import to avoid cycles
                Tooltip(btn_expand, "Expand all")
                Tooltip(btn_collapse, "Collapse all")
            except Exception:
                pass
            # Place in the top-right corner of the tree viewport (left of marker/scrollbar)
            overlay.place(relx=1.0, x=-4, y=2, anchor="ne")
            # Keep position stable on resize
            self._tree.bind("<Configure>", lambda _e: overlay.place_configure(relx=1.0, x=-4, y=2, anchor="ne"))
        except Exception:
            pass

        # Internal mappings: tree item id -> topic_ref
        self._id_to_ref: Dict[str, str] = {}
        # Reverse lookup for convenience: topic_ref -> first tree item id
        self._ref_to_id: Dict[str, str] = {}
        # Store resolved heading style per item id when available (topicref/topichead)
        self._id_to_style: Dict[str, str] = {}
        
        # Store reference to ditamap_root for section number calculation
        self._ditamap_root: Optional[object] = None
        # Precomputed section numbers for current ditamap_root
        self._section_number_map: Dict[object, str] = {}
        
        # Session-only expansion state tracking (no persistence between app sessions)
        self._has_been_populated: bool = False

        # Event bindings
        self._tree.bind("<<TreeviewSelect>>", self._on_select_event, add="+")
        self._tree.bind("<Double-1>", self._on_double_click_event, add="+")
        self._tree.bind("<Button-1>", self._on_single_click_event, add="+")
        self._tree.bind("<Button-3>", self._on_right_click_event, add="+")
        # Marker bar updates when branches open/close
        try:
            self._tree.bind("<<TreeviewOpen>>", lambda e: self._on_section_toggle(e, True), add="+")
            self._tree.bind("<<TreeviewClose>>", lambda e: self._on_section_toggle(e, False), add="+")
            # On vertical scroll via mouse wheel or touchpad, avoid recomputing markers repeatedly.
            self._tree.bind("<MouseWheel>", lambda _e: _bar.throttle_marker_viewport_update(self), add="+")
            self._tree.bind("<Button-4>", lambda _e: _bar.throttle_marker_viewport_update(self), add="+")  # Linux scroll up
            self._tree.bind("<Button-5>", lambda _e: _bar.throttle_marker_viewport_update(self), add="+")  # Linux scroll down
        except Exception:
            pass

        # Style exclusions map: style -> excluded flag (True means exclude)
        self._style_exclusions: Dict[str, bool] = {}
        
        # Style visibility tracking: style -> visible flag (True means show marker)
        self._style_visibility: Dict[str, bool] = {}
        
        # Style -> color mapping cache
        self._style_colors: Dict[str, str] = {}
        
        # Style markers cache: color -> PhotoImage
        self._style_markers: Dict[str, tk.PhotoImage] = {}

        # Tag configuration and marker icons for highlights
        try:
            # Fixed-width marker slot to prevent layout shifting; larger size for better visibility
            marker_w, marker_h = 20, 20
            self._marker_w, self._marker_h = marker_w, marker_h
            # Always reserve space with transparent background when no marker is needed
            self._marker_none = tk.PhotoImage(width=marker_w, height=marker_h)

            def _draw_circle(img: tk.PhotoImage, cx: int, cy: int, r: int, color: str) -> None:
                try:
                    r2 = r * r
                    for yy in range(max(0, cy - r), min(marker_h, cy + r + 1)):
                        dy = yy - cy
                        for xx in range(max(0, cx - r), min(marker_w, cx + r + 1)):
                            dx = xx - cx
                            if dx * dx + dy * dy <= r2:
                                img.put((color,), to=(xx, yy, xx + 1, yy + 1))
                except Exception:
                    pass

            def _build_variant(draw_search: bool, draw_filter: bool) -> tk.PhotoImage:
                img = tk.PhotoImage(width=marker_w, height=marker_h)
                s_color = "#0098e4"  # blue
                f_color = "#F57C00"  # orange
                # Slightly smaller radius and shorter arrow to prevent overlap
                radius = 4
                arrow_size = 10
                cy = marker_h // 2
                # Place markers with more spacing to avoid overlap
                left_cx = 4   # Search arrow position (left)
                # Place style circle near right edge but fully inside image and away from text
                right_cx = marker_w - 5
                if draw_search:
                    # Use shared graphics helper
                    try:
                        from orlando_toolkit.ui.common.graphics import draw_arrow_on_image
                        draw_arrow_on_image(img, left_cx, cy, arrow_size, s_color)
                    except Exception:
                        pass
                if draw_filter:
                    _draw_circle(img, cx=right_cx, cy=cy, r=radius, color=f_color)
                return img

            try:
                self._marker_search = _build_variant(True, False)
            except Exception:
                self._marker_search = self._marker_none  # type: ignore[assignment]
            try:
                self._marker_filter = _build_variant(False, True)
            except Exception:
                self._marker_filter = self._marker_none  # type: ignore[assignment]
            try:
                self._marker_both = _build_variant(True, True)
            except Exception:
                self._marker_both = self._marker_none  # type: ignore[assignment]
            # Tags exist but no background; visual feedback is the marker image
            self._tree.tag_configure("search-match")
            self._tree.tag_configure("filter-match")
            # Ensure tag-based highlighting wins over selection: selection tag has no bg
            self._tree.tag_configure("selected-row", background="")
            # Distinguish sections (topichead) visually with bold font
            try:
                base_font = None
                try:
                    base_font = tkfont.nametofont("TkDefaultFont")
                except Exception:
                    base_font = None
                if base_font is not None:
                    # Determine base size and build derived fonts
                    try:
                        base_size = int(tkfont.Font(self, font=base_font).cget("size"))
                    except Exception:
                        base_size = 9
                    # Section: base + 2, bold
                    self._font_section = tkfont.Font(self, font=base_font)
                    try:
                        self._font_section.configure(weight="bold", size=base_size + 2)
                    except Exception:
                        self._font_section.configure(weight="bold")
                    self._tree.tag_configure("section", font=self._font_section)
                    # Selected row: base + 4, normal weight
                    self._font_selected = tkfont.Font(self, font=base_font)
                    try:
                        self._font_selected.configure(size=base_size + 4)
                    except Exception:
                        self._font_selected.configure()
                    self._tree.tag_configure("selected-row", font=self._font_selected, foreground="#0098e4")
                    # Selected + highlighted: base + 4, underline (no bold) for clear signal on selection
                    self._font_selected_highlight = tkfont.Font(self, font=base_font)
                    try:
                        self._font_selected_highlight.configure(size=base_size + 4, underline=1)
                    except Exception:
                        self._font_selected_highlight.configure(underline=1)
                    self._tree.tag_configure("selected-highlight", font=self._font_selected_highlight, foreground="#0098e4")
                else:
                    # Fallback tuple if default font lookup fails
                    self._tree.tag_configure("section", font=("", 11, "bold"))
                    self._tree.tag_configure("selected-row", font=("", 13), foreground="#0098e4")
                    self._tree.tag_configure("selected-highlight", font=("", 13, "underline"), foreground="#0098e4")
            except Exception:
                pass
        except Exception:
            pass

        # Provide a helper for helpers: create an empty marker image with current dimensions
        def _create_empty_marker(width: int, height: int) -> tk.PhotoImage:
            try:
                return tk.PhotoImage(width=width, height=height)
            except Exception:
                # Fallback to default marker size
                return tk.PhotoImage(width=getattr(self, "_marker_w", 16), height=getattr(self, "_marker_h", 16))
        # Bind as instance method so helper modules can call widget._create_empty_marker
        self._create_empty_marker = _create_empty_marker  # type: ignore[attr-defined]

    # Public API

    def set_style_exclusions(self, exclusions: Dict[str, bool]) -> None:
        """Set style exclusions used during traversal.

        exclusions: Dict[str, bool] where True means the style is excluded.
        """
        try:
            self._style_exclusions = dict(exclusions or {})
        except Exception:
            # Keep robustness; if something odd is passed, reset to empty
            self._style_exclusions = {}

    def populate_tree(self, context: DitaContext, max_depth: int = 999) -> None:
        """Delegate population to module function (keeps widget lean)."""
        _pop.populate_tree(self, context, max_depth=max_depth)

    def update_selection(self, item_refs: List[str]) -> None:
        """Update the selection to the provided topic_ref values.

        Non-existent refs are silently ignored. Existing selected items not in
        the provided list will be deselected.

        Parameters
        ----------
        item_refs : List[str]
            List of topic_ref strings to select and focus.
        """
        # Compute item ids for provided refs
        ids = []
        for ref in item_refs:
            item_id = self.find_item_by_ref(ref)
            if item_id:
                ids.append(item_id)

        # Update selection in a single operation to avoid UI side effects
        self._tree.selection_set(ids)
        # Focus the first if present
        if ids:
            self._tree.focus(ids[0])
            # Ensure visibility without toggling expand/collapse states inadvertently
            try:
                self._tree.see(ids[0])
            except Exception:
                pass
        # Sync bold selection tag
        try:
            self._update_selection_tags()
        except Exception:
            pass
        # Update selection indicator in the marker bar
        try:
            self._update_selection_indicator()
        except Exception:
            pass

    def focus_item_by_ref(self, topic_ref: str, ensure_visible: bool = True) -> None:
        """Move focus to the first item matching the given topic_ref without changing selection.

        Parameters
        ----------
        topic_ref : str
            The reference of the item to focus.
        ensure_visible : bool, optional
            If True, scrolls the focused item into view, by default True.
        """
        try:
            item_id = self._ref_to_id.get(topic_ref)
            if not item_id:
                return
            self._tree.focus(item_id)
            if ensure_visible:
                try:
                    self._tree.see(item_id)
                except Exception:
                    pass
        except Exception:
            pass

    def focus_item_centered_by_ref(self, topic_ref: str) -> None:
        """Focus the item and center it vertically in the viewport when possible."""
        try:
            item_id = self._ref_to_id.get(topic_ref)
            if not item_id:
                return
            # Ensure it is visible first so bbox is available
            try:
                self._tree.see(item_id)
            except Exception:
                pass
            self._tree.focus(item_id)
            # Center using bbox-based scroll by units
            try:
                self._tree.update_idletasks()
                bbox = self._tree.bbox(item_id)
                if bbox:
                    x, y, w, h = bbox
                    if h <= 0:
                        return
                    widget_h = max(1, int(self._tree.winfo_height()))
                    target_center = widget_h // 2
                    row_center = y + (h // 2)
                    delta_px = row_center - target_center
                    # Convert px to rows; round to nearest int
                    rows = int(round(delta_px / float(h)))
                    if rows != 0:
                        try:
                            self._tree.yview_scroll(rows, "units")
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception:
            pass

    def set_highlight_refs(self, refs: List[str]) -> None:
        """Highlight the given topic_refs in yellow using a dedicated tag.

        This does not alter selection. Previously highlighted items are cleared first.
        """
        try:
            self.clear_highlight_refs()
            for ref in refs or []:
                item_id = self._ref_to_id.get(ref)
                if not item_id:
                    continue
                try:
                    tags = list(self._tree.item(item_id, "tags") or ())
                    if "search-match" not in tags:
                        tags.append("search-match")
                    self._tree.item(item_id, tags=tuple(tags))
                    # Apply marker image (blue). If filter tag also present, prefer filter marker.
                    self._apply_marker_image(item_id)
                except Exception:
                    continue
            # Ensure selection tags are layered under highlight tags
            try:
                self._update_selection_tags()
            except Exception:
                pass
            # Update marker bar
            try:
                from orlando_toolkit.ui.widgets.structure_tree import marker_bar_adapter as _bar
                _bar.update_marker_bar_positions(self)
            except Exception:
                pass
        except Exception:
            pass

    def clear_highlight_refs(self) -> None:
        """Remove the search highlight tag from all items."""
        try:
            for item_id in self._iter_all_item_ids():
                try:
                    tags = tuple(t for t in (self._tree.item(item_id, "tags") or ()) if t != "search-match")
                    self._tree.item(item_id, tags=tags)
                    self._apply_marker_image(item_id)
                except Exception:
                    continue
            try:
                self._update_selection_tags()
            except Exception:
                pass
            # Update marker bar
            try:
                from orlando_toolkit.ui.widgets.structure_tree import marker_bar_adapter as _bar
                _bar.update_marker_bar_positions(self)
            except Exception:
                pass
        except Exception:
            pass

    # --- Heading filter specific highlights (separate from search) ---

    def set_filter_highlight_refs(self, refs: List[str]) -> None:
        """Highlight refs for heading-filter selections without affecting search tags."""
        try:
            # Clear existing filter highlights only
            self.clear_filter_highlight_refs()
            for ref in refs or []:
                item_id = self._ref_to_id.get(ref)
                if not item_id:
                    continue
                try:
                    tags = list(self._tree.item(item_id, "tags") or ())
                    if "filter-match" not in tags:
                        tags.append("filter-match")
                    self._tree.item(item_id, tags=tuple(tags))
                    # Apply marker image (green)
                    self._apply_marker_image(item_id)
                except Exception:
                    continue
            # Ensure selection tags are layered under highlight tags
            try:
                self._update_selection_tags()
            except Exception:
                pass
            # Update marker bar
            try:
                from orlando_toolkit.ui.widgets.structure_tree import marker_bar_adapter as _bar
                _bar.update_marker_bar_positions(self)
            except Exception:
                pass
        except Exception:
            pass

    def set_style_visibility(self, style_visibility: Dict[str, bool]) -> None:
        """Update style visibility and refresh markers.

        Parameters
        ----------
        style_visibility : Dict[str, bool]
            Mapping style_name -> visible (True to show the marker)
        """
        try:
            self._style_visibility = dict(style_visibility or {})
            # Refresh all markers
            for item_id in self._iter_all_item_ids():
                try:
                    self._apply_marker_image(item_id)
                except Exception:
                    continue
            # Update marker bar
            try:
                from orlando_toolkit.ui.widgets.structure_tree import marker_bar_adapter as _bar
                _bar.update_marker_bar_positions(self)
            except Exception:
                pass
        except Exception:
            pass
            
    def update_style_colors(self, style_colors: Dict[str, str]) -> None:
        """Update style colors and recreate markers.

        Parameters
        ----------
        style_colors : Dict[str, str]
            Mapping style_name -> color_hex
        """
        try:
            self._style_colors = dict(style_colors or {})
            # Clear marker cache to force recreation
            self._style_markers.clear()
            # Refresh all markers
            for item_id in self._iter_all_item_ids():
                try:
                    self._apply_marker_image(item_id)
                except Exception:
                    continue
            # Update marker bar
            try:
                from orlando_toolkit.ui.widgets.structure_tree import marker_bar_adapter as _bar
                _bar.update_marker_bar_positions(self)
            except Exception:
                pass
        except Exception:
            pass

    def clear_filter_highlight_refs(self) -> None:
        """Remove heading-filter highlight tag from all items without touching search tags."""
        try:
            for item_id in self._iter_all_item_ids():
                try:
                    tags = tuple(t for t in (self._tree.item(item_id, "tags") or ()) if t != "filter-match")
                    self._tree.item(item_id, tags=tags)
                    self._apply_marker_image(item_id)
                except Exception:
                    continue
            try:
                self._update_selection_tags()
            except Exception:
                pass
            # Update marker bar
            try:
                self._update_marker_bar_positions()
            except Exception:
                pass
        except Exception:
            pass

    def _update_selection_tags(self) -> None:
        """Apply or remove the 'selected-row' tag and ensure highlight tags remain on top."""
        try:
            from orlando_toolkit.ui.widgets.structure_tree.selection import apply_selection_tags
            apply_selection_tags(self)
        except Exception:
            pass

    def _apply_marker_image(self, item_id: str) -> None:
        _markers.apply_marker_image(self, item_id)
            
    def _get_combined_marker(self, has_search: bool, style_color: str) -> tk.PhotoImage:
        return _markers.get_combined_marker(self, has_search, style_color)
        
    def _draw_circle_on_image(self, img: tk.PhotoImage, cx: int, cy: int, radius: int, color: str) -> None:
        # Delegate to shared graphics via markers helpers
        _ = img  # keep signature; not used here as we defer to _markers implementations when needed
        _ = cx; _ = cy; _ = radius; _ = color
        # No-op; retained for compatibility

    def _draw_arrow_on_image(self, img: tk.PhotoImage, cx: int, cy: int, size: int, color: str) -> None:
        _ = img; _ = cx; _ = cy; _ = size; _ = color
        # No-op; retained for compatibility
    
    def _draw_arrow_border(self, img: tk.PhotoImage, cx: int, cy: int, size: int, border_color: str) -> None:
        _ = img; _ = cx; _ = cy; _ = size; _ = border_color
        # No-op; retained for compatibility

    def _collect_child_styles(self, item_id: str) -> List[str]:
        return _markers.collect_child_styles(self, item_id)

    def _create_stacked_marker(self, style_colors: List[str], has_search: bool = False) -> tk.PhotoImage:
        return _markers.create_stacked_marker(self, style_colors, has_search)

    def _refresh_section_markers(self, item_ids: Optional[List[str]] = None) -> None:
        """Centralized method to refresh markers for sections when their state changes.
        
        Parameters
        ----------
        item_ids : Optional[List[str]]
            Specific items to refresh. If None, refreshes all section items.
        """
        try:
            if item_ids is None:
                # Refresh all section items
                items_to_refresh = []
                for item_id in self._iter_all_item_ids():
                    tags = tuple(self._tree.item(item_id, "tags") or ())
                    if "section" in tags:
                        items_to_refresh.append(item_id)
            else:
                items_to_refresh = item_ids
            
            # Update markers for each section
            for item_id in items_to_refresh:
                self._apply_marker_image(item_id)
            
            # Update marker bar positions once after all updates
            self._schedule_marker_update()
        except Exception:
            pass

    def _on_section_toggle(self, event: tk.Event, is_opening: bool) -> None:
        """Handle section open/close events to update stacked markers."""
        try:
            # Get the item that was toggled
            item_id = self._tree.focus()
            if item_id:
                # Use centralized refresh for this specific item
                self._refresh_section_markers([item_id])
        except Exception:
            pass

    def _iter_all_item_ids(self) -> List[str]:
        """Return a flat list of all item IDs in the tree."""
        result: List[str] = []
        try:
            def walk(parent: str) -> None:
                for cid in self._tree.get_children(parent):
                    result.append(cid)
                    walk(cid)
            walk("")
        except Exception:
            pass
        return result

    def get_selected_items(self) -> List[str]:
        """Return the list of currently selected topic_ref strings.

        Returns
        -------
        List[str]
            Selected topic_ref strings corresponding to current Treeview selection.
            Unknown items are omitted.
        """
        result: List[str] = []
        try:
            for item_id in self._tree.selection():
                ref = self._id_to_ref.get(item_id)
                if ref is not None:
                    result.append(ref)
        except Exception:
            # Be conservative and return what we have
            pass
        return result

    def find_item_by_ref(self, topic_ref: str) -> Optional[str]:
        """Find the first Treeview item ID matching the given topic_ref.

        Parameters
        ----------
        topic_ref : str
            Topic reference to look up.

        Returns
        -------
        Optional[str]
            The first matching Treeview item ID if found, else None.
        """
        return self._ref_to_id.get(topic_ref)

    def get_expanded_items(self) -> set[str]:
        """Get the set of topic_ref strings for currently expanded items.
        
        Returns
        -------
        set[str]
            Set of topic_ref strings corresponding to expanded items.
        """
        expanded_refs = set()
        try:
            for item_id in self._tree.get_children(""):
                self._collect_expanded_refs(item_id, expanded_refs)
        except Exception:
            pass
        return expanded_refs

    def get_selected_sections_index_paths(self) -> List[List[int]]:
        """Return index paths for all currently selected section rows (topichead).

        The index path is computed with `get_index_path_for_item_id`.
        """
        paths: List[List[int]] = []
        try:
            for item_id in self._tree.selection():
                try:
                    tags = tuple(self._tree.item(item_id, "tags") or ())
                except Exception:
                    tags = ()
                if "section" not in tags:
                    continue
                try:
                    path = self.get_index_path_for_item_id(item_id)
                except Exception:
                    path = []
                if path:
                    paths.append(path)
        except Exception:
            return []
        return paths
    
    def _collect_expanded_refs(self, item_id: str, expanded_refs: set[str]) -> None:
        """Recursively collect expanded item refs."""
        try:
            if self._tree.item(item_id, "open"):
                ref = self._id_to_ref.get(item_id)
                if ref is not None:
                    expanded_refs.add(ref)
            
            for child_id in self._tree.get_children(item_id):
                self._collect_expanded_refs(child_id, expanded_refs)
        except Exception:
            pass
    
    def restore_expanded_items(self, expanded_refs: set[str]) -> None:
        """Restore expansion state for items matching the provided refs.
        
        Parameters
        ----------
        expanded_refs : set[str]
            Set of topic_ref strings that should be expanded.
        """
        try:
            for ref in expanded_refs:
                item_id = self._ref_to_id.get(ref)
                if item_id:
                    self._tree.item(item_id, open=True)
            # Also update geometry after restoration
            self._tree.update_idletasks()
        except Exception:
            pass
        # Refresh all section markers after restoration
        try:
            self._refresh_section_markers()
        except Exception:
            pass
    
    def get_expanded_section_index_paths(self) -> List[List[int]]:
        """Return index paths for currently expanded section (topichead) rows.

        The index path is computed with `get_index_path_for_item_id` and is
        resilient to item id remapping after a repopulate.
        """
        paths: List[List[int]] = []
        try:
            for item_id in self._iter_all_item_ids():
                try:
                    tags = tuple(self._tree.item(item_id, "tags") or ())
                    is_open = bool(self._tree.item(item_id, "open"))
                except Exception:
                    tags = ()
                    is_open = False
                if ("section" in tags) and is_open:
                    try:
                        path = self.get_index_path_for_item_id(item_id)
                    except Exception:
                        path = []
                    if path:
                        paths.append(path)
        except Exception:
            return []
        return paths
    
    def find_item_id_by_index_path(self, index_path: List[int]) -> Optional[str]:
        """Locate a tree item id by walking the structural index path from the root.

        Returns None if the path is invalid or out of bounds.
        """
        try:
            parent = ""
            path = list(index_path or [])
            for idx in path:
                children = list(self._tree.get_children(parent))
                if idx < 0 or idx >= len(children):
                    return None
                parent = children[idx]
            return parent if parent else None
        except Exception:
            return None
    
    def restore_expanded_sections(self, index_paths: List[List[int]]) -> None:
        """Restore expansion state for sections addressed by index paths."""
        restored_ids: List[str] = []
        try:
            for path in (index_paths or []):
                item_id = self.find_item_id_by_index_path(path)
                if item_id:
                    try:
                        self._tree.item(item_id, open=True)
                        restored_ids.append(item_id)
                    except Exception:
                        continue
            # Update geometry once
            try:
                self._tree.update_idletasks()
            except Exception:
                pass
        except Exception:
            pass
        # Refresh markers for restored sections
        try:
            if restored_ids:
                self._refresh_section_markers(restored_ids)
            else:
                self._refresh_section_markers()
        except Exception:
            pass
    
    def expand_all(self) -> None:
        """Expand all items in the tree."""
        try:
            for item_id in self._tree.get_children(""):
                self._expand_recursive(item_id)
        except Exception:
            pass
        # Refresh all section markers after expansion
        try:
            self._refresh_section_markers()
        except Exception:
            pass
    
    def collapse_all(self) -> None:
        """Collapse all items in the tree."""
        try:
            for item_id in self._tree.get_children(""):
                self._collapse_recursive(item_id)
        except Exception:
            pass
        # Refresh all section markers after collapse
        try:
            self._refresh_section_markers()
        except Exception:
            pass
    
    def _expand_recursive(self, item_id: str) -> None:
        """Recursively expand an item and all its children."""
        try:
            self._tree.item(item_id, open=True)
            for child_id in self._tree.get_children(item_id):
                self._expand_recursive(child_id)
        except Exception:
            pass
    
    def _collapse_recursive(self, item_id: str) -> None:
        """Recursively collapse an item and all its children."""
        try:
            for child_id in self._tree.get_children(item_id):
                self._collapse_recursive(child_id)
            self._tree.item(item_id, open=False)
        except Exception:
            pass

    def clear(self) -> None:
        """Remove all items from the tree and clear internal mappings.

        This method rebuilds the widget to a pristine state.
        """
        try:
            self._tree.delete(*self._tree.get_children(""))
        except Exception:
            # If deletion fails for some reason, attempt a safe loop
            try:
                for child in self._tree.get_children(""):
                    self._tree.delete(child)
            except Exception:
                pass
        self._id_to_ref.clear()
        self._ref_to_id.clear()
        self._id_to_style.clear()
        self._ditamap_root = None
        self._section_number_map = {}
        # Reset population flag for next document load
        self._has_been_populated = False

    # Internal helpers (UI/presentation only)

    def _insert_item(self, parent: str, text: str, topic_ref: Optional[str], tags: Optional[Tuple[str, ...]] = None) -> str:
        safe_text = text if isinstance(text, str) and text else "Untitled"
        # Ensure tree labels are single-line and whitespace-normalized
        try:
            if isinstance(safe_text, str):
                # Collapse all whitespace (including newlines/tabs) to single spaces
                safe_text = " ".join(safe_text.split())
        except Exception:
            pass
        # Always reserve marker space to prevent layout shifting
        item_id = self._tree.insert(parent, "end", text=safe_text, image=self._marker_none, tags=(tags or ()))
        if topic_ref is not None:
            self._id_to_ref[item_id] = topic_ref
            # Only store the first id for a ref to satisfy "first Treeview item ID"
            if topic_ref not in self._ref_to_id:
                self._ref_to_id[topic_ref] = item_id
        return item_id

    def _traverse_and_insert(self, node: object, parent_id: str, depth: int, max_depth: int) -> None:
        if depth > max_depth:
            return

        # Helper to resolve style for exclusion checks
        def resolve_style(n: object) -> Optional[str]:
            # Prefer explicit data-style to preserve custom styles; fall back to level-derived
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

        # lxml-aware branch (duck-typed)
        try:
            is_element = hasattr(node, "tag")
        except Exception:
            is_element = False

        if is_element:
            try:
                tag_name = str(getattr(node, "tag", "") or "")
            except Exception:
                tag_name = ""

            # Before inserting, respect style exclusions for topicref/topichead
            if tag_name.endswith("topicref") or tag_name.endswith("topichead") or tag_name in {"topicref", "topichead"}:
                style = resolve_style(node) or "Heading"
                try:
                    if self._style_exclusions.get(style, False):
                        # Skip this node and its subtree
                        return
                except Exception:
                    pass

            # Label: prefer topicmeta/navtitle text; fall back to title/@navtitle, then generic
            label = "Item"
            try:
                text_val = None
                # Try topicmeta/navtitle
                try:
                    if hasattr(node, "find"):
                        navtitle_el = node.find("topicmeta/navtitle")
                        if navtitle_el is not None:
                            text_val = getattr(navtitle_el, "text", None)
                except Exception:
                    pass
                # Try title text
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
                    # As a last resort, use @navtitle attribute if present
                    try:
                        navtitle_attr = node.get("navtitle") if hasattr(node, "get") else None
                        if isinstance(navtitle_attr, str) and navtitle_attr.strip():
                            label = navtitle_attr.strip()
                    except Exception:
                        pass
            except Exception:
                label = "Item"

            # Add section number prefix to the label for topicref/topichead nodes
            if tag_name.endswith("topicref") or tag_name.endswith("topichead") or tag_name in {"topicref", "topichead"}:
                section_number = self._calculate_section_number(node)
                if section_number and section_number != "0":
                    label = f"{section_number}. {label}"

            # Ref: only for topicref nodes
            ref = None
            try:
                if tag_name.endswith("topicref") or tag_name == "topicref":
                    href_val = node.get("href") if hasattr(node, "get") else None
                    if isinstance(href_val, str) and href_val.strip():
                        ref = href_val.strip()
            except Exception:
                ref = None

            # Apply bold styling tag for sections (topichead), default styling for modules (topicref)
            is_section_node = (
                tag_name.endswith("topichead") or tag_name == "topichead"
            )
            current_id = self._insert_item(
                parent_id,
                label,
                ref,
                tags=(("section",) if is_section_node else None),
            )

            # Record resolved style for this item when available
            try:
                # Preserve custom explicit style when available; else synthesize from level
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
                    self._id_to_style[current_id] = node_style
            except Exception:
                pass

            # Children: topicref or topichead
            children = []
            try:
                if hasattr(node, "iterchildren"):
                    # Use iterchildren if available (lxml)
                    for child in node.iterchildren():
                        try:
                            child_tag = str(getattr(child, "tag", "") or "")
                        except Exception:
                            child_tag = ""
                        if child_tag.endswith("topicref") or child_tag.endswith("topichead") or child_tag in {"topicref", "topichead"}:
                            # Only collect topicref/topichead children; exclusions are enforced pre-order during recursion
                            children.append(child)
                elif hasattr(node, "getchildren"):
                    for child in node.getchildren():  # type: ignore[attr-defined]
                        try:
                            child_tag = str(getattr(child, "tag", "") or "")
                        except Exception:
                            child_tag = ""
                        if child_tag.endswith("topicref") or child_tag.endswith("topichead") or child_tag in {"topicref", "topichead"}:
                            # Only collect topicref/topichead children; exclusions are enforced in recursive visit
                            children.append(child)
                else:
                    # Fallback to searching via findall if present
                    try:
                        if hasattr(node, "findall"):
                            # Limit to direct children; recursion handles deeper levels
                            for child in list(node.findall("./topicref")):
                                children.append(child)
                            for child in list(node.findall("./topichead")):
                                children.append(child)
                    except Exception:
                        pass
            except Exception:
                children = []

            for child in children:
                try:
                    self._traverse_and_insert(child, current_id, depth + 1, max_depth)
                except Exception:
                    continue
            return
 
        # Generic branch (existing behavior)
        label = (
            self._safe_getattr(node, "title")
            or self._safe_getattr(node, "label")
            or self._safe_getattr(node, "name")
            or "Item"
        )
        try:
            if isinstance(label, str):
                label = " ".join(label.split())
        except Exception:
            pass
        ref = self._safe_getattr(node, "ref") or self._safe_getattr(node, "topic_ref")
        current_id = self._insert_item(parent_id, label, ref)
 
        children = (
            self._safe_getattr(node, "children")
            or self._safe_getattr(node, "topics")
            or self._safe_getattr(node, "items")
            or []
        )
        iterable = []
        if isinstance(children, dict):
            iterable = list(children.values())
        else:
            try:
                iterable = list(children)
            except Exception:
                iterable = []
 
        for child in iterable:
            try:
                self._traverse_and_insert(child, current_id, depth + 1, max_depth)
            except Exception:
                continue

    def _safe_getattr(self, obj: object, name: str) -> Optional[object]:
        try:
            return getattr(obj, name, None)
        except Exception:
            return None

    def is_item_open(self, item_id: str) -> bool:
        """Return True if the given item is expanded/open in the tree."""
        try:
            return bool(self._tree.item(item_id, "open"))
        except Exception:
            return False

    def _calculate_section_number(self, node: object) -> str:
        """Calculate the section number for a topicref/topichead node.
        
        Returns the precomputed value when available, otherwise falls back to a
        lightweight parent-walk computation. Returns "0" if not found.
        """
        if self._ditamap_root is None:
            return "0"

        # Fast path: use precomputed map when available
        try:
            if self._section_number_map:
                val = self._section_number_map.get(node)
                if isinstance(val, str):
                    return val
        except Exception:
            pass

        # Fallback: calculate by walking up parents and counting positions
        try:
            counters = []
            current = node

            while current is not None:
                parent = getattr(current, 'getparent', lambda: None)()
                if parent is None or parent == self._ditamap_root:
                    siblings = []
                    try:
                        if hasattr(self._ditamap_root, "iterchildren"):
                            for child in self._ditamap_root.iterchildren():
                                try:
                                    child_tag = str(getattr(child, "tag", "") or "")
                                except Exception:
                                    child_tag = ""
                                if child_tag.endswith("topicref") or child_tag.endswith("topichead") or child_tag in {"topicref", "topichead"}:
                                    siblings.append(child)
                        elif hasattr(self._ditamap_root, "getchildren"):
                            for child in self._ditamap_root.getchildren():
                                try:
                                    child_tag = str(getattr(child, "tag", "") or "")
                                except Exception:
                                    child_tag = ""
                                if child_tag.endswith("topicref") or child_tag.endswith("topichead") or child_tag in {"topicref", "topichead"}:
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
                                try:
                                    child_tag = str(getattr(child, "tag", "") or "")
                                except Exception:
                                    child_tag = ""
                                if child_tag.endswith("topicref") or child_tag.endswith("topichead") or child_tag in {"topicref", "topichead"}:
                                    siblings.append(child)
                        elif hasattr(parent, "getchildren"):
                            for child in parent.getchildren():
                                try:
                                    child_tag = str(getattr(child, "tag", "") or "")
                                except Exception:
                                    child_tag = ""
                                if child_tag.endswith("topicref") or child_tag.endswith("topichead") or child_tag in {"topicref", "topichead"}:
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

    def _extract_label_and_ref(self, item: object) -> Tuple[str, Optional[str]]:
        # Accept a tuple-like (label, ref), a mapping, or an object with attributes
        try:
            # Tuple or list (label, ref)
            if isinstance(item, (tuple, list)) and len(item) >= 2:
                label = item[0]
                ref = item[1]
                return (str(label) if label is not None else "Item", str(ref) if ref is not None else None)

            # Mapping-like
            if isinstance(item, dict):
                label = item.get("title") or item.get("label") or item.get("name") or "Item"
                ref = item.get("ref") or item.get("topic_ref")
                return (str(label), str(ref) if ref is not None else None)

            # Object with attributes
            label = (
                self._safe_getattr(item, "title")
                or self._safe_getattr(item, "label")
                or self._safe_getattr(item, "name")
                or "Item"
            )
            ref = self._safe_getattr(item, "ref") or self._safe_getattr(item, "topic_ref")
            return (str(label), str(ref) if ref is not None else None)
        except Exception:
            return ("Item", None)

    # Event handlers

    def _on_select_event(self, _event: tk.Event) -> None:
        if not self._on_selection_changed:
            # Still ensure visibility of first selected item for geometry/bbox stability
            try:
                sel = self._tree.selection()
                if sel:
                    self._tree.see(sel[0])
            except Exception:
                pass
            # Always update selection visuals
            try:
                self._update_selection_tags()
            except Exception:
                pass
            return
        try:
            # Ensure at least the first selected item is visible so bbox() is available
            try:
                sel = self._tree.selection()
                if sel:
                    self._tree.see(sel[0])
            except Exception:
                pass

            refs = self.get_selected_items()
            self._on_selection_changed(refs)
            # Update selection visuals to match heading filter
            try:
                self._update_selection_tags()
            except Exception:
                pass
            # Update selection indicator in marker bar
            try:
                self._update_selection_indicator()
            except Exception:
                pass
        except Exception:
            # UI robustness: swallow exceptions from callback
            pass

    def _on_double_click_event(self, event: tk.Event) -> None:
        if not self._on_item_activated:
            return
        try:
            item_id = self._tree.identify_row(event.y)
            ref = self._id_to_ref.get(item_id)
            self._on_item_activated(ref)
        except Exception:
            pass

    def _on_single_click_event(self, event: tk.Event) -> None:
        """Toggle open/closed state on section rows with a single click.

        Also prevent section rows from inheriting the selection style by removing
        the selection tag when a section is selected.
        """
        try:
            item_id = self._tree.identify_row(event.y)
            if not item_id:
                return
            # Toggle open state if this is a section
            tags = tuple(self._tree.item(item_id, "tags") or ())
            if "section" in tags:
                # If user is performing multi-select gestures (Shift/Ctrl), do not toggle
                try:
                    state = int(getattr(event, "state", 0))
                except Exception:
                    state = 0
                # Tk state bitmask: Shift=0x0001, Control=0x0004 (common across platforms)
                if (state & 0x0001) or (state & 0x0004):
                    return
                is_open = bool(self._tree.item(item_id, "open"))
                self._tree.item(item_id, open=not is_open)
                # Prevent selection styling from applying to sections
                try:
                    current_sel = set(self._tree.selection())
                    if item_id in current_sel:
                        # Remove selection of section to avoid selection styling
                        current_sel.remove(item_id)
                        self._tree.selection_set(tuple(current_sel))
                except Exception:
                    pass
                # Refresh markers for this section after toggle
                try:
                    self._refresh_section_markers([item_id])
                except Exception:
                    pass
                return
        except Exception:
            pass

    def _on_right_click_event(self, event: tk.Event) -> None:
        if not self._on_context_menu:
            return
        try:
            # Optional: adjust selection to item under cursor if not already selected.
            item_id = self._tree.identify_row(event.y)
            if item_id:
                current_sel = set(self._tree.selection())
                if item_id not in current_sel:
                    # Replace selection; conservative to avoid side-effect storms
                    self._tree.selection_set((item_id,))
                    self._tree.focus(item_id)
            refs = self.get_selected_items()
            self._on_context_menu(event, refs)
        except Exception:
            pass

    # --- Context helpers for external callers (e.g., to build context menus) ---

    def get_item_context_at(self, event: tk.Event) -> Dict[str, Any]:
        """Return context information about the item under the given mouse event.

        Returns a mapping with keys:
        - 'item_id': internal Treeview item id or ""
        - 'ref': associated topic_ref (href) when available, else None
        - 'is_section': True if the item is a section (topichead), else False
        - 'style': resolved heading style label when available, else None
        """
        item_id: str = ""
        try:
            item_id = self._tree.identify_row(getattr(event, "y", 0)) or ""
        except Exception:
            item_id = ""
        info: Dict[str, Any] = {"item_id": item_id, "ref": None, "is_section": False, "style": None}
        if not item_id:
            return info
        # Resolve ref
        try:
            info["ref"] = self._id_to_ref.get(item_id)
        except Exception:
            info["ref"] = None
        # Resolve section flag via tags
        try:
            tags = tuple(self._tree.item(item_id, "tags") or ())
            info["is_section"] = ("section" in tags)
        except Exception:
            info["is_section"] = False
        # Resolve style when known
        try:
            info["style"] = self._id_to_style.get(item_id)
        except Exception:
            info["style"] = None
        return info

    def get_style_for_ref(self, topic_ref: str) -> Optional[str]:
        """Return resolved style label for the first item matching the given ref, if known."""
        try:
            item_id = self._ref_to_id.get(topic_ref)
            if not item_id:
                return None
            return self._id_to_style.get(item_id)
        except Exception:
            return None

    # --- Successive selection and structural path helpers ---

    def are_refs_successive_topics(self, refs: List[str]) -> bool:
        """Return True if refs correspond to consecutive sibling topic items (no sections).

        - All refs must resolve to existing items
        - None of the items may be a section (topichead)
        - All items must share the same direct parent
        - Within that parent's children order, the items must be consecutive (no gaps)
        """
        try:
            if not isinstance(refs, list) or len(refs) < 2:
                return False
            item_ids: List[str] = []
            for ref in refs:
                iid = self._ref_to_id.get(ref)
                if not iid:
                    return False
                # Disallow sections
                try:
                    tags = tuple(self._tree.item(iid, "tags") or ())
                    if "section" in tags:
                        return False
                except Exception:
                    return False
                item_ids.append(iid)

            # All must share same parent
            parents = []
            for iid in item_ids:
                parents.append(self._tree.parent(iid))
            if not parents:
                return False
            parent0 = parents[0]
            if any(p != parent0 for p in parents):
                return False

            # Compute indices within the parent and check consecutiveness
            siblings = list(self._tree.get_children(parent0))
            indices = []
            for iid in item_ids:
                try:
                    indices.append(siblings.index(iid))
                except ValueError:
                    return False
            indices.sort()
            for a, b in zip(indices, indices[1:]):
                if b != a + 1:
                    return False
            return True
        except Exception:
            return False

    def get_ordered_consecutive_refs(self, refs: List[str]) -> List[str]:
        """Return refs ordered by their position in the tree, if they are consecutive.
        
        Returns empty list if refs are not consecutive or invalid.
        Used to preserve the original order when moving multiple topics.
        """
        try:
            if not self.are_refs_successive_topics(refs):
                return []
            
            # Get item IDs and their indices
            item_data = []
            parent = None
            for ref in refs:
                iid = self._ref_to_id.get(ref)
                if not iid:
                    return []
                current_parent = self._tree.parent(iid)
                if parent is None:
                    parent = current_parent
                elif parent != current_parent:
                    return []
                item_data.append((ref, iid))
            
            if parent is None:
                return []
            
            # Sort by tree position to preserve original order
            siblings = list(self._tree.get_children(parent))
            item_data.sort(key=lambda x: siblings.index(x[1]))
            
            return [ref for ref, _ in item_data]
        except Exception:
            return []

    def get_index_path_for_item_id(self, item_id: str) -> List[int]:
        """Return a stable index path for the given item among structural siblings.

        The path is computed as the sequence of indices from the root to the item,
        where each index refers to the position of the item among its parent's
        structural children (Treeview children order). This is suitable for locating
        the corresponding node in the ditamap when used consistently by the service.
        """
        path: List[int] = []
        try:
            current = item_id
            while current:
                parent = self._tree.parent(current)
                siblings = list(self._tree.get_children(parent))
                try:
                    idx = siblings.index(current)
                except ValueError:
                    break
                path.append(idx)
                current = parent
            path.reverse()
        except Exception:
            return []
        return path

    # --------------------------- Marker bar integration ---------------------------
    def _on_tree_yscroll(self, first: str, last: str) -> None:
        """Proxy yscrollcommand to scrollbar and marker bar viewport."""
        try:
            self._vsb.set(first, last)
        except Exception:
            pass
        # Only update viewport; do not recompute tick positions here to avoid flashing
        try:
            if getattr(self, "_marker_bar", None) is not None:
                self._marker_bar.set_viewport(float(first), float(last))  # type: ignore[union-attr]
        except Exception:
            pass

    def _schedule_marker_update(self) -> None:
        try:
            self.after_idle(self._update_marker_bar_positions)
        except Exception:
            pass

    def _throttle_marker_viewport_update(self) -> None:
        """On wheel scroll, only update the viewport band; positions stay as-is."""
        try:
            first, last = self._tree.yview()
            if getattr(self, "_marker_bar", None) is not None:
                self._marker_bar.set_viewport(float(first), float(last))  # type: ignore[union-attr]
        except Exception:
            pass

    def _iter_visible_item_ids(self) -> List[str]:
        return _bar.iter_visible_item_ids(self)

    def _update_marker_bar_positions(self) -> None:
        _bar.update_marker_bar_positions(self)

    def _on_marker_jump(self, norm: float) -> None:
        _bar.on_marker_jump(self, norm)

    def _on_marker_set_viewport(self, first: float) -> None:
        _bar.on_marker_set_viewport(self, first)

    # --------------------------- Selection indicator ---------------------------
    def _update_selection_indicator(self) -> None:
        """Compute normalized position of first selected visible row and update marker bar."""
        try:
            bar = getattr(self, "_marker_bar", None)
            if bar is None or not hasattr(bar, "set_selection_position"):
                return
            sel = self._tree.selection()
            if not sel:
                bar.set_selection_position(None)  # type: ignore[union-attr]
                return
            visible = self._iter_visible_item_ids()
            total = len(visible)
            if total <= 0:
                bar.set_selection_position(None)  # type: ignore[union-attr]
                return
            first_sel = sel[0]
            try:
                idx = visible.index(first_sel)
            except ValueError:
                bar.set_selection_position(None)  # type: ignore[union-attr]
                return
            pos = (idx + 0.5) / total
            bar.set_selection_position(pos)  # type: ignore[union-attr]
        except Exception:
            pass