"""
Skill-selection step: LLM picks skill ids from top-ρ candidates and emits a **sub-problem DAG**
for the current task. Rollout then builds augmentation from selected ids.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from loguru import logger

from skill_graph.graph import SolvitaSkillGraph  # noqa: E402
from skill_graph.nodes import SNode  # noqa: E402
from skill_graph.path_scoring import SkillPathContribution  # noqa: E402
from skill_graph.rl_rollout import RolloutContext  # noqa: E402
from src.llm import UnifiedLLMClient  # noqa: E402
from src.utils.json_utils import try_parse_json_dict  # noqa: E402
from src.utils.prompt_templates import (  # noqa: E402
    get_nested_template,
    load_prompt_templates,
    render_template,
)


def format_skill_ids_for_log(graph: SolvitaSkillGraph, skill_ids: Sequence[str]) -> str:
    """Human-readable skill list for logs (id + S-node title when available)."""
    if not skill_ids:
        return "(none)"
    parts: List[str] = []
    for sid in skill_ids:
        n = graph.get_node(sid)
        if isinstance(n, SNode):
            t = (n.title or "").strip()
            parts.append(f"{sid} ({t})" if t else str(sid))
        else:
            parts.append(str(sid))
    return " | ".join(parts)


def _skill_selection_system_prompt() -> str:
    """System message from ``config/prompt_template.yaml`` → ``solver_skill_selection.system``."""
    root = load_prompt_templates()
    tpl = get_nested_template(root, "solver_skill_selection.system")
    if not isinstance(tpl, str):
        raise KeyError("solver_skill_selection.system must be a string")
    return tpl.strip()


# UUID patterns; also allow compact 32-hex (aligned with candidate ids)
_UUID_HYPHEN_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_UUID_COMPACT_RE = re.compile(r"\b[0-9a-fA-F]{32}\b")


def _uuid_compact(s: str) -> str:
    return re.sub(r"[^0-9a-fA-F]+", "", s).lower()


@dataclass
class SkillSelectionResult:
    """Chosen skill ids and the LLM-authored sub-problem DAG for the current problem."""

    skill_ids: List[str]
    subproblem_dag: Dict[str, Any]


def normalize_subproblem_dag(raw: Any) -> Dict[str, Any]:
    """Ensure ``nodes`` / ``edges`` lists exist; drop invalid entries lightly."""
    if not isinstance(raw, dict):
        return {"nodes": [], "edges": []}
    nodes = raw.get("nodes")
    edges = raw.get("edges")
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []
    return {"nodes": nodes, "edges": edges}


def subproblem_dag_nonempty(dag: Any) -> bool:
    """True if the DAG has at least one node or one edge (after normalization)."""
    d = normalize_subproblem_dag(dag)
    return bool(d.get("nodes")) or bool(d.get("edges"))


def parse_skill_selection_response(
    text: str,
    candidate_ids: Sequence[str],
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Parse one LLM response: ``selected_skill_ids`` and ``subproblem_dag``.
    Falls back to UUID/id heuristics for ids only when the JSON list is missing.
    """
    obj = try_parse_json_dict(text)
    dag: Dict[str, Any] = {"nodes": [], "edges": []}
    ids: List[str] = []
    if isinstance(obj, dict):
        ids = _skill_ids_from_parsed_obj(obj)
        raw_dag = obj.get("subproblem_dag") or obj.get("sub_problem_dag")
        if isinstance(raw_dag, str) and raw_dag.strip():
            try:
                raw_dag = json.loads(raw_dag)
            except (json.JSONDecodeError, TypeError):
                raw_dag = {}
        dag = normalize_subproblem_dag(raw_dag)
    if not ids:
        ids = parse_selected_skill_ids_with_fallback(text, candidate_ids)
    return ids, dag


