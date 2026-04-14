"""
Fine-grained building blocks stored inside an MNode.

These structures mirror the JSON schema produced by the logic pipeline
(solver/prompt_templates/correct_solution_logic_chain.txt and
correct_vs_incorrect_logic_diff.txt).

Hierarchy inside one MNode
--------------------------
  FunctionBlock      – one function or logical code segment, with its
                       short id (e.g. "F1"), human-readable name/label,
                       and role description.  Tags are optionally inferred
                       from the role text for MS-edge initialisation.

  SubProblem         – one node of the sub-problem DAG.  Stores the
                       pipeline's id (e.g. "P1") and abstract algorithmic
                       description.

  DAGLink            – one directed edge of the sub-problem DAG,
                       mirroring sub_problem_dag.edges: {from_id, to_id}.

  BlockToSubproblem  – the block_to_subproblem mapping entry: which
                       FunctionBlock implements which SubProblem.

  ErrorExperience    – one entry from block_differences in the diff
                       pipeline output, plus the top-level global_diagnosis
                       for that incorrect-solution comparison.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .types import BlockId, TagSet, Metadata


# ---------------------------------------------------------------------------
# FunctionBlock
# ---------------------------------------------------------------------------

@dataclass
class FunctionBlock:
    """
    One function or logical code segment extracted from a correct solution.

    Fields map directly to the ``function_blocks`` array in the logic-chain
    pipeline output:

    block_id       – short unique id assigned by the pipeline, e.g. "F1".
    name_or_label  – function name, or a human-readable label for an unnamed
                     code segment, e.g. "read_input" or "build_prefix_sums".
    role           – 1–2 sentences describing what this block does.  For
                     blocks implementing a standard algorithmic technique
                     (BFS, DP, …) the technique is explicitly named here,
                     aligned with the problem's algorithm tags.
    tags           – algorithmic tags inferred from the role text (e.g.
                     ["bfs", "graphs"]).  Not produced by the pipeline
                     directly; populated during graph construction by
                     matching role vocabulary against the problem tag set.
                     Required by EdgeWeightInitializer for MS-edge setup.
    code           – optional: the actual source text of this block.
                     The pipeline does not extract per-block code, but
                     callers may populate this for richer context.
    """

    # NOTE: the logic prompt uses key name `id`; we store it as `id` to match.
    id:             BlockId
    name_or_label:  str
    role:           str
    tags:           TagSet           = field(default_factory=list)
    code:           str              = ""
    metadata:       Metadata         = field(default_factory=dict)

    @classmethod
    def new(cls, name_or_label: str, role: str,
            tags: Optional[TagSet] = None,
            code: str = "",
            id: Optional[BlockId] = None,
            block_id: Optional[BlockId] = None,
            **kwargs) -> "FunctionBlock":
        bid = id or block_id or str(uuid.uuid4())
        return cls(
            id=bid,
            name_or_label=name_or_label,
            role=role,
            tags=list(tags or []),
            code=code,
            **kwargs,
        )

    @property
    def block_id(self) -> BlockId:
        """Backward-compatible alias for older code paths."""
        return self.id

    def to_dict(self) -> Dict[str, Any]:
        # Mirror the prompt schema for logic_analysis.function_blocks
        return {
            "id": self.id,
            "name_or_label": self.name_or_label,
            "role": self.role,
            # These are framework-only extras; kept for completeness.
            "tags": list(self.tags),
            "code": self.code,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FunctionBlock":
        # Accept both prompt-style `id` and legacy `block_id`.
        fid = data.get("id", data.get("block_id"))
        return cls(
            id=str(fid),
            name_or_label=str(data.get("name_or_label", "")),
            role=str(data.get("role", "")),
            tags=list(data.get("tags", []) or []),
            code=str(data.get("code", "") or ""),
            metadata=data.get("metadata", {}) or {},
        )

    def tag_set(self) -> Set[str]:
        return set(self.tags)


# ---------------------------------------------------------------------------
# SubProblem
# ---------------------------------------------------------------------------

@dataclass
class SubProblem:
    """
    One node of the sub-problem DAG inside an MNode.

    Fields map to ``sub_problem_dag.nodes`` in the pipeline output:

    sub_id      – short unique id, e.g. "P1".
    description – abstract algorithmic description of what to compute,
                  independent of the problem's story framing.
    """

    # Prompt schema uses key name `id`; we store it as `id` to match.
    id:           str
    description:  str
    metadata:     Metadata = field(default_factory=dict)

    @classmethod
    def new(cls, description: str,
            id: Optional[str] = None,
            sub_id: Optional[str] = None) -> "SubProblem":
        sid = id or sub_id or str(uuid.uuid4())
        return cls(
            id=sid,
            description=description,
        )

    @property
    def sub_id(self) -> str:
        """Backward-compatible alias for older code paths."""
        return self.id

    def to_dict(self) -> Dict[str, Any]:
        # Mirror the prompt schema for sub_problem_dag.nodes
        return {
            "id": self.id,
            "description": self.description,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubProblem":
        sid = data.get("id", data.get("sub_id"))
        return cls(
            id=str(sid),
            description=str(data.get("description", "")),
            metadata=data.get("metadata", {}) or {},
        )


# ---------------------------------------------------------------------------
# DAGLink  (sub-problem dependency edge)
# ---------------------------------------------------------------------------

@dataclass
class DAGLink:
    """
    One directed edge in the sub-problem DAG.

    Maps to ``sub_problem_dag.edges`` in the pipeline output:
        {from_id: str, to_id: str}

    Meaning: the sub-problem identified by ``from_id`` must be solved
    (or its result available) before the sub-problem ``to_id``.
    """

    link_id:  str
    from_id:  str   # SubProblem.sub_id of the prerequisite
    to_id:    str   # SubProblem.sub_id of the dependent

    @classmethod
    def new(cls, from_id: str, to_id: str) -> "DAGLink":
        return cls(
            link_id=str(uuid.uuid4()),
            from_id=from_id,
            to_id=to_id,
        )

    def to_dict(self) -> Dict[str, Any]:
        # Prompt schema for sub_problem_dag.edges
        return {"from_id": self.from_id, "to_id": self.to_id}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DAGLink":
        return cls(
            link_id=str(data.get("link_id") or uuid.uuid4()),
            from_id=str(data.get("from_id", "")),
            to_id=str(data.get("to_id", "")),
        )


# ---------------------------------------------------------------------------
# BlockToSubproblem  (block ↔ sub-problem mapping)
# ---------------------------------------------------------------------------

@dataclass
class BlockToSubproblem:
    """
    One entry of the ``block_to_subproblem`` mapping from the pipeline.

    Links a FunctionBlock (by its pipeline id) to the SubProblem it
    primarily implements.

    block_id       – matches FunctionBlock.block_id (e.g. "F1").
    subproblem_id  – matches SubProblem.sub_id (e.g. "P2").
    rationale      – optional one-sentence explanation of the link.
    """

    block_id:      BlockId
    subproblem_id: str
    rationale:     Optional[str] = None

    @classmethod
    def new(cls, block_id: BlockId, subproblem_id: str,
            rationale: Optional[str] = None) -> "BlockToSubproblem":
        return cls(
            block_id=block_id,
            subproblem_id=subproblem_id,
            rationale=rationale,
        )

    def to_dict(self) -> Dict[str, Any]:
        # Prompt schema for block_to_subproblem
        out: Dict[str, Any] = {
            "block_id": self.block_id,
            "subproblem_id": self.subproblem_id,
        }
        if self.rationale is not None:
            out["rationale"] = self.rationale
        return out

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BlockToSubproblem":
        return cls(
            block_id=str(data.get("block_id", "")),
            subproblem_id=str(data.get("subproblem_id", "")),
            rationale=data.get("rationale"),
        )


# ---------------------------------------------------------------------------
# ErrorExperience
# ---------------------------------------------------------------------------

# Known error type tags (from the diff-template spec).
ERROR_TYPES = frozenset({
    "logic_bug",
    "index_boundary",
    "edge_case_missing",
    "algorithm_incomplete_or_wrong",
    "complexity_issue",
    "io_format",
    "state_definition_or_invariant",
    "overflow_or_numerical",
    "infinite_loop_or_non_termination",
})


@dataclass
class ErrorExperience:
    """
    A post-mortem entry produced by comparing a correct solution against
    one incorrect solution.  One MNode accumulates one ErrorExperience per
    incorrect solution it was compared with.

    Each ErrorExperience bundles:
    - Identification fields (which incorrect solution, which comparison run)
    - One or more ``block_differences`` items (see below)
    - A top-level ``global_diagnosis`` for the whole comparison

    The ``block_differences`` list maps to the pipeline's array of the same
    name; each entry is a ``BlockDifference`` (inner dataclass below).

    Fields
    ------
    exp_id           – unique id for this experience record.
    incorrect_sol_id – id/index of the incorrect solution in QNode.
    block_differences – list of per-block failure analyses.
    global_diagnosis  – 2–5 sentence high-level summary of how/why the
                        incorrect solution fails overall.
    requirements      – code templates / knowledge points that were missing
                        or misapplied in the incorrect solution (first 1–2
                        items are code templates; rest are techniques).
    """

    exp_id:             str
    incorrect_sol_id:   str
    block_differences:  List["BlockDifference"] = field(default_factory=list)
    global_diagnosis:   Optional[str]           = None
    requirements:       List[str]               = field(default_factory=list)
    metadata:           Metadata                = field(default_factory=dict)

    @classmethod
    def new(cls, incorrect_sol_id: str,
            block_differences: Optional[List["BlockDifference"]] = None,
            global_diagnosis: Optional[str] = None,
            requirements: Optional[List[str]] = None,
            **kwargs) -> "ErrorExperience":
        return cls(
            exp_id=str(uuid.uuid4()),
            incorrect_sol_id=incorrect_sol_id,
            block_differences=list(block_differences or []),
            global_diagnosis=global_diagnosis,
            requirements=list(requirements or []),
            **kwargs,
        )


@dataclass
class BlockDifference:
    """
    One item in the ``block_differences`` array from the diff pipeline.

    Describes a single block or sub-problem where the incorrect solution
    diverges from the correct one.

    block_name          – ``name_or_label`` of the matching FunctionBlock
                          in the reference (correct) solution; None if no
                          clear match exists.
    subproblem_name     – the ``description`` of the matching SubProblem;
                          None if the failure is not subproblem-specific.
    error_type          – short tag classifying the error category, e.g.
                          "logic_bug", "index_boundary", "complexity_issue".
                          See ``ERROR_TYPES`` for the canonical set.
    error_analysis      – 2–5 sentences explaining where and how the
                          incorrect solution goes wrong, contrasting it with
                          the correct behaviour at both code and algorithm
                          level.
    correct_rationale   – brief explanation of how the correct solution
                          handles this block/sub-problem correctly.
    prevention_guideline – concise, generalizable advice for avoiding this
                           class of mistake in the future.
    """

    error_type:           str
    error_analysis:       str
    correct_rationale:    str
    prevention_guideline: str
    block_name:           Optional[str] = None
    subproblem_name:      Optional[str] = None

    @classmethod
    def new(cls, error_type: str, error_analysis: str,
            correct_rationale: str, prevention_guideline: str,
            block_name: Optional[str] = None,
            subproblem_name: Optional[str] = None) -> "BlockDifference":
        return cls(
            error_type=error_type,
            error_analysis=error_analysis,
            correct_rationale=correct_rationale,
            prevention_guideline=prevention_guideline,
            block_name=block_name,
            subproblem_name=subproblem_name,
        )
