from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
from typing import List, Optional, Callable, Dict, Tuple, Any

from orlando_toolkit.core.models import DitaContext


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
                foreground=[('selected', '#0B6BD3'), ('!focus selected', '#0B6BD3')],
            )
        except Exception:
            style_name = "Treeview"

        # Tree and scrollbar
        # Provide a non-zero default row height to improve bbox availability in headless tests
        self._tree = ttk.Treeview(self, show="tree", selectmode="extended", style=style_name, height=12)
        self._vsb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=self._vsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        self._vsb.grid(row=0, column=1, sticky="ns")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

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

        # Event bindings
        self._tree.bind("<<TreeviewSelect>>", self._on_select_event, add="+")
        self._tree.bind("<Double-1>", self._on_double_click_event, add="+")
        self._tree.bind("<Button-1>", self._on_single_click_event, add="+")
        self._tree.bind("<Button-3>", self._on_right_click_event, add="+")

        # Style exclusions map: style -> excluded flag (True means exclude)
        self._style_exclusions: Dict[str, bool] = {}

        # Tag configuration and marker icons for highlights
        try:
            # Fixed-width transparent marker slot to avoid shifting text; draw circular dots inside
            marker_w, marker_h = 16, 16
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
                s_color = "#1976D2"  # blue
                f_color = "#F57C00"  # orange
                radius = 3  # results in ~7px diameter dot
                cy = marker_h // 2
                # Place dots far enough apart so they never overlap
                left_cx = 4
                right_cx = marker_w - 4
                if draw_search:
                    _draw_circle(img, cx=left_cx, cy=cy, r=radius, color=s_color)
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
                    self._tree.tag_configure("selected-row", font=self._font_selected, foreground="#0B6BD3")
                    # Selected + highlighted: base + 4, underline (no bold) for clear signal on selection
                    self._font_selected_highlight = tkfont.Font(self, font=base_font)
                    try:
                        self._font_selected_highlight.configure(size=base_size + 4, underline=1)
                    except Exception:
                        self._font_selected_highlight.configure(underline=1)
                    self._tree.tag_configure("selected-highlight", font=self._font_selected_highlight, foreground="#0B6BD3")
                else:
                    # Fallback tuple if default font lookup fails
                    self._tree.tag_configure("section", font=("", 11, "bold"))
                    self._tree.tag_configure("selected-row", font=("", 13), foreground="#0B6BD3")
                    self._tree.tag_configure("selected-highlight", font=("", 13, "underline"), foreground="#0B6BD3")
            except Exception:
                pass
        except Exception:
            pass

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
        """Rebuild the entire tree from the given DITA context.

        The population is conservative and presentation-focused. It attempts to
        render a ditamap-like hierarchy when available, and otherwise falls back
        to a minimal structure that best-effort represents the context content.

        Parameters
        ----------
        context : DitaContext
            The DITA context providing structural information.
        max_depth : int, optional
            Maximum depth to populate, by default 999.

        Notes
        -----
        - This method clears the existing tree and mappings.
        - Unknown or missing structural data does not raise; the method inserts
          minimal placeholder nodes where appropriate.
        """
        self.clear()

        # Strategy:
        # 1) Try to find a map-like root and traverse its children if available.
        # 2) Otherwise, add a single "Root" and list known topics (best-effort).
        #
        # Since this module must not contain business logic and must be resilient
        # to incomplete structures, we introspect context in a guarded, minimal way.

        # Heuristics for context structure without importing services:
        # We look for attributes that may plausibly exist, and if not present,
        # fall back safely.

        # Prefer lxml ditamap_root when available
        ditamap_root = self._safe_getattr(context, "ditamap_root")
        map_root = None
        if ditamap_root is not None:
            map_root = ditamap_root
        else:
            _mr = self._safe_getattr(context, "map_root")
            if _mr is not None:
                map_root = _mr
            else:
                map_root = self._safe_getattr(context, "structure")

        # If a ditamap-like root exists, insert its immediate children directly at the Treeview root.
        if ditamap_root is not None and map_root is not None:
            # Store ditamap_root reference for section number calculation
            self._ditamap_root = ditamap_root
            # Precompute section numbers once per populate to avoid O(N^2)
            try:
                from orlando_toolkit.core.utils import calculate_section_numbers  # local import to avoid cycles
                self._section_number_map = calculate_section_numbers(ditamap_root) or {}
            except Exception:
                self._section_number_map = {}
            # No synthetic visible root label; top-level items are the map children.
            traversed = False
            try:
                # Collect only direct topicref/topichead children of map_root, then traverse each
                children = []
                try:
                    if hasattr(map_root, "iterchildren"):
                        for child in map_root.iterchildren():
                            try:
                                child_tag = str(getattr(child, "tag", "") or "")
                            except Exception:
                                child_tag = ""
                            if child_tag.endswith("topicref") or child_tag.endswith("topichead") or child_tag in {"topicref", "topichead"}:
                                children.append(child)
                    elif hasattr(map_root, "getchildren"):
                        for child in map_root.getchildren():  # type: ignore[attr-defined]
                            try:
                                child_tag = str(getattr(child, "tag", "") or "")
                            except Exception:
                                child_tag = ""
                            if child_tag.endswith("topicref") or child_tag.endswith("topichead") or child_tag in {"topicref", "topichead"}:
                                children.append(child)
                    else:
                        try:
                            if hasattr(map_root, "findall"):
                                children.extend(list(map_root.findall("./topicref")))
                                children.extend(list(map_root.findall("./topichead")))
                        except Exception:
                            pass
                except Exception:
                    children = []

                for child in children:
                    try:
                        # Parent is "" (Treeview root). Depth starts at 1 for these top-level nodes.
                        self._traverse_and_insert(child, parent_id="", depth=1, max_depth=max_depth)
                    except Exception:
                        continue
                traversed = True
            except Exception:
                traversed = False

            if traversed:
                # Expand all items by default for ditamap branch too
                try:
                    self.expand_all()
                    self._tree.update_idletasks()
                except Exception:
                    pass
                return  # done; no fallback root row
            # If traversal failed unexpectedly, fall back to flat topics listing under Treeview root.

        # No ditamap_root: use existing fallback path (flat list) under Treeview root.
        # Reset precomputed section numbers as there is no structured map.
        self._section_number_map = {}
        root_label = self._safe_getattr(context, "title") or "Root"
        root_id = self._insert_item("", root_label, topic_ref=self._safe_getattr(context, "root_ref"))
        self._tree.item(root_id, open=True)

        # Fallback: list known topics best-effort under root with valid hrefs
        topics = self._safe_getattr(context, "topics") or self._safe_getattr(context, "topic_refs") or {}
        try:
            if isinstance(topics, dict):
                # topics: Dict[id_or_filename, Element]
                count = 0
                for key, element in topics.items():
                    if count >= 10000:
                        break
                    # Label from element's <title> if available
                    label = None
                    try:
                        if element is not None and hasattr(element, "find"):
                            title_el = element.find("title")
                            if title_el is not None:
                                text_val = getattr(title_el, "text", None)
                                if isinstance(text_val, str) and text_val.strip():
                                    label = text_val.strip()
                    except Exception:
                        label = None
                    if not label:
                        label = str(key)
                    # Keep ref equal to the dict key to align with tests expecting raw ids like "A", "B", "C".
                    ref = str(key)
                    self._insert_item(root_id, label, topic_ref=ref)
                    count += 1
            else:
                # If not a dict, reuse existing generic best-effort but ensure refs look like hrefs if possible
                count = 0
                iterable = topics
                try:
                    iterable = list(iterable)
                except Exception:
                    iterable = []
                for item in iterable:
                    if count >= 10000:
                        break
                    label, ref = self._extract_label_and_ref(item)
                    # Force href-like if looks like a filename without prefix
                    if isinstance(ref, str) and ref and not ref.startswith("topics/") and ref.endswith(".dita"):
                        ref = f"topics/{ref}"
                    self._insert_item(root_id, label, topic_ref=ref)
                    count += 1
        except Exception:
            # Keep only the root on failure
            pass

        # Expand all items by default and ensure geometry is realized so bbox is available
        try:
            self.expand_all()
            # Force a couple of idle updates to ensure layout is complete
            self._tree.update_idletasks()
            try:
                # Some environments require an additional tiny delay to compute bboxes
                self.after(0, self._tree.update_idletasks)
            except Exception:
                pass
        except Exception:
            pass

        # Best-effort: touch visibility for all rows so bbox() becomes available in headless tests
        try:
            for iid in self._iter_all_item_ids():
                try:
                    self._tree.see(iid)
                except Exception:
                    continue
            # Final idle flush after forcing visibility
            try:
                self._tree.update_idletasks()
            except Exception:
                pass
        except Exception:
            pass

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
        except Exception:
            pass

    def _update_selection_tags(self) -> None:
        """Apply or remove the 'selected-row' tag and ensure highlight tags remain on top.

        - Adds 'selected-row' for all selected items (bold + larger font) without altering
          search/filter tags.
        - Reorders tags so that 'search-match'/'filter-match' come AFTER 'selected-row' when present,
          keeping the yellow highlight visible on selected items.
        """
        try:
            selected_ids = set(self._tree.selection())
            for item_id in self._iter_all_item_ids():
                try:
                    tags = list(self._tree.item(item_id, "tags") or ())
                    has_selected = "selected-row" in tags
                    if item_id in selected_ids:
                        if not has_selected and ("section" not in tags):
                            tags.append("selected-row")
                        # Reorder so highlight tags are last
                        has_search = "search-match" in tags
                        has_filter = "filter-match" in tags
                        # Remove instances
                        if has_search:
                            tags = [t for t in tags if t != "search-match"]
                        if has_filter:
                            tags = [t for t in tags if t != "filter-match"]
                        # Ensure selected-row exists, then append highlights at the end
                        if ("selected-row" not in tags) and ("section" not in tags):
                            tags.append("selected-row")
                        # If selected and highlighted, add special tag to increase contrast
                        if has_search or has_filter:
                            if "selected-highlight" not in tags:
                                tags.append("selected-highlight")
                        else:
                            # Remove selected-highlight if no highlight now
                            tags = [t for t in tags if t != "selected-highlight"]
                        if has_search:
                            tags.append("search-match")
                        if has_filter:
                            tags.append("filter-match")
                        self._tree.item(item_id, tags=tuple(tags))
                        # Keep marker synced
                        self._apply_marker_image(item_id)
                    else:
                        if has_selected:
                            # Remove only the selection tag, preserving any highlight tags
                            tags = [t for t in tags if t not in ("selected-row", "selected-highlight")]
                            self._tree.item(item_id, tags=tuple(tags))
                        self._apply_marker_image(item_id)
                except Exception:
                    continue
        except Exception:
            pass

    def _apply_marker_image(self, item_id: str) -> None:
        """Apply a small two-dot marker image in a fixed slot based on tags.

        Priority/stacking:
        - Both present -> two dots (blue left, green right).
        - Filter only -> green dot.
        - Search only -> blue dot.
        - None -> transparent/blank slot image.
        """
        try:
            tags = tuple(self._tree.item(item_id, "tags") or ())
            has_search = ("search-match" in tags)
            has_filter = ("filter-match" in tags)
            if has_search and has_filter and getattr(self, "_marker_both", None) is not None:
                self._tree.item(item_id, image=self._marker_both)
            elif has_filter and getattr(self, "_marker_filter", None) is not None:
                self._tree.item(item_id, image=self._marker_filter)
            elif has_search and getattr(self, "_marker_search", None) is not None:
                self._tree.item(item_id, image=self._marker_search)
            else:
                # No marker: clear the image so level-1 items have no extra left padding
                self._tree.item(item_id, image="")
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
    
    def expand_all(self) -> None:
        """Expand all items in the tree."""
        try:
            for item_id in self._tree.get_children(""):
                self._expand_recursive(item_id)
        except Exception:
            pass
    
    def collapse_all(self) -> None:
        """Collapse all items in the tree."""
        try:
            for item_id in self._tree.get_children(""):
                self._collapse_recursive(item_id)
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
        # Insert without a reserved marker slot; we only set an image when a marker is needed
        item_id = self._tree.insert(parent, "end", text=safe_text, image="", tags=(tags or ()))
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
                # Stop further default handling to avoid double-toggle
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