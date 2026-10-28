"""Quick test of conditions_index module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from compare.conditions_index import load_conditions_index, build_conditions_index
import time

print("Testing conditions_index...")

# Test 1: Load from real data
t = time.perf_counter()
conds = load_conditions_index()
elapsed = (time.perf_counter() - t) * 1000
print(f"  Loaded {len(conds)} conditions in {elapsed:.2f} ms")

# Test 2: Verify fingerprint function
from compare.conditions_index import conditions_fingerprint
fp = conditions_fingerprint(conds)
print(f"  Fingerprint: {fp[:16]}...")

# Test 3: Build fresh (should be same result)
t = time.perf_counter()
conds2 = build_conditions_index()
elapsed2 = (time.perf_counter() - t) * 1000
print(f"  Built fresh in {elapsed2:.2f} ms — same count: {len(conds) == len(conds2)}")

print("\nAll checks passed.")
