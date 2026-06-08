# User-Supplied Problem Forced TestGen/Hack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Force stronger solve policy for user-supplied problems: always enable full test generation, default hacker on, and still respect an explicit `workflow.hacker_enabled: false`.

**Architecture:** Introduce one small Python-side origin helper so “user supplied” is represented explicitly rather than guessed in downstream logic. Entry points attach or derive `user_supplied` metadata, and `pre_solve_controller_node` becomes the single place that turns that marker into forced `run_testgen_initially` / `allow_hacker` policy.

**Tech Stack:** Python 3, pytest, existing CLI TypeScript helpers for pasted temp JSON, FastAPI dashboard backend, existing LangGraph workflow/controller

---

## File Map

- `src/utils/problem_origin.py` (new)
  Central helper for:
  - marking a problem as user-supplied
  - checking the `user_supplied` metadata flag
  - deciding whether an input path belongs to the repository-managed problem library
- `tests/utils/test_problem_origin.py` (new)
  Pure tests for the helper behavior.
- `main.py`
  Marks `--problem-description` payloads and non-library `--input` files as user-supplied.
- `tests/test_main_entrypoint.py`
  Regression coverage for `main.py` path/text marking behavior.
- `cli/src/tempInput.ts`
  Ensure pasted CLI temp problems include `_metadata.user_supplied = true`.
- `cli/src/tempInput.test.ts`
  Assert the CLI paste payload carries the new metadata.
- `dashboard/backend/server.py`
  Ensure dashboard custom problems carry `_metadata.user_supplied = true`.
- `tests/dashboard/test_custom_problem_metadata.py` (new)
  Direct regression for `_build_custom_problem_payload(...)`.
- `src/nodes/solve_controller.py`
  Apply the forced policy when `raw_problem._metadata.user_supplied` is true.
- `tests/nodes/test_solve_controller.py`
  Assert forced full testgen and hacker behavior, including explicit hacker disable precedence.
- `cli/README.md`
  Mention that pasted/external user problems automatically get stronger verification.
- `dashboard/README.md`
  Mention that custom problems automatically receive forced full test generation and default hacker checks.

---

### Task 1: Add Problem-Origin Helper and Pure Python Tests

**Files:**
- Create: `src/utils/problem_origin.py`
- Create: `tests/utils/test_problem_origin.py`

- [ ] **Step 1: Write the failing helper tests**

```python
from pathlib import Path

from src.utils.problem_origin import (
    is_repository_problem_path,
    is_user_supplied_problem,
    mark_user_supplied_problem,
)


def test_mark_user_supplied_problem_sets_flag_and_preserves_existing_metadata():
    problem = {
        "description": "demo",
        "_metadata": {
            "source": "custom",
            "name": "Demo",
        },
    }

    marked = mark_user_supplied_problem(problem, source="cli_paste")

    assert marked is not problem
    assert marked["_metadata"]["user_supplied"] is True
    assert marked["_metadata"]["source"] == "custom"
    assert marked["_metadata"]["name"] == "Demo"
    assert "user_supplied" not in problem["_metadata"]


def test_is_user_supplied_problem_reads_metadata_flag():
    assert is_user_supplied_problem({"_metadata": {"user_supplied": True}}) is True
    assert is_user_supplied_problem({"_metadata": {"user_supplied": False}}) is False
    assert is_user_supplied_problem({}) is False


def test_is_repository_problem_path_only_matches_repo_data_problem_dir(tmp_path: Path):
    repo_root = tmp_path / "repo"
    managed_dir = repo_root / "data" / "problem"
    managed_dir.mkdir(parents=True)
    managed = managed_dir / "managed.json"
    managed.write_text("{}", encoding="utf-8")

    external_dir = tmp_path / "external"
    external_dir.mkdir()
    external = external_dir / "external.json"
    external.write_text("{}", encoding="utf-8")

    assert is_repository_problem_path(managed, repo_root=repo_root) is True
    assert is_repository_problem_path(external, repo_root=repo_root) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
./.venv/bin/python -m pytest -q tests/utils/test_problem_origin.py
```

Expected:
- FAIL with `ModuleNotFoundError: No module named 'src.utils.problem_origin'`