def _llm_generate_skill_pick(
    llm: UnifiedLLMClient,
    user_prompt: str,
    config: Dict[str, Any],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Skill pick: system prompt from YAML + optional JSON mode; retry without if unsupported."""
    mt = int(
        max_tokens
        if max_tokens is not None
        else config.get("skill_selection_max_tokens", 4096)
    )
    temp = (
        float(temperature)
        if temperature is not None
        else float(config.get("skill_selection_temperature", 0.2))
    )
    base_kw: Dict[str, Any] = {"max_tokens": mt, "temperature": temp}
    system = _skill_selection_system_prompt()
    try:
        return llm.generate_with_system(
            system,
            user_prompt,
            response_format={"type": "json_object"},
            **base_kw,
        )
    except Exception as e:
        logger.warning(
            "skill selection with response_format=json_object failed (%s), retrying without",
            e,
        )
        return llm.generate_with_system(system, user_prompt, **base_kw)


def format_abstract_context_for_skill_selection(
    state: Dict[str, Any],
    max_chars: int | None = None,
) -> str:
    """
    Markdown context for skill-selection LLM when only ``abstract_problem`` has run:
    level-1/level-2 tags + abridged canonical (no algorithm choice or steps).
    """
    lines: List[str] = []
    prob = state.get("problem") or {}
    l1 = prob.get("tags_selected") or []
    l2 = prob.get("tags_level2_selected") or []
    if isinstance(l1, str):
        l1 = [l1]
    if isinstance(l2, str):
        l2 = [l2]
    if l1:
        lines.append("### Level-1 algorithmic tags")
        lines.append(", ".join(str(t).strip() for t in l1 if str(t).strip()))
        lines.append("")
    if l2:
        lines.append("### Level-2 algorithmic tags (fine-grained)")
        lines.append(", ".join(str(t).strip() for t in l2 if str(t).strip()))
        lines.append("")

    canon = prob.get("canonical") or {}
    if isinstance(canon, dict) and canon:
        lines.append("### Canonical problem (abridged)")
        obj = canon.get("objective")
        if obj:
            lines.append(f"- **Objective:** {obj}")
        for k in ("inputs", "outputs", "constraints"):
            v = canon.get(k)
            if v:
                try:
                    snippet = json.dumps(v, ensure_ascii=False)[:1200]
                except (TypeError, ValueError):
                    snippet = str(v)[:1200]
                lines.append(f"- **{k}:** {snippet}")
        lines.append("")

    out = "\n".join(lines).strip()
    if not out:
        return "(No abstract context available.)"
    if max_chars is not None and max_chars > 0 and len(out) > max_chars:
        out = out[:max_chars] + "\n\n…(abstract context truncated for skill selection)"
    return out


def _function_block_ids_reaching_skills(
    graph: SolvitaSkillGraph,
    m_id: str,
    function_blocks: Sequence[Any],
    candidate_skill_ids: Set[str],
) -> Set[str]:
    cand = {str(x) for x in candidate_skill_ids}
    relevant: Set[str] = set()
    for fb in function_blocks:
        bid = str(getattr(fb, "id", None) or getattr(fb, "block_id", "") or "").strip()
        if not bid:
            continue
        for snode, _w in graph.s_nodes_of_block(m_id, bid):
            if str(snode.node_id) in cand:
                relevant.add(bid)
                break
    return relevant


def _ordered_subproblems_for_blocks(m: Any, block_ids: Set[str]) -> List[Any]:
    """SubProblems linked to ``block_ids`` via ``block_to_subproblem`` (stable order)."""
    mappings = getattr(m, "block_to_subproblem", None) or []
    seen_sub: Set[str] = set()
    ordered: List[Any] = []
    for mapping in mappings:
        if str(getattr(mapping, "block_id", "")) not in block_ids:
            continue
        sid = str(getattr(mapping, "subproblem_id", "") or "").strip()
        if not sid or sid in seen_sub:
            continue
        sp = m.get_subproblem(sid) if hasattr(m, "get_subproblem") else None
        seen_sub.add(sid)
        ordered.append(sp if sp is not None else sid)
    return ordered


def format_activated_graph_context_for_skill_selection(
    graph: SolvitaSkillGraph,
    rollout_ctx: RolloutContext,
    *,
    candidate_skill_ids: Set[str],
    max_chars: int | None = None,
) -> str:
    """
    Build Markdown for skill selection: top-similarity **Q** nodes, then per **M** only
    **function blocks** and **subproblems** that connect to the **candidate skills** (ρ top-k
    ids used in the catalog). MS edges decide which blocks matter; ``block_to_subproblem``
    decides which subproblem rows to show for those blocks.
    """
    pairs = rollout_ctx.top_q_pairs or []
    if not pairs:
        return "(No activated Q-nodes in rollout context.)"

    if not candidate_skill_ids:
        return "(No candidate skill ids; cannot filter graph context.)"

    lines: List[str] = [
        "Context from the **skill graph** for this task: similar **Q-nodes** and, under each Q, "
        "**M-nodes** trimmed to **function blocks** and **subproblems** that connect to the "
        "**candidate skills** (same set as the ρ-ranked skill list you will choose from). "
        "MS edges link blocks to skills; subproblems are shown when mapped to those blocks.",
        "",
    ]

    for q, sim in pairs:
        lines.append(f"### Q-node `{q.node_id}`  (similarity to current problem: {float(sim):.6f})")
        lines.append(f"- **problem_id:** {getattr(q, 'problem_id', '')}")
        ttags = list(getattr(q, "tags", None) or []) or list(getattr(q, "tags_level1", None) or [])
        if ttags:
            lines.append(f"- **tags:** {', '.join(str(t) for t in ttags[:24])}")
        ad = (getattr(q, "abstract_description", None) or "").strip()
        if ad:
            tail = "…" if len(ad) > 1200 else ""
            lines.append(f"- **abstract_description:** {ad[:1200]}{tail}")

        m_list = graph.m_nodes_of(q.node_id)
        if not m_list:
            lines.append("- *(no M-nodes attached to this Q)*")
            lines.append("")
            continue

        for m in m_list:
            lines.append(f"#### M-node `{m.node_id}`  (kind={getattr(m, 'kind', '')!r})")
            blocks = getattr(m, "function_blocks", None) or []
            rel_bids = _function_block_ids_reaching_skills(
                graph, m.node_id, blocks, candidate_skill_ids
            )
            if not rel_bids:
                lines.append(
                    "- *(no function block in this M links to a candidate skill via MS edges)*"
                )
                lines.append("")
                continue

            lines.append("- **function blocks (candidate-linked only — labels / roles):**")
            for fb in blocks:
                bid = str(getattr(fb, "id", None) or getattr(fb, "block_id", "") or "").strip()
                if bid not in rel_bids:
                    continue
                label = getattr(fb, "name_or_label", "") or ""
                role = (getattr(fb, "role", "") or "").replace("\n", " ").strip()
                if len(role) > 280:
                    role = role[:280] + "…"
                lines.append(f"  - `{bid}` **{label}**: {role}")

            sub_items = _ordered_subproblems_for_blocks(m, rel_bids)
            if sub_items:
                lines.append("- **subproblem nodes (mapped from those blocks):**")
                for item in sub_items:
                    if isinstance(item, str):
                        lines.append(f"  - `{item}`: (description not loaded)")
                        continue
                    d = (getattr(item, "description", "") or "").replace("\n", " ").strip()
                    if len(d) > 320:
                        d = d[:320] + "…"
                    sid = getattr(item, "id", getattr(item, "sub_id", ""))
                    lines.append(f"  - `{sid}`: {d}")
            lines.append("")
        lines.append("")

    out = "\n".join(lines).strip()
    if max_chars is not None and max_chars > 0 and len(out) > max_chars:
        out = out[:max_chars] + "\n\n…(activated graph context truncated)"
    return out


def _format_candidate_skills_block(
    candidates: Sequence[Tuple[str, str, str, float]],
    max_desc_chars: int,
) -> str:
    lines: List[str] = []
    mc = max(80, int(max_desc_chars))
    for sid, title, desc, rv in candidates:
        d = (desc or "").replace("\n", " ").strip()
        if len(d) > mc:
            d = d[:mc] + "…"
        lines.append(f"- **{sid}** | {title!r} | ρ={rv:.6f}")
        lines.append(f"  {d}")
    return "\n".join(lines)


def _format_valid_skill_ids_block(candidates: Sequence[Tuple[str, str, str, float]]) -> str:
    return "\n".join(str(sid) for sid, _, _, _ in candidates)


def topk_skills_by_rho(
    rho: Dict[str, float],
    graph: SolvitaSkillGraph,
    k: int,
) -> List[Tuple[str, str, str, float]]:
    """
    Return top-``k`` skills by descending ρ.

    Returns
    -------
    List of ``(skill_id, title, description, rho_value)``.
    """
    if k <= 0 or not rho:
        return []
    items = sorted(rho.items(), key=lambda x: -float(x[1]))
    out: List[Tuple[str, str, str, float]] = []
    for sid, rv in items:
        if len(out) >= k:
            break
        snode = graph.s_nodes.get(str(sid))
        if snode is None:
            continue
        title = str(getattr(snode, "title", "") or "")
        desc = str(getattr(snode, "description", "") or "")
        out.append((str(sid), title, desc, float(rv)))
    return out


def build_skill_catalog_prompt(
    problem_summary: str,
    candidates: Sequence[Tuple[str, str, str, float]],
    *,
    min_select: int,
    max_select: int,
    activated_graph_context: str = "",
    max_desc_chars: int = 500,
) -> str:
    """
    User message for skill-id selection (``config/prompt_template.yaml`` → ``solver_skill_selection.user``).

    ``problem_summary`` is typically ``canonical.objective`` plus raw ``description``.
    ``activated_graph_context`` comes from ``RolloutContext`` (Q/M evidence), not free-form planner steps.
    """
    ag = (activated_graph_context or "").strip()
    if not ag:
        ag = "(No activated graph context.)"
    return render_template(
        "solver_skill_selection.user",
        MIN_SELECT=str(int(min_select)),
        MAX_SELECT=str(int(max_select)),
        PROBLEM_SUMMARY=problem_summary.strip(),
        ACTIVATED_GRAPH_CONTEXT=ag,
        CANDIDATE_SKILLS_BLOCK=_format_candidate_skills_block(candidates, max_desc_chars),
        VALID_SKILL_IDS_BLOCK=_format_valid_skill_ids_block(candidates),
    )


def build_minimal_skill_pick_prompt(
    problem_summary: str,
    candidates: Sequence[Tuple[str, str, str, float]],
    *,
    min_select: int,
    max_select: int,
    problem_max_chars: int = 1600,
) -> str:
    """
    Short retry user prompt (``solver_skill_selection.minimal_user``): compact task + one-line candidates.
    """
    ps = (problem_summary or "").strip()
    if problem_max_chars > 0 and len(ps) > problem_max_chars:
        ps = ps[:problem_max_chars] + "…"
    candidate_lines = "\n".join(
        f"- {sid}  ρ={rv:.4f}  {title!r}" for sid, title, _, rv in candidates
    )
    return render_template(
        "solver_skill_selection.minimal_user",
        MIN_SELECT=str(int(min_select)),
        MAX_SELECT=str(int(max_select)),
        PROBLEM_SUMMARY_SHORT=ps if ps else "(empty)",
        CANDIDATE_LINES_MINIMAL=candidate_lines,
        VALID_SKILL_IDS_BLOCK=_format_valid_skill_ids_block(candidates),
    )


_JSON_SKILL_ID_KEYS = (
    "selected_skill_ids",
    "skill_ids",
    "selected_skills",
    "skills",
    "chosen_skill_ids",
    "ids",
)


def _skill_ids_from_parsed_obj(obj: Any) -> List[str]:
    """Accept alternate JSON keys the model may use for the id list."""
    if not isinstance(obj, dict):
        return []
    for k in _JSON_SKILL_ID_KEYS:
        v = obj.get(k)
        if isinstance(v, list):
            out = [str(x).strip() for x in v if str(x).strip()]
            if out:
                return out
        if isinstance(v, str) and v.strip():
            return [v.strip()]
    return []


def _extract_uuids_allowed_in_order(text: str, candidate_ids: Sequence[str]) -> List[str]:
    """
    Collect UUIDs that appear in order in text and are in the candidate set (hyphenated or 32-hex).
    """
    if not (text or "").strip() or not candidate_ids:
        return []
    by_lower = {a.lower(): a for a in candidate_ids}
    by_c32 = {_uuid_compact(a): a for a in candidate_ids}
    hits: List[Tuple[int, str]] = []
    for m in _UUID_HYPHEN_RE.finditer(text):
        raw = m.group(0)
        aid = by_lower.get(raw.lower())
        if aid:
            hits.append((m.start(), aid))
    for m in _UUID_COMPACT_RE.finditer(text):
        raw = m.group(0)
        aid = by_c32.get(raw.lower())
        if aid:
            hits.append((m.start(), aid))
    hits.sort(key=lambda x: x[0])
    out: List[str] = []
    seen: set[str] = set()
    for _, aid in hits:
        if aid not in seen:
            out.append(aid)
            seen.add(aid)
    return out


def _extract_skill_ids_fallback(text: str, candidate_ids: Sequence[str]) -> List[str]:
    """
    When JSON is unusable, collect candidate ids by first occurrence in text (truncation / noise).
    """
    if not (text or "").strip() or not candidate_ids:
        return []
    tl = text.lower()
    hits: List[Tuple[int, str]] = []
    for aid in candidate_ids:
        lo = aid.lower()
        j = 0
        while True:
            pos = tl.find(lo, j)
            if pos < 0:
                break
            hits.append((pos, aid))
            j = pos + len(lo)
    hits.sort(key=lambda x: x[0])
    out: List[str] = []
    seen: set[str] = set()
    for _, aid in hits:
        if aid not in seen:
            out.append(aid)
            seen.add(aid)
    return out


def parse_selected_skill_ids(text: str) -> List[str]:
    """Parse skill id list from model output (JSON + alternate key names; same recovery as ``try_parse_json_dict``)."""
    obj = try_parse_json_dict(text)
    if obj is None:
        logger.warning("parse_selected_skill_ids: no JSON object found")
        return []
    ids = _skill_ids_from_parsed_obj(obj)
    if not ids:
        logger.debug(
            "parse_selected_skill_ids: JSON parsed but no id list in known keys; keys=%s",
            list(obj.keys())[:24],
        )
    return ids


def parse_selected_skill_ids_with_fallback(
    text: str,
    candidate_ids: Sequence[str],
) -> List[str]:
    """JSON (multiple keys) → substring match → UUID scan against candidates."""
    ids = parse_selected_skill_ids(text)
    if ids:
        return ids
    ids = _extract_skill_ids_fallback(text, candidate_ids)
    if ids:
        return ids
    return _extract_uuids_allowed_in_order(text, candidate_ids)


def llm_select_skills(
    config: Dict[str, Any],
    problem_summary: str,
    graph: SolvitaSkillGraph,
    rho: Dict[str, float],
    *,
    candidate_k: int,
    min_select: int = 3,
    max_select: int = 5,
    state: Dict[str, Any] | None = None,
    rollout_ctx: Optional[RolloutContext] = None,
) -> SkillSelectionResult:
    """
    Call the LLM once to pick **min_select–max_select** skill ids from the top-ρ ``candidate_k`` candidates
    and to output a **subproblem_dag** (nodes + edges) for the current problem.

    If ``rollout_ctx`` is set, the prompt includes **activated-graph context** from the rollout.
    Otherwise the prompt uses :func:`format_abstract_context_for_skill_selection` for the graph section.

    There is **no second attempt** when the model returns no valid ids: the parsed DAG (if any) is kept
    for codegen; the pipeline may fall back to :func:`softmax_rollout` for skills only.
    Each response is parsed with :func:`parse_skill_selection_response`.
    """
    min_select = max(0, int(min_select))
    max_select = max(min_select, int(max_select))

    candidates = topk_skills_by_rho(rho, graph, candidate_k)
    if not candidates:
        logger.warning("llm_select_skills: no candidates from rho")
        return SkillSelectionResult([], {})

    allowed = {c[0] for c in candidates}
    candidate_ids = [c[0] for c in candidates]

    base_temp = float(config.get("skill_selection_temperature", 0.2))
    temp_first = float(
        config.get("skill_selection_temperature_first", min(0.08, base_temp))
    )
    graph_ctx_max = int(config.get("skill_selection_planner_max_chars", 3500))
    desc_max = 500
    call_temp = min(base_temp, temp_first)

    try:
        role_cfg = UnifiedLLMClient.build_role_config(config, "plan")
        llm = UnifiedLLMClient(role_cfg)
    except Exception:
        llm = UnifiedLLMClient(config)

    if rollout_ctx is not None:
        graph_ctx = format_activated_graph_context_for_skill_selection(
            graph,
            rollout_ctx,
            candidate_skill_ids=allowed,
            max_chars=graph_ctx_max,
        )
    else:
        graph_ctx = format_abstract_context_for_skill_selection(
            state or {},
            max_chars=graph_ctx_max,
        )
    prompt = build_skill_catalog_prompt(
        problem_summary,
        candidates,
        min_select=min_select,
        max_select=max_select,
        activated_graph_context=graph_ctx,
        max_desc_chars=desc_max,
    )
    response = _llm_generate_skill_pick(
        llm,
        prompt,
        config,
        temperature=call_temp,
        max_tokens=None,
    )
    ids, dag = parse_skill_selection_response(response, candidate_ids)
    last_dag = normalize_subproblem_dag(dag)
    filtered = [x for x in ids if x in allowed][: max(0, max_select)]
    if not filtered:
        logger.warning(
            "llm_select_skills: no valid skill ids in one shot (parsed=%s)",
            ids[:8],
        )

    # Pad with top-rho candidates if the model returned too few ids (up to max_select).
    if 0 < len(filtered) < min_select:
        seen = set(filtered)
        for sid, _, _, _ in candidates:
            if sid in seen:
                continue
            filtered.append(sid)
            seen.add(sid)
            if len(filtered) >= min_select:
                break
        filtered = filtered[:max_select]

    if not filtered:
        nd = normalize_subproblem_dag(last_dag)
        if subproblem_dag_nonempty(nd):
            logger.info(
                "llm_select_skills: no valid skill ids; keeping subproblem_dag for codegen (nodes=%d edges=%d)",
                len(nd.get("nodes") or []),
                len(nd.get("edges") or []),
            )
        return SkillSelectionResult([], nd)

    skill_line = format_skill_ids_for_log(graph, filtered)
    logger.info(
        "LLM skill selection: {} skill(s) from {} candidates — {} | DAG nodes={} edges={}",
        len(filtered),
        len(candidates),
        skill_line,
        len(last_dag.get("nodes") or []),
        len(last_dag.get("edges") or []),
    )
    return SkillSelectionResult(filtered, normalize_subproblem_dag(last_dag))


def format_path_details_for_prompt(
    best_path_per_skill: Dict[str, SkillPathContribution],
    skill_ids: Sequence[str],
) -> str:
    """Explainability lines for high-scoring paths (codegen prompt blocks)."""
    lines: List[str] = ["### High-scoring graph paths (for selected skills)"]
    for sid in skill_ids:
        p = best_path_per_skill.get(sid)
        if p is None:
            lines.append(f"- **{sid}**: (no single best path recorded)")
            continue
        lines.append(
            f"- **{sid}**: path_score={p.path_score:.6f} | "
            f"Sim={p.sim:.4f} w_qm={p.w_qm:.4f} w_ms={p.w_ms:.4f} | "
            f"Q={p.q_node_id} M={p.m_node_id} block={p.block_id!r}"
        )
    return "\n".join(lines) + "\n" if len(lines) > 1 else ""
