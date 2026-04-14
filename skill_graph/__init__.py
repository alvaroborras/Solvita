"""
skill_graph — vendored graph library (project-local copy)
======================================
Three-layer heterogeneous graph framework for the Solvita coding agent.

Layer overview
--------------
  Q  (QNode)  –  Training-set problem: description, tags, correct/incorrect solutions
  M  (MNode)  –  Decomposed solution: FunctionBlocks, SubProblems, DAG, ErrorExperiences
  S  (SNode)  –  Skill knowledge-base entry: code template, tags, complexity

Typical usage
-------------
    from skill_graph import (
        SolvitaSkillGraph,
        QNode, MNode, SNode,
        QMEdge, MSEdge,
        FunctionBlock, SubProblem, DAGLink, ErrorExperience,
        EdgeWeightInitializer, SimilarityMetric,
        GraphInference, PlannerInput, SolverAugmentation,
        RLTrainer, TrainingEpisode, default_reward_fn,
        GraphStore,
        NodeType, EdgeType, Outcome, Dataset, ComplexityTier,
    )
"""

# ── types ──────────────────────────────────────────────────────────────────
from .types import (
    NodeType,
    EdgeType,
    Dataset,
    ComplexityTier,
    Outcome,
    NodeId,
    EdgeId,
    BlockId,
    TagSet,
    WeightTable,
    Metadata,
)

# ── building blocks ─────────────────────────────────────────────────────────
from .blocks import (
    FunctionBlock,
    SubProblem,
    DAGLink,
    BlockToSubproblem,
    BlockDifference,
    ErrorExperience,
    ERROR_TYPES,
)

# ── nodes ───────────────────────────────────────────────────────────────────
from .nodes import (
    BaseNode,
    QNode,
    MNode,
    SNode,
)

# ── edges ───────────────────────────────────────────────────────────────────
from .edges import (
    BaseEdge,
    QMEdge,
    MSEdge,
)

# ── graph ───────────────────────────────────────────────────────────────────
from .graph import MS_GROUP_WEIGHT_SUM, SolvitaSkillGraph

# ── initialiser ─────────────────────────────────────────────────────────────
from .initializer import (
    EdgeWeightInitializer,
    SimilarityMetric,
)

# ── inference ────────────────────────────────────────────────────────────────
from .inference import (
    PlannerInput,
    SkillRecommendation,
    SolverAugmentation,
    GraphInference,
)

# ── trainer ─────────────────────────────────────────────────────────────────
from .trainer import (
    TrainingEpisode,
    RLTrainer,
    default_reward_fn,
    judging_reward_fn,
    outcome_from_submission_result,
)
from .question_similarity import QuestionSimilarityWeights, sim_planner_to_qnode
from .path_scoring import (
    SkillPathContribution,
    compute_rho_per_skill,
    compute_rho_and_best_paths,
    softmax_skill_distribution,
    log_prob_under_softmax,
)
from .rl_rollout import (
    RolloutContext,
    SoftmaxRolloutResult,
    build_softmax_rollout_from_llm_skills,
    compute_rollout_context,
    softmax_rollout,
)
from .self_evolution import (
    SolveCandidate,
    EvolutionInput,
    EvolutionPlan,
    build_self_evolution_plan,
    official_correct_from_record,
)

# ── persistence ──────────────────────────────────────────────────────────────
from .store import GraphStore

# data loading
from .data_loader import SkillGraphDataLoader, SkillGraphDataPaths


__all__ = [
    # types
    "NodeType", "EdgeType", "Dataset", "ComplexityTier", "Outcome",
    "NodeId", "EdgeId", "BlockId", "TagSet", "WeightTable", "Metadata",
    # blocks
    "FunctionBlock", "SubProblem", "DAGLink",
    "BlockToSubproblem", "BlockDifference", "ErrorExperience", "ERROR_TYPES",
    # nodes
    "BaseNode", "QNode", "MNode", "SNode",
    # edges
    "BaseEdge", "QMEdge", "MSEdge",
    # graph
    "SolvitaSkillGraph",
    "MS_GROUP_WEIGHT_SUM",
    # initialiser
    "EdgeWeightInitializer", "SimilarityMetric",
    # inference
    "PlannerInput", "SkillRecommendation", "SolverAugmentation", "GraphInference",
    # trainer
    "TrainingEpisode", "RLTrainer", "default_reward_fn", "judging_reward_fn",
    "outcome_from_submission_result",
    # similarity / path RL
    "QuestionSimilarityWeights", "sim_planner_to_qnode",
    "SkillPathContribution",
    "compute_rho_per_skill",
    "compute_rho_and_best_paths",
    "softmax_skill_distribution",
    "log_prob_under_softmax",
    "RolloutContext",
    "SoftmaxRolloutResult",
    "compute_rollout_context",
    "build_softmax_rollout_from_llm_skills",
    "softmax_rollout",
    # self evolution
    "SolveCandidate",
    "EvolutionInput",
    "EvolutionPlan",
    "build_self_evolution_plan",
    "official_correct_from_record",
    # persistence
    "GraphStore",
    # data loading
    "SkillGraphDataLoader",
    "SkillGraphDataPaths",
]
