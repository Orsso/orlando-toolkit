from __future__ import annotations

from typing import Callable, Dict, List, Optional


class ContextMenuCoordinator:
    """Build and show the context menu for StructureTab.

    Parameters
    ----------
    tree : object
        Tree widget with helpers: get_selected_items, get_item_context_at, are_refs_successive_topics,
        get_index_path_for_item_id, get_selected_sections_index_paths.
    menu_handler : object
        ContextMenuHandler-like with show_context_menu(event, refs, context).
    controller_getter : Callable[[], object]
        Zero-arg callable returning current controller (or None).
    """

    def __init__(
        self,
        *,
        tree: object,
        menu_handler: object,
        controller_getter: Callable[[], object],
        on_action: Callable[[str, object], None],
    ) -> None:
        self._tree = tree
        self._menu = menu_handler
        self._get_controller = controller_getter
        self._on_action = on_action

    def show(self, event: object, refs: List[str]) -> None:
        try:
            if refs:
                current_refs = refs
            else:
                # Get selected XML nodes and extract hrefs
                selected_nodes = self._tree.get_selected_xml_nodes()
                current_refs = []
                for node in selected_nodes:
                    if hasattr(node, 'get') and hasattr(node, 'tag') and node.tag == 'topicref':
                        href = node.get('href')
                        if href:
                            current_refs.append(href)
        except Exception:
            current_refs = list(refs or [])

        # Info under cursor
        try:
            info = self._tree.get_item_context_at(event)
        except Exception:
            info = {"item_id": "", "ref": None, "is_section": False, "style": None}

        ctx: Dict[str, object] = {}

        # Topic vs section flags
        is_single = len(current_refs) == 1
        is_section = bool(info.get("is_section")) if isinstance(info, dict) else False
        style = info.get("style") if isinstance(info, dict) else None
        if is_single and not is_section:
            ctx["is_topic"] = True
            ctx["style"] = style
        else:
            ctx["is_topic"] = False

        # Merge successive topics flag
        try:
            ctx["force_can_merge"] = bool(self._tree.are_refs_successive_topics(current_refs))
        except Exception:
            pass

        # Section-specialized commands
        if is_section:
            item_id = info.get("item_id") if isinstance(info, dict) else ""
            index_path = []
            if isinstance(item_id, str) and item_id:
                try:
                    index_path = self._tree.get_index_path_for_item_id(item_id)
                except Exception:
                    index_path = []
            ctx["on_merge_command"] = (lambda p=index_path: self._emit("merge_section", p))
            ctx["on_rename_command"] = (lambda p=index_path: self._emit("rename_section", p))
            ctx["on_delete_command"] = (lambda p=index_path: self._emit("delete_section", p))
            ctx["force_can_rename"] = True
            ctx["force_can_merge"] = True
            ctx["force_can_delete"] = True
            # Add Section logic for sections:
            # - if section is open: add as first child (one level deeper)
            # - if closed: add as sibling below (same level)
            try:
                if index_path and isinstance(item_id, str) and item_id:
                    if hasattr(self._tree, "is_item_open") and self._tree.is_item_open(item_id):  # type: ignore[attr-defined]
                        ctx["on_add_section_command"] = (lambda p=index_path: self._emit("add_section_inside", p))
                    else:
                        ctx["on_add_section_command"] = (lambda p=index_path: self._emit("add_section_below", p))
                    ctx["force_can_add_section"] = True
            except Exception:
                pass
        else:
            # Topic: Add Section directly below the clicked topic at same level
            try:
                item_id = info.get("item_id") if isinstance(info, dict) else ""
                if isinstance(item_id, str) and item_id:
                    index_path = self._tree.get_index_path_for_item_id(item_id)
                else:
                    index_path = []
                if index_path:
                    ctx["on_add_section_command"] = (lambda p=index_path: self._emit("add_section_below", p))
                    ctx["force_can_add_section"] = True
            except Exception:
                pass

        # Send-to entries
        try:
            ctrl = self._get_controller()
            destinations = []
            if ctrl is not None and hasattr(ctrl, "list_send_to_destinations"):
                destinations = ctrl.list_send_to_destinations()
            send_entries = self._build_send_to_entries(current_refs, info, destinations)
            if send_entries:
                ctx["send_to_entries"] = send_entries
        except Exception:
            pass

        # Hook for style primary action (only if source plugin has style_toggle capability)
        if is_single and not is_section and isinstance(style, str) and style:
            # Check if document source plugin has style_toggle capability
            try:
                from orlando_toolkit.core.context import get_app_context
                app_context = get_app_context()
                if app_context and app_context.document_source_plugin_has_capability('style_toggle'):
                    ctx["on_style"] = (lambda s=style: self._emit("style_action", s))
            except Exception:
                pass

        try:
            self._menu.show_context_menu(event, current_refs, context=ctx)
        except Exception:
            pass

    # ------------------------------------------------------------- Internals
    def _emit(self, action: str, payload: object) -> None:
        try:
            self._on_action(action, payload)
        except Exception:
            pass

    def _build_send_to_entries(self, current_refs: List[str], info: Dict[str, object], destinations: List[dict]) -> List[tuple[str, Callable[[], None]]]:
        """Build unified Send To entries for any selection type.
        
        This method handles mixed selections (topics + sections) by always using
        the unified handler, regardless of what was right-clicked.
        """
        entries: List[tuple[str, Callable[[], None]]] = []
        try:
            # Get both topics and sections from current selection
            selected_topics = list(current_refs or [])
            selected_sections = []
            try:
                selected_sections = self._tree.get_selected_sections_index_paths()
            except Exception:
                selected_sections = []
            
            # If no explicit selection, use clicked item
            if not selected_topics and not selected_sections:
                is_section = bool(info.get("is_section"))
                item_id = info.get("item_id") or ""
                if is_section and item_id:
                    try:
                        selected_sections = [self._tree.get_index_path_for_item_id(item_id)]
                    except Exception:
                        pass
                # Note: topics already captured in current_refs parameter
            
            # Build entries using unified handler - works for any combination
            def add_entry(label, tpath):
                entries.append((
                    str(label), 
                    lambda topics=selected_topics, sections=selected_sections, t=tpath: 
                        self._emit("send_mixed_selection_to", (topics, sections, t))
                ))
            
            for d in destinations:
                try:
                    add_entry(d.get("label"), d.get("index_path"))
                except Exception:
                    continue
                    
        except Exception:
            return []
        return entries


