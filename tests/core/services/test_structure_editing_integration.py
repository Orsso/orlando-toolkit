import pytest

pytest.importorskip("lxml")
from lxml import etree as ET

from orlando_toolkit.core.services.structure_editing_service import StructureEditingService
from orlando_toolkit.core.services.undo_service import UndoService


# These integration tests operate on real lxml.etree.Element trees (DITA-like),
# with UndoService snapshots for undo/redo behavior. We do not rely on UI controllers.


def _new_section(nsmap, sid, title_text, p_text):
    ns = nsmap["dita"]
    def tag(local): return f"{{{ns}}}{local}"
    sec = ET.Element(tag("section"))
    sec.set("id", sid)
    title = ET.SubElement(sec, tag("title"))
    title.text = title_text
    p = ET.SubElement(sec, tag("p"))
    p.text = p_text
    return sec


def _index_of(parent, child):
    return list(parent).index(child)


def _as_text(elem):
    return ET.tostring(elem, encoding="unicode")


def _ns_tag(nsmap, local):
    return f"{{{nsmap['dita']}}}{local}"


def _find_xpath_namespaced(root, expr, nsmap):
    # Use full XPath engine with namespaces
    return root.xpath(expr, namespaces={"dita": nsmap["dita"]})


def _find_one_xpath_namespaced(root, expr, nsmap):
    res = _find_xpath_namespaced(root, expr, nsmap)
    return res[0] if res else None


def _find_section_by_id(root, sid, nsmap):
    return _find_one_xpath_namespaced(root, f".//dita:section[@id='{sid}']", nsmap)


def _find_body(root, nsmap):
    return _find_one_xpath_namespaced(root, ".//dita:body", nsmap)


def _find_first_p_under(elem, nsmap):
    return _find_one_xpath_namespaced(elem, "./dita:p", nsmap)


def _find_topic_title(root, nsmap):
    return _find_one_xpath_namespaced(root, "./dita:title", nsmap)


def _find_ul_under_body(root, nsmap):
    body = _find_body(root, nsmap)
    if body is None:
        return None
    return _find_one_xpath_namespaced(body, "./dita:ul", nsmap)


def _rebind_ctx_view(ctx, nsmap):
    root = ctx.ditamap_root
    body = _find_body(root, nsmap)
    return root, body


def _setup_ctx_from_topic(topic):
    from orlando_toolkit.core.models import DitaContext
    ctx = DitaContext()
    ctx.ditamap_root = topic
    ctx.topics = {}
    ctx.images = {}
    ctx.metadata = {}
    return ctx


def test_insert_section_into_body_undo_redo(
    nsmap_dita,
    minimal_topic_tree,
    undo_service: UndoService,
):
    topic, helpers = minimal_topic_tree
    ctx = _setup_ctx_from_topic(topic)
    body = _find_body(ctx.ditamap_root, nsmap_dita)
    assert body is not None
    initial_count = len(list(body))

    # Baseline snapshot BEFORE mutation
    undo_service.push_snapshot(ctx)

    # Perform mutation
    new_sec = _new_section(nsmap_dita, "sX", "SX", "PX")
    insert_index = 1
    body.insert(insert_index, new_sec)
    assert len(list(body)) == initial_count + 1

    # Push POST-mutation snapshot
    undo_service.push_snapshot(ctx)

    # Undo -> should restore baseline (no sX)
    assert undo_service.undo(ctx) is True
    _, body_u = _rebind_ctx_view(ctx, nsmap_dita)
    assert len(list(body_u)) == initial_count
    assert _find_section_by_id(ctx.ditamap_root, "sX", nsmap_dita) is None

    # Redo -> should restore mutated state (sX at index)
    assert undo_service.redo(ctx) is True
    _, body_r = _rebind_ctx_view(ctx, nsmap_dita)
    sec_restored = _find_section_by_id(ctx.ditamap_root, "sX", nsmap_dita)
    assert sec_restored is not None
    assert _index_of(body_r, sec_restored) == insert_index


def test_delete_nested_element_with_subtree_undo_redo(
    nsmap_dita,
    minimal_topic_tree,
    undo_service: UndoService,
    as_string,
):
    topic, _ = minimal_topic_tree
    ctx = _setup_ctx_from_topic(topic)
    s1 = _find_section_by_id(ctx.ditamap_root, "s1", nsmap_dita)
    assert s1 is not None
    snapshot_before = ET.fromstring(ET.tostring(ctx.ditamap_root))

    # Baseline
    undo_service.push_snapshot(ctx)

    # Mutate
    parent = s1.getparent()
    parent.remove(s1)
    assert _find_section_by_id(ctx.ditamap_root, "s1", nsmap_dita) is None

    # Post-mutation
    undo_service.push_snapshot(ctx)

    # Undo -> snapshot_before
    assert undo_service.undo(ctx) is True
    assert as_string(ctx.ditamap_root) == as_string(snapshot_before)

    # Redo -> deleted again
    assert undo_service.redo(ctx) is True
    assert _find_section_by_id(ctx.ditamap_root, "s1", nsmap_dita) is None


