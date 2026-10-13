"""LLM-multi-turn experiment for the debate_code chain (OPT-IN experimental).

Runs N turns of the MODE B (LLM) chain on a task, collects each tour's real
trace, aggregates them, then produces a structured synthesis:
  - observation  (what the 30 turns actually showed)
  - conclusion   (a verdict grounded only in the aggregated evidence)
  - next_leads   (concrete things worth pursuing next)

Purpose: since mode B is non-reproducible (LLM noise), a multi-turn run tells
you something a single run cannot — does the debate CONVERGE (stable spec_hash,
all PASS) or DRIFT (distinct spec_hash, varied verdicts)? That drift signal is
the honest answer to "est-ce que le système nous joue des tours".

Each tour goes through the SAME run_debate_code(mode='llm') path, so every
tour is fully traced (5 roles, spec_hash, generated_code, real pytest verify).
The synthesis is computed from the real traces, never fabricated; if an LLM
backend was wanted for the prose it can be wired later, but the structural
observation/conclusion/leads are deterministic from the evidence.

CLI: python -m experimental.llm_sweep --turns 30 --task "design a circuit breaker"
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List

from experimental.retry_agent import run_debate_code


def run_one_tour(task_prompt: str, tour: int, model: str = "") -> Dict[str, Any]:
    t0 = time.time()
    tr = run_debate_code(mode="llm", task_prompt=task_prompt, model=model)
    tr["tour"] = tour
    tr["duration_s"] = round(time.time() - t0, 3)
    return tr


def run_llm_sweep(turns: int = 30, task_prompt: str = "",
                  on_tour=None, model: str = "") -> Dict[str, Any]:
    """Run ``turns`` LLM-mode chain tours, aggregating a synthesis.

    ``on_tour(tour, status, spec_hash)`` is invoked as each tour finishes so a
    caller (e.g. the API) can publish live feedback without blocking the sweep.
    ``model`` forces a specific chat model for every tour (else client/router).
    """
    if not task_prompt.strip():
        task_prompt = "Design a small deterministic decision controller (no code)."

    tours: List[Dict[str, Any]] = []
    for i in range(1, turns + 1):
        tr = run_one_tour(task_prompt, i, model=model)
        tours.append(tr)
        if on_tour is not None:
            h = (tr.get("handoff") or {}).get("spec_hash")
            on_tour(i, tr.get("status"), h)

    # ── aggregate the real traces ───────────────────────────────────────────
    status_counts = Counter(t.get("status", "UNKNOWN") for t in tours)
    hashes: Dict[str, List[int]] = defaultdict(list)
    for t in tours:
        h = (t.get("handoff") or {}).get("spec_hash")
        if h:
            hashes[h].append(t["tour"])
    verify_fails = [
        {"tour": t["tour"], "status": t["status"]}
        for t in tours if t.get("verify") and t["verify"].get("failed")
    ]
    inconclusive_reasons = [
        {"tour": t["tour"], "reason": t.get("reason")}
        for t in tours if t["status"] == "INCONCLUSIVE" and t.get("reason")
    ]

    # ── structural synthesis (deterministic from the evidence) ─────────────
    n = len(tours)
    n_pass = status_counts.get("PASS", 0)
    n_distinct_hash = len(hashes)
    n_inconclusive = status_counts.get("INCONCLUSIVE", 0)
    pass_rate = n_pass / n if n else 0.0

    # convergence signal: how many tours produced a compiled+verified spec
    if n_pass == n and n_distinct_hash == 1:
        convergence = "HIGH_CONVERGENCE"
        observation = (f"{n}/{n} tours PASS with a single stable spec_hash: the "
                       f"LLM debate converged to the same verified contract every tour.")
        conclusion = ("The chain is reproducible IN BEHAVIOUR despite LLM noise: "
                      "every tour passed verification and produced an identical spec_hash.")
        next_leads = [
            "Freeze this task as a canary in a CI sweep (any hash drift flags it).",
            "Tighten the prompt if you want the debate to also converge on the SAME code, "
            "not just the same spec_hash.",
        ]
    elif n_pass > 0:
        convergence = "PARTIAL_CONVERGENCE"
        observation = (f"{n_pass}/{n} tours PASS, {n_distinct_hash} distinct spec_hash, "
                       f"{n_inconclusive} INCONCLUSIVE.")
        conclusion = ("The chain is sound but the LLM debate drifts: not every tour "
                      "converged to a usable, verified spec. This is the expected "
                      "non-reproducibility of mode B — now measured, not guessed.")
        next_leads = [
            "Compare the distinct spec_hash: which features vary between the converged "
            "and drifted tours?",
            "Strengthen the DECISION_SPEC prompt (required_inputs / allowed_outputs "
            "enumeration) to reduce INCONCLUSIVE drift.",
            "Decide the acceptance rule: is PASS-or-INCONCLUSIVE enough, or must a "
            "minimum pass_rate hold before the chain counts as usable?",
        ]
    else:
        convergence = "NO_CONVERGENCE"
        observation = (f"0/{n} tours produced a compiled, verified chain "
                       f"({n_inconclusive} INCONCLUSIVE / other).")
        conclusion = ("The LLM backend is not yielding a usable DECISION_SPEC "
                      "(backend down, or the task is out of scope). No chain-level "
                      "property can be claimed until it does.")
        next_leads = [
            "Check LLM backend availability/authentication first.",
            "If backend is up, inspect INCONCLUSIVE reasons to see why the spec is refused.",
        ]

    return {
        "turns": turns,
        "task_prompt": task_prompt,
        "status_counts": dict(status_counts),
        "pass_rate": round(pass_rate, 4),
        "spec_hashes_distinct": n_distinct_hash,
        "convergence": convergence,
        "verify_failures": verify_fails,
        "inconclusive_reasons": inconclusive_reasons,
        "synthesis": {
            "observation": observation,
            "conclusion": conclusion,
            "next_leads": next_leads,
        },
        "per_tour": [{"tour": t["tour"], "status": t["status"],
                      "spec_hash": (t.get("handoff") or {}).get("spec_hash"),
                      "passed": (t.get("verify") or {}).get("passed"),
                      "failed": (t.get("verify") or {}).get("failed"),
                      "duration_s": t["duration_s"]} for t in tours],
    }


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--turns", type=int, default=30)
    ap.add_argument("--task", default="Design a small deterministic decision controller (no code).")
    ap.add_argument("--json", default="", help="write the result to a JSON file")
    args = ap.parse_args(argv)

    print(f"Running {args.turns} LLM tours on: {args.task}")
    result = run_llm_sweep(args.turns, args.task)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\nwritten: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
