# LangGraph Pass@1 Benchmark Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the bootstrap-tests, verifier, failure-bank, and solve-controller flow so the LangGraph pipeline improves benchmark `pass@1` while keeping extra cost moderate.

**Architecture:** Keep LangGraph as the orchestration layer, but add a light trusted-test entry path, an evidence-oriented failure bank, an independent verifier before acceptance, and a cheap controller that decides when to pay for heavy phases. Preserve the existing codegen and hacker loops, and integrate the new phases by inserting a small number of focused nodes plus structured state fields.

**Tech Stack:** Python 3.10, LangGraph, pytest, SQLite, loguru, existing benchmark harness, existing dashboard DAG JSON

---

## File Structure

### New Files

- `src/utils/test_seed_cases.py`
  Shared helper for deterministic local exact certification cases used by both bootstrap tests and heavy test generation.
- `src/failure_bank/__init__.py`
  Package export for the failure-bank service.
- `src/failure_bank/service.py`
  SQLite-backed storage, lookup, and write helpers for failure cases, risk patterns, and repair outcomes.
- `src/nodes/bootstrap_tests.py`
  Low-cost node that constructs the minimal trusted execution test set.
- `src/nodes/failure_bank_lookup.py`
  Node that reads failure-bank context after abstraction and injects structured anti-patterns/counterexamples into state.
- `src/nodes/verifier_phase.py`
  Independent acceptance verifier that runs trusted tests, complexity audit, micro-oracle checks, and risk-pattern audit.
- `src/nodes/solve_controller.py`
  Rule-based pre-solve and post-verify controller nodes plus routing helpers.
- `tests/graph/test_pass1_state_schema.py`
  State/config scaffolding tests for the new LangGraph fields.
- `tests/nodes/test_bootstrap_tests.py`
  Unit tests for the bootstrap-tests node.
- `tests/failure_bank/test_service.py`
  SQLite storage and retrieval tests for the failure-bank service.
- `tests/nodes/test_failure_bank_lookup.py`
  Node-level tests for failure-bank lookup integration.
- `tests/nodes/test_verifier_phase.py`
  Verifier decision tests.
- `tests/nodes/test_solve_controller.py`
  Controller decision tests.
- `tests/graph/test_pass1_workflow.py`
  Workflow/routing integration tests for the new phase order.
- `tests/benchmark/test_pipeline_verification_metrics.py`
  Benchmark-result plumbing tests for verifier metrics and false-accept tracking.

### Modified Files

- `src/graph/state.py`
  Add `solve_policy`, `verification`, `failure_bank_context`, `tests.full_testgen_completed`, and `tests.trust_tiers`; merge failure-bank runtime defaults.
- `src/nodes/__init__.py`
  Export new lazy-loaded nodes and routing helpers.
- `src/nodes/generate_tests.py`
  Reuse `build_local_certified_tests`, emit trust-tier metadata, and mark heavy test generation as completed.
- `src/nodes/hack_test.py`
  Write high-confidence hacker breaks into the failure bank.
- `src/nodes/routing.py`
  Replace direct codegen success routing with verifier-aware and controller-aware routing.
- `src/graph/workflow.py`
  Insert `failure_bank_lookup`, `pre_solve_controller`, `bootstrap_tests`, `verifier_phase`, and `post_verify_controller`.
- `src/benchmark/types.py`
  Extend `BenchmarkResult` with verifier/control-flow metrics.
- `src/benchmark/modes/pipeline.py`
  Populate new benchmark-result fields and record official benchmark false accepts.
- `src/benchmark/reporting.py`
  Aggregate false-accept rate, verifier repair rate, and verifier escalation rate.
- `dashboard/dag-definition.json`
  Reflect the new top-level topology and verifier/controller nodes.

### Existing Tests to Re-run

- `tests/regression/test_workflow_import_regression.py`
- `tests/regression/test_baseline_runtime_regressions.py`
- `tests/nodes/test_generate_tests_oracle_status.py`
- `tests/benchmark/test_pipeline_mode.py`
- `tests/benchmark/test_reporting.py`

---

### Task 1: Add State and Runtime-Config Scaffolding

**Files:**
- Modify: `src/graph/state.py`
- Test: `tests/graph/test_pass1_state_schema.py`

- [ ] **Step 1: Write the failing state-schema tests**

```python
from src.graph.state import create_initial_state


def test_initial_state_contains_pass1_fields():
    state = create_initial_state(
        raw_problem={
            "description": "Example",
            "time_limit": 2000,
            "space_limit": 256,
            "public_tests": [],
        },
        config={},
    )

    assert state["solve_policy"] == {
        "risk_score": 0.0,
        "run_testgen_initially": False,
        "run_skill_plan": False,
        "initial_codegen_budget": 1,
        "verifier_mode": "standard",
        "allow_hacker": False,
        "escalate_after_failures": 1,
        "generated_test_target_scale": 0,
        "next_action": "",
    }
    assert state["verification"] == {
        "decision": "",
        "confidence": 0.0,
        "risk_flags": [],
        "new_tests": [],
        "feedback_summary": "",
        "trusted_failures": [],
        "open_failure_case_ids": [],
    }
    assert state["failure_bank_context"] == {
        "matched_patterns": [],
        "retrieved_counterexamples": [],
        "anti_patterns": [],
        "repair_summaries": [],
        "source_case_ids": [],
    }
    assert state["tests"]["full_testgen_completed"] is False
    assert state["tests"]["trust_tiers"] == {}


def test_runtime_config_merges_failure_bank_defaults():
    state = create_initial_state(
        raw_problem={"description": "Example", "public_tests": []},
        config={"failure_bank": {"lookup_limit": 7}},
    )

    failure_bank_cfg = state["config"]["failure_bank"]
    assert failure_bank_cfg["enabled"] is True
    assert failure_bank_cfg["lookup_limit"] == 7
    assert failure_bank_cfg["data_dir"].endswith("artifacts/failure_bank")
```

- [ ] **Step 2: Run the new tests to confirm the current state is missing fields**

Run: `pytest tests/graph/test_pass1_state_schema.py -v`

Expected: FAIL with `KeyError: 'solve_policy'` and missing `failure_bank` config defaults.

- [ ] **Step 3: Add the new typed dicts, config defaults, and initial-state values**

Add the new nested data structures near the other typed dicts in `src/graph/state.py`:

```python
class SolvePolicyData(TypedDict, total=False):
    risk_score: float
    run_testgen_initially: bool
    run_skill_plan: bool
    initial_codegen_budget: int
    verifier_mode: str
    allow_hacker: bool
    escalate_after_failures: int
    generated_test_target_scale: int
    next_action: str


class VerificationData(TypedDict, total=False):
    decision: str
    confidence: float
    risk_flags: List[str]
    new_tests: List[Dict[str, Any]]
    feedback_summary: str
    trusted_failures: List[Dict[str, Any]]
    open_failure_case_ids: List[str]


class FailureBankContextData(TypedDict, total=False):
    matched_patterns: List[Dict[str, Any]]
    retrieved_counterexamples: List[Dict[str, Any]]
    anti_patterns: List[str]
    repair_summaries: List[Dict[str, Any]]
    source_case_ids: List[str]
```

Extend `TestData`:

```python
class TestData(TypedDict, total=False):
    ...
    full_testgen_completed: bool
    trust_tiers: Dict[str, int]
```

Add a failure-bank config fallback and merge it in `_merge_runtime_config`:

```python
def _fallback_failure_bank_defaults(repo_root: Path) -> Dict[str, Any]:
    return {
        "enabled": True,
        "data_dir": _resolve_repo_path(repo_root, "artifacts/failure_bank"),
        "lookup_limit": 3,
    }
```

Initialize the new fields in `create_initial_state`:

