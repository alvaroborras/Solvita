from pathlib import Path

import pytest

from src.heuristic.bundle import CandidateBundleV1
from src.heuristic.plugins import load_problem


def test_bundle_is_canonical_and_hash_stable():
    left = CandidateBundleV1({"src/z.cpp": "// z", "main.cpp": "int main(){}"})
    right = CandidateBundleV1({"main.cpp": "int main(){}", "src/z.cpp": "// z"})
    assert left.canonical_json() == right.canonical_json()
    assert left.digest == right.digest
    assert CandidateBundleV1.from_json(left.canonical_json()) == left
    assert CandidateBundleV1({"main.cpp": "a\r\nb\r"}).files["main.cpp"] == "a\nb\n"
    with pytest.raises(ValueError, match="NUL"):
        CandidateBundleV1({"main.cpp": "a\x00b"})


@pytest.mark.parametrize(
    "path",
    [
        "../secret",
        "/etc/passwd",
        r"src\\evil.cpp",
        "src/../main.cpp",
        "Makefile",
        "src/Makefile",
        "include/blob.dat",
    ],
)
def test_bundle_rejects_path_attacks(path):
    with pytest.raises(ValueError):
        CandidateBundleV1({"main.cpp": "ok", path: "bad"})


def test_bundle_directory_rejects_symlink(tmp_path: Path):
    (tmp_path / "main.cpp").write_text("int main(){}", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "link.cpp").symlink_to(tmp_path / "main.cpp")
    with pytest.raises(ValueError, match="symlink"):
        CandidateBundleV1.from_directory(tmp_path)


def test_ogc_plugin_contract_and_split():
    problem = load_problem("ogc")
    train, validation = problem.adapter.split()
    assert problem.manifest.default_standard == "c++23"
    assert len(train) == 32
    assert len(validation) == 8
    assert not set(train) & set(validation)
    assert sorted(train + validation) == problem.adapter.discover_instances()
