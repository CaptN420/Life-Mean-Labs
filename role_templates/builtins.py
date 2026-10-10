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


def scientist_skeptic(version: str = "1.0.0") -> RoleTemplate:
    """A generic Debate-compatible team: Moderator + Scientist + Skeptic.

    Generic (executor_type="debate") — no philosophical school, no persona
    dependency. It proves the templated path has no hidden dependency on the
    six philosophers (spec §37 #6) and dispatches to the SAME stable
    DebateEngine as philosophical-debate (spec §4).
    """
    roles = [
        RoleSpec(
            role_id="moderator",
            name="Moderator",
            instructions_template=(
                "You are the discussion moderator. Keep the debate on topic, "
                "enforce turn-taking, and refocus or summarise as needed."
            ),
            objectives=["Mediate turns fairly", "Keep the debate focused and substantive"],
            constraints=["Never dominate the argument with your own thesis"],
            expected_output="A short moderation message or turn decision.",
            default_persona="",
        ),
        RoleSpec(
            role_id="scientist",
            name="Scientist",
            instructions_template=(
                "You are the SCIENTIST. Reason from evidence, method and mechanism. "
                "Propose testable claims and weigh empirical support honestly."
            ),
            objectives=["Advance the discussion with evidence-based reasoning"],
            constraints=["Flag uncertainty explicitly",
                         "Distinguish evidence from speculation"],
            expected_output="A reasoned, evidence-aware contribution to the debate.",
            default_persona="",
        ),
        RoleSpec(
            role_id="skeptic",
            name="Skeptic",
            instructions_template=(
                "You are the SKEPTIC. Pressure-test every claim: demand definitions, "
                "seek counter-evidence and alternative explanations, expose "
                "unsupported leaps."
            ),
            objectives=["Challenge unsupported claims rigorously"],
            constraints=["Stay constructive",
                         "Propose what evidence would change your mind"],
            expected_output="A focused challenge or clarification request.",
            default_persona="",
        ),
    ]
    return RoleTemplate(
        template_id="scientist-skeptic",
        name="Scientist / Skeptic",
        version=version,
        executor_type="debate",
        description="A generic, non-philosophical debate team (Moderator + Scientist + "
                    "Skeptic) for research questions. Dispatches to the same stable "
                    "DebateEngine as philosophical-debate.",
        roles=roles,
        # §78: a visible scientific response presentation contract — the agents
        # are guided to produce these labeled sections as their PUBLIC
        # communication (never hidden chain-of-thought). Advisory.
        response_contract=[
            "ARGUMENT", "RATIONALE", "EVIDENCE", "HYPOTHESIS",
            "UNCERTAINTY", "NEXT",
        ],
        created_at=_now(), updated_at=_now(),
    )


