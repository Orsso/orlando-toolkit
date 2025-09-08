from __future__ import annotations

from typing import Callable, Optional


class PreviewCoordinator:
    """Encapsulate preview rendering and breadcrumb updates for StructureTab.

    UI-only coordinator that delegates preview compilation/rendering to the
    controller and manages async delivery to the provided panel. Keeps a
    simple job sequence to avoid showing stale results.

    Parameters
    ----------
    controller_getter : Callable[[], object]
        Zero-arg callable returning the current controller (or None).
    panel : object
        Preview panel object with get_mode, set_loading, set_title, set_content,
        show_error, set_breadcrumb_path methods.
    schedule_ui : Callable[[int, Callable[[], None]], object]
        Tk-style scheduler (e.g., widget.after) used for UI thread callbacks.
    run_in_thread : Callable[[Callable[[], object], Optional[Callable[[object], None]]], None]
        Function that executes work_fn in a background thread and invokes
        done_fn on the UI thread via schedule_ui.
    """

    def __init__(
        self,
        *,
        controller_getter: Callable[[], object],
        panel: object,
        schedule_ui: Callable[[int, Callable[[], None]], object],
        run_in_thread: Callable[[Callable[[], object], Optional[Callable[[object], None]]], None],
    ) -> None:
        self._get_controller = controller_getter
        self._panel = panel
        self._schedule_ui = schedule_ui
        self._run_in_thread = run_in_thread
        self._job_seq: int = 0

    # -------------------------------------------------------------- Public API

    def render_for_node(self, node: object) -> None:
        """Render preview for an XML element (topicref or topichead).
        - topicref: full topic HTML/XML
        - topichead: minimal section/heading view
        """
        ctrl = self._get_controller()
        panel = self._panel
        if not ctrl or not panel or node is None:
            return

        # Determine mode (html|xml)
        try:
            mode = panel.get_mode()
        except Exception:
            mode = "html"

        # Pre-state
        try:
            panel.set_title("Preview")
            panel.set_loading(True)
        except Exception:
            pass

        # Invalidate older jobs
        try:
            self._job_seq += 1
        except Exception:
            self._job_seq = 1
        job_id = int(self._job_seq)

        def _work():
            try:
                if mode == "xml":
                    return ("xml", ctrl.compile_preview_for_node(node))  # type: ignore[attr-defined]
                return ("html", ctrl.render_html_preview_for_node(node))  # type: ignore[attr-defined]
            except Exception as ex:  # pragma: no cover
                return ("err", ex)

        def _done(result):
            if job_id != getattr(self, "_job_seq", 0):
                try:
                    panel.set_loading(False)
                except Exception:
                    pass
                return
            kind, payload = (result if isinstance(result, tuple) and len(result) == 2 else ("err", None))
            try:
                if kind == "err":
                    raise Exception(str(payload) if payload is not None else "Preview failed")
                res = payload
                if getattr(res, "success", False) and isinstance(getattr(res, "content", None), str):
                    content = getattr(res, "content")
                    # For XML mode, escape and wrap so raw tags are visible
                    try:
                        if mode == "xml":
                            from html import escape as _escape
                            content = f"<pre style=\"white-space:pre-wrap;\">{_escape(content)}</pre>"
                    except Exception:
                        pass
                    try:
                        panel.set_content(content)
                    except Exception:
                        pass
                    # Update breadcrumb for topic nodes
                    try:
                        if hasattr(node, 'tag') and getattr(node, 'tag', None) == 'topicref':
                            href = node.get('href') if hasattr(node, 'get') else ''
                            if href:
                                self._update_breadcrumb_for_ref(href)
                    except Exception:
                        pass
                else:
                    msg = getattr(res, "message", None) if res is not None else None
                    try:
                        panel.show_error(str(msg or "Unable to render preview"))
                    except Exception:
                        pass
            except Exception as _ex:
                try:
                    panel.show_error(f"Preview failed: {_ex}")
                except Exception:
                    pass
            finally:
                try:
                    panel.set_loading(False)
                except Exception:
                    pass

        self._run_in_thread(_work, _done)

    def update_for_selection(self, selection_nodes: list[object]) -> None:
        """Update preview for a selection of XML nodes.
        Preference order:
        - First topicref among nodes (auto-advance behavior)
        - Else first node (section) renders minimal heading view
        - Empty selection clears preview
        """
        nodes = list(selection_nodes or [])
        if not nodes:
            try:
                self._panel.clear()
            except Exception:
                pass
            return
        # Find first topicref in provided nodes
        topic_node = None
        for n in nodes:
            try:
                if hasattr(n, 'tag') and getattr(n, 'tag', None) == 'topicref':
                    topic_node = n
                    break
            except Exception:
                continue
        if topic_node is not None:
            self.render_for_node(topic_node)
            return
        # Fallback: render the first node (section minimal view)
        self.render_for_node(nodes[0])

    def on_mode_changed(self) -> None:
        # Caller should pass current selection
        pass

    # ------------------------------------------------------------- Internals
    def _update_breadcrumb_for_ref(self, topic_ref: str) -> None:
        ctrl = self._get_controller()
        panel = self._panel
        if not ctrl or not hasattr(ctrl, 'get_topic_path'):
            return
        try:
            from orlando_toolkit.ui.widgets.breadcrumb_widget import BreadcrumbItem
            path_data = ctrl.get_topic_path(topic_ref)
            breadcrumb_items = [BreadcrumbItem(label=title, value=href) for title, href in (path_data or [])]
            if hasattr(panel, 'set_breadcrumb_path'):
                panel.set_breadcrumb_path(breadcrumb_items)
        except Exception:
            pass


