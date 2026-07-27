import pytest

from src.heuristic.archive import ArchiveEntry, QDArchive
from src.heuristic.scoring import (
    bks_quality,
    robust_aggregate,
    standardized_raw_utilities,
    validation_gain,
    validation_lcb,
)


def test_scoring_contracts():
    assert bks_quality(80, 100, 50) == 0.4
    assert validation_gain(80, 100) == 0.2
    assert robust_aggregate([1, 2, 3, 4, 5]) == pytest.approx(2.4)
    utilities = standardized_raw_utilities([10, 5, 1])
    assert utilities[2] > utilities[1] > utilities[0]
    assert standardized_raw_utilities([5, 5]) == [0.125, 0.125]
    assert validation_lcb([0.1] * 8, bootstrap_samples=100) == 0.1


def test_archive_exact_quota_roles_and_repair_lane():
    archive = QDArchive()
    for index in range(30):
        archive.add(
            ArchiveEntry(
                f"{index:064x}",
                quality=float(index),
                novelty=float(30 - index),
                cluster=str(index % 5),
                lineage=str(index % 3),
                instance_scores={"a": float(index), "b": float(30 - index)},
                proposals_since_selected=index,
                children=index % 2,
            )
        )
    roles = [role for role, _ in archive.parent_pool_with_roles()]
    assert roles.count("quality") == 7
    assert roles.count("novelty") == 6
    assert roles.count("specialist") == 5
    assert roles.count("revival") == 2
    assert len(set(e.candidate_hash for _, e in archive.parent_pool_with_roles())) == 20
    invalid = ArchiveEntry("f" * 64, -3, valid=False)
    assert not archive.add(invalid)
    assert archive.repair_lane == [invalid]
