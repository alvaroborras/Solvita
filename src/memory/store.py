"""SQLite-backed persistence layer for memory items and events."""

import json
import logging
import sqlite3
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from contextlib import contextmanager

from src.memory.types import MemoryItem, MemoryEvent, MemoryNamespace

logger = logging.getLogger(__name__)


class MemoryStore:
    """
    SQLite-backed memory store with transactions and indexing.
    
    Database layout per namespace:
    - items table: id (PK), namespace, text, payload_json, tags_json, uses, avg_reward, deprecated, created_at, last_used
    - events table: id (auto PK), timestamp, namespace, observation_json, selected_item_ids_json, reward, problem_hash, iteration
    """

    def __init__(self, namespace: MemoryNamespace, data_dir: Path):
        self.namespace = namespace
        self.data_dir = data_dir / namespace.value
        self.db_path = self.data_dir / "memory.db"
        
        self.items: Dict[str, MemoryItem] = {}
        self.initialized = False
        self._conn: Optional[sqlite3.Connection] = None

    @contextmanager
    def _get_conn(self):
        """Context manager for database connections."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0)
            self._conn.row_factory = sqlite3.Row
        try:
            yield self._conn
        except Exception:
            self._conn.rollback()
            raise
        else:
            self._conn.commit()

    def initialize(self):
        """Create directories, tables, and load existing items."""
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created memory store directory: {self.data_dir}")
        
        self._create_tables()
        self._load_items()
        
        # Auto-migrate from jsonl if SQLite is empty but jsonl exists
        if not self.items:
            self._try_migrate_from_jsonl()
        
        self.initialized = True

    def _create_tables(self):
        """Create items and events tables with indexes."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY,
                    namespace TEXT NOT NULL,
                    text TEXT NOT NULL,
                    payload_json TEXT,
                    tags_json TEXT,
                    uses INTEGER DEFAULT 0,
                    avg_reward REAL DEFAULT 0.0,
                    deprecated INTEGER DEFAULT 0,
                    created_at TEXT,
                    last_used TEXT
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_items_namespace_deprecated 
                ON items(namespace, deprecated)
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    observation_json TEXT NOT NULL,
                    selected_item_ids_json TEXT NOT NULL,
                    reward REAL NOT NULL,
                    problem_hash TEXT,
                    iteration INTEGER DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
            """)

            event_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(events)").fetchall()
            }
            if "metadata_json" not in event_columns:
                conn.execute(
                    "ALTER TABLE events ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'"
                )
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_namespace_timestamp 
                ON events(namespace, timestamp)
            """)
            
            logger.debug(f"Tables initialized for namespace {self.namespace.value}")

    def _load_items(self):
        """Load items from SQLite database into memory."""
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(
                    "SELECT * FROM items WHERE namespace = ?",
                    (self.namespace.value,)
                )
                rows = cursor.fetchall()
                
                for row in rows:
                    item = MemoryItem(
                        id=row["id"],
                        namespace=MemoryNamespace(row["namespace"]),
                        text=row["text"],
                        payload=json.loads(row["payload_json"]) if row["payload_json"] else {},
                        tags=json.loads(row["tags_json"]) if row["tags_json"] else [],
                        uses=row["uses"],
                        avg_reward=row["avg_reward"],
                        deprecated=bool(row["deprecated"]),
                        created_at=row["created_at"],
                        last_used=row["last_used"],
                    )
                    self.items[item.id] = item
                
                logger.info(f"Loaded {len(self.items)} items from SQLite for {self.namespace.value}")
        except Exception as e:
            logger.error(f"Failed to load items from SQLite: {e}")

    def _try_migrate_from_jsonl(self):
        """One-time migration from existing jsonl files if they exist."""
        items_jsonl = self.data_dir / "items.jsonl"
        events_jsonl = self.data_dir / "events.jsonl"
        
        if not items_jsonl.exists():
            # No jsonl to migrate, do standard seeding
            self._seed_items()
            return
        
        logger.info(f"Migrating items from {items_jsonl} to SQLite...")
        
        try:
            # Migrate items
            with open(items_jsonl, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    item = MemoryItem.from_dict(data)
                    self.add_item(item)
            
            self.save_items()
            logger.info(f"Migrated {len(self.items)} items to SQLite")
            
            # Migrate events if present
            if events_jsonl.exists():
                with self._get_conn() as conn:
                    with open(events_jsonl, "r", encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            data = json.loads(line)
                            event = MemoryEvent.from_dict(data)
                            self._insert_event_db(conn, event)
                
                logger.info("Migrated events to SQLite")
            
            # Backup jsonl files
            items_jsonl.rename(items_jsonl.with_suffix(".jsonl.migrated"))
            if events_jsonl.exists():
                events_jsonl.rename(events_jsonl.with_suffix(".jsonl.migrated"))
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            # Fall back to seeding
            if not self.items:
                self._seed_items()

    def _seed_items(self):
        """Seed initial items based on namespace."""
        from src.memory.seeds import PLAN_SEED_ITEMS, SOLVE_SEED_ITEMS, HACK_SEED_ITEMS, ORACLE_SEED_ITEMS
        
        seed_map = {
            MemoryNamespace.PLAN: PLAN_SEED_ITEMS,
            MemoryNamespace.SOLVE: SOLVE_SEED_ITEMS,
            MemoryNamespace.HACK: HACK_SEED_ITEMS,
            MemoryNamespace.ORACLE: ORACLE_SEED_ITEMS,
        }
        
        seed_items = seed_map.get(self.namespace, [])
        
        for seed_data in seed_items:
            # Generate deterministic ID from text
            text = seed_data["text"]
            item_id = hashlib.md5(text.encode("utf-8")).hexdigest()[:16]
            
            item = MemoryItem(
                id=item_id,
                namespace=self.namespace,
                text=text,
                payload=seed_data.get("payload", {}),
                tags=seed_data.get("tags", []),
            )
            self.add_item(item)
        
        logger.info(f"Seeded {len(seed_items)} items for namespace {self.namespace.value}")
        
        # Save seeded items
        self.save_items()

    def add_item(self, item: MemoryItem):
        """Add or update an item."""
        if item.namespace != self.namespace:
            raise ValueError(f"Item namespace {item.namespace} does not match store namespace {self.namespace}")
        self.items[item.id] = item

    def save_items(self):
        """Persist all items to SQLite database."""
        try:
            with self._get_conn() as conn:
                for item in self.items.values():
                    conn.execute("""
                        INSERT OR REPLACE INTO items 
                        (id, namespace, text, payload_json, tags_json, uses, avg_reward, deprecated, created_at, last_used)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        item.id,
                        item.namespace.value,
                        item.text,
                        json.dumps(item.payload),
                        json.dumps(item.tags),
                        item.uses,
                        item.avg_reward,
                        int(item.deprecated),
                        item.created_at,
                        item.last_used,
                    ))
            
            logger.debug(f"Saved {len(self.items)} items to SQLite")
        except Exception as e:
            logger.error(f"Failed to save items to SQLite: {e}")

    def get_all_items(self) -> List[MemoryItem]:
        """Return all active (non-deprecated) items."""
        return [item for item in self.items.values() if not item.deprecated]

    def get_item(self, item_id: str) -> Optional[MemoryItem]:
        """Retrieve a specific item by ID."""
        return self.items.get(item_id)

    def update_item_stats(self, item_id: str, reward: float):
        """Update usage statistics for an item."""
        if item_id not in self.items:
            logger.warning(f"Item {item_id} not found in store")
            return
        
        item = self.items[item_id]
        n = item.uses
        item.avg_reward = (item.avg_reward * n + reward) / (n + 1)
        item.uses += 1
        item.last_used = datetime.now().isoformat()
        
        # Deprecate if consistently poor performance
        if n > 20 and item.avg_reward < -0.3:
            item.deprecated = True
            logger.info(f"Deprecating item {item_id} due to poor performance: {item.avg_reward:.2f}")

    def log_event(self, event: MemoryEvent):
        """Append an event to the event log in SQLite."""
        if event.namespace != self.namespace:
            raise ValueError(f"Event namespace {event.namespace} does not match store namespace {self.namespace}")
        
        try:
            with self._get_conn() as conn:
                self._insert_event_db(conn, event)
            logger.debug(f"Logged event: reward={event.reward:.2f}, items={len(event.selected_item_ids)}")
        except Exception as e:
            logger.error(f"Failed to log event to SQLite: {e}")

    def _insert_event_db(self, conn: sqlite3.Connection, event: MemoryEvent):
        """Insert event into database (helper for reuse in migration)."""
        conn.execute("""
            INSERT INTO events 
            (timestamp, namespace, observation_json, selected_item_ids_json, reward, problem_hash, iteration, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.timestamp,
            event.namespace.value,
            json.dumps({
                "fsm_state": event.observation.fsm_state,
                "failure_type": event.observation.failure_type,
                "attempt_count": event.observation.attempt_count,
                "canonical": event.observation.canonical,
                "feature_keys": event.observation.feature_keys,
                "raw_problem_desc": event.observation.raw_problem_desc,
            }),
            json.dumps(event.selected_item_ids),
            event.reward,
            event.problem_hash,
            event.iteration,
            json.dumps(event.metadata),
        ))

    def get_events(self, limit: Optional[int] = None) -> List[MemoryEvent]:
        """
        Read events from the log (for offline analysis).
        
        Args:
            limit: If provided, return only the last N events.
        """
        events = []
        try:
            with self._get_conn() as conn:
                if limit:
                    cursor = conn.execute(
                        "SELECT * FROM events WHERE namespace = ? ORDER BY id DESC LIMIT ?",
                        (self.namespace.value, limit)
                    )
                else:
                    cursor = conn.execute(
                        "SELECT * FROM events WHERE namespace = ? ORDER BY id",
                        (self.namespace.value,)
                    )
                
                rows = cursor.fetchall()
                
                for row in rows:
                    obs_data = json.loads(row["observation_json"])
                    from src.memory.types import Observation
                    
                    observation = Observation(
                        fsm_state=obs_data["fsm_state"],
                        failure_type=obs_data.get("failure_type"),
                        attempt_count=obs_data.get("attempt_count", 0),
                        canonical=obs_data.get("canonical", {}),
                        feature_keys=obs_data.get("feature_keys", []),
                        raw_problem_desc=obs_data.get("raw_problem_desc", ""),
                    )
                    
                    event = MemoryEvent(
                        timestamp=row["timestamp"],
                        namespace=MemoryNamespace(row["namespace"]),
                        observation=observation,
                        selected_item_ids=json.loads(row["selected_item_ids_json"]),
                        reward=row["reward"],
                        problem_hash=row["problem_hash"],
                        iteration=row["iteration"],
                        metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
                    )
                    events.append(event)
                
                logger.debug(f"Loaded {len(events)} events from SQLite")
                return events
        except Exception as e:
            logger.error(f"Failed to read events from SQLite: {e}")
            return []

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