```python
tests=TestData(
    generated_tests=[],
    total_tests=0,
    test_results=[],
    passed_tests=0,
    pass_rate=0.0,
    pending_execution=False,
    ready=False,
    full_testgen_completed=False,
    trust_tiers={},
    ...
),
...
verification=VerificationData(
    decision="",
    confidence=0.0,
    risk_flags=[],
    new_tests=[],
    feedback_summary="",
    trusted_failures=[],
    open_failure_case_ids=[],
),
solve_policy=SolvePolicyData(
    risk_score=0.0,
    run_testgen_initially=False,
    run_skill_plan=False,
    initial_codegen_budget=1,
    verifier_mode="standard",
    allow_hacker=False,
    escalate_after_failures=1,
    generated_test_target_scale=0,
    next_action="",
),
failure_bank_context=FailureBankContextData(
    matched_patterns=[],
    retrieved_counterexamples=[],
    anti_patterns=[],
    repair_summaries=[],
    source_case_ids=[],
),
```

- [ ] **Step 4: Run the state-schema tests again**

Run: `pytest tests/graph/test_pass1_state_schema.py -v`

Expected: PASS

- [ ] **Step 5: Commit the scaffolding change**

```bash
git add src/graph/state.py tests/graph/test_pass1_state_schema.py
git commit -m "feat: add pass1 workflow state scaffolding"
```

### Task 2: Add Bootstrap Tests and Trust-Tier Metadata

**Files:**
- Create: `src/utils/test_seed_cases.py`
- Create: `src/nodes/bootstrap_tests.py`
- Modify: `src/nodes/generate_tests.py`
- Modify: `src/nodes/__init__.py`
- Modify: `tests/nodes/test_generate_tests_oracle_status.py`
- Test: `tests/nodes/test_bootstrap_tests.py`

- [ ] **Step 1: Write the failing bootstrap-tests and trust-tier tests**

```python
from src.graph.state import create_initial_state
from src.nodes.bootstrap_tests import bootstrap_tests_node


def test_bootstrap_tests_create_trusted_suite_from_public_tests():
    state = create_initial_state(
        raw_problem={
            "description": "Example",
            "public_tests": [{"input": "1\n", "output": "1\n"}],
        },
        config={},
    )

    update = bootstrap_tests_node(state)
    tests = update["tests"]

    assert tests["ready"] is True
    assert tests["full_testgen_completed"] is False
    assert tests["trust_tiers"] == {"trusted": 1}
    assert tests["generated_tests"][0]["trust_tier"] == "trusted"
    assert tests["generated_tests"][0]["type"] == "public"


def test_bootstrap_tests_add_failure_bank_counterexamples_as_trusted():
    state = create_initial_state(
        raw_problem={"description": "Example", "public_tests": []},
        config={},
    )
    state["failure_bank_context"]["retrieved_counterexamples"] = [
        {
            "input_text": "2\n1 2\n",
            "expected_output": "3\n",
            "failure_type": "WA",
        }
    ]

    update = bootstrap_tests_node(state)

    assert update["tests"]["trust_tiers"] == {"trusted": 1}
    assert update["tests"]["generated_tests"][0]["type"] == "failure_bank"
    assert update["tests"]["generated_tests"][0]["trust_tier"] == "trusted"
```

Add a small assertion to `tests/nodes/test_generate_tests_oracle_status.py`:

```python
assert update["tests"]["full_testgen_completed"] is True
assert update["tests"]["trust_tiers"]["trusted"] >= 1
assert update["tests"]["trust_tiers"].get("advisory", 0) >= 0
```

- [ ] **Step 2: Run the new tests to verify the node does not exist and heavy testgen has no trust tiers**

Run: `pytest tests/nodes/test_bootstrap_tests.py tests/nodes/test_generate_tests_oracle_status.py -v`

Expected: FAIL with `ModuleNotFoundError: src.nodes.bootstrap_tests` and missing `trust_tiers` / `full_testgen_completed`.

- [ ] **Step 3: Extract deterministic local seed-case logic and implement `bootstrap_tests_node`**

Move the existing local exact-certification helper from `generate_tests.py` into `src/utils/test_seed_cases.py`:

```python
from typing import Any, Dict, List


def _count_cyclic_divisible_segments_bruteforce(n: int, m: int, k: int, a: List[int]) -> int:
    total_positions = n * m
    if total_positions > 256:
        raise ValueError("bruteforce helper is only intended for modest certification inputs")

    b = a * m
    total_sum = sum(b)
    answer = 0
    for start in range(total_positions):
        segment_sum = 0
        for length in range(1, total_positions):
            segment_sum += b[(start + length - 1) % total_positions]
            if segment_sum % k == 0:
                answer += 1
    if total_sum % k == 0:
        answer += 1
    return answer % 1000000007


def build_local_certified_tests(problem_desc: str) -> List[Dict[str, Any]]:
    text = (problem_desc or "").lower()
    markers = (
        "cyclic sequence",
        "segment",
        "sum of elements in the segment is divisible by k",
        "number of different segments",
        "same set of indices",
        "concatenating m copies",
    )
    if sum(1 for marker in markers if marker in text) < 4:
        return []

    cases = [
        (1, 3, 2, [1]),
        (1, 4, 3, [1]),
        (2, 1, 5, [0, 1]),
        (3, 2, 5, [1, 1, 1]),
    ]
    certified = []
    for n, m, k, a in cases:
        expected = _count_cyclic_divisible_segments_bruteforce(n, m, k, a)
        certified.append(
            {
                "input": f"{n} {m} {k}\n{' '.join(map(str, a))}\n",
                "output": f"{expected}\n",
                "type": "edge",
                "description": "Local exact certification case",
            }
        )
    return certified
```

Create `src/nodes/bootstrap_tests.py`:

```python
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

import src.events as events
from src.utils.test_seed_cases import build_local_certified_tests


def _append_trusted_case(out: List[Dict[str, Any]], *, input_text: str, output_text: str, case_type: str, description: str) -> None:
    normalized_input = str(input_text or "")
    normalized_output = str(output_text or "")
    if not normalized_input.strip():
        return
    out.append(
        {
            "input": normalized_input,
            "expected_output": normalized_output,
            "type": case_type,
            "description": description,
            "trust_tier": "trusted",
        }
    )


def bootstrap_tests_node(state: Dict[str, Any]) -> Dict[str, Any]:
    events.emit_node_enter("bootstrap_tests", "top")
    problem = state.get("problem", {}) or {}
    tests_patch = dict(state.get("tests", {}) or {})
    generated_tests: List[Dict[str, Any]] = []

    for public_case in problem.get("public_tests", []) or []:
        _append_trusted_case(
            generated_tests,
            input_text=public_case.get("input", ""),
            output_text=public_case.get("output", ""),
            case_type="public",
            description="Public test case",
        )

    problem_desc = problem.get("description", "")
    for local_case in build_local_certified_tests(problem_desc):
        _append_trusted_case(
            generated_tests,
            input_text=local_case.get("input", ""),
            output_text=local_case.get("output", ""),
            case_type=local_case.get("type", "edge"),
            description=local_case.get("description", "Local exact certification case"),
        )

    for counterexample in (state.get("failure_bank_context", {}) or {}).get("retrieved_counterexamples", []) or []:
        _append_trusted_case(
            generated_tests,
            input_text=counterexample.get("input_text", ""),
            output_text=counterexample.get("expected_output", ""),
            case_type="failure_bank",
            description=f"Historical trusted {counterexample.get('failure_type', 'failure')} counterexample",
        )

    trust_counts = Counter(test["trust_tier"] for test in generated_tests)
    tests_patch.update(
        {
            "generated_tests": generated_tests,
            "total_tests": len(generated_tests),
            "ready": True,
            "pending_execution": False,
            "full_testgen_completed": False,
            "trust_tiers": dict(trust_counts),
        }
    )
    return {
        "tests": tests_patch,
        "execution_log": [f"Bootstrap tests prepared: {len(generated_tests)} trusted cases"],
    }
```

- [ ] **Step 4: Annotate heavy test generation with trust tiers and completion state**

