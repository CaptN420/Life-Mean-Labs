"""P0.1 — design persistence: a FROZEN design must survive a restart.

The store is the experiment's contract; if it only lives in RAM, no run can be
re-executed later. These tests pin: durable save/load, immutable frozen
snapshot, per-snapshot history, corrupt-file tolerance and loud write failures.
"""

from __future__ import annotations

import json

import pytest

from experimental.schema import DesignStateError, ExperimentDesign
from experimental.store import DesignStoreError, ExperimentDesignStore


def _design(design_id: str = "DESIGN-TEST0001") -> ExperimentDesign:
    return ExperimentDesign(
        title="Sorting robustness",
        description="Compare deterministic sorting strategies",
        research_question="Does edge-case coverage change stability?",
        design_id=design_id,
    )


def test_save_then_reload_from_disk(tmp_path):
    store = ExperimentDesignStore(tmp_path)
    store.save(_design())

    reloaded = ExperimentDesignStore(tmp_path)
    got = reloaded.get("DESIGN-TEST0001")
    assert got is not None
    assert got.title == "Sorting robustness"
    assert got.status == "DRAFT"


def test_frozen_design_survives_restart_with_its_hash(tmp_path):
    store = ExperimentDesignStore(tmp_path)
    d = store.save(_design())
    store.transition(d.design_id, "REVIEWED")
    store.transition(d.design_id, "APPROVED")
    frozen = store.transition(d.design_id, "FROZEN")

    reloaded = ExperimentDesignStore(tmp_path)
    got = reloaded.get(d.design_id)
    assert got.status == "FROZEN"
    assert got.frozen_hash == frozen.frozen_hash
    assert got.content_hash() == frozen.content_hash()


def test_history_keeps_every_snapshot(tmp_path):
    store = ExperimentDesignStore(tmp_path)
    d = store.save(_design())
    store.transition(d.design_id, "REVIEWED")
    store.transition(d.design_id, "APPROVED")
    store.transition(d.design_id, "FROZEN")

    reloaded = ExperimentDesignStore(tmp_path)
    statuses = [snap["status"] for snap in reloaded.history(d.design_id)]
    assert statuses == ["DRAFT", "REVIEWED", "APPROVED", "FROZEN"]


def test_frozen_snapshot_is_never_overwritten(tmp_path):
    store = ExperimentDesignStore(tmp_path)
    d = store.save(_design())
    store.transition(d.design_id, "FROZEN")
    files = sorted(p.name for p in tmp_path.iterdir())
    assert any(name.endswith(".FROZEN.json") for name in files)
    # the DRAFT snapshot is still there as well: nothing was clobbered
    assert any(name.endswith(".DRAFT.json") for name in files)
    assert len(files) == 2


def test_frozen_design_refuses_further_transition(tmp_path):
    store = ExperimentDesignStore(tmp_path)
    d = store.save(_design())
    store.transition(d.design_id, "FROZEN")
    with pytest.raises(DesignStateError):
        store.transition(d.design_id, "DRAFT")


def test_list_returns_one_entry_per_design(tmp_path):
    store = ExperimentDesignStore(tmp_path)
    store.save(_design("DESIGN-A"))
    store.save(_design("DESIGN-B"))
    assert len(store.list()) == 2
    assert [d["design_id"] for d in ExperimentDesignStore(tmp_path).list()] == [
        "DESIGN-A", "DESIGN-B",
    ]


def test_corrupt_file_is_skipped_not_guessed(tmp_path):
    store = ExperimentDesignStore(tmp_path)
    store.save(_design("DESIGN-GOOD"))
    (tmp_path / "DESIGN-BROKEN.v1.DRAFT.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "DESIGN-FOREIGN.v1.DRAFT.json").write_text(
        json.dumps({"schema": "something-else/9", "design": {}}), encoding="utf-8"
    )

    reloaded = ExperimentDesignStore(tmp_path)
    ids = [d["design_id"] for d in reloaded.list()]
    assert ids == ["DESIGN-GOOD"]


def test_write_failure_raises_instead_of_pretending(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory", encoding="utf-8")
    store = ExperimentDesignStore(blocker / "designs", autoload=False)
    with pytest.raises(DesignStoreError):
        store.save(_design())


def test_unknown_design_transition_is_an_error(tmp_path):
    store = ExperimentDesignStore(tmp_path)
    with pytest.raises(KeyError):
        store.transition("DESIGN-MISSING", "REVIEWED")
