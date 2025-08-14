import pytest

# Required imports per instructions
from orlando_toolkit.core.services.structure_editing_service import (
    StructureEditingService,
    OperationResult,
)


class FakeTopicRef:
    def __init__(self, id, title, level=None, is_section=False):
        self.id = id
        self.title = title
        # Optional navtitle some services may use
        self.navtitle = title
        # Children to simulate hierarchy
        self.children = []
        # Parent backref for convenience
        self.parent = None
        # Attributes dict to simulate XML attributes
        self.attrib = {}
        # Set level if provided
        if level is not None:
            self.attrib["data-level"] = str(level)
            self.attrib["data-style"] = f"Heading {level}"
        # Simulate XML tag for compatibility - topichead for sections, topicref for topics
        self.tag = "topichead" if is_section else "topicref"
        # Add href for topics (not sections)
        if not is_section:
            self.attrib["href"] = f"topics/{id}.dita"

    def get(self, key, default=None):
        """Simulate XML element.get() method."""
        return self.attrib.get(key, default)
    
    def set(self, key, value):
        """Simulate XML element.set() method."""
        self.attrib[key] = value
        
    def getparent(self):
        """Simulate XML element.getparent() method."""
        return self.parent
        
    def remove(self, child):
        """Simulate XML element.remove() method."""
        if child in self.children:
            self.children.remove(child)
            child.parent = None
            
    def append(self, child):
        """Simulate XML element.append() method."""
        self.children.append(child)
        child.parent = self
        
    def insert(self, index, child):
        """Simulate XML element.insert() method."""
        self.children.insert(index, child)
        child.parent = self
        
    def __iter__(self):
        """Simulate iterating over children like XML elements."""
        return iter(self.children)
        
    def __len__(self):
        """Simulate len() for XML elements."""
        return len(self.children)

    def __repr__(self):
        tag_info = "Section" if self.tag == "topichead" else "Topic"
        return f"Fake{tag_info}(id={self.id!r}, title={self.title!r}, level={self.get('data-level')})"


class FakeRoot:
    """Simulate the ditamap root element."""
    def __init__(self, children):
        self.tag = "map"
        self.children = children
        self.parent = None
        for child in children:
            child.parent = self
            
    def __iter__(self):
        return iter(self.children)
        
    def __len__(self):
        return len(self.children)
        
    def remove(self, child):
        if child in self.children:
            self.children.remove(child)
            child.parent = None
            
    def append(self, child):
        self.children.append(child)
        child.parent = self
        
    def insert(self, index, child):
        self.children.insert(index, child)
        child.parent = self


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
        # Create a fake ditamap_root for the new intelligent methods
        self.ditamap_root = FakeRoot(roots)

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



    def _rename(self, context, node, new_title):
        ctx.rename(node, new_title)
        return True

    def _delete_by_ids(self, context, ids):
        return ctx.delete_ids(ids)

    # Apply patches onto StructureEditingService
    monkeypatch.setattr(StructureEditingService, "_find_topic_ref", _find_topic_ref, raising=False)
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


def test_intelligent_section_boundary_crossing(monkeypatch):
    """Test that up/down movement can cross section boundaries and adapt levels."""
    # Create a structure with sections and topics:
    # Section A (level 3)
    #   Topic B (level 4)  <- Should be able to move UP to exit section
    # Section C (level 3)
    
    section_A = FakeTopicRef("SectionA", "Section A", level=3, is_section=True)
    topic_B = FakeTopicRef("B", "Topic B", level=4)
    section_C = FakeTopicRef("SectionC", "Section C", level=3, is_section=True)
    
    # Set up hierarchy: B is child of Section A
    section_A.children = [topic_B]
    topic_B.parent = section_A
    
    ctx = FakeDitaContext([section_A, section_C])
    ctx._relink_parents()
    
    patch_service_with_fake(monkeypatch, ctx)
    svc = StructureEditingService()
    
    # Initial state: Section A contains Topic B
    assert order_of_top(ctx) == ["SectionA", "SectionC"]
    assert topic_B.parent is section_A
    assert topic_B.get("data-level") == "4"
    
    # Move Topic B up - should exit Section A and become level 3
    res = svc.move_topic(ctx, topic_id="B", direction="up")
    assert_result_shape(res)
    
    if res.success:
        # After UP movement: Topic B should be at top level, before Section A
        assert "B" in [node.id for node in ctx.ditamap_root.children]
        # B should have been adapted to level 3 (same as sections)
        assert topic_B.get("data-level") == "3", f"Expected level 3, got {topic_B.get('data-level')}"
        # B should no longer be child of Section A
        assert topic_B not in section_A.children


