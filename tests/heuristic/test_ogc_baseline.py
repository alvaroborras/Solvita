import shutil
import subprocess
from pathlib import Path

import pytest

from OGC import ogc_eval
from problems.ogc.adapter import OGCAdapter


@pytest.mark.skipif(
    not (shutil.which("g++") or shutil.which("clang++")),
    reason="C++ compiler unavailable",
)
def test_ogc_baseline_feasible_on_all_instances(tmp_path):
    compiler = shutil.which("g++") or shutil.which("clang++")
    binary = tmp_path / "baseline"
    subprocess.run(
        [
            compiler,
            "-std=c++23",
            "-O2",
            "-I",
            "problems/ogc/sdk",
            "problems/ogc/baseline/main.cpp",
            "-o",
            str(binary),
        ],
        check=True,
    )
    adapter = OGCAdapter()
    first_solution = None
    for instance_id in adapter.discover_instances():
        process = subprocess.run(
            [str(binary)],
            input=adapter.instance_stdin(instance_id),
            capture_output=True,
            check=True,
        )
        result = adapter.validate(instance_id, adapter.parse_output(process.stdout))
        assert result["feasible"], (instance_id, result["violations"])
        if first_solution is None:
            first_solution = adapter.parse_output(process.stdout)

    ogc_eval.SOLVER_DIR = Path("OGC").resolve()
    problem = adapter.load_instance("prob_1")
    assert adapter.validate(
        "prob_1", first_solution
    ) == ogc_eval.official_check_feasibility(problem, first_solution)