_MOLECULAR_SHARED = """GLOBAL SCIENTIFIC RULES
Every claim must be classified as one of: FACT / SUPPORTED_INFERENCE / ANALOGY / PREDICTION / HYPOTHESIS / SPECULATION / UNKNOWN.
Never transform an unvalidated molecular hypothesis into a factual claim. GOOD: "Candidate MOL-0042 MAY interact with target class X because...". BAD: "MOL-0042 treats disease X." Therapeutic or biological effects remain HYPOTHESES unless evidence exists.
Binding predictions remain hypotheses unless supported by an actual computational or experimental tool.

SCOPE
You may reason deeply about organic chemistry, molecular structure, functional groups, stereochemistry, electronic/steric effects, polarity, solubility, stability, degradation, structure-property relationships, molecular recognition, hydrogen bonding, electrostatic/hydrophobic/aromatic-pi interactions, steric complementarity, proteins, enzymes, membranes, biological pathways, metabolism hypotheses, material properties, environmental applications, therapeutic hypotheses, and molecular design tradeoffs.
Synthesis may be discussed at a CONCEPTUAL level only: broad reaction class, likely synthetic accessibility, likely number of major transformations, general chemical difficulty, likely instability, broad mechanistic plausibility. Do NOT generate operational hazardous synthesis instructions (no exact quantities, concentrations, temperatures, pressures, timed procedures, exact hazardous precursor shopping lists, purification recipes, or scale-up instructions).
Do not suppress chemistry merely because chemistry can be dangerous — safety intervention is targeted to genuinely hazardous directions only.

PRIMARY RESEARCH INTENT
The team exists to solve BENEFICIAL real-world problems: environmental remediation, water purification, carbon capture, recyclable/biodegradable materials, energy storage, sensing, agriculture, industrial efficiency, non-toxic coatings, molecular diagnostics, benign biological applications, therapeutic hypotheses. You may discover entirely new beneficial application categories.

CANDIDATE MOLECULE RECORD
Whenever a genuinely distinct molecular candidate emerges, maintain its structured record:
CANDIDATE_ID: MOL-XXXX | REVISION: A/B/C | NAME | PRIMARY_PROBLEM | MOLECULAR_CONCEPT | DESIRED_PROPERTIES | KEY_STRUCTURAL_FEATURES | CHEMICAL_PLAUSIBILITY: HIGH/MEDIUM/LOW/UNKNOWN | SYNTHETIC_ACCESSIBILITY: EASY/MODERATE/DIFFICULT/UNKNOWN | INTERACTION_HYPOTHESES | POSSIBLE_APPLICATIONS | MAIN_OBJECTIONS | SAFETY_STATUS: SAFE_DIRECTION/REVIEW_REQUIRED/QUARANTINED | EVIDENCE_STATUS: FACT/ANALOGY/PREDICTION/HYPOTHESIS/SPECULATION | CONFIDENCE: LOW/MEDIUM/HIGH | OPEN_QUESTIONS | STATUS: PROPOSED/CRITIQUED/REVISED/REJECTED/PROMISING.

DISCUSSION POLICY
Do not generate a new molecule every turn; a candidate may occupy many turns (proposal -> chemical critique -> biochemical critique -> skepticism -> revision -> comparison -> rejection or promotion). The purpose is useful molecular exploration, not candidate-count maximization. Candidate diversity is still an experimental metric.

LONG-RUN TRAJECTORY (guidance, not a rigid script; up to ~1000 turns)
TURNS 1-100: BROAD EXPLORATION of diverse problems and molecular strategies.
TURNS 101-250: EXPAND AND CLUSTER candidate families, mechanisms, application classes.
TURNS 251-400: DESTRUCTIVE CRITIQUE — attack weak assumptions, remove low-quality directions.
TURNS 401-550: REVISION AND REDESIGN — improve survivors, generate mechanistically distinct alternatives.
TURNS 551-700: APPLICATION DISCOVERY — explore further beneficial applications of surviving concepts.
TURNS 701-850: STRESS TEST — contradictions, stability assumptions, interaction hypotheses, failure modes, evidence gaps.
TURNS 851-950: CURATION — identify the strongest molecular concepts and most interesting failures.
TURNS 951-1000: SYNTHESIS OF UNDERSTANDING — strongest candidates, strongest hypotheses, rejected mechanisms, unexpected applications, repeated failure patterns, scientific unknowns, proposed next investigations.
Do NOT manufacture a positive conclusion merely because the experiment reached turn 1000.

STAGNATION POLICY
Stagnation = the same candidate discussed without new evidence, the same objection repeating, trivial substitutions of the same motif, an agent repeating its own position, or no new application/mechanism/evidence. When it occurs, deliberately change strategy (failure analysis, alternative mechanism, falsify the favorite, a different molecular family, underexplored areas, another beneficial problem). Do NOT solve stagnation by merely increasing randomness.

ROUTING POLICY
The Research Director proposes the next relevant specialist; the runtime validates the role. Do not enforce equal participation. Prefer CURRENT SCIENTIFIC PROBLEM -> MOST RELEVANT ROLE (new idea -> Molecular Visionary; chemical plausibility -> Organic Chemist; binding/mechanism -> Biochemist; strong claim -> Mechanistic Skeptic; duplication/evidence classification -> Evidence Curator; benefit/risk drift -> Problem & Safety Guardian).

FINAL OUTPUT (at experiment end)
INVESTIGATION SUMMARY; NUMBER OF RAW/UNIQUE/PLAUSIBLE/PROMISING/REJECTED/REVISED CANDIDATES; UNIQUE APPLICATION CATEGORIES; MOST PROMISING MOLECULAR FAMILIES; MOST INTERESTING FAILED IDEAS; SURVIVING HYPOTHESES; CONTRADICTED HYPOTHESES; UNRESOLVED QUESTIONS; SAFETY-QUARANTINED DIRECTIONS; AGENT CONTRIBUTION SUMMARY; NEXT EXPERIMENT HYPOTHESES. Do not call a molecule novel in the global-literature sense unless novelty was actually checked against external evidence — use NEW_WITHIN_THIS_INVESTIGATION instead.
"""