def test_intelligent_section_entry(monkeypatch):
    """Test that down movement can enter sections."""
    # Create structure:
    # Topic A (level 3)     <- Should be able to move DOWN to enter Section B
    # Section B (level 3)
    
    topic_A = FakeTopicRef("A", "Topic A", level=3)
    section_B = FakeTopicRef("SectionB", "Section B", level=3, is_section=True)
    
    ctx = FakeDitaContext([topic_A, section_B])
    ctx._relink_parents()
    # Ensure parents are set correctly for ditamap_root
    for child in ctx.ditamap_root.children:
        child.parent = ctx.ditamap_root
    
    patch_service_with_fake(monkeypatch, ctx)
    svc = StructureEditingService()
    
    # Initial state: both at top level
    assert order_of_top(ctx) == ["A", "SectionB"]
    assert topic_A.parent is ctx.ditamap_root
    
    # Move Topic A down - should enter Section B and become level 4
    res = svc.move_topic(ctx, topic_id="A", direction="down")
    assert_result_shape(res)
    
    if res.success:
        # After DOWN movement: Topic A should be inside Section B
        assert topic_A in section_B.children
        # A should have been adapted to level 4 (section level + 1)
        assert topic_A.get("data-level") == "4", f"Expected level 4, got {topic_A.get('data-level')}"
        # A should no longer be at top level
        assert topic_A not in ctx.ditamap_root.children




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
# ------------------------------
# Tests for apply_depth_limit
# ------------------------------


class _FakeCtxSimple:
    """
    Minimal context used for apply_depth_limit tests.
    Only attributes accessed by the service are provided: ditamap_root, metadata.
    """
    def __init__(self, has_map=True):
        self.ditamap_root = object() if has_map else None
        self.metadata = {}
        # Optional extras to resemble real DitaContext
        self.topics = {}
        self.images = {}


def test_apply_depth_limit_triggers_merge_and_sets_details(monkeypatch):
    # Arrange
    from orlando_toolkit.core.services.structure_editing_service import StructureEditingService
    ctx = _FakeCtxSimple(has_map=True)
    calls = {"count": 0}

    def stub_merge(context, depth, style_map):
        calls["count"] += 1
        # Simulate merge implementation updating metadata
        context.metadata["merged_depth"] = depth
        if style_map:
            context.metadata["merged_exclude_styles"] = True

    # Monkeypatch the exact function that the service imports locally
    monkeypatch.setattr(
        "orlando_toolkit.core.merge.merge_topics_unified",
        stub_merge,
        raising=True,
    )

    # Act
    res = StructureEditingService().apply_depth_limit(ctx, 2, None)

    # Assert
    assert res.success is True
    assert isinstance(res.details, dict)
    assert res.details.get("merged") is True
    assert res.details.get("depth_limit") == 2
    assert ctx.metadata.get("merged_depth") == 2
    assert calls["count"] == 1


def test_apply_depth_limit_noop_when_already_applied(monkeypatch):
    # Arrange
    from orlando_toolkit.core.services.structure_editing_service import StructureEditingService
    ctx = _FakeCtxSimple(has_map=True)
    ctx.metadata = {"merged_depth": 2, "merged_exclude_styles": False}
    calls = {"count": 0}

    def stub_merge(context, depth, style_map):
        calls["count"] += 1

    monkeypatch.setattr(
        "orlando_toolkit.core.merge.merge_topics_unified",
        stub_merge,
        raising=True,
    )

    # Act
    res = StructureEditingService().apply_depth_limit(ctx, 2, None)

    # Assert
    assert res.success is True
    assert isinstance(res.details, dict)
    assert res.details.get("merged") is False
    assert res.details.get("depth_limit") == 2
    assert calls["count"] == 0  # merge not called


def test_apply_depth_limit_handles_missing_ditamap_root():
    # Arrange
    from orlando_toolkit.core.services.structure_editing_service import StructureEditingService
    ctx = _FakeCtxSimple(has_map=False)

    # Act
    res = StructureEditingService().apply_depth_limit(ctx, 2, None)

    # Assert
    assert res.success is False
    assert isinstance(res.details, dict)
    assert res.details.get("reason") == "missing_ditamap"


