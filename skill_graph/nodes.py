"""
Node hierarchy for the three-layer skill graph.

Layer  Type   Meaning
-----  -----  -----------------------------------------------------------
  1     Q     One training-set problem (description + solutions + tags)
  2     M     One accepted solution, decomposed into FunctionBlocks,
              SubProblems, an internal DAG, and ErrorExperiences
  3     S     One skill-knowledge-base entry (code template + metadata)
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .types import NodeId, NodeType, TagSet, Dataset, ComplexityTier, Metadata
from .blocks import (
    BlockDifference,
    BlockToSubproblem,
    DAGLink,
    ErrorExperience,
    FunctionBlock,
    SubProblem,
)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseNode(ABC):
    """
    Common interface shared by Q / M / S nodes.

    Subclasses must declare ``node_type`` as a class variable.
    ``node_id`` is auto-generated when ``node_id=None`` is passed.
    """

    node_type: NodeType   # declared by each concrete subclass

    def __init__(self, node_id: Optional[NodeId] = None,
                 metadata: Optional[Metadata] = None) -> None:
        self.node_id:  NodeId  = node_id or str(uuid.uuid4())
        self.metadata: Metadata = metadata or {}

    # ------------------------------------------------------------------
    # Abstract helpers
    # ------------------------------------------------------------------

    @abstractmethod
    def tag_set(self) -> Set[str]:
        """Return the canonical set of algorithmic tags for this node."""

    @abstractmethod
    def to_dict(self) -> dict:
        """Serialise to a plain Python dict (JSON-compatible)."""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict) -> "BaseNode":
        """Deserialise from a plain Python dict."""

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.node_id!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseNode):
            return NotImplemented
        return self.node_id == other.node_id

    def __hash__(self) -> int:
        return hash(self.node_id)


# ---------------------------------------------------------------------------
# Q-Node  –  Problem node (Layer 1)
# ---------------------------------------------------------------------------

class QNode(BaseNode):
    """
    Represents one training-set problem.

    Fields
    ------
    problem_id          : Original ID in the source dataset.
    dataset             : Which dataset this problem comes from.
    abstract_description: Abstract problem description for retrieval/similarity.
    tags                : Backward-compatible tag list (defaults to tags_level1).
    tags_level1         : First-level tags (used in Jaccard matching).
    tags_level2         : Second-level tags (stored, not used in matching yet).
    correct_solutions   : List of accepted solution source strings.
    incorrect_solutions : List of (solution_id, source) pairs for WA/TLE solutions.
    test_cases          : Raw sample/generated test case strings.
    """

    node_type = NodeType.Q

    def __init__(
        self,
        problem_id:           str,
        abstract_description: str,
        tags:                 Optional[TagSet]                           = None,
        tags_level1:          Optional[TagSet]                           = None,
        tags_level2:          Optional[TagSet]                           = None,
        correct_solutions:    Optional[List[str]]                        = None,
        incorrect_solutions:  Optional[List[Dict[str, str]]]             = None,
        test_cases:           Optional[List[str]]                        = None,
        dataset:              Dataset                                    = Dataset.UNKNOWN,
        node_id:              Optional[NodeId]                           = None,
        metadata:             Optional[Metadata]                         = None,
    ) -> None:
        super().__init__(node_id=node_id, metadata=metadata)
        self.problem_id           = problem_id
        self.abstract_description = abstract_description
        base_tags = list(tags or [])
        level1 = list(tags_level1 or [])
        self.tags_level1:          TagSet                      = level1
        self.tags_level2:          TagSet                      = list(tags_level2 or [])
        self.tags:                 TagSet                      = base_tags
        self.correct_solutions:   List[str]                   = list(correct_solutions or [])
        # Each entry: {"sol_id": str, "source": str, "verdict": str, ...}
        self.incorrect_solutions: List[Dict[str, str]]        = list(incorrect_solutions or [])
        self.test_cases:          List[str]                   = list(test_cases or [])
        self.dataset:             Dataset                     = dataset

    # ------------------------------------------------------------------

    def tag_set(self) -> Set[str]:
        # Jaccard priority: tags -> fallback tags_level1.
        return set(self.tags or self.tags_level1)

    def to_dict(self) -> dict:
        return {
            "node_id":             self.node_id,
            "node_type":           self.node_type.value,
            "problem_id":          self.problem_id,
            "abstract_description": self.abstract_description,
            "tags":                self.tags,
            "tags_level1":         self.tags_level1,
            "tags_level2":         self.tags_level2,
            "correct_solutions":   self.correct_solutions,
            "incorrect_solutions": self.incorrect_solutions,
            "test_cases":          self.test_cases,
            "dataset":             self.dataset.value,
            "metadata":            self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QNode":
        return cls(
            node_id=data["node_id"],
            problem_id=data["problem_id"],
            abstract_description=data.get("abstract_description", data.get("description", "")),
            tags=data.get("tags", []),
            tags_level1=data.get("tags_level1"),
            tags_level2=data.get("tags_level2"),
            correct_solutions=data.get("correct_solutions", []),
            incorrect_solutions=data.get("incorrect_solutions", []),
            test_cases=data.get("test_cases", []),
            dataset=Dataset.from_str(data.get("dataset", "unknown")),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# M-Node  –  Method node (Layer 2)
# ---------------------------------------------------------------------------

class MNode(BaseNode):
    """
    Represents one method-layer node attached to a QNode.

    In this repo we model **two** kinds of M-nodes:
    - kind="analysis": logic structure extracted from the correct solution
      (from solver/prompt_templates/correct_solution_logic_chain.txt)
    - kind="contrast": comparison analysis between one correct and one incorrect
      solution (from solver/prompt_templates/correct_vs_incorrect_logic_diff.txt)

    Given the dataset setup (1 correct + 3 incorrect per problem), each QNode
    typically connects to 1 + 3 MNodes via QMEdge.

    Populated from the logic-pipeline JSON output for one correct solution:

    function_blocks      – list of FunctionBlock (from ``function_blocks``).
    subproblems          – list of SubProblem nodes (from
                           ``sub_problem_dag.nodes``).
    dag_links            – directed edges of the sub-problem DAG (from
                           ``sub_problem_dag.edges``).
    block_to_subproblem  – block ↔ sub-problem mapping (from
                           ``block_to_subproblem``).
    requirements         – code templates and knowledge points extracted by
                           the pipeline (from ``requirements``).
    error_experiences    – per-incorrect-solution post-mortems, each built
                           from one ``block_differences`` + ``global_diagnosis``
                           comparison run.
    """

    node_type = NodeType.M

    def __init__(
        self,
        source_problem_id:   NodeId,
        kind:                str                                = "analysis",
        incorrect_index:     Optional[int]                       = None,
        function_blocks:     Optional[List[FunctionBlock]]     = None,
        subproblems:         Optional[List[SubProblem]]        = None,
        dag_links:           Optional[List[DAGLink]]           = None,
        block_to_subproblem: Optional[List[BlockToSubproblem]] = None,
        requirements:        Optional[List[str]]               = None,
        error_experiences:   Optional[List[ErrorExperience]]   = None,
        node_id:             Optional[NodeId]                  = None,
        metadata:            Optional[Metadata]                = None,
    ) -> None:
        super().__init__(node_id=node_id, metadata=metadata)
        self.source_problem_id:   NodeId                    = source_problem_id
        self.kind:                str                       = kind
        self.incorrect_index:     Optional[int]             = incorrect_index
        self.function_blocks:     List[FunctionBlock]       = list(function_blocks or [])
        self.subproblems:         List[SubProblem]          = list(subproblems or [])
        self.dag_links:           List[DAGLink]             = list(dag_links or [])
        self.block_to_subproblem: List[BlockToSubproblem]   = list(block_to_subproblem or [])
        self.requirements:        List[str]                 = list(requirements or [])
        self.error_experiences:   List[ErrorExperience]     = list(error_experiences or [])

        # Fast lookup: block_id → FunctionBlock
        self._block_index: Dict[str, FunctionBlock] = {
            b.block_id: b for b in self.function_blocks
        }
        # Fast lookup: sub_id → SubProblem
        self._sub_index: Dict[str, SubProblem] = {
            s.sub_id: s for s in self.subproblems
        }

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def add_block(self, block: FunctionBlock) -> None:
        self.function_blocks.append(block)
        self._block_index[block.block_id] = block

    def get_block(self, block_id: str) -> Optional[FunctionBlock]:
        return self._block_index.get(block_id)

    def add_subproblem(self, sp: SubProblem) -> None:
        self.subproblems.append(sp)
        self._sub_index[sp.sub_id] = sp

    def get_subproblem(self, sub_id: str) -> Optional[SubProblem]:
        return self._sub_index.get(sub_id)

    def add_dag_link(self, link: DAGLink) -> None:
        self.dag_links.append(link)

    def add_block_mapping(self, mapping: BlockToSubproblem) -> None:
        self.block_to_subproblem.append(mapping)

    def add_error_experience(self, exp: ErrorExperience) -> None:
        self.error_experiences.append(exp)

    def subproblem_for_block(self, block_id: str) -> Optional[SubProblem]:
        """Return the SubProblem that block_id is mapped to, or None."""
        for mapping in self.block_to_subproblem:
            if mapping.block_id == block_id:
                return self._sub_index.get(mapping.subproblem_id)
        return None

    # ------------------------------------------------------------------

    def tag_set(self) -> Set[str]:
        """Union of all tags across every function block."""
        tags: Set[str] = set()
        for block in self.function_blocks:
            tags.update(block.tags)
        return tags

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        def _bd_to_dict(bd: BlockDifference) -> dict:
            return {
                "block_name":           bd.block_name,
                "subproblem_name":      bd.subproblem_name,
                "error_type":           bd.error_type,
                "error_analysis":       bd.error_analysis,
                "correct_rationale":    bd.correct_rationale,
                "prevention_guideline": bd.prevention_guideline,
            }

        def _exp_to_dict(e: ErrorExperience) -> dict:
            return {
                "exp_id":            e.exp_id,
                "incorrect_sol_id":  e.incorrect_sol_id,
                "block_differences": [_bd_to_dict(bd) for bd in e.block_differences],
                "global_diagnosis":  e.global_diagnosis,
                "requirements":      e.requirements,
                "metadata":          e.metadata,
            }

        return {
            "node_id":             self.node_id,
            "node_type":           self.node_type.value,
            "source_problem_id":   self.source_problem_id,
            "kind":                self.kind,
            "incorrect_index":     self.incorrect_index,
            "requirements":        self.requirements,
            # Use the block-layer serializers so keys match the prompt schema
            "function_blocks":     [b.to_dict() for b in self.function_blocks],
            "subproblems":         [s.to_dict() for s in self.subproblems],
            "dag_links":           [l.to_dict() for l in self.dag_links],
            "block_to_subproblem": [m.to_dict() for m in self.block_to_subproblem],
            "error_experiences":   [_exp_to_dict(e) for e in self.error_experiences],
            "metadata":            self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MNode":
        from dataclasses import fields as dc_fields

        def _simple(dc_cls, d: dict):
            # Prefer explicit from_dict (handles prompt-schema keys + legacy keys)
            if hasattr(dc_cls, "from_dict"):
                return dc_cls.from_dict(d)  # type: ignore[attr-defined]
            valid = {f.name for f in dc_fields(dc_cls)}
            return dc_cls(**{k: v for k, v in d.items() if k in valid})

        def _exp_from_dict(d: dict) -> ErrorExperience:
            bds = [
                BlockDifference(
                    block_name=bd.get("block_name"),
                    subproblem_name=bd.get("subproblem_name"),
                    error_type=bd["error_type"],
                    error_analysis=bd["error_analysis"],
                    correct_rationale=bd["correct_rationale"],
                    prevention_guideline=bd["prevention_guideline"],
                )
                for bd in d.get("block_differences", [])
            ]
            return ErrorExperience(
                exp_id=d["exp_id"],
                incorrect_sol_id=d["incorrect_sol_id"],
                block_differences=bds,
                global_diagnosis=d.get("global_diagnosis"),
                requirements=d.get("requirements", []),
                metadata=d.get("metadata", {}),
            )

        return cls(
            node_id=data["node_id"],
            source_problem_id=data["source_problem_id"],
            kind=data.get("kind", "analysis"),
            incorrect_index=data.get("incorrect_index"),
            requirements=data.get("requirements", []),
            function_blocks=[_simple(FunctionBlock, b)
                              for b in data.get("function_blocks", [])],
            subproblems=[_simple(SubProblem, s)
                         for s in data.get("subproblems", [])],
            dag_links=[_simple(DAGLink, l)
                       for l in data.get("dag_links", [])],
            block_to_subproblem=[_simple(BlockToSubproblem, m)
                                  for m in data.get("block_to_subproblem", [])],
            error_experiences=[_exp_from_dict(e)
                                for e in data.get("error_experiences", [])],
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# S-Node  –  Skill node (Layer 3)
# ---------------------------------------------------------------------------

class SNode(BaseNode):
    """
    Represents one entry in the algorithm skills knowledge base.

    The ``code_template`` field holds the authoritative implementation with
    a leading comment block (in English) that documents the algorithm logic
    and every public function's usage.

    ``source_url`` optionally traces back to the original teaching resource.
    """

    node_type = NodeType.S

    def __init__(
        self,
        skill_id:          str,
        title:             str,
        description:       str,
        tags:              Optional[TagSet]        = None,
        code_template:     str                     = "",
        complexity_time:   ComplexityTier          = ComplexityTier.UNKNOWN,
        complexity_space:  ComplexityTier          = ComplexityTier.UNKNOWN,
        source_url:        Optional[str]           = None,
        node_id:           Optional[NodeId]        = None,
        metadata:          Optional[Metadata]      = None,
    ) -> None:
        super().__init__(node_id=node_id, metadata=metadata)
        self.skill_id:          str             = skill_id
        self.title:             str             = title
        self.description:       str             = description
        self.tags:              TagSet          = list(tags or [])
        self.code_template:     str             = code_template
        self.complexity_time:   ComplexityTier  = complexity_time
        self.complexity_space:  ComplexityTier  = complexity_space
        self.source_url:        Optional[str]   = source_url

    # ------------------------------------------------------------------

    def tag_set(self) -> Set[str]:
        return set(self.tags)

    def to_dict(self) -> dict:
        return {
            "node_id":          self.node_id,
            "node_type":        self.node_type.value,
            "skill_id":         self.skill_id,
            "title":            self.title,
            "description":      self.description,
            "tags":             self.tags,
            "code_template":    self.code_template,
            "complexity_time":  self.complexity_time.value,
            "complexity_space": self.complexity_space.value,
            "source_url":       self.source_url,
            "metadata":         self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SNode":
        def _tier(v: str) -> ComplexityTier:
            try:
                return ComplexityTier(v)
            except ValueError:
                return ComplexityTier.UNKNOWN

        return cls(
            node_id=data["node_id"],
            skill_id=data["skill_id"],
            title=data["title"],
            description=data["description"],
            tags=data.get("tags", []),
            code_template=data.get("code_template", ""),
            complexity_time=_tier(data.get("complexity_time", "unknown")),
            complexity_space=_tier(data.get("complexity_space", "unknown")),
            source_url=data.get("source_url"),
            metadata=data.get("metadata", {}),
        )
