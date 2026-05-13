"""
训练状态持久化：每题写入 ``latest/`` + ``progress.json`` + ``rng.json``，便于中断恢复；
每 N 题（默认 50）额外写入 ``<state_dir>/milestones/ckpt_<step>/`` 里程碑快照。
"""

from __future__ import annotations

import base64
import json
import logging
import pickle
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from skill_graph_train.bootstrap import ensure_import_paths

ensure_import_paths()

from skill_graph import RLTrainer, SolvitaSkillGraph  # noqa: E402
from skill_graph.store import GraphStore  # noqa: E402

logger = logging.getLogger(__name__)

PROGRESS_VERSION = 1
PASS_STATS_VERSION = 1


@dataclass
class PassStatistics:
    """
    累计评测通过情况，随 ``progress.json`` 的 ``extra["pass_stats"]`` 持久化，
    并额外写入 ``pass_stats.json`` 便于直接查看。
    """

    version: int = PASS_STATS_VERSION
    episodes: int = 0
    with_full_ac: int = 0
    """with 技能图分支：全对（AC）次数。"""
    without_full_ac: int = 0
    """without 分支：全对次数（仅 contrastive 训练时有效）。"""
    both_full_ac: int = 0
    only_with_ac: int = 0
    only_without_ac: int = 0
    neither_full_ac: int = 0
    compile_fail_with: int = 0
    compile_fail_without: int = 0
    sum_delta_r: float = 0.0
    sum_pass_with: float = 0.0
    sum_pass_without: float = 0.0
    contrastive_episodes: int = 0
    """实际跑了 without 的题数（用于 without 率分母）。"""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "episodes": self.episodes,
            "with_full_ac": self.with_full_ac,
            "without_full_ac": self.without_full_ac,
            "both_full_ac": self.both_full_ac,
            "only_with_ac": self.only_with_ac,
            "only_without_ac": self.only_without_ac,
            "neither_full_ac": self.neither_full_ac,
            "compile_fail_with": self.compile_fail_with,
            "compile_fail_without": self.compile_fail_without,
            "sum_delta_r": self.sum_delta_r,
            "sum_pass_with": self.sum_pass_with,
            "sum_pass_without": self.sum_pass_without,
            "contrastive_episodes": self.contrastive_episodes,
        }

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "PassStatistics":
        if not d:
            return cls()
        return cls(
            version=int(d.get("version", PASS_STATS_VERSION)),
            episodes=int(d.get("episodes", 0)),
            with_full_ac=int(d.get("with_full_ac", 0)),
            without_full_ac=int(d.get("without_full_ac", 0)),
            both_full_ac=int(d.get("both_full_ac", 0)),
            only_with_ac=int(d.get("only_with_ac", 0)),
            only_without_ac=int(d.get("only_without_ac", 0)),
            neither_full_ac=int(d.get("neither_full_ac", 0)),
            compile_fail_with=int(d.get("compile_fail_with", 0)),
            compile_fail_without=int(d.get("compile_fail_without", 0)),
            sum_delta_r=float(d.get("sum_delta_r", 0.0)),
            sum_pass_with=float(d.get("sum_pass_with", 0.0)),
            sum_pass_without=float(d.get("sum_pass_without", 0.0)),
            contrastive_episodes=int(d.get("contrastive_episodes", 0)),
        )

    def update(self, er: Any, *, contrastive: bool) -> None:
        """用单题 :class:`EpisodeResult` 更新计数。"""
        from skill_graph import Outcome

        def _ac(pass_rate: float, outcome: Any) -> bool:
            if outcome == Outcome.COMPILATION_ERROR:
                return False
            try:
                return float(pass_rate) >= 1.0 - 1e-9
            except (TypeError, ValueError):
                return False

        self.episodes += 1
        self.sum_delta_r += float(er.delta_r)
        self.sum_pass_with += float(er.pass_with)
        w_ok = _ac(er.pass_with, er.outcome_with)
        if w_ok:
            self.with_full_ac += 1
        if not er.compile_ok_with:
            self.compile_fail_with += 1

        if contrastive:
            self.contrastive_episodes += 1
            self.sum_pass_without += float(er.pass_without)
            wo_ok = _ac(er.pass_without, er.outcome_without)
            if wo_ok:
                self.without_full_ac += 1
            if not er.compile_ok_without:
                self.compile_fail_without += 1
            if w_ok and wo_ok:
                self.both_full_ac += 1
            elif w_ok:
                self.only_with_ac += 1
            elif wo_ok:
                self.only_without_ac += 1
            else:
                self.neither_full_ac += 1

    def rates_summary(self) -> str:
        """一行可读汇总（用于日志）。"""
        n = max(1, self.episodes)
        nc = max(1, self.contrastive_episodes)
        avg_dr = self.sum_delta_r / n
        avg_pw = self.sum_pass_with / n
        avg_pwo = self.sum_pass_without / nc if self.contrastive_episodes else 0.0
        parts = [
            f"n={self.episodes}",
            f"with_AC={self.with_full_ac}({100.0 * self.with_full_ac / n:.1f}%)",
            f"avg_ΔR={avg_dr:.4f}",
            f"avg_pass_w={avg_pw:.3f}",
        ]
        if self.contrastive_episodes:
            parts.append(f"wo_AC={self.without_full_ac}({100.0 * self.without_full_ac / nc:.1f}%)")
            parts.append(f"both_AC={self.both_full_ac}")
            parts.append(f"only_w={self.only_with_ac} only_wo={self.only_without_ac} neither={self.neither_full_ac}")
            parts.append(f"avg_pass_wo={avg_pwo:.3f}")
        parts.append(f"CE_w={self.compile_fail_with} CE_wo={self.compile_fail_without}")
        return " | ".join(parts)


