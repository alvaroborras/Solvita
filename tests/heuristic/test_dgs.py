import numpy as np

from src.heuristic.archive import ArchiveEntry
from src.heuristic.dgs import (
    BootstrappedUtilityEnsemble,
    DGSObservation,
    DiagonalTransitionModel,
    QDSelector,
    acquisition,
    instance_embedding,
)
from src.heuristic.operators import OPERATORS


def test_surrogates_and_acquisition():
    model = BootstrappedUtilityEnsemble(seed=1)
    model.fit([[0], [1], [2], [3]], [0, 1, 2, 3])
    assert model.predict([3]).mean > model.predict([0]).mean
    transition = DiagonalTransitionModel()
    transition.fit([[0, 0], [1, 1]], [[1, 2], [2, 3]])
    mean, variance = transition.predict([4, 4])
    assert np.allclose(mean, [5, 6])
    assert np.all(variance > 0)
    assert acquisition(model.predict([2]), variance, 1, 1) > model.predict([2]).mean


def test_unseen_instance_has_feature_only_embedding():
    assert np.array_equal(
        instance_embedding([1, 2]), np.array([1, 2], dtype=np.float32)
    )


def test_qd_selector_targets_guided_action():
    selector = QDSelector([1, 2, 3, 4], seed=0)
    selector.embedder._model = False
    first = "a" * 64
    second = "b" * 64
    selector.observe(DGSObservation(first, "alpha code", 0.0, "10s", "new_paradigm"))
    selector.observe(
        DGSObservation(
            second, "beta improved code", 1.0, "60s", "tune_parameters", first
        )
    )
    entries = [
        ArchiveEntry(first, 0.0, novelty=1.0),
        ArchiveEntry(second, 1.0, novelty=0.5),
    ]
    action = selector.select(OPERATORS, entries)
    assert action is not None
    assert action[1] in entries


def test_qd_selector_trains_instance_conditioned_rows_and_residuals():
    selector = QDSelector({"easy": [0.0, 1.0], "hard": [1.0, 0.0]}, seed=3)
    selector.embedder._model = False
    selector.observe(
        DGSObservation(
            "c" * 64,
            "candidate code",
            0.0,
            "10s",
            "new_paradigm",
            instance_scores={"easy": 1.0, "hard": -1.0},
        )
    )
    selector.refresh()
    assert set(selector.instance_residuals) == {"easy", "hard"}
    assert selector.instance_residuals["easy"][0] > 0
    assert selector.instance_residuals["hard"][0] < 0
    assert len(selector.utility.weights) == 5

    restored = QDSelector({"easy": [0.0, 1.0], "hard": [1.0, 0.0]}, seed=3)
    restored.embedder._model = False
    for observation in selector.observations:
        restored.observe(observation)
    restored.load_state_dict(selector.state_dict())
    assert len(restored.utility.weights) == 5
    assert np.allclose(restored.projector.residual, selector.projector.residual)
