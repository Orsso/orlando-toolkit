import pytest

pytest.importorskip("lxml")
from lxml import etree as ET

from orlando_toolkit.core.services.undo_service import UndoService
from orlando_toolkit.core.models import DitaContext


def _as_string(elem):
    return ET.tostring(elem, encoding="unicode")


def _find_xpath_ns(root, expr, nsmap):
    return root.xpath(expr, namespaces={"dita": nsmap["dita"]})


def _find_one_xpath_ns(root, expr, nsmap):
    res = _find_xpath_ns(root, expr, nsmap)
    return res[0] if res else None


@pytest.fixture
def base_context(nsmap_dita, minimal_topic_tree):
    topic, helpers = minimal_topic_tree
    ctx = DitaContext()
    ctx.ditamap_root = topic
    ctx.topics = {}
    ctx.images = {}
    ctx.metadata = {}
    return ctx


def test_undo_redo_cursor_logic_real_tree(
    nsmap_dita,
    minimal_topic_tree,
    base_context: DitaContext,
):
    ctx = base_context
    undo = UndoService(max_history=10)

    # 3 sequential operations (insert, text edit, attribute edit)
    undo.push_snapshot(ctx)
    body = _find_one_xpath_ns(ctx.ditamap_root, ".//dita:body", nsmap_dita)
    new_s = ET.Element(f"{{{nsmap_dita['dita']}}}section")
    title = ET.SubElement(new_s, f"{{{nsmap_dita['dita']}}}title")
    title.text = "NX"
    p = ET.SubElement(new_s, f"{{{nsmap_dita['dita']}}}p")
    p.text = "PX"
    body.append(new_s)

    undo.push_snapshot(ctx)
    # text edit
    topic_title = _find_one_xpath_ns(ctx.ditamap_root, "./dita:title", nsmap_dita)
    topic_title.text = "T2"

    undo.push_snapshot(ctx)
    # attribute edit
    new_s.set("outputclass", "oc2")

    undo.push_snapshot(ctx)

    # Now undo stepwise to start
    assert undo.can_undo() is True
    assert undo.undo(ctx) is True  # undo attr
    # After undo, attribute should be gone; refresh handles
    new_s_u = _find_one_xpath_ns(ctx.ditamap_root, ".//dita:section[./dita:title='NX']", nsmap_dita)
    assert new_s_u is not None and new_s_u.get("outputclass") is None

    assert undo.undo(ctx) is True  # undo text
    title_u = _find_one_xpath_ns(ctx.ditamap_root, "./dita:title", nsmap_dita)
    assert title_u.text != "T2"

    assert undo.undo(ctx) is True  # undo insert
    new_s_u2 = _find_one_xpath_ns(ctx.ditamap_root, ".//dita:section[./dita:title='NX']", nsmap_dita)
    assert new_s_u2 is None

    # Extra undo is no-op
    _ = undo.undo(ctx)

    # Redo stepwise to end
    assert undo.redo(ctx) is True  # redo insert
    new_s_r1 = _find_one_xpath_ns(ctx.ditamap_root, ".//dita:section[./dita:title='NX']", nsmap_dita)
    assert new_s_r1 is not None

    assert undo.redo(ctx) is True  # redo text
    title_r = _find_one_xpath_ns(ctx.ditamap_root, "./dita:title", nsmap_dita)
    assert title_r.text == "T2"

    assert undo.redo(ctx) is True  # redo attr
    new_s_r2 = _find_one_xpath_ns(ctx.ditamap_root, ".//dita:section[./dita:title='NX']", nsmap_dita)
    assert new_s_r2 is not None and new_s_r2.get("outputclass") == "oc2"

    # Extra redo is no-op
    _ = undo.redo(ctx)


def test_journal_entries_restore_exact_prior_content(
    nsmap_dita,
    minimal_topic_tree,
    base_context: DitaContext,
):
    ctx = base_context
    undo = UndoService(max_history=10)

    snapshots = []

    # snapshot 0
    undo.push_snapshot(ctx)
    snapshots.append(_as_string(ctx.ditamap_root))

    # step 1: insert a section
    body = _find_one_xpath_ns(ctx.ditamap_root, ".//dita:body", nsmap_dita)
    sA = ET.Element(f"{{{nsmap_dita['dita']}}}section")
    sA.set("id", "A")
    ET.SubElement(sA, f"{{{nsmap_dita['dita']}}}title").text = "A"
    ET.SubElement(sA, f"{{{nsmap_dita['dita']}}}p").text = "PA"
    body.insert(1, sA)
    undo.push_snapshot(ctx)
    snapshots.append(_as_string(ctx.ditamap_root))

    # step 2: modify text
    s1 = _find_one_xpath_ns(ctx.ditamap_root, ".//dita:section[@id='s1']", nsmap_dita)
    p1 = _find_one_xpath_ns(s1, "./dita:p", nsmap_dita)
    p1.text = "Changed-1"
    undo.push_snapshot(ctx)
    snapshots.append(_as_string(ctx.ditamap_root))

    # step 3: attribute edit
    s2 = _find_one_xpath_ns(ctx.ditamap_root, ".//dita:section[@id='s2']", nsmap_dita)
    s2.set("outputclass", "k")
    undo.push_snapshot(ctx)
    snapshots.append(_as_string(ctx.ditamap_root))

    # Undo stepwise comparing against previous snapshot each step
    for idx in range(len(snapshots) - 1, 0, -1):
        assert undo.undo(ctx) is True
        assert _as_string(ctx.ditamap_root) == snapshots[idx - 1]

    # Extra undo is no-op
    _ = undo.undo(ctx)

    # Redo stepwise comparing against next snapshot
    for idx in range(1, len(snapshots)):
        assert undo.redo(ctx) is True
        assert _as_string(ctx.ditamap_root) == snapshots[idx]

    # Extra redo is no-op
    _ = undo.redo(ctx)