In `src/nodes/generate_tests.py`, import `build_local_certified_tests` from the new utility and mark generated tests explicitly:

```python
generated_tests.append(
    {
        "input": pt.get("input", ""),
        "expected_output": pt.get("output", ""),
        "type": "public",
        "description": "Public test case",
        "trust_tier": "trusted",
    }
)
...
generated_tests.append(
    {
        "input": pt.get("input", ""),
        "expected_output": pt.get("output", ""),
        "type": pt.get("type", "edge"),
        "description": pt.get("description", "Local exact certification case"),
        "trust_tier": "trusted",
    }
)
...
generated_tests.append(
    {
        "input": inp,
        "expected_output": out,
        "type": "generated",
        "description": "Generated test case",
        "trust_tier": "advisory",
    }
)
```

Set the summary fields near the final `tests = { ... }` payload:

```python
from collections import Counter

trust_counts = Counter(test.get("trust_tier", "advisory") for test in generated_tests)
tests = {
    ...
    "full_testgen_completed": True,
    "trust_tiers": dict(trust_counts),
    ...
}
```

Export the new node in `src/nodes/__init__.py`:

```python
elif name == "bootstrap_tests_node":
    from .bootstrap_tests import bootstrap_tests_node
    return bootstrap_tests_node
```

and add `"bootstrap_tests_node"` to `__all__`.

- [ ] **Step 5: Run the bootstrap and heavy-testgen trust-tier tests**

Run: `pytest tests/nodes/test_bootstrap_tests.py tests/nodes/test_generate_tests_oracle_status.py -v`

Expected: PASS

- [ ] **Step 6: Commit the bootstrap-tests change**

```bash
git add src/utils/test_seed_cases.py src/nodes/bootstrap_tests.py src/nodes/generate_tests.py src/nodes/__init__.py tests/nodes/test_bootstrap_tests.py tests/nodes/test_generate_tests_oracle_status.py
git commit -m "feat: add bootstrap tests and trust tiers"
```

### Task 3: Add Failure-Bank Storage and Lookup

**Files:**
- Create: `src/failure_bank/__init__.py`
- Create: `src/failure_bank/service.py`
- Create: `src/nodes/failure_bank_lookup.py`
- Modify: `src/nodes/__init__.py`
- Test: `tests/failure_bank/test_service.py`
- Test: `tests/nodes/test_failure_bank_lookup.py`

- [ ] **Step 1: Write the failing failure-bank service and lookup-node tests**

```python
from pathlib import Path

from src.failure_bank.service import FailureBankService
from src.graph.state import create_initial_state
from src.nodes.failure_bank_lookup import failure_bank_lookup_node


def test_failure_bank_service_stores_and_retrieves_context(tmp_path: Path):
    service = FailureBankService(tmp_path)
    service.initialize()
    service.record_risk_pattern(
        {
            "pattern_id": "pattern.cyclic.counting",
            "title": "Cyclic counting over-count",
            "applicable_tags": ["dp", "math"],
            "trigger_features": ["cyclic", "counting"],
            "anti_pattern_text": "Do not linearize cyclic set semantics without proof.",
            "recommended_checks": ["full_cycle_dedup", "wraparound_cases"],
            "evidence_case_ids": [],
        }
    )
    service.record_failure_case(
        {
            "canonical_objective": "Count valid cyclic segments",
            "tags_level1": ["dp", "math"],
            "tags_level2": ["cyclic_convolution"],
            "constraint_bucket": "n<=2e5",
            "phase_found": "verifier",
            "failure_type": "WA",
            "failure_subtype": "cyclic_overcount",
            "input_text": "1 3 2\n1\n",
            "expected_output": "1\n",
            "actual_output": "3\n",
            "checker_context": "",
            "trusted_level": "high",
            "source_run_id": "run-1",
            "source_solution_hash": "hash-1",
            "explanation": "Full cycle counted multiple times.",
            "minimized": True,
        }
    )

    context = service.lookup_context(
        canonical_objective="Count valid cyclic segments",
        tags_level1=["dp", "math"],
        tags_level2=["cyclic_convolution"],
        lookup_limit=3,
    )

    assert context["matched_patterns"][0]["pattern_id"] == "pattern.cyclic.counting"
    assert context["retrieved_counterexamples"][0]["failure_subtype"] == "cyclic_overcount"
    assert "Do not linearize cyclic set semantics without proof." in context["anti_patterns"]


def test_failure_bank_lookup_node_reads_context_from_configured_store(tmp_path: Path):
    service = FailureBankService(tmp_path)
    service.initialize()
    service.record_failure_case(
        {
            "canonical_objective": "Count paths",
            "tags_level1": ["graphs"],
            "tags_level2": [],
            "constraint_bucket": "n<=1e5",
            "phase_found": "hacker",
            "failure_type": "TLE",
            "failure_subtype": "quadratic_paths",
            "input_text": "5 4\n1 2\n2 3\n3 4\n4 5\n",
            "expected_output": "4\n",
            "actual_output": "timeout",
            "checker_context": "",
            "trusted_level": "high",
            "source_run_id": "run-2",
            "source_solution_hash": "hash-2",
            "explanation": "Nested loop over all pairs.",
            "minimized": True,
        }
    )

    state = create_initial_state(
        raw_problem={"description": "Count paths", "public_tests": []},
        config={"failure_bank": {"data_dir": str(tmp_path), "lookup_limit": 2}},
    )
    state["problem"]["canonical"] = {"objective": "Count paths"}
    state["problem"]["tags_selected"] = ["graphs"]

    update = failure_bank_lookup_node(state)

    assert update["failure_bank_context"]["retrieved_counterexamples"][0]["failure_subtype"] == "quadratic_paths"
```

- [ ] **Step 2: Run the failure-bank tests to confirm the package does not exist**

Run: `pytest tests/failure_bank/test_service.py tests/nodes/test_failure_bank_lookup.py -v`

Expected: FAIL with `ModuleNotFoundError: src.failure_bank` and missing node import.

- [ ] **Step 3: Implement the SQLite service and lookup node**

Create `src/failure_bank/__init__.py`:

```python
from .service import FailureBankService

__all__ = ["FailureBankService"]
```

Create `src/failure_bank/service.py`:

