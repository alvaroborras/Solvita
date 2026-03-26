"""Memory client for namespace-isolated trainable memory."""

import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

from src.memory.types import (
    MemoryNamespace,
    MemoryItem,
    MemoryEvent,
    Observation,
)
from src.memory.store import MemoryStore
from src.memory.policy import BanditPolicy
from src.memory.featurizer import Featurizer
from src.memory.skill_loader import SkillLoader

logger = logging.getLogger(__name__)


def render_oracle_plan_to_prompt_payload(plan: Any, catalog_item: Dict[str, Any]) -> List[Dict[str, Any]]:
    del plan
    return [
        {
            "family_id": catalog_item["family_id"],
            "name": catalog_item["text"],
            "strategy": ", ".join(catalog_item["payload"].get("brute_force_strategies", [])),
            "complexity_notes": catalog_item["payload"].get("complexity_notes", []),
            "code_snippet": catalog_item["payload"].get("code_template", "").strip(),
        }
    ]


def resolve_oracle_item_ids_by_family_ids(
    client: "MemoryClient",
    family_ids: List[str],
) -> List[str]:
    if not client.enabled or not client.store:
        return []

    remaining = set(family_ids)
    resolved: List[str] = []
    for item in client.store.get_all_items():
        family_id = item.payload.get("family_id")
        if family_id in remaining:
            resolved.append(item.id)
            remaining.remove(family_id)
    return resolved


