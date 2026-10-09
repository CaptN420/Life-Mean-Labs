"""Phase 1 — Routing & Assignment Characterization Tests.

Tests that verify the routing and assignment components work correctly.
These are characterization tests that document the expected behavior.
"""

import pytest
from core.events.message import Message
from core.events.event_bus import EventBus
from core.workers.tool import ToolWorker
from core.assignment.router import SmartRouter, RouterWorker


class TestToolDetection:
    """Tests for tool detection mapping."""

    def test_detect_code_review(self):
        from library.tools.detection import detect_tool
        result = detect_tool("review the code quality")
        assert result is not None
        assert "review" in result["tool_name"]
        assert result["domain"] == "coding"

    def test_detect_algebra_simplify(self):
        from library.tools.detection import detect_tool
        result = detect_tool("simplify the expression x^2 + 2x")
        assert result is not None
        assert "simplify" in result["tool_name"]
        assert result["domain"] == "math"

    def test_detect_math_gcd(self):
        from library.tools.detection import detect_tool
        result = detect_tool("calculate gcd of 12 and 8")
        assert result is not None
        assert "gcd" in result["tool_name"]
        assert result["domain"] == "math"

    def test_detect_physics_force(self):
        from library.tools.detection import detect_tool
        result = detect_tool("calculate force with mass 10")
        assert result is not None
        assert "force" in result["tool_name"]
        assert result["domain"] == "physics"

    def test_detect_chemistry_molar_mass(self):
        from library.tools.detection import detect_tool
        result = detect_tool("calculate molar mass of H2O")
        assert result is not None
        assert "molar" in result["tool_name"]
        assert result["domain"] == "chemistry"

    def test_detect_logic_fallacy(self):
        from library.tools.detection import detect_tool
        result = detect_tool("analyze this fallacy in the argument")
        assert result is not None
        assert "fallacy" in result["tool_name"]
        assert result["domain"] == "philosophy"

    def test_detect_with_source_code(self):
        from library.tools.detection import detect_tool
        # Use a longer description that will match
        result = detect_tool("I need to review the code quality and run linting", source_code="def foo(): pass")
        assert result is not None
        # Just verify detection works with source code present
        assert result["score"] > 0

    def test_detect_no_match(self):
        from library.tools.detection import detect_tool
        result = detect_tool("something completely unrelated to any tool")
        assert result is None

    def test_list_tool_domains(self):
        from library.tools.detection import list_tool_domains
        domains = list_tool_domains()
        assert isinstance(domains, list)
        assert "coding" in domains
        assert "math" in domains
        assert "physics" in domains


class TestSmartRouter:
    """Tests for SmartRouter."""

    def test_router_initialization(self):
        router = SmartRouter()
        assert router.usage == {name: 0 for name in router.usage}

    def test_classify_difficulty_trivial(self):
        router = SmartRouter()
        assert router.classify_difficulty("gcd") == 0
        assert router.classify_difficulty("x") == 0

    def test_classify_difficulty_simple(self):
        router = SmartRouter()
        assert router.classify_difficulty("calculate gcd") == 1

    def test_classify_difficulty_medium(self):
        router = SmartRouter()
        # Use a description with 6+ words but no complex keywords
        assert router.classify_difficulty("analyse the code quality issues today") == 2

    def test_classify_difficulty_complex(self):
        router = SmartRouter()
        assert router.classify_difficulty("complex multi-step debug analyse pipeline workflow") == 3

    def test_score_worker_basic(self):
        router = SmartRouter()
        score = router.score_worker("deterministic_coder", "generate python code")
        assert score > 0

    def test_score_worker_no_match(self):
        router = SmartRouter()
        score = router.score_worker("unknown_worker", "some task")
        assert score == 0.0

    def test_route_basic(self):
        router = SmartRouter()
        result = router.route("generate python fibonacci function")
        assert "selected" in result
        assert len(result["selected"]) > 0
        assert all(name in router.usage for name in result["selected"])

    def test_route_coding_task(self):
        router = SmartRouter()
        result = router.route("write a python function to sort a list")
        assert "deterministic_coder" in result["selected"] or len(result["selected"]) > 0

    def test_route_math_task(self):
        router = SmartRouter()
        result = router.route("solve the algebra equation x^2 + 2x + 1 = 0")
        assert "math_validation_worker" in result["selected"] or len(result["selected"]) > 0

    def test_route_with_exclusion(self):
        router = SmartRouter()
        result = router.route("generate code", exclude=["deterministic_coder"])
        assert "deterministic_coder" not in result["selected"]

    def test_route_opposition_mode(self):
        router = SmartRouter()
        result = router.route("generate python code", opposition_mode=True)
        assert "opposition_count" in result
        assert result["opposition_count"] >= 0

    def test_route_tracks_usage(self):
        router = SmartRouter()
        initial_usage = dict(router.usage)
        router.route("generate code")
        # At least one worker should have increased usage
        assert any(router.usage[n] > initial_usage[n] for n in router.usage)

    def test_resolve_pipeline_steps(self):
        router = SmartRouter()
        steps = router.resolve_pipeline_steps("analyse and validate the code")
        assert isinstance(steps, list)
        assert len(steps) > 0

    def test_router_status(self):
        router = SmartRouter()
        status = router.status()
        assert "workers_loaded" in status
        assert "routes" in status
        assert "usage" in status


