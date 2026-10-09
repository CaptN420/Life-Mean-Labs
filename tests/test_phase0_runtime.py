"""Phase 0 — Runtime Foundation Characterization Tests.

Tests that verify the core runtime components work correctly.
These are characterization tests that document the expected behavior
before refactoring.
"""

import pytest
from core.events.message import Message, Task, Rule, Pipeline
from core.events.event_bus import EventBus, InMemoryStateStore
from core.runtime.worker import Worker, BaseWorker, DeterministicWorker


class TestMessage:
    """Tests for Message dataclass."""

    def test_message_creation_defaults(self):
        msg = Message()
        assert msg.id is not None
        assert msg.sender == "system"
        assert msg.destination == "orchestrator"
        assert msg.type == "task"
        assert msg.payload == {}
        assert msg.timestamp > 0

    def test_message_creation_with_values(self):
        msg = Message(
            sender="test_sender",
            destination="test_dest",
            type="response",
            payload={"key": "value"}
        )
        assert msg.sender == "test_sender"
        assert msg.destination == "test_dest"
        assert msg.type == "response"
        assert msg.payload == {"key": "value"}

    def test_message_to_dict(self):
        msg = Message(sender="test", type="task", payload={"x": 1})
        d = msg.to_dict()
        assert d["sender"] == "test"
        assert d["type"] == "task"
        assert d["payload"] == {"x": 1}

    def test_message_from_dict(self):
        d = {
            "id": "test-id",
            "sender": "test_sender",
            "destination": "test_dest",
            "type": "response",
            "payload": {"key": "value"},
            "timestamp": 1234567890.0
        }
        msg = Message.from_dict(d)
        assert msg.id == "test-id"
        assert msg.sender == "test_sender"
        assert msg.type == "response"

    def test_message_id_uniqueness(self):
        msg1 = Message()
        msg2 = Message()
        assert msg1.id != msg2.id


class TestTask:
    """Tests for Task dataclass."""

    def test_task_creation(self):
        task = Task(
            task_id="task-1",
            source="test",
            action="analyze",
            pipeline_id="pipeline-1"
        )
        assert task.task_id == "task-1"
        assert task.status == "pending"
        assert task.priority == 1
        assert task.retries == 0

    def test_task_to_json(self):
        task = Task(
            task_id="task-1",
            source="test",
            action="analyze",
            pipeline_id="pipeline-1"
        )
        j = task.to_json()
        assert j["task_id"] == "task-1"
        assert j["status"] == "pending"

    def test_task_is_complete(self):
        task = Task(task_id="t1", source="s", action="a", pipeline_id="p")
        assert not task.is_complete
        task.status = "completed"
        assert task.is_complete
        task.status = "failed"
        assert task.is_complete


class TestRule:
    """Tests for Rule dataclass."""

    def test_rule_creation(self):
        rule = Rule(
            name="test_rule",
            description="A test rule",
            condition=lambda task: True,
            error_message="Rule violated"
        )
        assert rule.name == "test_rule"
        assert rule.condition(None) is True


class TestPipeline:
    """Tests for Pipeline dataclass."""

    def test_pipeline_creation(self):
        pipeline = Pipeline(
            id="pipeline-1",
            steps=["extractor", "normalizer", "validator"]
        )
        assert pipeline.id == "pipeline-1"
        assert len(pipeline.steps) == 3


class TestEventBus:
    """Tests for EventBus."""

    def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []
        bus.subscribe("test_event", lambda msg: received.append(msg))
        bus.publish(Message(type="test_event", payload={"x": 1}))
        assert len(received) == 1
        assert received[0].payload == {"x": 1}

    def test_multiple_subscribers(self):
        bus = EventBus()
        received1 = []
        received2 = []
        bus.subscribe("event", lambda msg: received1.append(msg))
        bus.subscribe("event", lambda msg: received2.append(msg))
        bus.publish(Message(type="event"))
        assert len(received1) == 1
        assert len(received2) == 1

    def test_history_tracking(self):
        bus = EventBus()
        bus.publish(Message(type="a"))
        bus.publish(Message(type="b"))
        assert bus.history_count == 2

    def test_clear_history(self):
        bus = EventBus()
        bus.publish(Message(type="a"))
        bus.clear_history()
        assert bus.history_count == 0


class TestInMemoryStateStore:
    """Tests for InMemoryStateStore."""

    def test_set_and_get(self):
        store = InMemoryStateStore()
        store.set("key", "value")
        assert store.get("key") == "value"

    def test_has(self):
        store = InMemoryStateStore()
        assert not store.has("missing")
        store.set("key", "value")
        assert store.has("key")

    def test_delete(self):
        store = InMemoryStateStore()
        store.set("key", "value")
        assert store.delete("key") is True
        assert not store.has("key")
        assert store.delete("missing") is False

    def test_keys(self):
        store = InMemoryStateStore()
        store.set("a", 1)
        store.set("b", 2)
        assert set(store.keys()) == {"a", "b"}

    def test_clear(self):
        store = InMemoryStateStore()
        store.set("key", "value")
        store.clear()
        assert not store.has("key")


class TestWorker:
    """Tests for Worker base class."""

    def test_worker_initialization(self):
        worker = Worker()
        assert worker.name == "base"
        assert worker.is_active is False

    def test_worker_initialize(self):
        worker = Worker()
        result = worker.initialize()
        assert result is True
        assert worker.is_active is True

    def test_worker_shutdown(self):
        worker = Worker()
        worker.initialize()
        result = worker.shutdown()
        assert result is True
        assert worker.is_active is False

    def test_worker_execute_raises(self):
        worker = Worker()
        with pytest.raises(NotImplementedError):
            worker.execute(Message())


class TestBaseWorker:
    """Tests for BaseWorker."""

    def test_base_worker_creation(self):
        worker = BaseWorker("test_worker")
        assert worker.name == "test_worker"
        assert worker.is_active is True

    def test_base_worker_execute_creates_response(self):
        bus = EventBus()
        worker = BaseWorker("test_worker", bus)
        msg = Message(
            type="task",
            payload={"task_id": "task-1"}
        )
        worker.execute(msg)
        assert bus.history_count == 1
        response = bus.get_history()[0]
        assert response.type == "response"
        assert response.payload["valid"] is True


class TestDeterministicWorker:
    """Tests for DeterministicWorker (testing utility)."""

    def test_deterministic_worker(self):
        bus = EventBus()
        worker = DeterministicWorker(
            "test_worker",
            result={"output": "deterministic_result"},
            bus=bus
        )
        msg = Message(type="task", payload={"task_id": "task-1"})
        worker.execute(msg)
        assert bus.history_count == 1
        response = bus.get_history()[0]
        assert response.payload["result"]["output"] == "deterministic_result"