```python
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List


class FailureBankService:
    def __init__(self, data_dir: str | Path) -> None:
        self.root = Path(data_dir)
        self.db_path = self.root / "failure_bank.db"

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS failure_cases (
                    case_id TEXT PRIMARY KEY,
                    canonical_objective TEXT,
                    tags_level1_json TEXT,
                    tags_level2_json TEXT,
                    constraint_bucket TEXT,
                    phase_found TEXT,
                    failure_type TEXT,
                    failure_subtype TEXT,
                    input_text TEXT,
                    expected_output TEXT,
                    actual_output TEXT,
                    checker_context TEXT,
                    trusted_level TEXT,
                    source_run_id TEXT,
                    source_solution_hash TEXT,
                    explanation TEXT,
                    minimized INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS risk_patterns (
                    pattern_id TEXT PRIMARY KEY,
                    title TEXT,
                    applicable_tags_json TEXT,
                    trigger_features_json TEXT,
                    anti_pattern_text TEXT,
                    recommended_checks_json TEXT,
                    evidence_case_ids_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS repair_outcomes (
                    repair_id TEXT PRIMARY KEY,
                    linked_case_ids_json TEXT,
                    repair_strategy TEXT,
                    repair_summary TEXT,
                    before_solution_hash TEXT,
                    after_solution_hash TEXT,
                    validated INTEGER
                )
                """
            )

    def record_failure_case(self, payload: Dict[str, Any]) -> str:
        canonical_objective = str(payload.get("canonical_objective", "") or "")
        input_text = str(payload.get("input_text", "") or "")
        actual_output = str(payload.get("actual_output", "") or "")
        raw_key = f"{canonical_objective}\n{input_text}\n{actual_output}"
        case_id = str(payload.get("case_id") or hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:20])
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO failure_cases (
                    case_id, canonical_objective, tags_level1_json, tags_level2_json, constraint_bucket,
                    phase_found, failure_type, failure_subtype, input_text, expected_output, actual_output,
                    checker_context, trusted_level, source_run_id, source_solution_hash, explanation, minimized
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    canonical_objective,
                    json.dumps(payload.get("tags_level1", [])),
                    json.dumps(payload.get("tags_level2", [])),
                    str(payload.get("constraint_bucket", "") or ""),
                    str(payload.get("phase_found", "") or ""),
                    str(payload.get("failure_type", "") or ""),
                    str(payload.get("failure_subtype", "") or ""),
                    input_text,
                    str(payload.get("expected_output", "") or ""),
                    actual_output,
                    str(payload.get("checker_context", "") or ""),
                    str(payload.get("trusted_level", "high") or "high"),
                    str(payload.get("source_run_id", "") or ""),
                    str(payload.get("source_solution_hash", "") or ""),
                    str(payload.get("explanation", "") or ""),
                    int(bool(payload.get("minimized", False))),
                ),
            )
        return case_id

    def record_risk_pattern(self, payload: Dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO risk_patterns (
                    pattern_id, title, applicable_tags_json, trigger_features_json,
                    anti_pattern_text, recommended_checks_json, evidence_case_ids_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload["pattern_id"]),
                    str(payload.get("title", "")),
                    json.dumps(payload.get("applicable_tags", [])),
                    json.dumps(payload.get("trigger_features", [])),
                    str(payload.get("anti_pattern_text", "")),
                    json.dumps(payload.get("recommended_checks", [])),
                    json.dumps(payload.get("evidence_case_ids", [])),
                ),
            )

    def lookup_context(self, *, canonical_objective: str, tags_level1: List[str], tags_level2: List[str], lookup_limit: int) -> Dict[str, Any]:
        tags = set(tags_level1 or []) | set(tags_level2 or [])
        matched_patterns: List[Dict[str, Any]] = []
        counterexamples: List[Dict[str, Any]] = []
        with sqlite3.connect(self.db_path) as conn:
            for row in conn.execute("SELECT * FROM risk_patterns").fetchall():
                applicable_tags = json.loads(row[2] or "[]")
                if tags.intersection(applicable_tags):
                    matched_patterns.append(
                        {
                            "pattern_id": row[0],
                            "title": row[1],
                            "applicable_tags": applicable_tags,
                            "trigger_features": json.loads(row[3] or "[]"),
                            "anti_pattern_text": row[4],
                            "recommended_checks": json.loads(row[5] or "[]"),
                            "evidence_case_ids": json.loads(row[6] or "[]"),
                        }
                    )
            for row in conn.execute(
                """
                SELECT case_id, failure_subtype, input_text, expected_output, actual_output, failure_type, explanation
                FROM failure_cases
                WHERE canonical_objective = ? OR tags_level1_json LIKE ?
                LIMIT ?
                """,
                (canonical_objective, f"%{next(iter(tags), '')}%", lookup_limit),
            ).fetchall():
                counterexamples.append(
                    {
                        "case_id": row[0],
                        "failure_subtype": row[1],
                        "input_text": row[2],
                        "expected_output": row[3],
                        "actual_output": row[4],
                        "failure_type": row[5],
                        "explanation": row[6],
                    }
                )
        return {
            "matched_patterns": matched_patterns[:lookup_limit],
            "retrieved_counterexamples": counterexamples[:lookup_limit],
            "anti_patterns": [pattern["anti_pattern_text"] for pattern in matched_patterns[:lookup_limit] if pattern.get("anti_pattern_text")],
            "repair_summaries": [],
            "source_case_ids": [item["case_id"] for item in counterexamples[:lookup_limit]],
        }
```

Create `src/nodes/failure_bank_lookup.py`:

```python
from __future__ import annotations

from typing import Any, Dict

import src.events as events
from src.failure_bank import FailureBankService


def failure_bank_lookup_node(state: Dict[str, Any]) -> Dict[str, Any]:
    events.emit_node_enter("failure_bank_lookup", "top")
    config = (state.get("config") or {}).get("failure_bank", {}) or {}
    if not bool(config.get("enabled", True)):
        return {
            "failure_bank_context": {
                "matched_patterns": [],
                "retrieved_counterexamples": [],
                "anti_patterns": [],
                "repair_summaries": [],
                "source_case_ids": [],
            }
        }

    service = FailureBankService(config.get("data_dir", "artifacts/failure_bank"))
    service.initialize()
    problem = state.get("problem", {}) or {}
    canonical = problem.get("canonical", {}) or {}
    context = service.lookup_context(
        canonical_objective=str(canonical.get("objective", "") or problem.get("description", "")),
        tags_level1=list(problem.get("tags_selected", []) or []),
        tags_level2=list(problem.get("tags_level2_selected", []) or []),
        lookup_limit=int(config.get("lookup_limit", 3) or 3),
    )
    return {
        "failure_bank_context": context,
        "execution_log": [
            f"Failure bank lookup: patterns={len(context['matched_patterns'])} counterexamples={len(context['retrieved_counterexamples'])}"
        ],
    }
```

Export the node in `src/nodes/__init__.py`.

- [ ] **Step 4: Run the failure-bank tests**

Run: `pytest tests/failure_bank/test_service.py tests/nodes/test_failure_bank_lookup.py -v`

Expected: PASS

- [ ] **Step 5: Commit the failure-bank lookup change**

```bash
git add src/failure_bank/__init__.py src/failure_bank/service.py src/nodes/failure_bank_lookup.py src/nodes/__init__.py tests/failure_bank/test_service.py tests/nodes/test_failure_bank_lookup.py
git commit -m "feat: add failure bank lookup service"
```

### Task 4: Add the Verifier Phase

**Files:**
- Create: `src/nodes/verifier_phase.py`
- Test: `tests/nodes/test_verifier_phase.py`

- [ ] **Step 1: Write the failing verifier decision tests**

```python
from pathlib import Path

from src.graph.state import create_initial_state
from src.nodes.verifier_phase import verifier_phase_node


def test_verifier_repairs_on_trusted_test_failure(tmp_path: Path):
    state = create_initial_state(
        raw_problem={"description": "Example", "public_tests": []},
        config={},
    )
    state["solution"]["executable_path"] = str(tmp_path / "dummy.exe")
    state["tests"]["generated_tests"] = [
        {
            "input": "1\n",
            "expected_output": "2\n",
            "trust_tier": "trusted",
            "type": "public",
            "description": "Public test",
        }
    ]
    state["tests"]["ready"] = True

    update = verifier_phase_node(
        state,
        run_program_fn=lambda *_args, **_kwargs: (0, "1\n", ""),
    )

    assert update["verification"]["decision"] == "repair"
    assert "trusted_suite_failed" in update["verification"]["risk_flags"]
    assert update["verification"]["trusted_failures"][0]["expected_output"] == "2\n"


def test_verifier_escalates_when_complexity_risk_is_high(tmp_path: Path):
    state = create_initial_state(raw_problem={"description": "Example", "public_tests": []}, config={})
    state["solution"]["code"] = "int main(){ for(int i=0;i<n;i++) for(int j=0;j<n;j++){} }"
    state["problem"]["constraints"] = {"n": "2e5"}
    state["solution"]["executable_path"] = str(tmp_path / "dummy.exe")
    state["tests"]["generated_tests"] = []
    state["tests"]["ready"] = True

    update = verifier_phase_node(state)

    assert update["verification"]["decision"] == "escalate_testgen"
    assert "possible_quadratic_on_large_n" in update["verification"]["risk_flags"]


def test_verifier_accepts_low_risk_candidate(tmp_path: Path):
    state = create_initial_state(raw_problem={"description": "Example", "public_tests": []}, config={})
    state["solution"]["code"] = "int main(){return 0;}"
    state["solution"]["executable_path"] = str(tmp_path / "dummy.exe")
    state["tests"]["generated_tests"] = []
    state["tests"]["ready"] = True

    update = verifier_phase_node(state, run_program_fn=lambda *_args, **_kwargs: (0, "", ""))

    assert update["verification"]["decision"] == "accept"
    assert update["verification"]["confidence"] > 0.0
```