def test_move_element_reorder_among_siblings_undo_redo(
    nsmap_dita,
    minimal_topic_tree,
    undo_service: UndoService,
):
    topic, _ = minimal_topic_tree
    ctx = _setup_ctx_from_topic(topic)
    body = _find_body(ctx.ditamap_root, nsmap_dita)
    s2 = _find_section_by_id(ctx.ditamap_root, "s2", nsmap_dita)
    assert body is not None and s2 is not None

    new_index = 1

    # Baseline
    undo_service.push_snapshot(ctx)

    # Mutate
    body.remove(s2)
    body.insert(new_index, s2)

    # Post-mutation
    undo_service.push_snapshot(ctx)

    # Undo -> original order
    assert undo_service.undo(ctx) is True
    _, body_u = _rebind_ctx_view(ctx, nsmap_dita)
    s2_u = _find_section_by_id(ctx.ditamap_root, "s2", nsmap_dita)
    assert _index_of(body_u, s2_u) != new_index

    # Redo -> new_index
    assert undo_service.redo(ctx) is True
    _, body_r = _rebind_ctx_view(ctx, nsmap_dita)
    s2_r = _find_section_by_id(ctx.ditamap_root, "s2", nsmap_dita)
    assert _index_of(body_r, s2_r) == new_index


def test_attribute_and_text_edits_undo_redo(
    nsmap_dita,
    minimal_topic_tree,
    undo_service: UndoService,
):
    topic, _ = minimal_topic_tree
    ctx = _setup_ctx_from_topic(topic)
    s1 = _find_section_by_id(ctx.ditamap_root, "s1", nsmap_dita)
    p_first = _find_first_p_under(s1, nsmap_dita)
    assert s1 is not None and p_first is not None

    # Baseline
    undo_service.push_snapshot(ctx)

    # Attribute mutation
    s1.set("outputclass", "oc-1")
    undo_service.push_snapshot(ctx)  # after attr

    # Text mutation
    p_first.text = "Changed"
    undo_service.push_snapshot(ctx)  # after text

    # Undo text -> attribute remains
    assert undo_service.undo(ctx) is True
    s1_u = _find_section_by_id(ctx.ditamap_root, "s1", nsmap_dita)
    p_first_u = _find_first_p_under(s1_u, nsmap_dita)
    assert s1_u.get("outputclass") == "oc-1"
    assert p_first_u.text != "Changed"

    # Undo attribute
    assert undo_service.undo(ctx) is True
    s1_uu = _find_section_by_id(ctx.ditamap_root, "s1", nsmap_dita)
    assert s1_uu.get("outputclass") is None

    # Redo attribute
    assert undo_service.redo(ctx) is True
    s1_r = _find_section_by_id(ctx.ditamap_root, "s1", nsmap_dita)
    assert s1_r.get("outputclass") == "oc-1"

    # Redo text
    assert undo_service.redo(ctx) is True
    s1_rr = _find_section_by_id(ctx.ditamap_root, "s1", nsmap_dita)
    p_first_rr = _find_first_p_under(s1_rr, nsmap_dita)
    assert p_first_rr.text == "Changed"


def test_composite_sequence_full_undo_all_redo_all_deep_equality(
    nsmap_dita,
    minimal_topic_tree,
    undo_service: UndoService,
):
    topic, _ = minimal_topic_tree
    ctx = _setup_ctx_from_topic(topic)

    # Baseline snapshot
    snapshot0 = ET.fromstring(ET.tostring(ctx.ditamap_root))
    undo_service.push_snapshot(ctx)

    body = _find_body(ctx.ditamap_root, nsmap_dita)

    # 1) insert section
    new_s = _new_section(nsmap_dita, "sX", "SX", "PX")
    body.insert(1, new_s)
    undo_service.push_snapshot(ctx)

    # 2) move s2
    s2 = _find_section_by_id(ctx.ditamap_root, "s2", nsmap_dita)
    body.remove(s2)
    body.insert(1, s2)
    undo_service.push_snapshot(ctx)

    # 3) set attribute on s1
    s1 = _find_section_by_id(ctx.ditamap_root, "s1", nsmap_dita)
    s1.set("outputclass", "c1")
    undo_service.push_snapshot(ctx)

    # 4) edit text
    p1 = _find_first_p_under(s1, nsmap_dita)
    p1.text = "Edited"
    undo_service.push_snapshot(ctx)

    # 5) delete ul
    ul = _find_ul_under_body(ctx.ditamap_root, nsmap_dita)
    body.remove(ul)
    undo_service.push_snapshot(ctx)

    # 6) change topic title
    t_title = _find_topic_title(ctx.ditamap_root, nsmap_dita)
    t_title.text = "Changed T"
    undo_service.push_snapshot(ctx)

    # Final snapshot
    snapshotF = ET.fromstring(ET.tostring(ctx.ditamap_root))

    # Undo all -> equals snapshot0
    changed = True
    while changed:
        changed = undo_service.undo(ctx)
    assert ET.tostring(ctx.ditamap_root, encoding="unicode") == ET.tostring(snapshot0, encoding="unicode")

    # Redo all -> equals snapshotF
    changed = True
    while changed:
        changed = undo_service.redo(ctx)
    assert ET.tostring(ctx.ditamap_root, encoding="unicode") == ET.tostring(snapshotF, encoding="unicode")