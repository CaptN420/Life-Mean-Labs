"""P0.2 — reproducibility block: what produced this result?

The manifest must state the engine version, the environment, a dependency
fingerprint, the git state, the seed and the models actually assigned. These
tests pin the contract and its two safety properties: no secret leaks, and a
stable fingerprint for identical conditions.
"""

from __future__ import annotations

import json

from experiments.reproducibility import (
    build_reproducibility_block,
    dependency_block,
    engine_block,
    environment_block,
    manifest_fingerprint,
)
from experiments.observability import AutopilotObservability


REQUIRED_KEYS = {
    "engine", "environment", "dependencies", "git",
    "seed", "deterministic", "models", "tools",
    "generator_version", "prompt_version",
}


def test_block_shape():
    block = build_reproducibility_block(config={"seed": 42})
    assert REQUIRED_KEYS.issubset(block.keys())
    assert block["engine"]["name"] == "life_mean_lab"
    assert isinstance(block["engine"]["version"], str) and block["engine"]["version"]
    assert block["environment"]["python"]
    assert block["dependencies"]["combined_sha256"]


def test_seed_comes_from_config_when_not_passed():
    block = build_reproducibility_block(config={"seed": 1234})
    assert block["seed"] == 1234
    # explicit argument wins
    assert build_reproducibility_block(config={"seed": 1234}, seed=7)["seed"] == 7


def test_models_collected_from_agents_and_role_models():
    cfg = {
        "seed": 1,
        "agents": [
            {"agent_id": "a1", "model_assignment": "qwen2.5-7b"},
            {"agent_id": "a2", "model": "llama-3-8b"},
            {"agent_id": "a3"},
        ],
        "role_models": {"coder": "deepseek-coder"},
    }
    block = build_reproducibility_block(config=cfg)
    assert block["models"] == ["deepseek-coder", "llama-3-8b", "qwen2.5-7b"]


def test_tools_collected_from_agents():
    cfg = {"agents": [{"agent_id": "a1", "allowed_tools": ["math_gcd", "math_lcm"]}]}
    assert build_reproducibility_block(config=cfg)["tools"] == ["math_gcd", "math_lcm"]


def test_fingerprint_is_stable_and_seed_sensitive():
    cfg = {"seed": 5, "agents": [{"agent_id": "a", "model_assignment": "m1"}]}
    a = build_reproducibility_block(config=cfg)
    b = build_reproducibility_block(config=dict(cfg))
    assert manifest_fingerprint(a) == manifest_fingerprint(b)

    c = build_reproducibility_block(config={**cfg, "seed": 6})
    assert manifest_fingerprint(a) != manifest_fingerprint(c)


def test_dependency_hash_stable_within_process():
    assert dependency_block()["combined_sha256"] == dependency_block()["combined_sha256"]


def test_environment_and_engine_are_honest():
    env = environment_block()
    assert env["python"].count(".") >= 1
    assert env["system"]
    # a version is either a real one or the explicit marker, never a guess
    assert engine_block()["version"] != ""


def test_no_secret_values_leak(monkeypatch):
    monkeypatch.setenv("LIFE_MEAN_LLM_API_KEY", "sk-super-secret-value-123")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-another-secret-456")
    blob = json.dumps(build_reproducibility_block(config={"seed": 1}), sort_keys=True)
    assert "sk-super-secret-value-123" not in blob
    assert "sk-another-secret-456" not in blob
    # no field is named like a credential
    lowered = blob.lower()
    for banned in ("api_key", "apikey", "token", "password"):
        assert banned not in lowered


def test_manifest_carries_reproducibility_block():
    obs = AutopilotObservability()
    obs.start_experiment(
        "exp_repro", {"seed": 99, "deterministic": True, "num_tasks": 2},
        prompt="gcd probe",
        agents=[{"agent_id": "agent_1", "model_assignment": "test-model"}],
    )
    obs.complete_experiment(status="COMPLETED")
    manifest = obs.export_manifest()

    assert "reproducibility" in manifest
    repro = manifest["reproducibility"]
    assert REQUIRED_KEYS.issubset(repro.keys())
    assert repro["seed"] == 99
    assert repro["deterministic"] is True
    assert "test-model" in repro["models"]
    assert manifest["reproducibility_fingerprint"] == manifest_fingerprint(repro)
    # backward compatible keys still present
    for key in ("experiment_id", "prompt", "config", "agents", "events", "traces", "progress"):
        assert key in manifest
