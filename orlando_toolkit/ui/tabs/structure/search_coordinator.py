from __future__ import annotations

from typing import Callable, List
import xml.etree.ElementTree as ET


class SearchCoordinator:
    """Coordinate search interactions between UI tree, controller, and preview."""

    def __init__(
        self,
        *,
        controller_getter: Callable[[], object],
        tree: object,
        preview: object,
        update_legend: Callable[[], None],
    ) -> None:
        self._get_controller = controller_getter
        self._tree = tree
        self._preview = preview
        self._update_legend = update_legend

    # ------------------------------------------------------------------
    def term_changed(self, term: str) -> None:
        ctrl = self._get_controller()
        if ctrl is None:
            return
        try:
            # XML-centric: controller returns List[ET.Element]
            results: List[ET.Element] = list(ctrl.handle_search(term) or [])  # type: ignore[assignment]
        except Exception:
            results = []  # type: ignore[assignment]

        # Highlight all matches without altering selection
        try:
            if results and hasattr(self._tree, 'set_highlight_xml_nodes'):
                self._tree.set_highlight_xml_nodes(results)  # type: ignore[attr-defined]
            else:
                # Fallback to href-based highlighting when XML API unavailable
                hrefs = []
                for node in results or []:
                    try:
                        if hasattr(node, 'tag') and node.tag == 'topicref':
                            href = node.get('href')
                            if href:
                                hrefs.append(href)
                    except Exception:
                        continue
                if hrefs:
                    self._tree.set_highlight_refs(hrefs)  # type: ignore[attr-defined]
                else:
                    self._tree.clear_highlight_refs()  # type: ignore[attr-defined]
        except Exception:
            pass

        # Focus and preview first match (auto-advance handled by preview coordinator)
        if results:
            try:
                # Prefer centering on the first result structurally
                if hasattr(self._tree, 'focus_item_centered'):
                    self._tree.focus_item_centered(results[0])  # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                if self._preview is not None and hasattr(self._preview, 'update_for_selection'):
                    # Pass full result list so the coordinator can auto-advance to a topic
                    self._preview.update_for_selection(results)  # type: ignore[attr-defined]
            except Exception:
                pass

        # Update legend
        try:
            self._update_legend()
        except Exception:
            pass

    # ------------------------------------------------------------------
    def navigate(self, direction: str) -> None:
        ctrl = self._get_controller()
        if ctrl is None:
            return
        try:
            results: List[ET.Element] = list(getattr(ctrl, "search_results", []) or [])
        except Exception:
            results = []
        if not results:
            return
        try:
            idx = getattr(ctrl, "search_index", -1)
        except Exception:
            idx = -1
        idx = max(0, idx - 1) if direction == "prev" else min(len(results) - 1, idx + 1)
        try:
            ctrl.search_index = idx  # type: ignore[attr-defined]
        except Exception:
            pass
        
        selected_node = results[idx]
        # Select current match, update tree/preview
        try:
            # Controller accepts XML nodes for selection
            ctrl.select_items([selected_node])
        except Exception:
            pass
        try:
            self._tree.update_selection_by_xml_nodes([selected_node])
        except Exception:
            pass
        try:
            self._tree.focus_item_centered(selected_node)
        except Exception:
            pass
        try:
            if self._preview is not None and hasattr(self._preview, 'update_for_selection'):
                # Provide current node first, followed by remaining results to enable auto-advance to topics
                ordered = [selected_node] + results[idx+1:] + results[:idx]
                self._preview.update_for_selection(ordered)  # type: ignore[attr-defined]
        except Exception:
            pass