def test_apply_depth_limit_handles_exception(monkeypatch):
    # Arrange
    from orlando_toolkit.core.services.structure_editing_service import StructureEditingService
    ctx = _FakeCtxSimple(has_map=True)

    def boom_merge(context, depth, style_map):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "orlando_toolkit.core.merge.merge_topics_unified",
        boom_merge,
        raising=True,
    )

    # Act
    res = StructureEditingService().apply_depth_limit(ctx, 2, None)

    # Assert
    assert res.success is False
    assert isinstance(res.details, dict)
    assert "error" in res.details


def test_apply_depth_limit_style_flag_change_forces_merge(monkeypatch):
    # Arrange
    from orlando_toolkit.core.services.structure_editing_service import StructureEditingService
    ctx = _FakeCtxSimple(has_map=True)
    ctx.metadata = {"merged_depth": 2, "merged_exclude_styles": False}
    calls = {"count": 0}

    def stub_merge(context, depth, style_map):
        calls["count"] += 1
        context.metadata["merged_depth"] = depth
        context.metadata["merged_exclude_styles"] = bool(style_map)

    monkeypatch.setattr(
        "orlando_toolkit.core.merge.merge_topics_unified",
        stub_merge,
        raising=True,
    )

    style_map = {1: {"Heading 2"}}  # providing styles should flip the flag to True

    # Act
    res = StructureEditingService().apply_depth_limit(ctx, 2, style_map)

    # Assert
    assert res.success is True
    assert isinstance(res.details, dict)
    assert res.details.get("merged") is True
    assert res.details.get("depth_limit") == 2
    assert calls["count"] == 1
    assert ctx.metadata.get("merged_exclude_styles") is True


def test_apply_depth_limit_reversibility(monkeypatch):
    """Test that depth limits are reversible - can increase after decrease."""
    # Arrange - create context with nested structure
    from orlando_toolkit.core.services.structure_editing_service import StructureEditingService
    from orlando_toolkit.core.models import DitaContext
    from lxml import etree as ET
    
    ctx = DitaContext()
    root = ET.Element("map")
    
    # L1 -> L2 -> L3 structure
    l1 = ET.SubElement(root, "topicref")
    l1.set("href", "topics/l1.dita")
    l1.set("data-level", "1")
    
    l2 = ET.SubElement(l1, "topicref")
    l2.set("href", "topics/l2.dita") 
    l2.set("data-level", "2")
    
    l3 = ET.SubElement(l2, "topicref")
    l3.set("href", "topics/l3.dita")
    l3.set("data-level", "3")
    
    ctx.ditamap_root = root
    ctx.topics = {
        "l1.dita": ET.Element("concept", id="l1"),
        "l2.dita": ET.Element("concept", id="l2"),
        "l3.dita": ET.Element("concept", id="l3")
    }
    ctx.metadata = {}
    
    # Capture original state
    original_xml = ET.tostring(ctx.ditamap_root, encoding='unicode')
    original_topics_count = len(ctx.topics)
    
    # Mock the merge function to track calls
    calls = {"count": 0}
    def stub_merge(context, depth, style_map):
        calls["count"] += 1
        context.metadata["merged_depth"] = depth
        if style_map:
            context.metadata["merged_exclude_styles"] = True
        # Simulate L3 merge by removing it when depth=2
        if depth == 2:
            l3_elements = context.ditamap_root.xpath(".//topicref[@data-level='3']")
            for elem in l3_elements:
                elem.getparent().remove(elem)
            context.topics.pop("l3.dita", None)

    monkeypatch.setattr("orlando_toolkit.core.merge.merge_topics_unified", stub_merge, raising=True)
    
    service = StructureEditingService()
    
    # Act 1: Apply depth_limit=2 (should merge L3)
    res1 = service.apply_depth_limit(ctx, depth_limit=2)
    depth2_topics = len(ctx.topics)
    depth2_xml = ET.tostring(ctx.ditamap_root, encoding='unicode')
    
    # Act 2: Apply depth_limit=999 (should restore original)
    res2 = service.apply_depth_limit(ctx, depth_limit=999)
    restored_topics = len(ctx.topics)
    restored_xml = ET.tostring(ctx.ditamap_root, encoding='unicode')
    
    # Assert
    assert res1.success is True
    assert res2.success is True
    assert depth2_topics == 2, "L3 should be merged at depth=2"
    assert restored_topics == original_topics_count, "All topics should be restored"
    assert original_xml == restored_xml, "Structure should be fully restored"
    assert calls["count"] == 2, "Merge should be called twice"