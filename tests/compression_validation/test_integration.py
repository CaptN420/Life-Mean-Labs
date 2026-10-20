#!/usr/bin/env python3
"""
Integration tests for Life_mean compression adapter.
Uses synthetic data only - no modification to existing RAW storage.
"""
from __future__ import annotations

import sys
import os
import time
import hashlib
import json
from pathlib import Path
from typing import Dict, Any

# Add Life_mean root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from code_lab.compression_adapter import (
    is_compression_enabled,
    compress_context_if_enabled,
)

# Test data - synthetic only (larger to force compression)
SYNTHETIC_HISTORY = [
    {"role": "system", "content": "You are a helpful AI assistant. Security rules apply at all times."},
]

for i in range(50):  # Larger history to exceed budget
    SYNTHETIC_HISTORY.append({
        "role": "user",
        "content": f"Task {i}: Please help me with this request. Remember to follow all security permissions and the project requirements."
    })
    SYNTHETIC_HISTORY.append({
        "role": "assistant",
        "content": f"I will help you with task {i}. Note: Security permission SP-{i} is active and must be preserved. The implementation follows the design document v2.3."
    })

SYNTHETIC_MEMORY = "\n".join([
    "User prefers Python for scripting.",
    "Project is Life_mean compression module.",
    "Security permissions must be preserved.",
] * 10)

SYNTHETIC_RETRIEVED = "\n\n".join([
    f"Fragment {i}: This is retrieved context about the project architecture and implementation details."
    for i in range(20)
])

SYNTHETIC_TOOLS = [
    {"type": "function", "function": {"name": f"tool_{i}", "description": "A test tool with parameters"}}
    for i in range(10)
]


def test_preconditions():
    """Test A: Verify preconditions."""
    print("\n=== TEST A: PRECONDITIONS ===")
    
    # Check feature flag interpretation
    print(f"  Feature flag env var: COMPRESSION_ENABLED")
    print(f"  Current value: {os.environ.get('COMPRESSION_ENABLED', 'not set')}")
    print(f"  is_compression_enabled(): {is_compression_enabled()}")
    
    # Verify system prompt preservation
    result = compress_context_if_enabled(
        messages=[{"role": "user", "content": "test"}],
        system_prompt="SECURITY RULE: Never expose API keys.",
    )
    print(f"  System prompt preserved: {result['system_prompt'] == 'SECURITY RULE: Never expose API keys.'}")
    
    # Verify fallback behavior
    result = compress_context_if_enabled(
        messages=[{"role": "user", "content": "test"}],
        system_prompt="test",
    )
    print(f"  Fallback to original on disabled: {not result['compressed']}")