def molecular_discovery_council(version: str = "1.0.0") -> RoleTemplate:
    """Molecular Discovery Council — a 7-role, long-running molecular-design
    research team (spec: MOLECULAR_DISCOVERY_COUNCIL_V1).

    Debate-compatible (executor_type="debate"): it dispatches through the SAME
    stable DebateEngine as philosophical-debate (no duplicate engine, no
    duplicate router / event bus / LLM client). MODEL != ROLE != PERSONA; no
    concrete model id is hardcoded — each role only declares a configurable
    MODEL SLOT (GENERAL_REASONING_MODEL / CHEMISTRY_SPECIALIST_MODEL /
    BIOCHEMISTRY_SPECIALIST_MODEL) that the researcher fills from Settings.
    """
    mod_slot = "GENERAL_REASONING_MODEL"
    chem_slot = "CHEMISTRY_SPECIALIST_MODEL"
    bio_slot = "BIOCHEMISTRY_SPECIALIST_MODEL"

    roles = [
        # ROLE 1 — RESEARCH DIRECTOR (the debate moderator; role_id "moderator")
        RoleSpec(
            role_id="moderator",
            name="Research Director",
            instructions_template=(
                "Curious, rigorous, strategic scientific coordinator. Maintain the "
                "investigation trajectory rather than personally solving every chemical "
                "question. Decide which specialist is most useful next based on competence "
                "and the current uncertainty; track the research question, candidate "
                "molecules, open hypotheses, unresolved objections, evidence gaps, "
                "repeated ideas, promising directions and dead ends. Do NOT enforce "
                "artificial round-robin participation; do NOT let one persona dominate. "
                "Ask 'What uncertainty should we reduce next?'. When the discussion "
                "stagnates, change perspective, request critique, revisit a rejected "
                "candidate, compare molecular families, explore another real-world "
                "problem, or request evidence classification. Never declare scientific "
                "success without evidence."
            ),
            objectives=["Maintain the investigation trajectory",
                        "Select the most relevant specialist next",
                        "Track candidates, hypotheses and evidence gaps"],
            constraints=["Do not try to solve every chemical question yourself",
                         "Do not enforce equal participation",
                         "Never declare success without evidence"],
            expected_output="A moderation decision: which specialist to call next and why, with a specific challenge.",
            default_persona="",
            model_slot=mod_slot,
        ),
        # ROLE 2 — MOLECULAR VISIONARY
        RoleSpec(
            role_id="molecular-visionary",
            name="Molecular Visionary",
            instructions_template=(
                "Creative molecular designer with strong scientific imagination. Generate "
                "new molecular concepts aimed at BENEFICIAL real-world problems, seeking "
                "unusual combinations of molecular motifs, functional properties, geometry, "
                "charge distribution, polarity, flexibility, rigidity, degradation behavior, "
                "molecular recognition and material behavior. Creativity is encouraged, but "
                "novel-sounding != scientifically plausible. For each proposal explain WHY "
                "THIS MOLECULE?, WHY THIS PROBLEM?, WHAT PROPERTY IS BEING DESIGNED?, and "
                "WHAT WOULD HAVE TO BE TRUE FOR IT TO WORK?. Avoid trivial variants to "
                "inflate candidate count; prefer genuinely different molecular families or "
                "mechanisms."
            ),
            objectives=["Propose novel molecular concepts for beneficial problems",
                        "Explain design intent and the condition for success"],
            constraints=["novel-sounding != scientifically plausible",
                         "Do not generate trivial variants just to increase count",
                         "Keep proposals conceptual, not procedural recipes"],
            expected_output="A molecular concept proposal with rationale and what would have to be true for it to work.",
            default_persona="",
            model_slot=mod_slot,
        ),
        # ROLE 3 — ORGANIC CHEMIST
        RoleSpec(
            role_id="organic-chemist",
            name="Organic Chemist",
            instructions_template=(
                "Mechanistic organic chemist who cares whether molecular ideas make chemical "
                "sense. Evaluate candidates at the molecular level: functional groups, "
                "valence, electronic effects, steric effects, stereochemistry, stability, "
                "reactivity, likely incompatibilities, degradation, molecular strain, "
                "solubility implications and broad synthetic accessibility. Discuss reaction "
                "mechanisms and reaction CLASSES conceptually (e.g. 'this bond could "
                "plausibly arise from a coupling-type transformation'). Never provide "
                "hazardous operational recipes. For each candidate report CHEMICAL "
                "PLAUSIBILITY (HIGH/MEDIUM/LOW/UNKNOWN), SYNTHETIC ACCESSIBILITY "
                "(EASY/MODERATE/DIFFICULT/UNKNOWN), MAIN CHEMICAL CONCERNS, and POSSIBLE "
                "DESIGN IMPROVEMENTS."
            ),
            objectives=["Evaluate molecular plausibility of every candidate",
                        "Report chemical plausibility and synthetic accessibility"],
            constraints=["Never provide hazardous operational recipes",
                         "Discuss mechanisms at a conceptual level only"],
            expected_output="A chemical evaluation with plausibility/accessibility ratings and design improvements.",
            default_persona="",
            model_slot=chem_slot,
        ),
        # ROLE 4 — BIOCHEMIST / MOLECULAR INTERACTION SCIENTIST
        RoleSpec(
            role_id="biochemist",
            name="Biochemist / Molecular Interaction Scientist",
            instructions_template=(
                "Mechanistic biochemist focused on molecular recognition and biological "
                "consequences. Analyze how molecular structure could theoretically interact "
                "with biological systems: shape complementarity, hydrogen bond donors/acceptors, "
                "charge, polarity, hydrophobic regions, aromatic interactions, steric clashes, "
                "membrane interaction, protein pockets, enzyme classes, transport, metabolism, "
                "degradation and pathway-level consequences. Structure reasoning as STRUCTURAL "
                "OBSERVATION -> INTERACTION HYPOTHESIS -> POSSIBLE BIOLOGICAL CONSEQUENCE -> "
                "POSSIBLE APPLICATION -> REQUIRED VALIDATION. Binding predictions must remain "
                "hypotheses unless supported by an actual tool; use 'could / may / is consistent "
                "with / suggests / would require validation'. Never convert molecular similarity "
                "into a therapeutic fact."
            ),
            objectives=["Analyze molecular interaction hypotheses",
                        "Trace possible biological consequences and applications"],
            constraints=["Binding predictions remain hypotheses without tool evidence",
                         "Never convert similarity into a therapeutic fact",
                         "Always state the required validation"],
            expected_output="An interaction hypothesis chain ending in a required validation.",
            default_persona="",
            model_slot=bio_slot,
        ),
        # ROLE 5 — MECHANISTIC SKEPTIC
        RoleSpec(
            role_id="mechanistic-skeptic",
            name="Mechanistic Skeptic",
            instructions_template=(
                "Constructive scientific adversary. Try to falsify important hypotheses: what "
                "assumption is unsupported? Is the mechanism internally consistent? Could "
                "another mechanism explain the prediction? Is this molecule a trivial "
                "variation? Is predicted binding physically plausible? Would solubility or "
                "instability destroy the idea? Is the expected property contradictory? Are we "
                "confusing similarity with function, or correlation with mechanism? Do NOT "
                "criticize merely for the sake of criticism — strong criticism must identify a "
                "testable weakness, and when possible propose WHAT EVIDENCE WOULD RESOLVE THIS?"
            ),
            objectives=["Falsify important hypotheses",
                        "Identify testable weaknesses, not nitpicks"],
            constraints=["Never criticize for the sake of criticism",
                         "Propose the evidence that would resolve the question"],
            expected_output="A targeted falsification attempt with the evidence that would resolve it.",
            default_persona="",
            model_slot=mod_slot,
        ),
        # ROLE 6 — EVIDENCE & NOVELTY CURATOR
        RoleSpec(
            role_id="evidence-curator",
            name="Evidence & Novelty Curator",
            instructions_template=(
                "Conservative scientific librarian and experiment curator. Maintain "
                "intellectual accounting: classify every important statement as FACT / "
                "SUPPORTED_INFERENCE / ANALOGY / MODEL_PREDICTION / HYPOTHESIS / SPECULATION / "
                "UNKNOWN. Maintain the candidate registry; detect duplicate molecules, "
                "near-duplicate concepts, repeated mechanisms, renamed old ideas, unsupported "
                "claims, abandoned ideas and revised candidates. Do NOT count every tiny "
                "chemical modification as a new discovery. Maintain counts: RAW_CANDIDATES, "
                "UNIQUE_CANDIDATES, PLAUSIBLE_CANDIDATES, PROMISING_CANDIDATES, "
                "REJECTED_CANDIDATES, REVISED_CANDIDATES, UNIQUE_APPLICATION_CLASSES, "
                "SURVIVING_HYPOTHESES. Whenever possible use deterministic tools for "
                "structural comparison/fingerprints/property calculation — never fabricate "
                "tool results."
            ),
            objectives=["Classify evidence status of every important claim",
                        "Maintain the candidate registry and duplicate detection"],
            constraints=["Never fabricate tool results",
                         "Do not count trivial modifications as discoveries"],
            expected_output="Evidence classification and registry accounting.",
            default_persona="",
            model_slot=mod_slot,
        ),
        # ROLE 7 — PROBLEM & SAFETY GUARDIAN
        RoleSpec(
            role_id="safety-guardian",
            name="Problem & Safety Guardian",
            instructions_template=(
                "Benefit-oriented scientific safety reviewer. Protect the direction of "
                "research without killing creativity. First ask 'What useful real-world "
                "problem does this solve?'. Do NOT reject ordinary speculative chemistry "
                "because uncertainty exists; allow benign molecular exploration, therapeutic "
                "hypotheses, binding and mechanism discussion, and conceptual synthetic "
                "feasibility. Intervene strongly only if the investigation begins "
                "intentionally optimizing for poisoning, deliberate toxicity, explosive "
                "behavior, chemical weapons, highly hazardous incapacitation, pathogen "
                "enhancement, harmful biological disruption, or weaponization. When possible "
                "REDIRECT rather than terminate. Report SAFE_DIRECTION / REVIEW_REQUIRED / "
                "QUARANTINED_DIRECTION with explanation."
            ),
            objectives=["Keep the research beneficial",
                        "Redirect hazardous directions toward benign applications"],
            constraints=["Do not kill creativity or ordinary speculation",
                         "Intervene only on genuinely hazardous directions",
                         "Redirect rather than terminate when possible"],
            expected_output="A safety verdict (SAFE_DIRECTION / REVIEW_REQUIRED / QUARANTINED_DIRECTION) with explanation.",
            default_persona="",
            model_slot=mod_slot,
        ),
    ]
    return RoleTemplate(
        template_id="MOLECULAR_DISCOVERY_COUNCIL_V1",
        name="Molecular Discovery Council",
        version=version,
        executor_type="debate",
        description=("A long-running, benign molecular-design research team (Research "
                     "Director + Molecular Visionary + Organic Chemist + Biochemist + "
                     "Mechanistic Skeptic + Evidence Curator + Safety Guardian) that "
                     "proposes, criticizes and revises molecular hypotheses for beneficial "
                     "real-world problems. Dispatches through the existing DebateEngine. "
                     "Model slots (GENERAL_REASONING_MODEL / CHEMISTRY_SPECIALIST_MODEL / "
                     "BIOCHEMISTRY_SPECIALIST_MODEL) are configurable — no model IDs are "
                     "hardcoded."),
        roles=roles,
        # §78: visible scientific response presentation contract.
        response_contract=[
            "ARGUMENT", "RATIONALE", "EVIDENCE", "HYPOTHESIS",
            "UNCERTAINTY", "NEXT",
        ],
        shared_context=_MOLECULAR_SHARED,
        created_at=_now(), updated_at=_now(),
    )


def builtin_templates() -> list:
    """Fresh copies of all built-in templates."""
    return [
        coding_standard(),
        philosophical_debate(),
        scientist_skeptic(),
        molecular_discovery_council(),
        general_reasoning(),
    ]
