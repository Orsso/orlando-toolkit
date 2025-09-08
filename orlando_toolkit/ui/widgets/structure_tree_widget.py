from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from typing import List, Optional, Callable, Dict, Tuple, Any
import xml.etree.ElementTree as ET
import logging
from orlando_toolkit.ui.widgets.structure_tree import population as _pop

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.ui.widgets.scroll_marker_bar import ScrollMarkerBar
from orlando_toolkit.ui.widgets.structure_tree import markers as _markers
from orlando_toolkit.ui.widgets.structure_tree import marker_bar_adapter as _bar

# Plugin marker support
try:
    from orlando_toolkit.core.plugins.marker_providers import get_marker_registry, MarkerProviderRegistry
except ImportError:
    # Graceful degradation if plugin system not available
    get_marker_registry = lambda: None  # type: ignore
    MarkerProviderRegistry = None  # type: ignore


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
        on_selection_changed: Optional[Callable[[List[ET.Element]], None]] = None,
        on_item_activated: Optional[Callable[[Optional[ET.Element]], None]] = None,
        on_context_menu: Optional[Callable[[tk.Event, List[ET.Element]], None]] = None,
    ) -> None:
        """Initialize the StructureTreeWidget.

        Parameters
        ----------
        master : tk.Widget
            Parent widget.
        on_selection_changed : Optional[Callable[[List[ET.Element]], None]], optional
            Callback invoked when selection changes. Receives a list of selected
            XML nodes (unknown items omitted).
        on_item_activated : Optional[Callable[[Optional[ET.Element]], None]], optional
            Callback invoked on item activation (double-click). Receives the
            activated XML node if known, else None.
        on_context_menu : Optional[Callable[[tk.Event, List[ET.Element]], None]], optional
            Callback invoked on context menu (right-click). Receives the event
            and a list of currently selected XML nodes.
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

        # XML element mappings for ALL tree items (topics + sections + future)
        self._id_to_xml_node: Dict[str, ET.Element] = {}
        self._xml_node_to_id: Dict[ET.Element, str] = {}
        # Store resolved heading style per item id when available (topicref/topichead)
        self._id_to_style: Dict[str, str] = {}
        
        # Store reference to ditamap_root for section number calculation
        self._ditamap_root: Optional[object] = None
        # Precomputed section numbers for current ditamap_root
        self._section_number_map: Dict[object, str] = {}
        
        # Session-only expansion state tracking (no persistence between app sessions)
        self._has_been_populated: bool = False
        # Lightweight caches to avoid O(N) scans on refresh
        self._expanded_item_ids: set[str] = set()
        self._expanded_xml_nodes: set[ET.Element] = set()

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
        
        # Plugin marker support
        self._marker_registry: Optional['MarkerProviderRegistry'] = None
        self._initialize_marker_providers()

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
    
    def _initialize_marker_providers(self) -> None:
        """Initialize plugin marker provider support."""
        try:
            self._marker_registry = get_marker_registry()
            if self._marker_registry:
                # Setup the built-in style marker provider with current settings
                style_provider = self._marker_registry.get_style_provider()
                if style_provider:
                    style_provider.set_style_visibility(self._style_visibility)
                    style_provider.set_style_colors(self._style_colors)
        except Exception as e:
            # Graceful degradation
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Plugin marker support not available: {e}")
            self._marker_registry = None

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
        # UNIFIED: Clear XML mappings before repopulation (prevents memory leaks)
        try:
            self._xml_node_to_id.clear()
            self._id_to_xml_node.clear()
        except Exception:
            pass
        
        _pop.populate_tree(self, context, max_depth=max_depth)

    def get_selected_xml_nodes(self) -> List[ET.Element]:
        """Get XML elements for all currently selected items (topics + sections)."""
        xml_nodes = []
        try:
            for item_id in self._tree.selection():
                xml_node = self._id_to_xml_node.get(item_id)
                if xml_node is not None:
                    xml_nodes.append(xml_node)
        except Exception:
            pass  # Robust fallback - return partial list
        return xml_nodes

    def update_selection_by_xml_nodes(self, xml_nodes: List[ET.Element]) -> None:
        """Restore selection for ALL items via XML elements (topics + sections)."""
        if not xml_nodes:
            return
        
        ids = []
        for xml_node in xml_nodes:
            try:
                item_id = self._xml_node_to_id.get(xml_node)
                if item_id:
                    ids.append(item_id)
            except Exception:
                continue  # Skip invalid nodes
        
        # Update selection in single operation (performance + UX)
        try:
            self._tree.selection_set(ids)
            # Focus the first if present
            if ids:
                self._tree.focus(ids[0])
                try:
                    self._tree.see(ids[0])
                except Exception:
                    pass
        except Exception:
            pass  # Robust fallback - no selection rather than crash

    def capture_current_selection(self) -> List[ET.Element]:
        """Capture current selection as XML elements for restoration after operations."""
        return self.get_selected_xml_nodes()

    def restore_captured_selection(self, xml_nodes: List[ET.Element]) -> None:
        """Restore selection from captured XML elements."""
        self.update_selection_by_xml_nodes(xml_nodes)

    def update_selection(self, item_refs: List[str]) -> None:
        """Backward compatible: select topics by href.
        
        Converts hrefs to XML nodes and uses unified selection system.

        Parameters
        ----------
        item_refs : List[str]
            List of topic_ref strings to select and focus.
        """
        if not item_refs:
            return
        
        target_nodes = []
        for href in item_refs:
            # Find XML node with matching href
            for xml_node in self._xml_node_to_id.keys():
                try:
                    if (hasattr(xml_node, 'get') and 
                        hasattr(xml_node, 'tag') and
                        xml_node.tag == 'topicref' and
                        xml_node.get('href') == href):
                        target_nodes.append(xml_node)
                        break  # Assume hrefs are unique (standard DITA practice)
                except Exception:
                    continue  # Skip malformed elements
        
        self.update_selection_by_xml_nodes(target_nodes)

    def focus_item_by_ref(self, topic_ref: str, ensure_visible: bool = True) -> None:
        """Move focus to the first item matching the given topic_ref without changing selection."""
        try:
            item_id = self.find_item_by_ref(topic_ref)
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
        """Center the first item matching topic_ref in the viewport (back-compat helper)."""
        try:
            item_id = self.find_item_by_ref(topic_ref)
            if not item_id:
                return
            # Ensure visible then center like focus_item_centered
            try:
                self._tree.see(item_id)
            except Exception:
                pass
            self._tree.focus(item_id)
            try:
                self._tree.update_idletasks()
                bbox = self._tree.bbox(item_id)
                if bbox and len(bbox) >= 4:
                    x, y, w, h = bbox
                    if h <= 0:
                        return
                    widget_height = self._tree.winfo_height()
                    target_center = widget_height / 2
                    row_center = y + (h / 2)
                    delta_px = row_center - target_center
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

    def focus_item_centered(self, xml_node: ET.Element) -> None:
        """Focus the item using XML node and center it vertically in the viewport."""
        try:
            item_id = self._xml_node_to_id.get(xml_node)
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
                if bbox and len(bbox) >= 4:
                    x, y, w, h = bbox
                    if h <= 0:
                        return
                    widget_height = self._tree.winfo_height()
                    target_center = widget_height / 2
                    row_center = y + (h / 2)
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
                item_id = self.find_item_by_ref(ref)  # Uses unified system
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
                self._update_marker_bar_positions()
            except Exception:
                pass
        except Exception:
            pass

    def set_highlight_xml_nodes(self, nodes: List[ET.Element]) -> None:
        """Highlight XML nodes by mapping them to tree item IDs.

        Falls back gracefully if a node is not present or mapping is missing.
        """
        try:
            self.clear_highlight_refs()
            ids: List[str] = []
            for node in nodes or []:
                try:
                    iid = self._xml_node_to_id.get(node)
                    if iid:
                        ids.append(iid)
                except Exception:
                    continue
            for iid in ids:
                try:
                    tags = list(self._tree.item(iid, "tags") or ())
                    if "search-match" not in tags:
                        tags.append("search-match")
                    self._tree.item(iid, tags=tuple(tags))
                    self._apply_marker_image(iid)
                except Exception:
                    continue
            try:
                self._update_selection_tags()
            except Exception:
                pass
            try:
                self._update_marker_bar_positions()
            except Exception:
                pass
        except Exception:
            pass
            pass

    # --- Heading filter specific highlights (separate from search) ---

    def set_filter_highlight_refs(self, refs: List[str]) -> None:
        """Highlight refs for heading-filter selections without affecting search tags."""
        try:
            # Clear existing filter highlights only
            self.clear_filter_highlight_refs()
            for ref in refs or []:
                item_id = self.find_item_by_ref(ref)  # Uses unified system
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
            
            # Update plugin marker registry if available
            if self._marker_registry:
                style_provider = self._marker_registry.get_style_provider()
                if style_provider:
                    style_provider.set_style_visibility(self._style_visibility)
            
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
            
            # Update plugin marker registry if available
            if self._marker_registry:
                style_provider = self._marker_registry.get_style_provider()
                if style_provider:
                    style_provider.set_style_colors(self._style_colors)
            
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
    
    # Plugin marker support
    def register_marker_provider(self, provider: 'MarkerProvider') -> None:
        """Register a marker provider with the marker system.
        
        Args:
            provider: MarkerProvider instance to register
        """
        if not self._marker_registry:
            self._initialize_marker_providers()
        
        if self._marker_registry:
            try:
                self._marker_registry.register_provider(provider)
                # Refresh markers to include new provider
                self.refresh_all_markers()
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to register marker provider: {e}")
    
    def unregister_marker_provider(self, marker_type: str) -> None:
        """Unregister a marker provider by type.
        
        Args:
            marker_type: Type identifier of marker provider to unregister
        """
        if self._marker_registry:
            try:
                self._marker_registry.unregister_provider(marker_type)
                # Refresh markers to remove unregistered provider
                self.refresh_all_markers()
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to unregister marker provider '{marker_type}': {e}")
    
    def get_marker_providers(self) -> List['MarkerProvider']:
        """Get all registered marker providers.
        
        Returns:
            List of registered marker providers
        """
        if self._marker_registry:
            return self._marker_registry.get_enabled_providers()
        return []
    
    def refresh_all_markers(self) -> None:
        """Refresh all markers using current providers."""
        try:
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
    
    def get_item_data_for_markers(self, item_id: str) -> Dict[str, Any]:
        """Get item data for marker providers.
        
        Args:
            item_id: Tree item ID
            
        Returns:
            Dictionary containing item data for marker evaluation
        """
        try:
            # Derive topic_ref from XML mapping when available (no separate id->ref map)
            topic_ref = ""
            try:
                xml_node = self._id_to_xml_node.get(item_id)
                if xml_node is not None and hasattr(xml_node, 'tag') and xml_node.tag == 'topicref':
                    href = xml_node.get('href') if hasattr(xml_node, 'get') else None
                    if isinstance(href, str) and href.strip():
                        topic_ref = href.strip()
            except Exception:
                topic_ref = ""
            style = self._id_to_style.get(item_id, "")
            
            # Get additional context data
            data = {
                'topic_ref': topic_ref,
                'style': style,
                'item_id': item_id,
                'tree_data': {}
            }
            
            # Add tree item information
            try:
                item_values = self._tree.item(item_id)
                if item_values:
                    data['tree_data'] = {
                        'text': item_values.get('text', ''),
                        'tags': list(item_values.get('tags', [])),
                        'open': item_values.get('open', False)
                    }
            except Exception:
                pass
            
            return data
        except Exception:
            return {'topic_ref': '', 'style': '', 'item_id': item_id, 'tree_data': {}}

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
        """Handle section open/close events to update stacked markers and caches."""
        try:
            # Get the item that was toggled
            item_id = self._tree.focus()
            if item_id:
                # Update expansion caches
                try:
                    xml_node = self._id_to_xml_node.get(item_id)
                    if is_opening:
                        self._expanded_item_ids.add(item_id)
                        if xml_node is not None:
                            self._expanded_xml_nodes.add(xml_node)
                    else:
                        self._expanded_item_ids.discard(item_id)
                        if xml_node is not None:
                            self._expanded_xml_nodes.discard(xml_node)
                except Exception:
                    pass
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
        """Backward compatible: return topic hrefs for selected topics only.
        
        Sections are excluded (no href) - maintains exact API contract.

        Returns
        -------
        List[str]
            Selected topic_ref strings corresponding to current Treeview selection.
            Unknown items are omitted.
        """
        hrefs = []
        try:
            for xml_node in self.get_selected_xml_nodes():
                if hasattr(xml_node, 'get') and hasattr(xml_node, 'tag'):
                    # Only topics (topicref) have hrefs
                    if xml_node.tag == 'topicref':
                        href = xml_node.get('href')
                        if href:  # Ensure href is non-empty
                            hrefs.append(href)
        except Exception:
            pass  # Robust fallback - return partial list
        return hrefs

    def find_item_by_ref(self, topic_ref: str) -> Optional[str]:
        """Find the first Treeview item ID matching the given topic_ref.
        
        Updated to use unified XML element system.

        Parameters
        ----------
        topic_ref : str
            Topic reference to look up.

        Returns
        -------
        Optional[str]
            The first matching Treeview item ID if found, else None.
        """
        # Find XML node with matching href, then get its item_id
        for xml_node, item_id in self._xml_node_to_id.items():
            try:
                if (hasattr(xml_node, 'get') and 
                    hasattr(xml_node, 'tag') and
                    xml_node.tag == 'topicref' and
                    xml_node.get('href') == topic_ref):
                    return item_id
            except Exception:
                continue
        return None


    def get_selected_sections_index_paths(self) -> List[List[int]]:
        """Return index paths for selected sections - SIMPLIFIED using unified system."""
        paths = []
        try:
            for xml_node in self.get_selected_xml_nodes():
                if (hasattr(xml_node, 'tag') and xml_node.tag == 'topichead'):
                    item_id = self._xml_node_to_id.get(xml_node)
                    if item_id:
                        try:
                            path = self.get_index_path_for_item_id(item_id)
                            if path:
                                paths.append(path)
                        except Exception:
                            continue
        except Exception:
            pass
        return paths
    
    
    
    
    
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
            # Update cache (if node mapping exists)
            try:
                xml_node = self._id_to_xml_node.get(item_id)
                if xml_node is not None:
                    self._expanded_item_ids.add(item_id)
                    self._expanded_xml_nodes.add(xml_node)
            except Exception:
                pass
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
            # Update cache
            try:
                self._expanded_item_ids.discard(item_id)
                xml_node = self._id_to_xml_node.get(item_id)
                if xml_node is not None:
                    self._expanded_xml_nodes.discard(xml_node)
            except Exception:
                pass
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
        self._id_to_style.clear()
        self._ditamap_root = None
        self._section_number_map = {}
        # Reset population flag for next document load
        self._has_been_populated = False
        # Clear expansion caches
        try:
            self._expanded_item_ids.clear()
            self._expanded_xml_nodes.clear()
        except Exception:
            pass

    # Internal helpers (UI/presentation only)


    # Removed duplicate traversal logic; population is centralized in population.py (DRY)

    def _safe_getattr(self, obj: object, name: str) -> Optional[object]:
        try:
            return getattr(obj, name, None)
        except Exception:
            return None

    def is_item_open(self, item_id: str) -> bool:
        """Return True if the given item is expanded/open in the tree (robust Tk conversion)."""
        try:
            raw = self._tree.item(item_id, "open")
            # Use Tk's boolean conversion to handle Tcl values like '0'/'1','true','false','on','off'
            return bool(self._tree.tk.getboolean(raw))
        except Exception:
            return False

    # --------------------------- Expansion (XML-node based) ---------------------------
    def is_node_expanded(self, xml_node: ET.Element) -> bool:
        """Return True if the given XML node is expanded/open in the tree.
        Falls back to False if the node cannot be resolved.
        Emits DEBUG logs with item_id, raw open value, normalized boolean, and tags to aid diagnostics.
        """
        log = logging.getLogger(__name__)
        try:
            item_id = self._xml_node_to_id.get(xml_node)
            if not item_id:
                log.debug("is_node_expanded: node has no item_id mapping; returning False")
                return False
            try:
                raw_open = self._tree.item(item_id, "open")
            except Exception:
                raw_open = None
            try:
                norm_open = self.is_item_open(item_id)
            except Exception:
                norm_open = False
            try:
                tags = tuple(self._tree.item(item_id, "tags") or ())
            except Exception:
                tags = ()
            try:
                log.debug(
                    "is_node_expanded: item_id=%s raw_open=%r open=%s tags=%s node_tag=%s (called from predicate)",
                    item_id, raw_open, norm_open, tags, getattr(xml_node, 'tag', None)
                )
            except Exception:
                pass
            return bool(norm_open)
        except Exception as e:
            try:
                log.debug("is_node_expanded: exception=%s; returning False", e)
            except Exception:
                pass
            return False

    def get_expanded_xml_nodes(self) -> List[ET.Element]:
        """Return a list of XML nodes that are currently expanded in the tree.
        
        Uses a cached set when available to avoid scanning the entire tree.
        Falls back to a safe scan if cache is empty (e.g., first load).
        """
        try:
            if self._expanded_xml_nodes:
                # Return only nodes that still exist in mapping
                result: List[ET.Element] = []
                for node in list(self._expanded_xml_nodes):
                    try:
                        if node in self._xml_node_to_id:
                            result.append(node)
                        else:
                            # Clean out stale entries
                            self._expanded_xml_nodes.discard(node)
                    except Exception:
                        continue
                return result
        except Exception:
            pass
        # Fallback: scan mapping
        expanded: List[ET.Element] = []
        try:
            for item_id, node in list(self._id_to_xml_node.items()):
                try:
                    if self.is_item_open(item_id) and node is not None:
                        expanded.append(node)
                        # Populate cache incrementally
                        self._expanded_item_ids.add(item_id)
                        self._expanded_xml_nodes.add(node)
                except Exception:
                    continue
        except Exception:
            pass
        return expanded

    def get_visible_neighbor_xml_node(self, xml_node: ET.Element, direction: str) -> Optional[ET.Element]:
        """Return the adjacent visible XML node in the given direction ('up'|'down').

        Uses the Treeview's actual visible order (respects expand/collapse).
        Returns None when the neighbor does not exist or mapping fails.
        """
        log = logging.getLogger(__name__)
        try:
            item_id = self._xml_node_to_id.get(xml_node)
            if not item_id:
                log.debug("get_visible_neighbor: no item_id for node")
                return None
            # Prefer fast visible iterator if available
            try:
                visible_ids = list(self._iter_visible_item_ids())  # type: ignore[attr-defined]
            except Exception:
                # Fallback: compute simple visible walk
                visible_ids = self._compute_visible_item_ids()
            if not visible_ids:
                log.debug("get_visible_neighbor: no visible items")
                return None
            try:
                idx = visible_ids.index(item_id)
            except ValueError:
                log.debug("get_visible_neighbor: item_id %s not in visible list", item_id)
                return None
            if direction == 'up':
                if idx <= 0:
                    log.debug("get_visible_neighbor: at top, no up neighbor")
                    return None
                neighbor_id = visible_ids[idx - 1]
            else:
                if idx >= len(visible_ids) - 1:
                    log.debug("get_visible_neighbor: at bottom, no down neighbor")
                    return None
                neighbor_id = visible_ids[idx + 1]
            neighbor_node = self._id_to_xml_node.get(neighbor_id)
            try:
                log.debug("get_visible_neighbor: %s from %s -> %s (idx %d->%d in %d visible)", 
                         direction, getattr(xml_node, 'tag', None), getattr(neighbor_node, 'tag', None),
                         idx, idx + (-1 if direction == 'up' else 1), len(visible_ids))
            except Exception:
                pass
            return neighbor_node
        except Exception as e:
            log.debug("get_visible_neighbor: exception %s", e)
            return None

    def _compute_visible_item_ids(self) -> List[str]:
        """Compute visible item ids by DFS respecting open state."""
        result: List[str] = []
        try:
            def dfs(parent_id: str) -> None:
                for child_id in self._tree.get_children(parent_id):
                    result.append(child_id)
                    try:
                        is_open = self.is_item_open(child_id)
                    except Exception:
                        is_open = False
                    if is_open:
                        dfs(child_id)
            dfs("")
        except Exception:
            return []
        return result

    def restore_expanded_xml_nodes(self, nodes: List[ET.Element]) -> None:
        """Restore expansion state by opening the provided XML nodes when present.

        Ensures ancestor chains are opened first so targets become visible.
        """
        try:
            for node in (nodes or []):
                try:
                    # Open ancestors first (best-effort)
                    try:
                        ancestors: List[ET.Element] = []
                        parent = getattr(node, 'getparent', lambda: None)()
                        while parent is not None and parent in self._xml_node_to_id:
                            ancestors.append(parent)
                            parent = getattr(parent, 'getparent', lambda: None)()
                        for anc in reversed(ancestors):
                            anc_id = self._xml_node_to_id.get(anc)
                            if anc_id:
                                self._tree.item(anc_id, open=True)
                                self._expanded_item_ids.add(anc_id)
                                self._expanded_xml_nodes.add(anc)
                    except Exception:
                        pass

                    # Open the node itself
                    item_id = self._xml_node_to_id.get(node)
                    if item_id:
                        self._tree.item(item_id, open=True)
                        self._expanded_item_ids.add(item_id)
                        self._expanded_xml_nodes.add(node)
                except Exception:
                    continue
            try:
                self._tree.update_idletasks()
            except Exception:
                pass
            # Refresh markers for restored sections
            try:
                self._refresh_section_markers()
            except Exception:
                pass
        except Exception:
            pass

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

    # Removed legacy generic extraction helper; population.py provides traversal/extraction

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

            # Get current selection as XML nodes and pass to callback directly
            selected_nodes = self.get_selected_xml_nodes()
            self._on_selection_changed(selected_nodes)
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
            xml_node = self._id_to_xml_node.get(item_id)
            self._on_item_activated(xml_node)
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
                is_open = self.is_item_open(item_id)
                new_open = not is_open
                self._tree.item(item_id, open=new_open)
                # Update expansion caches directly (more reliable than <<TreeviewOpen/Close>> focus)
                try:
                    xml_node = self._id_to_xml_node.get(item_id)
                    if new_open:
                        self._expanded_item_ids.add(item_id)
                        if xml_node is not None:
                            self._expanded_xml_nodes.add(xml_node)
                    else:
                        self._expanded_item_ids.discard(item_id)
                        if xml_node is not None:
                            self._expanded_xml_nodes.discard(xml_node)
                except Exception:
                    pass
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
            # Get current selection as XML nodes and pass to callback directly
            selected_nodes = self.get_selected_xml_nodes()
            self._on_context_menu(event, selected_nodes)
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
            item_id = self.find_item_by_ref(topic_ref)  # Uses unified system
            if not item_id:
                return None
            return self._id_to_style.get(item_id)
        except Exception:
            return None

    # --- Successive selection and structural path helpers ---



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