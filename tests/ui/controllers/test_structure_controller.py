import pytest
from typing import List, Dict, Optional

from orlando_toolkit.ui.controllers.structure_controller import StructureController
from orlando_toolkit.core.services.structure_editing_service import OperationResult
from orlando_toolkit.core.services.preview_service import PreviewResult


# ---------------------------
# Fakes / Mocks
# ---------------------------

class FakeContext:
    """
    Minimal fake DitaContext-like object exposing attributes that StructureController
    attempts to access in handle_search and for undo/preview delegation.
    """
    def __init__(self, topics: Optional[Dict[str, object]] = None, topic_refs: Optional[List[str]] = None):
        # Simulate common attributes the controller might probe:
        # topics: dict-like {id: ...}
        # topic_refs: list of string ids
        self.topics = topics or {}
        self.topic_refs = topic_refs or []
        self.all_topics = list(self.topics.keys())
        self.all_topic_refs = list(self.topic_refs)
        # Minimal metadata/images placeholders
        self.metadata = {}
        self.images = {}


class FakeEditingService:
    def __init__(self):
        self.calls = []
        # Depth handling tracking
        self.apply_depth_calls = []
        self.apply_depth_result = None  # optional override

    def move_topic(self, context, topic_ref: str, direction: str) -> OperationResult:
        self.calls.append(("move_topic", topic_ref, direction))
        # Return a simple success result
        return OperationResult(success=True, message=f"Moved {topic_ref} {direction}")

    def rename_topic(self, context, topic_ref: str, new_title: str) -> OperationResult:
        self.calls.append(("rename_topic", topic_ref, new_title))
        return OperationResult(success=True, message="Renamed")

    def delete_topics(self, context, topic_refs: List[str]) -> OperationResult:
        self.calls.append(("delete_topics", tuple(topic_refs)))
        return OperationResult(success=True, message="Deleted")

    def merge_topics(self, context, topic_refs: List[str]) -> OperationResult:
        self.calls.append(("merge_topics", tuple(topic_refs)))
        return OperationResult(success=False, message="Not implemented")

    def apply_depth_limit(self, context, depth_limit: int, style_exclusions=None):
        self.apply_depth_calls.append((context, depth_limit, style_exclusions))
        if self.apply_depth_result is not None:
            return self.apply_depth_result
        # Import OperationResult from the SUT module to preserve structure
        from orlando_toolkit.core.services.structure_editing_service import OperationResult
        return OperationResult(True, "ok", {"depth_limit": depth_limit, "merged": True})


class FakeUndoService:
    def __init__(self, can_undo: bool = False, can_redo: bool = False, undo_result: bool = False, redo_result: bool = False):
        self._can_undo = can_undo
        self._can_redo = can_redo
        self._undo_result = undo_result
        self._redo_result = redo_result
        self.counters = {
            "push_snapshot": 0,
            "undo": 0,
            "redo": 0,
            "can_undo": 0,
            "can_redo": 0,
        }

    def push_snapshot(self, context) -> None:
        self.counters["push_snapshot"] += 1

    def undo(self, context) -> bool:
        self.counters["undo"] += 1
        return self._undo_result

    def redo(self, context) -> bool:
        self.counters["redo"] += 1
        return self._redo_result

    def can_undo(self) -> bool:
        self.counters["can_undo"] += 1
        return self._can_undo

    def can_redo(self) -> bool:
        self.counters["can_redo"] += 1
        return self._can_redo


class FakePreviewService:
    def __init__(self):
        self.calls = []

    def compile_preview(self, context, topic_ref: str) -> PreviewResult:
        self.calls.append(("compile_preview", topic_ref))
        return PreviewResult(success=True, content="<xml/>", message="ok")

    def render_html_preview(self, context, topic_ref: str) -> PreviewResult:
        self.calls.append(("render_html_preview", topic_ref))
        return PreviewResult(success=True, content="<html/>", message="ok")


# ---------------------------
# Fixtures
# ---------------------------

@pytest.fixture
def controller():
    ctx = FakeContext(
        topics={"A": object(), "B": object()},
        topic_refs=["topics/A.dita", "topics/B.dita", "misc/C"]
    )
    editing = FakeEditingService()
    undo = FakeUndoService()
    preview = FakePreviewService()
    return StructureController(ctx, editing, undo, preview)


# ---------------------------
# Test cases
# ---------------------------

