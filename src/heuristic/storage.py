"""Immutable artifacts and transactional WAL persistence for heuristic runs."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import EvaluationRecord


class ArtifactStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, data: bytes, suffix: str = "") -> str:
        digest = hashlib.sha256(data).hexdigest()
        path = self.path(digest, suffix)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".artifact-")
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return digest

    def put_json(self, value: Any) -> str:
        return self.put_bytes(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            ".json",
        )

    def path(self, digest: str, suffix: str = "") -> Path:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("artifact digest must be lowercase SHA-256")
        return self.root / digest[:2] / f"{digest[2:]}{suffix}"

    def read_bytes(self, digest: str, suffix: str = "") -> bytes:
        return self.path(digest, suffix).read_bytes()


class HeuristicStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs(
              run_id TEXT PRIMARY KEY, problem_id TEXT NOT NULL, engine TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, status TEXT NOT NULL,
              config TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events(
              id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
              proposal INTEGER, kind TEXT NOT NULL, event_key TEXT UNIQUE NOT NULL,
              payload TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS candidates(
              candidate_hash TEXT PRIMARY KEY, bundle_artifact TEXT NOT NULL,
              language_standard TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS evaluations(
              candidate_hash TEXT, problem_id TEXT, instance_id TEXT, fidelity TEXT,
              seed INTEGER, scorer_version TEXT NOT NULL, payload TEXT NOT NULL,
              PRIMARY KEY(candidate_hash, problem_id, instance_id, fidelity, seed, scorer_version)
            );
            CREATE TABLE IF NOT EXISTS transitions(
              run_id TEXT, proposal INTEGER, operator TEXT NOT NULL,
              parent_hashes TEXT NOT NULL, child_hash TEXT NOT NULL, payload TEXT NOT NULL,
              PRIMARY KEY(run_id, proposal)
            );
            CREATE TABLE IF NOT EXISTS bks_pending(
              run_id TEXT NOT NULL, problem_id TEXT, fidelity TEXT, instance_id TEXT,
              objective REAL NOT NULL,
              candidate_hash TEXT NOT NULL,
              PRIMARY KEY(run_id, problem_id, fidelity, instance_id, candidate_hash)
            );
            CREATE TABLE IF NOT EXISTS bks_snapshots(
              run_id TEXT NOT NULL, problem_id TEXT, fidelity TEXT, instance_id TEXT,
              objective REAL NOT NULL,
              candidate_hash TEXT NOT NULL, active_epoch INTEGER NOT NULL,
              PRIMARY KEY(run_id, problem_id, fidelity, instance_id, active_epoch)
            );
            CREATE TABLE IF NOT EXISTS checkpoints(
              run_id TEXT PRIMARY KEY, proposal INTEGER NOT NULL, payload TEXT NOT NULL
            );
            """
        )
        self._migrate_bks_tables()
        self.db.commit()

    def _migrate_bks_tables(self) -> None:
        """Upgrade older run-unscoped BKS tables without discarding evidence."""
        for table in ("bks_pending", "bks_snapshots"):
            columns = {
                row["name"]
                for row in self.db.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if "run_id" in columns:
                continue
            legacy = f"{table}_legacy"
            self.db.execute(f"ALTER TABLE {table} RENAME TO {legacy}")
            if table == "bks_pending":
                self.db.execute(
                    """CREATE TABLE bks_pending(
                       run_id TEXT NOT NULL, problem_id TEXT, fidelity TEXT,
                       instance_id TEXT, objective REAL NOT NULL,
                       candidate_hash TEXT NOT NULL,
                       PRIMARY KEY(run_id,problem_id,fidelity,instance_id,candidate_hash))"""
                )
                self.db.execute(
                    """INSERT INTO bks_pending
                       SELECT 'legacy-global', problem_id, fidelity, instance_id,
                              objective, candidate_hash FROM bks_pending_legacy"""
                )
            else:
                self.db.execute(
                    """CREATE TABLE bks_snapshots(
                       run_id TEXT NOT NULL, problem_id TEXT, fidelity TEXT,
                       instance_id TEXT, objective REAL NOT NULL,
                       candidate_hash TEXT NOT NULL, active_epoch INTEGER NOT NULL,
                       PRIMARY KEY(run_id,problem_id,fidelity,instance_id,active_epoch))"""
                )
                self.db.execute(
                    """INSERT INTO bks_snapshots
                       SELECT 'legacy-global', problem_id, fidelity, instance_id,
                              objective, candidate_hash, active_epoch
                       FROM bks_snapshots_legacy"""
                )
            self.db.execute(f"DROP TABLE {legacy}")

    @contextmanager
    def transaction(self):
        with self._lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                yield self.db
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

    def create_run(
        self, run_id: str, problem_id: str, engine: str, config: Mapping[str, Any]
    ) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO runs(run_id,problem_id,engine,status,config) VALUES(?,?,?,?,?)",
                (
                    run_id,
                    problem_id,
                    engine,
                    "running",
                    json.dumps(config, sort_keys=True),
                ),
            )

    def runs(self) -> list[dict[str, Any]]:
        return [
            {**dict(row), "config": json.loads(row["config"])}
            for row in self.db.execute(
                "SELECT * FROM runs ORDER BY created_at DESC"
            ).fetchall()
        ]

    def run(self, run_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return {**dict(row), "config": json.loads(row["config"])} if row else None

    def set_run_status(self, run_id: str, status: str) -> None:
        if status not in {"running", "completed", "failed", "stopped"}:
            raise ValueError(f"invalid run status: {status}")
        with self.transaction() as db:
            db.execute("UPDATE runs SET status=? WHERE run_id=?", (status, run_id))

    def append_event(
        self,
        kind: str,
        event_key: str,
        payload: Mapping[str, Any],
        *,
        run_id: str = "global",
        proposal: int | None = None,
    ) -> bool:
        with self.transaction() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO events(run_id,proposal,kind,event_key,payload) VALUES(?,?,?,?,?)",
                (
                    run_id,
                    proposal,
                    kind,
                    event_key,
                    json.dumps(payload, sort_keys=True),
                ),
            )
            return cursor.rowcount == 1

    def has_event(self, event_key: str) -> bool:
        with self._lock:
            return (
                self.db.execute(
                    "SELECT 1 FROM events WHERE event_key=?", (event_key,)
                ).fetchone()
                is not None
            )

    def event(self, event_key: str) -> dict[str, Any] | None:
        with self._lock:
            row = self.db.execute(
                "SELECT * FROM events WHERE event_key=?", (event_key,)
            ).fetchone()
        return (
            {**dict(row), "payload": json.loads(row["payload"])}
            if row is not None
            else None
        )

    def commit_epoch(
        self,
        *,
        run_id: str,
        epoch: int,
        proposal: int,
        payload: Mapping[str, Any],
        checkpoint: Mapping[str, Any],
    ) -> bool:
        """Atomically commit an epoch marker and its fully refreshed state."""
        event_key = f"{run_id}:epoch:{epoch}"
        with self.transaction() as db:
            if db.execute(
                "SELECT 1 FROM events WHERE event_key=?", (event_key,)
            ).fetchone():
                return False
            db.execute(
                """INSERT INTO events(run_id,proposal,kind,event_key,payload)
                   VALUES(?,?,?,?,?)""",
                (
                    run_id,
                    proposal,
                    "epoch_boundary",
                    event_key,
                    json.dumps(dict(payload), sort_keys=True),
                ),
            )
            db.execute(
                "INSERT OR REPLACE INTO checkpoints VALUES(?,?,?)",
                (run_id, proposal, json.dumps(dict(checkpoint), sort_keys=True)),
            )
            return True

    def save_candidate(
        self, candidate_hash: str, bundle_artifact: str, standard: str
    ) -> None:
        with self.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO candidates VALUES(?,?,?,CURRENT_TIMESTAMP)",
                (candidate_hash, bundle_artifact, standard),
            )

    def candidates(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.db.execute("SELECT * FROM candidates ORDER BY created_at")
        ]

    def candidate(self, candidate_hash: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM candidates WHERE candidate_hash=?", (candidate_hash,)
        ).fetchone()
        return dict(row) if row else None

    def _save_evaluation(
        self, db: sqlite3.Connection, record: EvaluationRecord
    ) -> bool:
        cursor = db.execute(
            "INSERT OR IGNORE INTO evaluations VALUES(?,?,?,?,?,?,?)",
            (
                record.candidate_hash,
                record.problem_id,
                record.instance_id,
                record.fidelity.value,
                record.seed,
                record.scorer_version,
                json.dumps(record.to_dict(), sort_keys=True),
            ),
        )
        return cursor.rowcount == 1

    def save_evaluation(self, record: EvaluationRecord) -> bool:
        with self.transaction() as db:
            return self._save_evaluation(db, record)

    def get_evaluation(
        self,
        candidate_hash: str,
        problem_id: str,
        instance_id: str,
        fidelity: str,
        seed: int,
        scorer_version: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            row = self.db.execute(
                """SELECT payload FROM evaluations WHERE candidate_hash=? AND problem_id=?
                   AND instance_id=? AND fidelity=? AND seed=? AND scorer_version=?""",
                (
                    candidate_hash,
                    problem_id,
                    instance_id,
                    fidelity,
                    seed,
                    scorer_version,
                ),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def commit_proposal(
        self,
        *,
        run_id: str,
        proposal: int,
        operator: str,
        parent_hashes: Iterable[str],
        child_hash: str,
        transition: Mapping[str, Any],
        evaluations: Iterable[EvaluationRecord],
        checkpoint: Mapping[str, Any],
        bks_updates: Iterable[tuple[str, str, str, str, float, str]] = (),
    ) -> bool:
        """Atomically commit every durable effect of one generated proposal."""
        event_key = f"{run_id}:proposal:{proposal}"
        with self.transaction() as db:
            if db.execute(
                "SELECT 1 FROM events WHERE event_key=?", (event_key,)
            ).fetchone():
                return False
            for record in evaluations:
                self._save_evaluation(db, record)
            for update in bks_updates:
                db.execute(
                    "INSERT OR REPLACE INTO bks_pending VALUES(?,?,?,?,?,?)",
                    update,
                )
            db.execute(
                "INSERT INTO transitions VALUES(?,?,?,?,?,?)",
                (
                    run_id,
                    proposal,
                    operator,
                    json.dumps(list(parent_hashes)),
                    child_hash,
                    json.dumps(dict(transition), sort_keys=True),
                ),
            )
            db.execute(
                "INSERT INTO events(run_id,proposal,kind,event_key,payload) VALUES(?,?,?,?,?)",
                (
                    run_id,
                    proposal,
                    "proposal_committed",
                    event_key,
                    json.dumps({"child_hash": child_hash}, sort_keys=True),
                ),
            )
            db.execute(
                "INSERT OR REPLACE INTO checkpoints VALUES(?,?,?)",
                (run_id, proposal, json.dumps(dict(checkpoint), sort_keys=True)),
            )
            return True

    def record_bks(
        self,
        problem_id: str,
        fidelity: str,
        instance_id: str,
        objective: float,
        candidate_hash: str,
        *,
        active_epoch: int | None = None,
        run_id: str = "global",
    ) -> None:
        with self.transaction() as db:
            db.execute(
                (
                    "INSERT OR REPLACE INTO bks_pending VALUES(?,?,?,?,?,?)"
                    if active_epoch is None
                    else "INSERT OR REPLACE INTO bks_snapshots VALUES(?,?,?,?,?,?,?)"
                ),
                (
                    (
                        run_id,
                        problem_id,
                        fidelity,
                        instance_id,
                        objective,
                        candidate_hash,
                    )
                    if active_epoch is None
                    else (
                        run_id,
                        problem_id,
                        fidelity,
                        instance_id,
                        objective,
                        candidate_hash,
                        active_epoch,
                    )
                ),
            )

    def activate_pending_bks(
        self,
        problem_id: str,
        fidelity: str,
        epoch: int,
        *,
        minimize: bool = True,
        run_id: str = "global",
    ) -> dict[str, float]:
        """Freeze the best observations known at an epoch into a new snapshot."""
        order = "MIN" if minimize else "MAX"
        rows = self.db.execute(
            f"""SELECT instance_id, {order}(objective) objective
                FROM bks_pending WHERE run_id=? AND problem_id=? AND fidelity=?
                GROUP BY instance_id""",
            (run_id, problem_id, fidelity),
        ).fetchall()
        with self.transaction() as db:
            for row in rows:
                source = db.execute(
                    "SELECT candidate_hash FROM bks_pending WHERE run_id=? AND problem_id=? AND fidelity=? AND instance_id=? AND objective=? LIMIT 1",
                    (
                        run_id,
                        problem_id,
                        fidelity,
                        row["instance_id"],
                        row["objective"],
                    ),
                ).fetchone()
                db.execute(
                    "INSERT OR REPLACE INTO bks_snapshots VALUES(?,?,?,?,?,?,?)",
                    (
                        run_id,
                        problem_id,
                        fidelity,
                        row["instance_id"],
                        row["objective"],
                        source["candidate_hash"],
                        epoch,
                    ),
                )
        return {row["instance_id"]: float(row["objective"]) for row in rows}

    def checkpoint(
        self, run_id: str, payload: Mapping[str, Any], proposal: int | None = None
    ) -> None:
        proposal = int(payload.get("proposals", 0) if proposal is None else proposal)
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO checkpoints VALUES(?,?,?)",
                (run_id, proposal, json.dumps(payload, sort_keys=True)),
            )

    def load_checkpoint(self, run_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT payload FROM checkpoints WHERE run_id=?", (run_id,)
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM events WHERE run_id=? ORDER BY id", (run_id,)
        ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def transitions(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM transitions WHERE run_id=? ORDER BY proposal", (run_id,)
        ).fetchall()
        return [
            {
                **dict(row),
                "parent_hashes": json.loads(row["parent_hashes"]),
                "payload": json.loads(row["payload"]),
            }
            for row in rows
        ]

    def evaluation_records(
        self, candidate_hashes: Iterable[str] | None = None
    ) -> list[dict[str, Any]]:
        if candidate_hashes is None:
            rows = self.db.execute("SELECT payload FROM evaluations").fetchall()
        else:
            hashes = list(candidate_hashes)
            if not hashes:
                return []
            placeholders = ",".join("?" for _ in hashes)
            rows = self.db.execute(
                f"SELECT payload FROM evaluations WHERE candidate_hash IN ({placeholders})",
                hashes,
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def bks_snapshot_records(
        self,
        problem_id: str | None = None,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM bks_snapshots"
        clauses: list[str] = []
        parameters: list[str] = []
        if problem_id is not None:
            clauses.append("problem_id=?")
            parameters.append(problem_id)
        if run_id is not None:
            clauses.append("run_id=?")
            parameters.append(run_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY fidelity, instance_id, active_epoch"
        return [
            dict(row) for row in self.db.execute(query, tuple(parameters)).fetchall()
        ]

    def bks_snapshot(
        self,
        *,
        run_id: str,
        problem_id: str,
        fidelity: str,
        epoch: int,
    ) -> dict[str, float]:
        rows = self.db.execute(
            """SELECT instance_id, objective FROM bks_snapshots
               WHERE run_id=? AND problem_id=? AND fidelity=? AND active_epoch=?""",
            (run_id, problem_id, fidelity, epoch),
        ).fetchall()
        return {str(row["instance_id"]): float(row["objective"]) for row in rows}

    def close(self) -> None:
        self.db.close()