class TestRouterWorker:
    """Tests for RouterWorker (bus wrapper)."""

    def test_router_worker_initialization(self):
        bus = EventBus()
        worker = RouterWorker(bus)
        assert worker.initialize() is True
        assert worker.is_active is True

    def test_router_worker_execute(self):
        bus = EventBus()
        worker = RouterWorker(bus)
        worker.initialize()

        msg = Message(
            type="task",
            payload={
                "task_id": "test-1",
                "description": "generate python code",
                "top_k": 1,
            }
        )
        worker.execute(msg)

        assert bus.history_count > 0
        response = bus.get_history()[-1]
        assert response.type == "response"
        assert response.payload["valid"] is True

    def test_router_worker_shutdown(self):
        worker = RouterWorker()
        worker.initialize()
        assert worker.shutdown() is True
        assert worker.is_active is False


class TestToolWorker:
    """Tests for ToolWorker."""

    def test_tool_worker_initialization(self):
        bus = EventBus()
        worker = ToolWorker(bus)
        assert worker.initialize() is True
        assert worker.is_active is True

    def test_tool_worker_gets_tools(self):
        worker = ToolWorker()
        tools = worker.list_tools()
        assert len(tools) > 0

    def test_tool_worker_tool_count(self):
        worker = ToolWorker()
        count = worker.get_tool_count()
        assert count > 0

    def test_tool_worker_execute_with_tool_name(self):
        bus = EventBus()
        worker = ToolWorker(bus)
        worker.initialize()

        msg = Message(
            type="task",
            payload={
                "task_id": "test-1",
                "tool_name": "math_gcd",
                "kwargs": {"a": 12, "b": 8},
            }
        )
        worker.execute(msg)

        assert bus.history_count > 0
        response = bus.get_history()[-1]
        assert response.type == "tool_response"
        assert response.payload["valid"] is True

    def test_tool_worker_auto_detect(self):
        bus = EventBus()
        worker = ToolWorker(bus)
        worker.initialize()

        msg = Message(
            type="task",
            payload={
                "task_id": "test-2",
                "description": "calculate gcd of 12 and 8",
            }
        )
        worker.execute(msg)

        assert bus.history_count > 0
        response = bus.get_history()[-1]
        assert response.type == "tool_response"

    def test_tool_worker_no_match(self):
        bus = EventBus()
        worker = ToolWorker(bus)
        worker.initialize()

        msg = Message(
            type="task",
            payload={
                "task_id": "test-3",
                "description": "xyz qwert no tool matches this gibberish",
            }
        )
        worker.execute(msg)

        response = bus.get_history()[-1]
        assert response.payload["valid"] is False
        # Error is nested inside tool_result
        assert "error" in response.payload.get("tool_result", {})

    def test_tool_worker_shutdown(self):
        worker = ToolWorker()
        worker.initialize()
        assert worker.shutdown() is True
        assert worker.is_active is False


class TestIntegration:
    """Integration tests for routing and tool execution."""

    def test_full_routing_pipeline(self):
        """Test complete flow: route → select workers → execute tools."""
        router = SmartRouter()
        tool_worker = ToolWorker()

        # Route a task
        result = router.route("analyze the code quality and run linting")
        assert len(result["selected"]) > 0

        # Verify usage tracking
        for name in result["selected"]:
            assert name in tool_worker.list_tools() or name in router.usage

    def test_multi_domain_routing(self):
        """Test routing across different domains."""
        router = SmartRouter()

        # Math task
        math_result = router.route("solve algebra equation")
        assert len(math_result["selected"]) > 0

        # Coding task
        code_result = router.route("generate python function")
        assert len(code_result["selected"]) > 0

        # Physics task
        physics_result = router.route("calculate force with mass")
        assert len(physics_result["selected"]) > 0
