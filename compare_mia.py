"""Compare MIA versions — deterministic analysis of historical experiment runs.

Reads RAW JSONL evidence from data/raw_debates/ and compares experiments
from the MIA (Mia Brain) legacy system against current Life_mean runs.

Usage:
    python compare_mia.py [experiment_ids...]
    
If no experiment IDs provided, lists all available experiments.
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.resolve()
sys.path.insert(0, str(project_root))


def main():
    """Run comparison analysis on MIA experiments."""
    from compare.loader import list_available_experiments, load_experiment
    from compare.analyzer import CompareEngine
    
    # Get available experiments
    raw_dir = project_root / "data" / "raw_debates"
    experiments = list_available_experiments(raw_dir)
    
    if not experiments:
        print("No experiments found in data/raw_debates/")
        return
    
    print(f"Found {len(experiments)} experiments:\n")
    for i, exp_id in enumerate(experiments[:20], 1):
        print(f"  {i}. {exp_id}")
    if len(experiments) > 20:
        print(f"  ... and {len(experiments) - 20} more")
    
    # If no specific experiments requested, compare all MIA-style ones
    args = sys.argv[1:]
    if not args:
        # Look for MIA experiments (typically have specific patterns)
        mia_experiments = [e for e in experiments if 'mia' in e.lower() or 
                          any(prefix in e for prefix in ['exp_0', 'exp_1', 'exp_2'])]
        if mia_experiments:
            args = mia_experiments[:5]  # Compare first 5
        else:
            args = experiments[:5]
    
    print(f"\n=== Comparing {len(args)} experiments ===\n")
    
    try:
        engine = CompareEngine()
        result = engine.compare(args)
        
        print(f"Experiments compared: {[r.experiment_id for r in result.runs]}")
        print(f"\nPairwise comparisons: {len(result.pairs)}")
        print(f"Findings: {len(result.findings)}")
        print(f"Failure patterns: {len(result.failure_patterns)}\n")
        
        # Print summary
        for run in result.runs:
            print(f"  {run.experiment_id}: {run.num_tasks} tasks, "
                  f"{run.num_passed} passed ({run.success_rate*100:.1f}%), "
                  f"{run.num_failed} failed, {run.num_no_verdict} no verdict")
        
        # Print findings
        if result.findings:
            print("\n=== Findings ===")
            for finding in result.findings[:20]:
                print(f"  [{finding.kind}] {finding.message}")
                if finding.evidence:
                    print(f"    Evidence: {', '.join(finding.evidence[:5])}")
        
        # Print failure patterns
        if result.failure_patterns:
            print("\n=== Failure Patterns ===")
            for pattern in result.failure_patterns[:10]:
                print(f"  '{pattern.failure_reason}': {pattern.count} occurrences "
                      f"in {len(pattern.runs)} runs, tools: {', '.join(pattern.tools[:5])}")
        
    except Exception as e:
        print(f"Error during comparison: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
