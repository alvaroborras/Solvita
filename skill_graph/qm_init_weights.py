"""
QM 边（Q → M）初始权重规则。

analysis 与 contrast 共用一套常数，供 ``data_loader.build_graph`` 与
``evolution_apply._wire_qm_edges`` 使用。
"""

from __future__ import annotations

from typing import Tuple

# 所有 analysis M 合计占用的 QM 质量（若有多于一个 analysis，则平分）
QM_ANALYSIS_TOTAL = 0.4
# 每个 contrast M 的 QM 权重（与 contrast 个数无关，各自为 0.2）
QM_CONTRAST_EACH = 0.2


def qm_weights_per_m_kind(n_analysis: int, n_contrast: int) -> Tuple[float, float]:
    """
    返回 ``(每条 analysis QM 的 weight, 每条 contrast QM 的 weight)``。

    - 无 contrast 时：全部质量压在 analysis 上（与旧行为一致，按 analysis 个数平分 1.0）。
    - 有 contrast 时：analysis 合计 ``QM_ANALYSIS_TOTAL``（按 analysis 个数平分），
      每个 contrast 为 ``QM_CONTRAST_EACH``。
    - 仅有 contrast、无 analysis 的退化情况：每个 contrast 仍为 ``QM_CONTRAST_EACH``。
    """
    na = max(0, int(n_analysis))
    nc = max(0, int(n_contrast))

    if na == 0:
        return (0.0, QM_CONTRAST_EACH) if nc else (0.0, 0.0)

    if nc == 0:
        return 1.0 / na, 0.0

    return QM_ANALYSIS_TOTAL / na, QM_CONTRAST_EACH
