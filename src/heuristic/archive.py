"""Deterministic quality-diversity archive and 7/6/5/2 parent quotas."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class ArchiveEntry:
    candidate_hash: str
    quality: float
    novelty: float = 0.0
    cluster: str = "global"
    valid: bool = True
    lineage: str = "root"
    instance_scores: Mapping[str, float] = field(default_factory=dict)
    proposals_since_selected: int = 0
    children: int = 0


class QDArchive:
    """Problem-local archive.

    Invalid candidates are retained in ``repair_lane`` but can never enter the
    quality archive or its parent quotas.
    """

    QUOTAS = (("quality", 7), ("novelty", 6), ("specialist", 5), ("revival", 2))

    def __init__(self, capacity: int = 200, repair_capacity: int = 8):
        self.capacity = capacity
        self.repair_capacity = repair_capacity
        self._entries: dict[str, ArchiveEntry] = {}
        self.repair_lane: list[ArchiveEntry] = []

    def add(self, entry: ArchiveEntry) -> bool:
        if not entry.valid:
            self.repair_lane = (
                [entry]
                + [
                    item
                    for item in self.repair_lane
                    if item.candidate_hash != entry.candidate_hash
                ]
            )[: self.repair_capacity]
            return False
        old = self._entries.get(entry.candidate_hash)
        if old is not None and old.quality >= entry.quality:
            return False
        self._entries[entry.candidate_hash] = entry
        self._trim()
        return True

    def _trim(self) -> None:
        if len(self._entries) <= self.capacity:
            return
        ranked = sorted(
            self._entries.values(),
            key=lambda x: (-x.quality, -x.novelty, x.candidate_hash),
        )
        self._entries = {x.candidate_hash: x for x in ranked[: self.capacity]}

    def entries(self) -> list[ArchiveEntry]:
        return sorted(
            self._entries.values(),
            key=lambda x: (-x.quality, -x.novelty, x.candidate_hash),
        )

    def replace_scores(
        self, scores: Mapping[str, tuple[float, Mapping[str, float]]]
    ) -> None:
        """Atomically replace derived quality values after a BKS epoch changes."""
        replaced: dict[str, ArchiveEntry] = {}
        for candidate_hash, entry in self._entries.items():
            quality, instance_scores = scores.get(
                candidate_hash, (entry.quality, entry.instance_scores)
            )
            replaced[candidate_hash] = ArchiveEntry(
                candidate_hash=entry.candidate_hash,
                quality=quality,
                novelty=entry.novelty,
                cluster=entry.cluster,
                valid=entry.valid,
                lineage=entry.lineage,
                instance_scores=instance_scores,
                proposals_since_selected=entry.proposals_since_selected,
                children=entry.children,
            )
        self._entries = replaced

    def mark_selected(self, candidate_hashes: set[str]) -> None:
        """Advance deterministic revival counters after a parent selection."""
        self._entries = {
            candidate_hash: ArchiveEntry(
                candidate_hash=entry.candidate_hash,
                quality=entry.quality,
                novelty=entry.novelty,
                cluster=entry.cluster,
                valid=entry.valid,
                lineage=entry.lineage,
                instance_scores=entry.instance_scores,
                proposals_since_selected=(
                    0
                    if candidate_hash in candidate_hashes
                    else entry.proposals_since_selected + 1
                ),
                children=entry.children
                + (1 if candidate_hash in candidate_hashes else 0),
            )
            for candidate_hash, entry in self._entries.items()
        }

    @staticmethod
    def _specialist_score(entry: ArchiveEntry) -> float:
        if not entry.instance_scores:
            return entry.quality
        values = list(entry.instance_scores.values())
        return max(values) - sum(values) / len(values)

    def parent_pool_with_roles(self) -> list[tuple[str, ArchiveEntry]]:
        """Select up to 20 unique candidates using deterministic 7/6/5/2 quotas.

        When a category has too few unique candidates, its unused slots are
        filled by global quality after all category passes.
        """
        entries = self.entries()
        rankings = {
            "quality": entries,
            "novelty": sorted(
                entries, key=lambda x: (-x.novelty, -x.quality, x.candidate_hash)
            ),
            "specialist": sorted(
                entries,
                key=lambda x: (
                    -self._specialist_score(x),
                    -x.quality,
                    x.candidate_hash,
                ),
            ),
            "revival": sorted(
                entries,
                key=lambda x: (
                    -x.proposals_since_selected,
                    x.children,
                    -x.novelty,
                    x.candidate_hash,
                ),
            ),
        }
        selected: list[tuple[str, ArchiveEntry]] = []
        used: set[str] = set()
        for role, quota in self.QUOTAS:
            added = 0
            specialist_clusters: set[str] = set()
            for entry in rankings[role]:
                if entry.candidate_hash in used:
                    continue
                if role == "specialist" and entry.cluster in specialist_clusters:
                    continue
                selected.append((role, entry))
                used.add(entry.candidate_hash)
                specialist_clusters.add(entry.cluster)
                added += 1
                if added == quota:
                    break
            if role == "specialist" and added < quota:
                for entry in rankings[role]:
                    if entry.candidate_hash in used:
                        continue
                    selected.append((role, entry))
                    used.add(entry.candidate_hash)
                    added += 1
                    if added == quota:
                        break
        for entry in entries:
            if len(selected) >= 20:
                break
            if entry.candidate_hash not in used:
                selected.append(("quality_fill", entry))
                used.add(entry.candidate_hash)
        return selected

    def parent_pool(self) -> list[ArchiveEntry]:
        return [entry for _, entry in self.parent_pool_with_roles()]

    def to_dict(self) -> dict:
        return {
            "capacity": self.capacity,
            "repair_capacity": self.repair_capacity,
            "entries": [asdict(e) for e in self.entries()],
            "repair_lane": [asdict(e) for e in self.repair_lane],
        }

    @classmethod
    def from_dict(cls, data: Mapping) -> "QDArchive":
        archive = cls(
            int(data.get("capacity", 200)), int(data.get("repair_capacity", 8))
        )
        for raw in data.get("entries", []):
            archive._entries[raw["candidate_hash"]] = ArchiveEntry(**raw)
        archive.repair_lane = [
            ArchiveEntry(**raw) for raw in data.get("repair_lane", [])
        ]
        return archive
