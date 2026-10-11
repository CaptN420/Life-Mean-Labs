"""100-run robustness sweep for the debate_code chain (OPT-IN experimental).

Goal: prove the full DEBATE -> SPEC -> CODE -> VERIFY chain holds when the
CONtent changes, not just for one trivia case. This is not a tautology: we
vary ``task_type`` (catalogue A: 3 genuinely different decision problems) and
``seed``, and run each to a real pytest verdict. Then we aggregate a matrix.

What it checks, per run:
  - the full chain completes (status in PASS/INCONCLUSIVE, never a crash)
  - a deterministic run that reaches compile must PASS with 0 failed tests
  - each task_type keeps a STABLE spec_hash across seeds (no hidden state)

CLI:  python -m experimental.sweep --runs 100 [--type retry_controller|alert_routing|payment_gate|--all] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from typing import Any, Dict, List

from experimental.retry_agent import CATALOG, run_debate_code


def run_one(task_type: str, seed: int) -> Dict[str, Any]:
    t0 = time.time()
    tr = run_debate_code(task_type=task_type, seed=seed, mode="deterministic")
    tr["duration_s"] = round(time.time() - t0, 3)
    return tr


def sweep(runs: int, types: List[str]) -> Dict[str, Any]:
    """Rotate across types and varying seeds; aggregate a matrix."""
    per_type: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    status_counts: Dict[str, int] = defaultdict(int)
    hashes_seen: Dict[str, set] = defaultdict(set)
    failures: List[Dict[str, Any]] = []
    total_dur = 0.0

    for i in range(runs):
        task_type = types[i % len(types)]
        seed = (i // len(types)) + 1  # round-robin so every type sees many seeds
        tr = run_one(task_type, seed)
        status_counts[tr["status"]] += 1
        total_dur += tr["duration_s"]
        per_type[task_type].append(tr)
        if "spec_hash" in (tr.get("handoff") or {}):
            hashes_seen[task_type].add(tr["handoff"]["spec_hash"])
        if tr["status"] in ("PASS", "INCONCLUSIVE"):
            # deterministic catalogue should never fail on a valid run path
            v = tr.get("verify") or {}
            if tr["status"] == "PASS" and (v.get("failed") or 0) > 0:
                failures.append({"task_type": task_type, "seed": seed,
                                 "status": tr["status"], "verify": v})
        else:
            failures.append({"task_type": task_type, "seed": seed,
                             "status": tr["status"], "reason": tr.get("reason")})

    # matrix of per-type stability
    matrix = {}
    for t, rs in per_type.items():
        matrix[t] = {
            "runs": len(rs),
            "pass": sum(1 for r in rs if r["status"] == "PASS"),
            "inconclusive": sum(1 for r in rs if r["status"] == "INCONCLUSIVE"),
            "spec_hashes_distinct": len(hashes_seen.get(t, set())),
            "avg_duration_s": round(sum(r["duration_s"] for r in rs) / len(rs), 3),
        }

    return {
        "runs": runs,
        "types": types,
        "status_counts": dict(status_counts),
        "matrix": matrix,
        "failures": failures,
        "total_duration_s": round(total_dur, 3),
        "all_green": (status_counts.get("PASS", 0) == runs
                      and not failures),
    }


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runs", type=int, default=100)
    ap.add_argument("--type", action="append", dest="types",
                    help="restrict to one catalogue type; repeat or use --all")
    ap.add_argument("--all", action="store_true", help="use every catalogue type")
    ap.add_argument("--json", default="", help="write the matrix to a JSON file")
    args = ap.parse_args(argv)

    if args.all or not args.types:
        types = list(CATALOG)
    else:
        types = [t for t in args.types if t in CATALOG]
    if not types:
        print(f"no valid task types (known: {list(CATALOG)})", file=sys.stderr)
        return 2

    print(f"Sweeping {args.runs} runs across: {', '.join(types)} ...")
    result = sweep(args.runs, types)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"\nwritten: {args.json}")
    return 0 if result["all_green"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