def test_handle_depth_change_clamps_and_updates(controller):
    # Default max_depth initialized to 999 in controller
    # 0 should clamp to 1, and update from 999 -> 1
    # Also should delegate to editing.apply_depth_limit and push undo snapshot
    fake_editing: FakeEditingService = controller.editing_service  # type: ignore[attr-defined]
    fake_undo: FakeUndoService = controller.undo_service  # type: ignore[attr-defined]

    changed = controller.handle_depth_change(0)
    assert changed is True
    assert controller.max_depth == 1
    # Undo snapshot pushed before service call (we only assert at least one push)
    assert fake_undo.counters["push_snapshot"] >= 1
    # Service delegated exactly once with clamped depth
    assert len(fake_editing.apply_depth_calls) == 1
    _, depth_arg, _ = fake_editing.apply_depth_calls[0]
    assert depth_arg == 1

    # 1 from current 1 -> not changed, no delegation
    changed_same = controller.handle_depth_change(1)
    assert changed_same is False
    assert controller.max_depth == 1
    assert len(fake_editing.apply_depth_calls) == 1  # still one call
    pushes_after_same = fake_undo.counters["push_snapshot"]

    # 5 from current 1 -> changed and delegated again
    changed_to_5 = controller.handle_depth_change(5)
    assert changed_to_5 is True
    assert controller.max_depth == 5
    assert len(fake_editing.apply_depth_calls) == 2
    _, depth_arg2, _ = fake_editing.apply_depth_calls[-1]
    assert depth_arg2 == 5
    assert fake_undo.counters["push_snapshot"] >= pushes_after_same + 1


def test_select_and_get_selection_uniqueness(controller):
    # Provide duplicates and invalid entries
    controller.select_items(["ref1", "ref2", "ref1", "", None, "ref3", "ref2"])  # type: ignore[arg-type]
    assert controller.get_selection() == ["ref1", "ref2", "ref3"]

    # Non-list input clears selection
    controller.select_items("not-a-list")  # type: ignore[arg-type]
    assert controller.get_selection() == []


def test_move_operation_without_selection_returns_failure():
    ctx = FakeContext()
    editing = FakeEditingService()
    undo = FakeUndoService()
    preview = FakePreviewService()
    c = StructureController(ctx, editing, undo, preview)

    # No selection -> should fail without calling services
    res = c.handle_move_operation("up")
    assert isinstance(res, OperationResult)
    assert res.success is False
    assert "No selection" in res.message
    # Ensure no snapshot pushed and no editing call
    assert undo.counters["push_snapshot"] == 0
    assert [call for call in editing.calls if call[0] == "move_topic"] == []


def test_move_operation_with_selection_pushes_snapshot_and_delegates():
    ctx = FakeContext()
    editing = FakeEditingService()
    undo = FakeUndoService()
    preview = FakePreviewService()
    c = StructureController(ctx, editing, undo, preview)

    # Select multiple; only first should be used
    c.select_items(["topics/A.dita", "topics/B.dita"])
    res = c.handle_move_operation("up")

    assert isinstance(res, OperationResult)
    assert res.success is True

    # Snapshot pushed once
    assert undo.counters["push_snapshot"] == 1

    # Editing service called with first selected ref and direction
    move_calls = [call for call in editing.calls if call[0] == "move_topic"]
    assert len(move_calls) == 1
    _, ref, direction = move_calls[0]
    assert ref == "topics/A.dita"
    assert direction == "up"


def test_search_updates_state_and_returns_results():
    # Prepare a context with various attributes to be probed
    ctx = FakeContext(
        topics={"A": object(), "BTopic": object(), "ref-xyz": object()},
        topic_refs=["A", "BTopic", "misc-C", "ref-xyz", "A"]  # includes duplicates
    )
    c = StructureController(ctx, FakeEditingService(), FakeUndoService(), FakePreviewService())

    results = c.handle_search("ref")
    assert c.search_term == "ref"
    assert isinstance(results, list)
    # Expect only items that include "ref" (case-insensitive), deduped
    assert "ref-xyz" in results
    # Ensure deduped unique order preserved by controller's logic
    # We do not assert exact full order beyond inclusion and dedup characteristic
    assert len(results) == len(set(results))

    # Empty search clears results but persists blank term
    results_empty = c.handle_search("")
    assert c.search_term == ""
    assert results_empty == []


def test_filter_toggle_updates_mapping(controller):
    # Enabled=False -> excluded=True
    m = controller.handle_filter_toggle("Heading1", enabled=False)
    assert isinstance(m, dict)
    assert m.get("Heading1") is True

    # Enabled=True -> excluded=False
    m2 = controller.handle_filter_toggle("Heading2", enabled=True)
    assert m2.get("Heading2") is False

    # Toggling another again
    m3 = controller.handle_filter_toggle("Heading1", enabled=True)
    assert m3.get("Heading1") is False

    # Invalid style string should no-op and return the same mapping
    before = dict(controller.heading_filter_exclusions)
    m4 = controller.handle_filter_toggle("", enabled=True)
    assert m4 == before


