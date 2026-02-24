"""Feature extraction from observations for policy network."""

import logging
from typing import List

from src.memory.types import Observation, MemoryNamespace

logger = logging.getLogger(__name__)


class Featurizer:
    """
    Extracts sparse feature keys from Observation.
    
    Features are derived from:
    - FSM state
    - Failure type
    - Attempt count
    - problem.canonical (tags, constraints, objective type)
    """

    def extract_features(
        self,
        observation: Observation,
        namespace: MemoryNamespace,
    ) -> List[str]:
        """
        Extract feature keys from observation.
        
        Returns:
            List of string keys like ["GLOBAL_BIAS", "FSM:SOLVE_DRAFT", "TAG:dp", ...]
        """
        keys = ["GLOBAL_BIAS"]
        
        # FSM state
        if observation.fsm_state:
            keys.append(f"FSM:{observation.fsm_state}")
        
        # Failure type (for replanning/retry)
        if observation.failure_type:
            keys.append(f"FAIL:{observation.failure_type}")
        
        # Attempt count bucket
        if observation.attempt_count > 0:
            bucket = min(observation.attempt_count, 5)
            keys.append(f"ATTEMPT:{bucket}")
        
        # Extract canonical features
        canonical = observation.canonical
        if canonical:
            keys.extend(self._extract_canonical_features(canonical, namespace))
        
        return keys

    def _extract_canonical_features(
        self,
        canonical: dict,
        namespace: MemoryNamespace,
    ) -> List[str]:
        """
        Extract features from problem.canonical.
        
        Namespace-specific logic:
        - plan: focus on problem_type, tags, objective
        - solve: focus on constraints, complexity, data structures
        - test: focus on input/output patterns, constraint ranges
        """
        features = []
        
        # Common features
        if "problem_type" in canonical:
            problem_types = canonical["problem_type"]
            if isinstance(problem_types, list):
                for pt in problem_types[:3]:  # Top 3 types
                    features.append(f"TYPE:{pt}")
        
        if "key_elements" in canonical:
            elements = canonical["key_elements"]
            if isinstance(elements, list):
                for elem in elements[:3]:
                    features.append(f"ELEM:{elem}")
        
        # Namespace-specific features
        if namespace == MemoryNamespace.PLAN:
            features.extend(self._plan_features(canonical))
        elif namespace == MemoryNamespace.SOLVE:
            features.extend(self._solve_features(canonical))
        elif namespace == MemoryNamespace.TEST:
            features.extend(self._test_features(canonical))
        
        return features

    def _plan_features(self, canonical: dict) -> List[str]:
        """Extract plan-relevant features (tags, objective)."""
        features = []
        
        # Objective type
        if "objective" in canonical:
            obj = canonical["objective"]
            if "count" in obj.lower():
                features.append("OBJ:count")
            elif "minimize" in obj.lower() or "maximize" in obj.lower():
                features.append("OBJ:optimize")
            elif "find" in obj.lower():
                features.append("OBJ:search")
            else:
                features.append("OBJ:decide")
        
        # Tags (if provided)
        if "tags" in canonical:
            tags = canonical["tags"]
            if isinstance(tags, list):
                for tag in tags[:5]:
                    features.append(f"TAG:{tag}")
        
        return features

    def _solve_features(self, canonical: dict) -> List[str]:
        """Extract solve-relevant features (constraints, complexity)."""
        features = []
        
        # Constraint ranges
        if "constraints" in canonical:
            constraints = canonical["constraints"]
            if isinstance(constraints, dict):
                # Check for large N
                for key in ["n", "N", "size"]:
                    if key in constraints:
                        val_str = str(constraints[key])
                        if "1e5" in val_str or "10^5" in val_str or "100000" in val_str:
                            features.append("CONSTR:n_1e5")
                        elif "1e6" in val_str or "10^6" in val_str or "1000000" in val_str:
                            features.append("CONSTR:n_1e6")
                        elif "2e5" in val_str or "200000" in val_str:
                            features.append("CONSTR:n_2e5")
                        break
        
        # Data structures (if mentioned in canonical)
        if "data_structures" in canonical:
            ds_list = canonical["data_structures"]
            if isinstance(ds_list, list):
                for ds in ds_list[:3]:
                    features.append(f"DS:{ds}")
        
        return features

    def _test_features(self, canonical: dict) -> List[str]:
        """Extract test-relevant features (input/output format, constraint complexity)."""
        features = []

        # Input format
        if "input_format" in canonical:
            inp = canonical["input_format"]
            if "array" in inp.lower():
                features.append("INPUT:array")
            if "graph" in inp.lower():
                features.append("INPUT:graph")
            if "string" in inp.lower():
                features.append("INPUT:string")
            if "tree" in inp.lower():
                features.append("INPUT:tree")

        # Output format
        if "output_format" in canonical:
            out = canonical["output_format"]
            if "single" in out.lower() or "integer" in out.lower():
                features.append("OUTPUT:single")
            if "array" in out.lower() or "list" in out.lower():
                features.append("OUTPUT:array")
            if "string" in out.lower():
                features.append("OUTPUT:string")

        # Checker type: multi-solution vs single-solution
        if "is_multi_solution" in canonical:
            if canonical["is_multi_solution"]:
                features.append("CHECKER:multi")
            else:
                features.append("CHECKER:single")

        # Graph structure type (chain/star/tree/dag/bipartite/complete)
        if "graph_type" in canonical:
            graph_type = str(canonical["graph_type"]).lower()
            features.append(f"GRAPH:{graph_type}")
        # Also infer from problem_type list
        if "problem_type" in canonical:
            pts = canonical["problem_type"]
            if isinstance(pts, list):
                for pt in pts:
                    pt_lower = pt.lower()
                    if pt_lower in ("tree", "dag", "graph", "bipartite"):
                        features.append(f"GRAPH:{pt_lower}")

        # Integer overflow risk and SCALE features from n constraint
        if "constraints" in canonical:
            constraints = canonical["constraints"]
            if isinstance(constraints, dict):
                # Integer overflow risk
                for val in constraints.values():
                    val_str = str(val)
                    if any(marker in val_str for marker in ("1e18", "10^18", "1000000000000000000", "1e9")):
                        features.append("CONSTR:overflow_risk")
                        break
                        
                # SCALE buckets based on N
                if "n" in constraints:
                    val_str = str(constraints["n"]).replace(" ", "").lower()
                    if "1e6" in val_str or "10^6" in val_str or "1000000" in val_str:
                        features.append("SCALE:1M")
                    elif "1e5" in val_str or "10^5" in val_str or "100000" in val_str:
                        features.append("SCALE:100K")
                    elif "1e3" in val_str or "10^3" in val_str or "1000" in val_str:
                        features.append("SCALE:1K")

        return features
