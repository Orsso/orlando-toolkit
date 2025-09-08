from __future__ import annotations

from typing import Callable, List, Optional, Tuple


class ContextActions:
    """Encapsulate context-menu actions to keep StructureTab lean."""

    def __init__(
        self,
        *,
        controller_getter: Callable[[], object],
        tree: object,
        refresh_tree: Callable[[], None],
        select_style: Optional[Callable[[str], None]] = None,
        set_depth: Optional[Callable[[int], None]] = None,
    ) -> None:
        self._get_controller = controller_getter
        self._tree = tree
        self._refresh = refresh_tree
        self._select_style = select_style
        self._set_depth = set_depth
        # Depth prompt session state
        self._suppress_depth_prompt: bool = False
        self._auto_expand_on_deeper_insert: bool = False

    # ----------------------------- Internal helpers -----------------------------
    def _get_current_depth(self) -> int:
        ctrl = self._get_controller()
        try:
            if ctrl is not None and hasattr(ctrl, "max_depth"):
                d = int(getattr(ctrl, "max_depth", 1))
                return max(1, d)
        except Exception:
            pass
        try:
            ctx = getattr(ctrl, "context", None) if ctrl is not None else None
            if ctx is not None and hasattr(ctx, "metadata"):
                md = getattr(ctx, "metadata", {})
                if md.get("topic_depth") is not None:
                    d = int(md.get("topic_depth"))
                    return max(1, d)
        except Exception:
            pass
        return 1

    def _maybe_expand_depth(self, *, new_level: int) -> None:
        """If new_level exceeds current depth, optionally prompt user to expand.

        - Shows a modal with a "don't ask again" checkbox. If user confirms and checks the box,
          future deeper inserts will auto-expand without prompting for this session.
        - Expands depth before performing the structural edit to avoid flicker.
        """
        ctrl = self._get_controller()
        if ctrl is None:
            return
        current_depth = self._get_current_depth()
        # Prompt when creating at the boundary or deeper so that immediate contents remain visible
        if new_level < current_depth:
            return

        # Ensure at least one level beyond the new section level so its immediate contents are visible
        target_depth = max(current_depth, int(new_level) + 1)

        # Auto-expand if user previously opted in
        if self._suppress_depth_prompt and self._auto_expand_on_deeper_insert:
            try:
                if hasattr(ctrl, "handle_depth_change"):
                    ctrl.handle_depth_change(target_depth)  # type: ignore[attr-defined]
            except Exception:
                pass
            return

        # Show modal prompt
        try:
            from orlando_toolkit.ui.dialogs.expand_depth_prompt import ExpandDepthPrompt
            # Find a Tk parent widget: prefer tree's internal widget if available
            parent = None
            try:
                # StructureTreeWidget is a ttk.Frame, safe parent
                parent = getattr(self, "_tree", None)
            except Exception:
                parent = None
            prompt = ExpandDepthPrompt(parent, new_level=int(new_level), current_depth=int(current_depth), target_depth=int(target_depth))
            expand, dont_ask, cancelled = prompt.show()
        except Exception:
            expand, dont_ask, cancelled = (False, False, False)

        # Cancelled by user: abort operation
        if 'cancelled' in locals() and cancelled:
            return

        # Apply expansion if chosen
        if expand:
            # Preferred: use UI depth setter so normal depth-change flow (busy/async) runs
            if callable(getattr(self, "_set_depth", None)):
                try:
                    self._set_depth(int(target_depth))  # type: ignore[misc]
                except Exception:
                    pass
            else:
                # Fallback: controller path
                try:
                    if hasattr(ctrl, "handle_depth_change"):
                        ctrl.handle_depth_change(int(target_depth))  # type: ignore[attr-defined]
                except Exception:
                    pass
            if dont_ask:
                self._suppress_depth_prompt = True
                self._auto_expand_on_deeper_insert = True
            # UI will refresh via depth setter/flow; avoid extra refresh here

    # ----------------------------- Topic actions -----------------------------
    def style_action(self, style: str) -> None:
        if not isinstance(style, str) or not style:
            return
        try:
            if callable(self._select_style):
                self._select_style(style)
        except Exception:
            pass

    def rename(self, refs: List[str]) -> None:
        if len(refs) != 1:
            return
        ctrl = self._get_controller()
        if ctrl is None:
            return
        # Prefill with current title
        try:
            current_title = ""
            try:
                if hasattr(ctrl, "get_title_for_ref"):
                    current_title = ctrl.get_title_for_ref(refs[0])  # type: ignore[attr-defined]
            except Exception:
                current_title = ""
            try:
                from orlando_toolkit.ui.dialogs.rename_dialog import RenameDialog
                new_title = RenameDialog.ask_string(None, "Rename topic", "New title:", initialvalue=current_title or "")
            except Exception:
                from tkinter import simpledialog
                new_title = simpledialog.askstring("Rename topic", "New title:")
            if not new_title:
                return
            res = ctrl.handle_rename(refs[0], new_title)  # type: ignore[attr-defined]
            if getattr(res, "success", False):
                self._refresh()
        except Exception:
            pass

    def delete(self, refs: List[str]) -> None:
        if not refs:
            return
        ctrl = self._get_controller()
        if ctrl is None:
            return
        try:
            res = ctrl.handle_delete(refs)  # type: ignore[attr-defined]
            if not getattr(res, "success", False):
                return
            try:
                ctrl.select_items([])  # type: ignore[attr-defined]
            except Exception:
                pass
            self._refresh()
        except Exception:
            pass

    def merge(self, refs: List[str]) -> None:
        if len(refs) < 2:
            return
        ctrl = self._get_controller()
        if ctrl is None:
            return
        try:
            try:
                if hasattr(self._tree, "are_refs_successive_topics") and not self._tree.are_refs_successive_topics(refs):  # type: ignore[attr-defined]
                    return
            except Exception:
                pass
            res = ctrl.handle_merge(refs)  # type: ignore[attr-defined]
            if getattr(res, "success", False):
                self._refresh()
        except Exception:
            pass

    # ---------------------------- Section actions ----------------------------
    def merge_section(self, index_path: List[int]) -> None:
        ctrl = self._get_controller()
        if ctrl is None:
            return
        try:
            if not isinstance(index_path, list) or not index_path:
                return
            res = ctrl.handle_merge_section(index_path)  # type: ignore[attr-defined]
            if getattr(res, "success", False):
                self._refresh()
        except Exception:
            pass

    def add_section_below(self, index_path: List[int]) -> None:
        ctrl = self._get_controller()
        if ctrl is None:
            return
        try:
            if not isinstance(index_path, list) or not index_path:
                return
            # Depth prompt: inserting a sibling below stays at the same level as the reference
            try:
                new_level = max(1, int(len(index_path)))
            except Exception:
                new_level = self._get_current_depth()
            self._maybe_expand_depth(new_level=new_level)
            try:
                from orlando_toolkit.ui.dialogs.rename_dialog import RenameDialog
                title = RenameDialog.ask_string(None, "Add section", "Section title:", initialvalue="")
            except Exception:
                from tkinter import simpledialog
                title = simpledialog.askstring("Add section", "Section title:")
            if not title:
                return
            res = ctrl.handle_add_section_after(index_path, title)  # type: ignore[attr-defined]
            if getattr(res, "success", False):
                self._refresh()
        except Exception:
            pass

    def add_section_inside(self, index_path: List[int]) -> None:
        ctrl = self._get_controller()
        if ctrl is None:
            return
        try:
            if not isinstance(index_path, list) or not index_path:
                return
            # Depth prompt: inserting as first child increases level by 1
            try:
                new_level = max(1, int(len(index_path) + 1))
            except Exception:
                new_level = self._get_current_depth() + 1
            self._maybe_expand_depth(new_level=new_level)
            try:
                from orlando_toolkit.ui.dialogs.rename_dialog import RenameDialog
                title = RenameDialog.ask_string(None, "Add section", "Section title:", initialvalue="")
            except Exception:
                from tkinter import simpledialog
                title = simpledialog.askstring("Add section", "Section title:")
            if not title:
                return
            res = ctrl.handle_add_section_inside(index_path, title)  # type: ignore[attr-defined]
            if getattr(res, "success", False):
                self._refresh()
        except Exception:
            pass

    def rename_section(self, index_path: List[int]) -> None:
        ctrl = self._get_controller()
        if ctrl is None:
            return
        try:
            if not isinstance(index_path, list) or not index_path:
                return
            current_title = ""
            try:
                current_title = ctrl.get_title_for_section(index_path)  # type: ignore[attr-defined]
            except Exception:
                current_title = ""
            try:
                from orlando_toolkit.ui.dialogs.rename_dialog import RenameDialog
                new_title = RenameDialog.ask_string(None, "Rename section", "New title:", initialvalue=current_title or "")
            except Exception:
                from tkinter import simpledialog
                new_title = simpledialog.askstring("Rename section", "New title:", initialvalue=current_title or "")
            if not new_title:
                return
            res = ctrl.handle_rename_section(index_path, new_title)  # type: ignore[attr-defined]
            if getattr(res, "success", False):
                self._refresh()
        except Exception:
            pass

    def delete_section(self, index_path: List[int]) -> None:
        ctrl = self._get_controller()
        if ctrl is None:
            return
        try:
            if not isinstance(index_path, list) or not index_path:
                return
            res = ctrl.handle_delete_section(index_path)  # type: ignore[attr-defined]
            if getattr(res, "success", False):
                self._refresh()
        except Exception:
            pass

    # ------------------------------ Send-to actions ------------------------------
    def send_topics_to(self, refs: List[str], target_index_path: Optional[List[int]]) -> None:
        ctrl = self._get_controller()
        if ctrl is None:
            return
        
        # UNIFIED: Use same capture/restore pattern for consistency
        selected_elements = []
        try:
            if hasattr(self._tree, 'capture_current_selection'):
                selected_elements = self._tree.capture_current_selection()
        except Exception:
            pass
        
        try:
            res = ctrl.handle_send_topics_to(target_index_path, refs)  # type: ignore[attr-defined]
            if not getattr(res, "success", False):
                return
            self._refresh()
            
            # UNIFIED: Restore selection using unified system
            try:
                if selected_elements:
                    self._tree.restore_captured_selection(selected_elements)
            except Exception:
                pass
        except Exception:
            pass

    def send_section_to(self, source_index_path: List[int], target_index_path: Optional[List[int]]) -> None:
        ctrl = self._get_controller()
        if ctrl is None:
            return
        
        # UNIFIED: Capture ALL selected elements before operation
        selected_elements = []
        try:
            if hasattr(self._tree, 'capture_current_selection'):
                selected_elements = self._tree.capture_current_selection()
        except Exception:
            pass
        
        try:
            if not isinstance(source_index_path, list) or not source_index_path:
                return
            res = ctrl.handle_send_section_to(target_index_path, source_index_path)  # type: ignore[attr-defined]
            if getattr(res, "success", False):
                self._refresh()
                
                # UNIFIED: Restore ALL selected elements after operation
                try:
                    if selected_elements and hasattr(self._tree, 'restore_captured_selection'):
                        self._tree.restore_captured_selection(selected_elements)
                except Exception:
                    pass  # Robust fallback - operation succeeded, selection lost is acceptable
        except Exception:
            pass

    def send_sections_to(self, source_index_paths: List[List[int]], target_index_path: Optional[List[int]]) -> None:
        ctrl = self._get_controller()
        if ctrl is None:
            return
        
        # UNIFIED: Capture ALL selected elements before operation
        selected_elements = []
        try:
            if hasattr(self._tree, 'capture_current_selection'):
                selected_elements = self._tree.capture_current_selection()
        except Exception:
            pass
        
        try:
            if not isinstance(source_index_paths, list) or not source_index_paths:
                return
            if hasattr(ctrl.editing_service, "move_sections_to_target"):
                res = ctrl._recorded_edit(lambda: ctrl.editing_service.move_sections_to_target(ctrl.context, source_index_paths, target_index_path))  # type: ignore[attr-defined]
            else:
                res = None
                for ip in source_index_paths:
                    r = ctrl._recorded_edit(lambda p=list(ip): ctrl.editing_service.move_section_to_target(ctrl.context, p, target_index_path))  # type: ignore[attr-defined]
                    res = r
            if res and not getattr(res, "success", False):
                return
            self._refresh()
            
            # UNIFIED: Restore ALL selected elements after operation
            try:
                if selected_elements and hasattr(self._tree, 'restore_captured_selection'):
                    self._tree.restore_captured_selection(selected_elements)
            except Exception:
                pass  # Robust fallback - operation succeeded, selection lost is acceptable
        except Exception:
            pass

    def send_mixed_selection_to(
        self, 
        topic_refs: List[str], 
        section_paths: List[List[int]], 
        target_index_path: Optional[List[int]]
    ) -> None:
        """Unified handler for mixed topic+section selections - GREATLY SIMPLIFIED.
        
        Now uses single capture/restore for ALL elements with no topic/section distinction.
        """
        ctrl = self._get_controller()
        if ctrl is None:
            return
        
        # UNIFIED: Single capture for ALL elements (no topic/section distinction needed)
        selected_elements = []
        try:
            if hasattr(self._tree, 'capture_current_selection'):
                selected_elements = self._tree.capture_current_selection()
        except Exception:
            pass
        
        try:
            res = ctrl.handle_send_mixed_selection_to(target_index_path, topic_refs, section_paths)
            if getattr(res, "success", False):
                self._refresh()
                
                # UNIFIED: Single restore for ALL elements
                try:
                    if selected_elements and hasattr(self._tree, 'restore_captured_selection'):
                        self._tree.restore_captured_selection(selected_elements)
                except Exception:
                    pass
        except Exception:
            pass


