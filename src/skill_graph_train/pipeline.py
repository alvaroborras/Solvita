"""
End-to-end training episode: abstract problem → ρ / activated subgraph → (optional) LLM skill pick
→ skill-augmented prompt → codegen → compile → tests.

After ``compute_rollout_context`` (ρ, π, best paths), the LLM may pick skills from top-ρ candidates, then
``build_softmax_rollout_from_llm_skills`` builds ``SoftmaxRolloutResult`` for contrastive RL updates.

User tests must use ``input`` + ``expected_output`` (same convention as ``run_tests_node``).

Canonical skill-graph training loop; planning uses ``abstract_problem_node`` and codegen helpers under ``src``.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import logging

logger = logging.getLogger(__name__)

from skill_graph_train.bootstrap import ensure_import_paths

ensure_import_paths()

from src.nodes.abstract_problem import abstract_problem_node  # noqa: E402
from src.solver_network.graph_prompts import (  # noqa: E402
    format_enriched_path_context,
    format_skill_augmentation,
    format_selected_skills_content_by_ids,
)
from src.solver_network.planner_input import build_planner_input_from_state  # noqa: E402
from skill_graph import (  # noqa: E402
    GraphStore,
    Outcome,
    PlannerInput,
    RLTrainer,
    SolvitaSkillGraph,
)
from skill_graph.rl_rollout import (  # noqa: E402
    build_softmax_rollout_from_llm_skills,
    compute_rollout_context,
    softmax_rollout,
)

from skill_graph_train.codegen import attach_solution_to_state, generate_initial_cpp  # noqa: E402
from skill_graph_train.evaluate import compile_solution, run_user_tests  # noqa: E402
from skill_graph_train.evolution_hook import on_episode_finished  # noqa: E402
from skill_graph_train.minimal_state import create_initial_state_dict  # noqa: E402
from skill_graph_train.llm_skill_selection import (  # noqa: E402
    SkillSelectionResult,
    llm_select_skills,
    normalize_subproblem_dag,
    subproblem_dag_nonempty,
)


def _problem_summary_for_selection(state: Dict[str, Any]) -> str:
    """
    Short text for the skill-selection prompt **problem summary** block.

    Built from:

    - ``state["problem"]["canonical"]["objective"]`` — from ``abstract_problem_node`` (``canonical_problem.objective``).
    - ``state["problem"]["description"]`` — raw problem statement from the dataset / initial state.

    When ``objective`` is non-empty, format matches the main description line in :func:`build_planner_input`.
    """
    canonical = state.get("problem", {}).get("canonical", {}) or {}
    raw_desc = state.get("problem", {}).get("description", "")
    objective = canonical.get("objective", "")
    if objective:
        return f"{objective}\n\n{raw_desc}".strip()
    return raw_desc


def _implementation_steps_from_subproblem_dag(dag: Dict[str, Any]) -> List[str]:
    """Topological order of DAG nodes → lines for ``state.plan.implementation_steps`` (codegen)."""
    if not isinstance(dag, dict):
        return []
    nodes = dag.get("nodes") or []
    edges = dag.get("edges") or []
    id_to_desc: Dict[str, str] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        i = str(n.get("id", "") or "").strip()
        if not i:
            continue
        id_to_desc[i] = str(n.get("description", "") or "").strip()
    if not id_to_desc:
        return []
    if not edges:
        out: List[str] = []
        for n in nodes:
            if isinstance(n, dict):
                nid = str(n.get("id", "") or "").strip()
                d = str(n.get("description", "") or "").strip()
                if nid or d:
                    out.append(f"{nid}: {d}" if nid else d)
        return out

    adj: Dict[str, List[str]] = defaultdict(list)
    indeg: Dict[str, int] = defaultdict(int)
    for k in id_to_desc:
        indeg[k] = 0
    for e in edges:
        if not isinstance(e, dict):
            continue
        a = str(e.get("from_id", e.get("from", "")) or "").strip()
        b = str(e.get("to_id", e.get("to", "")) or "").strip()
        if a in id_to_desc and b in id_to_desc:
            adj[a].append(b)
            indeg[b] += 1
    queue = deque([k for k in id_to_desc if indeg[k] == 0])
    order: List[str] = []
    while queue:
        u = queue.popleft()
        order.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                queue.append(v)
    if len(order) < len(id_to_desc):
        order = list(id_to_desc.keys())
    return [f"{i}: {id_to_desc[i]}" for i in order if id_to_desc.get(i)]


def build_planner_input(state: Dict[str, Any], record: Dict[str, Any]) -> PlannerInput:
    """Build :class:`PlannerInput` after ``abstract_problem_node`` has filled ``canonical`` and tags."""
    p = build_planner_input_from_state(state)
    tags = record.get("tags")
    if tags:
        if isinstance(tags, str):
            tag_row = [tags.strip()]
        else:
            tag_row = [str(t) for t in tags]
    else:
        tag_row = list(p.tags)

    tc = record.get("test_case_strings")
    if isinstance(tc, list):
        test_cases = [str(x) for x in tc]
    else:
        test_cases = None
    pid = record.get("problem_id") or record.get("id")
    return PlannerInput(
        description=p.description,
        tags=tag_row,
        direction=p.direction,
        problem_id=str(pid) if pid is not None else None,
        test_cases=test_cases,
        similarity_description=p.similarity_description,
        similarity_tags=list(p.similarity_tags) if p.similarity_tags is not None else None,
    )


def normalize_user_tests(record: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Accept test lists from training JSONL:

    - ``test_cases`` / ``tests`` — list of ``{input, expected_output}`` (or ``output``).
    - ``test_case`` — singular key, list of cases (same as many logic pipelines).
    """
    raw = record.get("test_cases") or record.get("tests") or record.get("test_case")
    if not raw:
        logger.warning(
            "Skipping record (no test_case/test_cases/tests): id=%s",
            record.get("id", record.get("problem_id", "unknown")),
        )
        return []
    out: List[Dict[str, Any]] = []
    for t in raw:
        if isinstance(t, dict):
            inp = t.get("input", "")
            if isinstance(inp, list):
                inp = "\n".join(str(x) for x in inp)
            exp = t.get("expected_output", t.get("output", ""))
            if isinstance(exp, list):
                exp = "\n".join(str(x) for x in exp)
            out.append({"input": inp, "expected_output": exp})
        else:
            raise ValueError("test_cases entries must be objects with input/expected_output")
    return out


