"""Mode-B LLM design debate for the debate_code chain (OPT-IN experimental).

The LLM plays the roles and returns a DECISION_SPEC JSON. It is validated
upstream in retry_agent._validate_spec before being compiled. If the LLM is
unreachable/unauthenticated, we return a raised signal the orchestrator turns
into INCONCLUSIVE — never a fake spec.

This module carries the LLM-only dependencies; importing it must not force
them on the deterministic path (lazy import from retry_agent only).
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

ROLE_SYSTEM = (
    "You are the moderator of a multi-role design debate for building a small "
    "deterministic decision controller. The aim is to converge on an explicit, "
    "machine-readable DECISION_SPEC that the coding phase will implement and "
    "the verification phase will test. "
    "Do NOT write code. Do NOT write tests. Only produce the decision contract."
)

PROMPT_TEMPLATE = """Task to design a controller for (no code):
{task}

Running the design debate step by step. First, give each participating role's
position on its own line, EXACTLY one line per role, in this format:

Architect: <position on required inputs / output contract>
Reliability Engineer: <position on failure handling / stop conditions>
Skeptic: <position on what is wasteful or over-engineered>
Simplicity Advocate: <position on minimal viable rule set>
Moderator: <position synthesizing the agreed priorities into one ordered contract>

Then ON THE LAST LINE, output ONLY a valid JSON object (no markdown, no extra
text after it) with EXACTLY this schema, as the final line of your answer:
{{
  "module": "<snake_case_module_name>.py",
  "func": "<function_name>",
  "required_inputs": ["<input1>", ...],
  "allowed_outputs": ["ACTION_A", "ACTION_B", ...],
  "decision_rules_priority": [
    {{"if": "<python condition using only required_inputs and constants>", "action": "<allowed_output>"}},
    ...
    {{"else": "", "action": "<default allowed_output>"}}
  ],
  "constants": {{"NAME": value, ...}},
  "edge_cases": ["<case -> expected action>", ...],
  "stop_conditions": ["<condition>", ...],
  "acceptance_criteria": ["<criterion>", ...]
}}
Rules:
- The five role lines come BEFORE the JSON, one per role.
- allowed_outputs: UPPER_SNAKE names, at least 2, exactly those referenced by rules.
- The final rule must use "else": "" and give a default action.
- decision_rules_priority: first match wins, ordered from highest priority to default.
- required_inputs must cover every variable used in conditions.
- constants may only be referenced inside conditions or as default values.
- Output the role lines, then ONLY the JSON on the final line."""
from experimental.retry_validator import normalize_spec  # noqa  (schema cleanup)


def _join(parts):
    return "".join(parts)


# Model router override: prefer a chat/instruct model that executes the task,
# never a reasoning/planner/summarizer that only yields a plan, and never text
# embeddings/rerankers. Used only when the caller leaves ``model`` empty.
# Priority: models explicitly marked instruct/conversational first (they follow
# the strict JSON format reliably), then any model not clearly a bad trait.
_EXEC_MARKERS = ("-instruct", "-it", "-sft", "-chat", "it-text", "3.1-8b",
                 "-4b-instruct")
_BAD_MARKERS = ("embedding", "reranker", "reasoning", "summarizer", "think",
                "thinking", "-base", "depth", "plan", "agent")


def pick_exec_model(models):
    """Pick the best available chat/instruct model, excluding non-executors.

    First pass: models whose name marks them as instruction-tuned/instruct.
    Second pass: the first model that isn't clearly a planner/embedding/base.
    """
    if not models:
        return ""
    for m in models:
        ml = m.lower()
        if any(b in ml for b in _BAD_MARKERS):
            continue
        if any(x in ml for x in _EXEC_MARKERS):
            return m
    for m in models:
        ml = m.lower()
        if any(b in ml for b in _BAD_MARKERS):
            continue
        return m
    return models[0]


def llm_debate(task_prompt: str, model: str = "") -> Dict[str, Any]:
    """Run the LLM design debate; returns {'debate':..., 'handoff':...}.

    Raises LLMUnavailable on backend/auth errors so the orchestrator can turn
    it into INCONCLUSIVE honestly. A spec that does not survive normalization
    is returned as handoff=None (INCONCLUSIVE upstream), never a crash.
    """
    # A missing backend can hang on the network probe; bound it so a mode-B
    # run becomes INCONCLUSIVE (via LLMUnavailable) instead of blocking the
    # harness indefinitely.
    def _call():
        from philosophical_council.llm.client import LLMClient
        from code_lab.multiagent import probe_llm, resolve_llm_credentials

        base_url, api_key = resolve_llm_credentials()
        probe = probe_llm(base_url, api_key)
        if not probe.get("available"):
            raise LLMUnavailable(probe.get("error") or "LLM backend unavailable")
        effective = model
        if not effective:
            # Never default to a reasoning/planner model: force a chat/instruct
            # model that will actually produce the DECISION_SPEC.
            from experimental.retry_llm import pick_exec_model
            effective = pick_exec_model(probe.get("models") or [])
        client = LLMClient(base_url=base_url, api_key=api_key)
        user = PROMPT_TEMPLATE.format(task=task_prompt)
        text, finish = client.chat(
            messages=[
                {"role": "system", "content": ROLE_SYSTEM},
                {"role": "user", "content": user},
            ],
            model=effective,  # forced: never the resolver's trait-behavorial default
            temperature=0.2,
            max_tokens=2048,
        )
        return text

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        fut = pool.submit(_call)
        try:
            text = fut.result(timeout=120)
        except LLMUnavailable:
            raise
        except Exception as exc:  # network/timeout/finish errors
            raise LLMUnavailable(f"mode-B call failed: {type(exc).__name__}: {exc}") from exc
    finally:
        # Do NOT wait on a possibly-hung worker thread (shutdown(wait=True)
        # would block a 30-tour sweep if a backend stops responding).
        pool.shutdown(wait=False, cancel_futures=True)
    spec = _extract_json(text)
    if spec is None:
        return {"debate": {"roles": [], "deterministic": False,
                           "moderator_output": text},
                "handoff": None}
    try:
        spec = normalize_spec(spec)
    except ValueError as exc:
        # LLM gave a spec that failed schema validation -> honest INCONCLUSIVE
        # (the moderator captured below, minus a usable contract).
        return {"debate": {"roles": parse_role_lines(text),
                           "deterministic": False, "llm": True,
                           "moderator_output": text,
                           "normalization_error": str(exc)},
                "handoff": None}
    # Parse per-role contributions so mode B is as traceable as mode A: every
    # role's individual position is recorded, not just the moderator summary.
    roles = parse_role_lines(text)
    return {
        "debate": {
            "roles": roles, "deterministic": False, "llm": True,
            "moderator_summary": _summary(text),
            "moderator_output": text,
            "normalization_error": None,
        },
        "handoff": spec,
    }


_ROLE_LABELS = ["Architect", "Reliability Engineer", "Skeptic",
                "Simplicity Advocate", "Moderator"]


def parse_role_lines(text: str) -> List[Dict[str, str]]:
    """Extract 'Role: position' lines from the LLM debate text.

    Returns up to one contribution per role, in role order; a missing/unparseable
    line is skipped (the moderator_summary still preserves the full text)."""
    found: Dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        head, _, rest = stripped.partition(":")
        head = head.strip()
        if head in _ROLE_LABELS and rest.strip():
            if head not in found:  # first occurrence wins
                found[head] = rest.strip()
    return [{"role": r, "contribution": found[r], "source": "llm_debate_line"}
            for r in _ROLE_LABELS if r in found]


def _summary(text: str) -> str:
    s = text.strip()
    # take everything before the JSON block
    idx = s.find("{")
    return s[:idx].strip() if idx > 0 else s[:300]


def _extract_json(text: str) -> Dict[str, Any]:
    try:
        start = text.index("{")
        end = text.rindex("}")
        return json.loads(text[start:end + 1])
    except Exception:
        return None


class LLMUnavailable(RuntimeError):
    """The LLM backend for mode B is not reachable/authenticated."""