class MemoryClient:
    """
    Unified memory client supporting plan/solve/test namespaces.
    
    Usage:
        client = MemoryClient(namespace="plan", config=config, problem_desc=desc)
        injection_text, item_ids = client.get_injection(observation)
        # ... agent generates output ...
        client.log_event(observation, item_ids, reward)
    """

    def __init__(
        self,
        namespace: MemoryNamespace,
        config: Dict[str, Any],
        problem_desc: str = "",
        canonical: Optional[Dict[str, Any]] = None,
    ):
        if isinstance(namespace, str):
            namespace = MemoryNamespace(namespace)
        
        self.namespace = namespace
        self.config = config or {}
        self.enabled = self.config.get("trainable_memory", {}).get("enabled", False)
        self.top_k = self.config.get("trainable_memory", {}).get(f"{namespace.value}_top_k", 3)
        self.data_dir = Path(
            self.config.get("trainable_memory", {}).get("data_dir", "data/memory")
        )
        
        self.problem_desc = problem_desc
        self.canonical = canonical or {}
        self.problem_hash = hashlib.md5(problem_desc.encode("utf-8")).hexdigest()
        
        self.store: Optional[MemoryStore] = None
        self.policy: Optional[BanditPolicy] = None
        self.featurizer: Optional[Featurizer] = None
        self.skill_loader: Optional[SkillLoader] = None
        
        # Last suggested item IDs (for convenience)
        self.last_suggested_ids: List[str] = []

        if self.enabled:
            logger.info(f"Initializing Memory [{namespace.value}] at {self.data_dir} (SQLite)")
            try:
                self.store = MemoryStore(namespace, self.data_dir)
                self.store.initialize()
                
                # Initialize policy
                policy_path = self.data_dir / namespace.value / "policy.json"
                self.policy = BanditPolicy(policy_path)
                
                # Initialize featurizer
                self.featurizer = Featurizer()
                
                # Initialize skill loader (for solve namespace)
                if namespace == MemoryNamespace.SOLVE:
                    self.skill_loader = SkillLoader()
                
            except Exception as e:
                logger.error(f"Failed to initialize memory, disabling: {e}")
                self.enabled = False
        else:
            logger.debug(f"Memory [{namespace.value}] is disabled in config.")

    def get_injection(
        self,
        fsm_state: str,
        failure_type: Optional[str] = None,
        attempt_count: int = 0,
    ) -> Tuple[str, List[str]]:
        """
        Retrieve items for injection into the agent prompt.
        
        Returns:
            (injection_text, selected_item_ids)
        """
        if not self.enabled or not self.store:
            return "", []
        
        try:
            # Build observation
            obs = Observation(
                fsm_state=fsm_state,
                failure_type=failure_type,
                attempt_count=attempt_count,
                canonical=self.canonical,
                raw_problem_desc=self.problem_desc,
            )
            
            # Extract features (if featurizer available)
            if self.featurizer:
                obs.feature_keys = self.featurizer.extract_features(obs, self.namespace)
            
            # Get candidate items
            candidates = self.store.get_all_items()
            
            # Select items using policy (if available)
            if self.policy:
                chosen = self.policy.predict(obs, candidates, top_k=self.top_k)
            else:
                # Fallback: select by avg_reward
                chosen = sorted(candidates, key=lambda x: x.avg_reward, reverse=True)[:self.top_k]
            
            self.last_suggested_ids = [item.id for item in chosen]
            
            if not chosen:
                return "", []
            
            # Format injection text (namespace-specific formatting)
            injection_text = self._format_injection(chosen)
            
            return injection_text, self.last_suggested_ids
        
        except Exception as e:
            logger.error(f"Error in get_injection: {e}")
            return "", []

    def log_event(
        self,
        observation: Observation,
        selected_item_ids: List[str],
        reward: float,
        iteration: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Log an event and update policy + item stats.
        """
        if not self.enabled or not self.store:
            return
        
        try:
            # Create event
            event = MemoryEvent(
                timestamp=datetime.now().isoformat(),
                namespace=self.namespace,
                observation=observation,
                selected_item_ids=selected_item_ids,
                reward=reward,
                problem_hash=self.problem_hash,
                iteration=iteration,
                metadata=metadata or {},
            )
            
            # Log event to disk
            self.store.log_event(event)
            
            # Update policy (if available)
            if self.policy:
                self.policy.update(observation, selected_item_ids, reward)
                self.policy.save()
            
            # Update item statistics
            for item_id in selected_item_ids:
                self.store.update_item_stats(item_id, reward)
            self.store.save_items()
            
            logger.info(
                f"[{self.namespace.value}] Event logged: reward={reward:.2f}, "
                f"items={len(selected_item_ids)}"
            )
        
        except Exception as e:
            logger.error(f"Error logging event: {e}")

    def log_event_simple(
        self,
        fsm_state: str,
        failure_type: Optional[str],
        reward: float,
        item_ids: Optional[List[str]] = None,
        attempt_count: int = 0,
    ):
        """
        Convenience method: log event using simple params.
        
        If item_ids not provided, uses self.last_suggested_ids.
        """
        if item_ids is None:
            item_ids = self.last_suggested_ids
        
        if not item_ids:
            return
        
        obs = Observation(
            fsm_state=fsm_state,
            failure_type=failure_type,
            attempt_count=attempt_count,
            canonical=self.canonical,
            raw_problem_desc=self.problem_desc,
        )
        
        if self.featurizer:
            obs.feature_keys = self.featurizer.extract_features(obs, self.namespace)
        
        self.log_event(obs, item_ids, reward)

    def _format_injection(self, items: List[MemoryItem]) -> str:
        """Format selected items for prompt injection (namespace-specific)."""
        if not items:
            return ""
        
        lines = [f"\n[Memory: {self.namespace.value.upper()} strategies]"]
        
        for item in items:
            lines.append(f"- {item.text}")
            
            # Add payload details if relevant
            if self.namespace == MemoryNamespace.PLAN:
                payload = item.payload
                if payload.get("subfunctions"):
                    lines.append(f"  Subfunctions: {', '.join(payload['subfunctions'])}")
                if payload.get("canonical_hints"):
                    lines.append(f"  Hints: {payload['canonical_hints']}")
            
            elif self.namespace == MemoryNamespace.SOLVE:
                payload = item.payload
                if payload.get("step_strategies"):
                    for strat in payload["step_strategies"][:2]:  # Show top 2
                        lines.append(f"  - {strat}")
                if payload.get("anti_patterns"):
                    lines.append(f"  Avoid: {', '.join(payload['anti_patterns'][:2])}")
                # Load skills if available
                if self.skill_loader and payload.get("skills"):
                    skills_text = self.skill_loader.load_skills_for_item(payload)
                    if skills_text:
                        lines.append(skills_text)
            
            elif self.namespace == MemoryNamespace.TEST:
                payload = item.payload
                if payload.get("generation_strategies"):
                    for strat in payload["generation_strategies"][:2]:
                        lines.append(f"  - {strat}")
                        
            elif self.namespace == MemoryNamespace.HACK:
                payload = item.payload
                if payload.get("adversarial_patterns"):
                    lines.append(f"  Patterns: {', '.join(payload['adversarial_patterns'][:3])}")
                if payload.get("edge_cases"):
                    lines.append(f"  Edge Cases: {', '.join(payload['edge_cases'][:3])}")
                    
            elif self.namespace == MemoryNamespace.ORACLE:
                # Build structured JSON for ORACLE templates (consumed by build_solver_prompt)
                oracle_entries = []
                for index, item in enumerate(items):
                    payload = item.payload
                    entry = {
                        "name": item.text,
                        "strategy": ", ".join(payload.get("brute_force_strategies", [])),
                        "complexity_notes": payload.get("complexity_notes", []),
                    }
                    if index == 0:
                        entry["code_snippet"] = payload.get("code_template", "").strip()
                    oracle_entries.append(entry)
                import json as _json
                return _json.dumps(oracle_entries, indent=2)
        
        lines.append("")  # Trailing newline
        return "\n".join(lines)
