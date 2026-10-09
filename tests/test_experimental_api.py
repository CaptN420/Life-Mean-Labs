"""Experimental sandbox API tests — human-gated flow at the handler level.

Proves the wiring: create DRAFT -> no run before FROZEN -> freeze ->
run dispatches to the real adapters (or an injected engine), and an
unconnected stage fails honestly with EXECUTOR_NOT_AVAILABLE.
"""

import pytest

from experimental import (
    DesignAgent,
    DesignStage,
    ExperimentDesign,
    ExperimentDesignStore,
    ExperimentalApiMixin,
)


class _FakeHandler(ExperimentalApiMixin):
    """Minimal handler exposing just the JSON/error sinks the mixin needs."""

    def __init__(self):
        self.experimental_store = ExperimentDesignStore()
        self.experimental_engine = None  # falls back to build_engine()
        self._status = None
        self._json = None
        self._code = None
        self._err = None
        self._err_code = None

    def _send_json(self, data):
        self._status = 200
        self._json = data

    def _send_error(self, status, message, code="error", request_id=None):
        self._code = status
        self._err_code = code
        self._err = message


def _proposal_payload():
    return {"description": "Explore whether small heterogeneous agents can discover "
                           "edge cases in a sorting algorithm better than one solver."}


def _frozen_tool_design():
    st = DesignStage(stage_id="s1", executor_type="deterministic",
                     config={"tool": "math_gcd", "args": {"a": 12, "b": 8}},
                     participants=["a1"])
    return ExperimentDesign(
        research_question="compute gcd(12,8)",
        agents=[DesignAgent(agent_id="a1", role="experimentalist")],
        stages=[st]).approve().freeze()


# ── create DRAFT only; never executes ──────────────────────────────────────
def test_api_create_draft_only():
    h = _FakeHandler()
    h._experimental_design_create(_proposal_payload())
    assert h._status == 200
    assert h._json["status"] == "DRAFT"
    design_id = h._json["design_id"]
    # a proposal must not be directly runnable
    h._experimental_design_run(design_id)
    assert h._code == 400 and h._err_code == "DESIGN_INVALID"


def test_api_create_requires_description():
    h = _FakeHandler()
    h._experimental_design_create({"description": "  "})
    assert h._code == 400 and h._err_code == "designer_input"


# ── freeze gate at the API ─────────────────────────────────────────────────
def test_api_freeze_then_run_dispatch_to_real_tool():
    h = _FakeHandler()
    d = h.experimental_store.save(_frozen_tool_design())
    h._experimental_design_run(d.design_id)
    assert h._status == 200
    assert h._json["status"] == "COMPLETED"
    assert h._json["stages"][0]["result"]["dispatched_to"] == "ToolWorker"
    assert h._json["stages"][0]["result"]["result"]["valid"] is True


def test_api_frozen_cannot_transition():
    h = _FakeHandler()
    d = h.experimental_store.save(_frozen_tool_design())
    h._experimental_design_transition(d.design_id, {"target": "REJECTED"})
    assert h._code == 400 and h._err_code == "invalid_transition"


def test_api_unconnected_stage_fails_honestly():
    # designer proposal stages include research / synthesis (NOT connected):
    # running a frozen proposal must fail with EXECUTOR_NOT_AVAILABLE, never fake.
    h = _FakeHandler()
    h._experimental_design_create(_proposal_payload())
    design_id = h._json["design_id"]
    h._experimental_design_transition(design_id, {"target": "APPROVED"})
    h._experimental_design_transition(design_id, {"target": "FROZEN"})
    assert h._json["frozen"] is True
    h._experimental_design_run(design_id)
    assert h._code == 422 and h._err_code == "EXECUTOR_NOT_AVAILABLE"
    assert "EXPERIMENT_COMPLETED" not in (h._err or "")


def test_api_full_completed_with_injected_engine():
    h = _FakeHandler()
    d = h.experimental_store.save(_frozen_tool_design())
    calls = []

    class _E:
        def run(self, design):
            calls.append(design.is_frozen)
            return {"design_id": design.design_id, "version": design.version,
                    "status": "COMPLETED", "stages": []}

    h.experimental_engine = _E()
    h._experimental_design_run(d.design_id)
    assert h._status == 200 and h._json["status"] == "COMPLETED"
    assert calls == [True]  # engine only ever received a FROZEN design


def test_api_capabilities_lists_connected_executors():
    h = _FakeHandler()
    h._experimental_capabilities()
    assert h._status == 200
    assert "CodeLabEngine" in {e["engine"] for e in h._json["executors"].values()}
    assert "code" in h._json["connected_executors"]
    assert "debate" not in h._json["connected_executors"]  # not connected now


def test_api_store_dict_isolation():
    store = ExperimentDesignStore()
    d = store.save(_frozen_tool_design())
    got = store.get(d.design_id)
    assert got.design_id == d.design_id and got.is_frozen
    assert len(store.list()) == 1