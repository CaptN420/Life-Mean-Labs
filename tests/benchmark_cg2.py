"""CG2 benchmark - measure each phase of /api/cluster/graph separately."""
from __future__ import annotations
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from compare.index import load_index, build_index
from compare.loader import load_experiment
from compare.graph import build_graph_payload
from compare.subjects import SubjectTree
from compare.conditions_index import load_conditions_index

def main():
    raw_dir = Path("data/raw_debates")
    cache_path = Path("data/cluster_graph.json")
    if not raw_dir.is_dir():
        print(f"ERROR: RAW dir not found at {raw_dir}")
        sys.exit(1)
    
    raw_files = sorted([f for f in os.listdir(raw_dir) if f.endswith(".jsonl")])
    print(f"\n=== CG2 Benchmark - {len(raw_files)} RAW files ===\n")
    
    # Force rebuild index
    print("Forcing index rebuild...")
    rows = build_index(raw_dir)
    print(f"  Index built: {len(rows)} experiments\n")
    
    # Phase 1
    print("Phase 1: Loading index")
    t0 = time.perf_counter()
    index = load_index(raw_dir=raw_dir)
    rows = index.get("experiments", [])
    elapsed_idx = time.perf_counter() - t0
    print(f"  [index] {elapsed_idx*1000:.2f} ms - {len(rows)} experiments\n")
    
    # Phase 2: OLD method
    print("Phase 2: Reading RAW + extracting conditions (OLD)")
    t_start = time.perf_counter()
    conds_old = {}
    for row in rows:
        eid = str(row.get("experiment_id", ""))
        if not eid:
            continue
        try:
            exp = load_experiment(eid, raw_dir)
            conds_old[eid] = exp.condition
        except Exception:
            conds_old[eid] = {}
    elapsed_cond_old = time.perf_counter() - t_start
    print(f"  [conditions OLD] {elapsed_cond_old*1000:.2f} ms - {len(conds_old)} loaded\n")
    
    # Phase 2b: NEW method
    print("Phase 2b: Reading via conditions_index (NEW)")
    t_start = time.perf_counter()
    conds_new = load_conditions_index(raw_dir=raw_dir)
    elapsed_cond_new = time.perf_counter() - t_start
    print(f"  [conditions NEW] {elapsed_cond_new*1000:.2f} ms - {len(conds_new)} loaded\n")
    
    # Phase 3
    print("Phase 3: Building SubjectTree")
    st = SubjectTree(root=Path("data/subjects"))
    for row in rows:
        st.register(str(row.get("experiment_id", "")), row.get("subject") or "unknown")
    print(f"  [subject_tree] topics={len(st.topics())}\n")
    
    # Phase 4
    print("Phase 4: Building graph (force=True)")
    t_start = time.perf_counter()
    graph = build_graph_payload(rows, st, conds_new, cache_path=cache_path, force=True)
    elapsed_build = time.perf_counter() - t_start
    print(f"  [build] {elapsed_build*1000:.2f} ms")
    print(f"  nodes={graph['counts']['nodes']}, edges={graph['counts']['edges']}, clusters={graph['counts']['clusters']}\n")
    
    # Phase 5
    print("Phase 5: Cache reuse")
    t_start = time.perf_counter()
    graph2 = build_graph_payload(rows, st, conds_new, cache_path=cache_path, force=False)
    elapsed_cache = time.perf_counter() - t_start
    print(f"  [cache] {elapsed_cache*1000:.2f} ms\n")
    
    # Phase 6
    print("Phase 6: Serialization")
    t_start = time.perf_counter()
    blob = json.dumps(graph)
    elapsed_ser = time.perf_counter() - t_start
    size_kb = len(blob.encode("utf-8")) / 1024
    print(f"  [serialize] {elapsed_ser*1000:.2f} ms - {size_kb:.1f} KB\n")
    
    # Phase 7
    print("Phase 7: Three successive calls (cache verification)")
    for i in range(3):
        t_start = time.perf_counter()
        g = build_graph_payload(rows, st, conds_new, cache_path=cache_path, force=False)
        elapsed = time.perf_counter() - t_start
        print(f"  [call {i+1}] {elapsed*1000:.2f} ms")
    
    # Summary
    total_old = elapsed_idx + elapsed_cond_old + elapsed_build + elapsed_ser
    total_new = elapsed_idx + elapsed_cond_new + elapsed_build + elapsed_ser
    print(f"\n=== SUMMARY ===")
    print(f"  OLD API time: {total_old*1000:.2f} ms")
    print(f"  NEW API time: {total_new*1000:.2f} ms")
    print(f"  SPEEDUP: {elapsed_cond_old/elapsed_cond_new:.1f}x faster for conditions")
    print(f"  Cache hit: {elapsed_cache*1000:.2f} ms")
    print(f"  Payload: {size_kb:.1f} KB")

if __name__ == "__main__":
    main()
