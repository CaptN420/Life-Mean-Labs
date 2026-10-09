"""Code Lab — multi-agent integration layer (REAL LLM).

Reuses the EXISTING stable core's LLM infrastructure (`LLMClient` from
`philosophical_council.llm`) and model configuration (`ModelConfig`) to drive
logical coding roles. NO new debate engine, NO duplicated LLM client.

Roles are LOGICAL (rule 13): PLANNER / DEVELOPER / CRITIC / REVIEWER / JUDGE.
Models are selected through the existing `ModelConfig.get_model(role)` /
config, never hardcoded as "Mellum=developer" etc.

LLM availability is probed HONESTLY. If the backend is unreachable or the
stored API token is invalid, `llm_available` is False and the caller must use
the deterministic fallback — the system NEVER fakes an LLM turn (rule 4/15).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import os

from .config import CodeLabConfig, ENV_LLM_BASE, ENV_LLM_KEY
logger = logging.getLogger("CodeLab.MultiAgent")


def resolve_llm_credentials(base_url: str = "", api_key: str = "") -> tuple:
    """Resolve LLM credentials under the ONE canonical precedence policy.

    Delegates to `experiments.credentials` (the single source of truth) so every
    active runtime path agrees on the same order: explicit process env >
    Settings override (`overrides/llm.env`) > legacy `.env` > Config default.
    Never prints/returns the key to callers.
    """
    from experiments.credentials import resolve_llm_credentials as _canonical
    return _canonical(base_url, api_key)

# Logical coding roles -> system prompts (models assigned via ModelConfig).
ROLE_PROMPTS: Dict[str, str] = {
    "PLANNER": (
        "You are the PLANNER of a software project. Given a user prompt, "
        "produce a concise build plan: files to create, the function/API "
        "contract, and the test cases to implement. Return structured text "
        "with a clear 'PLAN:' and 'TESTS:' section. Do not write full code yet."
    ),
    "DEVELOPER": (
        "You are the DEVELOPER. Implement the requested Python module. "
        "Emit ONLY the source code for one file between triple-backtick "
        "markers ```python ... ```. Output valid, runnable Python."
    ),
    "CRITIC": (
        "You are the CRITIC/DEBUGGER. Given the failing pytest output and "
        "the current source, diagnose the root cause and output a precise "
        "patch description. Emit the corrected function(s) ONLY between "
        "```python ... ``` markers."
    ),
    "REVIEWER": (
        "You are the REVIEWER. Given the source and test output, assess "
        "correctness and edge cases. Reply with a verdict: PASS or FIX with "
        "specific reasons. You do NOT have authority over deterministic tests."
    ),
    "JUDGE": (
        "You are the JUDGE. Assess the semantic quality (naming, edge cases, "
        "robustness) of the produced code. You may NOT override deterministic "
        "test results. Provide: verdict, score 0-1, specific notes."
    ),
}

ROLE_MODEL_KEYS: Dict[str, str] = {
    "PLANNER": "planner",
    "DEVELOPER": "developer",
    "CRITIC": "critic",
    "REVIEWER": "reviewer",
    "JUDGE": "judge",
}


class LLMUnavailable(Exception):
    """Raised when the LLM backend is not usable for real invocation."""


def probe_llm(base_url: str = "http://localhost:1234/v1",
              api_key: str = "") -> Dict[str, Any]:
    """Honestly probe whether a real LLM backend is reachable + authenticated.

    Returns a dict: {available, base_url, error} — never raises for the common
    auth/unreachable cases so callers can decide the fallback path.
    """
    try:
        from philosophical_council.llm.client import LLMClient
        client = LLMClient(base_url, api_key=api_key)
        models = client.get_models()
        if not models:
            # Server reachable but 401/auth or empty. Distinguish if possible.
            return {
                "available": False,
                "base_url": base_url,
                "error": "no_models_or_auth",
            }
        return {
            "available": True,
            "base_url": base_url,
            "models": models,
            "error": None,
        }
    except ImportError:
        return {"available": False, "base_url": base_url,
                "error": "openai_package_missing"}
    except Exception as e:
        msg = str(e)
        if "401" in msg or "Invalid" in msg or "token" in msg.lower():
            err = "invalid_api_token"
        elif "connect" in msg.lower() or "timed out" in msg.lower() or "refused" in msg.lower():
            err = "backend_unreachable"
        else:
            err = msg[:80]
        return {"available": False, "base_url": base_url, "error": err}


class CodingAgent:
    """A logical coding-role agent backed by the real LLMClient.

    Reuses `LLMClient` (existing stable core). The model is resolved via
    `ModelConfig.get_model(role)` with fallback to the client's router/default.
    """

    def __init__(self, role: str, llm_client: Any, model_key: str = "") -> None:
        self.role = role
        self.llm = llm_client
        self.model_key = model_key or ROLE_MODEL_KEYS.get(role, "")
        self.prompt = ROLE_PROMPTS.get(role, "")
        self.history: List[Dict[str, str]] = []
        self.model_used: str = ""

    def turn(self, task: str, max_tokens: int = 1200,
             temperature: float = 0.4) -> Dict[str, str]:
        """Run one agent turn. Empty/whitespace response -> marked failed."""
        system = {"role": "system", "content": self.prompt}
        user = {"role": "user", "content": task}
        messages = [system] + self.history + [user]
        t0 = time.time()
        text, finish = self.llm.chat(
            messages, model=self.model_used or None,
            temperature=temperature, max_tokens=max_tokens,
        )
        dur = time.time() - t0
        # Record ACTUAL model when none was configured (router/fallback decided).
        if not self.model_used:
            self.model_used = getattr(self.llm, "last_model_used", "") or ""
        # Phantom-turn guard (rule 8): empty output is FAILURE.
        if not text or not text.strip() or text.startswith("[Error"):
            return {
                "role": self.role,
                "ok": False,
                "response": "",
                "finish": finish,
                "duration": round(dur, 2),
                "error": "empty_response" if not text.strip() else "llm_error",
            }
        self.history.append({"role": "assistant", "content": text})
        return {
            "role": self.role,
            "ok": True,
            "response": text.strip(),
            "finish": finish,
            "duration": round(dur, 2),
            "error": None,
        }


class CodingMultiAgent:
    """Orchestrates logical coding roles over the real LLM (rule 13).

    Reuses `Config`/`ModelConfig` for model assignment. Exposes a bounded
    PLANNER -> DEVELOPER -> (pytest feedback) -> CRITIC/REPAIR loop result
    that the Code Lab engine consumes. Each agent action is observable via the
    `on_event` callback (events are backend-real, rule 12/14).
    """

    def __init__(self, base_url: str, api_key: str, model_config: Any = None,
                 on_event=None, use_router: bool = True,
                 llm_client: Any = None, run_id: str = "",
                 role_prompts: Optional[Dict[str, str]] = None,
                 role_models: Optional[Dict[str, str]] = None,
                 template_id: str = "", template_version: str = "",
                 template_hash: str = "") -> None:
        # Dependency injection (GOAL 6): when a client is supplied, NOTHING is
        # constructed here — no LLMClient, no network, no key required. Used by
        # deterministic/unit tests with a stub. When absent, build the real
        # LLMClient from the existing stable core (live integration).
        self.base_url = base_url
        self.api_key = api_key
        self.on_event = on_event
        self.run_id = run_id
        if llm_client is not None:
            self.llm = llm_client
        else:
            from philosophical_council.llm.client import LLMClient
            self.llm = LLMClient(base_url, api_key=api_key)
        self.model_config = model_config  # existing ModelConfig (reused)
        self.use_router = use_router
        self.agents: Dict[str, CodingAgent] = {}
        # Role Template configuration (VERSIONED). `role_prompts` overrides the
        # default ROLE_PROMPTS for roles defined by a template; `role_models` is
        # the experiment-level CONFIGURED model mapping (role_id -> model). Model
        # assignment is NEVER baked into the template itself.
        self.role_prompts = role_prompts or {}
        self.role_models = role_models or {}
        self.template_id = template_id
        self.template_version = template_version
        self.template_hash = template_hash

    def role_model(self, role: str) -> str:
        # 1) Experiment-level CONFIGURED model mapping (RoleModelMapping).
        key = ROLE_MODEL_KEYS.get(role, role)
        if key in self.role_models:
            return self.role_models[key] or ""
        # 2) Existing ModelConfig (stable core) for debate-style roles.
        if self.model_config is not None and hasattr(self.model_config, "get_model"):
            return self.model_config.get_model(key) or ""
        return ""

    def emit(self, ev_type: str, **payload):
        ev = {"type": ev_type, "time": time.time(), **payload}
        if self.run_id:
            ev["run_id"] = self.run_id
        # Role Template provenance rides on every agent-level event so RAW / UI
        # can reconstruct template -> role -> model. Never includes secrets.
        if self.template_id:
            ev["template_id"] = self.template_id
            ev["template_version"] = self.template_version
            ev["template_hash"] = self.template_hash
        if self.on_event:
            try:
                self.on_event(ev)
            except Exception as e:  # pragma: no cover
                logger.warning("on_event failed: %s", e)

    def _emit_agent_started(self, role: str, stage: str) -> None:
        """Emit AGENT_STARTED BEFORE the LLM call so the event is observable
        while the model is still executing (§8) — never fake-frontend. Records
        CONFIGURED vs ACTUAL model for provenance. Template provenance rides on
        emit() itself."""
        agent = self._agent(role)
        self.emit("AGENT_STARTED", role=role, stage=stage,
                  model=agent.model_used or "auto",
                  configured_model=self.role_model(role),
                  run_id=self.run_id)

    def _emit_agent_result(self, role: str, stage: str, result: Dict[str, Any],
                           started_ts: float) -> None:
        """Emit AGENT_RESPONSE / AGENT_FAILED AFTER inference, with duration.

        Diagnostic metadata only — never secrets, never full prompts. Records
        CONFIGURED vs ACTUAL model for provenance.
        """
        agent = self._agent(role)
        configured = self.role_model(role)
        actual = agent.model_used or "auto"
        ok = bool(result.get("ok"))
        dur_ms = int((time.time() - started_ts) * 1000)
        response = result.get("response") or ""
        payload = {
            "role": role,
            "stage": stage,
            "model": actual,
            "configured_model": configured,
            "run_id": self.run_id,
            "duration_ms": dur_ms,
            "response_present": bool(response.strip()),
            "response_length": len(response),
            "finish_reason": result.get("finish"),
        }
        if ok:
            self.emit("AGENT_RESPONSE", ok=True, **payload)
        else:
            err_type = result.get("error") or "unknown_error"
            payload["error_type"] = err_type
            # Safe, short message — never a full backend dump.
            payload["message"] = {
                "empty_response": "Agent returned no usable output.",
                "llm_error": "Agent returned an LLM error.",
                "backend_error": "LLM backend returned an error.",
                "timeout": "Agent timed out.",
                "parse_error": "Agent output could not be parsed.",
                "invalid_output": "Agent output was invalid.",
                "stopped": "Agent stopped.",
            }.get(err_type, f"Agent failed ({err_type}).")
            self.emit("AGENT_FAILED", ok=False, **payload)

    def plan(self, prompt: str, language: str) -> Dict[str, Any]:
        agent = self._agent("PLANNER")
        task = self._plan_task(prompt, language)
        self._emit_agent_started("PLANNER", "plan")
        t0 = time.time()
        res = agent.turn(task)
        self._emit_agent_result("PLANNER", "plan", res, t0)
        return {"agent": "PLANNER", **res}

    def develop(self, plan_text: str, language: str) -> Dict[str, Any]:
        agent = self._agent("DEVELOPER")
        task = self._develop_task(plan_text, language)
        self._emit_agent_started("DEVELOPER", "develop")
        t0 = time.time()
        res = agent.turn(task, max_tokens=2000)
        self._emit_agent_result("DEVELOPER", "develop", res, t0)
        return {"agent": "DEVELOPER", **res}

    def critique(self, source: str, test_result: Dict[str, Any],
                 language: str) -> Dict[str, Any]:
        agent = self._agent("CRITIC")
        task = self._critique_task(source, test_result, language)
        self._emit_agent_started("CRITIC", "repair")
        t0 = time.time()
        res = agent.turn(task, max_tokens=1600)
        self._emit_agent_result("CRITIC", "repair", res, t0)
        return {"agent": "CRITIC", **res}

    def review(self, source: str, tests: str, test_result: Dict[str, Any]) -> Dict[str, Any]:
        agent = self._agent("REVIEWER")
        task = self._review_task(source, tests, test_result)
        self._emit_agent_started("REVIEWER", "review")
        t0 = time.time()
        res = agent.turn(task, max_tokens=800, temperature=0.2)
        self._emit_agent_result("REVIEWER", "review", res, t0)
        return {"agent": "REVIEWER", **res}

    def judge(self, source: str, tests: str, deterministic_valid: bool) -> Dict[str, Any]:
        """Judge semantic quality. CANNOT override deterministic validity."""
        agent = self._agent("JUDGE")
        task = self._judge_task(source, tests, deterministic_valid)
        self._emit_agent_started("JUDGE", "judge")
        t0 = time.time()
        res = agent.turn(task, max_tokens=900, temperature=0.2)
        self._emit_agent_result("JUDGE", "judge", res, t0)
        return {"agent": "JUDGE", **res}

    # ── helpers ───────────────────────────────────────────────────────────
    def _agent(self, role: str) -> CodingAgent:
        if role not in self.agents:
            model = self.role_model(role)
            prompt = self.role_prompts.get(role, ROLE_PROMPTS.get(role, ""))
            agent = CodingAgent(role, self.llm, model_key=model or "")
            agent.prompt = prompt
            if model:
                agent.model_used = model
            self.agents[role] = agent
        return self.agents[role]

    @staticmethod
    def _plan_task(prompt: str, language: str) -> str:
        return f"Language: {language}\nUser prompt:\n{prompt}\n\nProduce a build plan."

    @staticmethod
    def _develop_task(plan_text: str, language: str) -> str:
        return (f"Language: {language}\nPlan:\n{plan_text}\n\n"
                "Emit the implementation module as a single ```python code block.")

    @staticmethod
    def _critique_task(source: str, test_result: Dict[str, Any], language: str) -> str:
        out = test_result.get("output", "")
        return (f"Language: {language}\nThe following source FAILED its tests.\n\n"
                f"SOURCE:\n```python\n{source}\n```\n\n"
                f"PYTEST OUTPUT (tail):\n{out}\n\n"
                "Diagnose the root cause and emit the corrected module ONLY as "
                "```python ... ```.")

    @staticmethod
    def _review_task(source: str, tests: str, test_result: Dict[str, Any]) -> str:
        return (f"SOURCE:\n```python\n{source}\n```\n\nTESTS:\n```python\n{tests}\n```\n\n"
                f"pytest: passed={test_result.get('passed')}, total={test_result.get('total')}.\n"
                "Verdict: PASS or FIX with reasons. You do NOT outrank pytest.")

    @staticmethod
    def _judge_task(source: str, tests: str, deterministic_valid: bool) -> str:
        return (f"Deterministic_valid: {deterministic_valid}\n"
                f"SOURCE:\n```python\n{source}\n```\n\nTESTS:\n```python\n{tests}\n```\n\n"
                "Assess semantic quality. Verdict + score 0-1 + notes. "
                "Deterministic tests are the authority; you may not override them.")


class SemanticCodeJudge:
    """The Code Lab LLM semantic judge component (role JUDGE).

    This is the explicit, honest name for the semantic-quality component that
    Code Lab invokes through `CodingMultiAgent.judge()`. It is NOT the
    hermes-debate JudgeAgent (which is absent from the used code path, and
    which is not importable). It never overrides deterministic evidence:
    `validation.deterministic_validation` stays authoritative (rule 6).

    When the LLM backend is unavailable, the engine reports
    `judge_validation: unavailable` rather than faking a judgment (rule 15).
    """

    ROLE = "JUDGE"

    def __init__(self, multi_agent: CodingMultiAgent) -> None:
        self.ma = multi_agent

    def judge(self, source: str, tests: str, deterministic_valid: bool) -> Dict[str, Any]:
        result = self.ma.judge(source, tests, deterministic_valid)
        result["component"] = "SemanticCodeJudge"
        return result
