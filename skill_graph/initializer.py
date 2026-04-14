"""
Edge weight initialisation for the M → S layer.

Required rule in this project:
for each analysis block in an M-node, connect to all skills, score each edge by
semantic similarity between:
  - block.role
  - skill.tags concatenated with skill.description
keep only top-k edges for that block, then normalise retained weights to sum to
``MS_GROUP_WEIGHT_SUM`` (default 8, see :mod:`skill_graph.graph`).
"""

from __future__ import annotations

import logging
import math
import time
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Set, Tuple

import numpy as np

from .blocks import FunctionBlock
from .edges import MSEdge
from .graph import MS_GROUP_WEIGHT_SUM, SolvitaSkillGraph
from .nodes import MNode, SNode
from .types import BlockId, NodeId
from .tag_utils import canonicalize_tag_set

logger = logging.getLogger(__name__)

# Tag-embedding function signature: (tag: str) → vector (list of float)
TagEmbedder = Callable[[str], List[float]]


class SimilarityMetric(Enum):
    EMBEDDING = auto()
    JACCARD = auto()
    OVERLAP = auto()
    COSINE = auto()


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _overlap(a: Set[str], b: Set[str]) -> float:
    denom = min(len(a), len(b))
    if denom == 0:
        return 0.0
    return len(a & b) / denom