@dataclass
class EpisodeResult:
    pass_with: float
    pass_without: float
    outcome_with: Outcome
    outcome_without: Outcome
    compile_ok_with: bool
    compile_ok_without: bool
    delta_r: float
    rollout_rho_size: int


def _solve_until_compile_then_test(
    state: Dict[str, Any],
    skill_graph_block: str,
    tests: List[Dict[str, Any]],
    checker_exe: Optional[str],
    max_codegen_attempts: int,
    *,
    include_skill_selection_in_prompt: bool = True,
) -> Tuple[str, float, Outcome, bool, int]:
    """
    Retry codegen until compile succeeds, then score on ``tests``; on compile failure, feed errors back.

    When ``include_skill_selection_in_prompt=False`` (contrastive branch), omit skill blocks, DAG, ids,
    and DAG-derived ``implementation_steps`` (see :func:`generate_initial_cpp`).

    Returns
    -------
    code, pass_rate, outcome, compile_ok, llm_calls
    """
    feedback = ""
    llm_calls = 0
    last_code = ""
    checker = Path(checker_exe) if checker_exe else None
    n_attempts = max(1, int(max_codegen_attempts))
    for attempt in range(n_attempts):
        code, n = generate_initial_cpp(
            state,
            skill_graph_block=skill_graph_block,
            compile_feedback=feedback,
            include_skill_selection_in_prompt=include_skill_selection_in_prompt,
        )
        llm_calls += n
        last_code = code
        ok, exe, errs = compile_solution(code, diagnostic=False)
        if ok and exe is not None:
            pass_rate, _results, outcome = run_user_tests(exe, tests, checker_exe=checker)
            return code, pass_rate, outcome, True, llm_calls
        feedback = "\n".join(errs) if errs else "Compilation failed (no compiler messages captured)."
        feedback = (f"[compile validator round {attempt + 1}/{n_attempts}]\n" + feedback)[:8000]
    return last_code, 0.0, Outcome.COMPILATION_ERROR, False, llm_calls