def test_flag_scenarios():
    """Test B: Flag scenarios."""
    print("\n=== TEST B: FLAG SCENARIOS ===")
    
    scenarios = [
        ("false", False),
        ("true", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("invalid", False),
        ("", False),
    ]
    
    for value, expected in scenarios:
        os.environ["COMPRESSION_ENABLED"] = value
        result = is_compression_enabled()
        status = "OK" if result == expected else "FAIL"
        print(f"  [{status}] COMPRESSION_ENABLED={value!r} -> {result} (expected {expected})")
    
    # Clean up
    if "COMPRESSION_ENABLED" in os.environ:
        del os.environ["COMPRESSION_ENABLED"]


def test_compression_with_flag():
    """Test C: Compression with flag enabled."""
    print("\n=== TEST C: COMPRESSION WITH FLAG ===")
    
    # Enable compression
    os.environ["COMPRESSION_ENABLED"] = "true"
    
    # Test compression (larger history should trigger compression)
    result = compress_context_if_enabled(
        messages=SYNTHETIC_HISTORY,
        system_prompt="Security rules apply.",
        memory_text=SYNTHETIC_MEMORY,
        tools=SYNTHETIC_TOOLS,
        retrieved_context=SYNTHETIC_RETRIEVED,
        user_query="Task 49",
    )
    
    print(f"  Compressed: {result['compressed']}")
    print(f"  Original tokens: {result.get('stats', {}).get('original_tokens', 'N/A')}")
    print(f"  Selected tokens: {result.get('stats', {}).get('selected_tokens', 'N/A')}")
    print(f"  Reduction %: {result.get('stats', {}).get('reduction_pct', 'N/A')}")
    print(f"  History dropped: {result.get('stats', {}).get('history_dropped', 'N/A')}")
    print(f"  Error: {result.get('error')}")
    
    # Clean up
    del os.environ["COMPRESSION_ENABLED"]


def test_resilience():
    """Test D: Resilience scenarios."""
    print("\n=== TEST D: RESILIENCE ===")
    
    # Test with empty history
    result = compress_context_if_enabled(
        messages=[],
        system_prompt="test",
    )
    print(f"  Empty history: compressed={result['compressed']}, error={result.get('error')}")
    
    # Test with very short history
    result = compress_context_if_enabled(
        messages=[{"role": "user", "content": "hi"}],
        system_prompt="test",
    )
    print(f"  Short history: compressed={result['compressed']}, error={result.get('error')}")
    
    # Test with no flag set
    if "COMPRESSION_ENABLED" in os.environ:
        del os.environ["COMPRESSION_ENABLED"]
    result = compress_context_if_enabled(
        messages=[{"role": "user", "content": "hi"}],
        system_prompt="test",
    )
    print(f"  No flag set: compressed={result['compressed']}, error={result.get('error')}")


def test_integrity():
    """Test E: Integrity verification."""
    print("\n=== TEST E: INTEGRITY (SHA-256) ===")
    
    # Create test data and compute hash
    test_data = json.dumps(SYNTHETIC_HISTORY, ensure_ascii=False).encode('utf-8')
    original_hash = hashlib.sha256(test_data).hexdigest()
    
    # Process through compression (with flag enabled)
    os.environ["COMPRESSION_ENABLED"] = "true"
    result = compress_context_if_enabled(
        messages=SYNTHETIC_HISTORY,
        system_prompt="test",
        user_query="test",
    )
    del os.environ["COMPRESSION_ENABLED"]
    
    # The original data should not be modified
    processed_hash = hashlib.sha256(json.dumps(SYNTHETIC_HISTORY, ensure_ascii=False).encode('utf-8')).hexdigest()
    
    print(f"  Original SHA-256: {original_hash}")
    print(f"  After processing: {processed_hash}")
    print(f"  Match: {'YES' if original_hash == processed_hash else 'NO'}")


def test_performance():
    """Test F: Performance measurement."""
    print("\n=== TEST F: PERFORMANCE ===")
    
    # Warm up with compression
    os.environ["COMPRESSION_ENABLED"] = "true"
    for _ in range(3):
        compress_context_if_enabled(
            messages=SYNTHETIC_HISTORY[:5],
            system_prompt="test",
            user_query="test",
        )
    
    # Measure with compression
    times_compressed = []
    for _ in range(10):
        start = time.perf_counter()
        compress_context_if_enabled(
            messages=SYNTHETIC_HISTORY,
            system_prompt="Security rules apply.",
            memory_text=SYNTHETIC_MEMORY,
            tools=SYNTHETIC_TOOLS,
            retrieved_context=SYNTHETIC_RETRIEVED,
            user_query="Task 49",
        )
        times_compressed.append(time.perf_counter() - start)
    
    # Measure without compression
    del os.environ["COMPRESSION_ENABLED"]
    times_uncompressed = []
    for _ in range(10):
        start = time.perf_counter()
        compress_context_if_enabled(
            messages=SYNTHETIC_HISTORY,
            system_prompt="Security rules apply.",
            user_query="Task 49",
        )
        times_uncompressed.append(time.perf_counter() - start)
    
    avg_compressed = sum(times_compressed) / len(times_compressed)
    avg_uncompressed = sum(times_uncompressed) / len(times_uncompressed)
    
    print(f"  Avg time WITH compression: {avg_compressed*1000:.2f} ms")
    print(f"  Avg time WITHOUT compression: {avg_uncompressed*1000:.2f} ms")
    print(f"  Overhead: {(avg_compressed - avg_uncompressed)*1000:.2f} ms")


def test_security_preservation():
    """Test G: Security instruction preservation."""
    print("\n=== TEST G: SECURITY PRESERVATION ===")
    
    os.environ["COMPRESSION_ENABLED"] = "true"
    
    # Test with security instructions in system prompt
    result = compress_context_if_enabled(
        messages=SYNTHETIC_HISTORY,
        system_prompt="SECURITY RULE: Never expose API keys. Permission SP-001 is mandatory.",
        user_query="Task 49",
    )
    
    # Check if system prompt is preserved (it should be, even if compressed)
    print(f"  Compressed: {result['compressed']}")
    print(f"  System prompt in result: {'SECURITY RULE' in result.get('system_prompt', '')}")
    
    del os.environ["COMPRESSION_ENABLED"]


def main():
    """Run all tests."""
    print("=" * 60)
    print("LIFE_MEAN COMPRESSION INTEGRATION VALIDATION")
    print("=" * 60)
    
    try:
        test_preconditions()
        test_flag_scenarios()
        test_compression_with_flag()
        test_resilience()
        test_integrity()
        test_performance()
        test_security_preservation()
        
        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETED")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[X] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
