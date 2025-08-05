from __future__ import annotations

"""Service layer for structural edits on the in-memory DITA map.

This module provides a UI-agnostic, testable service that encapsulates the
business logic previously embedded in UI code for manipulating the DITA
structure (reordering, promoting/demoting, renaming, deleting topics).

Scope and guarantees:
- Operates purely in-memory on DitaContext, no file I/O nor UI imports.
- Conservative behavior with boundary checks; invalid operations return
  OperationResult(success=False, ...) with clear messaging, never raise.
- Keeps API stable and isolates uncertain internals into helpers with TODO notes.

This service focuses on topicref/topichead manipulation inside context.ditamap_root
and synchronizes with context.topics when necessary.

Examples
--------
Basic usage:

    service = StructureEditingService()
    result = service.move_topic(ctx, "topics/topic_123.dita", "up")
    if not result.success:
        print(result.message)

"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Literal

from lxml import etree as ET  # type: ignore

from orlando_toolkit.core.models import DitaContext
from orlando_toolkit.core import utils, merge


__all__ = ["OperationResult", "StructureEditingService"]


@dataclass(frozen=True)
class OperationResult:
    """Result of a structural editing operation.

    Attributes
    ----------
    success
        Whether the operation completed successfully.
    message
        Human-readable summary suitable for logs or UI display.
    details
        Optional structured details for diagnostics or caller logic.
    """
    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


class StructureEditingService:
    """Encapsulates structural edit operations on a DITA map.

    The service performs safe, conservative edits to the DITA map within
    a DitaContext. It manipulates topicref/topichead elements in
    context.ditamap_root and updates context.topics where applicable.

    Design principles:
    - No UI dependencies (no Tkinter), no disk I/O.
    - No exceptions for expected invalid actions; return OperationResult.
    - Non-destructive helpers are used to locate nodes and parents.
    - Where deeper internals are uncertain, the logic is isolated and documented
      for future refinement while preserving the public API.

    Notes
    -----
    Topic references are represented by elements with tag "topicref" (content-bearing)
    or "topichead" (structural). Renaming and deletion operate primarily on "topicref"
    with an href attribute pointing to topics/{filename}. Promote/demote and up/down
    are implemented in terms of reordering and reparenting of topicref/topichead nodes.
    """

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def move_topic(
        self,
        context,
        topic_id: str,
        direction: Literal["up", "down", "promote", "demote"],
    ) -> OperationResult:
        """Move a topic within the DITA map by topic_id.

        Canonical API: accepts topic_id only (href or filename). Topic refs/elements are not accepted.

        - Returns OperationResult with success flag and non-raising boundary handling.
        """
        # Do not hard-require a real ditamap here; tests may monkeypatch adapters.
        # Always attempt to resolve via the adapter first.
        node = self._find_topic_ref(context, topic_id)
        if node is None:
            return OperationResult(False, f"Topic not found for id '{topic_id}'.", {"topic_id": topic_id})

        if direction == "up":
            ok = self._move_up(context, node)
            return OperationResult(ok, ("Moved topic up." if ok else "Cannot move up (at boundary)."), {"topic_id": topic_id})
        if direction == "down":
            ok = self._move_down(context, node)
            return OperationResult(ok, ("Moved topic down." if ok else "Cannot move down (at boundary)."), {"topic_id": topic_id})
        if direction == "promote":
            ok = self._promote(context, node)
            return OperationResult(ok, ("Promoted topic." if ok else "Cannot promote (at root or invalid)."), {"topic_id": topic_id})
        if direction == "demote":
            ok = self._demote(context, node)
            return OperationResult(ok, ("Demoted topic." if ok else "Cannot demote (no previous sibling)."), {"topic_id": topic_id})

        return OperationResult(False, f"Unsupported move direction '{direction}'.", {"allowed": ["up", "down", "promote", "demote"]})

    def merge_topics(self, context, source_ids: List[str], target_id: str) -> OperationResult:
        """Non-mutating merge API placeholder.

        Canonical API: accepts topic_id/topic_ids only; topic refs/elements are not accepted by this method.
        """
        # Keep non-mutating per requirements
        return OperationResult(False, "Not implemented", details={"source_ids": list(source_ids), "target_id": target_id})

    def rename_topic(self, context, topic_id: str, new_title: str) -> OperationResult:
        """Rename a topic by topic_id (href or filename). Canonical API uses topic_id only; topic refs/elements are not accepted."""
        if getattr(context, "ditamap_root", None) is None:
            return OperationResult(False, "No ditamap available in context.", {"reason": "missing_ditamap"})

        node = self._find_topic_ref(context, topic_id)
        if node is None:
            return OperationResult(False, f"Topic not found for id '{topic_id}'.", {"topic_id": topic_id})

        ok = self._rename(context, node, new_title)
        if ok:
            filename = self._normalize_filename(topic_id)
            return OperationResult(True, f"Renamed topic '{filename}'.", {"topic_id": topic_id, "new_title": " ".join((new_title or "").split())})
        return OperationResult(False, "Rename failed.", {"topic_id": topic_id})

    def delete_topics(self, context, topic_ids: List[str]) -> OperationResult:
        """Delete topics by topic_ids (hrefs or filenames). Canonical API uses topic_ids only; topic refs/elements are not accepted."""
        if getattr(context, "ditamap_root", None) is None:
            return OperationResult(False, "No ditamap available in context.", {"reason": "missing_ditamap"})

        requested = list(topic_ids)
        deleted_count = self._delete_by_ids(context, topic_ids)

        details = {"requested": requested, "deleted": deleted_count, "skipped": max(0, len(requested) - deleted_count)}
        return OperationResult(deleted_count > 0, ("Deleted topics." if deleted_count > 0 else "No topics deleted."), details)

    # -------------------------------------------------------------------------
    # Internal helpers (non-destructive, isolated)
    # -------------------------------------------------------------------------

    # Adapter helpers (for monkeypatching in tests)
    def _find_topic_ref(self, context, topic_id):
        """Resolve topic_id (href or filename) to the topicref element, or None."""
        root = getattr(context, "ditamap_root", None)
        if root is None:
            return None
        if isinstance(topic_id, str) and "/" in topic_id:
            return self._find_topicref_by_href(root, topic_id)
        filename = self._normalize_filename(topic_id)
        return self._find_topicref_by_filename(root, filename)

    def _move_up(self, context, node) -> bool:
        """Adapter mapping to internal move up."""
        parent = node.getparent()
        if parent is None:
            return False
        res = self._move_sibling(context, parent, node, delta=-1)
        return bool(res.success)

    def _move_down(self, context, node) -> bool:
        """Adapter mapping to internal move down."""
        parent = node.getparent()
        if parent is None:
            return False
        res = self._move_sibling(context, parent, node, delta=1)
        return bool(res.success)

    def _promote(self, context, node) -> bool:  # adapter name required; delegates to existing internal
        res = super(type(self), self)._promote(context, node) if False else self.__class__.__dict__['_promote'](self, context, node)  # type: ignore
        # The above indirection keeps name intact while returning bool for adapter
        return bool(res.success)

    def _demote(self, context, node) -> bool:  # adapter name required; delegates to existing internal
        res = super(type(self), self)._demote(context, node) if False else self.__class__.__dict__['_demote'](self, context, node)  # type: ignore
        return bool(res.success)

    def _rename(self, context, node, new_title) -> bool:
        """Adapter encapsulating rename logic; updates topic title and navtitle."""
        cleaned = " ".join((new_title or "").split())
        if not cleaned:
            return False

        # Update topic XML title if content-bearing (has href -> filename -> context.topics)
        href = node.get("href")
        if href:
            fname = href.split("/")[-1]
            topic_el = context.topics.get(fname)
            if topic_el is not None:
                title_el = topic_el.find("title")
                if title_el is None:
                    title_el = ET.SubElement(topic_el, "title")
                title_el.text = cleaned

        # Update topicref's navtitle
        self._ensure_navtitle(node, cleaned)
        return True

    def _delete_by_ids(self, context, ids: List[str]) -> int:
        """Adapter performing deletion by ids, purging unreferenced topics afterwards."""
        if getattr(context, "ditamap_root", None) is None:
            return 0

        count = 0
        for tid in ids:
            node = self._find_topic_ref(context, tid)
            if node is None:
                continue
            href = node.get("href")
            if not href:
                # skip structural nodes
                continue
            parent = node.getparent()
            if parent is None:
                continue
            parent.remove(node)
            count += 1

        # purge topics after batch delete
        self._purge_unreferenced_topics(context)
        return count

    @staticmethod
    def _normalize_filename(topic_ref: str) -> str:
        """Return bare filename from an href or filename string."""
        # Accept "topics/foo.dita" or "foo.dita"
        if "/" in topic_ref:
            return topic_ref.split("/")[-1]
        return topic_ref

    @staticmethod
    def _find_topicref_by_filename(root: ET.Element, filename: str) -> Optional[ET.Element]:
        """Locate a topicref element pointing to topics/{filename}.

        Returns the first matching element or None if not found.
        """
        # Prefer exact href matches
        expr = f".//topicref[@href='topics/{filename}']"
        found = root.find(expr)
        if found is not None:
            return found

        # Fallback: any topicref whose href ends with the filename
        # This is more permissive and robust if paths varied.
        for tref in root.xpath(".//topicref[@href]"):
            href = tref.get("href", "")
            if href.endswith(filename):
                return tref
        return None

    @staticmethod
    def _find_topicref_by_href(root: ET.Element, href: str) -> Optional[ET.Element]:
        """Locate a topicref element by exact @href match."""
        try:
            expr = f".//topicref[@href='{href}']"
            return root.find(expr)
        except Exception:
            return None

    @staticmethod
    def _ensure_navtitle(tref: ET.Element, text: str) -> None:
        """Ensure topicmeta/navtitle exists and update its text."""
        topicmeta = tref.find("topicmeta")
        if topicmeta is None:
            topicmeta = ET.SubElement(tref, "topicmeta")
        navtitle = topicmeta.find("navtitle")
        if navtitle is None:
            navtitle = ET.SubElement(topicmeta, "navtitle")
        navtitle.text = text

    def _move_sibling(self, context: DitaContext, parent: ET.Element, tref: ET.Element, *, delta: int) -> OperationResult:
        """Move a topicref up/down among its siblings by one position."""
        # Consider only siblings that are structural/content nodes to preserve order relative to metadata
        siblings = [el for el in list(parent) if el.tag in ("topicref", "topichead")]
        try:
            idx_in_filtered = siblings.index(tref)
        except ValueError:
            # If tref not in filtered list (unlikely), fall back to raw indexing
            children = list(parent)
            if tref not in children:
                return OperationResult(False, "Internal error: node not found among parent's children.", {})
            current_index = children.index(tref)
            target_index = current_index + (-1 if delta < 0 else 1)
            if target_index < 0 or target_index >= len(children):
                return OperationResult(False, "Cannot move: already at boundary.", {"current_index": current_index})
            parent.remove(tref)
            parent.insert(target_index, tref)
            return OperationResult(True, "Moved topic.", {"from_index": current_index, "to_index": target_index})

        current_index = list(parent).index(tref)
        new_filtered_index = idx_in_filtered + (-1 if delta < 0 else 1)
        if new_filtered_index < 0 or new_filtered_index >= len(siblings):
            # Boundary; no change
            return OperationResult(False, "Cannot move: already at boundary.", {"filtered_index": idx_in_filtered})

        # Compute actual insertion index among all children by finding the target sibling
        target_sibling = siblings[new_filtered_index]
        target_index = list(parent).index(target_sibling)

        # When moving down and inserting before the target that follows after removing, adjust
        parent.remove(tref)
        insert_at = target_index
        if delta > 0:
            # Recompute index if needed after removal
            # If target_index was after tref, removing tref decreases indices by 1.
            # To keep relative order as "move after", we increment insertion by 1 when moving down.
            after_index = list(parent).index(target_sibling)
            insert_at = after_index + 1

        parent.insert(insert_at, tref)
        return OperationResult(True, "Moved topic.", {"from_index": current_index, "to_index": insert_at})

    def _promote(self, context: DitaContext, tref: ET.Element) -> OperationResult:
        """Promote a topicref one level up (outdent), placing it after its former parent."""
        parent = tref.getparent()
        if parent is None:
            return OperationResult(False, "Cannot promote: node has no parent.", {})

        grandparent = parent.getparent()
        if grandparent is None:
            return OperationResult(False, "Cannot promote: node is at root level.", {})

        # Find position of parent within grandparent among structural nodes
        gp_children = list(grandparent)
        if parent not in gp_children:
            return OperationResult(False, "Internal error: parent not found under grandparent.", {})
        parent_index = gp_children.index(parent)

        # Remove from current parent and insert after parent in grandparent
        parent.remove(tref)

        insert_at = parent_index + 1
        grandparent.insert(insert_at, tref)

        # Optionally update data-level to reflect new depth if present
        self._update_level_attributes_after_reparent(tref, parent, grandparent, direction="promote")

        return OperationResult(True, "Promoted topic one level up.", {"insert_index": insert_at})

    def _demote(self, context: DitaContext, tref: ET.Element) -> OperationResult:
        """Demote a topicref one level down (indent), making it the last child of the nearest previous sibling."""
        parent = tref.getparent()
        if parent is None:
            return OperationResult(False, "Cannot demote: node has no parent.", {})

        # Find previous sibling that is a structural/content node
        siblings = [el for el in list(parent) if el.tag in ("topicref", "topichead")]
        if tref not in siblings:
            return OperationResult(False, "Internal error: node not found among siblings.", {})
        idx = siblings.index(tref)
        if idx == 0:
            return OperationResult(False, "Cannot demote: no preceding sibling to become the new parent.", {})

        new_parent = siblings[idx - 1]

        # Only topicref or topichead can accept children; both are fine structurally
        # Insert as last child
        parent.remove(tref)
        new_parent.append(tref)

        # Optionally update data-level to reflect new depth if present
        self._update_level_attributes_after_reparent(tref, parent, new_parent, direction="demote")

        return OperationResult(True, "Demoted topic under previous sibling.", {})

    @staticmethod
    def _update_level_attributes_after_reparent(tref: ET.Element, old_parent: ET.Element, new_parent: ET.Element, *, direction: str) -> None:
        """Best-effort update of data-level attributes after reparenting.

        The codebase uses a 'data-level' attribute in several places to record
        logical depth. This helper performs a conservative adjustment:

        - promote: decrease tref's data-level by 1 if present
        - demote: increase tref's data-level by 1 if present

        It does not recursively update descendants; deeper synchronization may be
        addressed in future iterations if required by callers.

        TODO: Consider recalculating all levels with a traversal for strict
        consistency, or using utils.calculate_section_numbers if appropriate.
        """
        try:
            level_attr = tref.get("data-level")
            if level_attr is None:
                return
            level = int(level_attr)
            if direction == "promote":
                level = max(1, level - 1)
            elif direction == "demote":
                level = level + 1
            tref.set("data-level", str(level))
        except Exception:
            # Fail silently; level annotations are best-effort
            pass

    @staticmethod
    def _purge_unreferenced_topics(context: DitaContext) -> None:
        """Remove topics from context.topics that are no longer referenced in the map.

        Safe no-op if ditamap_root is missing or no hrefs found.
        """
        if context.ditamap_root is None:
            return
        hrefs = {
            (tref.get("href") or "").split("/")[-1]
            for tref in context.ditamap_root.xpath(".//topicref[@href]")
        }
        # Keep only referenced topics
        context.topics = {fn: el for fn, el in context.topics.items() if fn in hrefs}