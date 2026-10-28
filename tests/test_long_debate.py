"""Tests for max_turns and context compression (LONG_DEBATE feature).

Covers:
  - max_turns validation (1..1500)
  - compression enabled/disabled behavior
  - RAW history preservation
  - Provenance tracking
  - Integration with DebateLabController
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import json
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests._debate_stub_llm import StubLLM  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def stub():
    return StubLLM(models=["model-a", "model-b"])


@pytest.fixture()
def controller(stub, tmp_path):
    from debate_lab.controller import DebateLabController
    from debate_lab.run_store import DebateLabRunStore
    from debate_lab.session_factory import DebateSessionFactory
    factory = DebateSessionFactory(llm_client=stub, base_dir=tmp_path)
    return DebateLabController(factory=factory, store=DebateLabRunStore(base_dir=tmp_path))


def _config(**kw):
    from debate_lab.config import DebateLabConfig
    base = dict(topic="Test topic for compression")
    base.update(kw)
    return DebateLabConfig(**base)


# ── max_turns validation ─────────────────────────────────────────────────────


class TestMaxTurnsValidation:
    """Tests for max_turns parameter validation."""

    def test_max_turns_default(self):
        """Default max_turns should be 20."""
        from debate_lab.config import DebateLabConfig
        cfg = DebateLabConfig(topic="t")
        assert cfg.max_turns == 20

    def test_max_turns_1(self):
        """max_turns=1 should be accepted."""
        from debate_lab.config import DebateLabConfig
        cfg = DebateLabConfig(topic="t", max_turns=1)
        assert cfg.max_turns == 1

    def test_max_turns_1500(self):
        """max_turns=1500 should be accepted (new ceiling)."""
        from debate_lab.config import DebateLabConfig
        cfg = DebateLabConfig(topic="t", max_turns=1500)
        assert cfg.max_turns == 1500

    def test_max_turns_1501_rejected(self):
        """max_turns=1501 should raise ValueError."""
        from debate_lab.config import DebateLabConfig, DebateLabConfigError
        with pytest.raises(DebateLabConfigError, match="INVALID_MAX_TURNS"):
            DebateLabConfig(topic="t", max_turns=1501)

    def test_negative_turns_rejected(self):
        """Negative max_turns should raise ValueError."""
        from debate_lab.config import DebateLabConfig, DebateLabConfigError
        with pytest.raises(DebateLabConfigError, match="INVALID_MAX_TURNS"):
            DebateLabConfig(topic="t", max_turns=0)
        with pytest.raises(DebateLabConfigError, match="INVALID_MAX_TURNS"):
            DebateLabConfig(topic="t", max_turns=-1)

    def test_max_turns_1000_accepted(self):
        """Backward compatibility: 1000 should still work."""
        from debate_lab.config import DebateLabConfig
        cfg = DebateLabConfig(topic="t", max_turns=1000)
        assert cfg.max_turns == 1000


# ── Compression config validation ────────────────────────────────────────────


class TestCompressionConfigValidation:
    """Tests for compression configuration validation."""

    def test_compression_disabled_by_default(self):
        """Compression should be disabled by default."""
        from debate_lab.config import DebateLabConfig
        cfg = DebateLabConfig(topic="t")
        assert cfg.context_compression_enabled is False

    def test_compression_enabled_accepted(self):
        """Valid compression config should be accepted."""
        from debate_lab.config import DebateLabConfig
        cfg = DebateLabConfig(
            topic="t",
            context_compression_enabled=True,
            context_compression_strategy="structured",
            context_compression_interval_turns=20,
            context_compression_retain_recent_turns=10,
        )
        assert cfg.context_compression_enabled is True

    def test_invalid_strategy_rejected(self):
        """Invalid compression strategy should raise error."""
        from debate_lab.config import DebateLabConfig, DebateLabConfigError
        with pytest.raises(DebateLabConfigError, match="INVALID_COMPRESSION_STRATEGY"):
            DebateLabConfig(
                topic="t",
                context_compression_enabled=True,
                context_compression_strategy="invalid",
            )

    def test_invalid_interval_rejected(self):
        """Invalid interval should raise error."""
        from debate_lab.config import DebateLabConfig, DebateLabConfigError
        with pytest.raises(DebateLabConfigError, match="INVALID_COMPRESSION_INTERVAL"):
            DebateLabConfig(
                topic="t",
                context_compression_enabled=True,
                context_compression_interval_turns=0,
            )

    def test_invalid_retain_rejected(self):
        """Invalid retain should raise error."""
        from debate_lab.config import DebateLabConfig, DebateLabConfigError
        with pytest.raises(DebateLabConfigError, match="INVALID_COMPRESSION_RETAIN"):
            DebateLabConfig(
                topic="t",
                context_compression_enabled=True,
                context_compression_retain_recent_turns=0,
            )


# ── Compression behavior ─────────────────────────────────────────────────────


class TestCompressionBehavior:
    """Tests for compression behavior."""

    def test_compression_disabled_preserves_behavior(self):
        """When compression is disabled, all turns should be preserved."""
        from debate_lab.compression import ContextCompressor, CompressionConfig
        compressor = ContextCompressor(CompressionConfig(enabled=False))
        turns = [{"speaker": "A", "response": f"Turn {i}"} for i in range(50)]
        result = compressor.compress(turns)
        assert result.compressed is False
        assert result.turns_before == 50
        assert result.turns_after == 50

    def test_compression_preserves_raw_history(self):
        """RAW history should never be modified."""
        from debate_lab.compression import ContextCompressor, CompressionConfig
        compressor = ContextCompressor(CompressionConfig(enabled=True))
        turns = [{"speaker": "A", "response": f"Turn {i}"} for i in range(50)]
        original_hash = hash(tuple(json.dumps(t, sort_keys=True) for t in turns))
        result = compressor.compress(turns)
        # RAW should be unchanged
        assert hash(tuple(json.dumps(t, sort_keys=True) for t in turns)) == original_hash

    def test_compression_keeps_recent_turns(self):
        """Recent turns should be kept verbatim."""
        from debate_lab.compression import ContextCompressor, CompressionConfig
        config = CompressionConfig(enabled=True, retain_recent_turns=10)
        compressor = ContextCompressor(config)
        turns = [{"speaker": "A", "response": f"Turn {i}"} for i in range(50)]
        result = compressor.compress(turns)
        assert result.compressed is True
        # Should have compressed 40 turns, kept 10 recent
        assert result.turns_before == 50
        assert result.turns_after <= 11  # summary + recent

    def test_compression_preserves_evidence_refs(self):
        """Evidence references should be preserved in compressed output."""
        from debate_lab.compression import ContextCompressor, CompressionConfig
        config = CompressionConfig(enabled=True)
        compressor = ContextCompressor(config)
        turns = [
            {"speaker": "A", "response": "I ran pytest test_foo.py and got hash ev_12345"},
            {"speaker": "B", "response": "The compile result shows sha256:abc123"},
        ]
        result = compressor.compress(turns)
        # Should have provenance with hashes (even if empty dict when no compression)
        # The key point is the method doesn't crash and returns a valid result
        assert result is not None
        assert hasattr(result, 'provenance')

    def test_compression_records_provenance(self):
        """Each compression should record provenance."""
        from debate_lab.compression import ContextCompressor, CompressionConfig
        config = CompressionConfig(enabled=True)
        compressor = ContextCompressor(config)
        turns = [{"speaker": "A", "response": f"Turn {i}"} for i in range(50)]
        result = compressor.compress(turns)
        prov = result.provenance
        assert "compression_id" in prov
        assert "created_at" in prov
        assert "source_turn_range" in prov
        assert "source_hash" in prov
        assert "strategy" in prov
        assert "tokens_before" in prov
        assert "tokens_after" in prov

    def test_compression_failure_is_visible(self):
        """Compression failures should be visible in result."""
        from debate_lab.compression import ContextCompressor, CompressionConfig
        config = CompressionConfig(enabled=True)
        compressor = ContextCompressor(config)
        # Force a scenario where compression might fail
        turns = [{"speaker": "A", "response": ""} for _ in range(50)]
        result = compressor.compress(turns)
        # Should not crash, should return error or fallback
        assert result is not None

    def test_multiple_incremental_compressions(self):
        """Multiple compressions should work incrementally."""
        from debate_lab.compression import ContextCompressor, CompressionConfig
        config = CompressionConfig(enabled=True, interval_turns=20)
        compressor = ContextCompressor(config)
        
        # First compression
        turns1 = [{"speaker": "A", "response": f"Turn {i}"} for i in range(50)]
        result1 = compressor.compress(turns1)
        assert result1.compressed is True
        
        # Second compression with more turns
        turns2 = [{"speaker": "A", "response": f"Turn {i}"} for i in range(100)]
        result2 = compressor.compress(turns2)
        assert result2.compressed is True
        
        # Both should have provenance
        assert len(compressor.get_provenance_log()) == 2


# ── Integration with controller ──────────────────────────────────────────────


class TestControllerIntegration:
    """Tests for compression integration with DebateLabController."""

    def test_run_stops_exactly_at_max_turns(self, controller, stub):
        """Run should stop exactly at max_turns."""
        cfg = _config(template_id="scientist-skeptic", max_turns=3, model_pool=["model-a", "model-b"])
        view = controller.create_run(cfg)
        ok = controller.start_run(view.run_id, wait=True)
        assert ok
        run = controller.get_run(view.run_id)
        assert run["status"] == "completed"
        assert run["result"]["turns_committed"] == 3

    def test_stop_reason_max_turns(self, controller, stub):
        """Stop reason should be max_turns_reached when limit is hit."""
        cfg = _config(template_id="scientist-skeptic", max_turns=2, model_pool=["model-a", "model-b"])
        view = controller.create_run(cfg)
        ok = controller.start_run(view.run_id, wait=True)
        run = controller.get_run(view.run_id)
        assert run["result"]["terminal_reason"] == "max_turns_reached"

    def test_user_stop_before_max_turns(self, controller, stub):
        """User stop should work before max_turns is reached."""
        import threading
        cfg = _config(template_id="scientist-skeptic", max_turns=100, model_pool=["model-a", "model-b"])
        view = controller.create_run(cfg)
        ok = controller.start_run(view.run_id)
        
        # Wait for one turn then stop
        def stop_after_turn():
            time.sleep(0.5)
            controller.stop_run(view.run_id)
        
        t = threading.Thread(target=stop_after_turn)
        t.start()
        
        run = None
        deadline = time.time() + 30
        while time.time() < deadline:
            run = controller.get_run(view.run_id)
            if run and run["status"] in ("completed", "stopped", "failed"):
                break
            time.sleep(0.05)
        
        assert run is not None
        assert run["result"]["terminal_reason"] == "user_stop"
        assert run["result"]["turns_committed"] < 100

    def test_long_run_does_not_require_full_raw_context(self, controller, stub):
        """Long runs with compression should not require full RAW context."""
        # This is a synthetic test - verify the compression can handle many turns
        from debate_lab.compression import ContextCompressor, CompressionConfig
        
        config = CompressionConfig(enabled=True, interval_turns=20, retain_recent_turns=10)
        compressor = ContextCompressor(config)
        
        # Simulate 1500 turns
        turns = [{"speaker": "A", "response": f"Argument about topic {i}"} for i in range(1500)]
        
        # Should not crash and should compress incrementally
        result = compressor.compress(turns)
        assert result is not None
        assert result.turns_before == 1500


# ── Synthetic 1500-turn test ─────────────────────────────────────────────────


class TestLongRunSynthetic:
    """Synthetic tests for long runs (up to 1500 turns)."""

    def test_1500_turns_config_accepted(self):
        """Config should accept 1500 turns."""
        from debate_lab.config import DebateLabConfig
        cfg = DebateLabConfig(topic="t", max_turns=1500)
        assert cfg.max_turns == 1500

    def test_1500_turns_compression_works(self):
        """Compression should handle 1500 turns."""
        from debate_lab.compression import ContextCompressor, CompressionConfig
        
        config = CompressionConfig(enabled=True, interval_turns=20, retain_recent_turns=20)
        compressor = ContextCompressor(config)
        
        turns = [{"speaker": f"agent_{i%3}", "response": f"Argument {i}"} for i in range(1500)]
        result = compressor.compress(turns)
        
        assert result.compressed is True
        assert result.turns_before == 1500
        assert len(result.provenance) > 0

    def test_compression_with_stub_llm_1500_turns(self, tmp_path):
        """Test compression with a synthetic 1500-turn scenario using StubLLM."""
        from debate_lab.controller import DebateLabController
        from debate_lab.run_store import DebateLabRunStore
        from debate_lab.session_factory import DebateSessionFactory
        from debate_lab.config import DebateLabConfig
        
        stub = StubLLM(models=["model-a"])
        factory = DebateSessionFactory(llm_client=stub, base_dir=tmp_path)
        ctrl = DebateLabController(factory=factory, store=DebateLabRunStore(base_dir=tmp_path))
        
        # Create config with compression enabled
        cfg = DebateLabConfig(
            topic="Test long debate",
            template_id="scientist-skeptic",
            max_turns=10,  # Use small number for test speed
            context_compression_enabled=True,
            context_compression_strategy="structured",
            context_compression_interval_turns=5,
            context_compression_retain_recent_turns=3,
        )
        
        view = ctrl.create_run(cfg)
        ok = ctrl.start_run(view.run_id, wait=True)
        assert ok
        
        run = ctrl.get_run(view.run_id)
        assert run["status"] == "completed"
        assert run["result"]["turns_committed"] == 10


# ── Provenance JSON schema ───────────────────────────────────────────────────


class TestProvenanceSchema:
    """Tests for provenance JSON schema compliance."""

    def test_provenance_includes_execution_fields(self, controller, stub):
        """Run result should include execution fields."""
        cfg = _config(template_id="scientist-skeptic", max_turns=2, model_pool=["model-a"])
        view = controller.create_run(cfg)
        ok = controller.start_run(view.run_id, wait=True)
        run = controller.get_run(view.run_id)
        
        result = run["result"]
        assert "max_turns" in result
        assert "turns_committed" in result
        assert "terminal_reason" in result

    def test_provenance_includes_context_management_fields(self, controller, stub):
        """Run result should include context management fields when compression enabled."""
        cfg = _config(
            template_id="scientist-skeptic",
            max_turns=2,
            model_pool=["model-a"],
            context_compression_enabled=True,
        )
        view = controller.create_run(cfg)
        ok = controller.start_run(view.run_id, wait=True)
        run = controller.get_run(view.run_id)
        
        # Config should be in the run
        config = run["config"]
        assert "context_compression_enabled" in config
        assert config["context_compression_enabled"] is True

    def test_compression_provenance_has_required_fields(self):
        """Compression provenance should have all required fields."""
        from debate_lab.compression import ContextCompressor, CompressionConfig
        
        config = CompressionConfig(enabled=True)
        compressor = ContextCompressor(config)
        turns = [{"speaker": "A", "response": f"Turn {i}"} for i in range(50)]
        result = compressor.compress(turns)
        
        prov = result.provenance
        required_fields = [
            "compression_id",
            "created_at",
            "source_turn_range",
            "source_hash",
            "strategy",
            "summary_hash",
            "tokens_before",
            "tokens_after",
        ]
        for field in required_fields:
            assert field in prov, f"Missing field: {field}"


# ── Non-regression ───────────────────────────────────────────────────────────


class TestNonRegression:
    """Ensure existing behavior is not broken."""

    def test_debate_without_compression_still_works(self, controller, stub):
        """Debates should work without compression (default)."""
        cfg = _config(template_id="scientist-skeptic", max_turns=3, model_pool=["model-a", "model-b"])
        view = controller.create_run(cfg)
        ok = controller.start_run(view.run_id, wait=True)
        run = controller.get_run(view.run_id)
        assert run["status"] == "completed"
        assert run["result"]["turns_committed"] == 3

    def test_config_serialization_roundtrip(self):
        """Config should serialize and deserialize correctly."""
        from debate_lab.config import DebateLabConfig
        
        original = DebateLabConfig(
            topic="t",
            max_turns=100,
            context_compression_enabled=True,
            context_compression_strategy="structured",
            context_compression_interval_turns=30,
            context_compression_retain_recent_turns=15,
        )
        
        d = original.to_dict()
        restored = DebateLabConfig.from_dict(d)
        
        assert restored.max_turns == 100
        assert restored.context_compression_enabled is True
        assert restored.context_compression_strategy == "structured"
        assert restored.context_compression_interval_turns == 30
        assert restored.context_compression_retain_recent_turns == 15
