"""Code Lab free-form (generic) validation — regression tests.

Verifies the pass that removed the invented `run()->str` oracle for arbitrary
tasks (§1-4, §8, §10, §11, §12): free-form projects are validated with truthful
structural checks (syntax/compile + expected files), never against a fabricated
`from main import run` contract. Known templates keep their strong oracle.
"""

from __future__ import annotations

from pathlib import Path

from code_lab.config import CodeLabConfig
from code_lab.engine import build_default_engine
from code_lab.multiagent import CodingMultiAgent
from test_code_lab_multiagent import _FakeLLM

PLAN = "```text\nfree-form plan: build a tetris game\n```\n"
# Valid arbitrary code that has NO run()->str contract (a Tetris board lib).
TETRIS_SRC = "```python\nclass Board:\n    def __init__(self):\n        self.grid = [[0]*10 for _ in range(20)]\n    def clear_lines(self):\n        n = 0\n        for row in self.grid:\n            if all(cell for cell in row):\n                n += 1\n        return n\n```\n"
BROKEN_SRC = "```python\ndef broken(:\n    pass\n```\n"


def _ma_engine(tmp_path, src, script_extra=None):
    """A multi-agent engine whose DEVELOPER returns `src` for a free-form task."""
    script = script_extra or [(PLAN, "stop"), (src, "stop")]
    cfg = CodeLabConfig(run_id="ff_tetris", multi_agent=True, max_iterations=2,
                        prompt="create a tetris game")
    engine = build_default_engine(cfg, base_dir=tmp_path)
    engine._check_llm_availability = lambda: {
        "llm_available": True, "llm_error": None, "llm_models": ["stub-model"]}
    engine._new_coding_multi_agent = lambda: CodingMultiAgent(
        "http://fake/v1", "", llm_client=_FakeLLM(script=script),
        on_event=engine._agent_event, run_id=cfg.run_id)
    return engine, cfg


def test_tetris_freeform_no_invented_run_oracle(tmp_path):
    """§8: a valid arbitrary project is NOT rejected for lacking a run()->str."""
    engine, cfg = _ma_engine(tmp_path, TETRIS_SRC)
    res = engine.run()

    # classified as free-form / generic
    assert res["plan"]["plan_id"] == "generic"
    # no invented oracle test file, no run()->str requirement anywhere
    assert "test_main.py" not in res["files_created"]
    ws_files = [str(f.relative_to(engine.ws.root))
                for f in Path(engine.ws.root).rglob("*") if f.is_file()]
    assert not any("test_main" in f for f in ws_files)
    for f in ws_files:
        text = Path(engine.ws.root, f).read_text(encoding="utf-8")
        assert "from main import run" not in text, f"invented oracle leaked into {f}"

    # truthful structural validation: the compilable tetris code is accepted
    assert res["status"] == "passed"
    assert res["validator_protocol"] == "code-lab-v2-freeform"
    det = res["validation"]["details"]
    assert det["syntax_validation"] == "PASS"
    assert det["generated_tests"] == "NOT_AVAILABLE"
    assert det["task_semantic_validation"] == "NOT_AVAILABLE"
    assert res["validation"]["deterministic_validation"] is True


def test_freeform_parse_failure_is_honest_fail(tmp_path):
    """§2/§12: syntactically invalid free-form output fails structurally, honestly."""
    engine, cfg = _ma_engine(tmp_path, BROKEN_SRC)
    res = engine.run()
    assert res["status"] == "failed"
    assert res["validator_protocol"] == "code-lab-v2-freeform"
    det = res["validation"]["details"]
    assert det["syntax_validation"] == "FAIL"
    assert det["task_semantic_validation"] == "NOT_AVAILABLE"
    assert res["validation"]["deterministic_validation"] is False


def test_known_template_oracle_preserved(tmp_path):
    """§10: deterministic fibonacci still uses its strong oracle (no LLM)."""
    cfg = CodeLabConfig(run_id="ff_fib", multi_agent=False,
                        prompt="Create a Python function fibonacci(n) with unit tests.")
    engine = build_default_engine(cfg, base_dir=tmp_path)
    res = engine.run()
    assert res["status"] == "passed"
    assert res["execution_mode"] == "deterministic"
    assert res["validator_protocol"] == "code-lab-v2-known"
    # the template test file IS written and ran for a known contract
    assert "test_fibonacci.py" in res["files_created"]
    assert res["validation"]["deterministic_validation"] is True


def test_known_template_uses_oracle_not_freeform(tmp_path):
    """§3: a known contract must NOT be downgraded to free-form structural."""
    cfg = CodeLabConfig(run_id="ff_fact", multi_agent=False,
                        prompt="write factorial function")
    engine = build_default_engine(cfg, base_dir=tmp_path)
    res = engine.run()
    assert res["plan"]["plan_id"] == "factorial"
    assert res["validator_protocol"] == "code-lab-v2-known"
    assert "test_factorial.py" in res["files_created"]