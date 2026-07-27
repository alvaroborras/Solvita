"""Separate cross-problem strategy-card memory with observational evidence."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class StrategyCard:
    card_id: str
    mechanism: str
    preconditions: tuple[str, ...] = ()
    adaptation_recipe: tuple[str, ...] = ()
    operators: tuple[str, ...] = ()
    complexity: str = ""
    failure_modes: tuple[str, ...] = ()
    interactions: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
    provenance: str = ""
    scope: str = "incubator"
    owner_problem: str = ""


class StrategyStore:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS cards(card_id TEXT PRIMARY KEY, payload TEXT NOT NULL, scope TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evidence(
              id INTEGER PRIMARY KEY, card_id TEXT NOT NULL, problem_id TEXT NOT NULL,
              problem_family TEXT NOT NULL, delta REAL NOT NULL, descendant_delta REAL,
              positive INTEGER NOT NULL, causal INTEGER NOT NULL DEFAULT 0, context TEXT NOT NULL
            );
            """
        )
        self.db.commit()

    def put(self, card: StrategyCard) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO cards VALUES(?,?,?)",
            (card.card_id, json.dumps(asdict(card), sort_keys=True), card.scope),
        )
        self.db.commit()

    def add_evidence(
        self,
        card_id: str,
        problem_id: str,
        problem_family: str,
        delta: float,
        *,
        descendant_delta: float | None = None,
        context: dict | None = None,
    ) -> None:
        self.db.execute(
            """INSERT INTO evidence(card_id,problem_id,problem_family,delta,descendant_delta,
               positive,causal,context) VALUES(?,?,?,?,?,?,0,?)""",
            (
                card_id,
                problem_id,
                problem_family,
                delta,
                descendant_delta,
                int(delta > 0),
                json.dumps(context or {}, sort_keys=True),
            ),
        )
        self.db.commit()

    def promote_eligible(self) -> list[str]:
        rows = self.db.execute(
            """SELECT card_id FROM evidence WHERE positive=1 GROUP BY card_id
               HAVING COUNT(DISTINCT problem_family) >= 2"""
        ).fetchall()
        ids = [row["card_id"] for row in rows]
        self.db.executemany(
            "UPDATE cards SET scope='global' WHERE card_id=?", [(x,) for x in ids]
        )
        self.db.commit()
        return ids

    def approve_global(self, card_id: str, *, approved_by: str) -> None:
        """Explicit human override for cross-family evidence requirements."""
        cursor = self.db.execute(
            "UPDATE cards SET scope='global' WHERE card_id=?", (card_id,)
        )
        if cursor.rowcount != 1:
            raise KeyError(card_id)
        self.db.execute(
            """INSERT INTO evidence(card_id,problem_id,problem_family,delta,
               descendant_delta,positive,causal,context)
               VALUES(?, 'human', 'human-approval', 0, NULL, 1, 0, ?)""",
            (card_id, json.dumps({"approved_by": approved_by}, sort_keys=True)),
        )
        self.db.commit()

    def retrieve(
        self,
        *,
        domain: str | None = None,
        include_incubator: bool = False,
        problem_id: str | None = None,
    ) -> list[StrategyCard]:
        rows = self.db.execute(
            "SELECT payload, scope FROM cards"
            + ("" if include_incubator else " WHERE scope='global'")
        ).fetchall()
        cards = []
        for row in rows:
            payload = json.loads(row["payload"])
            payload["scope"] = row["scope"]
            card = StrategyCard(**payload)
            if (
                card.scope != "global"
                and problem_id is not None
                and card.owner_problem not in {"", problem_id}
            ):
                continue
            if domain is None or domain in card.domains:
                cards.append(card)
        return cards

    def evidence(self, card_id: str | None = None) -> list[dict]:
        query = "SELECT * FROM evidence"
        parameters: tuple[str, ...] = ()
        if card_id is not None:
            query += " WHERE card_id=?"
            parameters = (card_id,)
        query += " ORDER BY id"
        return [
            {**dict(row), "context": json.loads(row["context"])}
            for row in self.db.execute(query, parameters).fetchall()
        ]

    def close(self) -> None:
        self.db.close()
