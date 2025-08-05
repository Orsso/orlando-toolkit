import os
import sys
import pytest

# Ensure project root is importable when running pytest from repository root
# Insert the repository root (one level up from tests/) to sys.path
_THIS_DIR = os.path.dirname(__file__)
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

lxml = pytest.importorskip("lxml")
from lxml import etree as ET

from orlando_toolkit.core.services.structure_editing_service import StructureEditingService
from orlando_toolkit.core.services.undo_service import UndoService
from orlando_toolkit.core.models import DitaContext


@pytest.fixture
def nsmap_dita():
    return {"dita": "http://example.com/dita"}


def _make_tag(local: str, nsmap):
    ns = nsmap["dita"]
    return f"{{{ns}}}{local}"


def _section_factory(nsmap, id_value=None, title_text="Section", p_text="Para"):
    sec = ET.Element(_make_tag("section", nsmap))
    if id_value:
        sec.set("id", id_value)
    title = ET.SubElement(sec, _make_tag("title", nsmap))
    title.text = title_text
    p = ET.SubElement(sec, _make_tag("p", nsmap))
    p.text = p_text
    return sec


@pytest.fixture
def minimal_topic_tree(nsmap_dita):
    nsmap = nsmap_dita
    # topic root
    topic = ET.Element(_make_tag("topic", nsmap))
    title = ET.SubElement(topic, _make_tag("title", nsmap))
    title.text = "T"

    body = ET.SubElement(topic, _make_tag("body", nsmap))

    p0 = ET.SubElement(body, _make_tag("p", nsmap))
    p0.text = "Intro"

    s1 = _section_factory(nsmap, id_value="s1", title_text="S1", p_text="P1")
    body.append(s1)

    ul = ET.SubElement(body, _make_tag("ul", nsmap))
    li_a = ET.SubElement(ul, _make_tag("li", nsmap))
    li_a.text = "A"
    li_b = ET.SubElement(ul, _make_tag("li", nsmap))
    li_b.text = "B"

    s2 = _section_factory(nsmap, id_value="s2", title_text="S2", p_text="P2")
    body.append(s2)

    # helpers
    def get_body(root=topic):
        return root.find(f".//{_make_tag('body', nsmap)}")

    def get_section_by_id(id_):
        return topic.find(f".//{_make_tag('section', nsmap)}[@id='{id_}']")

    def get_first_p(elem):
        return elem.find(f"./{_make_tag('p', nsmap)}")

    helpers = {
        "get_body": get_body,
        "get_section_by_id": get_section_by_id,
        "get_first_p": get_first_p,
    }

    return topic, helpers


@pytest.fixture
def structure_editing_service():
    # The service in repo operates on a DitaContext/ditamap/topicrefs domain.
    # For integration tests using raw lxml Element trees, we expose the class so tests can adapt usage if needed.
    return StructureEditingService()


@pytest.fixture
def edit_journal():
    # The journal model exists but the integration scope here uses UndoService snapshots as primary undo/redo.
    # Provide a fresh instance placeholder if tests need to extend later.
    from orlando_toolkit.core.models.edit_journal import EditJournal
    return EditJournal()


@pytest.fixture
def undo_service():
    return UndoService(max_history=50)


@pytest.fixture
def deep_copy_xml():
    def copier(elem: ET._Element):
        return ET.fromstring(ET.tostring(elem))
    return copier


@pytest.fixture
def as_string():
    def to_str(elem: ET._Element):
        return ET.tostring(elem, encoding="unicode")
    return to_str


@pytest.fixture
def find_by_xpath(nsmap_dita):
    def finder(elem: ET._Element, xpath: str):
        return elem.xpath(xpath, namespaces=nsmap_dita)
    return finder


@pytest.fixture
def make_context():
    # Helper to build a minimal DitaContext compatible with UndoService snapshots.
    # It sets ditamap_root and topics so that snapshots include both map and topic content.
    def factory(map_root: ET._Element | None = None, topics_map: dict[str, ET._Element] | None = None):
        ctx = DitaContext()
        ctx.ditamap_root = map_root
        ctx.topics = dict(topics_map or {})
        ctx.images = {}
        ctx.metadata = {}
        return ctx
    return factory