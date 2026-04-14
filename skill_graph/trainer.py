"""
Reinforcement-learning trainer for the M → S edge weights.

Design
------
The training signal is the solver's outcome after receiving the
``SolverAugmentation``.  Positive outcomes increase the weights of the MS
edges that contributed to the recommended skills; negative outcomes decrease
them.

Algorithm  (policy-gradient / REINFORCE style on edge weights)
------
For each training episode:
    reward  = reward_fn(outcome)
    for each (m_node, block) group that contributed to a recommendation:
        for each MSEdge in that group:
            Δw = lr * reward * edge.weight  (proportional update)
        renormalise the group so weights sum to MS_GROUP_WEIGHT_SUM (default 8)

Entropy regularisation (optional) discourages weight collapse.

The ``TrainingEpisode`` dataclass captures one complete solve attempt so
episodes can be batched or replayed.

After training, call ``graph.prune_ms_edges(threshold)`` to remove
low-weight edges.

Contrastive signal (与草图一致)
------------------------------
``update_from_contrastive(ep_with, ep_without)`` 使用 :math:`\\Delta R = R_{with}-R_{without}`
作为标量优势，仅更新「带图增强」轨迹中出现的 (M, block) 组上的 MS 边权；
对应策略梯度形式 :math:`\\nabla \\mathcal{L} \\propto -\\Delta R \\cdot \\nabla\\log\\pi`
的简化实现（``\\pi`` 由边上的归一化权重近似）。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Set, Tuple

from .edges import MSEdge, QMEdge
from .graph import MS_GROUP_WEIGHT_SUM, SolvitaSkillGraph
from .inference import PlannerInput, SkillRecommendation, SolverAugmentation
from .path_scoring import softmax_skill_distribution
from .types import BlockId, NodeId, Outcome

if TYPE_CHECKING:
    from .rl_rollout import SoftmaxRolloutResult

logger = logging.getLogger(__name__)

# Reward function signature: (outcome, pass_rate) → float
RewardFn = Callable[[Outcome, float], float]


# ---------------------------------------------------------------------------
# Default reward shaping  (mirrors the existing BanditPolicy convention)
# ---------------------------------------------------------------------------

def judging_reward_fn(outcome: Outcome, pass_rate: float = 1.0) -> float:
    """
    以本地评测的 **通过率** 作为奖励信号（你当前的设定）。

    - 主要信号：``reward = pass_rate``，范围 [0, 1]
    - 编译失败：强制给 0（validator 失败不应获得任何正向信号）

    与 ``submit_with_compile_retries`` 配合时：应仅在「某次生成已通过编译并完成测试」之后，
    再用 :func:`outcome_from_submission_result` 与 ``pass_rate`` 构造 episode；编译阶段的重试
    不应单独产生训练信号（最终仍失败则 ``Outcome.COMPILATION_ERROR``、reward=0）。

    备注：Outcome 仍保留用于日志 / case 分类（AC/WA/TLE/RE/CE），但不再参与 reward shaping。
    """
    if outcome == Outcome.COMPILATION_ERROR:
        return 0.0
    # Clamp for safety (callers may pass percentages or NaNs).
    try:
        x = float(pass_rate)
    except Exception:
        return 0.0
    if x != x:  # NaN
        return 0.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def default_reward_fn(outcome: Outcome, pass_rate: float = 1.0) -> float:
    """向后兼容别名，等价于 :func:`judging_reward_fn`。"""
    return judging_reward_fn(outcome, pass_rate)


def outcome_from_submission_result(result: Any) -> Outcome:
    """
    将本地评测 ``SubmissionResult`` 映射为 :class:`Outcome`（需 ``src.submission`` 在路径上）。

    典型用法：先用 ``submit_with_compile_retries`` 在编译通过后再跑测试，再将最终 ``result``
    映射为 ``Outcome``；仅在所有编译重试仍失败时才会得到 ``Outcome.COMPILATION_ERROR``。
    """
    try:
        from src.submission.core import SubmitStatus
    except ImportError as e:
        raise ImportError(
            "outcome_from_submission_result needs `src.submission` on PYTHONPATH (optional; training does not use it)."
        ) from e

    st = result.status
    if st == SubmitStatus.ACCEPTED:
        return Outcome.ACCEPTED
    if st == SubmitStatus.WRONG_ANSWER:
        return Outcome.WRONG_ANSWER
    if st == SubmitStatus.TIME_LIMIT:
        return Outcome.TIME_LIMIT
    if st == SubmitStatus.RUNTIME_ERROR:
        return Outcome.RUNTIME_ERROR
    if st == SubmitStatus.COMPILATION_ERROR:
        return Outcome.COMPILATION_ERROR
    if st in (SubmitStatus.NOT_SUPPORTED, SubmitStatus.SUBMIT_FAILED, SubmitStatus.PENDING):
        return Outcome.PARTIAL
    return Outcome.PARTIAL


# ---------------------------------------------------------------------------
# Episode record
# ---------------------------------------------------------------------------

@dataclass
class TrainingEpisode:
    """
    Records one complete solve attempt for later RL update.

    Fields
    ------
    planner_input:
        The input that was fed into the inference engine.
    augmentation:
        The ``SolverAugmentation`` the solver received.
    outcome:
        Final verdict from the sandbox.
    pass_rate:
        Fraction of test cases that passed (used for PARTIAL rewards).
    reward:
        Computed scalar reward (filled in by ``RLTrainer.compute_reward``).
    contributing_edges:
        MS edge IDs that influenced the recommendations in ``augmentation``.
        Populated by ``RLTrainer.extract_contributing_edges``.
    """
    planner_input:       PlannerInput
    augmentation:        SolverAugmentation
    outcome:             Outcome
    pass_rate:           float                = 1.0
    reward:              float                = 0.0
    contributing_edges:  List[str]            = field(default_factory=list)


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------

class RLTrainer:
    """
    Online RL trainer for MS edge weights.

    Parameters
    ----------
    graph:
        The skill graph whose MS edges will be trained.
    learning_rate:
        Step size for weight updates.
    entropy_coeff:
        Coefficient for entropy regularisation term.  Set to 0 to disable.
    reward_fn:
        Function mapping (Outcome, pass_rate) → float.
    clip_weight_min:
        Floor for edge weights after an update (prevents negatives).
    clip_weight_max:
        Ceiling for edge weights after an update.
    """

    def __init__(
        self,
        graph:          SolvitaSkillGraph,
        learning_rate:  float            = 0.01,
        entropy_coeff:  float            = 0.001,
        reward_fn:      RewardFn         = default_reward_fn,
        clip_weight_min: float           = 1e-8,
        clip_weight_max: float           = 1.0,
    ) -> None:
        self.graph           = graph
        self.learning_rate   = learning_rate
        self.entropy_coeff   = entropy_coeff
        self.reward_fn       = reward_fn
        self.clip_min        = clip_weight_min
        self.clip_max        = clip_weight_max
        self._episode_count  = 0

    def _ms_clip_max(self) -> float:
        """MS weights live on [0, MS_GROUP_WEIGHT_SUM]; keep clip ceiling consistent."""
        return max(self.clip_max, float(MS_GROUP_WEIGHT_SUM))

    # ------------------------------------------------------------------
    # Reward computation
    # ------------------------------------------------------------------

    def compute_reward(self, outcome: Outcome, pass_rate: float = 1.0) -> float:
        return self.reward_fn(outcome, pass_rate)

    # ------------------------------------------------------------------
    # Identify edges that participated in recommendations
    # ------------------------------------------------------------------

    def extract_contributing_edges(
        self, augmentation: SolverAugmentation
    ) -> List[str]:
        """
        Walk the ``SkillRecommendation.contributing_blocks`` list and return
        all MS edge IDs that led to skill recommendations above the threshold.
        """
        edge_ids: List[str] = []
        for rec in augmentation.required_skills:
            for m_id, block_id in rec.contributing_blocks:
                edge = self.graph.get_ms_edge(
                    m_id, rec.skill.node_id, block_id
                )
                if edge is not None:
                    edge_ids.append(edge.edge_id)
        return edge_ids

    # ------------------------------------------------------------------
    # Core weight update  (REINFORCE with baseline = 0)
    # ------------------------------------------------------------------

    def _update_qm_edge(self, q_id: NodeId, m_id: NodeId, delta_r: float) -> None:
        """Policy-gradient style nudge on a single QM edge (no simplex renormalisation)."""
        edge = self.graph.get_qm_edge(q_id, m_id)
        if edge is None or not getattr(edge, "trainable", True):
            return
        pg_grad = delta_r * edge.weight
        delta = self.learning_rate * pg_grad
        if self.entropy_coeff > 0.0 and edge.weight > 0.0:
            entropy_grad = -(math.log(edge.weight) + 1.0)
            delta += self.learning_rate * self.entropy_coeff * entropy_grad
        edge.weight = max(
            self.clip_min,
            min(self.clip_max, edge.weight + delta),
        )

    def _update_group(
        self,
        m_id:     NodeId,
        block_id: BlockId,
        reward:   float,
        active_edge_ids: set,
    ) -> None:
        """
        Update all MS edges in the (m_id, block_id) group.

        Active edges (those that contributed to recommendations) receive the
        full policy-gradient update.  Inactive edges receive the negative
        counterpart to preserve the normalisation invariant.
        """
        edges = self.graph.all_ms_edges_of_block(m_id, block_id)
        if not edges:
            return

        # Entropy gradient: ∂H/∂w_i = -(log w_i + 1)  — pushes weights away from extremes
        for edge in edges:
            if not edge.trainable:
                continue

            pg_grad = reward * edge.weight
            if edge.edge_id in active_edge_ids:
                delta = self.learning_rate * pg_grad
            else:
                delta = -self.learning_rate * pg_grad * 0.1

            if self.entropy_coeff > 0.0 and edge.weight > 0.0:
                entropy_grad = -(math.log(edge.weight) + 1.0)
                delta += self.learning_rate * self.entropy_coeff * entropy_grad

            edge.weight = max(
                self.clip_min,
                min(self._ms_clip_max(), edge.weight + delta),
            )

        # Renormalise so weights sum to MS_GROUP_WEIGHT_SUM
        self.graph.normalize_ms_weights(m_id, block_id)

    # ------------------------------------------------------------------
    # Public training step
    # ------------------------------------------------------------------

    def update(self, episode: TrainingEpisode) -> float:
        raise RuntimeError(
            "Heuristic MS update has been retired. "
            "Use update_from_contrastive_softmax_rollout_strict(...) with a SoftmaxRolloutResult."
        )

    def update_from_contrastive(
        self,
        episode_with_aug: TrainingEpisode,
        episode_without_aug: TrainingEpisode,
    ) -> Tuple[float, float, float]:
        raise RuntimeError(
            "Heuristic contrastive update has been retired. "
            "Use update_from_contrastive_softmax_rollout_strict(...) with a SoftmaxRolloutResult."
        )

    def update_from_contrastive_softmax_rollout(
        self,
        rollout: "SoftmaxRolloutResult",
        outcome_with: Outcome,
        pass_with: float,
        outcome_without: Outcome,
        pass_without: float,
    ) -> Tuple[float, float, float]:
        # Backward-compatible name, now strict by default.
        return self.update_from_contrastive_softmax_rollout_strict(
            rollout,
            outcome_with,
            pass_with,
            outcome_without,
            pass_without,
        )

    def update_from_contrastive_softmax_rollout_strict(
        self,
        rollout: "SoftmaxRolloutResult",
        outcome_with: Outcome,
        pass_with: float,
        outcome_without: Outcome,
        pass_without: float,
    ) -> Tuple[float, float, float]:
        """
        Strict REINFORCE-aligned update for the Figure logic (mk==selected skill sk):

            L = - E[ ΔR * log p(SampledSkills | q_new) ]
            ΔR = R_with - R_wo
            ∇_w L = -ΔR * ∇_w log p(...)

        Policy is π(s)=softmax(ρ(s)/T). We backpropagate through:

            ρ(s) = Σ Sim(q_new,q_i) * w_qm(i,j) * w_ms(j,k; block)

        Implementation notes:
        - We assume sampling is IID-with-replacement when using strict mode,
          so log p = Σ_t log π(a_t). (See rl_rollout.sample_with_replacement=True)
        - We compute the exact score-function gradient w.r.t ρ (softmax derivative),
          then apply chain rule to w_qm and w_ms by iterating the activated subgraph
          (candidate Qs → Ms → blocks → skills).
        - MS weights are renormalised per (m, block) group after updates (simplex).
        """
        r_with = self.compute_reward(outcome_with, pass_with)
        r_wo = self.compute_reward(outcome_without, pass_without)
        delta_r = r_with - r_wo
        self._episode_count += 1

        rho = rollout.rho or {}
        if not rho:
            return r_with, r_wo, delta_r

        # Recompute π from ρ/T to guarantee consistency.
        pi = softmax_skill_distribution(rho, temperature=rollout.temperature)

        # Counts of sampled skills (IID with replacement => Σ log π(a_t)).
        k = max(0, len(rollout.sampled_skill_ids))
        counts: Dict[NodeId, int] = {}
        for sid in rollout.sampled_skill_ids:
            counts[sid] = counts.get(sid, 0) + 1

        # Gradient of log-prob w.r.t rho(s):
        #   ∂/∂rho_s Σ_t log π(a_t) = (1/T) * (count_s - k * π_s)
        t = max(float(rollout.temperature), 1e-8)
        g_rho: Dict[NodeId, float] = {}
        for sid, p in pi.items():
            c = float(counts.get(sid, 0))
            g_rho[sid] = (c - float(k) * float(p)) / t

        # Apply chain rule to w_ms and w_qm by iterating activated subgraph.
        # Only analysis M-nodes contribute to rho (contrast nodes have no blocks).
        # We update:
        #   w_ms += lr * delta_r * g_rho[skill] * ∂rho(skill)/∂w_ms
        #   w_qm += lr * delta_r * Σ_skill g_rho[skill] * ∂rho(skill)/∂w_qm
        #
        # Where:
        #   ∂rho(skill)/∂w_ms(m,block,skill) = Σ_{q uses m} Sim(q_new,q) * w_qm(q,m)
        #   ∂rho(skill)/∂w_qm(q,m) = Sim(q_new,q) * Σ_{block} w_ms(m,block,skill)
        #
        # We compute these exactly by walking q→m→block→skill edges once.
        qm_seen: Set[Tuple[NodeId, NodeId]] = set()

        for q, sim in rollout.top_q_pairs:
            if sim <= 0.0:
                continue
            for m in self.graph.m_nodes_of(q.node_id):
                if getattr(m, "kind", "analysis") == "contrast":
                    continue
                qm_edge = self.graph.get_qm_edge(q.node_id, m.node_id)
                if qm_edge is None or not getattr(qm_edge, "trainable", True):
                    w_qm = 1.0
                else:
                    w_qm = float(qm_edge.weight)

                # Accumulate gradient for this QM edge across all skills under m's blocks.
                qm_key = (q.node_id, m.node_id)
                g_qm_total = 0.0

                for block in m.function_blocks:
                    bid = block.block_id
                    # graph.s_nodes_of_block yields (snode, w_ms)
                    for snode, w_ms in self.graph.s_nodes_of_block(m.node_id, bid):
                        sid = snode.node_id
                        gr = g_rho.get(sid, 0.0)
                        if gr == 0.0:
                            continue

                        # ---- MS edge update ----
                        ms_edge = self.graph.get_ms_edge(m.node_id, sid, bid)
                        if ms_edge is not None and ms_edge.trainable:
                            # ∂rho/∂w_ms = sim * w_qm
                            grad = float(sim) * float(w_qm)
                            delta = self.learning_rate * float(delta_r) * float(gr) * grad
                            ms_edge.weight = max(
                                self.clip_min,
                                min(self._ms_clip_max(), float(ms_edge.weight) + delta),
                            )

                        # ---- QM edge gradient accumulation ----
                        # ∂rho/∂w_qm = sim * w_ms (uses current w_ms from iterator)
                        g_qm_total += float(gr) * float(sim) * float(w_ms)

                if qm_edge is not None and getattr(qm_edge, "trainable", True):
                    if qm_key not in qm_seen:
                        qm_seen.add(qm_key)
                        delta = self.learning_rate * float(delta_r) * float(g_qm_total)
                        qm_edge.weight = max(
                            self.clip_min,
                            min(self.clip_max, float(qm_edge.weight) + delta),
                        )

                # Renormalise all MS groups (sum to MS_GROUP_WEIGHT_SUM) touched under this M node.
                for block in m.function_blocks:
                    self.graph.normalize_ms_weights(m.node_id, block.block_id)

        logger.debug(
            "Strict contrastive softmax update %d: R_with=%.3f R_wo=%.3f ΔR=%.3f k=%d",
            self._episode_count,
            r_with,
            r_wo,
            delta_r,
            k,
        )
        return r_with, r_wo, delta_r

    def update_batch(self, episodes: List[TrainingEpisode]) -> List[float]:
        raise RuntimeError(
            "Heuristic batch update has been retired. "
            "Use update_from_contrastive_softmax_rollout_strict(...) per rollout."
        )

    # ------------------------------------------------------------------
    # Post-training utilities
    # ------------------------------------------------------------------

    def prune(self, threshold: Optional[float] = None) -> int:
        """Convenience wrapper for ``graph.prune_ms_edges``."""
        return self.graph.prune_ms_edges(threshold)

    @property
    def episode_count(self) -> int:
        return self._episode_count

    # ------------------------------------------------------------------
    # Checkpoint helpers
    # ------------------------------------------------------------------

    def state_dict(self) -> Dict:
        """Export trainer hyperparameters for serialisation."""
        return {
            "learning_rate":  self.learning_rate,
            "entropy_coeff":  self.entropy_coeff,
            "clip_weight_min": self.clip_min,
            "clip_weight_max": self.clip_max,
            "episode_count":  self._episode_count,
        }

    def load_state_dict(self, state: Dict) -> None:
        self.learning_rate  = state.get("learning_rate",  self.learning_rate)
        self.entropy_coeff  = state.get("entropy_coeff",  self.entropy_coeff)
        self.clip_min       = state.get("clip_weight_min", self.clip_min)
        self.clip_max       = state.get("clip_weight_max", self.clip_max)
        self._episode_count = state.get("episode_count",  self._episode_count)
