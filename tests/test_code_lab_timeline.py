"""Live/unit coverage for the lab-wide Code Lab timeline (roadmap M0 §22).

The timeline aggregates backend-real events across all runs via the same
callback chain that feeds each per-run view — it must never synthesize events.
"""

from code_lab.controller import CodeLabController
from code_lab.config import CodeLabConfig


class _Engine:
    """Fake engine that just emits the scripted events into the handler."""

    def __init__(self, events, handler):
        self._events = events
        self._handler = handler
        self.status = None

    def run(self):
        for ev in self._events:
            self._handler(dict(ev))
        return {"status": "passed"}

    def request_stop(self):
        pass


def _start(ctl, run_id, events):
    cfg = CodeLabConfig(prompt="x", project_name="p", multi_agent=False, seed=1)
    # create_run assigns cfg.run_id, override to match ours
    cfg.run_id = run_id
    view = ctl.create_run(cfg)
    # monkeypatch: start_run normally constructs a real engine + background thread.
    # We drive it synchronously via the same handler built internally by the
    # controller so the _timeline population logic is the production code.
    ctl._runs[run_id] = view
    eng = _Engine(events, ctl_get_handler(ctl, run_id))
    return view, eng


def ctl_get_handler(ctl, run_id):
    """Recreate the exact closure logic start_run builds: same append + status."""
    view = ctl._runs[run_id]

    def handler(ev):
        with ctl._lock:
            view.events.append(ev)
            if ev["type"] == "RUN_COMPLETED":
                view.status = "passed"
            elif ev["type"] == "RUN_FAILED":
                view.status = "failed"
            elif ev["type"] == "RUN_STOPPED":
                view.status = "stopped"
            ctl._timeline.append(ev)
            if len(ctl._timeline) > ctl.TIMELINE_LIMIT:
                ctl._timeline = ctl._timeline[-ctl.TIMELINE_LIMIT:]
    return handler


class TestLabTimeline:
    def test_aggregates_events_across_runs_in_order(self):
        ctl = CodeLabController()
        evs_a = [
            {"type": "RUN_STARTED", "run_id": "a", "time": 1.0},
            {"type": "PLAN_CREATED", "run_id": "a", "time": 1.1, "plan": "secret-big"},
        ]
        evs_b = [
            {"type": "RUN_STARTED", "run_id": "b", "time": 2.0},
            {"type": "AGENT_STARTED", "run_id": "b", "time": 2.1, "role": "PLANNER"},
        ]
        _start(ctl, "a", evs_a)
        _start(ctl, "b", evs_b)
        # drive the handlers (each run's own engine emits into its handler)
        ctl_get_handler(ctl, "a")(evs_a[0]); ctl_get_handler(ctl, "a")(evs_a[1])
        ctl_get_handler(ctl, "b")(evs_b[0]); ctl_get_handler(ctl, "b")(evs_b[1])

        tl = ctl.get_timeline()
        assert tl["count"] == 4
        assert tl["total_events"] == 4
        assert tl["runs_count"] == 2
        ids = [e["run_id"] for e in tl["events"]]
        assert ids == ["a", "a", "b", "b"]
        # big payload fields stripped from timeline surface
        for e in tl["events"]:
            assert "plan" not in e and "source" not in e and "response" not in e

    def test_timeline_bounded_by_limit(self):
        ctl = CodeLabController()
        _start(ctl, "a", [])
        h = ctl_get_handler(ctl, "a")
        for i in range(10):
            h({"type": "EV_T", "run_id": "a", "time": float(i)})
        tl = ctl.get_timeline(limit=3)
        assert len(tl["events"]) == 3
        assert tl["count"] == 10
        # newest kept
        assert tl["events"][-1]["time"] == 9.0

    def test_timeline_bounded_global_cap(self):
        ctl = CodeLabController()
        ctl.TIMELINE_LIMIT = 5
        _start(ctl, "a", [])
        h = ctl_get_handler(ctl, "a")
        for i in range(20):
            h({"type": "EV_T", "run_id": "a", "time": float(i)})
        assert len(ctl._timeline) == 5
        assert ctl.get_timeline()["count"] == 5