- [ ] **Step 2: Run the verifier tests to confirm the node is missing**

Run: `pytest tests/nodes/test_verifier_phase.py -v`

Expected: FAIL with `ModuleNotFoundError: src.nodes.verifier_phase`.

- [ ] **Step 3: Implement the verifier node and its helper checks**

Create `src/nodes/verifier_phase.py`:

```python
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import src.events as events
from src.utils.cpp_execution import ExecutionLimits, run_program


def _trusted_tests(tests: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [test for test in tests if test.get("trust_tier", "advisory") == "trusted"]


def _run_trusted_suite(exe_path: Path, tests: List[Dict[str, Any]], run_program_fn=run_program) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
    for test in _trusted_tests(tests):
        retcode, stdout, stderr = run_program_fn(
            exe_path,
            input_text=test.get("input", ""),
            limits=ExecutionLimits.default_run(),
        )
        expected_output = str(test.get("expected_output", "") or "")
        if retcode != 0 or stdout.strip() != expected_output.strip():
            failures.append(
                {
                    "input_text": test.get("input", ""),
                    "expected_output": expected_output,
                    "actual_output": stdout,
                    "stderr": stderr,
                    "failure_type": "WA" if retcode == 0 else "RE",
                    "source_type": test.get("type", "trusted"),
                }
            )
    return failures


def _complexity_risk_flags(code: str, constraints: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    rendered_constraints = str(constraints or {}).lower()
    loop_count = len(re.findall(r"\\bfor\\b|\\bwhile\\b", code or ""))
    if loop_count >= 2 and any(token in rendered_constraints for token in ("1e5", "10^5", "100000", "2e5", "200000")):
        flags.append("possible_quadratic_on_large_n")
    if "vector<vector" in (code or "") and any(token in rendered_constraints for token in ("1e5", "10^5", "100000")):
        flags.append("possible_dense_memory")
    return flags


def _risk_pattern_flags(state: Dict[str, Any]) -> List[str]:
    flags: List[str] = []
    for pattern in (state.get("failure_bank_context", {}) or {}).get("matched_patterns", []) or []:
        flags.extend(str(item) for item in pattern.get("recommended_checks", []) or [])
    return flags


def verifier_phase_node(
    state: Dict[str, Any],
    *,
    run_program_fn=run_program,
) -> Dict[str, Any]:
    events.emit_node_enter("verifier_phase", "top")
    events.emit("phase_start", phase="verifier_phase", label="Independent Verification")

    tests = list((state.get("tests", {}) or {}).get("generated_tests", []) or [])
    exe_path_raw = (state.get("solution", {}) or {}).get("executable_path")
    exe_path = Path(exe_path_raw) if exe_path_raw else None
    code = str((state.get("solution", {}) or {}).get("code", "") or "")
    constraints = (state.get("problem", {}) or {}).get("constraints", {}) or {}

    trusted_failures: List[Dict[str, Any]] = []
    if exe_path is not None and exe_path.exists() and tests:
        trusted_failures = _run_trusted_suite(exe_path, tests, run_program_fn=run_program_fn)
    elif exe_path_raw and tests:
        trusted_failures = _run_trusted_suite(Path(exe_path_raw), tests, run_program_fn=run_program_fn)

    if trusted_failures:
        verification = {
            "decision": "repair",
            "confidence": 1.0,
            "risk_flags": ["trusted_suite_failed"],
            "new_tests": [],
            "feedback_summary": "Trusted verification suite exposed a mismatch.",
            "trusted_failures": trusted_failures,
            "open_failure_case_ids": [],
        }
        events.emit("phase_done", phase="verifier_phase", label="Independent Verification", data={"decision": "repair"})
        return {"verification": verification}

    risk_flags = _complexity_risk_flags(code, constraints)
    risk_flags.extend(_risk_pattern_flags(state))
    if risk_flags:
        verification = {
            "decision": "escalate_testgen",
            "confidence": 0.7,
            "risk_flags": risk_flags,
            "new_tests": [],
            "feedback_summary": "No trusted counterexample found, but risk remains too high for acceptance.",
            "trusted_failures": [],
            "open_failure_case_ids": [],
        }
        events.emit("phase_done", phase="verifier_phase", label="Independent Verification", data={"decision": "escalate_testgen"})
        return {"verification": verification}

    verification = {
        "decision": "accept",
        "confidence": 0.9,
        "risk_flags": [],
        "new_tests": [],
        "feedback_summary": "Trusted checks passed and no strong residual risk was detected.",
        "trusted_failures": [],
        "open_failure_case_ids": [],
    }
    events.emit("phase_done", phase="verifier_phase", label="Independent Verification", data={"decision": "accept"})
    return {"verification": verification}
```

- [ ] **Step 4: Run the verifier tests**

Run: `pytest tests/nodes/test_verifier_phase.py -v`

Expected: PASS

- [ ] **Step 5: Commit the verifier change**

```bash
git add src/nodes/verifier_phase.py tests/nodes/test_verifier_phase.py
git commit -m "feat: add verifier phase"
```

### Task 5: Add the Solve Controller and Wire the Workflow

**Files:**
- Create: `src/nodes/solve_controller.py`
- Modify: `src/nodes/__init__.py`
- Modify: `src/nodes/routing.py`
- Modify: `src/graph/workflow.py`
- Modify: `dashboard/dag-definition.json`
- Test: `tests/nodes/test_solve_controller.py`
- Test: `tests/graph/test_pass1_workflow.py`

- [ ] **Step 1: Write the failing controller and workflow-routing tests**

```python
from src.graph.state import create_initial_state
from src.graph.workflow import create_solvita_workflow
from src.nodes.solve_controller import pre_solve_controller_node, post_verify_controller_node


def test_pre_solve_controller_skips_full_testgen_for_low_risk_problem():
    state = create_initial_state(
        raw_problem={"description": "Add two numbers", "public_tests": [{"input": "1 2\n", "output": "3\n"}]},
        config={},
    )
    state["problem"]["canonical"] = {"objective": "Add two integers"}
    state["problem"]["abstract_confidence"] = 0.95
    state["problem"]["tags_selected"] = ["implementation"]

    update = pre_solve_controller_node(state)

    assert update["solve_policy"]["run_testgen_initially"] is False
    assert update["solve_policy"]["allow_hacker"] is False


def test_pre_solve_controller_escalates_high_risk_cyclic_problem():
    state = create_initial_state(raw_problem={"description": "Count cyclic segments", "public_tests": []}, config={})
    state["problem"]["canonical"] = {"objective": "Count cyclic segments"}
    state["problem"]["abstract_confidence"] = 0.60
    state["problem"]["tags_selected"] = ["dp", "math"]
    state["problem"]["tags_level2_selected"] = ["cyclic_convolution"]
    state["failure_bank_context"]["matched_patterns"] = [{"pattern_id": "pattern.cyclic.counting"}]

    update = pre_solve_controller_node(state)

    assert update["solve_policy"]["run_testgen_initially"] is True
    assert update["solve_policy"]["verifier_mode"] == "strict"


def test_post_verify_controller_requests_repair_and_bumps_iteration():
    state = create_initial_state(raw_problem={"description": "Example", "public_tests": []}, config={})
    state["iteration"] = 1
    state["verification"] = {"decision": "repair", "confidence": 1.0, "risk_flags": ["trusted_suite_failed"], "new_tests": [], "feedback_summary": "", "trusted_failures": [], "open_failure_case_ids": []}

    update = post_verify_controller_node(state)

    assert update["solve_policy"]["next_action"] == "repair"
    assert update["iteration"] == 2
    assert update["status"] == "pending"


def test_pass1_workflow_compiles_with_new_nodes():
    workflow = create_solvita_workflow()
    assert workflow is not None
```

