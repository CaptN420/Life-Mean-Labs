"""Built-in Role Templates.

Each factory returns a fresh `RoleTemplate` (immutable-ish: deterministic hash
that changes only when content changes).

Three built-ins are shipped:

CODING_STANDARD      — reuses the *existing* Code Lab role prompts (PLANNER /
                       DEVELOPER / CRITIC / REVIEWER / JUDGE). It does NOT
                       redefine them; the multi-agent still emits the same agent
                       events and behavior when configured from this template.
PHILOSOPHICAL_DEBATE — *adapts* the existing philosophical roles/personas
                       (moderator + 6 schools). Persona system prompts are NOT
                       rewritten here — they stay in the existing Config and are
                       referenced via `default_persona`.
GENERAL_REASONING    — a minimal solver / critic / verifier team.

No template hardcodes a MODEL. Model assignment stays in the experiment's
`RoleModelMapping`.
"""

from __future__ import annotations

import time

from .core import RoleSpec, RoleTemplate

_TS = time.strftime


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def coding_standard(version: str = "1.0.0") -> RoleTemplate:
    """The standard collaborative coding team. Reuses existing coding roles."""
    from code_lab.multiagent import ROLE_PROMPTS  # existing role prompts

    def _role(r: str, objectives, constraints, expected, persona=""):
        return RoleSpec(
            role_id=r.lower(),
            name=r.title(),
            instructions_template=ROLE_PROMPTS.get(r, ""),
            objectives=objectives,
            constraints=constraints,
            expected_output=expected,
            permissions=["read_workspace", "write_workspace", "run_pytest"] if r != "JUDGE" else ["read_workspace"],
            default_persona=persona,
        )

    roles = [
        _role(
            "PLANNER",
            ["Produce a concise build plan: files, function/API contract, test cases."],
            ["Do not write full code yet.", "Use a clear 'PLAN:' and 'TESTS:' structure."],
            "Structured plan text with PLAN: and TESTS: sections.",
        ),
        _role(
            "DEVELOPER",
            ["Implement the requested Python module returning valid, runnable source."],
            ["Emit ONLY source for one file inside ```python ... ``` markers.",
             "Do not emit prose or analysis."],
            "A single ```python ... ``` block with runnable code.",
        ),
        _role(
            "CRITIC",
            ["Diagnose the root cause of failing pytest output and emit a precise patch."],
            ["Emit corrected function(s) ONLY between ```python ... ``` markers.",
             "Do not rewrite unrelated code."],
            "A corrected code block that fixes the reported failures.",
        ),
        _role(
            "REVIEWER",
            ["Assess correctness and edge cases of source + test output."],
            ["You do NOT have authority over deterministic tests.",
             "Reply with a specific PASS or FIX verdict and reasons."],
            "A verdict: PASS or FIX with concrete reasons.",
        ),
        _role(
            "JUDGE",
            ["Assess semantic quality (naming, edge cases, robustness)."],
            ["You may NOT override deterministic test results.",
             "Provide verdict + score 0-1 + specific notes."],
            "Verdict, score in [0,1], and specific notes.",
        ),
    ]
    return RoleTemplate(
        template_id="coding-standard",
        name="Coding Standard",
        version=version,
        executor_type="code_lab",
        description="Standard collaborative coding team (Planner → Developer → Critic → Reviewer → Judge).",
        roles=roles,
        created_at=_now(), updated_at=_now(),
    )