def _cosine_tag(a: Set[str], b: Set[str], embedder: TagEmbedder) -> float:
    def avg_embed(tags: Set[str]) -> List[float]:
        vecs = [embedder(t) for t in tags]
        if not vecs:
            return []
        dim = len(vecs[0])
        return [sum(v[i] for v in vecs) / len(vecs) for i in range(dim)]

    va, vb = avg_embed(a), avg_embed(b)
    if not va or not vb or len(va) != len(vb):
        return _jaccard(a, b)

    dot = sum(x * y for x, y in zip(va, vb))
    norm_a = math.sqrt(sum(x * x for x in va))
    norm_b = math.sqrt(sum(y * y for y in vb))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class EdgeWeightInitializer:
    """
    Computes initial M → S edge weights.

    Parameters
    ----------
    metric:
        ``SimilarityMetric.EMBEDDING`` computes semantic similarity between
        ``block.role`` and ``(skill.tags + skill.description)`` text.
    embedder:
        仅 ``COSINE`` 旧模式需要。
    top_k_per_block:
        Retain only top-k skills per block before normalisation.
    tag_weight / logic_weight / max_code_chars:
        Kept for backward compatibility and ignored by this initializer mode.
    min_nonzero_weight:
        正分下界，避免数值下溢。
    create_zero_edges:
        若为 False，得分为 0 的 (block, S) 不建边。
    ms_block_log_step:
        MS 初始化时每隔多少个 (M, block) 打一行进度；``None`` 表示自动（约 40 行）；
        ``0`` 表示关闭（仍保留技能批量 embedding 的前后日志）。
    """

    def __init__(
        self,
        metric: SimilarityMetric = SimilarityMetric.EMBEDDING,
        embedder: Optional[TagEmbedder] = None,
        top_k_per_block: int = 16,
        tag_weight: float = 0.5,
        logic_weight: float = 0.5,
        max_code_chars: int = 3000,
        min_nonzero_weight: float = 1e-6,
        create_zero_edges: bool = True,
        ms_block_log_step: Optional[int] = None,
    ) -> None:
        tw, lw = float(tag_weight), float(logic_weight)
        if abs(tw + lw - 1.0) > 1e-6:
            raise ValueError("tag_weight + logic_weight must equal 1.0")
        self.metric = metric
        self.embedder = embedder
        self.top_k_per_block = max(1, int(top_k_per_block))
        self.tag_weight = tw
        self.logic_weight = lw
        self.max_code_chars = int(max_code_chars)
        self.min_nonzero_weight = min_nonzero_weight
        self.create_zero_edges = create_zero_edges
        self._ms_block_log_step: Optional[int] = ms_block_log_step
        # EMBEDDING batch cache (per graph build)
        self._skill_ids_order: Optional[List[NodeId]] = None
        self._skill_text_norm: Optional[np.ndarray] = None

    def clear_skill_embedding_cache(self) -> None:
        self._skill_ids_order = None
        self._skill_text_norm = None

    def _warm_skill_embedding_cache(self, graph: SolvitaSkillGraph) -> None:
        if self.metric != SimilarityMetric.EMBEDDING:
            return
        if self._skill_text_norm is not None and self._skill_ids_order is not None:
            return
        from . import question_similarity as qs

        s_nodes = list(graph.s_nodes.values())
        if not s_nodes:
            self._skill_ids_order = []
            self._skill_text_norm = np.zeros((0, 0), dtype=np.float64)
            return
        self._skill_ids_order = [s.node_id for s in s_nodes]
        skill_texts = []
        for s in s_nodes:
            tags_text = " ".join(sorted(canonicalize_tag_set(s.tags)))
            desc = s.description or ""
            skill_texts.append((tags_text + "\n" + desc).strip() or "[no_skill_text]")
        n_skill = len(skill_texts)
        logger.info(
            "MS init (EMBEDDING): encoding %d skill text vectors (batch sentence-transformers; may take a while)",
            n_skill,
        )
        t0 = time.perf_counter()
        self._skill_text_norm = qs.encode_l2_normalized_batch(skill_texts)
        elapsed = time.perf_counter() - t0
        logger.info(
            "MS init (EMBEDDING): skill vectors done in %.2fs (dim=%s)",
            elapsed,
            getattr(self._skill_text_norm, "shape", ()),
        )
        if self._skill_text_norm.shape[0] != len(s_nodes):
            raise RuntimeError("skill embedding row count mismatch")

    def compute_similarity(self, block: FunctionBlock, skill: SNode) -> float:
        """Single-pair similarity for non-batch paths."""
        if self.metric == SimilarityMetric.EMBEDDING:
            from . import question_similarity as qs
            block_text = (block.role or "").strip() or "[no_role]"
            skill_text = (
                " ".join(sorted(canonicalize_tag_set(skill.tags)))
                + "\n"
                + (skill.description or "")
            ).strip() or "[no_skill_text]"
            return qs.problem_text_similarity(block_text, skill_text)

        a = canonicalize_tag_set(block.tags)
        b = canonicalize_tag_set(skill.tags)
        if not (a & b):
            return 0.0

        if self.metric == SimilarityMetric.JACCARD:
            return _jaccard(a, b)
        if self.metric == SimilarityMetric.OVERLAP:
            return _overlap(a, b)
        if self.metric == SimilarityMetric.COSINE:
            return _cosine_tag(a, b, self.embedder)  # type: ignore[arg-type]
        return _jaccard(a, b)

    def initialize_block_edges(
        self,
        graph: SolvitaSkillGraph,
        m_node: MNode,
        block: FunctionBlock,
    ) -> List[MSEdge]:
        raw_scores: List[Tuple[NodeId, float]] = []

        if self.metric == SimilarityMetric.EMBEDDING:
            self._warm_skill_embedding_cache(graph)
            assert self._skill_ids_order is not None
            assert self._skill_text_norm is not None
            if not self._skill_ids_order:
                return []

            from . import question_similarity as qs

            block_text = (block.role or "").strip() or "[no_role]"
            b_vec = qs.encode_l2_normalized_batch([block_text])[0]
            sims = np.clip(self._skill_text_norm @ b_vec, 0.0, 1.0)

            for i, s_id in enumerate(self._skill_ids_order):
                score = float(sims[i])
                if score > 0.0:
                    raw_scores.append(
                        (s_id, max(score, self.min_nonzero_weight))
                    )
                elif self.create_zero_edges:
                    raw_scores.append((s_id, 0.0))
        else:
            for s_id, snode in graph.s_nodes.items():
                score = self.compute_similarity(block, snode)
                if score > 0.0:
                    raw_scores.append((s_id, max(score, self.min_nonzero_weight)))
                elif self.create_zero_edges:
                    raw_scores.append((s_id, 0.0))

        # Keep only top-k edges per block by score.
        raw_scores.sort(key=lambda x: x[1], reverse=True)
        raw_scores = raw_scores[: self.top_k_per_block]
        total = sum(s for _, s in raw_scores)

        created: List[MSEdge] = []
        for s_id, score in raw_scores:
            norm_w = (score / total) * MS_GROUP_WEIGHT_SUM if total > 0.0 else 0.0
            edge = MSEdge(
                source_id=m_node.node_id,
                target_id=s_id,
                block_id=block.block_id,
                weight=norm_w,
                initialised=True,
            )
            try:
                graph.add_edge(edge)
                created.append(edge)
            except ValueError as exc:
                logger.warning("Skipping edge: %s", exc)

        return created

    def initialize_m_node(
        self,
        graph: SolvitaSkillGraph,
        m_node: MNode,
    ) -> int:
        total_created = 0
        for block in m_node.function_blocks:
            edges = self.initialize_block_edges(graph, m_node, block)
            total_created += len(edges)
        return total_created

    def initialize_all_ms_edges(self, graph: SolvitaSkillGraph) -> int:
        if not graph.s_nodes:
            logger.warning(
                "No S-nodes found in graph; MS edge initialisation skipped."
            )
            return 0

        if self.metric == SimilarityMetric.EMBEDDING:
            self.clear_skill_embedding_cache()

        total = 0
        analysis_nodes = [m for m in graph.m_nodes.values() if getattr(m, "kind", "analysis") != "contrast"]
        contrast_nodes = [m for m in graph.m_nodes.values() if getattr(m, "kind", "analysis") == "contrast"]

        # 1) Initialize analysis nodes (log progress: each block encodes role + scores all skills).
        total_blocks = sum(len(m.function_blocks) for m in analysis_nodes)
        cfg_step = self._ms_block_log_step
        if cfg_step is None:
            log_step = max(1, (total_blocks + 39) // 40) if total_blocks else 1
        elif cfg_step <= 0:
            log_step = 0
        else:
            log_step = int(cfg_step)

        t_blocks = time.perf_counter()
        blk_done = 0
        logger.info(
            "MS init: %d analysis M-nodes, %d function blocks (embedding metric will warm cache on first block)",
            len(analysis_nodes),
            total_blocks,
        )
        for m_node in analysis_nodes:
            for block in m_node.function_blocks:
                n_e = len(self.initialize_block_edges(graph, m_node, block))
                total += n_e
                blk_done += 1
                if log_step and (blk_done % log_step == 0 or blk_done == total_blocks):
                    logger.info(
                        "MS init progress: blocks %d/%d, edges_created=%d, elapsed=%.2fs",
                        blk_done,
                        total_blocks,
                        total,
                        time.perf_counter() - t_blocks,
                    )

        # 2) For contrast nodes, copy MS edges/weights from same-problem analysis blocks.
        #    Rule: locate the corresponding block in analysis and mirror its skill edges.
        analysis_by_q: Dict[NodeId, MNode] = {}
        for m in analysis_nodes:
            analysis_by_q.setdefault(m.source_problem_id, m)
        if contrast_nodes:
            logger.info("MS init: mirroring edges for %d contrast M-nodes...", len(contrast_nodes))
        t_con = time.perf_counter()
        for m in contrast_nodes:
            src = analysis_by_q.get(m.source_problem_id)
            if src is None:
                continue
            total += self._copy_ms_from_analysis(graph, src, m)
        if contrast_nodes:
            logger.info(
                "MS init: contrast mirror done in %.2fs (extra edges this phase included in total below)",
                time.perf_counter() - t_con,
            )

        if self.metric == SimilarityMetric.EMBEDDING:
            self.clear_skill_embedding_cache()

        logger.info(
            "Initialised %d MS edges across %d M-nodes.",
            total,
            len(graph.m_nodes),
        )
        return total

    def _copy_ms_from_analysis(
        self,
        graph: SolvitaSkillGraph,
        analysis_m: MNode,
        contrast_m: MNode,
    ) -> int:
        """
        Copy MS edges from analysis M to contrast M for matched block_ids.
        """
        created = 0
        for b in contrast_m.function_blocks:
            src_edges = graph.all_ms_edges_of_block(analysis_m.node_id, b.block_id)
            if not src_edges:
                continue
            for se in src_edges:
                edge = MSEdge(
                    source_id=contrast_m.node_id,
                    target_id=se.target_id,
                    block_id=b.block_id,
                    weight=se.weight,
                    initialised=True,
                )
                try:
                    graph.add_edge(edge)
                    created += 1
                except ValueError:
                    # Duplicate edge tuple can occur on repeated init, ignore.
                    continue
            graph.normalize_ms_weights(contrast_m.node_id, b.block_id)
        return created