- [ ] **Step 3: Implement `src/utils/problem_origin.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


def mark_user_supplied_problem(problem: Mapping[str, Any], *, source: str) -> dict[str, Any]:
    copied = dict(problem)
    metadata = dict(copied.get("_metadata") or {})
    metadata["user_supplied"] = True
    metadata.setdefault("source", source)
    copied["_metadata"] = metadata
    return copied


def is_user_supplied_problem(problem: Mapping[str, Any] | None) -> bool:
    if not isinstance(problem, Mapping):
        return False
    metadata = problem.get("_metadata")
    if not isinstance(metadata, Mapping):
        return False
    return bool(metadata.get("user_supplied", False))


def is_repository_problem_path(
    problem_path: str | Path,
    *,
    repo_root: str | Path,
) -> bool:
    resolved_problem = Path(problem_path).expanduser().resolve()
    managed_root = Path(repo_root).expanduser().resolve() / "data" / "problem"

    try:
        resolved_problem.relative_to(managed_root)
    except ValueError:
        return False
    return True
```

- [ ] **Step 4: Re-run the tests**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
./.venv/bin/python -m pytest -q tests/utils/test_problem_origin.py
```

Expected:
- PASS

- [ ] **Step 5: Commit Task 1**

```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
git add src/utils/problem_origin.py tests/utils/test_problem_origin.py
git commit -m "feat: add user supplied problem origin helpers"
```

---

### Task 2: Mark `main.py` Text and External-Path Inputs as User-Supplied

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main_entrypoint.py`

- [ ] **Step 1: Write the failing `main.py` metadata tests**

```python
from pathlib import Path

import main as main_module


def test_build_problem_from_description_marks_user_supplied():
    problem = main_module.build_problem_from_description("Demo problem text")

    assert problem["_metadata"]["user_supplied"] is True
    assert problem["_metadata"]["source"] == "cli_description"


def test_load_problem_marks_external_json_as_user_supplied(tmp_path: Path, monkeypatch):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    external = tmp_path / "external.json"
    external.write_text('{"description": "demo"}', encoding="utf-8")

    monkeypatch.setattr(main_module, "PROJECT_ROOT", repo_root)

    problem = main_module.load_problem(str(external))

    assert problem["_metadata"]["user_supplied"] is True
    assert problem["_metadata"]["source"] == "cli_path"


def test_load_problem_keeps_repository_managed_problem_unmarked(tmp_path: Path, monkeypatch):
    repo_root = tmp_path / "repo"
    managed_dir = repo_root / "data" / "problem"
    managed_dir.mkdir(parents=True)
    managed = managed_dir / "managed.json"
    managed.write_text('{"description": "demo"}', encoding="utf-8")

    monkeypatch.setattr(main_module, "PROJECT_ROOT", repo_root)

    problem = main_module.load_problem(str(managed))

    assert problem.get("_metadata", {}).get("user_supplied") is not True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
./.venv/bin/python -m pytest -q tests/test_main_entrypoint.py
```

Expected:
- FAIL because `build_problem_from_description()` and `load_problem()` do not yet attach the required metadata

- [ ] **Step 3: Implement the `main.py` marking logic**

```python
from src.utils.problem_origin import (
    is_repository_problem_path,
    mark_user_supplied_problem,
)


PROJECT_ROOT = Path(__file__).resolve().parent


def load_problem(input_path: str) -> dict:
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Problem file not found: {input_path}")

    with open(path, "r", encoding="utf-8") as f:
        problem_data = json.load(f)

    if not is_repository_problem_path(path, repo_root=PROJECT_ROOT):
        problem_data = mark_user_supplied_problem(problem_data, source="cli_path")

    logger.info(f"Loaded problem from {input_path}")
    return problem_data


def build_problem_from_description(description: str) -> dict:
    return mark_user_supplied_problem(
        {
            "description": description,
            "time_limit": 2000,
            "space_limit": 256,
            "public_tests": [],
        },
        source="cli_description",
    )
```

- [ ] **Step 4: Re-run the tests**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
./.venv/bin/python -m pytest -q tests/test_main_entrypoint.py tests/utils/test_problem_origin.py
```

Expected:
- PASS

- [ ] **Step 5: Commit Task 2**

```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
git add main.py tests/test_main_entrypoint.py
git commit -m "feat: mark direct user supplied problems in main"
```

---

### Task 3: Mark CLI Paste Problems and Dashboard Custom Problems

**Files:**
- Modify: `cli/src/tempInput.ts`
- Modify: `cli/src/tempInput.test.ts`
- Modify: `dashboard/backend/server.py`
- Create: `tests/dashboard/test_custom_problem_metadata.py`

- [ ] **Step 1: Write the failing metadata tests**

```ts
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { createTempInputFile } from './tempInput.ts';

