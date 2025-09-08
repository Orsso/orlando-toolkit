from typing import List, Dict, Literal, Optional, Callable, Any, Set
import xml.etree.ElementTree as ET

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.services.structure_editing_service import (
    StructureEditingService,
    OperationResult,
)
from orlando_toolkit.core.services.undo_service import UndoService
from orlando_toolkit.core.services.preview_service import PreviewService, PreviewResult
try:
    from orlando_toolkit.core.context import get_app_context
except Exception:
    def get_app_context():
        return None


class StructureController:
    """Controller for coordinating structure editing UI actions with services.

    This controller maintains transient UI-related state and delegates operations
    to the appropriate services. It contains no UI toolkit code and does not
    perform I/O or logging.

    Parameters
    ----------
    context : DitaContext
        The active DITA context the UI is working with.
    editing_service : StructureEditingService
        Service that performs structural editing operations.
    undo_service : UndoService
        Service that manages undo/redo snapshots and restoration.
    preview_service : PreviewService
        Service that compiles previews and renders HTML previews.

    Notes
    -----
    - This controller is conservative and non-raising for routine validation
      failures; most methods return booleans or result objects indicating success.
    - No Tkinter or UI framework code should appear in this module.
    """

    def __init__(
        self,
        context: DitaContext,
        editing_service: StructureEditingService,
        undo_service: UndoService,
        preview_service: PreviewService,
    ) -> None:
        # Dependencies
        self.context: DitaContext = context
        self.editing_service: StructureEditingService = editing_service
        self.undo_service: UndoService = undo_service
        self.preview_service: PreviewService = preview_service

        # Transient UI-related state
        self.max_depth: int = 999
        self.search_term: str = ""
        self.search_results: List[ET.Element] = []  # XML nodes matching search
        self.search_index: int = -1  # current index into search_results for navigation
        self.selected_items: List[str] = []
        self.filter_exclusions: Dict[str, bool] = {}  # group_key -> excluded
        self.style_visibility: Dict[str, bool] = {}  # style -> visible (show marker)

    # ---------------------------------------------------------------------------------
    # Internal helpers
    # ---------------------------------------------------------------------------------

    def _recorded_edit(self, mutate: Callable[[], Any]) -> Any:
        """Execute a mutating operation with pre/post undo snapshots.

        - Pushes a snapshot before mutation; failure is non-fatal.
        - Executes the provided callable.
        - On success (OperationResult.success True or boolean True), pushes a post snapshot.
        - Returns the original result.

        This preserves business logic in services and keeps snapshot policy DRY.
        """
        pre_snapshot_failed = False
        try:
            self.undo_service.push_snapshot(self.context)
        except Exception:
            pre_snapshot_failed = True

        result = None
        try:
            result = mutate()
        except Exception:
            return result

        # Determine success flag conservatively
        success = False
        if isinstance(result, bool):
            success = result
        else:
            success = bool(getattr(result, "success", False))

        if success:
            try:
                self.undo_service.push_snapshot(self.context)
            except Exception:
                # Non-fatal – the operation already succeeded; redo may be limited
                pass

        # Optionally augment message if pre-snapshot failed
        if pre_snapshot_failed and hasattr(result, "success") and getattr(result, "success"):
            msg = getattr(result, "message", "") or ""
            warning = " Warning: Undo snapshot failed - undo may not be available for this operation."
            try:
                result.message = f"{msg}{warning}".strip()
            except Exception:
                pass
        return result

    def handle_depth_change(self, new_depth: int) -> bool:
        """Handle a change in the maximum depth to display.

        Clamps the value to be at least 1, stores it, and returns True if
        the value actually changed.

        Parameters
        ----------
        new_depth : int
            The requested new maximum depth.

        Returns
        -------
        bool
            True if the stored depth changed, False otherwise.
        """
        # Guard: new_depth must be an int
        if not isinstance(new_depth, int):
            return False

        # Clamp to minimum of 1
        clamped = max(1, new_depth)

        # If no effective change, preserve previous behavior
        if clamped == self.max_depth:
            return False

        # Only proceed when the clamped value differs from current max_depth.
        # Push an undo snapshot (non-fatal on failure).
        pre_failed = False
        try:
            self.undo_service.push_snapshot(self.context)
        except Exception:
            pre_failed = True
            if hasattr(self, "logger"):
                self.logger.warning("Failed to push undo snapshot for depth change", exc_info=True)

        # Build a per-level style exclusion map using the original structure for levels.
        # This keeps exclusions precise and stable across depth changes.
        style_exclusions_map = None
        try:
            if hasattr(self, "filter_exclusions") and isinstance(self.filter_exclusions, dict):
                # Derive levels per style from original structure
                style_exclusions_map = self.build_style_exclusion_map_from_flags(self.filter_exclusions)
                if not any(style_exclusions_map.values()):
                    style_exclusions_map = None
        except Exception:
            style_exclusions_map = None

        # Delegate to the structure editing service to apply the depth limit/merge.
        try:
            result = self.editing_service.apply_depth_limit(self.context, clamped, style_exclusions_map)
        except Exception:
            return False

        # Require an explicit success signal
        if not getattr(result, "success", False):
            return False

        # On success, update controller state and report True
        self.max_depth = clamped
        # Persist chosen depth so packaging/export uses the same value
        try:
            if hasattr(self, "context") and hasattr(self.context, "metadata"):
                self.context.metadata["topic_depth"] = clamped
        except Exception:
            # Best-effort only; keep UI responsive even if metadata is not writable
            pass
        # Push post-mutation snapshot to enable redo
        try:
            self.undo_service.push_snapshot(self.context)
        except Exception:
            # Non-fatal: operation already applied
            pass

        return True

    def get_topic_path(self, topic_ref: str) -> List[tuple[str, str]]:
        """Get the hierarchical path for a topic reference.
        
        Returns a list of (title, href) tuples representing the path from
        root to the given topic with real section titles. Used for breadcrumb navigation.
        
        Parameters
        ----------
        topic_ref : str
            The topic reference (href) to get the path for.
            
        Returns
        -------
        List[tuple[str, str]]
            List of (title, href) tuples representing the hierarchical path.
            Empty list if topic_ref is not found.
        """
        if not topic_ref or not hasattr(self, "context"):
            return []
            
        try:
            root = getattr(self.context, "ditamap_root", None)
            if root is None:
                return []
                
            # Find the topicref element with this href
            target_ref = root.find(f".//topicref[@href='{topic_ref}']")
            if target_ref is None:
                return []
                
            # Build path by walking up the tree
            path = []
            current = target_ref
            
            while current is not None:
                # Only include topicref and topichead elements
                if current.tag in ("topicref", "topichead"):
                    title = self._extract_node_title(current)
                    
                    # For breadcrumb navigation, use a simple unique identifier
                    # - topicref: use href
                    # - topichead: use memory address as unique ID
                    if current.tag == "topicref":
                        nav_id = current.get("href", "")
                    else:
                        # Use id() as unique identifier for sections
                        nav_id = f"section_{id(current)}"
                    
                    path.insert(0, (title, nav_id))
                
                # Move up to parent
                current = current.getparent()
                # Stop if we reach the root map element
                if current is not None and current.tag == "map":
                    break
                    
            return path
            
        except Exception:
            return []

    def _extract_node_title(self, node) -> str:
        """Extract title from a topicref/topichead node with section numbers."""
        try:
            # Get base title
            base_title = ""
            
            # Try topicmeta/navtitle first
            try:
                navtitle_el = node.find("topicmeta/navtitle")
                if navtitle_el is not None and navtitle_el.text:
                    base_title = navtitle_el.text.strip()
            except Exception:
                pass
                
            # Try title element
            if not base_title:
                try:
                    title_el = node.find("title")
                    if title_el is not None and title_el.text:
                        base_title = title_el.text.strip()
                except Exception:
                    pass
                    
            # Try navtitle attribute
            if not base_title:
                try:
                    navtitle_attr = node.get("navtitle", "")
                    if navtitle_attr.strip():
                        base_title = navtitle_attr.strip()
                except Exception:
                    pass
                    
            # Fallback to href filename for topicref
            if not base_title:
                if node.tag == "topicref":
                    href = node.get("href", "")
                    if href:
                        base_title = href.split("/")[-1].replace(".dita", "").replace("_", " ").title()
                else:
                    base_title = "Section"
            
            # Add section number if available
            section_number = self._get_section_number_for_node(node)
            if section_number and section_number != "0":
                return f"{section_number}. {base_title}"
            
            return base_title
            
        except Exception:
            return "Section"

    def _get_section_number_for_node(self, node) -> str:
        """Get section number for a node using utils.calculate_section_numbers."""
        try:
            root = getattr(self.context, "ditamap_root", None)
            if root is None:
                return ""
                
            # Calculate section numbers for the entire map
            from orlando_toolkit.core.utils import calculate_section_numbers
            section_map = calculate_section_numbers(root)
            
            return section_map.get(node, "")
            
        except Exception:
            return ""

    def handle_move_operation(
        self, direction: Literal["up", "down", "promote", "demote"]
    ) -> OperationResult:
        """Handle a move operation on the first selected item.

        If there is no selection, an unsuccessful OperationResult is returned.
        Otherwise, this pushes an undo snapshot, delegates to the editing service
        for the move, and relies on UndoService snapshot semantics to manage
        redo clearing.

        Parameters
        ----------
        direction : Literal["up", "down", "promote", "demote"]
            The move direction to apply to the first selected item.

        Returns
        -------
        OperationResult
            The result of the move operation from the editing service. If the
            undo snapshot fails to be created, the operation will still proceed
            but the result will include a warning about the undo capability loss.

        Notes
        -----
        - Multi-select handling is intentionally left for future extension.
        - Routine validation failures should not raise; instead an unsuccessful
          OperationResult is returned.
        - Snapshot failures are caught and reported in the result message to
          inform users of potential undo capability loss.
        """
        first_ref: Optional[str] = self.selected_items[0] if self.selected_items else None
        if not first_ref:
            # Construct a conservative unsuccessful result without raising.
            return OperationResult(success=False, message="No selection")

        try:
            return self._recorded_edit(
                lambda: self.editing_service.move_topic(self.context, first_ref, direction)
            )
        except Exception:
            # Non-raising for routine errors: return an unsuccessful result.
            return OperationResult(success=False, message="Move operation failed")


    def handle_rename(self, topic_ref: str, new_title: str) -> OperationResult:
        """Rename a topic via the editing service wrapped with undo snapshots."""
        if not isinstance(topic_ref, str) or not topic_ref:
            return OperationResult(success=False, message="No topic selected to rename")
        if not isinstance(new_title, str) or not new_title.strip():
            return OperationResult(success=False, message="Empty title is not allowed")
        try:
            return self._recorded_edit(
                lambda: self.editing_service.rename_topic(self.context, topic_ref, new_title)
            )
        except Exception:
            return OperationResult(success=False, message="Rename operation failed")

    def handle_delete(self, topic_refs: List[str]) -> OperationResult:
        """Delete topics via the editing service wrapped with undo snapshots."""
        refs = [r for r in (topic_refs or []) if isinstance(r, str) and r]
        if not refs:
            return OperationResult(success=False, message="No topics selected to delete")
        try:
            return self._recorded_edit(
                lambda: self.editing_service.delete_topics(self.context, refs)
            )
        except Exception:
            return OperationResult(success=False, message="Delete operation failed")

    def handle_merge(self, topic_refs: List[str]) -> OperationResult:
        """Merge topics via the editing service with undo snapshots.

        Policy: first ref is target, remaining are sources. Requires >= 2 refs.
        Falls back to a two-arg merge signature if service expects it.
        """
        refs = [r for r in (topic_refs or []) if isinstance(r, str) and r]
        if len(refs) < 2:
            return OperationResult(success=False, message="Select at least two topics to merge")
        target_id = refs[0]
        source_ids = refs[1:]

        def _call_merge():
            try:
                # Preferred signature: (context, source_ids, target_id)
                return self.editing_service.merge_topics(self.context, source_ids, target_id)
            except TypeError:
                # Fallback legacy signature: (context, refs)
                return self.editing_service.merge_topics(self.context, refs)  # type: ignore[arg-type]

        try:
            return self._recorded_edit(_call_merge)
        except Exception:
            return OperationResult(success=False, message="Merge operation failed")

    # --- Section-specific operations ---

    def handle_merge_section(self, index_path: List[int]) -> OperationResult:
        """Convert a section at index_path into a topic and move its subtree under it.

        Delegates to editing_service.convert_section_to_topic with undo snapshots.
        """
        if not isinstance(index_path, list) or not index_path:
            return OperationResult(success=False, message="No section selected to merge")
        try:
            return self._recorded_edit(
                lambda: self.editing_service.convert_section_to_topic(self.context, index_path)
            )
        except Exception:
            return OperationResult(success=False, message="Section merge failed")

    def handle_add_section_after(self, index_path: List[int], title: str) -> OperationResult:
        """Insert a new section below the structural node at index_path.

        Delegates to editing_service.insert_section_after_index_path with undo snapshots.
        """
        if not isinstance(index_path, list) or not index_path:
            return OperationResult(success=False, message="No reference selected to insert after")
        if not isinstance(title, str) or not title.strip():
            return OperationResult(success=False, message="Empty title is not allowed")
        try:
            return self._recorded_edit(
                lambda: self.editing_service.insert_section_after_index_path(self.context, index_path, title)
            )
        except Exception:
            return OperationResult(success=False, message="Failed to add section")

    def handle_add_section_inside(self, index_path: List[int], title: str) -> OperationResult:
        """Insert a new section as first child of the section at index_path (undo-wrapped)."""
        if not isinstance(index_path, list) or not index_path:
            return OperationResult(success=False, message="No section selected to insert into")
        if not isinstance(title, str) or not title.strip():
            return OperationResult(success=False, message="Empty title is not allowed")
        try:
            return self._recorded_edit(
                lambda: self.editing_service.insert_section_as_first_child(self.context, index_path, title)
            )
        except Exception:
            return OperationResult(success=False, message="Failed to add section inside")

    def handle_rename_section(self, index_path: List[int], new_title: str) -> OperationResult:
        """Rename a section (topichead) title at index_path.

        Delegates to editing_service.rename_section.
        """
        if not isinstance(index_path, list) or not index_path:
            return OperationResult(success=False, message="No section selected to rename")
        if not isinstance(new_title, str) or not new_title.strip():
            return OperationResult(success=False, message="Empty title is not allowed")
        try:
            return self._recorded_edit(
                lambda: self.editing_service.rename_section(self.context, index_path, new_title)
            )
        except Exception:
            return OperationResult(success=False, message="Section rename failed")

    def handle_delete_section(self, index_path: List[int]) -> OperationResult:
        """Delete a section (topichead) located by index_path.

        Removes the topichead and its subtree from the map. Does not delete topics
        that are still referenced elsewhere; after removal, unreferenced topics are purged.
        """
        if not isinstance(index_path, list) or not index_path:
            return OperationResult(success=False, message="No section selected to delete")
        try:
            return self._recorded_edit(
                lambda: self.editing_service.delete_section(self.context, index_path)
            )
        except Exception:
            return OperationResult(success=False, message="Section delete failed")

    # --- Title getters for pre-filling rename dialogs ---

    def get_title_for_ref(self, topic_ref: str) -> str:
        """Return current title for a topicref href, best-effort.

        Prefers the topic's <title>; falls back to navtitle.
        """
        try:
            if not isinstance(topic_ref, str) or not topic_ref:
                return ""
            root = getattr(self.context, "ditamap_root", None)
            if root is None:
                return ""
            # Extract filename and look up topic element
            fname = topic_ref.split("/")[-1]
            topic_el = getattr(self.context, "topics", {}).get(fname)
            if topic_el is not None:
                t = topic_el.find("title")
                if t is not None and t.text:
                    return " ".join(t.text.split())
            # Fallback to navtitle on the topicref element
            tref = root.find(f".//topicref[@href='{topic_ref}']")
            if tref is not None:
                nt = tref.find("topicmeta/navtitle")
                if nt is not None and nt.text:
                    return " ".join(nt.text.split())
        except Exception:
            pass
        return ""

    def get_title_for_section(self, index_path: List[int]) -> str:
        """Return current navtitle for a section (topichead) at index_path, best-effort."""
        try:
            node = self._locate_node_by_index_path(index_path)
            if node is None:
                return ""
            nav = node.find("topicmeta/navtitle")
            if nav is not None and nav.text:
                return " ".join(nav.text.split())
        except Exception:
            pass
        return ""

    def handle_apply_filters(self, style_excl_map: Optional[Dict[int, Set[str]]] = None) -> OperationResult:
        """Apply filters via StructureEditingService with undo snapshots."""
        try:
            return self._recorded_edit(
                lambda: self.editing_service.apply_depth_limit(self.context, self.max_depth, style_excl_map)
            )
        except Exception:
            return OperationResult(success=False, message="Failed to apply filters")

    # ---------------------------------------------------------------------
    # Heading analysis wrappers (UI queries)
    # ---------------------------------------------------------------------

    def get_heading_counts(self) -> Dict[str, int]:
        """Return counts per provider-defined group key (plugin-supplied)."""
        try:
            app_ctx = get_app_context()
            provider = app_ctx.get_filter_provider_for_source() if app_ctx else None
            return provider.get_counts(self.context) if provider else {}
        except Exception:
            return {}

    def get_heading_occurrences(self) -> Dict[str, List[Dict[str, str]]]:
        try:
            app_ctx = get_app_context()
            provider = app_ctx.get_filter_provider_for_source() if app_ctx else None
            return provider.get_occurrences(self.context) if provider else {}
        except Exception:
            return {}

    def get_heading_occurrences_current(self) -> Dict[str, List[Dict[str, str]]]:
        try:
            app_ctx = get_app_context()
            provider = app_ctx.get_filter_provider_for_source() if app_ctx else None
            return provider.get_occurrences_current(self.context) if provider else {}
        except Exception:
            return {}

    def get_style_levels(self) -> Dict[str, Optional[int]]:
        try:
            app_ctx = get_app_context()
            provider = app_ctx.get_filter_provider_for_source() if app_ctx else None
            return provider.get_levels(self.context) if provider else {}
        except Exception:
            return {}

    def estimate_unmergable(self, style_excl_map: Dict[int, Set[str]]) -> int:
        try:
            app_ctx = get_app_context()
            provider = app_ctx.get_filter_provider_for_source() if app_ctx else None
            return int(provider.estimate_unmergable(self.context, style_excl_map)) if provider else 0
        except Exception:
            return 0

    def build_style_exclusion_map_from_flags(self, exclusions: Dict[str, bool]) -> Dict[int, Set[str]]:
        """Generic mapping from group_key->excluded flags to level->set map using provider levels."""
        levels_map = self.get_style_levels()
        style_excl_map: Dict[int, Set[str]] = {}
        try:
            for key, excluded in (exclusions or {}).items():
                if not excluded:
                    continue
                level_val = levels_map.get(key)
                level = int(level_val) if isinstance(level_val, int) else 1
                style_excl_map.setdefault(level, set()).add(key)
        except Exception:
            pass
        return style_excl_map

    def handle_search(self, term: str) -> List[ET.Element]:
        """Handle a search request and store transient search state.

        Attempts to compute conservative search results using the available
        context if possible. If underlying data is unavailable or access fails,
        returns an empty list while persisting state.

        Parameters
        ----------
        term : str
            The search term to apply.

        Returns
        -------
        List[ET.Element]
            A list of matched XML nodes. Empty list on failure or no match.

        Notes
        -----
        - Method should not raise for data access issues; returns [] in such cases.
        - Results are intentionally conservative given limited knowledge of the context.
        """
        self.search_term = term or ""
        self.search_results = []
        self.search_index = -1

        if not self.search_term:
            return self.search_results

        # Prefer searching the structured ditamap when available so that we
        # return hrefs that the tree widget understands and can highlight.
        try:
            root = getattr(self.context, "ditamap_root", None)
        except Exception:
            root = None

        term_lower = self.search_term.lower()

        if root is not None:
            try:
                def iter_heading_children(node: object):
                    try:
                        if hasattr(node, "iterchildren"):
                            for child in node.iterchildren():
                                try:
                                    tag = str(getattr(child, "tag", "") or "")
                                except Exception:
                                    tag = ""
                                if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                                    yield child
                            return
                    except Exception:
                        pass
                    try:
                        if hasattr(node, "getchildren"):
                            for child in node.getchildren():  # type: ignore[attr-defined]
                                try:
                                    tag = str(getattr(child, "tag", "") or "")
                                except Exception:
                                    tag = ""
                                if tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}:
                                    yield child
                            return
                    except Exception:
                        pass
                    try:
                        if hasattr(node, "findall"):
                            for child in list(node.findall("./topicref")) + list(node.findall("./topichead")):
                                yield child
                    except Exception:
                        return

                def extract_title(node: object) -> str:
                    # Prefer topicmeta/navtitle, then <title>, else @navtitle
                    try:
                        if hasattr(node, "find"):
                            nav = node.find("topicmeta/navtitle")
                            if nav is not None:
                                txt = getattr(nav, "text", None)
                                if isinstance(txt, str) and txt.strip():
                                    return txt.strip()
                            tnode = node.find("title")
                            if tnode is not None:
                                ttxt = getattr(tnode, "text", None)
                                if isinstance(ttxt, str) and ttxt.strip():
                                    return ttxt.strip()
                    except Exception:
                        pass
                    try:
                        if hasattr(node, "get"):
                            alt = node.get("navtitle")
                            if isinstance(alt, str) and alt.strip():
                                return alt.strip()
                    except Exception:
                        pass
                    return ""

                def extract_href(node: object) -> str:
                    try:
                        if hasattr(node, "get"):
                            href = node.get("href")
                            if isinstance(href, str) and href.strip():
                                return href.strip()
                    except Exception:
                        pass
                    return ""

                matches: List[str] = []
                stack = [root]
                visited = 0
                max_nodes = 200000

                while stack and visited < max_nodes:
                    node = stack.pop()
                    visited += 1
                    try:
                        tag = str(getattr(node, "tag", "") or "")
                    except Exception:
                        tag = ""

                    is_heading = tag.endswith("topicref") or tag.endswith("topichead") or tag in {"topicref", "topichead"}
                    if is_heading:
                        title = extract_title(node)
                        href = extract_href(node)
                        # Match on title text, full href, file basename
                        basename = href.split("/")[-1] if href else ""
                        def _contains(s: str) -> bool:
                            return bool(s) and term_lower in s.lower()
                        if _contains(title) or _contains(href) or _contains(basename):
                            if href:
                                matches.append(node)

                    try:
                        # Push children in reverse order so the DFS visit preserves
                        # the original left-to-right visual order when popping.
                        children = []
                        for child in iter_heading_children(node):
                            children.append(child)
                        for child in reversed(children):
                            stack.append(child)
                    except Exception:
                        pass

                # Deduplicate while preserving order
                seen: Dict[int, bool] = {}
                uniq: List[ET.Element] = []
                for node in matches:
                    node_id = id(node)  # Use object identity for deduplication
                    if node_id not in seen:
                        seen[node_id] = True
                        uniq.append(node)
                self.search_results = uniq
                self.search_index = 0 if self.search_results else -1
                return self.search_results
            except Exception:
                # Fall through to attribute-based best-effort search
                pass

        # Best-effort fallback: probe common attributes and filter by substring
        try:
            candidates: List[str] = []
            possible_attrs = [
                "topics",
                "topic_refs",
                "all_topics",
                "all_topic_refs",
                "nodes",
                "items",
            ]
            for attr in possible_attrs:
                if hasattr(self.context, attr):
                    value = getattr(self.context, attr)
                    if isinstance(value, dict):
                        candidates.extend(list(value.keys()))
                    elif isinstance(value, list):
                        for entry in value:
                            if isinstance(entry, str):
                                candidates.append(entry)
                            else:
                                for id_attr in ["id", "ref", "topic_ref", "uid"]:
                                    if hasattr(entry, id_attr):
                                        ref_val = getattr(entry, id_attr)
                                        if isinstance(ref_val, str):
                                            candidates.append(ref_val)
                                            break

            # Deduplicate
            seen2: Dict[str, bool] = {}
            unique_candidates: List[str] = []
            for c in candidates:
                if c not in seen2:
                    seen2[c] = True
                    unique_candidates.append(c)

            # Fallback search now returns empty - XML-based search above should handle most cases
            self.search_results = []
            self.search_index = 0 if self.search_results else -1
        except Exception:
            self.search_results = []
            self.search_index = -1

        return self.search_results

    def handle_filter_toggle(self, style: str, enabled: bool) -> Dict[str, bool]:
        """Toggle a heading style filter.

        Updates the internal mapping of style exclusions. When enabled=False,
        the style is considered excluded (i.e., not shown).

        Parameters
        ----------
        style : str
            The heading style key (e.g., 'Heading1', 'Heading2').
        enabled : bool
            Whether the style should be enabled (shown). If False, it is excluded.

        Returns
        -------
        Dict[str, bool]
            The current mapping of style to excluded flag.
        """
        if not isinstance(style, str) or not style:
            # Do nothing if invalid style label; keep conservative behavior
            return self.filter_exclusions

        excluded = not enabled
        self.filter_exclusions[style] = excluded
        return self.filter_exclusions

    def handle_style_visibility_toggle(self, style: str, visible: bool) -> Dict[str, bool]:
        """Toggle visibility of a style marker.

        Updates the internal mapping of style visibility for tree markers.

        Parameters
        ----------
        style : str
            Style name (e.g., 'Heading1', 'Heading2').
        visible : bool
            True to show the marker, False to hide it.

        Returns
        -------
        Dict[str, bool]
            Current mapping style -> visible.
        """
        if not isinstance(style, str) or not style:
            return self.style_visibility
            
        # Enforce a maximum of 5 simultaneously visible styles
        if visible:
            active_count = sum(1 for v in self.style_visibility.values() if v)
            if active_count >= 5 and not self.style_visibility.get(style, False):
                # Ignore request if it would exceed the limit
                return self.style_visibility
        self.style_visibility[style] = bool(visible)
        return self.style_visibility
        
    def get_style_visibility(self) -> Dict[str, bool]:
        """Return the current visibility for all styles."""
        return dict(self.style_visibility)
        
    def get_style_colors(self) -> Dict[str, str]:
        """Generate and return the colors assigned to styles.

        Uses the same logic as `StyleLegend` to preserve consistency.
        """
        colors: Dict[str, str] = {}
        try:
            from orlando_toolkit.ui.common.style_colors import _color_manager, STYLE_COLORS
        except Exception:
            _color_manager = None  # type: ignore[assignment]
            STYLE_COLORS = ["#FF1744", "#00C853", "#FF9100", "#9C27B0", "#FF00A8"]

        visible_styles = [s for s, v in self.style_visibility.items() if v]
        try:
            if _color_manager is not None and visible_styles:
                assigned = _color_manager.assign_unique(visible_styles)
                colors.update(assigned)
                return colors
        except Exception:
            pass

        # Fallback deterministic mapping
        used = set()
        for s in visible_styles:
            idx = hash(s) % len(STYLE_COLORS)
            for _ in range(len(STYLE_COLORS)):
                if idx not in used:
                    used.add(idx)
                    colors[s] = STYLE_COLORS[idx]
                    break
                idx = (idx + 1) % len(STYLE_COLORS)
        return colors

    # --- Internal helper to locate nodes by index_path ---

    def _locate_node_by_index_path(self, index_path: List[int]):
        try:
            root = getattr(self.context, "ditamap_root", None)
            if root is None:
                return None
            node = root
            for idx in index_path:
                # Filter to structural children only to match tree view
                structural_children = [el for el in list(node) if getattr(el, "tag", None) in ("topicref", "topichead")]
                if idx < 0 or idx >= len(structural_children):
                    return None
                node = structural_children[idx]
            return node
        except Exception:
            return None

    def select_items(self, xml_nodes: List[ET.Element]) -> None:
        """Set the current selection using XML nodes.

        Extracts hrefs from topicref nodes and stores as unique references.

        Parameters
        ----------
        xml_nodes : List[ET.Element]
            List of XML nodes to select

        Returns
        -------
        None
        """
        if not isinstance(xml_nodes, list):
            self.selected_items = []
            return

        # Extract hrefs from XML nodes
        hrefs = []
        for node in xml_nodes:
            if hasattr(node, 'get') and hasattr(node, 'tag') and node.tag == 'topicref':
                href = node.get('href')
                if href:
                    hrefs.append(href)

        # Store unique hrefs in order of first appearance
        seen: Dict[str, bool] = {}
        unique_refs: List[str] = []
        for ref in hrefs:
            if ref and ref not in seen:
                seen[ref] = True
                unique_refs.append(ref)
        self.selected_items = unique_refs

    def get_selection(self) -> List[str]:
        """Get the current selection.

        Returns
        -------
        List[str]
            The list of selected item reference identifiers.
        """
        return list(self.selected_items)

    def can_undo(self) -> bool:
        """Check if an undo operation is available.

        Returns
        -------
        bool
            True if undo is available, False otherwise.
        """
        try:
            return self.undo_service.can_undo()
        except Exception:
            return False

    def can_redo(self) -> bool:
        """Check if a redo operation is available.

        Returns
        -------
        bool
            True if redo is available, False otherwise.
        """
        try:
            return self.undo_service.can_redo()
        except Exception:
            return False

    def undo(self) -> bool:
        """Perform an undo operation by restoring the previous snapshot into the context.

        Returns
        -------
        bool
            True if the undo succeeded, False otherwise.
        """
        try:
            return self.undo_service.undo(self.context)
        except Exception:
            return False

    def redo(self) -> bool:
        """Perform a redo operation by restoring the next snapshot into the context.

        Returns
        -------
        bool
            True if the redo succeeded, False otherwise.
        """
        try:
            return self.undo_service.redo(self.context)
        except Exception:
            return False


    def render_html_preview(self, topic_ref: str) -> PreviewResult:
        """Render an HTML preview for the provided or selected topic reference.

        If topic_ref is falsy, attempts to use the first selected item. Returns
        a conservative unsuccessful PreviewResult if neither is available.

        Parameters
        ----------
        topic_ref : str
            The topic reference identifier to render. If empty, uses selection.

        Returns
        -------
        PreviewResult
            The result from the preview service HTML rendering.
        """
        ref = topic_ref or (self.selected_items[0] if self.selected_items else "")
        if not isinstance(ref, str) or not ref:
            return PreviewResult(success=False, message="No topic reference provided")

        try:
            return self.preview_service.render_html_preview(self.context, ref)
        except Exception:
            return PreviewResult(success=False, message="HTML rendering failed")

    # XML-centric preview forwarding
    def compile_preview_for_node(self, node: ET.Element) -> PreviewResult:
        try:
            return self.preview_service.compile_node_preview(self.context, node)
        except Exception:
            return PreviewResult(success=False, message="Failed to compile XML preview")

    def render_html_preview_for_node(self, node: ET.Element) -> PreviewResult:
        try:
            return self.preview_service.render_html_preview_for_node(self.context, node)
        except Exception:
            return PreviewResult(success=False, message="Failed to render HTML preview")

    # ---------------------------------------------------------------------
    # Send-to operations and destination listing
    # ---------------------------------------------------------------------

    def handle_send_topics_to(
        self, target_index_path: Optional[List[int]], topic_refs: List[str]
    ) -> OperationResult:
        """Move given topic refs to the destination identified by index_path (or root).

        Topics are appended at destination end in the provided order.
        """
        refs = [r for r in (topic_refs or []) if isinstance(r, str) and r]
        if not refs:
            return OperationResult(success=False, message="No topics to move")
        try:
            return self._recorded_edit(
                lambda: self.editing_service.move_topics_to_target(self.context, refs, target_index_path)
            )
        except Exception:
            return OperationResult(success=False, message="Failed to move topics")

    def handle_send_section_to(
        self, target_index_path: Optional[List[int]], section_index_path: List[int]
    ) -> OperationResult:
        """Move a section (topichead) to another section or root (append at end)."""
        idx = list(section_index_path or [])
        if not idx:
            return OperationResult(success=False, message="No section to move")
        try:
            return self._recorded_edit(
                lambda: self.editing_service.move_section_to_target(self.context, idx, target_index_path)
            )
        except Exception:
            return OperationResult(success=False, message="Failed to move section")

    def handle_send_mixed_selection_to(
        self, 
        target_index_path: Optional[List[int]], 
        topic_refs: List[str],
        section_paths: List[List[int]]
    ) -> OperationResult:
        """Handle unified send-to for mixed topic+section selections.
        
        This method provides a single entry point for moving any combination of
        topics and sections, with automatic hierarchy preservation and validation.
        
        Parameters
        ----------
        target_index_path : Optional[List[int]]
            Destination path (None for root level)
        topic_refs : List[str]
            List of topic href references to move
        section_paths : List[List[int]]
            List of section index paths to move
            
        Returns
        -------
        OperationResult
            Success/failure result with appropriate message
        """
        try:
            return self._recorded_edit(
                lambda: self.editing_service.move_mixed_selection_to_target(
                    self.context, topic_refs, section_paths, target_index_path
                )
            )
        except Exception:
            return OperationResult(success=False, message="Failed to move mixed selection")

    # XML-centric movement API
    def handle_move_selection(self, nodes: List[ET.Element], direction: Literal["up", "down", "promote", "demote"]) -> OperationResult:
        """Move selected XML nodes intelligently.
        - For consecutive topicrefs and direction up/down: preserve group order using existing multi move
        - Otherwise move nodes one-by-one using intelligent algorithms (supports sections too)
        """
        if not nodes:
            return OperationResult(success=False, message="No selection")
        # Filter out non-elements
        xml_nodes = [n for n in nodes if hasattr(n, 'tag')]
        if not xml_nodes:
            return OperationResult(success=False, message="No selection")

        # Group consecutive topics path - but prefer single-item movement for stability
        only_topics = all(getattr(n, 'tag', None) == 'topicref' for n in xml_nodes)
        if only_topics and direction in ("up", "down") and len(xml_nodes) >= 3:
            # Only use grouped move for 3+ topics (2 topics can be unstable)
            hrefs: List[str] = []
            for n in xml_nodes:
                try:
                    href = n.get('href')  # type: ignore[attr-defined]
                    if href:
                        hrefs.append(href)
                except Exception:
                    pass
            if len(hrefs) >= 3:
                try:
                    return self._recorded_edit(lambda: self.editing_service.move_consecutive_topics(self.context, hrefs, direction))
                except Exception:
                    # Fallback to one-by-one
                    pass
            # For 1-2 topics, use one-by-one movement for better stability

        # Fallback: move one-by-one using intelligent element movement
        def _move_one(n: ET.Element) -> bool:
            try:
                if direction == 'up':
                    return bool(self.editing_service.move_element_up(self.context, n).success)
                elif direction == 'down':
                    return bool(self.editing_service.move_element_down(self.context, n).success)
                # Promote/demote could be implemented later
                return False
            except Exception:
                return False

        # Order matters for stability
        ordered = list(xml_nodes) if direction == 'up' else list(reversed(xml_nodes))
        moved_any = False
        for n in ordered:
            if _move_one(n):
                moved_any = True

        return OperationResult(success=moved_any, message=("Moved selection." if moved_any else "Cannot move selection."))

    def list_send_to_destinations(self) -> List[Dict[str, object]]:
        """Return list of possible destinations for Send-to menu.

        Each entry is a dict with keys:
        - 'label': str (e.g., "Root (Top level)" or "3.2. Section title")
        - 'index_path': Optional[List[int]] (None means root)
        """
        destinations: List[Dict[str, object]] = []
        try:
            destinations.append({"label": "Root (Top level)", "index_path": None})
            root = getattr(self.context, "ditamap_root", None)
            if root is None:
                return destinations

            # Precompute section numbering once (O(N)) and reuse
            try:
                from orlando_toolkit.core.utils import calculate_section_numbers
                section_number_map = calculate_section_numbers(root) or {}
            except Exception:
                section_number_map = {}

            def _extract_base_title(node: object) -> str:
                # Minimal, non-recursive title extraction to avoid heavy work in loop
                try:
                    nav = node.find("topicmeta/navtitle") if hasattr(node, "find") else None
                    if nav is not None and getattr(nav, "text", None):
                        return str(nav.text).strip()
                except Exception:
                    pass
                try:
                    t = node.find("title") if hasattr(node, "find") else None
                    if t is not None and getattr(t, "text", None):
                        return str(t.text).strip()
                except Exception:
                    pass
                try:
                    if hasattr(node, "get"):
                        attr = node.get("navtitle", "")
                        if isinstance(attr, str) and attr.strip():
                            return attr.strip()
                except Exception:
                    pass
                return "Section"

            def walk(node: object, path: List[int]) -> None:
                try:
                    structural_children = [el for el in list(node) if getattr(el, "tag", None) in ("topicref", "topichead")]
                except Exception:
                    structural_children = []
                for i, child in enumerate(structural_children):
                    child_path = path + [i]
                    tag = getattr(child, "tag", None)
                    if tag == "topichead":
                        # Build label from precomputed section number + base title
                        try:
                            num = section_number_map.get(child, "")
                        except Exception:
                            num = ""
                        base = _extract_base_title(child)
                        label = f"{num}. {base}" if num and num != "0" else base
                        destinations.append({"label": label, "index_path": child_path})
                    # Recurse
                    walk(child, child_path)

            walk(root, [])
        except Exception:
            pass
        return destinations
