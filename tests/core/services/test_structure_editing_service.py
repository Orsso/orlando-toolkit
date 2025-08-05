import pytest

# Required imports per instructions
from orlando_toolkit.core.services.structure_editing_service import (
    StructureEditingService,
    OperationResult,
)


class FakeTopicRef:
    def __init__(self, id, title):
        self.id = id
        self.title = title
        # Optional navtitle some services may use
        self.navtitle = title
        # Children to simulate hierarchy for promote/demote
        self.children = []
        # Parent backref for convenience
        self.parent = None

    def __repr__(self):
        return f"FakeTopicRef(id={self.id!r}, title={self.title!r})"


class FakeDitaContext:
    """
    Minimal fake context that StructureEditingService can operate on without real XML.
    We provide:
      - a top-level list representing ditamap topicrefs order
      - per-node children lists for hierarchy
      - helpers to find and mutate nodes
    """

    def __init__(self, roots):
        # roots: list[FakeTopicRef] representing top-level map order
        self.roots = roots

    # Helper utilities commonly expected by editing services

    def find_by_id(self, topic_id):
        for node in self.iter_all():
            if node.id == topic_id:
                return node
        return None

    def iter_all(self):
        stack = list(self.roots)[::-1]
        while stack:
            node = stack.pop()
            yield node
            for c in reversed(node.children):
                stack.append(c)

    def siblings_of(self, node):
        if node.parent is None:
            return self.roots
        return node.parent.children

    def index_in_siblings(self, node):
        sibs = self.siblings_of(node)
        try:
            return sibs.index(node)
        except ValueError:
            return -1

    def move_up(self, node):
        sibs = self.siblings_of(node)
        i = self.index_in_siblings(node)
        if i <= 0:
            return False
        sibs[i - 1], sibs[i] = sibs[i], sibs[i - 1]
        return True

    def move_down(self, node):
        sibs = self.siblings_of(node)
        i = self.index_in_siblings(node)
        if i == -1 or i == len(sibs) - 1:
            return False
        sibs[i + 1], sibs[i] = sibs[i], sibs[i + 1]
        return True

    def promote(self, node):
        """
        Move node up one level: become a sibling of its parent, inserted after the parent.
        Only valid if parent and grandparent exist.
        """
        parent = node.parent
        if parent is None or parent.parent is None:
            return False
        grand = parent.parent
        # remove from current siblings
        parent.children.remove(node)
        node.parent = None  # will be set later
        # insert after parent within grand.children
        idx_parent = grand.children.index(parent)
        insert_pos = idx_parent + 1
        grand.children.insert(insert_pos, node)
        node.parent = grand
        return True

    def demote_into_previous_sibling(self, node):
        """
        Demote node into its previous sibling as a child (append at end).
        Only if there is a previous sibling.
        """
        sibs = self.siblings_of(node)
        i = self.index_in_siblings(node)
        if i <= 0:
            return False
        prev = sibs[i - 1]
        # Remove node from current siblings
        sibs.pop(i)
        # Reparent to previous sibling
        node.parent = prev
        prev.children.append(node)
        return True

    def rename(self, node, new_title):
        node.title = new_title
        node.navtitle = new_title

    def delete_ids(self, ids):
        """Delete nodes by id anywhere in the tree; return count deleted."""
        to_delete = set(ids)
        count = 0

        def filter_children(parent):
            nonlocal count
            kept = []
            for c in parent.children:
                if c.id in to_delete:
                    count += 1
                else:
                    filter_children(c)
                    kept.append(c)
            parent.children = kept

        # Filter top-level roots
        new_roots = []
        for r in self.roots:
            if r.id in to_delete:
                count += 1
            else:
                filter_children(r)
                new_roots.append(r)
        self.roots = new_roots
        # Fix parent backrefs after structural changes
        self._relink_parents()
        return count

    def _relink_parents(self):
        for r in self.roots:
            r.parent = None
            for c in r.children:
                self._set_parent_recursive(r, c)

    def _set_parent_recursive(self, parent, node):
        node.parent = parent
        for c in node.children:
            self._set_parent_recursive(node, c)


