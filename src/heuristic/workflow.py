"""Event-wise Solvita heuristic workflow, budgets, cadence, and resume state."""

from __future__ import annotations

import base64
import pickle
import random
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from .archive import ArchiveEntry, QDArchive
from .bundle import CandidateBundleV1
from .operators import BY_NAME, OPERATORS, Operator
from .scoring import robust_aggregate, validation_lcb


class Solver(Protocol):
    def __call__(
        self,
        *,
        operator: Operator,
        parents: Sequence[CandidateBundleV1],
        context: Mapping[str, Any],
    ) -> CandidateBundleV1: ...


@dataclass
class Budgets:
    proposals: int = 200
    support_calls: int = 40
    evaluation_calls: int | None = None
    tokens: int | None = None
    cost_usd: float | None = None
    wall_seconds: float | None = None


@dataclass
class HeuristicRunState:
    run_id: str
    proposal_budget: int = 200
    support_budget: int = 40
    epoch_size: int = 20
    proposals: int = 0
    support_calls: int = 0
    evaluation_calls: int = 0
    epoch: int = 0
    stagnant_guided_epochs: int = 0
    best_training: float = float("-inf")
    best_validation_lcb: float = float("-inf")
    archive: QDArchive = field(default_factory=QDArchive)
    rng_seed: int = 0
    active_bks_epoch: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self._rng = random.Random(self.rng_seed)

    def consume_proposal(self) -> int:
        if self.proposals >= self.proposal_budget:
            raise RuntimeError("proposal budget exhausted")
        self.proposals += 1
        self.epoch = self.proposals // self.epoch_size
        return self.proposals

    def consume_support(self, role: str = "support") -> int:
        if self.support_calls >= self.support_budget:
            raise RuntimeError("support-role budget exhausted")
        self.support_calls += 1
        self.metadata.setdefault("support_roles", []).append(role)
        return self.support_calls

    def consume_evaluations(self, count: int, cap: int | None = None) -> None:
        if cap is not None and self.evaluation_calls + count > cap:
            raise RuntimeError("evaluation budget exhausted")
        self.evaluation_calls += count

    @property
    def complete(self):
        return self.proposals >= self.proposal_budget

    def checkpoint(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "proposal_budget": self.proposal_budget,
            "support_budget": self.support_budget,
            "epoch_size": self.epoch_size,
            "proposals": self.proposals,
            "support_calls": self.support_calls,
            "evaluation_calls": self.evaluation_calls,
            "epoch": self.epoch,
            "stagnant_guided_epochs": self.stagnant_guided_epochs,
            "best_training": self.best_training,
            "best_validation_lcb": self.best_validation_lcb,
            "archive": self.archive.to_dict(),
            "rng_seed": self.rng_seed,
            "rng_state": base64.b64encode(pickle.dumps(self._rng.getstate())).decode(),
            "active_bks_epoch": self.active_bks_epoch,
            "metadata": self.metadata,
        }

    @classmethod
    def restore(cls, payload: Mapping[str, Any]) -> "HeuristicRunState":
        state = cls(
            run_id=str(payload["run_id"]),
            proposal_budget=int(payload["proposal_budget"]),
            support_budget=int(payload["support_budget"]),
            epoch_size=int(payload.get("epoch_size", 20)),
            proposals=int(payload["proposals"]),
            support_calls=int(payload["support_calls"]),
            evaluation_calls=int(payload.get("evaluation_calls", 0)),
            epoch=int(payload["epoch"]),
            stagnant_guided_epochs=int(payload.get("stagnant_guided_epochs", 0)),
            best_training=float(payload.get("best_training", float("-inf"))),
            best_validation_lcb=float(
                payload.get("best_validation_lcb", float("-inf"))
            ),
            archive=QDArchive.from_dict(payload["archive"]),
            rng_seed=int(payload.get("rng_seed", 0)),
            active_bks_epoch=int(payload.get("active_bks_epoch", 0)),
            metadata=dict(payload.get("metadata", {})),
        )
        if payload.get("rng_state"):
            state._rng.setstate(pickle.loads(base64.b64decode(payload["rng_state"])))
        return state

    def select_operator(self, engine: str) -> Operator:
        proposal = self.proposals
        if proposal < 16:
            # Independent seed briefs use architecture rewrites.
            return BY_NAME["new_paradigm"]
        choices = [op for op in OPERATORS if op.name != "repair_invalid"]
        if self.archive.repair_lane and proposal % 10 == 0:
            return BY_NAME["repair_invalid"]
        if engine == "best_of_n":
            return BY_NAME["new_paradigm"]
        if engine == "random_qd" or proposal < 40:
            return choices[self._rng.randrange(len(choices))]
        # DGS callers may replace this with acquisition ranking; stable fallback.
        return choices[proposal % len(choices)]

    def select_parents(self, operator: Operator, engine: str) -> list[ArchiveEntry]:
        if engine == "best_of_n" or self.proposals < 16:
            return []
        pool = self.archive.parent_pool()
        if operator.name == "repair_invalid" and self.archive.repair_lane:
            return self.archive.repair_lane[:1]
        if not pool:
            return []
        start = self._rng.randrange(len(pool))
        return [
            pool[(start + i) % len(pool)] for i in range(min(operator.arity, len(pool)))
        ]

    def update_epoch_progress(
        self,
        training_score: float,
        validation_values: Sequence[float],
        threshold: float = 0.005,
        *,
        validation_feasible: bool = True,
    ) -> bool:
        lcb = (
            validation_lcb(validation_values) if validation_feasible else float("-inf")
        )
        improved = (
            training_score > self.best_training + threshold
            or lcb > self.best_validation_lcb + threshold
        )
        self.best_training = max(self.best_training, training_score)
        self.best_validation_lcb = max(self.best_validation_lcb, lcb)
        if self.epoch <= 2:
            self.stagnant_guided_epochs = 0
        else:
            self.stagnant_guided_epochs = (
                0 if improved else self.stagnant_guided_epochs + 1
            )
        return improved

    def should_stop(self) -> bool:
        return self.complete or (self.epoch >= 5 and self.stagnant_guided_epochs >= 3)


@dataclass(frozen=True)
class EpochSchedule:
    epoch_size: int = 20
    promotions: int = 2

    def boundary(self, proposals: int) -> bool:
        return proposals > 0 and proposals % self.epoch_size == 0

    @staticmethod
    def full_evaluation_count(
        proposals: int = 200,
        train_instances: int = 32,
        validation_instances: int = 8,
        epochs: int = 10,
        promotions: int = 2,
    ) -> int:
        return (
            proposals * train_instances
            + epochs * promotions * train_instances
            + epochs * validation_instances
        )


def candidate_quality(instance_qualities: Mapping[str, float]) -> float:
    return robust_aggregate(instance_qualities.values())
