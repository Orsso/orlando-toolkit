import pytest

from orlando_toolkit.core.services.undo_service import UndoService


class FakeDitaContext:
    """
    Minimal in-memory fake matching UndoService expectations.

    UndoService uses lxml.etree to serialize/deserialize:
      - context.ditamap_root (Element or None)
      - context.topics: dict[str, Element]
    It also copies:
      - context.images: dict[str, bytes]
      - context.metadata: dict[str, Any]

    To keep tests light and not bring lxml as a dependency for the tests,
    we use the actual lxml Elements implicitly via UndoService. We only
    provide convenience mutators dealing with string payloads so assertions
    remain simple and robust to internal structure: we normalize state into
    strings for equality checks.
    """
    def __init__(self, map_xml: str, topics: dict[str, str]) -> None:
        # Delay lxml import until runtime to avoid test dependency leaks
        from lxml import etree as ET

        self.images = {}
        self.metadata = {}

        self.ditamap_root = ET.fromstring(map_xml) if map_xml is not None else None
        self.topics = {k: ET.fromstring(v) for k, v in topics.items()}

    # Helpers used by tests to mutate state between snapshots using strings.
    def set_map(self, map_xml: str | None) -> None:
        from lxml import etree as ET

        self.ditamap_root = ET.fromstring(map_xml) if map_xml is not None else None

    def set_topic(self, topic_id: str, topic_xml: str) -> None:
        from lxml import etree as ET

        self.topics[topic_id] = ET.fromstring(topic_xml)

    def delete_topic(self, topic_id: str) -> None:
        if topic_id in self.topics:
            del self.topics[topic_id]

    # Normalized state view for simple equality checks
    def snapshot_view(self) -> tuple[str | None, dict[str, str]]:
        from lxml import etree as ET

        map_str = None
        if self.ditamap_root is not None:
            map_str = ET.tostring(self.ditamap_root, encoding="utf-8").decode("utf-8")

        topics_str: dict[str, str] = {}
        for k, elem in sorted(self.topics.items(), key=lambda x: x[0]):
            topics_str[k] = ET.tostring(elem, encoding="utf-8").decode("utf-8")

        return map_str, topics_str


@pytest.fixture
def fake_context():
    # Initial simple map and two topics, use raw XML literals
    map_xml = "<map><topicref href=\"topic1.dita\"/><topicref href=\"topic2.dita\"/></map>"

    topics = {
        "topic1.dita": "<topic id=\"t1\"><title>Title 1</title></topic>",
        "topic2.dita": "<topic id=\"t2\"><title>Title 2</title></topic>",
    }
    return FakeDitaContext(map_xml, topics)


@pytest.fixture
def service():
    return UndoService(max_history=3)


def test_push_snapshot_clears_redo_and_enforces_max_history(fake_context, service):
    # Initial state
    service.push_snapshot(fake_context)  # 1
    # Mutate and push more than max_history
    fake_context.set_topic("topic1.dita", "<topic id=\"t1\"><title>Title 1a</title></topic>")
    service.push_snapshot(fake_context)  # 2

    fake_context.set_topic("topic2.dita", "<topic id=\"t2\"><title>Title 2a</title></topic>")
    service.push_snapshot(fake_context)  # 3

    fake_context.set_map("<map><topicref href=\"topic1.dita\"/></map>")
    service.push_snapshot(fake_context)  # 4 -> should trim to 3

    # Undo stack length capped to 3, redo empty after pushes
    assert service.can_undo() is True
    assert service.can_redo() is False

    # Access internal stacks indirectly via behavior:
    # Perform 3 undos successfully; 4th should fail due to trimming.
    assert service.undo(fake_context) is True
    assert service.undo(fake_context) is True
    assert service.undo(fake_context) is True
    assert service.undo(fake_context) is False  # trimmed away


def test_undo_redo_roundtrip_restores_state_in_place(fake_context, service):
    # Push baseline
    service.push_snapshot(fake_context)
    baseline_view = fake_context.snapshot_view()

    # Mutate
    fake_context.set_topic("topic1.dita", "<topic id=\"t1\"><title>Changed</title></topic>")
    fake_context.set_map("<map><topicref href=\"topic1.dita\"/><topicref href=\"topic2.dita\"/><topicref href=\"extra.dita\"/></map>")
    service.push_snapshot(fake_context)
    mutated_view = fake_context.snapshot_view()

    # Undo should restore baseline
    assert service.undo(fake_context) is True
    assert fake_context.snapshot_view() == baseline_view

    # Redo should restore mutated
    assert service.redo(fake_context) is True
    assert fake_context.snapshot_view() == mutated_view


def test_can_undo_can_redo_transitions(fake_context, service):
    # Fresh service
    assert service.can_undo() is False
    assert service.can_redo() is False

    # Push first snapshot
    service.push_snapshot(fake_context)
    assert service.can_undo() is True
    assert service.can_redo() is False

    # Mutate and push second snapshot
    fake_context.set_topic("topic2.dita", "<topic id=\"t2\"><title>V2</title></topic>")
    service.push_snapshot(fake_context)
    assert service.can_undo() is True
    assert service.can_redo() is False

    # Undo makes redo available
    assert service.undo(fake_context) is True
    assert service.can_undo() is True  # there is at least one more on undo
    assert service.can_redo() is True

    # Redo removes redo availability
    assert service.redo(fake_context) is True
    assert service.can_undo() is True
    assert service.can_redo() is False

    # Pushing a new snapshot clears redo
    fake_context.set_map("<map/>")
    service.push_snapshot(fake_context)
    assert service.can_undo() is True
    assert service.can_redo() is False


def test_undo_on_empty_stack_returns_false(fake_context, service):
    assert service.undo(fake_context) is False


def test_redo_on_empty_stack_returns_false(fake_context, service):
    assert service.redo(fake_context) is False


def test_corrupted_snapshot_is_skipped_gracefully(fake_context, service, monkeypatch):
    # Push a valid snapshot to have something in history
    service.push_snapshot(fake_context)
    original_view = fake_context.snapshot_view()

    # Inject corrupted entry into the undo stack via monkeypatch
    # The _restore_snapshot_into_context expects _Snapshot with specific attributes;
    # provide a wrong type or invalid payload to cause a graceful failure.
    class BadSnap:
        # Missing expected bytes; attributes of wrong types will cause exceptions on restore
        ditamap_xml = b"<not-xml>"
        topics_xml = {"topic1.dita": b"<broken>"}  # invalid xml
        images = {}
        metadata = {}

    # Place the bad snapshot on top of the undo stack so undo tries to restore it
    service._undo_stack.append(BadSnap())  # type: ignore[attr-defined]

    # Undo should return False and not raise; context remains unchanged
    assert service.undo(fake_context) is False
    assert fake_context.snapshot_view() == original_view