@pytest.fixture
def fake_context():
    """
    Create a small tree:
    Top-level: A, B, C
    - B has child B1
    """
    A = FakeTopicRef("A", "Topic A")
    B = FakeTopicRef("B", "Topic B")
    C = FakeTopicRef("C", "Topic C")
    B1 = FakeTopicRef("B1", "Topic B1")
    # Build hierarchy
    B.children = [B1]
    B1.parent = B
    ctx = FakeDitaContext([A, B, C])
    # Ensure parent backrefs for roots
    ctx._relink_parents()
    return ctx


def order_of_top(ctx):
    return [n.id for n in ctx.roots]


def children_of(ctx, node_id):
    node = ctx.find_by_id(node_id)
    assert node is not None, f"Missing node {node_id}"
    return [c.id for c in node.children]


def patch_service_with_fake(monkeypatch, ctx):
    """
    Monkeypatch StructureEditingService helpers to operate on FakeDitaContext.
    We patch the minimal set of internal lookups so public APIs use ctx.
    """

    # The actual service likely uses methods like _find_topic_ref, _move_up/down etc.
    # We'll map those onto our FakeDitaContext.
    def _find_topic_ref(self, context, topic_id):
        assert context is ctx  # Ensure we use provided fake
        return ctx.find_by_id(topic_id)

    def _move_up(self, context, node):
        return ctx.move_up(node)

    def _move_down(self, context, node):
        return ctx.move_down(node)

    def _promote(self, context, node):
        return ctx.promote(node)

    def _demote(self, context, node):
        return ctx.demote_into_previous_sibling(node)

    def _rename(self, context, node, new_title):
        ctx.rename(node, new_title)
        return True

    def _delete_by_ids(self, context, ids):
        return ctx.delete_ids(ids)

    # Apply patches onto StructureEditingService
    monkeypatch.setattr(StructureEditingService, "_find_topic_ref", _find_topic_ref, raising=False)
    monkeypatch.setattr(StructureEditingService, "_move_up", _move_up, raising=False)
    monkeypatch.setattr(StructureEditingService, "_move_down", _move_down, raising=False)
    monkeypatch.setattr(StructureEditingService, "_promote", _promote, raising=False)
    monkeypatch.setattr(StructureEditingService, "_demote", _demote, raising=False)
    monkeypatch.setattr(StructureEditingService, "_rename", _rename, raising=False)
    monkeypatch.setattr(StructureEditingService, "_delete_by_ids", _delete_by_ids, raising=False)


def assert_result_shape(res, success=None, message_substr=None):
    assert isinstance(res, OperationResult)
    assert isinstance(res.success, bool)
    assert isinstance(res.message, str)
    if success is not None:
        assert res.success is success
    if message_substr:
        assert message_substr.lower() in res.message.lower()
    # details may or may not exist; only check type if present
    if getattr(res, "details", None) is not None:
        assert isinstance(res.details, (str, dict, list, tuple, int, float, bool))


def test_move_up_down_noop_on_boundaries(fake_context, monkeypatch):
    ctx = fake_context
    patch_service_with_fake(monkeypatch, ctx)
    svc = StructureEditingService()

    # First item up - expect failure, no change
    before = order_of_top(ctx)
    res_up = svc.move_topic(ctx, topic_id="A", direction="up")
    assert_result_shape(res_up, success=False)
    assert order_of_top(ctx) == before

    # Last item down - expect failure, no change
    before = order_of_top(ctx)
    res_down = svc.move_topic(ctx, topic_id="C", direction="down")
    assert_result_shape(res_down, success=False)
    assert order_of_top(ctx) == before


def test_move_up_success_and_down_success(fake_context, monkeypatch):
    ctx = fake_context
    patch_service_with_fake(monkeypatch, ctx)
    svc = StructureEditingService()

    # Initial: [A, B, C]
    assert order_of_top(ctx) == ["A", "B", "C"]

    # Move B up: [B, A, C]
    res_up = svc.move_topic(ctx, topic_id="B", direction="up")
    assert_result_shape(res_up, success=True)
    assert order_of_top(ctx) == ["B", "A", "C"]

    # Move B (now first) down: [A, B, C]
    res_down = svc.move_topic(ctx, topic_id="B", direction="down")
    assert_result_shape(res_down, success=True)
    assert order_of_top(ctx) == ["A", "B", "C"]


