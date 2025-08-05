from __future__ import annotations

"""Undo/redo snapshot management for DitaContext.

This service is UI-agnostic and performs pure in-memory history tracking of
the entire DitaContext state. It serializes the full XML map and topics in
snapshots and can restore previous states into a provided DitaContext instance.

Design principles
-----------------
- No UI imports and no I/O (filesystem/console).
- Conservative, self-contained implementation with graceful error handling.
- Snapshots are immutable blobs once stored.
- Redo stack is cleared on every new snapshot push (standard undo/redo behavior).
- Memory usage controlled by a max_history ring-like policy (trim oldest).

Notes
-----
If the core models expose richer serialization, those could be adopted here.
Given current DitaContext shape, we fallback to robust XML serialization via
lxml.etree.tostring() for map and topics, while copying images and metadata.

"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple

from lxml import etree as ET

from orlando_toolkit.core.models import DitaContext


@dataclass(frozen=True)
class _Snapshot:
    """Immutable in-memory snapshot of a DitaContext.

    Fields contain serialized XML byte blobs for map and topics, plus shallow
    copies of images and metadata that are JSON-serializable or plain bytes/str.

    Attributes
    ----------
    ditamap_xml :
        Serialized ditamap root as bytes, or None if no map exists.
    topics_xml :
        Mapping of topic filename -> serialized topic XML as bytes.
    images :
        Mapping of image filename -> raw bytes (copied reference).
    metadata :
        Shallow-copied metadata dictionary.
    """

    ditamap_xml: Optional[bytes]
    topics_xml: Dict[str, bytes]
    images: Dict[str, bytes]
    metadata: Dict[str, Any]


class UndoService:
    """Manage undo/redo stacks for :class:`DitaContext`.

    The service keeps two stacks of immutable snapshots: an undo stack and a redo
    stack. Each snapshot fully captures the DitaContext state (ditamap, topics,
    images, metadata). Undo/redo restore the previous/next snapshot state into
    a provided DitaContext instance in place.

    Parameters
    ----------
    max_history : int, default=50
        Maximum number of undo snapshots to keep. Oldest entries are discarded
        when the capacity is exceeded. Must be >= 1; if passed lower, it will be
        coerced to 1.

    Notes
    -----
    - Push operations clear the redo stack.
    - Routine errors during restore are handled gracefully (method returns False).
    - No I/O or logging is performed here; callers can handle UI feedback.

    Examples
    --------
    Create a service, push states, undo/redo:

    >>> ctx = DitaContext()
    >>> svc = UndoService(max_history=10)
    >>> # After mutating ctx externally:
    >>> svc.push_snapshot(ctx)
    >>> changed = svc.undo(ctx)   # Restores previous state if available
    >>> redo_ok = svc.redo(ctx)   # Redo if available
    """

    def __init__(self, max_history: int = 50) -> None:
        self._max_history: int = max(1, int(max_history))
        self._undo_stack: List[_Snapshot] = []
        self._redo_stack: List[_Snapshot] = []

    # --------------------------------------------------------------------- API

    def push_snapshot(self, context: DitaContext) -> None:
        """Capture current context state and push onto the undo stack.

        The redo stack is cleared to follow standard undo/redo semantics.
        If the undo stack exceeds max_history, the oldest snapshot is dropped.

        Parameters
        ----------
        context : DitaContext
            The context whose state is to be captured.

        Notes
        -----
        - This method does not raise on serialization issues; if an unexpected
          issue occurs during snapshotting, the snapshot is simply not pushed.
        - Snapshots are immutable blobs and will not be mutated after push.
        """
        snap = self._create_snapshot(context)
        if snap is None:
            # Graceful no-op if serialization failed
            return
        self._undo_stack.append(snap)
        # New user action invalidates redo history
        self._redo_stack.clear()
        # Enforce capacity
        if len(self._undo_stack) > self._max_history:
            # Trim oldest
            overflow = len(self._undo_stack) - self._max_history
            if overflow > 0:
                del self._undo_stack[0:overflow]

    def undo(self, context: DitaContext) -> bool:
        """Restore the previous state into the provided context.

        Semantics (baseline-oriented):
        - Assumes callers push a snapshot BEFORE mutation (baseline) and AFTER mutation (post).
        - Undo will restore the previous snapshot (baseline) and move the post snapshot to redo.

        Behavior
        --------
        Given undo_stack = [..., baseline, post] and current context == post:
        - Pop 'post' from undo_stack and push it onto redo_stack (so it can be redone).
        - Restore 'baseline' from the new top of undo_stack.
        """
        # Need at least one snapshot to undo to a previous state
        if not self._undo_stack:
            return False



        # Pop the latest (post-mutation) snapshot and push it to redo stack
        post_snap = self._undo_stack.pop()

        # If now the undo stack is empty, we cannot restore a baseline; revert operation.
        if not self._undo_stack:
            # Put back the popped snapshot as we cannot complete undo
            self._undo_stack.append(post_snap)
            return False

        # Previous snapshot on top is the baseline to restore
        baseline_snap = self._undo_stack[-1]

        # Attempt restore of baseline
        if not self._restore_snapshot_into_context(context, baseline_snap):
            # Restoration failed; return False and do not alter stacks further
            # Put back the popped snapshot to maintain stack consistency
            self._undo_stack.append(post_snap)
            return False

        # On success, push the post snapshot to redo stack
        self._redo_stack.append(post_snap)
        if len(self._redo_stack) > self._max_history:
            overflow = len(self._redo_stack) - self._max_history
            if overflow > 0:
                del self._redo_stack[0:overflow]
        return True

    def redo(self, context: DitaContext) -> bool:
        """Re-apply a state that was previously undone.

        Semantics (baseline-oriented complement):
        - Given undo_stack = [..., baseline] and redo_stack = [post],
          redo restores 'post' and moves it back onto the undo stack.
        """
        if not self._redo_stack:
            return False

        # Candidate snapshot to restore is the latest post-mutation state
        post_snap = self._redo_stack.pop()

        # Attempt restore of post state
        if not self._restore_snapshot_into_context(context, post_snap):
            return False

        # Push restored post state back onto undo stack
        self._undo_stack.append(post_snap)
        if len(self._undo_stack) > self._max_history:
            overflow = len(self._undo_stack) - self._max_history
            if overflow > 0:
                del self._undo_stack[0:overflow]
        return True

    def can_undo(self) -> bool:
        """Return True if an undo operation is currently possible."""
        return len(self._undo_stack) > 1

    def can_redo(self) -> bool:
        """Return True if an undo operation is currently possible."""
        return len(self._undo_stack) > 1    
    def clear(self) -> None:
        """Clear both undo and redo histories."""
        self._undo_stack.clear()
        self._redo_stack.clear()

    # --------------------------------------------------------------- Internals

    def _create_snapshot(self, context: DitaContext) -> Optional[_Snapshot]:
        """Serialize the entire DitaContext into an immutable snapshot.

        Uses conservative serialization via lxml.etree.tostring for XML content.
        Images and metadata are shallow-copied.

        Parameters
        ----------
        context : DitaContext

        Returns
        -------
        Optional[_Snapshot]
            The created snapshot, or None if serialization failed.
        """
        try:
            # Serialize map
            ditamap_xml: Optional[bytes]
            if context.ditamap_root is not None:
                ditamap_xml = ET.tostring(context.ditamap_root, encoding="utf-8")
            else:
                ditamap_xml = None

            # Serialize topics
            topics_xml: Dict[str, bytes] = {}
            for name, elem in context.topics.items():
                if elem is None:
                    # Defensive: skip None entries
                    continue
                topics_xml[name] = ET.tostring(elem, encoding="utf-8")

            # Copy images and metadata (no deep serialization needed here)
            images_copy: Dict[str, bytes] = dict(context.images)
            metadata_copy: Dict[str, Any] = dict(context.metadata)

            return _Snapshot(
                ditamap_xml=ditamap_xml,
                topics_xml=topics_xml,
                images=images_copy,
                metadata=metadata_copy,
            )
        except Exception:
            # Graceful failure
            return None

    def _restore_snapshot_into_context(self, context: DitaContext, snap: _Snapshot) -> bool:
        """Restore a snapshot state into the provided context in place.

        This method attempts a full reconstruction of the DitaContext based on the
        serialized blobs. It replaces the ditamap root, topics mapping, images and
        metadata with reconstructed/copied values.

        Parameters
        ----------
        context : DitaContext
            The target context to mutate in-place.
        snap : _Snapshot
            The snapshot to restore from.

        Returns
        -------
        bool
            True if the context was restored successfully, False otherwise.

        Notes
        -----
        - Any parse/validation failure results in False and leaves the context
          in its previous state as much as possible.
        - Restoration is performed in a local build-then-swap manner to avoid
          partial updates if an error occurs mid-way.
        """
        try:
            # Rebuild ditamap
            if snap.ditamap_xml is not None:
                new_map_root = ET.fromstring(snap.ditamap_xml)
            else:
                new_map_root = None  # type: ignore[assignment]

            # Rebuild topics
            new_topics: Dict[str, ET.Element] = {}
            for name, xml_bytes in snap.topics_xml.items():
                new_topics[name] = ET.fromstring(xml_bytes)

            # Prepare new images/metadata
            new_images: Dict[str, bytes] = dict(snap.images)
            new_metadata: Dict[str, Any] = dict(snap.metadata)

            # If everything parsed fine, swap into the context atomically
            context.ditamap_root = new_map_root
            context.topics = new_topics
            context.images = new_images
            context.metadata = new_metadata

            return True
        except Exception:
            # Gracefully fail and keep existing context unmodified when possible.
            return False