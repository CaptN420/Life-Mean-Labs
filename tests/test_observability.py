"""Tests for Autopilot observability module."""
import time

import pytest

from experiments.observability import (
    AgentRecord,
    AutopilotObservability,
    DebateEvent,
    DeterministicTrace,
    EventKind,
    ExperimentProgress,
)


class TestAgentRecord:
    def test_create_agent_record(self):
        rec = AgentRecord("agent1", persona="researcher", role="analyst", model="model_a", provider="provider_a")
        assert rec.agent_id == "agent1"
        assert rec.persona == "researcher"
        assert rec.model == "model_a"
        assert rec.provider == "provider_a"
        assert rec.status == "Waiting"

    def test_agent_record_to_dict(self):
        rec = AgentRecord("agent1", persona="researcher", role="analyst", model="model_a", provider="provider_a")
        d = rec.to_dict()
        assert d["agent_id"] == "agent1"
        assert d["status"] == "Waiting"
        assert d["persona"] == "researcher"

    def test_agent_record_update_status(self):
        rec = AgentRecord("agent1", persona="researcher", role="analyst", model="model_a", provider="provider_a")
        rec.status = "Running"
        assert rec.status == "Running"
        rec.status = "Completed"
        assert rec.status == "Completed"


class TestDebateEvent:
    def test_create_debate_event(self):
        event = DebateEvent(
            kind=EventKind.TURN_COMPLETED.value,
            agent_id="agent1",
            round_num=1,
            response="Hello world",
        )
        assert event.kind == "turn_completed"
        assert event.agent_id == "agent1"

    def test_debate_event_to_dict(self):
        event = DebateEvent(
            kind=EventKind.TURN_COMPLETED.value,
            agent_id="agent1",
            round_num=1,
            response="Hello world",
        )
        d = event.to_dict()
        assert d["kind"] == "turn_completed"
        assert d["agent_id"] == "agent1"


class TestDeterministicTrace:
    def test_create_trace(self):
        trace = DeterministicTrace(
            rule_name="round_robin",
            rule_version="1.0",
            input_snapshot={"agent_id": "agent1"},
            output_snapshot={"selected": True},
            agent_affected="agent1",
            state_before={"current_round": 0},
            state_after={"current_round": 1},
        )
        assert trace.rule_name == "round_robin"
        assert trace.agent_affected == "agent1"

    def test_trace_to_dict(self):
        trace = DeterministicTrace(
            rule_name="round_robin",
            input_snapshot={"agent_id": "agent1"},
            output_snapshot={"selected": True},
        )
        d = trace.to_dict()
        assert d["rule_name"] == "round_robin"


class TestExperimentProgress:
    def test_create_progress(self):
        progress = ExperimentProgress(
            experiment_id="exp1",
            status="RUNNING",
            current_round=2,
            total_rounds=5,
        )
        assert progress.experiment_id == "exp1"
        assert progress.status == "RUNNING"

    def test_progress_to_dict(self):
        progress = ExperimentProgress(experiment_id="exp1")
        d = progress.to_dict()
        assert d["experiment_id"] == "exp1"


class TestAutopilotObservability:
    def test_initial_state(self):
        obs = AutopilotObservability()
        assert obs.get_prompt() == ""
        assert obs.get_config() == {}
        assert obs.get_progress() is None

    def test_start_experiment(self):
        obs = AutopilotObservability()
        obs.start_experiment(
            experiment_id="exp1",
            config={"num_tasks": 10, "strategy": "round_robin"},
            prompt="Test prompt",
            agents=[{"agent_id": "agent1", "persona": "researcher", "role": "analyst"}],
        )
        assert obs.get_prompt() == "Test prompt"
        assert obs.get_config()["num_tasks"] == 10
        progress = obs.get_progress()
        assert progress["status"] == "RUNNING"

    def test_record_turn(self):
        obs = AutopilotObservability()
        obs.start_experiment("exp1", {"num_tasks": 5}, "Test prompt")
        obs.record_turn("agent1", 1, "Hello world", rule="round_robin")
        events = obs.get_events()
        assert len(events) == 2  # started + turn
        assert events[1]["kind"] == "turn_completed"
        assert events[1]["agent_id"] == "agent1"

    def test_record_rule_application(self):
        obs = AutopilotObservability()
        obs.start_experiment("exp1", {"num_tasks": 5}, "Test prompt")
        obs.record_rule_application(
            rule_name="round_robin",
            rule_version="1.0",
            input_data={"agent_id": "agent2"},
            output_data={"selected": True},
            agent_id="agent1",
        )
        traces = obs.get_traces()
        assert len(traces) == 1
        assert traces[0]["rule_name"] == "round_robin"

    def test_record_error(self):
        obs = AutopilotObservability()
        obs.start_experiment("exp1", {"num_tasks": 5}, "Test prompt")
        obs.record_error("Connection timeout", agent_id="agent1")
        events = obs.get_events()
        assert len(events) == 2
        assert events[1]["kind"] == "error"
        assert events[1]["error"] == "Connection timeout"

    def test_update_progress(self):
        obs = AutopilotObservability()
        obs.start_experiment("exp1", {"num_tasks": 10}, "Test prompt")
        obs.update_progress(
            current_round=3,
            total_rounds=5,
            active_agent="agent1",
            tasks_completed=3,
        )
        progress = obs.get_progress()
        assert progress["current_round"] == 3
        assert progress["total_rounds"] == 5

    def test_complete_experiment(self):
        obs = AutopilotObservability()
        obs.start_experiment("exp1", {"num_tasks": 5}, "Test prompt")
        obs.complete_experiment(status="COMPLETED")
        progress = obs.get_progress()
        assert progress["status"] == "COMPLETED"

    def test_export_manifest(self):
        obs = AutopilotObservability()
        obs.start_experiment(
            experiment_id="exp1",
            config={"strategy": "round_robin"},
            prompt="Test prompt",
            agents=[{"agent_id": "agent1", "persona": "researcher"}],
        )
        obs.record_turn("agent1", 1, "Hello")
        manifest = obs.export_manifest()
        assert manifest["experiment_id"] == "exp1"
        assert manifest["prompt"] == "Test prompt"
        assert "agents" in manifest
        assert "events" in manifest
        assert "config" in manifest

    def test_events_limit(self):
        obs = AutopilotObservability()
        obs.start_experiment("exp1", {"num_tasks": 5}, "Test prompt")
        for i in range(10):
            obs.record_turn("agent1", i, f"Response {i}")
        events = obs.get_events(limit=5)
        assert len(events) == 5  # limited to 5 total

    def test_traces_limit(self):
        obs = AutopilotObservability()
        obs.start_experiment("exp1", {"num_tasks": 5}, "Test prompt")
        for i in range(10):
            obs.record_rule_application(f"rule_{i}", "1.0", {}, {}, f"agent{i}")
        traces = obs.get_traces(limit=5)
        assert len(traces) == 5

    def test_no_events_or_traces(self):
        obs = AutopilotObservability()
        # Before starting, no events or traces
        assert obs.get_events() == []
        assert obs.get_traces() == []
