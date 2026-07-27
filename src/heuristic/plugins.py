"""Manifest-first trusted problem plugin discovery."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from .contracts import ProblemAdapter, ProblemManifestV1


@dataclass(frozen=True)
class LoadedProblem:
    root: Path
    manifest: ProblemManifestV1
    adapter: ProblemAdapter


def load_problem(name: str, problems_root: str | Path | None = None) -> LoadedProblem:
    problems_root = Path(
        problems_root or Path(__file__).resolve().parents[2] / "problems"
    ).resolve()
    root = (problems_root / name).resolve()
    if root.parent != problems_root or not root.is_dir():
        raise ValueError(f"unknown heuristic problem: {name}")
    manifest_path = root / "problem.yaml"
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest = ProblemManifestV1.from_dict(raw)
    adapter_path = (root / manifest.adapter).resolve()
    if adapter_path.parent != root or not adapter_path.is_file():
        raise ValueError(
            "adapter path must name a file directly inside the problem plugin"
        )
    module_name = f"_solvita_problem_{manifest.problem_id}_{manifest.version}".replace(
        "-", "_"
    )
    spec = importlib.util.spec_from_file_location(module_name, adapter_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load problem adapter: {adapter_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    adapter_class = getattr(module, "Adapter", None)
    if adapter_class is None:
        candidates = [
            value
            for value in vars(module).values()
            if isinstance(value, type) and value.__name__.endswith("Adapter")
        ]
        if len(candidates) != 1:
            raise TypeError("adapter.py must expose Adapter or one *Adapter class")
        adapter_class = candidates[0]
    adapter = adapter_class()
    if not isinstance(adapter, ProblemAdapter):
        raise TypeError(f"{adapter_class.__name__} does not satisfy ProblemAdapter")
    if adapter.problem_id != manifest.problem_id:
        raise ValueError("adapter problem_id does not match manifest")
    return LoadedProblem(root, manifest, adapter)