- [ ] **Step 2: Run the controller/workflow tests to verify the new nodes and routes are absent**

Run: `pytest tests/nodes/test_solve_controller.py tests/graph/test_pass1_workflow.py -v`

Expected: FAIL with missing `solve_controller` node and unchanged workflow routing.

- [ ] **Step 3: Implement the rule-based pre/post controller nodes**

Create `src/nodes/solve_controller.py`:

```python
from __future__ import annotations

from typing import Any, Dict, List

import src.events as events


HIGH_RISK_LEVEL1 = {"dp", "graphs", "math", "strings"}
HIGH_RISK_LEVEL2 = {"cyclic_convolution", "dsu_on_tree", "divide_and_conquer_dp", "implicit_segment_tree"}


def _risk_score(state: Dict[str, Any]) -> float:
    problem = state.get("problem", {}) or {}
    score = 0.0
    if float(problem.get("abstract_confidence", 0.0) or 0.0) < 0.75:
        score += 1.0
    tags_level1 = set(problem.get("tags_selected", []) or [])
    tags_level2 = set(problem.get("tags_level2_selected", []) or [])
    score += 0.5 * len(tags_level1.intersection(HIGH_RISK_LEVEL1))
    score += 1.0 * len(tags_level2.intersection(HIGH_RISK_LEVEL2))
    score += 1.0 * len((state.get("failure_bank_context", {}) or {}).get("matched_patterns", []) or [])
    if not (problem.get("public_tests", []) or []):
        score += 0.5
    return score


def pre_solve_controller_node(state: Dict[str, Any]) -> Dict[str, Any]:
    events.emit_node_enter("pre_solve_controller", "top")
    score = _risk_score(state)
    benchmark_mode = bool((state.get("config", {}) or {}).get("benchmark_output_dir"))
    solver_network_cfg = (state.get("config", {}) or {}).get("solver_network", {}) or {}
    run_skill_plan = bool(solver_network_cfg.get("enabled")) and score >= 1.5
    solve_policy = {
        "risk_score": score,
        "run_testgen_initially": score >= 2.5,
        "run_skill_plan": run_skill_plan,
        "initial_codegen_budget": 1 if score < 2.5 else 2,
        "verifier_mode": "strict" if score >= 2.5 else "standard",
        "allow_hacker": (not benchmark_mode) and score >= 3.0,
        "escalate_after_failures": 1,
        "generated_test_target_scale": 50 if score >= 2.5 else 0,
        "next_action": "",
    }
    return {
        "solve_policy": solve_policy,
        "execution_log": [f"Pre-solve controller: risk={score:.2f} run_testgen={solve_policy['run_testgen_initially']}"],
    }


def post_verify_controller_node(state: Dict[str, Any]) -> Dict[str, Any]:
    events.emit_node_enter("post_verify_controller", "top")
    verification = state.get("verification", {}) or {}
    decision = str(verification.get("decision", "") or "")
    policy = dict(state.get("solve_policy", {}) or {})

    if decision == "repair":
        policy["next_action"] = "repair"
        return {"solve_policy": policy, "status": "pending", "iteration": int(state.get("iteration", 0) or 0) + 1}
    if decision == "escalate_testgen":
        policy["next_action"] = "escalate_testgen"
        return {"solve_policy": policy, "status": "pending", "iteration": int(state.get("iteration", 0) or 0) + 1}
    if policy.get("allow_hacker", False):
        policy["next_action"] = "accept_hack"
    else:
        policy["next_action"] = "accept_end"
    return {"solve_policy": policy}
```

- [ ] **Step 4: Rewire the workflow, routing helpers, and dashboard DAG**

Add exports in `src/nodes/__init__.py`:

```python
elif name == "failure_bank_lookup_node":
    from .failure_bank_lookup import failure_bank_lookup_node
    return failure_bank_lookup_node
elif name == "bootstrap_tests_node":
    from .bootstrap_tests import bootstrap_tests_node
    return bootstrap_tests_node
elif name == "verifier_phase_node":
    from .verifier_phase import verifier_phase_node
    return verifier_phase_node
elif name == "pre_solve_controller_node":
    from .solve_controller import pre_solve_controller_node
    return pre_solve_controller_node
elif name == "post_verify_controller_node":
    from .solve_controller import post_verify_controller_node
    return post_verify_controller_node
elif name == "bootstrap_routing":
    from .routing import bootstrap_routing
    return bootstrap_routing
elif name == "plan_or_codegen_routing":
    from .routing import plan_or_codegen_routing
    return plan_or_codegen_routing
elif name == "post_verify_routing":
    from .routing import post_verify_routing
    return post_verify_routing
```

Replace the direct-success routing helpers in `src/nodes/routing.py`:

```python
def post_codegen_routing(state: Dict[str, Any]) -> str:
    return "to_verifier" if state.get("status", "pending") == "success" else "end"


def bootstrap_routing(state: Dict[str, Any]) -> str:
    policy = state.get("solve_policy", {}) or {}
    if bool(policy.get("run_testgen_initially", False)):
        return "run_full_testgen"
    return "skip_full_testgen"


def plan_or_codegen_routing(state: Dict[str, Any]) -> str:
    policy = state.get("solve_policy", {}) or {}
    if bool(policy.get("run_skill_plan", False)):
        return "skill_plan"
    return "direct_codegen"


def post_verify_routing(state: Dict[str, Any]) -> str:
    action = str((state.get("solve_policy", {}) or {}).get("next_action", "") or "")
    if action in {"repair", "escalate_testgen", "accept_hack", "accept_end"}:
        return action
    return "accept_end"
```

Rewire the top-level graph in `src/graph/workflow.py`:

```python
workflow.add_node("failure_bank_lookup", failure_bank_lookup_node)
workflow.add_node("pre_solve_controller", pre_solve_controller_node)
workflow.add_node("bootstrap_tests", bootstrap_tests_node)
workflow.add_node("verifier_phase", verifier_phase_node)
workflow.add_node("post_verify_controller", post_verify_controller_node)

workflow.set_entry_point("abstract_phase")
workflow.add_edge("abstract_phase", "failure_bank_lookup")
workflow.add_edge("failure_bank_lookup", "pre_solve_controller")
workflow.add_edge("pre_solve_controller", "phase_transition_0")
workflow.add_edge("phase_transition_0", "bootstrap_tests")
workflow.add_conditional_edges(
    "bootstrap_tests",
    bootstrap_routing,
    {
        "run_full_testgen": "testgen_phase",
        "skip_full_testgen": "phase_transition_1",
    },
)
workflow.add_edge("testgen_phase", "phase_transition_1")
workflow.add_conditional_edges(
    "phase_transition_1",
    plan_or_codegen_routing,
    {
        "skill_plan": "solver_skill_plan",
        "direct_codegen": "codegen_phase",
    },
)
workflow.add_edge("solver_skill_plan", "codegen_phase")
workflow.add_conditional_edges(
    "codegen_phase",
    post_codegen_routing,
    {
        "to_verifier": "verifier_phase",
        "end": END,
    },
)
workflow.add_edge("verifier_phase", "post_verify_controller")
workflow.add_conditional_edges(
    "post_verify_controller",
    post_verify_routing,
    {
        "repair": "codegen_phase",
        "escalate_testgen": "testgen_phase",
        "accept_hack": "phase_transition_2",
        "accept_end": END,
    },
)
```

Update `dashboard/dag-definition.json` so the top-level node list and edge list include:

```json
{ "id": "failure_bank_lookup", "label": "Failure Bank Lookup", "type": "node" },
{ "id": "pre_solve_controller", "label": "Pre-Solve Controller", "type": "node" },
{ "id": "bootstrap_tests", "label": "Bootstrap Tests", "type": "node" },
{ "id": "verifier_phase", "label": "Independent Verification", "type": "node" },
{ "id": "post_verify_controller", "label": "Post-Verify Controller", "type": "node" }
```

