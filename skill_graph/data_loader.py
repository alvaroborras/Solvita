"""
Data-loading interface for building the three-layer SolvitaSkillGraph.

The expected on-disk formats are inferred from existing pipelines:

Q layer source
  data/logic/pipeline_both_solutions_with_logic_*.jsonl
  (or data/logic_copy with the same schema)
  Q nodes are intentionally lightweight and only keep:
    - problem_id (internal linkage key)
    - description
    - tags
  These three fields are read from each logic record.

M layer source
  data/logic_copy/pipeline_both_solutions_with_logic_*.jsonl
  Each JSONL record contains:
    - id/dataset/description/test_case/tags
    - correct_solution: list[str]
    - incorrect_solution: list[{"code": str, ...}]
    - logic_analysis: { requirements, function_blocks, sub_problem_dag, block_to_subproblem }
    - logic_contrasts: list[ { correct_index, incorrect_index, logic_contrast } ]

S layer source
  skills/*.md
  The skills README defines the markdown fields:
    - "## Skill: SkillName"
    - "- Tag: tag_value" (one or more)
    - "- Complexity: ..."
    - "### Snippet (C++17)" followed by a fenced code block
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from .blocks import (
    BlockDifference,
    BlockToSubproblem,
    DAGLink,
    ErrorExperience,
    FunctionBlock,
    SubProblem,
)
from .edges import QMEdge
from .graph import SolvitaSkillGraph
from .qm_init_weights import qm_weights_per_m_kind
from .initializer import EdgeWeightInitializer
from .nodes import MNode, QNode, SNode
from .types import ComplexityTier
from .tag_utils import canonicalize_tag, canonicalize_tag_set, canonicalize_text

logger = logging.getLogger(__name__)


_SKILL_HEADER_RE = re.compile(r"^##\\s*Skill:\\s*(.*)\\s*$")
_SKILL_TAG_RE = re.compile(r"^-\\s*Tag:\\s*(.*)\\s*$")
_SKILL_COMPLEXITY_RE = re.compile(r"^-\\s*Complexity:\\s*(.*)\\s*$")
_COMMENT_TAG_RE = re.compile(r"^\\s*\\*\\s*Tag\\s*:\\s*(.*)\\s*$")
_COMMENT_DESCRIPTION_RE = re.compile(r"^\\s*\\*\\s*Description\\s*:\\s*(.*)\\s*$")


def _infer_skill_complexity_tiers(complexity_line: str) -> Tuple[str, str]:
    """
    Best-effort heuristics to map free-form complexity text to our tier set.

    Returns:
      (time_tier, space_tier) as strings for later mapping or UNKNOWN.
    """
    t = (complexity_line or "").lower()
    # Space tier is often in the same sentence; we keep it coarse.
    def map_time() -> str:
        if "2^" in t or "2**" in t or "2^n" in t or "exponential" in t:
            return "O(2^n) or higher"
        if "n log n" in t or "n*log" in t or "nlog" in t:
            return "O(n log n)"
        if "log n" in t:
            return "O(log n)"
        if "n^3" in t or "n3" in t:
            return "O(n^3)"
        if "n^2" in t or "n2" in t:
            return "O(n^2)"
        if "o(n)" in t or "o(n)" in t:
            return "O(n)"
        if "o(1)" in t or "constant" in t:
            return "O(1)"
        return "unknown"

    # Space tier: detect "space O(...)" if present.
    if "space" in t:
        space = t.split("space", 1)[-1]
    else:
        space = ""

    def map_space() -> str:
        s = space
        if "log n" in s:
            return "O(log n)"
        if "n^2" in s or "n2" in s:
            return "O(n^2)"
        if "n^3" in s or "n3" in s:
            return "O(n^3)"
        if "o(1)" in s or "constant" in s:
            return "O(1)"
        if "o(n log n)" in s:
            return "O(n log n)"
        if "o(n)" in s:
            return "O(n)"
        return map_time()

    return map_time(), map_space()


def _extract_code_fence(text: str) -> str:
    """
    Extract the first fenced code block.

    If a structured skills template exists, we prefer the code block under
    the "### Snippet" section; otherwise we fall back to the first code
    fence in the whole document.
    """
    search_text = text
    if "### Snippet" in text:
        idx = text.find("### Snippet")
        search_text = text[idx:]

    m = re.search(r"```(?:[a-zA-Z0-9_+-]+)?\\n(.*?)```", search_text, flags=re.S)
    if not m:
        return ""
    return m.group(1).rstrip() + "\n"


def _infer_complexity_tier_from_blob(blob: str) -> str:
    """
    Infer a ComplexityTier string from free-form complexity text.
    """
    t = (blob or "").lower()
    if "2^" in t or "2**" in t or "2^n" in t or "exponential" in t:
        return "O(2^n) or higher"
    if "n log n" in t or "n*log" in t or "nlog" in t:
        return "O(n log n)"
    if "log n" in t:
        return "O(log n)"
    if "n^3" in t or "n3" in t:
        return "O(n^3)"
    if "n^2" in t or "n2" in t:
        return "O(n^2)"
    if "o(n)" in t:
        return "O(n)"
    if "o(1)" in t or "constant" in t:
        return "O(1)"
    if "o(n log n)" in t:
        return "O(n log n)"
    if "o(2^" in t:
        return "O(2^n) or higher"
    return "unknown"


def _infer_skill_complexity_from_alt_markdown(content: str) -> Tuple[str, str]:
    """
    Fallback complexity inference for skills that use a C-style comment
    header with lines like "* Complexity:" and "*   - Worst Time: O(...)".
    """
    lines = content.splitlines()
    worst_time = ""
    avg_time = ""
    space = ""
    for line in lines:
        s = line.strip()
        if "worst time" in s.lower() and "o(" in s.lower():
            worst_time = s
        elif "average time" in s.lower() and "o(" in s.lower():
            avg_time = s
        elif "space" in s.lower() and "o(" in s.lower():
            space = s

    if worst_time:
        time_blob = worst_time
    elif avg_time:
        time_blob = avg_time
    else:
        # Last resort: use first O(...) occurrence in the file.
        time_blob = next((ln for ln in lines if "o(" in ln.lower()), "")

    time_tier = _infer_complexity_tier_from_blob(time_blob)
    space_tier = _infer_complexity_tier_from_blob(space)
    return time_tier, space_tier


def _infer_function_block_tags(role: str, problem_tags: Sequence[str]) -> List[str]:
    """
    Infer FunctionBlock.tags by checking whether the canonicalised tag token
    appears inside the canonicalised role text.
    """
    if not role:
        return []
    cr = canonicalize_text(role)
    out: List[str] = []
    for t in problem_tags:
        ct = canonicalize_tag(t)
        if not ct:
            continue
        # Compare on both underscore and space forms.
        token_underscore = ct
        token_space = ct.replace("_", " ")
        if token_underscore in cr.replace("_", " ") or token_space in cr:
            out.append(ct)
    # Deduplicate while preserving order.
    seen: set[str] = set()
    dedup: List[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            dedup.append(t)
    return dedup


@dataclass(frozen=True)
class SkillGraphDataPaths:
    """
    Paths for building a graph from storage.
    """

    logic_dir: Path
    skills_dir: Path
    logic_glob: str = "pipeline_both_solutions_with_logic_*.jsonl"
    # If provided, use these files instead of (logic_dir / logic_glob).
    # Useful when the dataset is a single large jsonl (e.g. solvita_logic_train.jsonl).
    logic_files: Optional[Sequence[Path]] = None
    # Kept for backward compatibility but no longer used for Q loading.
    q_jsonl: Optional[Path] = None


class SkillGraphDataLoader:
    """
    Streaming loader for Q / M / S nodes and a graph builder.
    """

    def __init__(self, paths: SkillGraphDataPaths, progress_every: Optional[int] = None) -> None:
        self.paths = paths
        if progress_every is not None:
            self._progress_every = max(0, int(progress_every))
        else:
            self._progress_every = int(os.environ.get("SOLVITA_PROGRESS_EVERY", "2000"))
        self._expect_q = int(os.environ.get("SOLVITA_EXPECT_Q", "0")) or None
        self._expect_m = int(os.environ.get("SOLVITA_EXPECT_M", "0")) or None
        self._expect_s = int(os.environ.get("SOLVITA_EXPECT_S", "0")) or None

    def _maybe_log_progress(self, label: str, count: int, extra: str = "") -> None:
        every = self._progress_every
        if every > 0 and count > 0 and (count % every == 0):
            expect = None
            if label == "Q":
                expect = self._expect_q
            elif label == "M":
                expect = self._expect_m
            elif label == "S":
                expect = self._expect_s
            if expect:
                pct = count * 100.0 / expect
                logger.info(
                    "%s progress: %d/%d (%.2f%%)%s",
                    label,
                    count,
                    expect,
                    pct,
                    f" {extra}" if extra else "",
                )
            else:
                logger.info("%s progress: %d%s", label, count, f" {extra}" if extra else "")

    def _iter_logic_files(self) -> List[Path]:
        if self.paths.logic_files:
            return [Path(p) for p in self.paths.logic_files]
        return sorted(self.paths.logic_dir.glob(self.paths.logic_glob))

    # ------------------------------------------------------------------
    # Q layer
    # ------------------------------------------------------------------

    def iter_q_nodes(
        self,
        limit: Optional[int] = None,
        q_problem_id_whitelist: Optional[set[str]] = None,
    ) -> Iterator[QNode]:
        """
        Stream lightweight QNode objects directly from logic files.

        QNode fields intentionally kept minimal:
          - problem_id
          - description
          - tags
        """
        count = 0
        seen_problem_ids: set[str] = set()
        logic_files = self._iter_logic_files()
        for lp in logic_files:
            if not lp.exists():
                continue
            with lp.open("r", encoding="utf-8") as f:
                for line in f:
                    if limit is not None and count >= limit:
                        return
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    q_id = str(record.get("id", ""))
                    if not q_id:
                        continue
                    if q_id in seen_problem_ids:
                        continue
                    if q_problem_id_whitelist is not None and q_id not in q_problem_id_whitelist:
                        continue

                    tags = canonicalize_tag_set(record.get("tags", []))
                    tags_l1 = canonicalize_tag_set(record.get("tags_level1", []))
                    raw_l2 = record.get("tags_level2", [])
                    if isinstance(raw_l2, str):
                        parts = [x.strip() for x in raw_l2.split(",") if x.strip()]
                    elif isinstance(raw_l2, list):
                        parts = [str(x).strip() for x in raw_l2 if str(x).strip()]
                    else:
                        parts = []
                    tags_l2 = canonicalize_tag_set(parts)
                    raw_desc = str(record.get("description", "") or "")
                    abs_desc = str(record.get("abstract_description", "") or "")
                    _cs_list = record.get("correct_solutions")
                    if isinstance(_cs_list, list) and _cs_list:
                        _correct: List[str] = [str(s) for s in _cs_list if s is not None and str(s).strip()]
                    else:
                        _one = record.get("correct_solution")
                        _correct = [str(_one)] if isinstance(_one, str) and _one.strip() else []
                    q = QNode(
                        problem_id=q_id,
                        abstract_description=abs_desc or raw_desc,
                        tags=sorted(tags),
                        tags_level1=sorted(tags_l1),
                        tags_level2=sorted(tags_l2),
                        correct_solutions=_correct,
                        metadata={
                            "dataset_raw": record.get("dataset"),
                            "q_source": "logic",
                            "logic_file": str(lp),
                            "description": raw_desc,
                        },
                    )
                    seen_problem_ids.add(q_id)
                    yield q
                    count += 1
                    self._maybe_log_progress("Q", count, extra=f"last_id={q_id}")

    # ------------------------------------------------------------------
    # S layer
    # ------------------------------------------------------------------

    def iter_s_nodes(
        self,
        limit: Optional[int] = None,
    ) -> Iterator[SNode]:
        """
        Stream SNode objects from skills/*.md.
        """
        count = 0
        for md_path in sorted(self.paths.skills_dir.glob("*.md")):
            if limit is not None and count >= limit:
                break
            try:
                content = md_path.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning("Failed to read skill md %s: %s", md_path, exc)
                continue

            # Try structured template first (quick_sort-style).
            skill_id: Optional[str] = None
            tags: List[str] = []
            complexity_line: str = ""
            description_parts: List[str] = []

            for line in content.splitlines():
                m = _SKILL_HEADER_RE.match(line.strip())
                if m and skill_id is None:
                    skill_id = m.group(1).strip()
                    continue

                m = _SKILL_TAG_RE.match(line.strip())
                if m:
                    tags.append(m.group(1).strip())
                    continue

                m = _SKILL_COMPLEXITY_RE.match(line.strip())
                if m:
                    complexity_line = m.group(1).strip()
                    continue

                if line.strip().startswith("- Applicable_when:"):
                    description_parts.append(line.split(":", 1)[-1].strip())
                if line.strip().startswith("- Pitfalls:"):
                    description_parts.append(line.split(":", 1)[-1].strip())

            # Fallback template: C-style comment header (many skills in this repo).
            if skill_id is None:
                skill_id = md_path.stem
                for line in content.splitlines():
                    m = _COMMENT_TAG_RE.match(line)
                    if m:
                        raw = m.group(1).strip()
                        # Tags are often comma-separated in a single line.
                        for part in raw.split(","):
                            tags.append(part.strip())

                in_desc = False
                desc_lines: List[str] = []
                for line in content.splitlines():
                    if not in_desc:
                        dm = _COMMENT_DESCRIPTION_RE.match(line)
                        if dm:
                            in_desc = True
                            first = dm.group(1).strip()
                            if first:
                                desc_lines.append(first)
                        continue
                    # Stop at the end of the big comment block.
                    if "*/" in line:
                        break
                    # Keep bullet-like lines inside the comment.
                    s = line.strip()
                    if s.startswith("*"):
                        s = s.lstrip("*").strip()
                    if s:
                        desc_lines.append(s)

                if desc_lines:
                    description_parts = desc_lines[:10]

                time_tier, space_tier = _infer_skill_complexity_from_alt_markdown(content)
            else:
                time_tier, space_tier = _infer_skill_complexity_tiers(complexity_line)

            # Extract code template from either style.
            snippet_code = _extract_code_fence(content)
            stags = canonicalize_tag_set(tags)

            try:
                ctime = ComplexityTier(time_tier)
            except ValueError:
                ctime = ComplexityTier.UNKNOWN
            try:
                cspace = ComplexityTier(space_tier)
            except ValueError:
                cspace = ComplexityTier.UNKNOWN

            node = SNode(
                skill_id=skill_id,
                title=skill_id,
                description="; ".join(description_parts) if description_parts else content[:200],
                tags=sorted(stags),
                code_template=snippet_code,
                complexity_time=ctime,
                complexity_space=cspace,
                source_url=None,
                node_id=None,
                metadata={
                    "path": str(md_path),
                    "complexity_raw": complexity_line,
                },
            )
            yield node
            count += 1
            self._maybe_log_progress("S", count, extra=f"last_skill={skill_id}")

    # ------------------------------------------------------------------
    # M layer
    # ------------------------------------------------------------------

    def iter_m_nodes(
        self,
        qnode_id_by_problem_id: Dict[str, str],
        limit: Optional[int] = None,
        q_problem_id_whitelist: Optional[set[str]] = None,
    ) -> Iterator[MNode]:
        """
        Stream MNode objects from logic_copy/pipeline_both_solutions_with_logic_*.jsonl.
        """
        count = 0
        logic_files = self._iter_logic_files()
        for lp in logic_files:
            if not lp.exists():
                continue
            with lp.open("r", encoding="utf-8") as f:
                for line in f:
                    if limit is not None and count >= limit:
                        return
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    q_problem_id = str(record.get("id", ""))
                    if not q_problem_id:
                        continue
                    if q_problem_id_whitelist is not None and q_problem_id not in q_problem_id_whitelist:
                        continue
                    qnode_id = qnode_id_by_problem_id.get(q_problem_id)
                    if qnode_id is None:
                        continue

                    tags = canonicalize_tag_set(record.get("tags", []))
                    la = record.get("logic_analysis") or {}
                    if not isinstance(la, dict):
                        # Some records may contain string placeholders like "[API Error: ...]".
                        logger.warning(
                            "Skipping record %s: logic_analysis is not an object (type=%s)",
                            record.get("id"),
                            type(la).__name__,
                        )
                        continue
                    requirements = la.get("requirements", []) or []
                    fn_blocks = la.get("function_blocks", []) or []
                    sub_dag = la.get("sub_problem_dag") or {}
                    block_to_sub = la.get("block_to_subproblem", []) or []

                    # -------- analysis MNode (correct_solution_logic_chain) --------
                    function_blocks: List[FunctionBlock] = []
                    for b in fn_blocks:
                        block_id = str(b.get("id"))
                        name_or_label = str(b.get("name_or_label", ""))
                        role = str(b.get("role", ""))
                        inferred_tags = _infer_function_block_tags(role, list(tags))
                        function_blocks.append(
                            FunctionBlock(
                                id=block_id,
                                name_or_label=name_or_label,
                                role=role,
                                tags=inferred_tags,
                                code="",
                                metadata={},
                            )
                        )

                    subproblems: List[SubProblem] = []
                    for sn in (sub_dag.get("nodes", []) or []):
                        subproblems.append(
                            SubProblem(
                                id=str(sn.get("id")),
                                description=str(sn.get("description", "")),
                                metadata={},
                            )
                        )

                    dag_links: List[DAGLink] = []
                    for ed in (sub_dag.get("edges", []) or []):
                        dag_links.append(
                            DAGLink.new(
                                from_id=str(ed.get("from_id")),
                                to_id=str(ed.get("to_id")),
                            )
                        )

                    block_to_subproblem: List[BlockToSubproblem] = []
                    for m in block_to_sub:
                        block_to_subproblem.append(
                            BlockToSubproblem(
                                block_id=str(m.get("block_id")),
                                subproblem_id=str(m.get("subproblem_id")),
                                rationale=m.get("rationale"),
                            )
                        )

                    analysis_mnode = MNode(
                        source_problem_id=qnode_id,
                        kind="analysis",
                        function_blocks=function_blocks,
                        subproblems=subproblems,
                        dag_links=dag_links,
                        block_to_subproblem=block_to_subproblem,
                        requirements=requirements,
                        error_experiences=[],
                        node_id=None,
                        metadata={
                            "logic_file": str(lp),
                            "logic_record_id": q_problem_id,
                        },
                    )
                    count += 1
                    yield analysis_mnode
                    self._maybe_log_progress("M", count, extra=f"last_q={q_problem_id} kind=analysis")

                    # -------- contrast MNodes (correct_vs_incorrect_logic_diff) --------
                    for contrast_item in (record.get("logic_contrasts") or []):
                        incorrect_index = contrast_item.get("incorrect_index")
                        logic_contrast = contrast_item.get("logic_contrast") or {}
                        if not isinstance(logic_contrast, dict):
                            logger.warning(
                                "Skipping contrast for %s (incorrect_index=%s): logic_contrast is not an object (type=%s)",
                                q_problem_id,
                                incorrect_index,
                                type(logic_contrast).__name__,
                            )
                            continue

                        exp = ErrorExperience.new(
                            incorrect_sol_id=f"inc_{incorrect_index}",
                            block_differences=[
                                BlockDifference(
                                    block_name=bd.get("block_name"),
                                    subproblem_name=bd.get("subproblem_name"),
                                    error_type=str(bd.get("error_type", "")),
                                    error_analysis=str(bd.get("error_analysis", "")),
                                    correct_rationale=str(bd.get("correct_rationale", "")),
                                    prevention_guideline=str(bd.get("prevention_guideline", "")),
                                )
                                for bd in (logic_contrast.get("block_differences") or [])
                            ],
                            global_diagnosis=logic_contrast.get("global_diagnosis"),
                            requirements=logic_contrast.get("requirements", []) or [],
                        )

                        # Contrast nodes keep only blocks mentioned in block_differences.
                        # These blocks are copied from the analysis MNode (same id/name/role/tags)
                        # so their downstream MS edges can be mirrored during initialization.
                        block_names = [
                            (bd.block_name or "").strip()
                            for bd in exp.block_differences
                            if (bd.block_name or "").strip()
                        ]
                        seen_names: set[str] = set()
                        contrast_blocks: List[FunctionBlock] = []
                        for bname in block_names:
                            if bname in seen_names:
                                continue
                            seen_names.add(bname)
                            src_block = next(
                                (b for b in function_blocks if b.name_or_label == bname),
                                None,
                            )
                            if src_block is None:
                                continue
                            contrast_blocks.append(
                                FunctionBlock(
                                    id=src_block.id,
                                    name_or_label=src_block.name_or_label,
                                    role=src_block.role,
                                    tags=list(src_block.tags),
                                    code=src_block.code,
                                    metadata={**(src_block.metadata or {}), "copied_from_analysis": "true"},
                                )
                            )

                        contrast_mnode = MNode(
                            source_problem_id=qnode_id,
                            kind="contrast",
                            incorrect_index=incorrect_index if isinstance(incorrect_index, int) else None,
                            # Keep only blocks referenced by contrast diagnostics.
                            function_blocks=contrast_blocks,
                            subproblems=[],
                            dag_links=[],
                            block_to_subproblem=[],
                            requirements=logic_contrast.get("requirements", []) or [],
                            error_experiences=[exp],
                            node_id=None,
                            metadata={
                                "logic_file": str(lp),
                                "logic_record_id": q_problem_id,
                                "incorrect_index": incorrect_index,
                            },
                        )
                        yield contrast_mnode
                        count += 1
                        self._maybe_log_progress("M", count, extra=f"last_q={q_problem_id} kind=contrast")

    # ------------------------------------------------------------------
    # Graph builder
    # ------------------------------------------------------------------

    def build_graph(
        self,
        edge_initializer: EdgeWeightInitializer,
        q_limit: Optional[int] = None,
        m_limit: Optional[int] = None,
        s_limit: Optional[int] = None,
        q_problem_id_whitelist: Optional[set[str]] = None,
    ) -> SolvitaSkillGraph:
        """
        Build a fully initialised graph (including M->S edge weights).
        """
        t_all = time.perf_counter()
        graph = SolvitaSkillGraph()

        qnode_id_by_problem_id: Dict[str, str] = {}
        # 1) Load Q nodes
        logger.info("build_graph phase 1/5: loading Q nodes...")
        t0 = time.perf_counter()
        for q in self.iter_q_nodes(limit=q_limit, q_problem_id_whitelist=q_problem_id_whitelist):
            graph.add_node(q)
            qnode_id_by_problem_id[q.problem_id] = q.node_id
        logger.info(
            "build_graph phase 1/5: Q nodes=%d (%.2fs)",
            len(graph.q_nodes),
            time.perf_counter() - t0,
        )

        # 2) Load M nodes
        logger.info("build_graph phase 2/5: loading M nodes...")
        t0 = time.perf_counter()
        m_nodes: List[MNode] = []
        for m in self.iter_m_nodes(
            qnode_id_by_problem_id=qnode_id_by_problem_id,
            limit=m_limit,
            q_problem_id_whitelist=q_problem_id_whitelist,
        ):
            graph.add_node(m)
            m_nodes.append(m)
        logger.info(
            "build_graph phase 2/5: M nodes=%d (%.2fs)",
            len(m_nodes),
            time.perf_counter() - t0,
        )

        # 3) Add QM edges (see qm_init_weights.qm_weights_per_m_kind)
        t_qm = time.perf_counter()
        m_by_q: Dict[str, List[MNode]] = {}
        for m in m_nodes:
            m_by_q.setdefault(m.source_problem_id, []).append(m)

        for q_id, lst in m_by_q.items():
            analysis = [m for m in lst if getattr(m, "kind", "analysis") == "analysis"]
            contrast = [m for m in lst if getattr(m, "kind", "analysis") == "contrast"]

            w_analysis_each, w_contrast_each = qm_weights_per_m_kind(
                len(analysis), len(contrast)
            )

            for m in analysis:
                graph.add_edge(
                    QMEdge(
                        source_id=q_id,
                        target_id=m.node_id,
                        weight=w_analysis_each,
                        trainable=True,
                    )
                )
            for m in contrast:
                graph.add_edge(
                    QMEdge(
                        source_id=q_id,
                        target_id=m.node_id,
                        weight=w_contrast_each,
                        trainable=True,
                    )
                )
        logger.info(
            "build_graph phase 3/5: QM edges=%d (%.2fs)",
            len(graph.qm_edges),
            time.perf_counter() - t_qm,
        )

        # 4) Load S nodes
        logger.info("build_graph phase 4/5: loading S nodes from skills/*.md ...")
        t0 = time.perf_counter()
        for s in self.iter_s_nodes(limit=s_limit):
            graph.add_node(s)
        logger.info(
            "build_graph phase 4/5: S nodes=%d (%.2fs)",
            len(graph.s_nodes),
            time.perf_counter() - t0,
        )

        # 5) Initialise MS edges
        logger.info(
            "build_graph phase 5/5: MS edge init (skills embedding + per-block scoring; often the slowest step)..."
        )
        t0 = time.perf_counter()
        edge_initializer.initialize_all_ms_edges(graph)
        logger.info(
            "build_graph phase 5/5: MS edges=%d (%.2fs)",
            len(graph.ms_edges),
            time.perf_counter() - t0,
        )

        logger.info(
            "build_graph complete: total %.2fs | stats=%s",
            time.perf_counter() - t_all,
            graph.stats(),
        )
        return graph

