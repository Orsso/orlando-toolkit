from __future__ import annotations

"""Edit journaling model for structural edits.

This module defines a minimal, UI-agnostic, in-memory journal for structural
editing operations that can be recorded during a session and later replayed
against a rebuilt DitaContext.

Scope:
- Pure core model (no I/O, no UI).
- Conservative and robust: failures during replay are collected, not raised.
- JSON-serializable serialization format for persistence by callers.

Supported operations (initial set):
- "move":   {"topic_ref": str, "direction": Literal["up", "down", "promote", "demote"]}
- "rename": {"topic_ref": str, "new_title": str}
- "delete": {"topic_refs": List[str]}
- "merge":  {"topic_refs": List[str]}

Dispatch is delegated to StructureEditingService methods:
- move      -> StructureEditingService.move_topic
- rename    -> StructureEditingService.rename_topic
- delete    -> StructureEditingService.delete_topics
- merge     -> StructureEditingService.merge_topics
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, TypedDict
from typing import TYPE_CHECKING

import time

from orlando_toolkit.core.models import DitaContext

if TYPE_CHECKING:
    # Import only for type checking to avoid runtime circular import
    from orlando_toolkit.core.services.structure_editing_service import StructureEditingService

# Optional typed payloads for common operations (helpers for type hints only)
class MoveEntry(TypedDict):
    topic_ref: str
    direction: Literal["up", "down", "promote", "demote"]


class RenameEntry(TypedDict):
    topic_ref: str
    new_title: str


class DeleteEntry(TypedDict):
    topic_refs: List[str]


class MergeEntry(TypedDict):
    topic_refs: List[str]


@dataclass
class JournalEntry:
    """Single journal entry representing one structural edit.

    Attributes
    ----------
    operation
        Operation kind, one of: "move", "rename", "delete", "merge".
    details
        Operation-specific payload. Must be JSON-serializable.
    timestamp
        Unix epoch seconds when the entry was recorded.
    """
    operation: str
    details: Dict[str, Any]
    timestamp: float


class EditJournal:
    """In-memory journal of structural edits with record/replay capabilities.

    The journal accumulates edits as JournalEntry records and can replay them
    against a DitaContext using a provided StructureEditingService instance.

    Notes
    -----
    - This class does not perform any persistence or I/O. Callers are responsible
      for saving/loading serialized data.
    - Replay is resilient: routine errors are swallowed and collected in a report.
    """

    def __init__(self) -> None:
        """Initialize an empty edit journal."""
        self._entries: List[JournalEntry] = []

    def record_edit(self, operation: str, details: Dict[str, Any]) -> None:
        """Record a new edit entry with current timestamp.

        Parameters
        ----------
        operation
            Operation kind. Expected values: "move", "rename", "delete", "merge".
        details
            Operation-specific payload. Must be JSON-serializable.

        Notes
        -----
        This method does not validate the payload shape beyond basic type assumptions.
        Validation occurs during replay when dispatching to the service.
        """
        entry = JournalEntry(operation=operation, details=dict(details), timestamp=time.time())
        self._entries.append(entry)

    def replay_edits(self, context: DitaContext, editing_service: "StructureEditingService") -> Dict[str, Any]:
        """Replay all recorded edits against the given DitaContext.

        Parameters
        ----------
        context
            Target DitaContext to apply edits to.
        editing_service
            Service providing structural operations. Must implement:
            - move_topic(context, topic_ref, direction)
            - rename_topic(context, topic_ref, new_title)
            - delete_topics(context, topic_refs)
            - merge_topics(context, topic_refs)

        Returns
        -------
        dict
            Structured report:
            {
              "applied": int,   # number of edits successfully applied
              "skipped": int,   # number of edits that were skipped or failed
              "errors": List[str],  # collected error messages
            }

        Behavior
        --------
        - Iterates entries in order.
        - For each entry, dispatches to the corresponding service method.
        - Does not raise for routine errors; collects messages and continues.
        - Counts as applied only if the service returns success=True.
        """
        applied = 0
        skipped = 0
        errors: List[str] = []

        for idx, entry in enumerate(self._entries):
            op = entry.operation
            details = entry.details
            try:
                if op == "move":
                    # Expect: {"topic_ref": str, "direction": Literal["up","down","promote","demote"]}
                    topic_ref = _safe_str(details.get("topic_ref"))
                    direction = _safe_str(details.get("direction"))
                    if not topic_ref or direction not in ("up", "down", "promote", "demote"):
                        skipped += 1
                        errors.append(f"[{idx}] move: invalid payload {details!r}")
                        continue
                    result = editing_service.move_topic(context, topic_ref, direction)  # type: ignore[attr-defined]
                    if getattr(result, "success", False):
                        applied += 1
                    else:
                        skipped += 1
                        msg = getattr(result, "message", "Unknown error")
                        errors.append(f"[{idx}] move failed: {msg}")

                elif op == "rename":
                    # Expect: {"topic_ref": str, "new_title": str}
                    topic_ref = _safe_str(details.get("topic_ref"))
                    new_title = _safe_str(details.get("new_title"))
                    if not topic_ref or not new_title:
                        skipped += 1
                        errors.append(f"[{idx}] rename: invalid payload {details!r}")
                        continue
                    result = editing_service.rename_topic(context, topic_ref, new_title)  # type: ignore[attr-defined]
                    if getattr(result, "success", False):
                        applied += 1
                    else:
                        skipped += 1
                        msg = getattr(result, "message", "Unknown error")
                        errors.append(f"[{idx}] rename failed: {msg}")

                elif op == "delete":
                    # Expect: {"topic_refs": List[str]}
                    topic_refs = details.get("topic_refs")
                    if not isinstance(topic_refs, list) or not all(isinstance(x, str) for x in topic_refs):
                        skipped += 1
                        errors.append(f"[{idx}] delete: invalid payload {details!r}")
                        continue
                    result = editing_service.delete_topics(context, topic_refs)  # type: ignore[attr-defined]
                    if getattr(result, "success", False):
                        applied += 1
                    else:
                        skipped += 1
                        msg = getattr(result, "message", "Unknown error")
                        errors.append(f"[{idx}] delete failed: {msg}")

                elif op == "merge":
                    # Expect: {"topic_refs": List[str]}
                    topic_refs = details.get("topic_refs")
                    if not isinstance(topic_refs, list) or not all(isinstance(x, str) for x in topic_refs):
                        skipped += 1
                        errors.append(f"[{idx}] merge: invalid payload {details!r}")
                        continue
                    result = editing_service.merge_topics(context, topic_refs)  # type: ignore[attr-defined]
                    if getattr(result, "success", False):
                        applied += 1
                    else:
                        skipped += 1
                        msg = getattr(result, "message", "Unknown error")
                        errors.append(f"[{idx}] merge failed: {msg}")

                else:
                    skipped += 1
                    errors.append(f"[{idx}] unsupported operation '{op}'")

            except Exception as exc:
                # Routine exceptions are swallowed; collect error and continue.
                skipped += 1
                errors.append(f"[{idx}] {op} exception: {exc}")

        return {"applied": applied, "skipped": skipped, "errors": errors}

    def clear_journal(self) -> None:
        """Remove all entries from the journal."""
        self._entries.clear()

    def serialize(self) -> List[Dict[str, Any]]:
        """Serialize journal entries to a JSON-compatible list of dicts.

        Returns
        -------
        List[Dict[str, Any]]
            Lossless representation of all entries, preserving timestamps.
        """
        data: List[Dict[str, Any]] = []
        for e in self._entries:
            data.append(
                {
                    "operation": e.operation,
                    "details": e.details,
                    "timestamp": e.timestamp,
                }
            )
        return data

    @classmethod
    def deserialize(cls, data: List[Dict[str, Any]]) -> "EditJournal":
        """Create an EditJournal from serialized data.

        Parameters
        ----------
        data
            Serialized list created by serialize().

        Returns
        -------
        EditJournal
            A journal instance. If the input is malformed, an empty journal is returned.
        """
        journal = cls()
        try:
            if not isinstance(data, list):
                return journal
            for item in data:
                if not isinstance(item, dict):
                    continue
                op = item.get("operation")
                details = item.get("details")
                ts = item.get("timestamp")
                if not isinstance(op, str) or not isinstance(details, dict) or not isinstance(ts, (int, float)):
                    continue
                journal._entries.append(JournalEntry(operation=op, details=details, timestamp=float(ts)))
        except Exception:
            # Malformed input: return empty journal per requirements
            return cls()
        return journal


def _safe_str(value: Any) -> str:
    """Return the value if it's a string; otherwise empty string."""
    return value if isinstance(value, str) else ""