@dataclass
class TrainingProgress:
    """训练进度：下一题从 ``(next_epoch, next_row)`` 开始；``global_step`` 为已完成题数。"""

    version: int = PROGRESS_VERSION
    global_step: int = 0
    """已完成题目数（每跑完一题 +1）。"""
    next_epoch: int = 0
    """下一轮开始的 epoch 下标（0-based）。"""
    next_row: int = 0
    """下一轮开始的 dataset 行下标（0-based）。"""
    dataset_path: str = ""
    rows_count: int = 0
    seed: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "global_step": self.global_step,
            "next_epoch": self.next_epoch,
            "next_row": self.next_row,
            "dataset_path": self.dataset_path,
            "rows_count": self.rows_count,
            "seed": self.seed,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TrainingProgress":
        return cls(
            version=int(d.get("version", PROGRESS_VERSION)),
            global_step=int(d.get("global_step", 0)),
            next_epoch=int(d.get("next_epoch", 0)),
            next_row=int(d.get("next_row", 0)),
            dataset_path=str(d.get("dataset_path", "")),
            rows_count=int(d.get("rows_count", 0)),
            seed=int(d.get("seed", 0)),
            extra=dict(d.get("extra") or {}),
        )


def _default_state_dir(graph_dir: Path) -> Path:
    return graph_dir.resolve() / "training_state"


def save_rng_state(state_dir: Path, rng: random.Random) -> None:
    blob = base64.b64encode(pickle.dumps(rng.getstate())).decode("ascii")
    path = state_dir / "rng.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rng_state": blob}, indent=2), encoding="utf-8")


def load_rng_state(state_dir: Path, rng: random.Random) -> None:
    path = state_dir / "rng.json"
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    blob = data.get("rng_state")
    if not blob:
        return
    # SECURITY: pickle.loads is unsafe on untrusted input. rng.json is only ever
    # produced by save_rng_state() above and read back from a checkpoint dir
    # owned by the same user. Never load checkpoints from untrusted sources
    # (PRs, shared buckets, downloaded artifacts) without regenerating them.
    rng.setstate(pickle.loads(base64.b64decode(blob)))


