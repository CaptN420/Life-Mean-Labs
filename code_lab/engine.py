"""Code Lab engine (V1).

Orchestrates a Code Lab run over the EXISTING stable core:

    PLANNER  -> detects plan (deterministic template)
    DEVELOPER-> writes generated source+tests into isolated workspace
    VERIFIER -> runs real `pytest` in the workspace (evidence, rule 5)
    CRITIC   -> turns pytest failure into a diagnosis
    REPAIR   -> deterministic fix attempts (retry policy)
    VALIDATE -> OracleValidator on structure / deterministic properties
    RAW      -> RawDebateRecorder + immutable workspace raw snapshots

Judge / SemanticCodeJudge note: the LLM semantic judge is the Code Lab
component `SemanticCodeJudge` (role JUDGE via CodingMultiAgent). It is NOT the
hermes-debate JudgeAgent (absent / not importable from the used code path).
Deterministic validation is always the authority (rule 6); the semantic judge
opinion is stored separately and never overrides it. When the LLM backend is
unavailable (e.g. invalid LM Studio token), the engine records
judge_validation: unavailable rather than faking a judge (rule 15).
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import CodeLabConfig
from .workspace import CodeLabWorkspace, WorkspaceError

logger = logging.getLogger("CodeLab.Engine")

# ── pipeline event types (backend-real, consumed by API/UI) ─────────────
RUN_STARTED = "RUN_STARTED"
PLAN_CREATED = "PLAN_CREATED"
AGENT_STARTED = "AGENT_STARTED"
AGENT_RESPONSE = "AGENT_RESPONSE"
FILE_CREATED = "FILE_CREATED"
FILE_MODIFIED = "FILE_MODIFIED"
TEST_STARTED = "TEST_STARTED"
TEST_FAILED = "TEST_FAILED"
TEST_PASSED = "TEST_PASSED"
CRITIQUE_STARTED = "CRITIQUE_STARTED"
REPAIR_STARTED = "REPAIR_STARTED"
VALIDATION_COMPLETED = "VALIDATION_COMPLETED"
RUN_COMPLETED = "RUN_COMPLETED"
RUN_FAILED = "RUN_FAILED"
RUN_STOPPED = "RUN_STOPPED"
EVENT_TYPES = frozenset({
    RUN_STARTED, PLAN_CREATED, AGENT_STARTED, AGENT_RESPONSE,
    FILE_CREATED, FILE_MODIFIED, TEST_STARTED, TEST_FAILED, TEST_PASSED,
    CRITIQUE_STARTED, REPAIR_STARTED, VALIDATION_COMPLETED,
    RUN_COMPLETED, RUN_FAILED, RUN_STOPPED,
})


def _extract_python_blocks(text: str) -> str:
    """Extract the first ```python ... ``` block from an LLM response.

    Returns "" if none found (caller decides whether to fall back to the raw
    text). Used so agent output becomes a real file (rule 4/5: filesystem is
    the source of truth, not the agent's words).
    """
    if not text:
        return ""
    import re
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    if m:
        return m.group(1).strip()
    return ""


def _is_bare_markdown_garbage(text: str) -> bool:
    """True when a DEVELOPER response cannot become valid source.

    Any text containing a markdown fence (```` ``` ````) that did NOT yield a
    complete block in ``_extract_python_blocks`` is degenerate (e.g. a bare
    "```" or an unclosed fence) and MUST NOT be written as a source file — a
    latent "```" in fibonacci.py is a SyntaxError the CRITIC/repair loop can
    never recover from. Only truly unfenced plain code may fall back to raw.
    """
    if not text:
        return True
    import re
    if re.search(r"```", text):
        return True  # fenced but unparseable (extraction already returned "")
    return False


def _developer_source(resp: str) -> str:
    """Turn a DEVELOPER response into candidate source, returning ``""`` for
    degenerate output (empty, or a markdown fence with no parseable code)."""
    extracted = _extract_python_blocks(resp)
    if extracted:
        return extracted
    if _is_bare_markdown_garbage(resp):
        return ""
    return resp


class CodeLabEngine:
    """Runs a single Code Lab pipeline."""

    def __init__(
        self,
        config: Optional[CodeLabConfig] = None,
        event_handler=None,
        oracle_validator=None,
        raw_recorder=None,
        router=None,
        event_bus=None,
        base_dir: Optional[Path] = None,
        llm_client=None,
    ) -> None:
        """Build an engine. All collaborators are injectable for testing.

        By default, real instances of the existing stable core are wired in
        (SmartRouter, EventBus, OracleValidator, RawDebateRecorder) when the
        relevant package imports succeed; otherwise a plain emitter is used.
        ``llm_client`` lets tests inject a fake LLM client (keeps multi-agent
        runs fully offline/deterministic).
        """
        self.config = config or CodeLabConfig()
        self.event_handler = event_handler
        self.stop_requested = False
        self.base_dir = base_dir
        self.ws: Optional[CodeLabWorkspace] = None

        self.oracle = oracle_validator
        self.recorder = raw_recorder
        self.router = router
        self.event_bus = event_bus
        self.llm_client = llm_client

        self.events: List[Dict[str, Any]] = []
        self._status: str = "idle"

    # ── helpers ───────────────────────────────────────────────────────────
    def _emit(self, event_type: str, **payload: Any) -> None:
        ev = {"type": event_type, "time": time.time(), **payload}
        self.events.append(ev)
        if self.event_handler is not None:
            try:
                self.event_handler(ev)
            except Exception as e:  # pragma: no cover
                logger.warning("event handler raised: %s", e)

    def _ensure_recorder(self):
        if self.recorder is not None:
            return self.recorder
        try:
            from philosophical_council.raw_protocol import RawDebateRecorder
            self.recorder = RawDebateRecorder()
        except Exception as e:  # pragma: no cover
            logger.warning("RawDebateRecorder unavailable (%s)", e)
            self.recorder = None
        return self.recorder

    # Public API used by controller/API
    def request_stop(self) -> None:
        self.stop_requested = True

    @property
    def status(self) -> str:
        return self._status

    # ── core run ──────────────────────────────────────────────────────────
    def run(self) -> Dict[str, Any]:
        """Execute the full Code Lab pipeline, returning the final result."""
        self._t0 = time.time()
        env = self._check_llm_availability()
        # Snapshot the Settings at run start (Settings → snapshot → core → RAW):
        # immutable in the result so later Settings edits never rewrite history.
        self._settings_snapshot = self._capture_settings_snapshot()
        self._status = "starting"
        self._emit(RUN_STARTED, run_id=self.config.run_id, llm_available=env["llm_available"])

        try:
            # Resolve + VALIDATE the versioned Role Template (id / version / hash
            # / executor compatibility) ONLY on the LLM (multi-agent) path. An
            # incompatible template fails with a controlled error instead of a
            # silent fallback (no false provenance). Deterministic mode does NOT
            # use an LLM role template — its provenance records role_template=null.
            if self.config.multi_agent and not getattr(self, "_role_template", None):
                self._role_template = self._resolve_role_template()
            self.ws = CodeLabWorkspace(self.config, base_dir=self.base_dir).create()

            plan = self._plan()
            self._status = "planning_done"

            result = self._execute(plan, env)
            self._status = result["status"]
            # GOAL 4: explicit terminal events — RUN_COMPLETED ONLY on success,
            # RUN_FAILED on failure, RUN_STOPPED already emitted inside
            # _execute for the cancelled case (avoid double-emit).
            if result["status"] == "passed":
                self._emit_terminal(RUN_COMPLETED, result)
            elif result["status"] != "stopped":
                self._emit_terminal(RUN_FAILED, result)
            return result
        except Exception as e:
            logger.exception("Code Lab run failed")
            self._status = "failed"
            self._emit(RUN_FAILED, run_id=self.config.run_id, error=str(e),
                       status="failed", error_count=1,
                       stage_reached="exception", files_created=[], iterations=0)
            return {
                "run_id": self.config.run_id,
                "status": "failed",
                "error": str(e),
                "llm_available": env["llm_available"],
            }

    def _emit_terminal(self, event_type: str, result: Dict[str, Any]) -> None:
        """Emit a structured terminal event (GOAL 4) — never secrets."""
        sj = result.get("semantic_judge", {}) or {}
        rt = result.get("role_template") or {}
        self._emit(
            event_type,
            run_id=self.config.run_id,
            status=result.get("status"),
            stage_reached="failed" if event_type == RUN_FAILED else "completed",
            error_count=len(result.get("errors", [])),
            files_created=result.get("files_created", []),
            iterations=result.get("iterations", 0),
            deterministic_validation=result.get("deterministic_validation_status"),
            semantic_judge_status=sj.get("status"),
            template_id=rt.get("template_id"),
            template_version=rt.get("template_version"),
            template_hash=rt.get("template_hash"),
        )

    def _check_llm_availability(self) -> Dict[str, Any]:
        """Honestly probe whether a real LLM backend is reachable + authenticated.

        Uses the ONE canonical credential resolver (experiments.credentials) then
        falls back to the existing philosophical_council config. The resolved key
        is stored on the engine but NEVER exposed in results/provenance/events.

        DETERMINISTIC mode (multi_agent=False) makes NO network call and does not
        require a backend — deterministic validation must run even when LM Studio
        is stopped / unauthenticated (§7). The probe is only performed on the
        LLM-dependent (multi-agent) path.
        """
        if not self.config.multi_agent:
            return {"llm_available": False, "llm_error": "not used (deterministic)",
                    "llm_models": []}
        from .multiagent import probe_llm, resolve_llm_credentials
        base_url, api_key = resolve_llm_credentials()
        self._llm_base_url = base_url
        self._llm_api_key = api_key
        probe = probe_llm(base_url, api_key)
        available = probe.get("available", False)
        return {
            "llm_available": available,
            "llm_error": probe.get("error"),
            "llm_models": probe.get("models", []) if available else [],
        }

    def _capture_settings_snapshot(self) -> Optional[Dict[str, Any]]:
        """Build the immutable Settings snapshot for this run (never secrets)."""
        try:
            from experiments.settings import build_settings_snapshot
            snap = build_settings_snapshot()
            if snap is not None:
                # Fuse the ACTUAL resolved template into the snapshot so the
                # settings history + the executed template are one record.
                tpl = getattr(self, "_role_template", None)
                snap["resolved_template"] = (None if (tpl is None or not self.config.multi_agent) else {
                    "template_id": tpl.template_id, "version": tpl.version,
                    "hash": tpl.content_hash(), "executor_type": tpl.executor_type,
                })
            return snap
        except Exception:  # pragma: no cover
            return None

    def _new_coding_multi_agent(self):
        """Build a CodingMultiAgent reusing existing ModelConfig (rule 13).

        The team is CONFIGURED from a VERSIONED Role Template (loaded via the
        existing registry): role prompts come from the template, configured
        models come from `CodeLabConfig.role_models` (experiment-level, never
        baked into the template). If the template is missing/unknown, the
        existing default `ROLE_PROMPTS` are used — preserving current behavior.

        Agent events (AGENT_STARTED / AGENT_RESPONSE / AGENT_FAILED) are
        bridged through the engine's own emitter so they land in
        `self.events` AND any external handler — single observability path
        (GOAL 2/11: engine log == UI feed == API events).
        """
        from .multiagent import CodingMultiAgent
        model_config = None
        try:
            from philosophical_council.config import Config
            model_config = Config.default().models
        except Exception:
            model_config = None

        template = getattr(self, "_role_template", None) or self._resolve_role_template()
        self._role_template = template
        # Build role_prompts from the template (upper-cased role ids to match
        # the multi-agent role naming). Missing roles fall back to the defaults.
        role_prompts = {}
        if template is not None:
            role_prompts = {
                r.role_id.upper(): r.instructions_template
                for r in template.roles if r.instructions_template
            }

        ma = CodingMultiAgent(
            base_url=getattr(self, "_llm_base_url", "http://localhost:1234/v1"),
            api_key=getattr(self, "_llm_api_key", ""),
            model_config=model_config,
            on_event=self._agent_event,
            run_id=self.config.run_id,
            role_prompts=role_prompts,
            role_models=dict(self.config.role_models or {}),
            template_id=(template.template_id if template else self.config.template_id),
            template_version=(template.version if template else ""),
            template_hash=(template.content_hash() if template else ""),
            llm_client=getattr(self, "llm_client", None),
        )
        return ma

    def _resolve_role_template(self):
        """Resolve + VALIDATE the configured template against the Code Lab executor.

        Code Lab may only run templates whose ``executor_type == \"code_lab\"`` and
        that carry the minimal executable roles (planner, developer). Anything
        else is rejected with a CONTROLLED error — NEVER a silent fallback to the
        default coding prompts — so provenance can never claim a template ran when
        it did not. (Correction of the false-provenance path.)
        """
        try:
            from role_templates.registry import get_registry
            tpl = get_registry().get_template(self.config.template_id)
        except Exception as e:  # pragma: no cover
            logger.warning("role template registry unavailable: %s", e)
            raise ValueError(
                f"role template registry unavailable while resolving "
                f"'{self.config.template_id}': {e}") from e
        if tpl is None:
            raise ValueError(
                f"unknown role template '{self.config.template_id}' for Code Lab. "
                "Select a Code-Lab-compatible template (e.g. 'coding-standard').")
        if tpl.executor_type != "code_lab":
            raise ValueError(
                f"role template '{self.config.template_id}' is of executor type "
                f"'{tpl.executor_type or 'unspecified'}' — it is NOT compatible with "
                "Code Lab and cannot be run here. Select a Code-Lab template "
                "(e.g. 'coding-standard'). No fallback prompts were used.")
        required = {"planner", "developer"}
        have = {r.role_id for r in tpl.roles}
        missing = sorted(required - have)
        if missing:
            raise ValueError(
                f"role template '{self.config.template_id}' is missing executable "
                f"roles required by Code Lab: {missing}. Rejected before starting.")
        return tpl

    def _agent_event(self, ev: Dict[str, Any]) -> None:
        """Route a multi-agent event into the engine event log + handler."""
        self.events.append(ev)
        if self.event_handler is not None:
            try:
                self.event_handler(ev)
            except Exception as e:  # pragma: no cover
                logger.warning("event handler raised: %s", e)

    def _plan(self) -> Dict[str, Any]:
        """PLANNER: detect plan and (if available) route via SmartRouter.

        NOTE (GOAL 6): `plan_id` is a DETERMINISTIC TEMPLATE classification
        (fibonacci / factorial / ... / generic), not a plan authored by the
        PLANNER LLM. This is surfaced explicitly so the UI never presents
        "generic" as if the Planner agent wrote it. In multi-agent mode the
        real PLANNER runs later and produces its own plan — the template id is
        only a targeting hint, never attributed to the agent.
        """
        from .generator import detect_plan
        plan_id, params = detect_plan(self.config.prompt)
        plan = {
            "plan_id": plan_id,
            "template_plan": plan_id,          # deterministic template classification
            "planner_status": "template",      # not an LLM-authored plan
            "origin": "deterministic_template",
            "params": params,
            "source_target": plan_id if plan_id != "generic" else "main",
        }

        # Record routing decision through the real SmartRouter when available.
        router_decision = None
        if self.router is not None:
            try:
                r = self.router.route(self.config.prompt, top_k=1)
                router_decision = {
                    "selected": r.get("selected") if isinstance(r, dict) else None,
                    "detected_domain": "coding",
                }
            except Exception as e:  # pragma: no cover
                logger.warning("SmartRouter route failed: %s", e)

        self._emit(PLAN_CREATED, run_id=self.config.run_id, plan=plan, router=router_decision)

        # Persist to RAW recorder.
        rec = self._ensure_recorder()
        if rec is not None:
            try:
                meta = rec.start_experiment(
                    task_id=self.config.run_id,
                    dataset_source="code_lab",
                    random_seed=self.config.seed,
                )
                rec.record_input(
                    meta.experiment_id,
                    raw_prompt=self.config.prompt,
                    language=self.config.language,
                    constraints=["isolated-workspace"],
                    generation_params={"max_iterations": self.config.max_iterations},
                )
                self.recorder_experiment_id = meta.experiment_id
            except Exception as e:  # pragma: no cover
                logger.warning("RAW start failed: %s", e)
        return plan

    def _execute(self, plan: Dict[str, Any], env: Dict[str, Any]) -> Dict[str, Any]:
        """DEVELOPER + VERIFIER + CRITIC + REPAIR loop over iterations.

        Two explicit execution modes (never silent):
          - multi_agent (config.multi_agent and llm_available): the generated
            code comes from the REAL LLM DEVELOPER agent; repair uses the REAL
            CRITIC agent. pytest/compile remain the deterministic authority.
          - deterministic: fixed templates, explicitly labeled.
        """
        llm_available = env.get("llm_available", False)
        use_llm = self.config.multi_agent and llm_available

        iterations: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        files_created: List[str] = []
        agent_trace: List[Dict[str, Any]] = []

        gen = self._get_generator()
        generated = gen.generate_files(self.config.prompt, self.config.seed)
        src_name = generated["source_filename"]
        test_name = generated["test_filename"]

        ma = None
        if use_llm:
            ma = self._new_coding_multi_agent()
            tpl = getattr(self, "_role_template", None)
            self._emit("AGENT_SELECTED", run_id=self.config.run_id,
                       roles=["PLANNER", "DEVELOPER", "CRITIC", "REVIEWER", "JUDGE"],
                       template_id=tpl.template_id if tpl else self.config.template_id,
                       template_version=tpl.version if tpl else "",
                       template_hash=tpl.content_hash() if tpl else "")

        # ── DEVELOP / PLAN (LLM or deterministic) ──────────────────────────
        src: str = ""
        tests: str = ""
        if use_llm:
            plan_res = ma.plan(self.config.prompt, self.config.language)
            agent_trace.append({"agent": "PLANNER", **plan_res})
            # DEVELOP: one fresh retry when the first output is degenerate
            # (empty or a bare markdown fence) — frustration rule 7 / retry:
            # a single bad draw is NOT the terminal verdict. The second attempt
            # emits its own AGENT_STARTED/AGENT_RESPONSE(/FAILED) events and is
            # recorded in the trace with an explicit attempt marker. Only when
            # BOTH attempts are unusable do we classify developer failure.
            dev_res = ma.develop(plan_res.get("response", ""), self.config.language)
            agent_trace.append({"agent": "DEVELOPER", **dev_res})
            src = _developer_source(dev_res.get("response", ""))
            if not src.strip():
                dev_res2 = ma.develop(plan_res.get("response", ""), self.config.language)
                agent_trace.append({"agent": "DEVELOPER", "attempt": 2, **dev_res2})
                src = _developer_source(dev_res2.get("response", ""))
            tests = generated.get("tests", "")  # deterministic tests remain the spec
            if not src.strip():
                # GOAL 3/4: after the retry, an empty/phantom DEVELOPER output is
                # an explicit, classified failure — NOT an opaque "completed".
                # The AGENT_FAILED event is emitted by CodingMultiAgent._emit_agent
                # (this is the multi-agent path), so no duplicate is added here.
                errors.append({"stage": "agent_develop",
                               "message": "DEVELOPER returned empty/phantom output after retry"})
                return self._finalize(plan, env, files_created, iterations, errors,
                                      judge_status="NOT_REACHED",
                                      judge_reason="developer_stage_failed",
                                      det_status="NOT_REACHED",
                                      agent_trace=agent_trace)
        else:
            src = (generated.get("source") or "").strip()
            tests = (generated.get("tests") or "").strip()
            if not src or not tests:
                self._emit("AGENT_FAILED", run_id=self.config.run_id,
                           role="DEVELOPER", stage="generate",
                           error_type="empty_response",
                           message="Deterministic generator produced no usable output.")
                errors.append({"stage": "generate", "message": "empty deterministic output"})
                return self._finalize(plan, env, files_created, iterations, errors,
                                      judge_status="NOT_REACHED",
                                      judge_reason="generate_failed",
                                      det_status="NOT_REACHED")

        self._write_files([(src_name, src), (test_name, tests)])
        files_created = [src_name, test_name]
        # GOAL 8: explicit per-file events (relative paths only, never abs).
        for fname in files_created:
            self._emit(FILE_CREATED, run_id=self.config.run_id, file=fname,
                       operation="created", stage="develop",
                       agent_role="DEVELOPER",
                       mode="multi_agent" if use_llm else "deterministic")

        # ── bounded VERIFY + repair loop ────────────────────────────────────
        last_tests_passed = False
        for iteration in range(1, self.config.max_iterations + 1):
            if self.stop_requested:
                self._status = "stopped"
                self._emit(RUN_STOPPED, run_id=self.config.run_id)
                return self._finalize(plan, env, files_created, iterations, errors,
                                      status="stopped", judge_status="NOT_REACHED",
                                      judge_reason="stopped", det_status="NOT_REACHED",
                                      agent_trace=agent_trace,
                                      mode="multi_agent" if use_llm else "deterministic")

            ver = self._run_tests()
            iterations.append({"iteration": iteration, "pytest": ver, "stage": "verify"})

            if ver.get("passed"):
                last_tests_passed = True
                self._emit(TEST_PASSED, run_id=self.config.run_id, iteration=iteration,
                           passed=ver["passed"], total=ver.get("total"))
                break

            self._emit(TEST_FAILED, run_id=self.config.run_id, iteration=iteration,
                       failures=ver.get("failures", 0))
            errors.append({"stage": f"pytest_iter{iteration}", "message": ver.get("output", "")[-500:]})

            if iteration == self.config.max_iterations:
                break

            # CRITIC / REPAIR — real LLM critique when in multi-agent mode.
            self._emit(CRITIQUE_STARTED, run_id=self.config.run_id, iteration=iteration)
            self._emit(REPAIR_STARTED, run_id=self.config.run_id, iteration=iteration)
            changed = False
            if use_llm:
                crit = ma.critique(self.ws.read_text(src_name), ver, self.config.language)
                agent_trace.append({"agent": "CRITIC", **crit})
                if crit.get("ok"):
                    new_src = _extract_python_blocks(crit.get("response", ""))
                    cur = self.ws.read_text(src_name).strip()
                    if new_src.strip() and new_src.strip() != cur:
                        self.ws.write_text(src_name, new_src)
                        self._emit(FILE_MODIFIED, run_id=self.config.run_id,
                                   file=src_name, iteration=iteration, by_agent="CRITIC")
                        changed = True
                if not changed:
                    errors.append({"stage": f"repair_iter{iteration}",
                                   "message": "critic produced no usable patch"})
                    break
            else:
                repaired = self._repair(src_name, test_name, iteration, ver)
                changed = repaired.get("changed", False)
                if not changed:
                    errors.append({"stage": f"repair_iter{iteration}",
                                   "message": "no deterministic fix applied"})
                    break

        # REVIEWER + JUDGE (multi-agent mode only, AFTER deterministic pass).
        review = judge = None
        if use_llm and last_tests_passed:
            try:
                review = ma.review(self.ws.read_text(src_name), tests, {"passed": True})
                agent_trace.append(review)
            except Exception as e:  # pragma: no cover
                review = {"agent": "REVIEWER", "ok": False, "error": str(e)}
            try:
                from .multiagent import SemanticCodeJudge
                judge = SemanticCodeJudge(ma).judge(self.ws.read_text(src_name), tests, True)
                agent_trace.append(judge)
                self._emit("JUDGE_COMPLETED", run_id=self.config.run_id,
                           verdict=judge.get("response", "")[:120])
            except Exception as e:  # pragma: no cover
                judge = {"agent": "JUDGE", "ok": False, "error": str(e)}

        # DETERMINISTIC VALIDATION (authority; rule 6 — even if Judge disagrees).
        det_status = "ERROR"  # conservative default if the validator throws
        try:
            validation = self._validate_files(files_created, generated)
            det_ok = validation.get("deterministic_validation")
            det_status = "PASS" if (det_ok is True and last_tests_passed) else "FAIL"
        except Exception as _ve:  # validator crashed -> explicit ERROR disposition
            validation = {"method": "deterministic_compile", "error": str(_ve)[:200]}
            det_status = "ERROR"
            logger.warning("Deterministic validator ERROR: %s", _ve)

        disagreement = None
        if judge and last_tests_passed and "FAIL" in (judge.get("response") or "").upper():
            disagreement = {
                "deterministic_validation": "pass",  # authority (rule 6)
                "semantic_judge": "fail",
                "note": "SemanticCodeJudge opinion does not override deterministic tests (rule 6)",
            }

        det_ok = validation["deterministic_validation"]
        status = "passed" if (last_tests_passed and det_ok) else "failed"

        # GOAL 5: distinguish "judge NOT_REACHED" (pipeline stopped before the
        # judge stage) from "judge UNAVAILABLE" (stage would have run but the
        # LLM semantic judge backend was not available) and ERROR/PASS/FAIL.
        judge_status = "NOT_REACHED"
        judge_reason = "tests_never_passed"
        if last_tests_passed:
            if judge is None:
                if use_llm:
                    judge_status = "ERROR"
                    judge_reason = "judge_raised"
                else:
                    # Deterministic PASS but no LLM semantic judge ran.
                    judge_status = "UNAVAILABLE"
                    judge_reason = "llm_backend_unavailable"
            else:
                if not judge.get("ok"):
                    judge_status = "ERROR"
                    judge_reason = judge.get("error") or "judge_failed"
                else:
                    verdict = (judge.get("response") or "").upper()
                    if "FAIL" in verdict:
                        judge_status = "FAIL"
                        judge_reason = "semantic_verdict_fail"
                    else:
                        judge_status = "PASS"
                        judge_reason = "semantic_verdict_pass"

        result = self._finalize(
            plan, env, files_created, iterations, errors, status=status,
            agent_trace=agent_trace,
            mode="multi_agent" if use_llm else "deterministic",
            judge_status=judge_status,
            judge_reason=judge_reason,
            det_status=det_status,
        )
        result["validation"] = validation
        result["tests_last_passed"] = last_tests_passed
        result["reviewer"] = review
        # The LLM semantic judge is the CODE LAB component
        # `SemanticCodeJudge` (role JUDGE) — NOT the hermes-debate JudgeAgent,
        # which is absent from the used code path. Deterministic evidence
        # (`validation.deterministic_validation`) remains authoritative.
        #
        # Keep the structured status set by _finalize (NOT_REACHED /
        # UNAVAILABLE / ERROR / PASS / FAIL) and attach the RAW judge outcome
        # as a separate opaque trace (never overriding the structured status).
        sj = result.get("semantic_judge", {})
        if isinstance(sj, dict):
            sj["raw_judge"] = judge  # None when the judge never ran
            result["semantic_judge"] = sj
        else:
            result["semantic_judge"] = {"status": "UNKNOWN",
                                        "reason": "finalize_did_not_set",
                                        "component": "SemanticCodeJudge"}
        result["judge_disagreement"] = disagreement
        return result

    def _get_generator(self):
        from . import generator as _gen
        return _gen

    def _write_files(self, files) -> None:
        for rel, content in files:
            self.ws.write_text(rel, content)

    def _run_tests(self) -> Dict[str, Any]:
        self._emit(TEST_STARTED, run_id=self.config.run_id)
        # Run pytest in the workspace directory only.
        import re
        proc = subprocess.run(
            ["python", "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"],
            cwd=str(self.ws.workspace),
            capture_output=True,
            text=True,
            timeout=self.config.timeout_seconds,
        )
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        passed = proc.returncode == 0
        total = failed = errors = passed_count = 0
        m = re.search(r"(\d+) passed", out)
        if m:
            passed_count = int(m.group(1))
        m = re.search(r"(\d+) failed", out)
        if m:
            failed = int(m.group(1))
        m = re.search(r"(\d+) error", out)
        if m:
            errors = int(m.group(1))
        total = passed_count + failed + errors
        return {
            "passed": passed and passed_count > 0,
            "returncode": proc.returncode,
            "total": total,
            "passed_count": passed_count,
            "failures": failed,
            "errors": errors,
            "output": out[-2000:],
            "command": "python -m pytest -q",
            "executed": True,
        }

    def _repair(self, src_name: str, test_name: str, iteration: int, test_result: Dict[str, Any]):
        """Deterministic repair: attempts a bounded set of generic fixes.

        V1 repairs are conservative: e.g. if the generated source fails to
        import (NameError/ImportError/TypeError edges), no safe automatic fix
        is invented — the run reports an honest failure rather than faking a
        pass (rule 6/15). Applies only known-safe structural rewrites.
        """
        changed = False
        try:
            self.ws.read_text(src_name)
            # A bounded, provable fix: strip an empty return at end-of-module
            # if present, which can confuse some toolchains.
            content = self.ws.read_text(src_name)
            fixed = content
            if content.endswith("\n\n"):
                fixed = content.rstrip("\n") + "\n"
            if fixed != content:
                self.ws.write_text(src_name, fixed)
                self._emit(FILE_MODIFIED, run_id=self.config.run_id, file=src_name, iteration=iteration)
                changed = True
        except WorkspaceError:
            pass
        return {"changed": changed, "iteration": iteration}

    def _validate_files(self, files, generated) -> Dict[str, Any]:
        # DETERMINISTIC structural validation (authority over any judge opinion).
        # For code, deterministic evidence = real `compile()` of each source file.
        # The math/physics OracleValidator is not meaningful for code structure,
        # so a direct compile-based check is used (no fabricated ground truth).
        results: Dict[str, Any] = {
            "method": "deterministic_compile",
            "files": files,
            "detected_plan": generated.get("plan_id"),
        }
        ok = True
        source_files = [f for f in files if f.endswith(".py") and not f.startswith("test_")]
        for f in source_files:
            try:
                compile(self.ws.read_text(f), f, "exec")
                results[f"{f}_compile"] = "ok"
            except SyntaxError as e:
                ok = False
                results[f"{f}_compile"] = f"syntax_error: {e}"
        results["source_files"] = source_files
        self._emit(VALIDATION_COMPLETED, run_id=self.config.run_id, results=results)
        return {"valid": ok, "deterministic_validation": ok, "details": results}

    def _finalize(self, plan, env, files_created, iterations, errors, status=None,
                  agent_trace=None, mode=None, judge_status=None, judge_reason=None,
                  det_status=None):
        status = status or ("failed" if errors else "passed")
        duration = time.time() - getattr(self, "_t0", time.time())
        result = {
            "run_id": self.config.run_id,
            "project": self.config.project_name,
            "status": status,
            "plan": plan,
            "execution_mode": mode or ("multi_agent" if env.get("llm_available") else "deterministic"),
            "iterations": len(iterations),
            "errors": errors[-20:],
            "files_created": files_created,
            "duration": round(duration, 3),
            "llm_available": env.get("llm_available", False),
            "llm_error": env.get("llm_error"),
            "agent_trace": agent_trace or [],
            "judge_validation": "unavailable (no JudgeAgent in used code path)",
            # GOAL 5: structured semantic-judge disposition — NOT_REACHED means
            # the judge stage was never entered (pipeline stopped earlier);
            # UNAVAILABLE means the stage would have run but the LLM semantic
            # judge backend was not available; ERROR/PASS/FAIL otherwise. The
            # deterministic validation is always separate and authoritative.
            "semantic_judge": {
                "status": judge_status or "NOT_REACHED",
                "reason": judge_reason or "unknown",
                "component": "SemanticCodeJudge",
            },
        }
        # Role Template provenance (VERSIONED): template id/version/hash + the
        # experiment-level CONFIGURED model mapping. Distinguishes CONFIGURED
        # (what was requested) from ACTUAL (per-agent, captured in agent events).
        # Only set when a template was actually resolved on the LLM path — the
        # deterministic mode has NO LLM role template (role_template: null), so
        # provenance can never claim a template that did not drive execution.
        tpl = getattr(self, "_role_template", None)
        result["role_template"] = None if tpl is None or not self.config.multi_agent else {
            "template_id": tpl.template_id,
            "template_version": tpl.version,
            "template_hash": tpl.content_hash(),
            "roles": [r.role_id for r in tpl.roles],
            "configured_models": dict(self.config.role_models or {}),
            "executor_type": tpl.executor_type,
        }
        # Settings snapshot (Settings → experiment → snapshot → core → RAW): the
        # immutable record of what Settings applied to THIS run. Never secrets.
        # Persisted with the result into RAW so later Settings edits do NOT
        # rewrite historical provenance.
        snap = getattr(self, "_settings_snapshot", None)
        if snap is not None and not result.get("settings_snapshot"):
            result["settings_snapshot"] = snap
        # Deterministic validation disposition — EXPLICIT, never "FAIL" when the
        # validation stage was never reached (§10): PASS = validated & passed;
        # FAIL = pytest/compile executed and failed; NOT_REACHED = pipeline
        # stopped BEFORE deterministic validation ran; ERROR = the validator
        # itself threw. Ordered honestly, fallback is a guarded derivation.
        dv = det_status
        if dv is None:
            if status == "stopped" or not errors and status != "passed":
                dv = "NOT_REACHED"
            else:
                dv = "PASS" if (status == "passed" and not errors) else "FAIL"
        result["deterministic_validation_status"] = dv
        if judge_status == "NOT_REACHED":
            result["semantic_judge"]["reached"] = False
        else:
            result["semantic_judge"]["reached"] = True
        self._persist_raw(result, iterations)
        return result

    def _persist_raw(self, result, iterations) -> None:
        """Write immutable RAW snapshot + append trajectory (rule 11/15)."""
        if self.ws is None:
            return
        try:
            self.ws.write_raw_snapshot(f"run_{self.config.run_id}", result)
            for it in iterations:
                self.ws.append_raw("trajectory", it)
        except WorkspaceError:
            logger.warning("RAW snapshot already exists; not overwriting (immutable).")
        except Exception as e:  # pragma: no cover
            logger.warning("RAW persist failed: %s", e)


def build_default_engine(config: Optional[CodeLabConfig] = None, **kw) -> CodeLabEngine:
    """Builds an engine wired to the real stable core where possible."""
    from .config import CodeLabConfig as _C
    cfg = config or _C()
    engine = CodeLabEngine(config=cfg, **kw)

    # Wire real OracleValidator (deterministic).
    if engine.oracle is None:
        try:
            from experiments.validation.oracle import OracleValidator
            engine.oracle = OracleValidator()
        except Exception:
            engine.oracle = None

    # Wire real SmartRouter.
    if engine.router is None:
        try:
            from core.assignment.router import SmartRouter
            engine.router = SmartRouter()
        except Exception:
            engine.router = None

    # Wire real EventBus.
    if engine.event_bus is None:
        try:
            from core.events.event_bus import EventBus
            engine.event_bus = EventBus()
        except Exception:
            engine.event_bus = None
    return engine