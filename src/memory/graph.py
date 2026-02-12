"""Memory Graph Management.

Handles storage and retrieval of strategies and their relationships.
"""

import json
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Set

from src.memory.types import Strategy, StrategyType, Observation
from src.memory.seed_strategies import SEED_STRATEGIES

logger = logging.getLogger(__name__)


class MemoryGraph:
    """
    The persistent graph storage for memories.
    """
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.strategies_path = data_dir / "strategies.jsonl"
        
        self.strategies: Dict[str, Strategy] = {}
        self.initialized = False
        
    def initialize(self):
        """Load or create the memory graph."""
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
            
        self._load_strategies()
        self.initialized = True
        
    def _load_strategies(self):
        """Load strategies from disk. If empty, seed them."""
        if self.strategies_path.exists():
            try:
                with open(self.strategies_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        data = json.loads(line)
                        strat = Strategy.from_dict(data)
                        self.strategies[strat.id] = strat
                logger.info(f"Loaded {len(self.strategies)} strategies from {self.strategies_path}")
            except Exception as e:
                logger.error(f"Failed to load strategies: {e}")
        
        # Cold start check
        if not self.strategies:
            logger.info("No strategies found. Seeding memory...")
            self._seed_strategies()

    def _seed_strategies(self):
        """Inject hardcoded seed strategies."""
        for data in SEED_STRATEGIES:
            # Generate deterministic ID based on text
            text = data["text"]
            sid = hashlib.md5(text.encode("utf-8")).hexdigest()[:16]
            
            strat = Strategy(
                id=sid,
                text=text,
                kind=data.get("kind", StrategyType.ADVICE),
                tags=data.get("tags", []),
                uses=0,
                avg_reward=0.0
            )
            self.add_strategy(strat)
            
        # Force save after seeding
        self.save_strategies()

    def add_strategy(self, strategy: Strategy):
        """Add or update a strategy."""
        self.strategies[strategy.id] = strategy

    def save_strategies(self):
        """Persist strategies to strategies.jsonl atomically."""
        temp_path = self.strategies_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                for strat in self.strategies.values():
                    f.write(json.dumps(strat.to_dict()) + "\n")
            temp_path.replace(self.strategies_path)
        except Exception as e:
            logger.error(f"Failed to save strategies: {e}")

    def update_strategy_stats(self, sid: str, reward: float):
        """Update usage stats for a strategy."""
        if sid not in self.strategies:
            return
            
        strat = self.strategies[sid]
        
        # Moving average update
        n = strat.uses
        strat.avg_reward = (strat.avg_reward * n + reward) / (n + 1)
        strat.uses += 1
        strat.last_used = datetime.now().isoformat()
        
        # Optional: Deprecate if performance is terrible over many uses
        if n > 20 and strat.avg_reward < -0.3:
            strat.deprecated = True
            logger.info(f"Deprecating strategy {sid} due to poor performance: {strat.avg_reward:.2f}")

    def get_all_strategies(self) -> List[Strategy]:
        """Return all active (non-deprecated) strategies."""
        return [s for s in self.strategies.values() if not s.deprecated]

    def get_strategy(self, sid: str) -> Optional[Strategy]:
        return self.strategies.get(sid)