def save_latest(
    state_dir: Path,
    graph: SolvitaSkillGraph,
    trainer: RLTrainer,
    progress: TrainingProgress,
    rng: random.Random,
) -> None:
    """
    将当前图、trainer 超参、进度与 RNG 写入 ``state_dir``（每题结束后调用）。
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    latest = state_dir / "latest"
    store = GraphStore(str(state_dir))
    store.save(
        graph,
        trainer_state=trainer.state_dict(),
        target_dir=str(latest),
    )
    (state_dir / "progress.json").write_text(
        json.dumps(progress.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    save_rng_state(state_dir, rng)
    ps = progress.extra.get("pass_stats")
    if isinstance(ps, dict):
        (state_dir / "pass_stats.json").write_text(
            json.dumps(ps, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    logger.info("Saved training state to %s (global_step=%d)", state_dir, progress.global_step)


def load_latest_graph_and_trainer(
    state_dir: Path,
) -> Tuple[SolvitaSkillGraph, Dict[str, Any]]:
    """从 ``state_dir/latest`` 加载图与 ``trainer_state``。"""
    latest = state_dir / "latest"
    meta_path = latest / "meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"Missing {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    trainer_state = meta.get("trainer_state") or {}
    graph = GraphStore(str(state_dir)).load(source_dir=str(latest))
    return graph, trainer_state


def load_progress(state_dir: Path) -> Optional[TrainingProgress]:
    p = state_dir / "progress.json"
    if not p.is_file():
        return None
    return TrainingProgress.from_dict(json.loads(p.read_text(encoding="utf-8")))


def milestones_dir(state_dir: Path) -> Path:
    """里程碑专用子目录：``<state_dir>/milestones/``。"""
    return state_dir / "milestones"


def save_milestone(
    state_dir: Path,
    graph: SolvitaSkillGraph,
    trainer: RLTrainer,
    global_step: int,
) -> Path:
    """
    里程碑检查点：写入 ``<state_dir>/milestones/ckpt_<global_step>/``（与 GraphStore 约定一致）。
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    mdir = milestones_dir(state_dir)
    mdir.mkdir(parents=True, exist_ok=True)
    store = GraphStore(str(mdir))
    out = store.save_checkpoint(graph, global_step, trainer_state=trainer.state_dict())
    logger.info("Milestone checkpoint saved: %s", out)
    return out


def advance_progress(
    progress: TrainingProgress,
    epoch: int,
    row_index: int,
    rows_count: int,
    epochs_planned: int,
) -> None:
    """
    在刚完成 ``(epoch, row_index)`` 这一题后更新 ``progress``（global_step、next_epoch、next_row）。
    """
    progress.global_step += 1
    candidate_row = row_index + 1
    if candidate_row < rows_count:
        progress.next_epoch = epoch
        progress.next_row = max(progress.next_row, candidate_row)
    elif epoch + 1 < epochs_planned:
        progress.next_epoch = epoch + 1
        progress.next_row = 0
    else:
        progress.next_epoch = epochs_planned
        progress.next_row = 0


def normalize_resume_start(
    progress: TrainingProgress,
    rows_count: int,
    epochs_planned: int,
) -> Tuple[int, int]:
    """
    将 ``progress.next_epoch`` / ``next_row`` 夹到合法范围（数据集变更或手动改文件时）。
    若 ``next_epoch >= epochs_planned``，返回 ``(epochs_planned, 0)``（主循环将不执行任何题）。
    """
    if rows_count <= 0:
        return 0, 0
    if progress.next_epoch >= epochs_planned:
        return epochs_planned, 0
    ep = max(0, min(progress.next_epoch, epochs_planned - 1))
    row = max(0, min(progress.next_row, rows_count - 1))
    return ep, row


def validate_dataset_for_resume(
    progress: TrainingProgress,
    dataset_path: str,
    rows_count: int,
) -> None:
    """若数据集行数或路径变化，给出警告（仍允许继续，由用户负责）。"""
    if progress.rows_count and progress.rows_count != rows_count:
        logger.warning(
            "Resume: row count changed (%d -> %d); indices may be wrong.",
            progress.rows_count,
            rows_count,
        )
    if progress.dataset_path and Path(progress.dataset_path).resolve() != Path(dataset_path).resolve():
        logger.warning(
            "Resume: dataset path differs from saved progress (saved=%s, current=%s).",
            progress.dataset_path,
            dataset_path,
        )
