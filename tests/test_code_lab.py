"""Code Lab — unit & integration tests (Phase 13).

Covers the milestone pipeline plus failure cases. Deterministic; no LLM.
"""

from __future__ import annotations

import subprocess
import sys
import threading

import pytest

from code_lab.config import CodeLabConfig
from code_lab.workspace import CodeLabWorkspace, WorkspaceError
from code_lab.generator import detect_plan, generate, generate_files, PLANS
from code_lab.engine import build_default_engine, CodeLabEngine
from code_lab.controller import CodeLabController


@pytest.fixture(scope="module")
def base_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("code_lab_runs")


# ── config ────────────────────────────────────────────────────────────────
class TestConfig:
    def test_defaults_and_roundtrip(self):
        cfg = CodeLabConfig()
        d = cfg.to_dict()
        cfg2 = CodeLabConfig.from_dict(d)
        assert cfg2.run_id == cfg.run_id
        assert cfg2.max_iterations == cfg.max_iterations

    def test_bool_from_string(self):
        cfg = CodeLabConfig.from_dict({"multi_agent": "true", "run_tests": "on"})
        assert cfg.multi_agent is True
        assert cfg.run_tests is True


# ── workspace ─────────────────────────────────────────────────────────────
class TestWorkspace:
    def test_isolated_layout(self, base_dir):
        cfg = CodeLabConfig(run_id="ws_1")
        ws = CodeLabWorkspace(cfg, base_dir=base_dir).create()
        assert ws.workspace.exists()
        assert ws.raw.exists()
        assert ws.metadata_path.exists()

    def test_write_read_roundtrip(self, base_dir):
        cfg = CodeLabConfig(run_id="ws_2")
        ws = CodeLabWorkspace(cfg, base_dir=base_dir).create()
        ws.write_text("src/mod.py", "x = 1\n")
        assert ws.read_text("src/mod.py") == "x = 1\n"

    def test_path_escape_blocked(self, base_dir):
        cfg = CodeLabConfig(run_id="ws_3")
        ws = CodeLabWorkspace(cfg, base_dir=base_dir).create()
        with pytest.raises(WorkspaceError):
            ws.resolve("../../outside.py")

    def test_absolute_host_path_blocked(self, base_dir):
        cfg = CodeLabConfig(run_id="ws_4")
        ws = CodeLabWorkspace(cfg, base_dir=base_dir).create()
        with pytest.raises(WorkspaceError):
            ws.resolve("C:\\Users\\evil.py")

    def test_command_allowlist(self, base_dir):
        cfg = CodeLabConfig(run_id="ws_5")
        ws = CodeLabWorkspace(cfg, base_dir=base_dir).create()
        ws.assert_command_allowed(["python", "-m", "pytest"])
        with pytest.raises(WorkspaceError):
            ws.assert_command_allowed(["rm", "-rf", "/"])

    def test_raw_immutable_snapshot(self, base_dir):
        cfg = CodeLabConfig(run_id="ws_6")
        ws = CodeLabWorkspace(cfg, base_dir=base_dir).create()
        ws.write_raw_snapshot("final", {"a": 1})
        with pytest.raises(WorkspaceError):
            ws.write_raw_snapshot("final", {"a": 2})  # immutable

    def test_append_raw_jsonl(self, base_dir):
        cfg = CodeLabConfig(run_id="ws_7")
        ws = CodeLabWorkspace(cfg, base_dir=base_dir).create()
        ws.append_raw("traj", {"it": 1})
        ws.append_raw("traj", {"it": 2})
        assert [e["it"] for e in ws.read_raw("traj")] == [1, 2]


# ── generator ─────────────────────────────────────────────────────────────
class TestGenerator:
    @pytest.mark.parametrize("plan", [p for p in PLANS if p != "generic"])
    def test_generated_code_passes_real_pytest(self, plan, tmp_path):
        src_name, test_name = PLANS[plan]
        src, tests = generate(plan)
        (tmp_path / src_name).write_text(src)
        (tmp_path / test_name).write_text(tests)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
            cwd=str(tmp_path), capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_detect_plan_fibonacci(self):
        assert detect_plan("Create a Python function fibonacci(n) with unit tests")[0] == "fibonacci"

    def test_detect_plan_generic_fallback(self):
        assert detect_plan("anything at all here")[0] == "generic"

    def test_generate_unknown_raises(self):
        with pytest.raises(Exception):
            generate("not_a_plan")