def test_undo_redo_delegation_and_returns():
    ctx = FakeContext()
    editing = FakeEditingService()
    # Configure undo service to report available and return True on actions
    undo = FakeUndoService(can_undo=True, can_redo=True, undo_result=True, redo_result=True)
    preview = FakePreviewService()
    c = StructureController(ctx, editing, undo, preview)

    # can_undo/can_redo reflect fake
    assert c.can_undo() is True
    assert c.can_redo() is True
    assert undo.counters["can_undo"] == 1
    assert undo.counters["can_redo"] == 1

    # undo/redo delegate and return booleans
    assert c.undo() is True
    assert c.redo() is True
    assert undo.counters["undo"] == 1
    assert undo.counters["redo"] == 1


def test_compile_and_render_preview_delegate():
    ctx = FakeContext()
    editing = FakeEditingService()
    undo = FakeUndoService()
    preview = FakePreviewService()
    c = StructureController(ctx, editing, undo, preview)

    # With selection set, None/empty provided uses first selection per controller logic
    c.select_items(["topics/Selected.dita", "topics/Other.dita"])

    # compile_preview with falsy parameter -> use selected
    res_compile_default = c.compile_preview("")  # falsy string
    assert isinstance(res_compile_default, PreviewResult)
    assert res_compile_default.success is True
    assert preview.calls and preview.calls[-1] == ("compile_preview", "topics/Selected.dita")

    # render_html_preview with falsy parameter -> use selected
    res_render_default = c.render_html_preview(None)  # type: ignore[arg-type]
    assert isinstance(res_render_default, PreviewResult)
    assert res_render_default.success is True
    assert preview.calls and preview.calls[-1] == ("render_html_preview", "topics/Selected.dita")

    # Now call with explicit ref; should override selection
    res_compile_explicit = c.compile_preview("topics/Explicit.dita")
    assert res_compile_explicit.success is True
    assert preview.calls and preview.calls[-1] == ("compile_preview", "topics/Explicit.dita")

    res_render_explicit = c.render_html_preview("topics/Explicit2.dita")
    assert res_render_explicit.success is True
    assert preview.calls and preview.calls[-1] == ("render_html_preview", "topics/Explicit2.dita")
    
    
    def test_handle_depth_change_service_failure_returns_false():
        ctx = FakeContext()
        fake_editing = FakeEditingService()
        # Configure failure result
        from orlando_toolkit.core.services.structure_editing_service import OperationResult as _Op
        fake_editing.apply_depth_result = _Op(False, "err", {"x": 1})
        fake_undo = FakeUndoService()
        preview = FakePreviewService()
        c = StructureController(ctx, fake_editing, fake_undo, preview)
    
        # initial depth default 999, change to 3 triggers service failure -> return False and do not update
        before = c.max_depth
        changed = c.handle_depth_change(3)
        assert changed is False
        assert c.max_depth == before
    
    
    def test_handle_depth_change_no_change_no_service_call():
        ctx = FakeContext()
        fake_editing = FakeEditingService()
        fake_undo = FakeUndoService()
        preview = FakePreviewService()
        c = StructureController(ctx, fake_editing, fake_undo, preview)
    
        # Set initial value
        c.max_depth = 4
        # Calling with same value should no-op
        changed = c.handle_depth_change(4)
        assert changed is False
        assert fake_editing.apply_depth_calls == []
        assert fake_undo.counters["push_snapshot"] == 0
    
    
    def test_handle_depth_change_with_style_exclusions_mapping():
        ctx = FakeContext()
        fake_editing = FakeEditingService()
        fake_undo = FakeUndoService()
        preview = FakePreviewService()
        c = StructureController(ctx, fake_editing, fake_undo, preview)
    
        # Set exclusions; minimal mapping expectation allowed
        c.heading_filter_exclusions = {"Heading 2": True, "Heading 3": False, "Title": True}
        c.max_depth = 2
        changed = c.handle_depth_change(3)
        assert changed is True
    
        # Either None or specific mapping is acceptable depending on controller implementation
        assert len(fake_editing.apply_depth_calls) == 1
        _, depth_arg, style_excl = fake_editing.apply_depth_calls[0]
        assert depth_arg == 3
        if style_excl is not None:
            assert style_excl == {1: {"Heading 2", "Title"}}
    
    
    def test_handle_depth_change_undo_snapshot_failure_is_non_fatal(monkeypatch):
        ctx = FakeContext()
        fake_editing = FakeEditingService()
        fake_undo = FakeUndoService()
        preview = FakePreviewService()
        c = StructureController(ctx, fake_editing, fake_undo, preview)
    
        # Force undo push_snapshot to raise
        def _raise(_ctx):
            raise RuntimeError("boom")
        monkeypatch.setattr(fake_undo, "push_snapshot", _raise)
    
        # Operation should still proceed and return True when service succeeds
        c.max_depth = 2
        changed = c.handle_depth_change(4)
        assert changed is True
        assert len(fake_editing.apply_depth_calls) == 1