from __future__ import annotations

from dataclasses import dataclass
import logging
from html import escape
from typing import Optional, Dict, Any, Iterable, Tuple

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core.preview import xml_compiler

logger = logging.getLogger(__name__)


@dataclass
class PreviewResult:
    """Structured result for preview-oriented operations.

    Attributes
    ----------
    success : bool
        Indicates whether the operation completed successfully.
    content : Optional[str]
        Result payload when successful (XML or HTML depending on the method).
        May be None on failure.
    message : str
        Human-readable outcome message. Clear on failure, brief on success.
    details : Optional[Dict[str, Any]]
        Structured ancillary data (e.g., error kinds, fallbacks, metadata).
    """
    success: bool
    content: Optional[str]
    message: str
    details: Optional[Dict[str, Any]] = None


class PreviewService:
    """Service wrapper for preview compilation logic.

    This service provides a thin, typed abstraction around the lower-level
    XML/HTML compilation utilities in ``core.preview.xml_compiler`` to keep
    higher layers (e.g., UI) decoupled from deep internals.

    The methods in this service follow a non-raising pattern for routine
    failures: they return a ``PreviewResult`` with ``success=False`` and a
    clear, user-facing message. Unexpected exceptions are caught and returned
    as structured failures including the exception class name for diagnostics.

    Notes
    -----
    - No I/O is performed by this service. It operates purely on in-memory
      data via the provided ``DitaContext`` and topic references.
    - Imports of ``xml_compiler`` are used conservatively; specific calls are
      isolated in private helpers with try/except wrappers. If the expected
      functions are not available, the service responds gracefully with a
      not-implemented style message in ``details``.
    - Where HTML rendering is not supported natively by ``xml_compiler``,
      a conservative fallback wraps XML in a minimal readable HTML template
      with escaped content in a ``<pre>`` block.

    Examples
    --------
    Basic usage:

    >>> service = PreviewService()
    >>> result = service.compile_topic_preview(context, "topics/introduction.dita")
    >>> if result.success:
    ...     xml = result.content
    ... else:
    ...     print(result.message)
    """

    # -----------------------------
    # Public API
    # -----------------------------

    def compile_topic_preview(self, context: DitaContext, topic_ref: str) -> PreviewResult:
        """Compile a topic into preview-ready XML.

        Parameters
        ----------
        context : DitaContext
            Active DITA processing context.
        topic_ref : str
            Topic reference path or identifier within the context.

        Returns
        -------
        PreviewResult
            On success, ``content`` contains XML as a string.

        Notes
        -----
        - Validates ``context`` and ``topic_ref`` before calling internals.
        - Does not raise for routine errors; returns a structured failure.
        """
        logger.debug("Preview: compile_topic_preview topic_ref=%s", topic_ref)
        validation = self._validate_inputs(context, topic_ref)
        if validation is not None:
            logger.info("Preview FAIL: invalid input reason=%s", (validation.details or {}).get("reason", "invalid_input"))
            return validation

        try:
            xml = self._try_compile_xml(context, topic_ref)
            if isinstance(xml, dict) and xml.get("_ni") is True:
                # Not implemented or topicref not found
                reason = str(xml.get("reason") or "not_implemented")
                if reason == "topicref_not_found":
                    logger.info("Preview FAIL: topicref_not_found topic_ref=%s", topic_ref)
                    return PreviewResult(
                        success=False,
                        content=None,
                        message="Topic reference not found in the current context.",
                        details={"reason": "topicref_not_found"},
                    )
                # generic not implemented
                logger.info("Preview NA: xml_compiler missing function get_raw_topic_xml")
                return PreviewResult(
                    success=False,
                    content=None,
                    message="XML compilation is not available.",
                    details={"reason": "compiler_function_missing" if reason == "compiler_function_missing" else "not_implemented"},
                )
            elif isinstance(xml, str):
                logger.debug("Preview OK: compile_topic_preview len=%d", len(xml))
                return PreviewResult(
                    success=True,
                    content=xml,
                    message="",
                    details=None,
                )
            else:
                logger.info("Preview NA: unexpected return type from get_raw_topic_xml")
                return PreviewResult(
                    success=False,
                    content=None,
                    message="XML compilation is not available.",
                    details={"reason": "not_implemented"},
                )
        except Exception as exc:  # noqa: BLE001 - intentionally broad for service boundary
            # Keep traceback formatter for potential logging, but don't include in details
            logger.error("Preview FAIL: exception type=%s msg=%s", exc.__class__.__name__, str(exc), exc_info=True)
            return PreviewResult(
                success=False,
                content=None,
                message="Failed to compile XML preview.",
                details={
                    "reason": "exception",
                    "exception_type": exc.__class__.__name__,
                    "exception_message": str(exc),
                },
            )

    def compile_preview(self, context: DitaContext, topic_ref: str) -> PreviewResult:
        """Alias for compile_topic_preview to keep controller naming stable."""
        return self.compile_topic_preview(context, topic_ref)

    def render_html_preview(self, context: DitaContext, topic_ref: str) -> PreviewResult:
        """Render a topic as HTML suitable for quick preview.

        Parameters
        ----------
        context : DitaContext
            Active DITA processing context.
        topic_ref : str
            Topic reference path or identifier within the context.

        Returns
        -------
        PreviewResult
            On success, ``content`` contains HTML as a string.

        Notes
        -----
        - Attempts a native HTML render via ``xml_compiler`` if available.
        - If HTML is not natively supported, compiles XML and wraps it in a
          minimal HTML fallback (escaped, preformatted), indicating the
          fallback in ``details``.
        """
        logger.debug("Preview: render_html_preview topic_ref=%s", topic_ref)
        validation = self._validate_inputs(context, topic_ref)
        if validation is not None:
            logger.info("Preview FAIL: invalid input reason=%s", (validation.details or {}).get("reason", "invalid_input"))
            return validation

        # First attempt HTML via xml_compiler; then fallback to XML wrapped into minimal HTML.
        # Keep results concise.
        # Step 1: try HTML
        try:
            html = self._try_compile_html(context, topic_ref)
            if isinstance(html, str):
                logger.debug("Preview OK: render_html_preview len=%d", len(html))
                return PreviewResult(
                    success=True,
                    content=html,
                    message="",
                    details=None,
                )
            else:
                # not implemented or topicref not found
                html_not_impl = html  # dict or other
        except Exception as exc:  # noqa: BLE001
            # proceed to fallback
            logger.debug("Preview: HTML compiler unavailable, falling back to XML (exc=%s)", exc.__class__.__name__)
            html_not_impl = {"_ni": True, "reason": "exception", "exception_type": exc.__class__.__name__, "exception_message": str(exc)}

        # Step 2: fallback: get XML and wrap
        try:
            xml_attempt = self._try_compile_xml(context, topic_ref)
            if isinstance(xml_attempt, str):
                wrapped = self._xml_to_minimal_html(xml_attempt)
                logger.debug("Preview OK: fallback HTML len=%d", len(wrapped))
                return PreviewResult(
                    success=True,
                    content=wrapped,
                    message="",
                    details=None,
                )
            else:
                # Could not compile XML either
                # Decide concise failure reason
                reason = "compiler_function_missing" if (isinstance(xml_attempt, dict) and xml_attempt.get("reason") == "compiler_function_missing") else "not_implemented"
                # If topicref specifically not found, prefer that message
                if isinstance(xml_attempt, dict) and xml_attempt.get("reason") == "topicref_not_found":
                    logger.info("Preview FAIL: topicref_not_found topic_ref=%s", topic_ref)
                    return PreviewResult(
                        success=False,
                        content=None,
                        message="Topic reference not found in the current context.",
                        details={"reason": "topicref_not_found"},
                    )
                logger.info("Preview NA: HTML rendering unavailable (reason=%s)", reason)
                return PreviewResult(
                    success=False,
                    content=None,
                    message="HTML rendering is not available.",
                    details={"reason": reason},
                )
        except Exception as exc:  # noqa: BLE001
            logger.error("Preview FAIL: exception during fallback type=%s msg=%s", exc.__class__.__name__, str(exc), exc_info=True)
            return PreviewResult(
                success=False,
                content=None,
                message="Failed to render HTML preview.",
                details={
                    "reason": "exception",
                    "exception_type": exc.__class__.__name__,
                    "exception_message": str(exc),
                },
            )

    def get_raw_xml(self, context: DitaContext, topic_ref: str) -> PreviewResult:
        """Return the raw XML for a topic without additional decoration.

        Parameters
        ----------
        context : DitaContext
            Active DITA processing context.
        topic_ref : str
            Topic reference path or identifier within the context.

        Returns
        -------
        PreviewResult
            On success, ``content`` contains XML as a string.

        Notes
        -----
        - Equivalent to ``compile_topic_preview`` semantically, but explicitly
          positioned as a raw retrieval API to help distinguish intent.
        """
        # Delegate to the same XML compilation flow for clarity and consistency.
        return self.compile_topic_preview(context, topic_ref)

    # -----------------------------
    # Internal helpers
    # -----------------------------

    def _validate_inputs(self, context: Optional[DitaContext], topic_ref: Optional[str]) -> Optional[PreviewResult]:
        """Validate context and topic reference.

        Returns
        -------
        Optional[PreviewResult]
            ``None`` when inputs are valid. Otherwise, a failure ``PreviewResult``.
        """
        if context is None:
            return PreviewResult(
                success=False,
                content=None,
                message="Context is required.",
                details={"reason": "invalid_input", "field": "context"},
            )

        # Try to ensure the context looks minimally sound.
        # We avoid importing UI or touching I/O here.
        if not isinstance(context, DitaContext):
            return PreviewResult(
                success=False,
                content=None,
                message="Invalid DitaContext instance.",
                details={"reason": "invalid_input", "field": "context", "type": type(context).__name__},
            )

        if topic_ref is None or (isinstance(topic_ref, str) and topic_ref.strip() == ""):
            return PreviewResult(
                success=False,
                content=None,
                message="Topic reference must be a non-empty string.",
                details={"reason": "invalid_input", "field": "topic_ref"},
            )

        if not isinstance(topic_ref, str):
            return PreviewResult(
                success=False,
                content=None,
                message="Topic reference must be a string.",
                details={"reason": "invalid_input", "field": "topic_ref", "type": type(topic_ref).__name__},
            )

        # Optional existence check if the context exposes a way to verify.
        # Kept conservative: do not assume internal structure of context.
        try:
            if hasattr(context, "topic_exists") and callable(getattr(context, "topic_exists")):
                exists = context.topic_exists(topic_ref)  # type: ignore[attr-defined]
                if not exists:
                    return PreviewResult(
                        success=False,
                        content=None,
                        message="Topic reference not found in the current context.",
                        details={"reason": "not_found", "topic_ref": topic_ref},
                    )
        except Exception as exc:  # noqa: BLE001
            # If validation helper itself fails, we proceed rather than block,
            # but note the anomaly in details for downstream debugging.
            return PreviewResult(
                success=False,
                content=None,
                message="Failed to validate topic existence due to an internal error.",
                details={
                    "reason": "validation_error",
                    "exception_type": exc.__class__.__name__,
                    "topic_ref": topic_ref,
                },
            )

        return None

    def _try_compile_xml(self, context: DitaContext, topic_ref: str):
        """Attempt to compile topic to XML using xml_compiler.

        Uses xml_compiler.get_raw_topic_xml(context, tref_element) if available.
        Returns:
          - str: XML string on success
          - dict with {"_ni": True, "reason": "..."} when not-implemented-like situations arise
        """
        fn = getattr(xml_compiler, "get_raw_topic_xml", None)
        if not callable(fn):
            return {"_ni": True, "reason": "compiler_function_missing", "attempted_call": "get_raw_topic_xml"}

        tref_el = self._resolve_topicref_element(context, topic_ref)
        if tref_el is None:
            return {"_ni": True, "reason": "topicref_not_found", "topic_ref": topic_ref}

        result = fn(context, tref_el)  # type: ignore[misc]
        if isinstance(result, str):
            return result
        return {"_ni": True, "reason": "unexpected_return_type", "attempted_call": "get_raw_topic_xml"}

    def _try_compile_html(self, context: DitaContext, topic_ref: str):
        """Attempt to compile topic to HTML using xml_compiler.

        Uses xml_compiler.render_html_preview(context, tref_element) if available.
        Returns:
          - str: HTML string on success
          - dict with {"_ni": True, "reason": "..."} when not-implemented-like situations arise
        """
        fn = getattr(xml_compiler, "render_html_preview", None)
        if not callable(fn):
            return {"_ni": True, "reason": "compiler_function_missing", "attempted_call": "render_html_preview"}

        tref_el = self._resolve_topicref_element(context, topic_ref)
        if tref_el is None:
            return {"_ni": True, "reason": "topicref_not_found", "topic_ref": topic_ref}

        result = fn(context, tref_el)  # type: ignore[misc]
        if isinstance(result, str):
            return result
        return {"_ni": True, "reason": "unexpected_return_type", "attempted_call": "render_html_preview"}

    def _xml_to_minimal_html(self, xml: str) -> str:
        """Wrap XML into a minimal readable HTML document.

        Parameters
        ----------
        xml : str
            XML content to display, escaped and placed within <pre>.

        Returns
        -------
        str
            Minimal HTML string safe for preview rendering.
        """
        escaped = escape(xml, quote=False)
        return (
            "<!DOCTYPE html>\n"
            "<html lang=\"en\">\n"
            "  <head>\n"
            "    <meta charset=\"utf-8\" />\n"
            "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
            "    <title>Preview</title>\n"
            "    <style>\n"
            "      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 0; padding: 1rem; }\n"
            "      pre { white-space: pre-wrap; word-break: break-word; background: #f6f8fa; padding: 1rem; border-radius: 6px; }\n"
            "    </style>\n"
            "  </head>\n"
            "  <body>\n"
            "    <pre>"
            f"{escaped}"
            "</pre>\n"
            "  </body>\n"
            "</html>\n"
        )

    # -----------------------------
    # Topicref resolver and diagnostics
    # -----------------------------

    def _resolve_topicref_element(self, context: DitaContext, topic_ref: str):
        """Resolve a topicref/topichead element in the context's ditamap_root.

        The resolver accepts href-like strings or IDs and tries multiple matching
        strategies conservatively:
          - Normalize input and compare with @href on topicref/topichead nodes.
          - Accept small variations like leading './' and OS path separators.
          - Try fragment-insensitive matching: 'a/b.dita#frag' ~ 'a/b.dita'.
          - As a last resort, compare against navtitle text for human-friendly refs.

        Returns:
          - lxml.etree._Element on success
          - None when not found or context lacks a traversable ditamap_root
        """
        try:
            from lxml import etree as ET  # type: ignore
        except Exception:
            return None

        root = getattr(context, "ditamap_root", None)
        if root is None:
            return None

        # Gather candidates: topicref and topichead elements in the map
        # Avoid XPath dependency differences; iterate tree manually.
        def iter_candidates(node) -> Iterable:
            stack = [node]
            while stack:
                el = stack.pop()
                if not hasattr(el, "tag"):
                    continue
                tag_local = el.tag.split("}")[-1] if isinstance(el.tag, str) else ""
                if tag_local in ("topicref", "topichead"):
                    yield el
                # push children
                try:
                    stack.extend(list(el))
                except Exception:
                    pass

        # Normalization helpers
        def _normalize_href(h: str) -> Tuple[str, str]:
            h0 = h.strip()
            # Unify path separators and strip leading './'
            h1 = h0.replace("\\", "/")
            if h1.startswith("./"):
                h1 = h1[2:]
            # Split fragment if any
            if "#" in h1:
                base, frag = h1.split("#", 1)
            else:
                base, frag = h1, ""
            return h1, base

        q_full, q_base = _normalize_href(topic_ref)

        # First pass: match exact @href (normalized)
        for el in iter_candidates(root):
            href = el.get("href") or ""
            if href:
                h_full, h_base = _normalize_href(href)
                if q_full == h_full or q_full == h_base or q_base == h_full or q_base == h_base:
                    return el

        # Second pass: if input looked like an ID-only ref, try @id direct match
        # (some contexts might pass bare IDs)
        for el in iter_candidates(root):
            el_id = el.get("id")
            if el_id and (topic_ref == el_id or q_base == el_id or q_full == el_id):
                return el

        # Third pass: try navtitle text as a lenient alias
        for el in iter_candidates(root):
            try:
                navtitle = el.find("topicmeta/navtitle")
                if navtitle is not None and isinstance(navtitle.text, str):
                    if navtitle.text.strip() == topic_ref.strip():
                        return el
            except Exception:
                continue

        return None

    def _format_traceback_head(self) -> str:
        """Return a condensed first line of the current exception; kept for potential future use."""
        try:
            import sys
            etype, value, _tb = sys.exc_info()
            if etype is None:
                return ""
            # Concise single-line summary without full traceback to avoid verbose diagnostics
            return f"{etype.__name__}: {value}"
        except Exception:
            return ""