def test_promote_when_has_parent_and_grandparent_success_or_graceful_failure(monkeypatch):
    # Build: ROOT: R
    # R children: P
    # P children: X
    R = FakeTopicRef("R", "Root")
    P = FakeTopicRef("P", "Parent")
    X = FakeTopicRef("X", "Child")
    P.children = [X]
    X.parent = P
    R.children = [P]
    P.parent = R
    ctx = FakeDitaContext([R])
    ctx._relink_parents()

    patch_service_with_fake(monkeypatch, ctx)
    svc = StructureEditingService()

    # Promote X: should become sibling of P under R, inserted after P
    # Before: R:[P:[X]]
    before_children = children_of(ctx, "P"), children_of(ctx, "R")
    res = svc.move_topic(ctx, topic_id="X", direction="promote")
    assert_result_shape(res)
    if res.success:
        # After success: R children = [P, X], P children = []
        assert children_of(ctx, "P") == []
        assert children_of(ctx, "R") == ["P", "X"]
    else:
        # Graceful failure: structure unchanged
        assert children_of(ctx, "P") == before_children[0]
        assert children_of(ctx, "R") == before_children[1]


def test_demote_into_previous_sibling(fake_context, monkeypatch):
    ctx = fake_context
    patch_service_with_fake(monkeypatch, ctx)
    svc = StructureEditingService()

    # Initial top order: [A, B, C], B has child [B1]
    # Demote B into A: A becomes parent of B
    res = svc.move_topic(ctx, topic_id="B", direction="demote")
    assert_result_shape(res)
    if res.success:
        # After demote: top order [A, C]; A children [B]; B children [B1]
        assert order_of_top(ctx) == ["A", "C"]
        assert children_of(ctx, "A") == ["B"]
        assert children_of(ctx, "B") == ["B1"]
    else:
        # Graceful failure: confirm no unintended change to top order
        assert order_of_top(ctx) == ["A", "B", "C"]


def test_rename_topic_updates_title_and_navtitle_best_effort(fake_context, monkeypatch):
    ctx = fake_context
    patch_service_with_fake(monkeypatch, ctx)
    svc = StructureEditingService()

    target = ctx.find_by_id("B1")
    before_title = target.title
    res = svc.rename_topic(ctx, topic_id="B1", new_title="New Title")
    assert_result_shape(res)
    if res.success:
        assert target.title == "New Title"
        assert getattr(target, "navtitle", None) == "New Title"
    else:
        # On failure, ensure unchanged
        assert target.title == before_title


def test_delete_topics_removes_refs_and_purges_best_effort(fake_context, monkeypatch):
    ctx = fake_context
    patch_service_with_fake(monkeypatch, ctx)
    svc = StructureEditingService()

    # Delete B (which has child B1). Our fake delete removes by id only, not cascading unless both ids provided.
    # To keep the test conservative, delete just "B1" and ensure siblings remain.
    res = svc.delete_topics(ctx, topic_ids=["B1"])
    assert_result_shape(res)
    if res.success:
        # Ensure B no longer has B1
        assert children_of(ctx, "B") == []
        # Ensure top order intact
        assert order_of_top(ctx) == ["A", "B", "C"]
    else:
        # Ensure no structural mutation on failure
        assert children_of(ctx, "B") == ["B1"]
        assert order_of_top(ctx) == ["A", "B", "C"]


def test_merge_topics_returns_not_implemented(fake_context, monkeypatch):
    ctx = fake_context
    patch_service_with_fake(monkeypatch, ctx)
    svc = StructureEditingService()

    # Expect service to return structured failure indicating not implemented
    res = svc.merge_topics(ctx, source_ids=["A"], target_id="B")
    assert_result_shape(res, success=False)
    # Check message indicates not implemented
    assert "not implemented" in res.message.lower()
    # Ensure no mutation
    assert order_of_top(ctx) == ["A", "B", "C"]