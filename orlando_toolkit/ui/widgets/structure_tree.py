from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Callable, Dict, Tuple

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

        # Tree and scrollbar
        self._tree = ttk.Treeview(self, show="tree", selectmode="extended")
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

        # Event bindings
        self._tree.bind("<<TreeviewSelect>>", self._on_select_event, add="+")
        self._tree.bind("<Double-1>", self._on_double_click_event, add="+")
        self._tree.bind("<Button-3>", self._on_right_click_event, add="+")

        # Style exclusions map: style -> excluded flag (True means exclude)
        self._style_exclusions: Dict[str, bool] = {}

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
        map_root = ditamap_root or self._safe_getattr(context, "map_root") or self._safe_getattr(context, "structure")

        # If a ditamap-like root exists, insert its immediate children directly at the Treeview root.
        if ditamap_root is not None and map_root is not None:
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
                return  # done; no fallback root row
            # If traversal failed unexpectedly, fall back to flat topics listing under Treeview root.

        # No ditamap_root: use existing fallback path (flat list) under Treeview root.
        root_label = self._safe_getattr(context, "title") or "Root"
        root_id = self._insert_item("", root_label, topic_ref=self._safe_getattr(context, "root_ref"))
        self._tree.item(root_id, open=True)

        # Fallback: list known topics best-effort under root with valid hrefs
        topics = self._safe_getattr(context, "topics") or self._safe_getattr(context, "topic_refs") or {}
        try:
            if isinstance(topics, dict):
                # topics: Dict[filename, Element]
                count = 0
                for filename, element in topics.items():
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
                        label = str(filename)
                    ref = f"topics/{filename}"
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

    # Internal helpers (UI/presentation only)

    def _insert_item(self, parent: str, text: str, topic_ref: Optional[str]) -> str:
        safe_text = text if isinstance(text, str) and text else "Untitled"
        item_id = self._tree.insert(parent, "end", text=safe_text)
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
            try:
                if hasattr(n, "get"):
                    style = n.get("data-style")
                else:
                    style = None
            except Exception:
                style = None
            if style:
                return style
            level = None
            try:
                if hasattr(n, "get"):
                    level = n.get("data-level")
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

            # Ref: only for topicref nodes
            ref = None
            try:
                if tag_name.endswith("topicref") or tag_name == "topicref":
                    href_val = node.get("href") if hasattr(node, "get") else None
                    if isinstance(href_val, str) and href_val.strip():
                        ref = href_val.strip()
            except Exception:
                ref = None

            current_id = self._insert_item(parent_id, label, ref)

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
            return
        try:
            refs = self.get_selected_items()
            self._on_selection_changed(refs)
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