and the matching edges around `abstract_phase`, `codegen_phase`, and `phase_transition_2`.

- [ ] **Step 5: Run the controller/workflow tests**

Run: `pytest tests/nodes/test_solve_controller.py tests/graph/test_pass1_workflow.py tests/regression/test_workflow_import_regression.py -v`

Expected: PASS

- [ ] **Step 6: Commit the controller/workflow change**

```bash
git add src/nodes/solve_controller.py src/nodes/__init__.py src/nodes/routing.py src/graph/workflow.py dashboard/dag-definition.json tests/nodes/test_solve_controller.py tests/graph/test_pass1_workflow.py
git commit -m "feat: add pass1 controller workflow"
```

### Task 6: Add Failure-Bank Writeback and Benchmark Metrics

**Files:**
- Modify: `src/failure_bank/service.py`
- Modify: `src/nodes/verifier_phase.py`
- Modify: `src/nodes/solve_controller.py`
- Modify: `src/nodes/hack_test.py`
- Modify: `src/benchmark/types.py`
- Modify: `src/benchmark/modes/pipeline.py`
- Modify: `src/benchmark/reporting.py`
- Test: `tests/failure_bank/test_service.py`
- Modify: `tests/nodes/test_solve_controller.py`
- Test: `tests/benchmark/test_pipeline_verification_metrics.py`
- Modify: `tests/benchmark/test_reporting.py`

- [ ] **Step 1: Write the failing writeback and benchmark-metric tests**

```python
from pathlib import Path

from src.failure_bank.service import FailureBankService
from src.benchmark.reporting import summarize_results
from src.benchmark.types import BenchmarkResult


def test_failure_bank_records_repair_outcomes(tmp_path: Path):
    service = FailureBankService(tmp_path)
    service.initialize()
    repair_id = service.record_repair_outcome(
        linked_case_ids=["case-1"],
        repair_strategy="verifier_repair",
        repair_summary="Switched from quadratic scan to prefix sums.",
        before_solution_hash="before",
        after_solution_hash="after",
        validated=True,
    )

    assert repair_id
    assert service.list_repair_outcomes()[0]["repair_strategy"] == "verifier_repair"


def test_reporting_includes_false_accept_and_verifier_rates():
    rows = [
        BenchmarkResult(
            problem_id="p1",
            mode="solvita_pipeline",
            status="success",
            compile_success=True,
            passed_tests=10,
            total_tests=10,
            elapsed_total_s=1.0,
            llm_infer_s=0.5,
            error=None,
            verifier_decision="accept",
            verifier_confidence=0.9,
            false_accept=False,
            full_testgen_completed=False,
        ),
        BenchmarkResult(
            problem_id="p2",
            mode="solvita_pipeline",
            status="success",
            compile_success=True,
            passed_tests=5,
            total_tests=10,
            elapsed_total_s=1.2,
            llm_infer_s=0.6,
            error="WA",
            verifier_decision="accept",
            verifier_confidence=0.8,
            false_accept=True,
            full_testgen_completed=True,
        ),
    ]

    summary = summarize_results(rows)

    assert summary["modes"]["solvita_pipeline"]["false_accept_rate"] == 0.5
    assert summary["modes"]["solvita_pipeline"]["verifier_accept_rate"] == 1.0
    assert summary["modes"]["solvita_pipeline"]["full_testgen_completion_rate"] == 0.5


def test_post_verify_controller_records_repair_outcome_on_accept(tmp_path: Path):
    from src.graph.state import create_initial_state
    from src.nodes.solve_controller import post_verify_controller_node

    state = create_initial_state(
        raw_problem={"description": "Example", "public_tests": []},
        config={"failure_bank": {"data_dir": str(tmp_path)}},
    )
    state["verification"] = {
        "decision": "accept",
        "confidence": 0.9,
        "risk_flags": [],
        "new_tests": [],
        "feedback_summary": "Trusted mismatch fixed after verifier-driven repair.",
        "trusted_failures": [],
        "open_failure_case_ids": ["case-1"],
    }
    state["solve_policy"]["allow_hacker"] = False
    state["solution"]["code"] = "int main(){return 0;}"

    update = post_verify_controller_node(state)

    assert update["solve_policy"]["next_action"] == "accept_end"
    service = FailureBankService(tmp_path)
    service.initialize()
    assert service.list_repair_outcomes()[0]["linked_case_ids"] == ["case-1"]
```

- [ ] **Step 2: Run the new tests to verify the writeback and metric fields do not exist**

Run: `pytest tests/failure_bank/test_service.py tests/nodes/test_solve_controller.py tests/benchmark/test_pipeline_verification_metrics.py tests/benchmark/test_reporting.py -v`

Expected: FAIL with missing `record_repair_outcome`, missing `BenchmarkResult` fields, and missing reporting keys.

- [ ] **Step 3: Implement failure-case/repair writeback and benchmark result fields**

Extend `src/failure_bank/service.py`:

```python
def record_repair_outcome(
    self,
    *,
    linked_case_ids: List[str],
    repair_strategy: str,
    repair_summary: str,
    before_solution_hash: str,
    after_solution_hash: str,
    validated: bool,
) -> str:
    raw_key = f"{linked_case_ids}|{repair_strategy}|{after_solution_hash}"
    repair_id = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:20]
    with sqlite3.connect(self.db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO repair_outcomes (
                repair_id, linked_case_ids_json, repair_strategy, repair_summary,
                before_solution_hash, after_solution_hash, validated
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                repair_id,
                json.dumps(linked_case_ids),
                repair_strategy,
                repair_summary,
                before_solution_hash,
                after_solution_hash,
                int(validated),
            ),
        )
    return repair_id


def list_repair_outcomes(self) -> List[Dict[str, Any]]:
    with sqlite3.connect(self.db_path) as conn:
        return [
            {
                "repair_id": row[0],
                "linked_case_ids": json.loads(row[1] or "[]"),
                "repair_strategy": row[2],
                "repair_summary": row[3],
                "before_solution_hash": row[4],
                "after_solution_hash": row[5],
                "validated": bool(row[6]),
            }
            for row in conn.execute("SELECT * FROM repair_outcomes").fetchall()
        ]
```

Write verifier failures to the bank in `src/nodes/verifier_phase.py` when `trusted_failures` is non-empty:

```python
from src.failure_bank import FailureBankService

...
service = FailureBankService((state.get("config", {}) or {}).get("failure_bank", {}).get("data_dir", "artifacts/failure_bank"))
service.initialize()
case_ids = [
    service.record_failure_case(
        {
            "canonical_objective": str(((state.get("problem", {}) or {}).get("canonical", {}) or {}).get("objective", "")),
            "tags_level1": list((state.get("problem", {}) or {}).get("tags_selected", []) or []),
            "tags_level2": list((state.get("problem", {}) or {}).get("tags_level2_selected", []) or []),
            "constraint_bucket": str((state.get("problem", {}) or {}).get("constraints", {})),
            "phase_found": "verifier",
            "failure_type": failure["failure_type"],
            "failure_subtype": "trusted_suite_failed",
            "input_text": failure["input_text"],
            "expected_output": failure["expected_output"],
            "actual_output": failure["actual_output"],
            "checker_context": failure["stderr"],
            "trusted_level": "high",
            "source_run_id": "",
            "source_solution_hash": "",
            "explanation": "Verifier trusted suite mismatch.",
            "minimized": True,
        }
    )
    for failure in trusted_failures
]
verification["open_failure_case_ids"] = case_ids
```

Add hacker writeback in `src/nodes/hack_test.py` immediately after `failures` is known:

