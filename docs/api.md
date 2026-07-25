---
layout: docs
title: Solvita API Docs
description: Public API reference for Solvita workflow, CLI, model configuration, and dashboard services.
active: api
source_path: docs/api.md
---

# Solvita API Docs

This reference is organized by component role. Start from the public workflow API for scripts, use the command-line interfaces for local solving, and use the dashboard API when you need a service process with REST and WebSocket updates.

## API Contents

| Section | Public surface | Use when |
| --- | --- | --- |
| [Core Components](#core-components) | `src.graph`, `src.graph.state`, `src.events`, `src.llm` | You need the canonical workflow, state contract, event stream, or model client configuration. |
| [Agent Components](#agent-components) | Planner, Solver, Oracle, Hacker nodes | You want to understand the role-specialized agent loop and the data each role writes. |
| [Memory Components](#memory-components) | Trainable memory, solver network, failure bank, oracle and hacker memory | You want retrieval, skill routing, or learning from prior runs. |
| [Runtime Interfaces](#runtime-interfaces) | Python API, Python CLI, terminal CLI, model configuration | You want to run Solvita from scripts or local command lines. |
| [Dashboard Components](#dashboard-components) | FastAPI REST endpoints and live WebSocket | You want a long-running API process for demos, dashboards, or external services. |
| [Data Contracts](#data-contracts) | Problem payload, final state, events, run objects | You need stable request and response shapes. |

## Core Components

### Overview

The core layer provides the infrastructure shared by all Solvita entry points. It builds the LangGraph workflow, validates the problem payload shape, records state across phases, routes model calls, and emits optional NDJSON events for frontends.

### Essential Infrastructure

- **Workflow**: `src.graph.workflow` exposes `run_workflow`, `stream_workflow`, and `create_solvita_workflow`.
- **State**: `src.graph.state` defines `SolvitaState` plus typed nested dictionaries such as `ProblemData`, `PlanData`, `SolutionData`, and `TestData`.
- **Events**: `src.events` provides an opt-in NDJSON emitter used by the terminal CLI and dashboard runner.
- **LLM Client**: `src.llm.unified_client.UnifiedLLMClient` resolves provider settings from runtime config, YAML, and environment variables.
- **Sandbox Utilities**: `src.utils.cpp_execution` compiles and runs generated C++ artifacts under bounded execution limits.

### Key Features

- **Unified Interface**: Python, CLI, and dashboard calls all use the same problem schema and workflow state.
- **Configuration-Driven Execution**: Runtime behavior is controlled through `config`, `config/models.yaml`, and `SOLVITA_*` environment variables.
- **Streamable Runs**: `stream_workflow` and `--stream-events` expose workflow progress as one JSON object per line.
- **Role Separation**: Planner, Solver, Oracle, and Hacker phases write to separate state fields.
- **Token Accounting**: Final states include prompt and completion token counters when provider metadata is available or locally estimated.

### Component Interactions

1. **Problem Input** enters as a dictionary with description, limits, public tests, and optional metadata.
2. **Workflow State** stores phase outputs under `problem`, `plan`, `solution`, `tests`, `verification`, and hacker fields.
3. **Agent Nodes** update the state through the Abstract -> TestGen -> CodeGen -> Hacker loop.
4. **Memory Components** retrieve advice before generation and settle rewards after outcomes are known.
5. **Runtime Interfaces** either return the final state directly or stream events while the same workflow runs.

### Design Principles

- **Stable Public Surface**: Prefer `src.graph.run_workflow` and `src.graph.stream_workflow` over calling individual nodes directly.
- **Composable State**: Nodes communicate through typed dictionaries rather than global mutable objects.
- **Local First**: The default API runs from a checkout and writes outputs locally unless a dashboard server is started.
- **Secret Safety**: Real provider keys belong in environment variables or local ignored config, not in committed files.

## Data Contracts

### Problem Schema

All public entry points accept the same minimal problem shape.

```json
{
  "problem_id": "optional-id",
  "description": "Full problem statement, including input/output format and constraints.",
  "time_limit": 2000,
  "space_limit": 256,
  "public_tests": [
    {"input": "5\n1 2 3 4 5\n6", "output": "1 5"}
  ]
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `problem_id` | string | Optional stable id for logs, dashboard runs, and output files. |
| `description` | string | Required for normal solving. Include constraints and examples when possible. |
| `time_limit` | integer | Milliseconds. Defaults are applied by some frontends when omitted. |
| `space_limit` | integer | Megabytes. |
| `public_tests` | array | Each item has `input` and `output` strings. |
| `_metadata` | object | Optional UI metadata such as source, title, rating, tags, family, or custom flags. |

### Final State

`run_workflow` and `stream_workflow` return the full workflow state. Most integrations only need these fields.

| Field | Meaning |
| --- | --- |
| `status` | Final workflow status, such as `success`, `max_iterations`, or `error`. |
| `solution.code` | Final C++ solution, when one was produced. |
| `tests.pass_rate` | Fraction of final tests passed by the solution. |
| `tests.test_results` | Per-case execution details collected by the test runner. |
| `iteration` | Number of code-repair iterations used. |
| `llm_calls` | Count of LLM calls made by the workflow. |
| `prompt_tokens`, `completion_tokens` | Token usage recorded from provider usage metadata or estimated locally. |
| `current_phase` | Last workflow phase reached: `ABSTRACT`, `TESTGEN`, `CODEGEN`, or `HACKER`. |

## Runtime Interfaces

### Python Workflow API

Use `run_workflow` for blocking calls from Python.

```python
from src.graph import run_workflow

problem = {
    "problem_id": "demo-two-sum",
    "description": "Given an array, find two numbers that sum to target.",
    "time_limit": 2000,
    "space_limit": 256,
    "public_tests": [
        {"input": "5\n1 2 3 4 5\n6", "output": "1 5"},
    ],
}

config = {
    "max_iterations": 5,
    "max_hack_rounds": 3,
    "solver_network": {"enabled": True},
    "trainable_memory": {"enabled": True, "data_dir": "data/memory"},
}

final_state = run_workflow(problem, config)

print(final_state["status"])
print(final_state.get("solution", {}).get("code", ""))
print(final_state.get("prompt_tokens", 0), final_state.get("completion_tokens", 0))
```

### Streaming Workflow API

Use `stream_workflow` when you want NDJSON progress events on stdout through `src.events`.

```python
import src.events as events
from src.graph import stream_workflow

events.configure(enabled=True)
final_state = stream_workflow(problem, {"max_iterations": 5})
```

Common event types include `solve_start`, `phase_start`, `phase_done`, `token_sample`, `final`, `solution_saved`, and `error`.

### Python Command-Line API

Run from the repository root.

```bash
python main.py --input examples/problem_input_example.json --output solution.cpp
```

You can also pass a raw statement directly.

```bash
python main.py \
  --problem-description "Given N, print N." \
  --output solution.cpp \
  --max-iterations 5
```

Useful flags:

| Flag | Description |
| --- | --- |
| `--input <path>` | JSON problem file. |
| `--problem-description <text>` | Plain text problem statement. |
| `--output <path>` | C++ output path, default `solution.cpp`. |
| `--model <name>` | Overrides the model configured in YAML or environment variables. |
| `--temperature <float>` | LLM temperature, default `0.1`. |
| `--max-iterations <n>` | Code repair budget, default `5`. |
| `--config <dir>` | Config directory, default `config`. |
| `--stream-events` | Emit one JSON event per line for TUI/dashboard integrations. |

### Terminal CLI

The Node-based terminal interface wraps the Python streaming API.

```bash
cd cli
npm install && npm run build && npm link
cd ..

solvita solve examples/problem_input_example.json
```

Run `solvita` with no arguments for the interactive flow, or `solvita solve` with no file to start interactive problem selection.

### Model Configuration API

Solvita uses an OpenAI-compatible client by default. Configuration is resolved from runtime config, `config/models.yaml`, and environment variables.

```bash
export SOLVITA_BASE_URL="https://api.openai.com/v1"
export OPENAI_API_KEY="<set-in-your-shell-only>"
export SOLVITA_MODEL="gpt-4"
export SOLVITA_TEMPERATURE="0.1"
export SOLVITA_MAX_TOKENS="128000"
```

Copy the template when you want role-specific defaults.

```bash
cp config/models.yaml.example config/models.yaml
```

```yaml
llm:
  base_url: "https://api.openai.com/v1"
  model: "gpt-4"
  temperature: 0.1
  max_tokens: 128000
  roles:
    generator:
      model: "gpt-4"
    checker:
      model: "gpt-4"
    hacker:
      model: "gpt-4"
```

Keep credentials in `OPENAI_API_KEY`; never put them in `config/models.yaml`.

Runtime config can override the same values for one call.

```python
final_state = run_workflow(
    problem,
    config={
        "base_url": "https://api.openai.com/v1",
                "model": "gpt-4",
        "temperature": 0.1,
        "max_iterations": 5,
    },
)
```

### Azure OpenAI with AAD

When no API key is supplied and `azure_tenant_id` plus `azure_scope` are set, Solvita uses Azure OpenAI AAD authentication through `azure-identity` and the Azure CLI.

```bash
pip install azure-identity
az login --tenant <tenant-id>

export SOLVITA_BASE_URL="https://<resource>.openai.azure.com"
export SOLVITA_AZURE_TENANT_ID="<tenant-id>"
export SOLVITA_AZURE_SCOPE="https://cognitiveservices.azure.com/.default"
export SOLVITA_AZURE_API_VERSION="2025-04-01-preview"
export SOLVITA_MODEL="<deployment-name>"
```

For providers that support the OpenAI Responses API path:

```bash
export SOLVITA_USE_RESPONSES_API=true
export SOLVITA_REASONING_EFFORT=medium
```

or pass the same values in runtime config:

```python
config = {"use_responses_api": True, "reasoning_effort": "medium"}
```

## Agent Components

### Overview

The agent layer is organized around four role-specialized phases. The public API should normally call the workflow, while the table below helps you map final-state fields and dashboard events back to the underlying components.

### Available Components

| Component | Main modules | Writes to state | Responsibility |
| --- | --- | --- | --- |
| Planner | `src.nodes.abstract_problem`, `src.nodes.solver_skill_plan` | `problem`, `plan`, `solve_policy` | Extract canonical tags, select algorithmic hints, and optionally choose solver skills. |
| Solver | `src.nodes.generate_code`, `src.nodes.compile_code`, `src.nodes.run_tests`, `src.nodes.analyze_feedback` | `solution`, `feedback`, `best_solution` | Generate C++ code, compile it, execute tests, and repair failures. |
| Oracle | `src.nodes.generate_tests`, `src.oracle.*` | `tests`, `oracle_event_metadata`, `oracle_memory_decision` | Build certified internal tests, validators, checkers, and oracle-family evidence. |
| Hacker | `src.nodes.hack_test`, `src.hacker.*` | `hack_result`, `hack_failures`, `hacker_reward` | Search for adversarial counterexamples and route failures back to the Solver. |

### Common Features

- Each component receives and returns dictionaries compatible with `SolvitaState`.
- Nodes are assembled by `create_solvita_workflow`; external callers should avoid invoking nodes in isolation unless writing tests.
- Phase events are emitted when streaming is enabled, so frontends can track progress without polling internal state.
- Agent outputs are retained in the final state for debugging, replay, and dashboard rendering.

### Usage Example

Inspect the phases after a run.

```python
final_state = run_workflow(problem, {"max_iterations": 3})

print(final_state["current_phase"])
print(final_state.get("problem", {}).get("tags_selected", []))
print(final_state.get("plan", {}).get("algorithm_choice", ""))
print(final_state.get("hack_result", "NONE"))
```

## Memory Components

### Overview

Solvita can augment generation with trainable memory and graph-structured skill routing. These components are optional at runtime and are controlled by the `config` dictionary.

### Common Features

- Role-specific namespaces keep planning, solving, testing, oracle, and hacker signals separate.
- Retrieval results are injected into prompts before generation.
- Rewards are settled after final outcomes or phase-specific evidence is available.
- Memory data is local to the configured `data_dir` unless you wire an external store.

### Available Components

| Component | Main modules | Configuration | Purpose |
| --- | --- | --- | --- |
| Trainable Memory | `src.memory.*` | `trainable_memory.enabled`, `trainable_memory.data_dir` | Retrieve and update role-specific advice from prior solving traces. |
| Solver Network | `src.solver_network.*` | `solver_network.enabled` | Select reusable algorithmic skills and build codegen augmentation blocks. |
| Failure Bank | `src.failure_bank.*`, `src.nodes.failure_bank_lookup` | failure-bank config entries | Reuse known counterexamples, anti-patterns, and repair summaries. |
| Oracle Memory | `src.oracle.oracle_memory_*` | `oracle.mode`, oracle memory config | Gate oracle-family choices and learn when a certification path is reliable. |
| Hacker Memory | `src.hacker.*`, `src.nodes.settle_hacker_memory` | hacker memory config | Record adversarial generation outcomes and reward useful failure discovery. |

### Usage Example

```python
config = {
    "max_iterations": 5,
    "trainable_memory": {
        "enabled": True,
        "data_dir": "data/memory",
        "plan_top_k": 5,
        "solve_top_k": 3,
        "test_top_k": 3,
    },
    "solver_network": {"enabled": True},
    "oracle": {
        "mode": "safe",
        "accept_threshold": 0.95,
        "enable_fallback": False,
    },
}

final_state = run_workflow(problem, config)
print(final_state.get("plan", {}).get("memory_item_ids", []))
print(final_state.get("solution", {}).get("memory_item_ids", []))
```

For the lower-level memory client, see the [Trainable Memory System Guide](MEMORY_SYSTEM_GUIDE.md).

## Dashboard Components

### Overview

The dashboard backend exposes Solvita as a FastAPI service. Use it when a web UI, demo server, or external client needs to start runs, inspect run history, and subscribe to live progress.

### Start the Backend

```bash
pip install -r dashboard/backend/requirements.txt
python -m dashboard.backend.server
```

By default the server listens on `http://127.0.0.1:8766` unless overridden in `dashboard/backend/config.py` or the environment.

### REST Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Health check. |
| `GET` | `/api/dag` | Static DAG definition used by the dashboard. |
| `GET` | `/api/problems` | List local problem JSON files. |
| `GET` | `/api/problems/{problem_id}` | Read one problem JSON. |
| `POST` | `/api/problems/custom` | Create a custom problem. |
| `PUT` | `/api/problems/custom/{problem_id}` | Update a custom problem. |
| `DELETE` | `/api/problems/custom/{problem_id}` | Delete a custom problem. |
| `GET` | `/api/sources/codeforces/search?q=<query>&limit=<n>` | Search cached Codeforces metadata. |
| `POST` | `/api/sources/codeforces/import` | Fetch and save a Codeforces problem. |
| `POST` | `/api/runs` | Start a Solvita run. |
| `GET` | `/api/runs` | List active and stored runs. |
| `GET` | `/api/runs/{run_id}` | Read run detail and buffered events. |
| `POST` | `/api/runs/{run_id}/cancel` | Cancel a running solve process. |
| `DELETE` | `/api/runs/{run_id}` | Delete a completed stored run. |

### Request and Response Models

| Model | Fields |
| --- | --- |
| `RunRequest` | `problem: dict`, `config: dict` |
| `RunResponse` | `run_id`, `status`, `ws_url` |
| `RunDetail` | `run_id`, `problem_id`, `problem`, `config`, `started_at`, `completed_at`, `final_status`, `events` |
| `CustomProblemRequest` | `title`, `description`, `source`, `difficulty`, `constraints_text`, limits, `public_tests` |
| `CodeforcesImportRequest` | `contest_id`, `index`, or `url` |

### Start a Run

```bash
curl -sS -X POST http://127.0.0.1:8766/api/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "problem": {
      "problem_id": "demo",
      "description": "Given N, print N.",
      "time_limit": 2000,
      "space_limit": 256,
      "public_tests": [{"input": "7", "output": "7"}]
    },
    "config": {"max_iterations": 5, "max_hack_rounds": 3}
  }'
```

Response:

```json
{
  "run_id": "...",
  "status": "running",
  "ws_url": "ws://127.0.0.1:8766/ws/live/..."
}
```

### Watch Live Events

Connect to the returned `ws_url`.

```javascript
const socket = new WebSocket(wsUrl);

socket.onmessage = (message) => {
  const event = JSON.parse(message.data);
  console.log(event.type, event);
};
```

Dashboard events include workflow milestones such as `solve_start`, `phase_start`, `phase_done`, `final`, and run bookkeeping events such as `run_complete`.

### Import a Codeforces Problem

```bash
curl -sS -X POST http://127.0.0.1:8766/api/sources/codeforces/import \
  -H 'Content-Type: application/json' \
  -d '{"contest_id": 1873, "index": "A"}'
```

You can also provide a Codeforces problem URL instead of `contest_id` and `index`.

## Secret Safety

- Do not commit real API keys into `config/models.yaml`, `.env`, shell scripts, or Markdown files.
- Prefer `OPENAI_API_KEY` and other environment variables for local usage.
- Install the repository hook with `./scripts/install-git-hooks.sh` before contributing.
