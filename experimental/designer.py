"""ExperimentDesigner — proposes a DRAFT experiment design. NEVER runs.

Per the core rule: Design -> human review -> freeze -> execute -> RAW. A
proposal is purely descriptive; the designer has no path to start anything.
The 0.6B-class LLM is a LOGICAL role (EXPERIMENT_DESIGNER) resolved through
Settings/model assignment — never hardcoded. The actual LLM proposer is
probe-gated; when no live backend is available the designer falls back to a
DETERMINISTIC-FIRST baseline (spec §19) that still inspects the Lab's real
capabilities and stops at DRAFT.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from experimental.dispatch import executor_catalog
from experimental.prompts import compose_system_prompt
from experimental.schema import (
    DesignAgent,
    DesignBudgets,
    DesignStage,
    ExperimentDesign,
)


class DesignerInputError(ValueError):
    """Raised when a proposal request is unusable (e.g. empty description)."""


# Deterministic baseline role vocabulary keyed by description keyword. These are
# only PROPOSED roles; the researcher reviews/edits them (spec §5). A proposal
# never hardcodes a model — model_assignment stays None (dynamic) unless the
# caller injects one from Settings.
_BASELINE_ROLES: List[Dict[str, Any]] = [
    {"match": ("algorithm", "sort", "data structure", "search", "optimize"),
     "role": "algorithm_researcher", "persona": "methodical",
     "skills": ("computer-science-research", "algorithm-analysis")},
    {"match": ("edge case", "adversarial", "weakness", "failure", "robust"),
     "role": "adversarial_analyst", "persona": "skeptical",
     "skills": ("failure-analysis",)},
    {"match": ("benchmark", "measure", "compare", "evaluate", "performance"),
     "role": "experimentalist", "persona": "empirical",
     "skills": ("benchmark-design",)},
    {"match": ("chem", "molecule", "reaction", "dendrite", "electrolyte"),
     "role": "chemist", "persona": "methodical",
     "skills": ("chemistry-literature-analysis", "experimental-design")},
    {"match": ("debate", "philosoph", "argument", "stance", "proposition"),
     "role": "debater", "persona": "principled",
     "skills": ("argumentation", "logic")},
]
_FALLBACK_ROLE = {"role": "experimentalist", "persona": "empirical",
                  "skills": ("experimental-design",)}
_DEFAULT_STAGES = [
    ("research", "review existing approaches and relevant prior evidence"),
    ("reasoning", "reason about the question with the team"),
    ("validation", "subject every measurable claim to deterministic checks"),
    ("synthesis", "separate observations, hypotheses and recommendations"),
]


def _propose_roles(description: str) -> List[DesignAgent]:
    """Deterministic baseline: pick roles from keywords, then guarantee a
    verifier. Returns AGENT PROPOSALS only (DRAFT)."""
    low = description.lower()
    chosen = [_FALLBACK_ROLE]
    for row in _BASELINE_ROLES:
        if any(k in low for k in row["match"]):
            chosen.append(row)
    # de-dup while keeping order
    seen: List[str] = []
    unique = []
    for r in chosen:
        if r["role"] not in seen:
            seen.append(r["role"])
            unique.append(r)
    agents = []
    for i, r in enumerate(unique, start=1):
        agents.append(DesignAgent(
            agent_id=f"agent-{i}",
            role=r["role"],
            persona=r.get("persona", ""),
            skills=list(r.get("skills", [])),
            allowed_tools=[],
            system_prompt="",
        ))
    agents.append(DesignAgent(
        agent_id=f"agent-{len(agents) + 1}",
        role="verifier",
        persona="rigorous",
        skills=["validation"],
        allowed_tools=["tests.run", "benchmark.run"],
        system_prompt="",
    ))
    return agents


class ExperimentDesigner:
    """Builds a DRAFT :class:`ExperimentDesign` from a natural-language request.

    Responsibilities (spec §2): inspect capabilities, propose the team, stop
    after producing DRAFT. It cannot start, mutate the DB as truth, or approve
    anything. The LLM proposer role is reserved for ``EXPERIMENT_DESIGNER`` and
    resolved via ``model_pool``/settings — never a hardcoded model name.
    """

    logical_role = "EXPERIMENT_DESIGNER"

    def __init__(self, model_pool: Optional[Dict[str, str]] = None,
                 capabilities: Optional[Dict[str, Any]] = None) -> None:
        # model_pool: e.g. {"coding": {...}, "debate": {...}, "designer": "..."}.
        self.model_pool = dict(model_pool or {})
        self.capabilities = capabilities or {}
        # The LLM path is probe-gated; when unavailable the baseline is used.
        self.llm_available = bool(
            self.capabilities.get("llm_available", False)
            or self.model_pool.get("designer"))

    def _honour_capabilities(self, agents: List[DesignAgent]) -> List[DesignAgent]:
        """Only keep skills/tools that the Lab actually owns (spec §13): never
        invent a capability the Lab doesn't expose."""
        known_skills = set(self.capabilities.get("skills", []))
        known_tools = set(self.capabilities.get("tools", []))
        for a in agents:
            a.skills = [s for s in a.skills if not known_skills or s in known_skills]
            a.allowed_tools = [t for t in a.allowed_tools if not known_tools or t in known_tools]
        return agents

    def propose(self, description: str, research_question: str = "") -> ExperimentDesign:
        """Produce a DRAFT design. Returns only a proposal — no execution."""
        description = (description or "").strip()
        if not description:
            raise DesignerInputError("an experiment description is required to propose a design")
        title = next((ln.strip() for ln in description.splitlines() if ln.strip()),
                     "Untitled experiment")[:80]
        q = research_question.strip() or description

        agents = self._honour_capabilities(_propose_roles(description))
        for a in agents:
            built = compose_system_prompt(
                role=a.role,
                persona=a.persona,
                skills=a.skills,
                context=description,
                capabilities=a.allowed_tools or None,
                constraints=["Do not claim causality without controlled evidence."],
                output_contract="Separate observations, hypotheses and recommendations.",
            )
            a.prompt_components = built["components"]
            a.system_prompt = built["system_prompt"]
        stages = [DesignStage(stage_id=sid, executor_type=et, request=req,
                              participants=[a.agent_id for a in agents[:2]])
                  for sid, et, req in (
                      ("research", "research", ""),
                      ("reasoning", "general_reasoning", ""),
                      ("validation", "deterministic", ""),
                      ("synthesis", "synthesis", ""),
                  )]

        design = ExperimentDesign(
            title=title,
            description=description,
            research_question=q,
            agents=agents,
            stages=stages,
            validators=[],  # filled at review; verifier covers deterministic checks
            budgets=DesignBudgets(),
            metadata={"proposer": self.logical_role, "proposal_basis": "deterministic_baseline"},
        )
        return design

    # LLM proposal interface (0.6B / EXPERIMENT_DESIGNER). Kept separate from
    # the narrative role (LAB_NARRATOR) — different responsibility (§12).
    def propose_llm(self, description: str, research_question: str = "") -> Optional[ExperimentDesign]:
        """Reserved path for a live small model proposing the team. Gated: if no
        backend is available this returns None and the caller uses
        :meth:`propose`. Never executes anything."""
        if not self.llm_available:
            return None
        # An honest LLM proposer would call the resolved model here via the
        # EXISTING LLM client and parse the structured proposal. That is the
        # future live path; the interface is separate so a deployment can add it
        # without touching the deterministic baseline.
        raise NotImplementedError(
            "live LLM proposer not wired: supply an OUTPUT_CONTRACT parser")


def inspect_capabilities() -> Dict[str, Any]:
    """Expose the Lab's current stage-execution capabilities for the designer
    (spec §13). Deterministic-only functions live here; live LLM gating is read
    from the environment at request time."""
    cats = executor_catalog()
    return {
        "executors": cats,
        "connected_executors": sorted(et for et, c in cats.items() if c.get("connected")),
        # skills/tools inventories are injected by the caller (registry) so the
        # designer never guesses at capabilities — it only filters by them.
    }