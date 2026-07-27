"""QD-DGS embeddings, bootstrapped utility, transition model, and acquisition."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, ClassVar, Iterable, Mapping, Sequence

import numpy as np


def _hash_embedding(text: str, dimensions: int = 384) -> np.ndarray:
    """Deterministic offline fallback; never silently used when strict=True."""
    result = np.zeros(dimensions, dtype=np.float32)
    for token in text.split():
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:4], "little") % dimensions
        result[index] += 1.0 if digest[4] & 1 else -1.0
    norm = float(np.linalg.norm(result))
    return result / norm if norm else result


class CodeEmbedder:
    model_name = "sentence-transformers/all-MiniLM-L6-v2"
    _shared_model: ClassVar[Any] = None

    def __init__(self, *, strict: bool = False):
        self.strict = strict
        self._model: Any = None
        self.cache: dict[str, np.ndarray] = {}

    def _load(self):
        if self._model is not None:
            return
        if self.__class__._shared_model is not None:
            self._model = self.__class__._shared_model
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name, device="cpu")
            self.__class__._shared_model = self._model
        except Exception:
            if self.strict:
                raise
            self._model = False

    def preflight(self) -> str:
        self._load()
        if not self._model:
            raise RuntimeError(
                f"required embedding model unavailable: {self.model_name}"
            )
        return self.model_name

    def embed(self, bundle_hash: str, canonical_source: str) -> np.ndarray:
        if bundle_hash in self.cache:
            return self.cache[bundle_hash]
        self._load()
        if self._model:
            vector = np.asarray(
                self._model.encode(canonical_source, normalize_embeddings=True),
                dtype=np.float32,
            )
        else:
            vector = _hash_embedding(canonical_source)
        self.cache[bundle_hash] = vector
        return vector


def instance_embedding(features: Any, residual: Any | None = None) -> np.ndarray:
    base = np.asarray(features, dtype=np.float32)
    if residual is None:
        return base
    residual_array = np.asarray(residual, dtype=np.float32)
    if residual_array.shape != base.shape:
        raise ValueError("instance residual must match feature shape")
    return base + residual_array


class ResidualCodeProjector:
    """Task-adaptive residual projection over frozen code embeddings."""

    def __init__(
        self, input_dimensions: int = 384, output_dimensions: int = 32, seed: int = 0
    ):
        rng = np.random.default_rng(seed)
        self.base = rng.normal(
            0.0,
            1.0 / math.sqrt(input_dimensions),
            size=(input_dimensions, output_dimensions),
        )
        self.residual = np.zeros_like(self.base)

    def transform(self, embedding: Any) -> np.ndarray:
        vector = np.asarray(embedding, dtype=np.float64)
        return vector @ (self.base + self.residual)

    def fit_residual(
        self,
        embeddings: Any,
        targets: Any,
        ridge: float = 1e-2,
    ) -> None:
        x = np.asarray(embeddings, dtype=np.float64)
        y = np.asarray(targets, dtype=np.float64)
        if not len(x):
            return
        desired = y - x @ self.base
        self.residual = np.asarray(
            np.linalg.solve(x.T @ x + ridge * np.eye(x.shape[1]), x.T @ desired),
            dtype=np.float64,
        )


FIDELITY_EMBEDDINGS = {
    "10s": np.asarray([1.0, 0.0], dtype=np.float32),
    "60s": np.asarray([0.0, 1.0], dtype=np.float32),
}


def utility_features(
    code_latent: Any,
    instance_latent: Any,
    fidelity: str,
) -> np.ndarray:
    if fidelity not in FIDELITY_EMBEDDINGS:
        raise ValueError(f"unknown fidelity: {fidelity}")
    return np.concatenate(
        [
            np.asarray(code_latent, dtype=np.float32),
            np.asarray(instance_latent, dtype=np.float32),
            FIDELITY_EMBEDDINGS[fidelity],
        ]
    )


@dataclass
class Prediction:
    mean: float
    uncertainty: float


class BootstrappedUtilityEnsemble:
    """Five-head deterministic bootstrapped ridge ensemble.

    The target combines magnitude, within-instance rank, and drift terms before
    fitting. This is lightweight enough for per-epoch full refreshes.
    """

    def __init__(self, heads: int = 5, ridge: float = 1e-3, seed: int = 0):
        self.heads, self.ridge, self.seed = heads, ridge, seed
        self.weights: list[np.ndarray] = []

    def fit(
        self,
        rows: Sequence[Sequence[float]],
        magnitude: Sequence[float],
        rank: Sequence[float] | None = None,
        drift: Sequence[float] | None = None,
    ) -> None:
        x = np.asarray(rows, dtype=np.float64)
        if x.ndim != 2 or len(x) == 0:
            self.weights = []
            return
        y = np.asarray(magnitude, dtype=np.float64)
        if rank is not None:
            y = y + 0.25 * np.asarray(rank, dtype=np.float64)
        if drift is not None:
            y = y + 0.10 * np.asarray(drift, dtype=np.float64)
        augmented = np.column_stack([x, np.ones(len(x))])
        rng = np.random.default_rng(self.seed)
        self.weights = []
        identity = np.eye(augmented.shape[1])
        for _ in range(self.heads):
            indices = rng.integers(0, len(x), len(x))
            xb, yb = augmented[indices], y[indices]
            self.weights.append(
                np.linalg.solve(xb.T @ xb + self.ridge * identity, xb.T @ yb)
            )

    def predict(self, row: Any) -> Prediction:
        if not self.weights:
            return Prediction(0.0, 1.0)
        x = np.append(np.asarray(row, dtype=np.float64), 1.0)
        values = np.asarray([float(x @ weight) for weight in self.weights])
        return Prediction(float(values.mean()), float(values.std(ddof=0)))


class DiagonalTransitionModel:
    def __init__(self):
        self.delta_mean: np.ndarray | None = None
        self.delta_var: np.ndarray | None = None

    def fit(self, parents: Any, children: Any) -> None:
        delta = np.asarray(children, dtype=np.float64) - np.asarray(
            parents, dtype=np.float64
        )
        if delta.ndim != 2 or len(delta) == 0:
            self.delta_mean = self.delta_var = None
            return
        self.delta_mean = delta.mean(axis=0)
        self.delta_var = delta.var(axis=0) + 1e-6

    def predict(self, parent: Any) -> tuple[np.ndarray, np.ndarray]:
        p = np.asarray(parent, dtype=np.float64)
        if self.delta_mean is None:
            return p.copy(), np.ones_like(p)
        assert self.delta_var is not None
        return p + self.delta_mean, self.delta_var.copy()


class ActionTransitionEnsemble:
    """One diagonal-Gaussian child-latent model per operator/action."""

    def __init__(self):
        self.models: dict[str, DiagonalTransitionModel] = {}

    def fit_action(
        self,
        action: str,
        parents: Any,
        children: Any,
    ) -> None:
        model = DiagonalTransitionModel()
        model.fit(parents, children)
        self.models[action] = model

    def predict(
        self,
        action: str,
        parent: Any,
    ) -> tuple[np.ndarray, np.ndarray]:
        if action not in self.models:
            vector = np.asarray(parent, dtype=np.float64)
            return vector.copy(), np.ones_like(vector)
        return self.models[action].predict(parent)


@dataclass(frozen=True)
class DGSObservation:
    candidate_hash: str
    source: str
    utility: float
    fidelity: str
    operator: str
    parent_hash: str | None = None
    instance_scores: Mapping[str, float] = field(default_factory=dict)


class QDSelector:
    """Full-refresh DGS action selector targeting predicted 60-second utility."""

    def __init__(
        self,
        instance_features: Sequence[float] | Mapping[str, Sequence[float]],
        *,
        seed: int = 0,
    ):
        if isinstance(instance_features, Mapping):
            self.instance_features = {
                str(instance_id): np.asarray(features, dtype=np.float32)
                for instance_id, features in instance_features.items()
            }
        else:
            self.instance_features = {
                "__aggregate__": np.asarray(instance_features, dtype=np.float32)
            }
        self.instance_residuals: dict[str, np.ndarray] = {}
        self.embedder = CodeEmbedder()
        self.projector = ResidualCodeProjector(seed=seed)
        self.utility = BootstrappedUtilityEnsemble(seed=seed)
        self.transitions = ActionTransitionEnsemble()
        self.observations: list[DGSObservation] = []
        self.latents: dict[str, np.ndarray] = {}

    def _latent(self, candidate_hash: str, source: str) -> np.ndarray:
        if candidate_hash not in self.latents:
            embedding = self.embedder.embed(candidate_hash, source)
            self.latents[candidate_hash] = self.projector.transform(embedding)
        return self.latents[candidate_hash]

    def observe(self, observation: DGSObservation) -> None:
        self._latent(observation.candidate_hash, observation.source)
        self.observations.append(observation)

    def novelty(
        self, candidate_hash: str, source: str, *, neighbours: int = 5
    ) -> float:
        candidate = self._latent(candidate_hash, source)
        distances = sorted(
            float(np.linalg.norm(candidate - latent))
            for other_hash, latent in self.latents.items()
            if other_hash != candidate_hash
        )
        return float(np.mean(distances[:neighbours])) if distances else 1.0

    def state_dict(self) -> dict[str, Any]:
        return {
            "projector_residual": self.projector.residual.tolist(),
            "utility_weights": [weight.tolist() for weight in self.utility.weights],
            "instance_residuals": {
                instance_id: residual.tolist()
                for instance_id, residual in self.instance_residuals.items()
            },
            "transitions": {
                action: {
                    "delta_mean": (
                        model.delta_mean.tolist()
                        if model.delta_mean is not None
                        else None
                    ),
                    "delta_var": (
                        model.delta_var.tolist()
                        if model.delta_var is not None
                        else None
                    ),
                }
                for action, model in self.transitions.models.items()
            },
        }

    def load_state_dict(self, state: Mapping[str, Any]) -> None:
        self.projector.residual = np.asarray(
            state.get("projector_residual", self.projector.residual),
            dtype=np.float64,
        )
        self.utility.weights = [
            np.asarray(weight, dtype=np.float64)
            for weight in state.get("utility_weights", [])
        ]
        self.instance_residuals = {
            instance_id: np.asarray(residual, dtype=np.float32)
            for instance_id, residual in state.get("instance_residuals", {}).items()
        }
        self.transitions.models = {}
        for action, values in state.get("transitions", {}).items():
            model = DiagonalTransitionModel()
            if values.get("delta_mean") is not None:
                model.delta_mean = np.asarray(values["delta_mean"], dtype=np.float64)
            if values.get("delta_var") is not None:
                model.delta_var = np.asarray(values["delta_var"], dtype=np.float64)
            self.transitions.models[action] = model
        self.latents.clear()
        for observation in self.observations:
            self._latent(observation.candidate_hash, observation.source)

    def refresh(self, max_observations: int | None = None) -> None:
        observations = (
            self.observations
            if max_observations is None
            else self.observations[:max_observations]
        )
        unique_sources = {
            observation.candidate_hash: observation.source
            for observation in observations
        }
        if unique_sources:
            hashes = sorted(unique_sources)
            embeddings = np.asarray(
                [
                    self.embedder.embed(candidate_hash, unique_sources[candidate_hash])
                    for candidate_hash in hashes
                ]
            )
            utility_by_hash: dict[str, list[float]] = {}
            for observation in observations:
                utility_by_hash.setdefault(observation.candidate_hash, []).append(
                    observation.utility
                )
            targets = embeddings @ self.projector.base
            targets[:, 0] += np.asarray(
                [np.mean(utility_by_hash[candidate_hash]) for candidate_hash in hashes]
            )
            self.projector.fit_residual(embeddings, targets)
            self.latents.clear()
        rows, targets = [], []
        row_instances: list[str] = []
        drift: list[float] = []
        previous_target: dict[str, float] = {}
        transition_rows: dict[str, tuple[list[np.ndarray], list[np.ndarray]]] = {}
        score_history: dict[str, list[float]] = {}
        for observation in observations:
            for instance_id, score in observation.instance_scores.items():
                if instance_id in self.instance_features:
                    score_history.setdefault(instance_id, []).append(float(score))
        if score_history:
            global_mean = float(
                np.mean(
                    [score for scores in score_history.values() for score in scores]
                )
            )
            for instance_id, scores in score_history.items():
                residual = np.zeros_like(self.instance_features[instance_id])
                if residual.size:
                    residual[0] = float(np.mean(scores)) - global_mean
                self.instance_residuals[instance_id] = residual
        for observation in observations:
            child = self._latent(observation.candidate_hash, observation.source)
            scores = observation.instance_scores or {
                "__aggregate__": observation.utility
            }
            for instance_id, score in scores.items():
                features = self.instance_features.get(instance_id)
                if features is None:
                    continue
                rows.append(
                    utility_features(
                        child,
                        instance_embedding(
                            features, self.instance_residuals.get(instance_id)
                        ),
                        observation.fidelity,
                    )
                )
                targets.append(float(score))
                row_instances.append(instance_id)
                drift.append(
                    float(score) - previous_target.get(instance_id, float(score))
                )
                previous_target[instance_id] = float(score)
            if observation.parent_hash and observation.parent_hash in self.latents:
                parents, children = transition_rows.setdefault(
                    observation.operator, ([], [])
                )
                parents.append(self.latents[observation.parent_hash])
                children.append(child)
        # Rank is instance-local; drift compares each instance with its own
        # preceding trajectory observation.
        ranks = [0.0] * len(targets)
        indices_by_instance: dict[str, list[int]] = {}
        for index, instance_id in enumerate(row_instances):
            indices_by_instance.setdefault(instance_id, []).append(index)
        for indices in indices_by_instance.values():
            ordered = sorted(indices, key=lambda index: (targets[index], index))
            denominator = max(1, len(ordered) - 1)
            for rank, index in enumerate(ordered):
                ranks[index] = rank / denominator
        self.utility.fit(rows, targets, ranks, drift)
        for action, (parents, children) in transition_rows.items():
            self.transitions.fit_action(action, parents, children)

    def select(
        self,
        operators: Sequence[Any],
        parent_entries: Sequence[Any],
    ) -> tuple[Any, Any] | None:
        if not self.observations or not parent_entries:
            return None
        best: tuple[float, str, str, Any, Any] | None = None
        for operator in operators:
            if getattr(operator, "name", "") == "repair_invalid":
                continue
            for parent in parent_entries:
                latent = self.latents.get(parent.candidate_hash)
                if latent is None:
                    continue
                child_mean, child_variance = self.transitions.predict(
                    operator.name, latent
                )
                predictions = [
                    self.utility.predict(
                        utility_features(
                            child_mean,
                            instance_embedding(
                                features, self.instance_residuals.get(instance_id)
                            ),
                            "60s",
                        )
                    )
                    for instance_id, features in self.instance_features.items()
                ]
                prediction = Prediction(
                    float(np.mean([item.mean for item in predictions])),
                    float(
                        np.mean([item.uncertainty for item in predictions])
                        if predictions
                        else 1.0
                    ),
                )
                value = acquisition(
                    prediction,
                    child_variance,
                    float(parent.novelty),
                    1.0 / (1.0 + float(parent.children)),
                )
                key = (value, operator.name, parent.candidate_hash, operator, parent)
                if best is None or key[:3] > best[:3]:
                    best = key
        return (best[3], best[4]) if best else None

    def complete_parents(
        self,
        operator: Any,
        first_parent: Any,
        parent_entries: Sequence[Any],
    ) -> list[Any]:
        """Choose every required parent; recombination favors latent diversity."""
        if int(getattr(operator, "arity", 1)) <= 1:
            return [first_parent]
        first_latent = self.latents.get(first_parent.candidate_hash)
        alternatives = [
            entry
            for entry in parent_entries
            if entry.candidate_hash != first_parent.candidate_hash
        ]
        if not alternatives:
            return [first_parent]
        second = max(
            alternatives,
            key=lambda entry: (
                float(np.linalg.norm(first_latent - self.latents[entry.candidate_hash]))
                if first_latent is not None and entry.candidate_hash in self.latents
                else 0.0,
                float(entry.quality),
                entry.candidate_hash,
            ),
        )
        return [first_parent, second]


def acquisition(
    utility: Prediction,
    transition_variance: Iterable[float],
    novelty: float,
    coverage_value: float,
    *,
    beta_utility: float = 0.5,
    beta_transition: float = 0.1,
) -> float:
    transition_uncertainty = math.sqrt(sum(float(v) for v in transition_variance))
    return (
        utility.mean
        + beta_utility * utility.uncertainty
        + beta_transition * transition_uncertainty
        + 0.15 * novelty
        + 0.15 * coverage_value
    )
