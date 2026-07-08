# Solvita API Usage

This document covers the public call surfaces that are useful for scripts, services, and demos:

- Python workflow API
- Python command-line entry point
- LLM provider configuration
- Dashboard REST and WebSocket API

## Problem Schema

All entry points accept the same minimal problem shape.

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

Recommended fields:

| Field | Type | Notes |
| --- | --- | --- |
| `problem_id` | string | Optional stable id for logs and dashboard runs. |
| `description` | string | Required for normal solving. Include constraints and examples when possible. |
| `time_limit` | integer | Milliseconds. Defaults are applied by some frontends when omitted. |
| `space_limit` | integer | Megabytes. |
| `public_tests` | array | Each item has `input` and `output` strings. |
| `_metadata` | object | Optional UI metadata such as source, title, rating, tags, or family. |

## Python Workflow API

Use `run_workflow` for blocking calls from Python.

```python
from src.graph.workflow import run_workflow

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
print(final_state["solution"]["code"])
print(final_state.get("prompt_tokens", 0), final_state.get("completion_tokens", 0))
```

Common result fields:

| Field | Meaning |
| --- | --- |
| `status` | Final workflow status, such as `success`, `max_iterations`, or `error`. |
| `solution.code` | Final C++ solution, when one was produced. |
| `tests.pass_rate` | Fraction of internal tests passed by the final solution. |
| `iteration` | Number of code-repair iterations used. |
| `llm_calls` | Count of LLM calls made by the workflow. |
| `prompt_tokens`, `completion_tokens` | Token usage recorded from provider usage metadata or estimated locally. |

Use `stream_workflow` when you want NDJSON progress events on stdout through `src.events`.

```python
import src.events as events
from src.graph.workflow import stream_workflow

events.configure(enabled=True)
final_state = stream_workflow(problem, config)
```

## Command-Line API

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

## Model API Configuration

Solvita uses an OpenAI-compatible client by default. Configuration is resolved in this order, with later layers overriding earlier layers:

1. `config/models.yaml`
2. Environment variables
3. Explicit runtime `config` passed to `run_workflow`

### Environment Variables

```bash
export SOLVITA_BASE_URL="https://api.openai.com/v1"
export SOLVITA_API_KEY="<your-api-key>"
export SOLVITA_MODEL="gpt-4"
export SOLVITA_TEMPERATURE="0.1"
export SOLVITA_MAX_TOKENS="128000"
```

### YAML Configuration

Copy the template and edit only non-secret settings unless this is a private local checkout.

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

Keep real keys in `SOLVITA_API_KEY`; `config/models.yaml` is intended to remain local.

### Runtime Override

```python
final_state = run_workflow(
    problem,
    config={
        "base_url": "https://api.openai.com/v1",
        "api_key": "<your-api-key>",
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

### Responses API Options

For providers that support the OpenAI Responses API path:

```bash
export SOLVITA_USE_RESPONSES_API=true
export SOLVITA_REASONING_EFFORT=medium
```

or pass the same values in the runtime config:

```python
config = {"use_responses_api": True, "reasoning_effort": "medium"}
```

## Dashboard API

Start the FastAPI backend:

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

Events include workflow milestones such as `solve_start`, `phase_start`, `phase_done`, `final`, and dashboard bookkeeping events such as `run_complete`.

### Import a Codeforces Problem

```bash
curl -sS -X POST http://127.0.0.1:8766/api/sources/codeforces/import \
  -H 'Content-Type: application/json' \
  -d '{"contest_id": 1873, "index": "A"}'
```

You can also provide a Codeforces problem URL instead of `contest_id` and `index`.

## Secret Safety

- Do not commit real API keys into `config/models.yaml`, `.env`, shell scripts, or Markdown files.
- Prefer `SOLVITA_API_KEY` and other environment variables for local usage.
- Install the repository hook with `./scripts/install-git-hooks.sh` before contributing.
