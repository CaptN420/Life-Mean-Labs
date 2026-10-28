"""Tests for TaskScheduler."""
import json
import pytest
from core.workers.task_scheduler import (
    Task, TaskScheduler, TaskStatus, CircularDependencyError, ValidationError
)


class TestValidation:
    """Test task validation."""

    def test_valid_tasks(self):
        sched = TaskScheduler()
        sched.add_task(Task("a", 1, 1, []))
        sched.add_task(Task("b", 2, 2, ["a"]))
        sched.validate()  # should not raise

    def test_duplicate_id_raises(self):
        sched = TaskScheduler()
        sched.add_task(Task("a", 1, 1, []))
        with pytest.raises(ValidationError, match="Duplicate"):
            sched.add_task(Task("a", 2, 2, []))

    def test_missing_dependency_raises(self):
        sched = TaskScheduler()
        sched.add_task(Task("a", 1, 1, ["nonexistent"]))
        with pytest.raises(ValidationError, match="dependency.*does not exist"):
            sched.validate()

    def test_negative_duration_raises(self):
        sched = TaskScheduler()
        sched.add_task(Task("a", -1, 1, []))
        with pytest.raises(ValidationError):
            sched.validate()


class TestCircularDependencies:
    """Test cycle detection."""

    def test_cycle_a_b_c_a(self):
        sched = TaskScheduler()
        sched.add_task(Task("a", 1, 1, ["c"]))
        sched.add_task(Task("b", 1, 1, ["a"]))
        sched.add_task(Task("c", 1, 1, ["b"]))
        with pytest.raises(CircularDependencyError):
            sched.validate()

    def test_self_dependency(self):
        sched = TaskScheduler()
        sched.add_task(Task("a", 1, 1, ["a"]))
        with pytest.raises(CircularDependencyError):
            sched.validate()


class TestBasicExecution:
    """Test basic task execution."""

    def test_sequential_chain(self):
        """load(2) -> clean(1) -> analyze(3) -> report(1) = total 7."""
        sched = TaskScheduler(max_workers=2)
        for t in [
            Task("load", 2, 3, []),
            Task("clean", 1, 2, ["load"]),
            Task("analyze", 3, 5, ["clean"]),
            Task("report", 1, 1, ["analyze"]),
        ]:
            sched.add_task(t)
        sched.validate()
        report = sched.run()

        assert report["tasks"]["load"]["status"] == "completed"
        assert report["tasks"]["load"]["start_time"] == 0
        assert report["tasks"]["load"]["end_time"] == 2
        assert report["tasks"]["clean"]["start_time"] == 2
        assert report["tasks"]["clean"]["end_time"] == 3
        assert report["tasks"]["analyze"]["start_time"] == 3
        assert report["tasks"]["analyze"]["end_time"] == 6
        assert report["tasks"]["report"]["start_time"] == 6
        assert report["tasks"]["report"]["end_time"] == 7
        assert report["total_duration"] == 7

    def test_parallel_independent_tasks(self):
        """backup and load run in parallel, total = max(2,2) + rest."""
        sched = TaskScheduler(max_workers=2)
        for t in [
            Task("load", 2, 3, []),
            Task("backup", 2, 4, []),
            Task("clean", 1, 2, ["load"]),
            Task("analyze", 3, 5, ["clean"]),
            Task("report", 1, 1, ["analyze"]),
        ]:
            sched.add_task(t)
        sched.validate()
        report = sched.run()

        # load and backup start at 0, both finish at 2
        assert report["tasks"]["load"]["start_time"] == 0
        assert report["tasks"]["backup"]["start_time"] == 0
        assert report["tasks"]["backup"]["end_time"] == 2
        # total should be 7 (same as sequential since backup finishes same time)
        assert report["total_duration"] == 7

    def test_priority_ordering(self):
        """Higher priority tasks should start first when multiple available."""
        sched = TaskScheduler(max_workers=2)
        for t in [
            Task("low", 1, 1, []),
            Task("high", 1, 5, []),
            Task("mid", 1, 3, []),
        ]:
            sched.add_task(t)
        sched.validate()
        report = sched.run()

        # high (priority 5) and mid (priority 3) should start before low
        events = report["events"]
        start_events = [e for e in events if e["event_type"] == "started"]
        assert start_events[0]["task_id"] == "high"
        assert start_events[1]["task_id"] == "mid"


class TestFailureHandling:
    """Test failure and blocking behavior."""

    def test_task_failure_blocks_dependents(self):
        """If load fails, clean and analyze are blocked."""
        sched = TaskScheduler(max_workers=2)
        for t in [
            Task("load", 2, 3, []),
            Task("clean", 1, 2, ["load"]),
            Task("analyze", 3, 5, ["clean"]),
            Task("report", 1, 1, ["analyze"]),
            Task("backup", 2, 4, []),
        ]:
            sched.add_task(t)
        sched.validate()
        report = sched.run(failures={"load": 1})

        assert report["tasks"]["load"]["status"] == "failed"
        assert report["tasks"]["clean"]["status"] == "blocked"
        assert report["tasks"]["analyze"]["status"] == "blocked"
        assert report["tasks"]["report"]["status"] == "blocked"
        # backup should still complete independently
        assert report["tasks"]["backup"]["status"] == "completed"

    def test_independent_tasks_continue_after_failure(self):
        """Unrelated tasks should complete even if one fails."""
        sched = TaskScheduler(max_workers=2)
        for t in [
            Task("a", 1, 1, []),
            Task("b", 1, 2, []),
            Task("c", 1, 3, ["a"]),
        ]:
            sched.add_task(t)
        sched.validate()
        report = sched.run(failures={"a": 1})

        assert report["tasks"]["a"]["status"] == "failed"
        assert report["tasks"]["b"]["status"] == "completed"
        assert report["tasks"]["c"]["status"] == "blocked"


class TestRetryBonus:
    """Test retry mechanism (bonus)."""

    def test_retry_succeeds(self):
        """Task fails once, succeeds on retry."""
        sched = TaskScheduler(max_workers=2)
        task = Task("flaky", 1, 1, [], max_retries=1, retry_delays=[0])
        sched.add_task(task)
        sched.validate()
        report = sched.run(failures={"flaky": 1})

        assert report["tasks"]["flaky"]["status"] == "completed"
        assert report["tasks"]["flaky"]["attempts"] == 2

    def test_retry_exhausted(self):
        """Task fails all attempts including retries."""
        sched = TaskScheduler(max_workers=2)
        task = Task("broken", 1, 1, [], max_retries=1, retry_delays=[0])
        sched.add_task(task)
        sched.validate()
        report = sched.run(failures={"broken": 2})

        assert report["tasks"]["broken"]["status"] == "failed"
        assert report["tasks"]["broken"]["attempts"] == 2


class TestExportJSON:
    """Test JSON export."""

    def test_export_json(self, tmp_path):
        sched = TaskScheduler()
        sched.add_task(Task("a", 1, 1, []))
        sched.validate()
        path = str(tmp_path / "report.json")
        sched.export_json(path)
        data = json.loads(Path(path).read_text())
        assert "tasks" in data
        assert "a" in data["tasks"]


from pathlib import Path
