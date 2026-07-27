from pathlib import Path

import pytest

from src.heuristic.archive import ArchiveEntry
from src.heuristic.contracts import EvaluationRecord, Fidelity
from src.heuristic.runner import RunConfig
from src.heuristic.storage import ArtifactStore, HeuristicStore
from src.heuristic.workflow import EpochSchedule, HeuristicRunState


def record(candidate="a" * 64):
    return EvaluationRecord(
        candidate, "ogc", "prob_1", Fidelity.SEARCH, 0, "v1", True, 10.0
    )


def test_atomic_proposal_is_idempotent_and_restores_rng(tmp_path: Path):
    store = HeuristicStore(tmp_path / "db.sqlite3")
    state = HeuristicRunState("run", proposal_budget=2, rng_seed=7)
    state.consume_proposal()
    state.archive.add(ArchiveEntry("a" * 64, 1.0))
    checkpoint = state.checkpoint()
    assert store.commit_proposal(
        run_id="run",
        proposal=1,
        operator="new_paradigm",
        parent_hashes=[],
        child_hash="a" * 64,
        transition={},
        evaluations=[record()],
        checkpoint=checkpoint,
    )
    assert not store.commit_proposal(
        run_id="run",
        proposal=1,
        operator="new_paradigm",
        parent_hashes=[],
        child_hash="a" * 64,
        transition={},
        evaluations=[record()],
        checkpoint=checkpoint,
    )
    restored = HeuristicRunState.restore(store.load_checkpoint("run"))
    assert restored.checkpoint()["rng_state"] == state.checkpoint()["rng_state"]
    assert restored.proposals == 1
    assert len(store.events("run")) == 1


def test_epoch_event_and_refreshed_checkpoint_commit_together(tmp_path: Path):
    store = HeuristicStore(tmp_path / "epoch.sqlite3")
    checkpoint = {
        "run_id": "run",
        "proposals": 20,
        "epoch": 1,
        "archive": {"entries": [], "repair_lane": []},
    }
    assert store.commit_epoch(
        run_id="run",
        epoch=1,
        proposal=20,
        payload={"promoted": []},
        checkpoint=checkpoint,
    )
    assert store.has_event("run:epoch:1")
    assert store.load_checkpoint("run")["epoch"] == 1
    assert not store.commit_epoch(
        run_id="run",
        epoch=1,
        proposal=20,
        payload={"promoted": ["different"]},
        checkpoint={**checkpoint, "epoch": 99},
    )
    assert store.load_checkpoint("run")["epoch"] == 1


def test_failed_proposal_transaction_leaves_no_partial_budget_or_lineage(tmp_path):
    import sqlite3

    store = HeuristicStore(tmp_path / "rollback.sqlite3")
    with pytest.raises(sqlite3.IntegrityError):
        store.commit_proposal(
            run_id="rollback",
            proposal=1,
            operator="new_paradigm",
            parent_hashes=[],
            child_hash="a" * 64,
            transition={"quality": 1.0},
            evaluations=[record()],
            checkpoint={"run_id": "rollback", "proposals": 1},
            # A null run_id violates the BKS transaction schema after the
            # immutable evaluation insert has already been attempted.
            bks_updates=[
                (None, "ogc", "10s", "prob_1", 10.0, "a" * 64)  # type: ignore[list-item]
            ],
        )
    assert store.events("rollback") == []
    assert store.transitions("rollback") == []
    assert store.load_checkpoint("rollback") is None
    assert store.evaluation_records() == []


def test_artifacts_and_evaluation_accounting(tmp_path: Path):
    artifacts = ArtifactStore(tmp_path / "artifacts")
    digest = artifacts.put_bytes(b"hello")
    assert artifacts.read_bytes(digest) == b"hello"
    assert EpochSchedule.full_evaluation_count() == 7120


def test_role_caps_and_three_epoch_stopping():
    state = HeuristicRunState("caps", proposal_budget=200, support_budget=2)
    state.consume_support("planner")
    state.consume_support("oracle")

    with pytest.raises(RuntimeError, match="support-role"):
        state.consume_support("hacker")
    state.best_training = 0.0
    state.best_validation_lcb = 0.0
    for epoch in (3, 4, 5):
        state.epoch = epoch
        state.update_epoch_progress(0.0, [0.0] * 8)
    assert state.should_stop()


def test_infeasible_validation_cannot_become_incumbent():
    state = HeuristicRunState("validation")
    state.epoch = 3
    state.update_epoch_progress(
        1.0,
        [100.0] * 8,
        validation_feasible=False,
    )
    assert state.best_validation_lcb == float("-inf")


def test_acceptance_config_can_disable_early_stopping():
    assert not RunConfig("acceptance", early_stopping=False).early_stopping


def test_bks_snapshots_are_fidelity_separated(tmp_path: Path):
    store = HeuristicStore(tmp_path / "bks.sqlite3")
    store.record_bks("ogc", "10s", "prob_1", 100.0, "a" * 64)
    store.record_bks("ogc", "10s", "prob_1", 90.0, "b" * 64)
    store.record_bks("ogc", "60s", "prob_1", 70.0, "c" * 64)
    assert store.activate_pending_bks("ogc", "10s", 1) == {"prob_1": 90.0}
    assert store.activate_pending_bks("ogc", "60s", 1) == {"prob_1": 70.0}
    assert store.bks_snapshot(
        run_id="global",
        problem_id="ogc",
        fidelity="10s",
        epoch=1,
    ) == {"prob_1": 90.0}
    store.record_bks(
        "ogc",
        "10s",
        "prob_1",
        50.0,
        "d" * 64,
        run_id="other",
    )
    assert store.activate_pending_bks("ogc", "10s", 1, run_id="other") == {
        "prob_1": 50.0
    }
    assert store.bks_snapshot(
        run_id="global",
        problem_id="ogc",
        fidelity="10s",
        epoch=1,
    ) == {"prob_1": 90.0}