```python
from src.failure_bank import FailureBankService

...
if failures:
    service = FailureBankService((state.get("config", {}) or {}).get("failure_bank", {}).get("data_dir", "artifacts/failure_bank"))
    service.initialize()
    for failure in failures:
        service.record_failure_case(
            {
                "canonical_objective": str(((state.get("problem", {}) or {}).get("canonical", {}) or {}).get("objective", "")),
                "tags_level1": list((state.get("problem", {}) or {}).get("tags_selected", []) or []),
                "tags_level2": list((state.get("problem", {}) or {}).get("tags_level2_selected", []) or []),
                "constraint_bucket": str((state.get("problem", {}) or {}).get("constraints", {})),
                "phase_found": "hacker",
                "failure_type": str(failure.get("type", "WA")),
                "failure_subtype": str(failure.get("type", "WA")).lower(),
                "input_text": str(failure.get("input", "")),
                "expected_output": str(failure.get("expected", "")),
                "actual_output": str(failure.get("output", "")),
                "checker_context": str(failure.get("details", "")),
                "trusted_level": "high",
                "source_run_id": "",
                "source_solution_hash": "",
                "explanation": "Hacker-discovered counterexample.",
                "minimized": True,
            }
        )
```

Record completed repair outcomes in `src/nodes/solve_controller.py` when post-verifier acceptance closes previously opened verifier cases:

```python
import hashlib

from src.failure_bank import FailureBankService

...
    if policy.get("allow_hacker", False):
        policy["next_action"] = "accept_hack"
    else:
        policy["next_action"] = "accept_end"

    open_case_ids = list(verification.get("open_failure_case_ids", []) or [])
    if open_case_ids:
        service = FailureBankService((state.get("config", {}) or {}).get("failure_bank", {}).get("data_dir", "artifacts/failure_bank"))
        service.initialize()
        service.record_repair_outcome(
            linked_case_ids=open_case_ids,
            repair_strategy="verifier_repair",
            repair_summary=str(verification.get("feedback_summary", "") or "Verifier-discovered failure closed by accepted solution."),
            before_solution_hash="",
            after_solution_hash=hashlib.sha1(str((state.get("solution", {}) or {}).get("code", "")).encode("utf-8")).hexdigest(),
            validated=True,
        )
        verification_patch = dict(verification)
        verification_patch["open_failure_case_ids"] = []
        return {"solve_policy": policy, "verification": verification_patch}
    return {"solve_policy": policy}
```

Extend `BenchmarkResult` in `src/benchmark/types.py`:

```python
@dataclass(frozen=True)
class BenchmarkResult:
    ...
    verifier_decision: Optional[str] = None
    verifier_confidence: Optional[float] = None
    false_accept: Optional[bool] = None
    full_testgen_completed: Optional[bool] = None
```

Populate the new fields in `src/benchmark/modes/pipeline.py`:

```python
verification = final_state.get("verification") or {}
tests_data = final_state.get("tests") or {}
false_accept = bool(
    verification.get("decision") == "accept"
    and float(score.get("pass_rate", 0.0) or 0.0) < 1.0
)

return BenchmarkResult(
    ...
    verifier_decision=verification.get("decision"),
    verifier_confidence=float(verification.get("confidence", 0.0) or 0.0),
    false_accept=false_accept,
    full_testgen_completed=bool(tests_data.get("full_testgen_completed", False)),
)
```

Aggregate the new fields in `src/benchmark/reporting.py`:

```python
"false_accept_rate": (
    sum(1 for item in items if item.get("false_accept")) / total if total else 0.0
),
"verifier_accept_rate": (
    sum(1 for item in items if item.get("verifier_decision") == "accept") / total if total else 0.0
),
"verifier_repair_rate": (
    sum(1 for item in items if item.get("verifier_decision") == "repair") / total if total else 0.0
),
"verifier_escalation_rate": (
    sum(1 for item in items if item.get("verifier_decision") == "escalate_testgen") / total if total else 0.0
),
"full_testgen_completion_rate": (
    sum(1 for item in items if item.get("full_testgen_completed")) / total if total else 0.0
),
```

- [ ] **Step 4: Run the failure-bank and benchmark-metric tests**

Run: `pytest tests/failure_bank/test_service.py tests/nodes/test_solve_controller.py tests/benchmark/test_pipeline_verification_metrics.py tests/benchmark/test_reporting.py tests/benchmark/test_pipeline_mode.py -v`

Expected: PASS

- [ ] **Step 5: Commit the writeback and benchmark reporting change**

```bash
git add src/failure_bank/service.py src/nodes/verifier_phase.py src/nodes/solve_controller.py src/nodes/hack_test.py src/benchmark/types.py src/benchmark/modes/pipeline.py src/benchmark/reporting.py tests/failure_bank/test_service.py tests/nodes/test_solve_controller.py tests/benchmark/test_pipeline_verification_metrics.py tests/benchmark/test_reporting.py tests/benchmark/test_pipeline_mode.py
git commit -m "feat: track verifier metrics and failure bank writeback"
```

### Task 7: Run the Regression Sweep and Benchmark Smoke Tests

**Files:**
- Test: `tests/regression/test_workflow_import_regression.py`
- Test: `tests/regression/test_baseline_runtime_regressions.py`
- Test: `tests/nodes/test_generate_tests_oracle_status.py`
- Test: `tests/nodes/test_hack_test.py`
- Test: `tests/benchmark/test_benchmark_smoke.py`
- Test: `tests/benchmark/test_reporting.py`

- [ ] **Step 1: Run the focused LangGraph and node regression suite**

Run:

```bash
pytest \
  tests/graph/test_pass1_state_schema.py \
  tests/nodes/test_bootstrap_tests.py \
  tests/nodes/test_failure_bank_lookup.py \
  tests/nodes/test_verifier_phase.py \
  tests/nodes/test_solve_controller.py \
  tests/regression/test_workflow_import_regression.py \
  tests/regression/test_baseline_runtime_regressions.py \
  -v
```

Expected: PASS

- [ ] **Step 2: Run the benchmark-facing regression suite**

Run:

```bash
pytest \
  tests/benchmark/test_pipeline_mode.py \
  tests/benchmark/test_pipeline_verification_metrics.py \
  tests/benchmark/test_reporting.py \
  tests/benchmark/test_benchmark_smoke.py \
  -v
```

Expected: PASS

- [ ] **Step 3: Run one targeted benchmark smoke command**

Run:

```bash
python scripts/run_benchmark.py \
  --manifest benchmark/manifests/code-contest.jsonl \
  --output-dir benchmark_output/pass1-smoke \
  --modes solvita_pipeline \
  --limit 1
```

Expected:

- command exits `0`
- `benchmark_output/pass1-smoke/results.jsonl` exists
- `benchmark_output/pass1-smoke/summary.json` includes `false_accept_rate`

- [ ] **Step 4: Commit the final regression-proven integration**

```bash
git add .
git commit -m "test: validate pass1 benchmark workflow integration"
```

---

## Self-Review

### Spec Coverage Check

- `bootstrap_tests` is covered by Task 2.
- `failure_bank` lookup and storage are covered by Task 3.
- `verifier_phase` is covered by Task 4.
- `solve_controller` is covered by Task 5.
- workflow topology changes are covered by Task 5.
- failure-bank writeback and benchmark metrics are covered by Task 6.
- regression and benchmark smoke validation are covered by Task 7.

No spec section is left without an implementation task.

### Placeholder Scan

This plan intentionally avoids:

- `TODO`
- `TBD`
- “similar to previous task”
- unnamed commands
- unspecified files

All tasks include concrete file paths, code snippets, commands, and expected outcomes.

### Type Consistency Check

State/property names used consistently across tasks:

- `solve_policy`
- `verification`
- `failure_bank_context`
- `tests.full_testgen_completed`
- `tests.trust_tiers`
- `verifier_decision`
- `false_accept`

The workflow routing contract is also consistent:

- `repair`
- `escalate_testgen`
- `accept_hack`
- `accept_end`

---