test('createTempInputFile marks pasted problems as user supplied', () => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), 'algopilot-temp-input-'));

  try {
    const inputFile = createTempInputFile('Find the maximum subarray sum.', tempRoot);
    const payload = JSON.parse(readFileSync(inputFile, 'utf8'));

    assert.equal(payload._metadata.user_supplied, true);
    assert.equal(payload._metadata.source, 'cli_paste');
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});
```

```python
from dashboard.backend.models import CustomProblemRequest, PublicTestCase
from dashboard.backend.server import _build_custom_problem_payload


def test_build_custom_problem_payload_marks_user_supplied():
    req = CustomProblemRequest(
        title="Demo",
        description="Example",
        source="custom",
        public_tests=[PublicTestCase(input="1\n", output="1\n")],
    )

    _, payload = _build_custom_problem_payload(req)

    assert payload["_metadata"]["custom"] is True
    assert payload["_metadata"]["user_supplied"] is True
    assert payload["_metadata"]["source"] == "custom"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
cd cli && npm test -- src/tempInput.test.ts
cd ..
./.venv/bin/python -m pytest -q tests/dashboard/test_custom_problem_metadata.py
```

Expected:
- CLI temp input test FAIL because `_metadata.user_supplied` is absent
- Python dashboard test FAIL because `_build_custom_problem_payload` does not set the flag

- [ ] **Step 3: Implement entry-point metadata marking**

```ts
// cli/src/tempInput.ts
const DEFAULT_TEMP_INPUT = {
  time_limit: 2000,
  space_limit: 256,
  public_tests: [] as [],
  _metadata: {
    user_supplied: true,
    source: 'cli_paste',
  },
};
```

```python
# dashboard/backend/server.py inside _build_custom_problem_payload
"_metadata": {
    "source": req.source.strip() or "custom",
    "platform": "custom",
    "question_id": stem,
    "name": req.title.strip(),
    "difficulty": req.difficulty if req.difficulty not in ("", None) else "custom",
    "created_at": timestamp,
    "custom": True,
    "user_supplied": True,
},
```

- [ ] **Step 4: Re-run the tests**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent/cli
npm test -- src/tempInput.test.ts
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
./.venv/bin/python -m pytest -q tests/dashboard/test_custom_problem_metadata.py
```

Expected:
- PASS

- [ ] **Step 5: Commit Task 3**

```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
git add cli/src/tempInput.ts cli/src/tempInput.test.ts dashboard/backend/server.py tests/dashboard/test_custom_problem_metadata.py
git commit -m "feat: mark custom and pasted problems as user supplied"
```

---

### Task 4: Force Full TestGen and Default Hacker in the Pre-Solve Controller

**Files:**
- Modify: `src/nodes/solve_controller.py`
- Modify: `tests/nodes/test_solve_controller.py`
- Modify: `src/nodes/routing.py` only if required for clarity (prefer not to touch)

- [ ] **Step 1: Write the failing controller-policy tests**

```python
from src.graph.state import create_initial_state
from src.nodes.solve_controller import pre_solve_controller_node


def test_pre_solve_controller_forces_full_testgen_and_hacker_for_user_supplied_problem():
    state = create_initial_state(
        raw_problem={
            "description": "Add two integers",
            "public_tests": [{"input": "1 2\n", "output": "3\n"}],
            "_metadata": {"user_supplied": True},
        },
        config={},
    )
    state["problem"]["canonical"] = {"objective": "Add two integers"}
    state["problem"]["abstract_confidence"] = 0.95
    state["problem"]["tags_selected"] = ["implementation"]

    update = pre_solve_controller_node(state)

    assert update["solve_policy"]["run_testgen_initially"] is True
    assert update["solve_policy"]["allow_hacker"] is True


def test_pre_solve_controller_respects_explicit_hacker_disable_for_user_supplied_problem():
    state = create_initial_state(
        raw_problem={
            "description": "Add two integers",
            "public_tests": [{"input": "1 2\n", "output": "3\n"}],
            "_metadata": {"user_supplied": True},
        },
        config={"workflow": {"hacker_enabled": False}},
    )
    state["problem"]["canonical"] = {"objective": "Add two integers"}
    state["problem"]["abstract_confidence"] = 0.95
    state["problem"]["tags_selected"] = ["implementation"]

    update = pre_solve_controller_node(state)

    assert update["solve_policy"]["run_testgen_initially"] is True
    assert update["solve_policy"]["allow_hacker"] is False


def test_pre_solve_controller_keeps_normal_low_risk_policy_for_repository_problem():
    state = create_initial_state(
        raw_problem={
            "description": "Add two integers",
            "public_tests": [{"input": "1 2\n", "output": "3\n"}],
        },
        config={},
    )
    state["problem"]["canonical"] = {"objective": "Add two integers"}
    state["problem"]["abstract_confidence"] = 0.95
    state["problem"]["tags_selected"] = ["implementation"]

    update = pre_solve_controller_node(state)

    assert update["solve_policy"]["run_testgen_initially"] is False
    assert update["solve_policy"]["allow_hacker"] is False
```

