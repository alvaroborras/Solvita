import json
import shutil
from dataclasses import replace

import pytest

from src.heuristic.bundle import CandidateBundleV1
from src.heuristic.contracts import Fidelity, ResourceLimits
from src.heuristic.evaluator import DockerEvaluator, DockerUnavailable
from src.heuristic.plugins import load_problem
from src.heuristic.storage import ArtifactStore, HeuristicStore


def _evaluator(tmp_path):
    problem = load_problem("ogc")
    limits = ResourceLimits(
        time_limit_ms=100,
        memory_mb=256,
        output_bytes=1024,
        pids=16,
    )
    manifest = replace(
        problem.manifest,
        search_limits=limits,
        final_limits=limits,
    )
    artifacts = ArtifactStore(tmp_path / "artifacts")
    evaluator = DockerEvaluator(
        manifest,
        problem.adapter,
        sdk_dir=problem.root / "sdk",
        cache_dir=tmp_path / "compile",
        artifacts=artifacts,
        store=HeuristicStore(tmp_path / "heuristic.sqlite3"),
    )
    try:
        evaluator.preflight()
    except DockerUnavailable:
        pytest.skip("pinned heuristic Docker image unavailable")
    return problem, evaluator, artifacts


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker unavailable")
@pytest.mark.parametrize(
    ("source", "failure"),
    [
        ('#error "nope"\n', "compile"),
        ("int main(){return 7;}\n", "runtime"),
        (
            '#include <iostream>\nint main(){std::cout << "not-json";}\n',
            "invalid_output",
        ),
        ('#include <iostream>\nint main(){std::cout << "{}";}\n', "infeasible"),
        (
            "#include <iostream>\n"
            "int main(){for(int i=0;i<5000;++i)std::cout << 'x';}\n",
            "output_limit",
        ),
        ("int main(){for(;;){} }\n", "timeout"),
    ],
)
def test_docker_evaluator_classifies_hard_failures(tmp_path, source, failure):
    _, evaluator, _ = _evaluator(tmp_path)
    record = evaluator.evaluate(
        CandidateBundleV1({"main.cpp": source}),
        "prob_1",
        Fidelity.SEARCH,
        0,
    )
    assert not record.feasible
    assert record.failure is not None
    assert record.failure.startswith(failure)


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker unavailable")
def test_candidate_cannot_reach_network_or_trusted_host_paths(tmp_path):
    _, evaluator, artifacts = _evaluator(tmp_path)
    source = r"""
#include <arpa/inet.h>
#include <fstream>
#include <iostream>
#include <sys/socket.h>
#include <unistd.h>
int main() {
  int fd = socket(AF_INET, SOCK_STREAM, 0);
  sockaddr_in addr{};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(53);
  inet_pton(AF_INET, "1.1.1.1", &addr.sin_addr);
  bool connected = fd >= 0 && connect(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) == 0;
  if (fd >= 0) close(fd);
  std::ifstream scorer("/sdk/solvita_ogc.hpp");
  std::ifstream validation("/validation/prob_21.json");
  std::cout << "{\"connected\":" << (connected ? "true" : "false")
            << ",\"scorer_visible\":" << (scorer.good() ? "true" : "false")
            << ",\"validation_visible\":" << (validation.good() ? "true" : "false")
            << "}";
}
"""
    record = evaluator.evaluate(
        CandidateBundleV1({"main.cpp": source}),
        "prob_1",
        Fidelity.SEARCH,
        0,
    )
    assert record.failure == "infeasible"
    assert record.output_artifact is not None
    observed = json.loads(
        artifacts.read_bytes(record.output_artifact, ".stdout").decode()
    )
    assert observed == {
        "connected": False,
        "scorer_visible": False,
        "validation_visible": False,
    }


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker unavailable")
def test_whitelisted_header_and_source_bundle_compiles(tmp_path):
    _, evaluator, _ = _evaluator(tmp_path)
    bundle = CandidateBundleV1(
        {
            "main.cpp": (
                '#include "answer.hpp"\n'
                "#include <iostream>\n"
                "int main(){std::cout << answer();}\n"
            ),
            "include/answer.hpp": "#pragma once\nconst char* answer();\n",
            "src/answer.cpp": (
                '#include "answer.hpp"\nconst char* answer(){return "{}";}\n'
            ),
        }
    )
    record = evaluator.evaluate(bundle, "prob_1", Fidelity.SEARCH, 0)
    assert record.failure == "infeasible"
