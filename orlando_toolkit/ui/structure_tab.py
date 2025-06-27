# -*- coding: utf-8 -*-
"""Topic-structure configuration tab.

Allows the user to choose the maximum heading level that starts a new topic
and preview the resulting topic hierarchy extracted from the current
``DitaContext``.
"""

from __future__ import annotations

from typing import Optional
import copy
import tkinter as tk
from tkinter import ttk
from lxml import etree as ET

if False:  # TYPE_CHECKING pragma
    from orlando_toolkit.core.models import DitaContext

__all__ = ["StructureTab"]


class StructureTab(ttk.Frame):
    """A tab that lets the user configure topic depth and preview structure."""

    def __init__(self, parent, depth_change_callback=None, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.context: Optional["DitaContext"] = None
        self._depth_var = tk.IntVar(value=3)
        self._merge_enabled_var = tk.BooleanVar(value=True)
        self._depth_change_callback = depth_change_callback

        # --- UI ---------------------------------------------------------
        config_frame = ttk.LabelFrame(self, text="Topic splitting", padding=15)
        config_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(config_frame, text="Maximum heading level that starts a topic:").grid(row=0, column=0, sticky="w")
        depth_spin = ttk.Spinbox(
            config_frame,
            from_=1,
            to=9,
            textvariable=self._depth_var,
            width=3,
            command=self._on_depth_spin,
        )
        depth_spin.grid(row=0, column=1, sticky="w", padx=(5, 0))

        # Real-time merge toggle
        merge_chk = ttk.Checkbutton(
            config_frame,
            text="Merge deeper topics into parent (accurate preview)",
            variable=self._merge_enabled_var,
            command=self._on_merge_toggle,
        )
        merge_chk.grid(row=1, column=0, columnspan=3, sticky="w", pady=(5, 0))

        # Progress bar (hidden by default)
        self._progress = ttk.Progressbar(config_frame, mode="indeterminate")
        self._progress.grid(row=2, column=0, columnspan=3, sticky="we", pady=(4, 0))
        self._progress.grid_remove()

        # --- Toolbar for structural editing --------------------------------
        toolbar = ttk.Frame(config_frame)
        toolbar.grid(row=0, column=2, padx=(15, 0))

        self._btn_up = ttk.Button(toolbar, text="↑", width=3, command=lambda: self._move("up"))
        self._btn_down = ttk.Button(toolbar, text="↓", width=3, command=lambda: self._move("down"))
        self._btn_left = ttk.Button(toolbar, text="◀", width=3, command=lambda: self._move("promote"))
        self._btn_right = ttk.Button(toolbar, text="▶", width=3, command=lambda: self._move("demote"))
        self._btn_del = ttk.Button(toolbar, text="✖", width=3, command=self._delete_selected)

        for i, b in enumerate((self._btn_up, self._btn_down, self._btn_left, self._btn_right, self._btn_del)):
            b.grid(row=0, column=i, padx=1)

        # --- Preview ----------------------------------------------------
        preview_frame = ttk.LabelFrame(self, text="Topic preview", padding=10)
        preview_frame.pack(expand=True, fill="both", padx=10, pady=(0, 10))

        self.tree = ttk.Treeview(preview_frame, show="tree", selectmode="extended")
        self.tree.pack(side="left", expand=True, fill="both")

        # Prevent collapsing: re-open any item that tries to close
        self.tree.bind("<<TreeviewClose>>", self._on_close_attempt)
        self.tree.bind("<<TreeviewSelect>>", self._update_toolbar_state)
        self.tree.bind("<Double-1>", self._on_item_preview)

        # Global shortcuts for undo/redo
        self.bind_all("<Control-z>", self._undo)
        self.bind_all("<Control-y>", self._redo)

        # Undo/redo stacks
        self._undo_stack: list[bytes] = []
        self._redo_stack: list[bytes] = []

        # Journal of structural edits so they can be replayed after depth rebuild
        self._edit_journal: list[dict] = []

        yscroll = ttk.Scrollbar(preview_frame, orient="vertical", command=self.tree.yview)
        yscroll.pack(side="right", fill="y")

        # Enable horiz. scrolling with Shift+MouseWheel without a visible scrollbar
        self.tree.configure(yscrollcommand=yscroll.set)

        def _on_shift_wheel(event):
            self.tree.xview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        self.tree.bind("<Shift-MouseWheel>", _on_shift_wheel)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_context(self, context: "DitaContext") -> None:
        # Keep an immutable copy so we can rebuild when depth changes up/down
        self._orig_context = copy.deepcopy(context)
        self.context = copy.deepcopy(context)
        self._depth_var.set(int(context.metadata.get("topic_depth", 3)))
        self._merge_enabled_var.set(bool(context.metadata.get("realtime_merge", True)))
        self._rebuild_preview()
        self._update_toolbar_state()

        # Reset history and journal when new context loaded
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._edit_journal.clear()

        # Ensure original context retains realtime flag
        self._orig_context.metadata.setdefault("realtime_merge", True)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _rebuild_preview(self):
        self.tree.delete(*self.tree.get_children())
        if self.context is None or self.context.ditamap_root is None:
            return

        max_depth = int(self._depth_var.get())

        # Mapping tree item id -> topicref element for inline editing
        self._item_map = {}

        def _clean(txt: str) -> str:
            return " ".join(txt.split())

        def _add_topicref(node: ET.Element, level: int, parent_id=""):
            for tref in [el for el in list(node) if el.tag in ("topicref", "topichead")]:
                t_level = int(tref.get("data-level", level))
                if t_level > max_depth:
                    continue
                navtitle_el = tref.find("topicmeta/navtitle")
                raw_title = navtitle_el.text if navtitle_el is not None else "(untitled)"
                title = _clean(raw_title)
                item_id = self.tree.insert(parent_id, "end", text=title)
                self._item_map[item_id] = tref
                _add_topicref(tref, t_level + 1, item_id)

        _add_topicref(self.context.ditamap_root, 1)

        # Expand everything so the hierarchy is fully visible
        for itm in self.tree.get_children(""):
            self.tree.item(itm, open=True)
            self._expand_all(itm)

        self._update_toolbar_state()

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_depth_spin(self):
        # Live preview of depth change (local, does not trigger re-parse)
        new_depth = int(self._depth_var.get())
        if self.context:
            self.context.metadata["topic_depth"] = new_depth
            self._maybe_merge_and_refresh()

    def _on_merge_toggle(self):
        if self.context is None:
            return
        self.context.metadata["realtime_merge"] = bool(self._merge_enabled_var.get())
        # Recompute preview to reflect potential content change
        self._maybe_merge_and_refresh()

    def _maybe_merge_and_refresh(self):
        if self.context is None:
            return

        # Always start from pristine copy to allow depth increases
        if hasattr(self, "_orig_context"):
            self.context = copy.deepcopy(self._orig_context)

        depth_limit = int(self._depth_var.get())
        realtime = bool(self._merge_enabled_var.get())
        self.context.metadata["realtime_merge"] = realtime

        if realtime:
            self._progress.grid()
            self._progress.start()
            self.update_idletasks()

            from orlando_toolkit.core.merge import merge_topics_below_depth

            if self.context.metadata.get("merged_depth") != depth_limit:
                merge_topics_below_depth(self.context, depth_limit)

            self._progress.stop()
            self._progress.grid_remove()

        else:
            # Ensure merged_depth flag cleared so export merges later
            self.context.metadata.pop("merged_depth", None)
            self.context.metadata["realtime_merge"] = False

        # Replay structural edits on refreshed context
        self._replay_edits()

        self._rebuild_preview()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _expand_all(self, item):
        for child in self.tree.get_children(item):
            self.tree.item(child, open=True)
            self._expand_all(child)

    def _on_close_attempt(self, event):
        item = self.tree.focus()
        if item:
            self.tree.item(item, open=True)
        return "break"

    def _on_item_preview(self, event):
        item = self.tree.focus()
        if not item or item not in self._item_map:
            return

        tref_el = self._item_map[item]

        # --- Build preview window -----------------------------------
        from tkinter import scrolledtext as _stxt
        import tempfile, webbrowser, pathlib

        preview_win = tk.Toplevel(self)
        preview_win.title("XML Preview")
        preview_win.geometry("700x500")

        # Toolbar with "Open in browser" button
        toolbar = ttk.Frame(preview_win)
        toolbar.pack(fill="x")

        def _open_browser():
            """Render HTML preview to a temporary file and open it externally."""
            from orlando_toolkit.core.preview.xml_compiler import render_html_preview  # type: ignore

            html = render_html_preview(self.context, tref_el) if self.context else "<p>No preview</p>"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.html', prefix='orlando_preview_', mode='w', encoding='utf-8')
            tmp.write(html)
            tmp.flush()
            webbrowser.open_new_tab(pathlib.Path(tmp.name).as_uri())

        ttk.Button(toolbar, text="Open HTML in Browser", command=_open_browser).pack(side="left", padx=5, pady=2)

        # Raw XML display
        raw_txt = _stxt.ScrolledText(preview_win, wrap="none")
        raw_txt.pack(fill="both", expand=True)

        from orlando_toolkit.core.preview.xml_compiler import get_raw_topic_xml  # type: ignore
        xml_str = get_raw_topic_xml(self.context, tref_el) if self.context else ""
        raw_txt.insert("1.0", xml_str)
        raw_txt.yview_moveto(0)

    def _update_toolbar_state(self, event=None):
        """Enable/disable toolbar buttons based on current selection."""
        sel = self.tree.selection()
        enabled = len(sel) > 0
        for btn in (self._btn_up, self._btn_down, self._btn_left, self._btn_right, self._btn_del):
            btn.config(state="normal" if enabled else "disabled")

    # ------------------------------------------------------------------
    # Structural mutations
    # ------------------------------------------------------------------

    def _move(self, direction: str):
        selected = list(self.tree.selection())
        if not selected:
            return

        # Snapshot for undo
        self._push_undo_snapshot()

        changed = False
        selected_trefs: list[ET.Element] = []

        for sel in selected:
            if sel not in self._item_map:
                continue
            tref = self._item_map[sel]
            parent = tref.getparent()
            if parent is None:
                continue
            siblings = list(parent)
            idx = siblings.index(tref)

            if direction == "up" and idx > 0:
                parent.remove(tref)
                parent.insert(idx - 1, tref)
                changed = True
                selected_trefs.append(tref)
            elif direction == "down" and idx < len(siblings) - 1:
                parent.remove(tref)
                parent.insert(idx + 1, tref)
                changed = True
                selected_trefs.append(tref)
            elif direction == "promote" and parent.tag == "topicref":
                grand = parent.getparent()
                if grand is not None:
                    parent_idx = list(grand).index(parent)
                    parent.remove(tref)
                    grand.insert(parent_idx + 1, tref)
                    changed = True
                    selected_trefs.append(tref)
            elif direction == "demote" and idx > 0:
                left_sibling = siblings[idx - 1]
                left_sibling.append(tref)
                changed = True
                selected_trefs.append(tref)

        if changed:
            self._rebuild_preview()
            self._restore_selection(selected_trefs)

            # Record move in journal
            for tref in selected_trefs:
                href = tref.get("href", "")
                self._edit_journal.append({"op": "move", "href": href, "dir": direction})

    def _delete_selected(self):
        selected = list(self.tree.selection())
        removed = False
        removed_trefs = []
        for sel in selected:
            tref = self._item_map.get(sel)
            if tref is None:
                continue
            parent = tref.getparent()
            if parent is None:
                continue
            parent.remove(tref)
            removed_trefs.append(tref)
            removed = True
        if removed:
            self._rebuild_preview()
            # after delete nothing selected

            for t in removed_trefs:
                href = t.get("href", "")
                self._edit_journal.append({"op": "delete", "href": href})

    # ------------------------------------------------------------------
    # Undo / Redo helpers
    # ------------------------------------------------------------------

    def _snapshot(self) -> bytes:
        """Serialize current ditamap for undo/redo."""
        if self.context and self.context.ditamap_root is not None:
            from lxml import etree as _ET
            return _ET.tostring(self.context.ditamap_root)
        return b""

    def _push_undo_snapshot(self):
        snap = self._snapshot()
        if snap:
            self._undo_stack.append(snap)
            self._redo_stack.clear()

    def _undo(self, event=None):
        if not self._undo_stack:
            return "break"
        snap = self._undo_stack.pop()
        if snap:
            # Push current to redo
            current = self._snapshot()
            if current:
                self._redo_stack.append(current)
            self._restore_snapshot(snap)
        return "break"

    def _redo(self, event=None):
        if not self._redo_stack:
            return "break"
        snap = self._redo_stack.pop()
        if snap:
            current = self._snapshot()
            if current:
                self._undo_stack.append(current)
            self._restore_snapshot(snap)
        return "break"

    def _restore_snapshot(self, snap: bytes):
        from lxml import etree as _ET
        try:
            new_root = _ET.fromstring(snap)
        except Exception:
            return
        if self.context:
            self.context.ditamap_root = new_root
            self._rebuild_preview()

    def _restore_selection(self, tref_list):
        # Reselect items corresponding to trefs after rebuild
        sel_items = []
        for item, tref in self._item_map.items():
            if tref in tref_list:
                sel_items.append(item)
        self.tree.selection_set(sel_items)
        if sel_items:
            self.tree.focus(sel_items[0])

    # ------------------------------------------------------------------
    # Journal replay helpers
    # ------------------------------------------------------------------

    def _find_tref_by_href(self, root: ET.Element, href: str):
        if not href:
            return None
        return root.xpath(f'.//topicref[@href="{href}"]')

    def _replay_edits(self):
        if self.context is None or self.context.ditamap_root is None:
            return
        root = self.context.ditamap_root
        for rec in self._edit_journal:
            op = rec.get("op")
            href = rec.get("href", "")
            matches = self._find_tref_by_href(root, href)
            if not matches:
                continue
            tref = matches[0]
            if op == "delete":
                parent = tref.getparent()
                if parent is not None:
                    parent.remove(tref)
            elif op == "move":
                direction = rec.get("dir")
                parent = tref.getparent()
                if parent is None:
                    continue
                siblings = list(parent)
                idx = siblings.index(tref)
                if direction == "up" and idx > 0:
                    parent.remove(tref)
                    parent.insert(idx - 1, tref)
                elif direction == "down" and idx < len(siblings) - 1:
                    parent.remove(tref)
                    parent.insert(idx + 1, tref)
                elif direction == "promote" and parent.tag == "topicref":
                    grand = parent.getparent()
                    if grand is not None:
                        pidx = list(grand).index(parent)
                        parent.remove(tref)
                        grand.insert(pidx + 1, tref)
                elif direction == "demote" and idx > 0:
                    left = siblings[idx - 1]
                    left.append(tref) 