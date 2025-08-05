import os
import sys
import tkinter as tk
import pytest

from orlando_toolkit.ui.widgets.structure_tree import StructureTreeWidget


def _can_create_tk_root() -> bool:
    try:
        r = tk.Tk()
        r.destroy()
        return True
    except tk.TclError:
        return False


pytestmark = pytest.mark.skipif(
    not _can_create_tk_root(),
    reason="Tkinter root cannot be created in this environment (likely headless CI without display).",
)


class FakeDitaContext:
    """
    Minimal fake context to exercise populate_tree fallback behavior.

    We deliberately do NOT provide map_root and NOT provide a traversable structure
    so that StructureTreeWidget.populate_tree falls back to listing topics (lines 137-156 in widget).
    """

    def __init__(self, title=None, root_ref=None, topics=None):
        self.title = title  # optional, widget will default to "Root" if None
        self.root_ref = root_ref  # optional mapping to root item ref
        # Fallback path prefers 'topics' (line 140)
        # Provide as dict[str, dict] with 'title' and 'ref'
        self.topics = topics or {}


@pytest.fixture
def tk_root():
    root = tk.Tk()
    # Avoid showing a window during tests
    root.withdraw()
    yield root
    # Ensure proper teardown
    try:
        root.update_idletasks()
    except Exception:
        pass
    root.destroy()


@pytest.fixture
def callback_recorder():
    class Recorder:
        def __init__(self):
            self.selection_calls = []
            self.activation_calls = []
            self.context_calls = []

        def on_sel(self, refs):
            self.selection_calls.append(list(refs))

        def on_act(self, ref):
            self.activation_calls.append(ref)

        def on_ctx(self, event, refs):
            # Record event widget class and refs for light assertion
            self.context_calls.append((event.__class__.__name__, list(refs)))

    return Recorder()


@pytest.fixture
def widget(tk_root, callback_recorder):
    w = StructureTreeWidget(
        tk_root,
        on_selection_changed=callback_recorder.on_sel,
        on_item_activated=callback_recorder.on_act,
        on_context_menu=callback_recorder.on_ctx,
    )
    # Geometry management for event coordinate calculations
    w.pack(fill="both", expand=True)
    tk_root.update_idletasks()
    return w


def make_context_with_ids(ids):
    """
    Build a FakeDitaContext whose topics dict contains entries for provided ids.
    """
    topics = {ref: {"title": ref, "ref": ref} for ref in ids}
    return FakeDitaContext(title="Test Root", root_ref=None, topics=topics)


def get_item_bbox_y(tree: tk.Widget, item_id: str) -> int:
    """
    Helper to compute a y coordinate within the row bounding box of a given item.
    """
    bbox = tree.bbox(item_id)
    # bbox: (x, y, width, height) in pixels; pick vertical middle
    if not bbox:
        # Force update and try again
        tree.update_idletasks()
        bbox = tree.bbox(item_id)
    assert bbox, "Treeview bbox for item not available"
    return bbox[1] + bbox[3] // 2


def get_item_id_for_ref(widget: StructureTreeWidget, ref: str) -> str:
    item_id = widget.find_item_by_ref(ref)
    assert item_id is not None, f"Expected item id for ref {ref}"
    return item_id


def test_populate_tree_creates_items_and_maps_refs(widget):
    # Given a fake context with A, B, C, no map_root and no structure
    ctx = make_context_with_ids(["A", "B", "C"])

    # When
    widget.populate_tree(ctx)
    widget.update()  # flush geometry for bbox availability

    # Then: find_item_by_ref returns an item id for each
    for ref in ["A", "B", "C"]:
        item_id = widget.find_item_by_ref(ref)
        assert isinstance(item_id, str) and item_id, f"Item id for {ref} should exist"

    # And initially selection is empty
    assert widget.get_selected_items() == []


def test_update_selection_and_get_selected_items_roundtrip(widget, callback_recorder):
    ctx = make_context_with_ids(["A", "B", "C"])
    widget.populate_tree(ctx)
    widget.update()

    # When: update selection to B and C
    widget.update_selection(["B", "C"])
    widget.update()

    # The widget fires callbacks on the <<TreeviewSelect>> virtual event; generate it if needed
    widget.event_generate("<<TreeviewSelect>>")
    widget.update()

    selected = widget.get_selected_items()
    # Order-insensitive check
    assert set(selected) == {"B", "C"}
    # Callback invoked with the same set
    assert callback_recorder.selection_calls, "Selection callback should have been invoked"
    assert set(callback_recorder.selection_calls[-1]) == {"B", "C"}


def test_find_item_by_ref_returns_none_for_missing(widget):
    ctx = make_context_with_ids(["A", "B", "C"])
    widget.populate_tree(ctx)
    widget.update()

    assert widget.find_item_by_ref("Z") is None


def test_activation_callback_on_double_click_invoked_with_item_ref(widget, callback_recorder, tk_root):
    ctx = make_context_with_ids(["A", "B", "C"])
    widget.populate_tree(ctx)
    widget.update()

    # Select B and focus it
    b_id = get_item_id_for_ref(widget, "B")
    # Focus and ensure visible
    widget._tree.focus(b_id)
    widget._tree.selection_set((b_id,))
    tk_root.update_idletasks()

    # Compute y coordinate within B's row and synthesize double-click
    y = get_item_bbox_y(widget._tree, b_id)
    widget._tree.event_generate("<Double-1>", x=5, y=y)
    widget.update()

    # Assert activation callback received 'B'
    assert callback_recorder.activation_calls, "Activation callback should have been invoked"
    assert callback_recorder.activation_calls[-1] == "B"


def test_context_menu_callback_receives_event_and_selection(widget, callback_recorder, tk_root):
    ctx = make_context_with_ids(["A", "B", "C"])
    widget.populate_tree(ctx)
    widget.update()

    # Select A
    a_id = get_item_id_for_ref(widget, "A")
    widget._tree.focus(a_id)
    widget._tree.selection_set((a_id,))
    tk_root.update_idletasks()

    # Right-click on A row
    y = get_item_bbox_y(widget._tree, a_id)
    widget._tree.event_generate("<Button-3>", x=5, y=y)
    widget.update()

    # Assert context menu callback invoked with event and ['A']
    assert callback_recorder.context_calls, "Context menu callback should have been invoked"
    last_event_class, refs = callback_recorder.context_calls[-1]
    assert isinstance(last_event_class, str) and last_event_class, "Event class name should be captured"
    assert refs == ["A"]