def philosophical_debate(version: str = "1.0.0") -> RoleTemplate:
    """The philosophical debate team.

    ADAPTS the existing roles/personas already present in Life_mean — it does
    NOT rewrite them. Each philosopher role references its persona via
    `default_persona` (same role_id) so the existing `Config.personas` supplies
    the actual system prompt; the model mapping stays experiment-level.
    """
    moderators = [
        RoleSpec(
            role_id="moderator",
            name="Moderator",
            instructions_template=(
                "You are the discussion moderator. Keep the debate on topic, "
                "enforce turn-taking, and summarise or refocus as needed. "
                "Prefer the configured moderator persona when one is set."
            ),
            objectives=["Mediate turns fairly", "Keep the debate focused and substantive"],
            constraints=["Never dominate the argument with your own philosophical thesis"],
            expected_output="A short moderation message or turn decision.",
            default_persona="moderator",
        )
    ]
    # Inspired by the existing personas in Config.DEFAULT_CONFIG["personas"].
    school_meta = [
        ("existentialist", "Existentialist", "freedom, authenticity, meaning and the absurd"),
        ("stoic", "Stoic", "virtue, control, reason, fate and equanimity"),
        ("nihilist", "Nihilist", "meaning, value and the conditions of value"),
        ("spiritual", "Spiritual", "transcendence, the sacred and human flourishing"),
        ("skeptic", "Skeptic", "limits of knowledge, epoché and intellectual humility"),
        ("pragmatist", "Pragmatist", "truth as what works and practical consequences"),
    ]
    philosophers = [
        RoleSpec(
            role_id=rid,
            name=name,
            instructions_template=(
                f"You are the {name} philosopher in a structured debate. Argue from "
                f"your school's perspective ({focus}). Engage with others' arguments "
                "directly and honestly. Your concrete system prompt is supplied by "
                "your PERSONA (overrideable at experiment level), not hardcoded here."
            ),
            objectives=["Defend your school's position rigorously", "Engage other speakers' arguments"],
            constraints=["Do not merely quote philosophers; reason independently.",
                         "Keep responses in the persona's target length."],
            expected_output="A reasoned philosophical turn in the debate.",
            default_persona=rid,
        )
        for rid, name, focus in school_meta
    ]
    return RoleTemplate(
        template_id="philosophical-debate",
        name="Philosophical Debate",
        version=version,
        executor_type="philosophical_debate",
        description="The existing philosophical debate team (moderator + six schools), reusing the "
                    "Life_mean personas via default_persona. DebateEngine executes it.",
        roles=moderators + philosophers,
        created_at=_now(), updated_at=_now(),
    )


def general_reasoning(version: str = "1.0.0") -> RoleTemplate:
    """A minimal generic problem-solving team."""
    roles = [
        RoleSpec(
            role_id="solver", name="Solver",
            instructions_template=(
                "You are the SOLVER. Given a task, produce a clear, correct solution "
                "or answer directly."
            ),
            objectives=["Produce a correct, well-reasoned solution"],
            constraints=["Be explicit about assumptions"],
            expected_output="The solution or answer.",
        ),
        RoleSpec(
            role_id="critic", name="Critic",
            instructions_template=(
                "You are the CRITIC. Evaluate the proposed solution for correctness, "
                "edge cases and hidden assumptions, and either approve it or identify "
                "specific flaws."
            ),
            objectives=["Find genuine weaknesses, not nitpicks"],
            constraints=["Distinguish critical defects from style preferences"],
            expected_output="A verdict (APPROVE / REVISE) with concrete reasons.",
        ),
        RoleSpec(
            role_id="verifier", name="Verifier",
            instructions_template=(
                "You are the VERIFIER. Independently confirm the solution satisfies "
                "the stated requirements and deterministic constraints."
            ),
            objectives=["Confirm requirement coverage"],
            constraints=["You do not outrank deterministic validation"],
            expected_output="A PASS / FAIL verdict on the solution.",
        ),
    ]
    return RoleTemplate(
        template_id="general-reasoning",
        name="General Reasoning",
        version=version,
        executor_type="general_reasoning",
        description="A minimal solver / critic / verifier team for generic reasoning tasks.",
        roles=roles,
        created_at=_now(), updated_at=_now(),
    )


def builtin_templates() -> list:
    """Fresh copies of all built-in templates."""
    return [
        coding_standard(),
        philosophical_debate(),
        general_reasoning(),
    ]