- [ ] **Step 2: Run the controller tests to verify they fail**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
./.venv/bin/python -m pytest -q tests/nodes/test_solve_controller.py
```

Expected:
- FAIL because `pre_solve_controller_node` still uses only risk-driven policy

- [ ] **Step 3: Implement the forced-policy override**

```python
from src.utils.problem_origin import is_user_supplied_problem


def pre_solve_controller_node(state: Dict[str, Any]) -> Dict[str, Any]:
    _emit_node_enter("pre_solve_controller", "top")

    score = _risk_score(state)
    config = state.get("config", {}) or {}
    benchmark_mode = bool(config.get("benchmark_output_dir"))
    solver_network_cfg = config.get("solver_network", {}) or {}
    hacker_enabled = _hacker_enabled(state)
    raw_problem = state.get("raw_problem", {}) or {}
    problem_id = str(raw_problem.get("problem_id", "") or "")

    if is_user_supplied_problem(raw_problem):
        solve_policy = {
            "risk_score": score,
            "run_testgen_initially": True,
            "run_skill_plan": bool(solver_network_cfg.get("enabled")) and score >= 1.5,
            "initial_codegen_budget": 1 if score < 2.5 else 2,
            "verifier_mode": "strict" if score >= 2.5 else "standard",
            "allow_hacker": hacker_enabled,
            "escalate_after_failures": 1,
            "generated_test_target_scale": 50 if score >= 2.5 else 0,
            "next_action": "",
        }
        return {
            "solve_policy": solve_policy,
            "execution_log": [
                "Pre-solve controller: forced full testgen for user-supplied problem",
            ],
        }

    if problem_id == SHOWCASE_FORCE_RISK_PROBLEM_ID:
        ...
```

- [ ] **Step 4: Re-run all affected Python tests**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
./.venv/bin/python -m pytest -q \
  tests/utils/test_problem_origin.py \
  tests/test_main_entrypoint.py \
  tests/dashboard/test_custom_problem_metadata.py \
  tests/nodes/test_solve_controller.py
```

Expected:
- PASS

- [ ] **Step 5: Commit Task 4**

```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
git add src/nodes/solve_controller.py tests/nodes/test_solve_controller.py
git commit -m "feat: force stronger policy for user supplied problems"
```

---

### Task 5: Update User-Facing Docs and Run End-to-End Verification

**Files:**
- Modify: `cli/README.md`
- Modify: `dashboard/README.md`

- [ ] **Step 1: Update docs to mention stronger verification for user-supplied problems**

```md
## Safety Policy for User-Supplied Problems

When you provide your own problem (for example by pasting a statement, using a custom dashboard problem, or solving a non-library JSON file), AlgoPilot forces stronger verification:

- full test generation always runs
- the hacker phase is enabled by default
- if `workflow.hacker_enabled: false` is explicitly set, that explicit disable still wins
```

- [ ] **Step 2: Run final verification**

Run:
```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent/cli
npm test -- src/tempInput.test.ts

cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
./.venv/bin/python -m pytest -q \
  tests/utils/test_problem_origin.py \
  tests/test_main_entrypoint.py \
  tests/dashboard/test_custom_problem_metadata.py \
  tests/nodes/test_solve_controller.py
```

Expected:
- CLI targeted metadata test PASS
- Python entry-point + controller tests PASS

- [ ] **Step 3: Commit Task 5**

```bash
cd /ssd-disk/lih/Software-Engineering-work/algorithm-agent
git add cli/README.md dashboard/README.md
git commit -m "docs: describe stronger policy for user supplied problems"
```