# ── engine integration (milestone) ───────────────────────────────────────
class TestEngineE2E:
    def test_fibonacci_run_passes(self, base_dir):
        # Forced deterministic (GOAL 3): the engine is authoritative and
        # reproducible independent of a live LLM. The judge is therefore
        # honestly unavailable (rule 15/6).
        cfg = CodeLabConfig(
            run_id="e2e_fib",
            prompt="Create a Python function fibonacci(n) with unit tests.",
            multi_agent=False,
        )
        eng = build_default_engine(cfg, base_dir=base_dir)
        res = eng.run()
        assert res["status"] == "passed", res
        assert res["plan"]["plan_id"] == "fibonacci"
        assert "fibonacci.py" in res["files_created"]
        assert res["tests_last_passed"] is True
        assert res["validation"]["deterministic_validation"] is True
        # Judge honesty (rule 15/6)
        assert "unavailable" in res["judge_validation"]
        # Events observable (rule 14)
        types = [e["type"] for e in eng.events]
        assert "RUN_STARTED" in types and "TEST_PASSED" in types and "RUN_COMPLETED" in types

    def test_raw_persisted_immutable(self, base_dir):
        cfg = CodeLabConfig(run_id="e2e_raw", prompt="Create a Python function is_prime(n) with unit tests.", multi_agent=False)
        eng = build_default_engine(cfg, base_dir=base_dir)
        eng.run()
        raw_dir = base_dir / "e2e_raw" / "raw"
        assert (raw_dir / f"run_e2e_raw.json").exists()
        assert (raw_dir / "trajectory.jsonl").exists()
        assert len((raw_dir / "trajectory.jsonl").read_text().splitlines()) >= 1

    def test_empty_prompt_uses_default(self, base_dir):
        # default prompt still works with a fresh run id (deterministic)
        cfg = CodeLabConfig(run_id="e2e_default", multi_agent=False)
        eng = build_default_engine(cfg, base_dir=base_dir)
        res = eng.run()
        assert res["status"] == "passed", res

    def test_run_isolated_to_workspace(self, base_dir):
        "Generated files appear only under the run workspace."
        cfg = CodeLabConfig(run_id="e2e_iso", prompt="Create a Python function fibonacci(n) with unit tests.", multi_agent=False)
        eng = build_default_engine(cfg, base_dir=base_dir)
        eng.run()
        files = (base_dir / "e2e_iso" / "workspace").rglob("*.py")
        rel = {str(p.relative_to(base_dir / "e2e_iso" / "workspace")) for p in files}
        assert any(str(f).startswith("fibonacci") for f in rel)


# ── controller ────────────────────────────────────────────────────────────
class TestController:
    def test_create_list_get(self, base_dir):
        ctl = CodeLabController(base_dir=base_dir)
        cfg = CodeLabConfig(run_id="ctl_1")
        view = ctl.create_run(cfg)
        assert ctl.get_run("ctl_1")["status"] == "pending"
        assert any(r["run_id"] == "ctl_1" for r in ctl.list_runs())

    def test_stop_unknown_returns_false(self, base_dir):
        ctl = CodeLabController(base_dir=base_dir)
        assert ctl.stop_run("nope") is False

    def test_start_wait_synchronous_result(self, base_dir):
        ctl = CodeLabController(base_dir=base_dir)
        cfg = CodeLabConfig(
            run_id="ctl_sync",
            prompt="Create a Python function palindrome() with unit tests.",
            multi_agent=False,  # deterministic authority (rule 6)
        )
        ctl.create_run(cfg)
        res = ctl.start_run(cfg.run_id, wait=True)
        assert res is not None
        assert res["status"] == "passed"

    def test_read_file_and_list_files(self, base_dir):
        ctl = CodeLabController(base_dir=base_dir)
        cfg = CodeLabConfig(run_id="ctl_files",
                            prompt="Create a Python function fibonacci(n) with unit tests.",
                            multi_agent=False)  # deterministic authority (rule 6)
        ctl.create_run(cfg)
        ctl.start_run(cfg.run_id, wait=True)
        files = ctl.list_files("ctl_files")
        assert "fibonacci.py" in files
        assert "def fibonacci" in ctl.read_file("ctl_files", "fibonacci.py")