def run_episode(
    graph: SolvitaSkillGraph,
    trainer: RLTrainer,
    record: Dict[str, Any],
    config: Dict[str, Any],
    *,
    sample_k: int = 5,
    temperature: float = 1.0,
    top_k_problems: int = 5,
    contrastive_llm: bool = True,
    rng: Optional[random.Random] = None,
    use_llm_skill_selection: bool = True,
    skill_candidate_k: int = 64,
    min_llm_skills: int = 3,
    max_llm_skills: int = 5,
    max_codegen_attempts: int = 5,
    skill_graph_evolution: Optional[bool] = None,
    log_episode_index: Optional[int] = None,
    log_dataset_total: Optional[int] = None,
    graph_lock: Any = None,
) -> Tuple[EpisodeResult, Optional[Any]]:
    """
    One training episode.

    - Similarity uses planner canonical text + tags (see ``build_planner_input``).
    - ρ / softmax(π) and LLM skill pick from top-ρ; path details go into codegen.
    - Compile gate: retry codegen with errors until compile OK, then run tests for reward.
    - Default: **with** and **without** skill-graph prompt (ΔR = R_with − R_without); set ``contrastive_llm=False`` to skip the second branch.

    ``log_episode_index`` / ``log_dataset_total`` add global progress hints to logs (for ``scripts/train.py``).
    """
    rng = rng or random.Random()

    def _train_phase(phase: str, detail: str = "") -> None:
        pid = str(record.get("problem_id") or record.get("id") or "?")
        geo = ""
        if log_episode_index is not None:
            if log_dataset_total is not None:
                geo = f"item {log_episode_index}/{log_dataset_total} "
            else:
                geo = f"item {log_episode_index} "
        tail = f" — {detail}" if detail else ""
        logger.info("[train] %sid=%s | %s%s", geo, pid, phase, tail)
    evo_enabled = (
        bool(skill_graph_evolution)
        if skill_graph_evolution is not None
        else bool(config.get("skill_graph_evolution", False))
    )
    tests = normalize_user_tests(record)
    if not tests:
        pid = str(record.get("problem_id") or record.get("id") or "?")
        logger.warning("Skipping record with no tests: id=%s", pid)
        return EpisodeResult(
            pass_with=0.0,
            pass_without=0.0,
            outcome_with=Outcome.PARTIAL,
            outcome_without=Outcome.PARTIAL,
            compile_ok_with=False,
            compile_ok_without=False,
            delta_r=0.0,
            rollout_rho_size=-1,
        ), None
    if record.get("public_tests") is not None:
        pub = record.get("public_tests")
    elif isinstance(record.get("test_case"), list) and record["test_case"]:
        # No public_tests: use first test_case row as public sample (Solvita-style)
        t0 = record["test_case"][0]
        if isinstance(t0, dict) and ("input" in t0):
            pub = [
                {
                    "input": t0.get("input", ""),
                    "output": t0.get("output") or t0.get("expected_output", ""),
                }
            ]
        else:
            pub = []
    else:
        pub = []
    raw_problem = {
        "description": record.get("description", ""),
        "time_limit": record.get("time_limit") or 2000,
        "space_limit": record.get("space_limit") or 256,
        "public_tests": pub if isinstance(pub, list) else [],
    }
    state = create_initial_state_dict(raw_problem, config)
    state["tests"] = {
        **state.get("tests", {}),
        "generated_tests": tests,
        "total_tests": len(tests),
        "ready": True,
        "checker_exe": record.get("checker_exe"),
    }

    _train_phase("1-abstract", "abstract_problem (canonical + tags)")
    ps = abstract_problem_node(state)
    state = _merge_state(state, ps)

    planner = build_planner_input(state, record)
    _train_phase("2-rollout", "top-Q sim → ρ/π → LLM skills or softmax")
    graph_guard = graph_lock if graph_lock is not None else nullcontext()
    llm_returned_no_skills = False
    with graph_guard:
        ctx = compute_rollout_context(
            graph,
            planner,
            top_k_problems=top_k_problems,
            temperature=temperature,
        )

        sel: SkillSelectionResult = SkillSelectionResult([], {})

        if ctx is None:
            rollout = softmax_rollout(
                graph,
                planner,
                top_k_problems=top_k_problems,
                sample_k=sample_k,
                temperature=temperature,
                rng=rng,
                sample_with_replacement=True,
            )
            sel = SkillSelectionResult(list(rollout.sampled_skill_ids or []), {})
        elif use_llm_skill_selection:
            summary = _problem_summary_for_selection(state)
            sel = llm_select_skills(
                config,
                summary,
                graph,
                ctx.rho,
                candidate_k=skill_candidate_k,
                min_select=min_llm_skills,
                max_select=max_llm_skills,
                state=state,
                rollout_ctx=ctx,
            )
            if sel.skill_ids:
                rollout = build_softmax_rollout_from_llm_skills(graph, planner, ctx, sel.skill_ids)
            else:
                logger.info(
                    "LLM returned no skills; keep DAG but do not inject skill block into codegen "
                    "(softmax_rollout is still computed for rollout stats/RL update)"
                )
                llm_returned_no_skills = True
                preserved_dag = sel.subproblem_dag
                rollout = softmax_rollout(
                    graph,
                    planner,
                    top_k_problems=top_k_problems,
                    sample_k=sample_k,
                    temperature=temperature,
                    rng=rng,
                    sample_with_replacement=True,
                )
                dag_out: Dict[str, Any] = (
                    normalize_subproblem_dag(preserved_dag)
                    if subproblem_dag_nonempty(preserved_dag)
                    else {}
                )
                # User requested behavior: when LLM returns no skills, do not provide graph-skill
                # guidance to codegen. Keep DAG if available.
                sel = SkillSelectionResult([], dag_out)
        else:
            rollout = softmax_rollout(
                graph,
                planner,
                top_k_problems=top_k_problems,
                sample_k=sample_k,
                temperature=temperature,
                rng=rng,
                sample_with_replacement=True,
            )
            sel = SkillSelectionResult(list(rollout.sampled_skill_ids or []), {})

        plan_patch: Dict[str, Any] = {
            "skill_selection_subproblem_dag": sel.subproblem_dag,
            "skill_selection_skill_ids": sel.skill_ids,
            "skill_selection_skills_content_md": format_selected_skills_content_by_ids(graph, sel.skill_ids),
        }
        steps_from_dag = _implementation_steps_from_subproblem_dag(sel.subproblem_dag)
        if steps_from_dag:
            plan_patch["implementation_steps"] = steps_from_dag
        state = _merge_state(state, {"plan": plan_patch})

        if llm_returned_no_skills:
            skill_block = ""
        else:
            skill_block = format_skill_augmentation(
                rollout.augmentation,
                include_required_skill_templates=False,
            )
            if rollout.sampled_skill_ids:
                pi_roll = rollout.pi or {}
                skill_block += "\n" + format_enriched_path_context(
                    graph,
                    rollout.best_path_per_skill,
                    pi_roll,
                    rollout.sampled_skill_ids,
                    section_index=4,
                )
            if record.get("append_graph_stats"):
                skill_block += "\n" + json.dumps({"rho_keys": len(rollout.rho or {}), "sampled": rollout.sampled_skill_ids})

    _train_phase("3-solve-with", "codegen + compile + tests (with skill prompt)")
    code_wo = ""
    if contrastive_llm:
        _train_phase("4-solve-without", "codegen + compile + tests (without, for ΔR)")
        # Parallelize the two solve branches while keeping RL update order unchanged.
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_with = pool.submit(
                _solve_until_compile_then_test,
                state,
                skill_block,
                tests,
                record.get("checker_exe"),
                max_codegen_attempts,
            )
            fut_wo = pool.submit(
                _solve_until_compile_then_test,
                state,
                "",
                tests,
                record.get("checker_exe"),
                max_codegen_attempts,
                include_skill_selection_in_prompt=False,
            )
            code_with, pw, ow, cw, _llm_w = fut_with.result()
            code_wo, pwo, owo, cwo, _llm_wo = fut_wo.result()
        state_wo = dict(state)
        state_wo.update(attach_solution_to_state(state_wo, code_wo))
    else:
        code_with, pw, ow, cw, _llm_w = _solve_until_compile_then_test(
            state,
            skill_block,
            tests,
            record.get("checker_exe"),
            max_codegen_attempts,
        )
        pwo, owo, cwo = 0.0, Outcome.PARTIAL, False
        _train_phase("4-solve-without", "skipped (contrastive_llm=False)")
    state_w = dict(state)
    state_w.update(attach_solution_to_state(state_w, code_with))

    _train_phase("5-rl-update", "ΔR contrastive update → QM/MS weights")
    with graph_guard:
        r_with, r_wo, delta_r = trainer.update_from_contrastive_softmax_rollout_strict(
            rollout,
            ow,
            pw,
            owo,
            pwo,
        )

    _pid = record.get("problem_id") or record.get("id") or "?"
    logger.info(
        "Episode reward id=%s R_with=%.4f R_wo=%.4f ΔR=%.4f pass_with=%.2f pass_wo=%.2f "
        "out_w=%s out_wo=%s compile_w=%s compile_wo=%s rho=%d skills=%d",
        _pid,
        r_with,
        r_wo,
        delta_r,
        pw,
        pwo,
        ow.name if hasattr(ow, "name") else ow,
        owo.name if hasattr(owo, "name") else owo,
        cw,
        cwo,
        len(rollout.rho or {}),
        len(rollout.sampled_skill_ids or []),
    )

    if evo_enabled:
        _train_phase("6-evolution", "evolution_hook (optional Q/M writes)")
    else:
        _train_phase("6-evolution", "skipped (skill_graph_evolution=False)")

    er = EpisodeResult(
        pass_with=pw,
        pass_without=pwo,
        outcome_with=ow,
        outcome_without=owo,
        compile_ok_with=cw,
        compile_ok_without=cwo,
        delta_r=delta_r,
        rollout_rho_size=len(rollout.rho or {}),
    )
    with graph_guard:
        on_episode_finished(
            {
                "record": record,
                "config": config,
                "pass_with": pw,
                "pass_without": pwo,
                "outcome_with": ow,
                "outcome_without": owo,
                "code_with": code_with,
                "code_without": code_wo,
                "delta_r": delta_r,
                "rollout": rollout,
                "graph": graph,
                "trainer": trainer,
                "planner": planner,
                "state": state_w,
                "skill_graph_evolution": evo_enabled,
                "contrastive_llm": contrastive_llm,
            }
        )
    return er, rollout


def _merge_state(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in patch.items():
        if k in ("problem", "plan", "solution", "tests", "feedback") and isinstance(v, dict):
            merged = dict(out.get(k, {}))
            merged.update(v)
            out[k] = merged
        elif k == "llm_calls":
            out[k] = int(out.get("llm_calls", 0)) + int(v or 0)
        elif k == "execution_log":
            out[k] = list(out.get("execution_log", [])) + list(v or [])
        else:
            out[k] = v
    return out


def load_graph(graph_dir: str) -> SolvitaSkillGraph:
    store = GraphStore(graph_dir)
    return store.load()


def save_graph(graph: SolvitaSkillGraph, graph_dir: str) -> None:
    GraphStore(graph_dir).save(graph)
