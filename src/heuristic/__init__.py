"""Additive heuristic-optimization subsystem.

The exact CP workflow intentionally does not import this package.  Heuristic
problems are discovered through a manifest and evaluated through trusted
problem adapters.
"""

from src.heuristic.bundle import CandidateBundleV1
from src.heuristic.contracts import EvaluationRecord, Fidelity, ProblemManifestV1

__all__ = ["ProblemManifestV1", "EvaluationRecord", "Fidelity", "CandidateBundleV1"]
