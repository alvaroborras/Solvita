import sys

from src.heuristic.evaluator import DockerEvaluator
from src.heuristic.plugins import load_problem


def test_runtime_command_exposes_only_binary_and_has_security_flags(tmp_path):
    problem = load_problem("ogc")
    evaluator = DockerEvaluator(problem.manifest, problem.adapter)
    command = evaluator.runtime_command(
        tmp_path / "candidate", problem.manifest.search_limits, seed=7
    )
    joined = " ".join(map(str, command))
    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "no-new-privileges" in command
    assert "--pids-limit" in command
    assert "--memory" in command
    assert f"{tmp_path / 'candidate'}:/candidate:ro" in command
    assert "utils.py" not in joined
    assert "split.json" not in joined
    assert "bks" not in joined.lower()
    assert "prob_" not in joined


def test_host_side_output_and_timeout_guards_are_streaming():
    _, stdout, failure = DockerEvaluator._run_limited(
        [sys.executable, "-c", "print('x' * 1000000)"],
        b"",
        timeout_seconds=2,
        output_bytes=1024,
    )
    assert failure == "output_limit"
    assert len(stdout) <= 1025

    _, _, failure = DockerEvaluator._run_limited(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        b"",
        timeout_seconds=0.05,
        output_bytes=1024,
    )
    assert failure == "timeout"
