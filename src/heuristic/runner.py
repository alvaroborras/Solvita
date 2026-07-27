"""End-to-end heuristic run coordinator over adapters, evaluators, and storage."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Protocol, Sequence

from .agents import (
    RolePrompt,
    assert_no_validation_leakage,
    hacker_prompt,
    oracle_prompt,
    planner_prompt,
    solver_prompt,
)
from .archive import ArchiveEntry
from .bundle import CandidateBundleV1
from .contracts import Fidelity
from .dgs import DGSObservation, QDSelector
from .knowledge import StrategyCard, StrategyStore
from .operators import OPERATORS, Operator
from .scoring import (
    robust_aggregate,
    training_quality_matrix,
    validation_gain,
    validation_lcb,
)
from .storage import ArtifactStore, HeuristicStore
from .workflow import EpochSchedule, HeuristicRunState


class SolverBackend(Protocol):
    def generate(
        self,
        operator: Operator,
        parents: Sequence[CandidateBundleV1],
        context: Mapping[str, Any],
    ) -> CandidateBundleV1: ...


class SupportBackend(Protocol):
    def respond(self, prompt: RolePrompt) -> str: ...


@dataclass
class SeedSolver:
    seed: CandidateBundleV1

    def generate(self, operator, parents, context) -> CandidateBundleV1:
        # Two semantics-preserving variants exercise non-duplicate promotion
        # accounting without pretending to be an optimizing solver.
        variant = int(context.get("proposal", 1)) % 2
        files = dict(self.seed.files)
        files["main.cpp"] = (
            files["main.cpp"] + f"\n// SOLVITA_SMOKE_VARIANT_{variant}\n"
        )
        return CandidateBundleV1(files)


@dataclass
class CommandSolver:
    command: Sequence[str]

    def generate(self, operator, parents, context) -> CandidateBundleV1:
        request = {
            "operator": operator.__dict__,
            "parents": [json.loads(parent.canonical_json()) for parent in parents],
            "context": dict(context),
        }
        process = subprocess.run(
            list(self.command),
            input=json.dumps(request).encode(),
            capture_output=True,
            timeout=600,
        )
        if process.returncode:
            # Malformed solver output is represented as a compilable invalid
            # candidate so the failed proposal remains durable and countable.
            return CandidateBundleV1({"main.cpp": "int main(){return 1;}\n"})
        return CandidateBundleV1.from_json(process.stdout.decode("utf-8"))


@dataclass
class UnifiedLLMSolver:
    llm_config: Mapping[str, Any]
    _runtime_config: dict[str, Any] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        from src.llm.token_usage import ensure_token_usage_accumulator

        self._runtime_config = dict(self.llm_config)
        ensure_token_usage_accumulator(self._runtime_config)

    def generate(self, operator, parents, context) -> CandidateBundleV1:
        from src.llm.unified_client import UnifiedLLMClient

        strategies = [
            StrategyCard(**raw)
            for raw in context.get("strategies", [])
            if isinstance(raw, dict)
        ]
        prompt = solver_prompt(
            operator=operator,
            parent_sources=[parent.canonical_json() for parent in parents],
            training_feedback=context,
            strategies=strategies,
        )
        config = UnifiedLLMClient.build_role_config(
            self._runtime_config, "solver_codegen"
        )
        response = UnifiedLLMClient(config).chat(
            [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ]
        )
        return CandidateBundleV1.from_json(response)

    def usage_snapshot(self) -> Mapping[str, Any]:
        from src.llm.token_usage import get_token_usage_snapshot

        return get_token_usage_snapshot(self._runtime_config)


@dataclass
class UnifiedLLMSupport:
    llm_config: Mapping[str, Any]
    _runtime_config: dict[str, Any] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        from src.llm.token_usage import ensure_token_usage_accumulator

        self._runtime_config = dict(self.llm_config)
        ensure_token_usage_accumulator(self._runtime_config)

    def respond(self, prompt: RolePrompt) -> str:
        from src.llm.unified_client import UnifiedLLMClient

        config = UnifiedLLMClient.build_role_config(self._runtime_config, prompt.role)
        return UnifiedLLMClient(config).chat(
            [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ]
        )

    def usage_snapshot(self) -> Mapping[str, Any]:
        from src.llm.token_usage import get_token_usage_snapshot

        return get_token_usage_snapshot(self._runtime_config)


@dataclass
class RunConfig:
    run_id: str
    engine: str = "solvita_dgs"
    proposals: int = 200
    support_calls: int = 40
    epoch_size: int = 20
    promotions: int = 2
    seed: int = 0
    improvement_threshold: float = 0.005
    early_stopping: bool = True
    plugin_hash: str = ""
    manifest_digest: str = ""
    language_standard: str = ""
    image_digest: str = ""


class HeuristicRunner:
    def __init__(
        self,
        *,
        problem,
        evaluator,
        store: HeuristicStore,
        artifacts: ArtifactStore,
        solver: SolverBackend,
        config: RunConfig,
        support: SupportBackend | None = None,
        strategy_store: StrategyStore | None = None,
    ):
        self.problem, self.evaluator, self.store = problem, evaluator, store
        self.artifacts, self.solver, self.config = artifacts, solver, config
        self.support = support
        self.strategy_store = strategy_store
        self.minimize = problem.manifest.objective == "minimize"
        self.config.plugin_hash = self.config.plugin_hash or problem.adapter.hash()
        self.config.manifest_digest = (
            self.config.manifest_digest or problem.manifest.digest()
        )
        self.config.language_standard = (
            self.config.language_standard or problem.manifest.default_standard
        )
        self.config.image_digest = self.config.image_digest or str(
            getattr(evaluator, "_image_digest", "") or "trusted-test-evaluator"
        )
        self.schedule = EpochSchedule(config.epoch_size, config.promotions)
        checkpoint = store.load_checkpoint(config.run_id)
        self.state = (
            HeuristicRunState.restore(checkpoint)
            if checkpoint
            else HeuristicRunState(
                config.run_id,
                config.proposals,
                config.support_calls,
                config.epoch_size,
                rng_seed=config.seed,
            )
        )
        self.bundles: dict[str, CandidateBundleV1] = {}
        for row in self.store.candidates():
            try:
                payload = self.artifacts.read_bytes(
                    row["bundle_artifact"], ".bundle.json"
                ).decode()
                bundle = CandidateBundleV1.from_json(payload)
                self.bundles[bundle.digest] = bundle
            except (FileNotFoundError, ValueError):
                continue
        self.train, self.validation = problem.adapter.split()
        self.baselines: dict[str, dict[str, float]] = {"10s": {}, "60s": {}}
        self.active_bks: dict[str, dict[str, float]] = {"10s": {}, "60s": {}}
        raw_features = {
            instance_id: problem.adapter.features(instance_id)
            for instance_id in self.train
        }
        feature_names = sorted(
            {name for values in raw_features.values() for name in values}
        )
        feature_rows = {
            instance_id: [float(values.get(name, 0.0)) for name in feature_names]
            for instance_id, values in raw_features.items()
        }
        columns = list(zip(*feature_rows.values()))
        means = [sum(column) / len(column) for column in columns]
        scales = [
            max(
                1e-9,
                (sum((value - mean) ** 2 for value in column) / len(column)) ** 0.5,
            )
            for column, mean in zip(columns, means)
        ]
        normalized_features = {
            instance_id: [
                (value - mean) / scale for value, mean, scale in zip(row, means, scales)
            ]
            for instance_id, row in feature_rows.items()
        }
        self.feature_summary = {
            "instances": len(feature_rows),
            "feature_names": feature_names,
            "means": dict(zip(feature_names, means)),
            "scales": dict(zip(feature_names, scales)),
        }
        self.instance_feature_rows = normalized_features
        self.selector = QDSelector(normalized_features, seed=config.seed)
        for raw in self.state.metadata.get("dgs_observations", []):
            self.selector.observe(DGSObservation(**raw))
        surrogate_artifact = self.state.metadata.get("surrogate_artifact")
        if surrogate_artifact:
            try:
                surrogate_state = json.loads(
                    self.artifacts.read_bytes(surrogate_artifact, ".json").decode(
                        "utf-8"
                    )
                )
                self.selector.load_state_dict(surrogate_state)
            except (FileNotFoundError, ValueError):
                surrogate_artifact = None
        if not surrogate_artifact:
            refreshed_count = int(self.state.metadata.get("dgs_refresh_count", 0))
            if refreshed_count:
                self.selector.refresh(refreshed_count)
        existing_run = self.store.run(config.run_id)
        if existing_run is not None:
            existing_config = existing_run["config"]
            for key in (
                "plugin_hash",
                "manifest_digest",
                "language_standard",
                "image_digest",
            ):
                if existing_config.get(key) not in (None, "", getattr(config, key)):
                    raise RuntimeError(
                        f"cannot resume {config.run_id}: pinned {key} changed"
                    )
        self.store.create_run(
            config.run_id,
            problem.manifest.problem_id,
            config.engine,
            config.__dict__,
        )

    def register_bundle(self, bundle: CandidateBundleV1) -> None:
        artifact = self.artifacts.put_bytes(
            bundle.canonical_json().encode(), ".bundle.json"
        )
        self.store.save_candidate(
            bundle.digest, artifact, self.problem.manifest.default_standard
        )
        self.bundles[bundle.digest] = bundle

    def _observe_dgs(self, observation: DGSObservation) -> None:
        self.selector.observe(observation)
        self.state.metadata.setdefault("dgs_observations", []).append(
            asdict(observation)
        )

    def baseline_preflight(self, baseline: CandidateBundleV1) -> None:
        self.register_bundle(baseline)
        for fidelity, ids in (
            (Fidelity.SEARCH, self.train),
            (Fidelity.PROMOTION, self.train + self.validation),
        ):
            for instance_id in ids:
                record = self.evaluator.evaluate(
                    baseline, instance_id, fidelity, self.config.seed
                )
                if not record.feasible or record.objective is None:
                    raise RuntimeError(
                        f"baseline infeasible on {instance_id}/{fidelity.value}: {record.failure}"
                    )
                self.baselines[fidelity.value][instance_id] = record.objective
                if instance_id in self.train:
                    self.store.record_bks(
                        self.problem.manifest.problem_id,
                        fidelity.value,
                        instance_id,
                        record.objective,
                        baseline.digest,
                        run_id=self.config.run_id,
                    )
        self.active_bks["10s"] = dict(self.baselines["10s"])
        self.active_bks["60s"] = {
            key: value
            for key, value in self.baselines["60s"].items()
            if key in self.train
        }
        self.store.append_event(
            "baseline_preflight",
            f"{self.config.run_id}:baseline",
            {
                "candidate_hash": baseline.digest,
                "instances": len(self.train) + len(self.validation),
            },
            run_id=self.config.run_id,
        )

    def _evaluate_training(self, bundle: CandidateBundleV1, fidelity: Fidelity):
        records = [
            self.evaluator.evaluate(bundle, instance_id, fidelity, self.config.seed)
            for instance_id in self.train
        ]
        self.state.consume_evaluations(len(records))
        objectives = {
            record.instance_id: (
                record.objective
                if record.feasible and record.objective is not None
                else None
            )
            for record in records
        }
        qualities = self._score_objectives(objectives, fidelity.value)
        candidate_objectives = self.state.metadata.setdefault(
            "candidate_objectives", {}
        )
        candidate_objectives.setdefault(bundle.digest, {})[fidelity.value] = objectives
        population = self.state.metadata.setdefault(
            "population_objectives", {}
        ).setdefault(fidelity.value, {})
        for instance_id, objective in objectives.items():
            if objective is not None:
                population.setdefault(instance_id, []).append(objective)
        return records, qualities

    def _score_objectives(
        self, objectives: Mapping[str, float | None], fidelity: str
    ) -> dict[str, float]:
        population = self.state.metadata.get("population_objectives", {}).get(
            fidelity, {}
        )
        return training_quality_matrix(
            objectives,
            self.baselines[fidelity],
            self.active_bks[fidelity],
            population,
            minimize=self.minimize,
        )

    def _refresh_derived_scores(self) -> None:
        candidate_objectives = self.state.metadata.get("candidate_objectives", {})
        archive_scores: dict[str, tuple[float, Mapping[str, float]]] = {}
        for entry in self.state.archive.entries():
            objectives = candidate_objectives.get(entry.candidate_hash, {}).get("10s")
            if objectives:
                scores = self._score_objectives(objectives, "10s")
                archive_scores[entry.candidate_hash] = (
                    robust_aggregate(scores.values()),
                    scores,
                )
        self.state.archive.replace_scores(archive_scores)

        refreshed: list[DGSObservation] = []
        for raw in self.state.metadata.get("dgs_observations", []):
            observation = DGSObservation(**raw)
            objectives = candidate_objectives.get(observation.candidate_hash, {}).get(
                observation.fidelity
            )
            if objectives:
                scores = self._score_objectives(objectives, observation.fidelity)
                observation = DGSObservation(
                    observation.candidate_hash,
                    observation.source,
                    robust_aggregate(scores.values()),
                    observation.fidelity,
                    observation.operator,
                    observation.parent_hash,
                    scores,
                )
            refreshed.append(observation)
        self.selector = QDSelector(self.instance_feature_rows, seed=self.config.seed)
        for observation in refreshed:
            self.selector.observe(observation)
        self.selector.refresh()
        self.state.metadata["dgs_observations"] = [
            asdict(observation) for observation in refreshed
        ]
        self.state.metadata["dgs_refresh_count"] = len(refreshed)
        self.state.metadata["surrogate_artifact"] = self.artifacts.put_json(
            self.selector.state_dict()
        )

    def _support_event(self, role: str, payload: Mapping[str, Any]) -> None:
        if self.state.support_calls >= self.state.support_budget:
            return
        event_key = f"{self.config.run_id}:{role}:{self.state.support_calls + 1}"
        existing = self.store.event(event_key)
        if existing is not None:
            self.state.consume_support(role)
            response = existing["payload"].get("response")
            if response is not None:
                self.state.metadata.setdefault("support_responses", {}).setdefault(
                    role, []
                ).append(response)
            return
        self.state.consume_support(role)
        response = None
        if self.support:
            if role == "planner":
                prompt = planner_prompt(
                    (
                        f"Problem {self.problem.manifest.problem_id} "
                        f"({self.problem.manifest.objective}); produce architecture "
                        "hypotheses and independent seed briefs."
                    ),
                    {**self.feature_summary, **dict(payload)},
                )
            elif role == "oracle":
                prompt = oracle_prompt(self.state.epoch, payload)
            elif role == "hacker":
                prompt = hacker_prompt(self.state.epoch, payload)
            else:
                prompt = RolePrompt(
                    role,
                    f"You are Solvita {role.title()}. Use training evidence only.",
                    json.dumps(dict(payload), sort_keys=True),
                )
            response = self.support.respond(prompt)
            self._refresh_usage_metadata()
            self.state.metadata.setdefault("support_responses", {}).setdefault(
                role, []
            ).append(response)
        self.store.append_event(
            role,
            event_key,
            {**dict(payload), "response": response},
            run_id=self.config.run_id,
            proposal=self.state.proposals,
        )

    def _refresh_usage_metadata(self) -> None:
        snapshots = []
        for backend in (self.solver, self.support):
            snapshot = getattr(backend, "usage_snapshot", None)
            if callable(snapshot):
                snapshots.append(snapshot())
        if not snapshots:
            return
        self.state.metadata["tokens"] = sum(
            int(item.get("prompt_tokens", 0)) + int(item.get("completion_tokens", 0))
            for item in snapshots
        )
        self.state.metadata["llm_calls"] = sum(
            int(item.get("llm_calls", 0)) for item in snapshots
        )

    def _epoch_boundary(self) -> None:
        entries = self.state.archive.entries()[: self.config.promotions]
        promoted: list[tuple[ArchiveEntry, float]] = []
        for entry in entries:
            bundle = self.bundles.get(entry.candidate_hash)
            if bundle is None:
                continue
            records, qualities = self._evaluate_training(bundle, Fidelity.PROMOTION)
            promotion_quality = robust_aggregate(qualities.values())
            promoted.append((entry, promotion_quality))
            self._observe_dgs(
                DGSObservation(
                    entry.candidate_hash,
                    bundle.canonical_json(),
                    promotion_quality,
                    "60s",
                    "promotion",
                    instance_scores=qualities,
                )
            )
            for record in records:
                if record.feasible and record.objective is not None:
                    self.store.record_bks(
                        self.problem.manifest.problem_id,
                        "60s",
                        record.instance_id,
                        record.objective,
                        entry.candidate_hash,
                        run_id=self.config.run_id,
                    )
        promoted.sort(key=lambda item: (-item[1], item[0].candidate_hash))
        validation_values: list[float] = []
        validation_feasible = bool(promoted)
        validation_candidate_hash: str | None = None
        if promoted:
            best = self.bundles[promoted[0][0].candidate_hash]
            validation_candidate_hash = best.digest
            for instance_id in self.validation:
                record = self.evaluator.evaluate(
                    best, instance_id, Fidelity.PROMOTION, self.config.seed
                )
                self.state.consume_evaluations(1)
                validation_feasible = (
                    validation_feasible
                    and record.feasible
                    and record.objective is not None
                )
                validation_values.append(
                    validation_gain(
                        record.objective,
                        self.baselines["60s"][instance_id],
                        minimize=self.minimize,
                    )
                    if record.feasible and record.objective is not None
                    else -3.0
                )
        self._support_event(
            "oracle", {"epoch": self.state.epoch, "audit": "scores,bks,anomalies"}
        )
        self._support_event(
            "hacker",
            {
                "epoch": self.state.epoch,
                "analysis": "regret,rank_flips,weak_clusters,invalidity,timeouts",
            },
        )
        for fidelity in ("10s", "60s"):
            activated = self.store.activate_pending_bks(
                self.problem.manifest.problem_id,
                fidelity,
                self.state.epoch,
                minimize=self.minimize,
                run_id=self.config.run_id,
            )
            self.active_bks[fidelity].update(activated)
        self._refresh_derived_scores()
        promoted_scores = [
            robust_aggregate(
                self._score_objectives(
                    self.state.metadata["candidate_objectives"][entry.candidate_hash][
                        "60s"
                    ],
                    "60s",
                ).values()
            )
            for entry, _ in promoted
        ]
        training_score = (
            max(promoted_scores)
            if promoted_scores
            else max(
                (entry.quality for entry in self.state.archive.entries()),
                default=self.state.best_training,
            )
        )
        improved = self.state.update_epoch_progress(
            training_score,
            validation_values or [-3.0],
            self.config.improvement_threshold,
            validation_feasible=validation_feasible,
        )
        current_validation_lcb = (
            validation_lcb(validation_values) if validation_feasible else float("-inf")
        )
        incumbent_lcb = float(
            self.state.metadata.get("validation_incumbent_lcb", float("-inf"))
        )
        if (
            validation_feasible
            and validation_candidate_hash is not None
            and (
                current_validation_lcb > incumbent_lcb
                or (
                    current_validation_lcb == incumbent_lcb
                    and validation_candidate_hash
                    < str(self.state.metadata.get("validation_incumbent_hash", "~"))
                )
            )
        ):
            self.state.metadata["validation_incumbent_hash"] = validation_candidate_hash
            self.state.metadata["validation_incumbent_lcb"] = current_validation_lcb
        if not improved:
            self._support_event(
                "planner",
                {"epoch": self.state.epoch, "phase": "plateau_reset"},
            )
        self.state.active_bks_epoch = self.state.epoch
        self.store.commit_epoch(
            run_id=self.config.run_id,
            epoch=self.state.epoch,
            proposal=self.state.proposals,
            payload={
                "promoted": [entry.candidate_hash for entry, _ in promoted],
                "validation_candidate_hash": validation_candidate_hash,
                "validation_feasible": validation_feasible,
                "validation_epoch_lcb": current_validation_lcb,
                "validation_lcb": self.state.best_validation_lcb,
            },
            checkpoint=self.state.checkpoint(),
        )

    def run(self, baseline: CandidateBundleV1) -> HeuristicRunState:
        if not self.baselines["10s"]:
            self.baseline_preflight(baseline)
        if self.state.active_bks_epoch:
            for fidelity in ("10s", "60s"):
                restored_snapshot = self.store.bks_snapshot(
                    run_id=self.config.run_id,
                    problem_id=self.problem.manifest.problem_id,
                    fidelity=fidelity,
                    epoch=self.state.active_bks_epoch,
                )
                if restored_snapshot:
                    self.active_bks[fidelity] = restored_snapshot
        if self.state.proposals == 0:
            self._support_event("planner", {"phase": "initialization"})
            self._support_event("oracle", {"phase": "plugin_audit"})
        elif self.schedule.boundary(self.state.proposals) and not self.store.has_event(
            f"{self.config.run_id}:epoch:{self.state.epoch}"
        ):
            self._epoch_boundary()
        while not self.state.complete and not (
            self.config.early_stopping and self.state.should_stop()
        ):
            operator = self.state.select_operator(self.config.engine)
            parent_entries = self.state.select_parents(operator, self.config.engine)
            if (
                self.config.engine == "solvita_dgs"
                and self.state.proposals >= 40
                and operator.name != "repair_invalid"
                and (
                    selection := self.selector.select(
                        OPERATORS, self.state.archive.parent_pool()
                    )
                )
            ):
                operator, selected_parent = selection
                parent_entries = self.selector.complete_parents(
                    operator,
                    selected_parent,
                    self.state.archive.parent_pool(),
                )
            parents = [
                self.bundles[item.candidate_hash]
                for item in parent_entries
                if item.candidate_hash in self.bundles
            ]
            strategies = (
                self.strategy_store.retrieve(
                    domain=self.problem.manifest.problem_family,
                    include_incubator=True,
                    problem_id=self.problem.manifest.problem_id,
                )
                if self.strategy_store
                else []
            )
            generation_failure = None
            try:
                planner_responses = self.state.metadata.get(
                    "support_responses", {}
                ).get("planner", [])
                support_responses = self.state.metadata.get("support_responses", {})
                solver_context = {
                    "proposal": self.state.proposals + 1,
                    "mode": operator.mode,
                    "strategies": [asdict(card) for card in strategies],
                    "planner_brief": (
                        planner_responses[-1] if planner_responses else None
                    ),
                    "support_guidance": {
                        role: responses[-1]
                        for role, responses in support_responses.items()
                        if role in {"oracle", "hacker"} and responses
                    },
                }
                assert_no_validation_leakage(solver_context)
                child = self.solver.generate(
                    operator,
                    parents,
                    solver_context,
                )
            except (ValueError, subprocess.TimeoutExpired) as exc:
                generation_failure = f"{type(exc).__name__}: {exc}"[:2000]
                child = CandidateBundleV1(
                    {
                        "main.cpp": (
                            '#error "Solver failed to produce CandidateBundleV1"\n'
                            "int main() { return 1; }\n"
                        )
                    }
                )
            self._refresh_usage_metadata()
            proposal = self.state.consume_proposal()
            self.register_bundle(child)
            records, qualities = self._evaluate_training(child, Fidelity.SEARCH)
            quality = robust_aggregate(qualities.values())
            novelty = self.selector.novelty(child.digest, child.canonical_json())
            entry = ArchiveEntry(
                child.digest,
                quality,
                novelty=novelty,
                cluster=max(
                    qualities,
                    key=lambda instance_id: (
                        qualities[instance_id],
                        instance_id,
                    ),
                    default="global",
                ),
                valid=all(record.feasible for record in records),
                lineage=parent_entries[0].lineage
                if parent_entries
                else f"seed-{proposal}",
                instance_scores=qualities,
            )
            self.state.archive.mark_selected(
                {parent.candidate_hash for parent in parent_entries}
            )
            self.state.archive.add(entry)
            self._observe_dgs(
                DGSObservation(
                    child.digest,
                    child.canonical_json(),
                    quality,
                    "10s",
                    operator.name,
                    parent_entries[0].candidate_hash if parent_entries else None,
                    qualities,
                )
            )
            if self.strategy_store and parent_entries:
                delta = quality - parent_entries[0].quality
                lineage_cards = self.state.metadata.setdefault("lineage_cards", {})
                inherited_cards = {
                    card_id
                    for parent in parent_entries
                    for card_id in lineage_cards.get(parent.candidate_hash, [])
                }
                current_cards = {card.card_id for card in strategies}
                for card in strategies:
                    self.strategy_store.add_evidence(
                        card.card_id,
                        self.problem.manifest.problem_id,
                        self.problem.manifest.problem_family,
                        delta,
                        descendant_delta=delta,
                        context={
                            "run_id": self.config.run_id,
                            "proposal": proposal,
                            "operator": operator.name,
                            "observational": True,
                            "evidence_kind": "direct_transition",
                        },
                    )
                for card_id in sorted(inherited_cards - current_cards):
                    self.strategy_store.add_evidence(
                        card_id,
                        self.problem.manifest.problem_id,
                        self.problem.manifest.problem_family,
                        0.0,
                        descendant_delta=delta,
                        context={
                            "run_id": self.config.run_id,
                            "proposal": proposal,
                            "operator": operator.name,
                            "observational": True,
                            "evidence_kind": "descendant",
                        },
                    )
                lineage_cards[child.digest] = sorted(inherited_cards | current_cards)
            elif self.strategy_store:
                self.state.metadata.setdefault("lineage_cards", {})[child.digest] = (
                    sorted(card.card_id for card in strategies)
                )
            bks_updates = [
                (
                    self.config.run_id,
                    self.problem.manifest.problem_id,
                    "10s",
                    record.instance_id,
                    record.objective,
                    child.digest,
                )
                for record in records
                if record.feasible and record.objective is not None
            ]
            self.store.commit_proposal(
                run_id=self.config.run_id,
                proposal=proposal,
                operator=operator.name,
                parent_hashes=[entry.candidate_hash for entry in parent_entries],
                child_hash=child.digest,
                transition={
                    "quality": quality,
                    "mode": operator.mode,
                    "strategy_cards": [card.card_id for card in strategies],
                    "generation_failure": generation_failure,
                },
                evaluations=records,
                checkpoint=self.state.checkpoint(),
                bks_updates=bks_updates,
            )
            if self.schedule.boundary(proposal):
                self._epoch_boundary()
        self.store.set_run_status(self.config.run_id, "completed")
        return self.state
