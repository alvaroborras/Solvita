"""OGC adapter; all checker code remains trusted and outside candidate code."""

from __future__ import annotations
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
INSTANCE_ROOT = ROOT / "OGC" / "train"


class OGCAdapter:
    problem_id = "ogc"
    objective = "minimize"
    scorer_version = "ogc-official-utils-v1"

    def discover_instances(self) -> list[str]:
        return sorted(p.stem for p in INSTANCE_ROOT.glob("prob_*.json") if p.is_file())

    def load_instance(self, instance_id: str) -> dict[str, Any]:
        path = INSTANCE_ROOT / (
            instance_id if instance_id.endswith(".json") else f"{instance_id}.json"
        )
        if path.parent != INSTANCE_ROOT or not path.is_file():
            raise FileNotFoundError(instance_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def instance_stdin(self, instance_id: str) -> bytes:
        return (
            json.dumps(self.load_instance(instance_id), separators=(",", ":")) + "\n"
        ).encode()

    def features(self, instance_id: str) -> dict[str, float]:
        d = self.load_instance(instance_id)
        blocks = d.get("blocks", [])
        return {
            "bays": float(len(d.get("bays", []))),
            "blocks": float(len(blocks)),
            "workload": float(sum(float(b.get("workload", 0)) for b in blocks)),
            "horizon": float(max((b.get("due_date", 0) for b in blocks), default=0)),
        }

    def parse_output(self, stdout: bytes) -> Any:
        return json.loads(stdout.decode("utf-8"))

    def validate(self, instance_id: str, solution: Any) -> dict[str, Any]:
        path = ROOT / "OGC" / "utils.py"
        module_name = "_solvita_ogc_utils"
        if module_name in sys.modules:
            module = sys.modules[module_name]
            checker = getattr(module, "check_feasibility")
            return dict(checker(self.load_instance(instance_id), solution))
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load OGC checker")
        module = importlib.util.module_from_spec(spec)
        # dataclasses resolves postponed annotations through sys.modules while
        # the module body executes.
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        checker = getattr(module, "check_feasibility")
        return dict(checker(self.load_instance(instance_id), solution))

    def hash(self) -> str:
        h = hashlib.sha256()
        for p in sorted(INSTANCE_ROOT.glob("prob_*.json")):
            h.update(p.name.encode())
            h.update(p.read_bytes())
        trusted_files = [
            ROOT / "OGC" / "utils.py",
            Path(__file__),
            Path(__file__).with_name("problem.yaml"),
            Path(__file__).with_name("split.json"),
        ]
        trusted_files.extend(
            path
            for path in sorted(Path(__file__).with_name("sdk").rglob("*"))
            if path.is_file()
        )
        for path in trusted_files:
            h.update(path.relative_to(ROOT).as_posix().encode())
            h.update(path.read_bytes())
        return h.hexdigest()

    def split(self) -> tuple[list[str], list[str]]:
        raw = json.loads(
            Path(__file__).with_name("split.json").read_text(encoding="utf-8")
        )
        train = list(map(str, raw["train"]))
        validation = list(map(str, raw["validation"]))
        if sorted(train + validation) != self.discover_instances():
            raise ValueError("OGC split manifest does not cover the declared instances")
        if set(train) & set(validation):
            raise ValueError("OGC split manifest overlaps train and validation")
        return train, validation


Adapter = OGCAdapter
