"""
Self-evolution after one episode.

记号（与题述一致）
-----------------
- **A** = **with skill** 的提交与评测结果（``with_skill_candidate``）。
- **B** = **without skill** 的提交与评测结果（``no_skill_candidate``）。

规则
----
- **A 为正解（AC）**：对 **A** 建 ``logic_analysis``；若 **B 为错解**，再建 ``logic_contrast``（错解 B vs 正解 A）。
- **A 为错解**：
  - 若有 **官方正解**：对官方做 chain，再 contrast（错解 **A(with)** vs 官方）；若 **B 也正解**，Q 的 ``correct_solutions`` 同时收录 B。
  - 若无官方但 **B 为正解**：对 **B** 做 chain，再 contrast（错解 **A** vs 正解 **B**）。
  - 若无官方且 **B 也错**：不自进化。

正/错解代码来自本轮 with/without 或官方；不为自进化再调 codegen。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SolveCandidate:
    """单次提交：either with-skill (A) or without-skill (B)."""

    candidate_id: str
    code: str
    passed: bool
    pass_rate: float = 0.0
    score: float = 0.0
    from_skill_path: bool = True
    skill_id: str = ""


@dataclass
class EvolutionInput:
    """``with_skill_candidate`` = A；``no_skill_candidate`` = B。"""

    no_skill_candidate: SolveCandidate  # B = without
    with_skill_candidate: SolveCandidate  # A = with
    official_correct_solution: Optional[str] = None


@dataclass
class EvolutionPlan:
    """
    ``logic_chain_code``：送给 correct_solution_logic_chain 的**正解**源码。
    ``contrast_wrong_codes``：错解列表（通常 1 个）；非空则对每个调用 logic_diff（正=logic_chain_code）。
    """

    create_qi: bool
    logic_chain_code: str = ""
    contrast_wrong_codes: List[str] = field(default_factory=list)
    correct_solutions_for_q: List[str] = field(default_factory=list)
    incorrect_solutions_for_q: List[Dict[str, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def official_correct_from_record(record: dict) -> Optional[str]:
    s = record.get("correct_solution")
    if isinstance(s, str) and s.strip():
        return s.strip()
    xs = record.get("correct_solutions")
    if isinstance(xs, list):
        for x in xs:
            if isinstance(x, str) and x.strip():
                return x.strip()
    return None


def _same_code(a: str, b: str) -> bool:
    return (a or "").strip() == (b or "").strip()


def build_self_evolution_plan(inp: EvolutionInput) -> EvolutionPlan:
    A = inp.with_skill_candidate  # with
    B = inp.no_skill_candidate  # without
    official = (inp.official_correct_solution or "").strip() or None
    a_ok = bool(A.passed)
    b_ok = bool(B.passed)

    def fail_empty_chain(note: str) -> EvolutionPlan:
        return EvolutionPlan(create_qi=False, notes=[note, "empty_logic_chain_code"])

    # ----- A（with）为正解 -----
    if a_ok:
        cc = (A.code or "").strip()
        if not cc:
            return fail_empty_chain("A_with_ok_empty_code")
        wrongs: List[str] = []
        inc: List[Dict[str, str]] = []
        if not b_ok and (B.code or "").strip():
            wrongs.append(B.code.strip())
            inc.append({"sol_id": "no_skill", "source": B.code, "verdict": "failed_tests"})
        corr = [A.code.strip()]
        if b_ok and not _same_code(A.code, B.code):
            corr.append(B.code.strip())
        return EvolutionPlan(
            create_qi=True,
            logic_chain_code=cc,
            contrast_wrong_codes=wrongs,
            correct_solutions_for_q=corr,
            incorrect_solutions_for_q=inc,
            notes=["evolve/A_with_correct" + ("/contrast_B_without_wrong" if wrongs else "/analysis_only")],
        )

    # ----- A（with）为错解 -----
    if official:
        cc = official.strip()
        wrongs = [A.code.strip()] if (A.code or "").strip() else []
        if not wrongs:
            return fail_empty_chain("A_with_wrong_official_no_A_code")
        corr = [official]
        if b_ok and not _same_code(official, B.code):
            corr.append(B.code.strip())
        inc = [{"sol_id": "with_skill", "source": A.code, "verdict": "failed_tests"}]
        return EvolutionPlan(
            create_qi=True,
            logic_chain_code=cc,
            contrast_wrong_codes=wrongs,
            correct_solutions_for_q=corr,
            incorrect_solutions_for_q=inc,
            notes=["evolve/A_with_wrong_official_contrast_A_vs_official"],
        )

    if b_ok:
        cc = (B.code or "").strip()
        if not cc:
            return fail_empty_chain("A_wrong_B_without_ok_empty_B_code")
        wrongs = [A.code.strip()] if (A.code or "").strip() else []
        if not wrongs:
            return fail_empty_chain("A_wrong_B_ok_no_A_code")
        return EvolutionPlan(
            create_qi=True,
            logic_chain_code=cc,
            contrast_wrong_codes=wrongs,
            correct_solutions_for_q=[B.code.strip()],
            incorrect_solutions_for_q=[
                {"sol_id": "with_skill", "source": A.code, "verdict": "failed_tests"},
            ],
            notes=["evolve/A_with_wrong_B_without_ok_contrast_A_vs_B"],
        )

    return EvolutionPlan(
        create_qi=False,
        notes=["skip_no_official_A_with_wrong_B_without_wrong"],
    )
