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
from typing import Any, Dict

ROLE_SYSTEM = (
    "You are the moderator of a multi-role design debate for building a small "
    "deterministic decision controller. The aim is to converge on an explicit, "
    "machine-readable DECISION_SPEC that the coding phase will implement and "
    "the verification phase will test. "
    "Do NOT write code. Do NOT write tests. Only produce the decision contract."
)

PROMPT_TEMPLATE = """Task to design a controller for (no code):
{task}

Participating roles: Architect, Reliability Engineer, Skeptic, Simplicity Advocate, Moderator.
First give a 1-2 sentence summary of the debate. Then, ON THE LAST LINE, output ONLY a
valid JSON object (no markdown, no explanation) with EXACTLY this schema:
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
- allowed_outputs: UPPER_SNAKE names, at least 2, exactly those referenced by rules.
- The final rule must use "else": "" and give a default action.
- decision_rules_priority: first match wins, ordered from highest priority to default.
- required_inputs must cover every variable used in conditions.
- constants may only be referenced inside conditions or as default values.
Return ONLY the JSON on the final line, prefixed by the summary."""
from experimental.retry_validator import normalize_spec  # noqa  (schema cleanup)


def _join(parts):
    return "".join(parts)


def llm_debate(task_prompt: str) -> Dict[str, Any]:
    """Run the LLM design debate; returns {'debate':..., 'handoff':...}.

    Raises LLMUnavailable on backend/auth errors so the orchestrator can turn
    it into INCONCLUSIVE honestly.
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
        client = LLMClient(base_url=base_url, api_key=api_key)
        user = PROMPT_TEMPLATE.format(task=task_prompt)
        text, finish = client.chat(
            messages=[
                {"role": "system", "content": ROLE_SYSTEM},
                {"role": "user", "content": user},
            ],
            model="",
            temperature=0.2,
            max_tokens=2048,
        )
        return text

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_call)
        try:
            text = fut.result(timeout=90)
        except LLMUnavailable:
            raise
        except Exception as exc:  # network/timeout/finish errors
            raise LLMUnavailable(f"mode-B call failed: {type(exc).__name__}: {exc}") from exc
    spec = _extract_json(text)
    if spec is None:
        return {"debate": {"roles": [], "deterministic": False,
                           "moderator_output": text},
                "handoff": None}
    spec = normalize_spec(spec)
    return {
        "debate": {
            "roles": [], "deterministic": False, "llm": True,
            "moderator_summary": _summary(text),
            "moderator_output": text,
        },
        "handoff": spec,
    }


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
