import types
import xml.etree.ElementTree as ET

from orlando_toolkit.ui.tabs.structure.preview_coordinator import PreviewCoordinator
from orlando_toolkit.ui.tabs.structure.search_coordinator import SearchCoordinator


class FakePanel:
    def __init__(self):
        self.mode = "html"
        self.content = None
        self.loading = False
        self.breadcrumb = []
        self.errors = []

    def get_mode(self):
        return self.mode

    def set_loading(self, v: bool):
        self.loading = bool(v)

    def set_title(self, _):
        pass

    def set_content(self, c: str):
        self.content = c

    def show_error(self, m: str):
        self.errors.append(m)

    def clear(self):
        self.content = ""

    def set_breadcrumb_path(self, items):
        self.breadcrumb = items


class FakeCtrl:
    def __init__(self):
        self.context = types.SimpleNamespace()

    # Node-based preview
    def render_html_preview_for_node(self, _ctx, node):
        # Produce recognizable output per tag
        if getattr(node, 'tag', None) == 'topicref':
            return types.SimpleNamespace(success=True, content="<html>topic</html>")
        return types.SimpleNamespace(success=True, content="<html>section</html>")

    def compile_preview_for_node(self, _ctx, node):
        return types.SimpleNamespace(success=True, content="<xml></xml>")

    # Search
    def handle_search(self, term: str):
        # Return [section, topic]
        s = ET.Element('topichead')
        t = ET.Element('topicref')
        t.set('href', 'topics/x.dita')
        return [s, t]


def test_preview_coordinator_renders_topic_first(monkeypatch):
    panel = FakePanel()
    ctrl = FakeCtrl()

    def getter():
        return ctrl

    # Replace threading with direct call
    pc = PreviewCoordinator(controller_getter=getter, panel=panel,
                            schedule_ui=lambda *a, **k: None,
                            run_in_thread=lambda work, done: done(work()))

    # Provide both section and topic; coordinator should pick topic
    s = ET.Element('topichead')
    t = ET.Element('topicref'); t.set('href', 'topics/x.dita')

    pc.update_for_selection([s, t])

    assert panel.content is not None
    assert 'topic' in panel.content


def test_search_coordinator_calls_update_for_selection(monkeypatch):
    panel = FakePanel()
    ctrl = FakeCtrl()

    def getter():
        return ctrl

    called = {'ok': False}

    class FakePreview:
        def update_for_selection(self, nodes):
            called['ok'] = bool(nodes)

    class FakeTree:
        def set_highlight_xml_nodes(self, nodes):
            assert nodes
        def focus_item_centered(self, node):
            pass

    sc = SearchCoordinator(controller_getter=getter, tree=FakeTree(), preview=FakePreview(), update_legend=lambda: None)
    sc.term_changed("x")

    assert called['ok'] is True

