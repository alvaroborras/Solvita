<div align="center">
  <img src="image.png" alt="Solvita" width="100%" style="max-width: 1200px; background: #ffffff;"/>
  
  <h1 style="margin-top: 20px; font-size: 3em; color: #2c3e50;">Solvita</h1>
  <p style="font-size: 1.2em; color: #7f8c8d; margin-bottom: 30px;">
    <strong>Intelligent Competitive Programming Agent</strong>
  </p>

  [![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
  [![License](https://img.shields.io/badge/License-MIT-success.svg?style=for-the-badge)](LICENSE)
  [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg?style=for-the-badge)](https://github.com/psf/black)
  [![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC.svg?style=for-the-badge&logo=pytest&logoColor=white)](https://pytest.org/)

  <br/>

  [Features](#-features) • [Architecture](#-architecture) • [Installation](#-installation) • [Quick Start](#-quick-start) • [Documentation](#-documentation)

</div>

---

## Introduction

**Solvita** is an autonomous agent for solving competitive programming problems (Codeforces-style). It combines a LangGraph workflow, a trainable contextual-bandit memory system, sandboxed C++ execution, and iterative SEARCH/REPLACE patching to automatically understand problems, generate tests, plan solutions, and produce passing C++ code.

---

## Features

<table>
<tr>
<td width="50%">

### Trainable Memory
Contextual-bandit network that learns which strategies work for which problem types across plan, solve, and test phases

### Multi-Model LLM Support
Works with any OpenAI-compatible API (GPT-4, Claude, local models) via a single config file

### C++ Sandboxed Execution
Resource-limited compilation and execution with `rlimit` sandboxing (CPU, memory, file size, process limits)

</td>
<td width="50%">

### Automatic Test Generation
Generates extensive test suites with generators, validators, and custom checkers

### SEARCH/REPLACE Patching
Iterative code repair via structured patches instead of full rewrites

### Adversarial Hack Testing
Post-success adversarial phase that stress-tests solutions to find edge-case bugs

</td>
</tr>
</table>

---

## Architecture

```mermaid
graph TD
    A[Problem Input] --> B[Abstract Problem]
    B --> C[Phase Transition]
    C --> D[Generate Tests]
    D --> E[Phase Transition]
    E --> F[Solver Skill Plan Optional]
    F --> G[Generate Code]
    G --> H[Compile Code]
    H -->|success| I[Run Tests]
    H -->|failed| N[Analyze Feedback]
    I --> J[Unified Check]
    J --> K1[Update Plan Memory]
    K1 --> K2[Update Solve Memory]
    K2 --> K3[Update Oracle Memory]
    K3 -->|continue| N
    K3 -->|success| L[Phase Transition]
    K3 -->|max iterations| Z[END]
    N --> G
    L --> M[Hack Test]
    M -->|all clear| Z
    M -->|bug found| O[Phase Transition]
    O --> G
```

---

## Project Structure

```
solvita/
├── config/
│   ├── models.yaml             # LLM + embedding backend configuration
│   ├── solver_network.yaml     # Skill-graph runtime defaults and toggles
│   ├── trainable_memory.yaml   # Trainable memory runtime defaults and toggles
│   ├── prompt_template.yaml    # Prompt templates used by nodes
│   └── tag_whitelist.yaml      # Allowed algorithmic tags for abstract node
├── src/
│   ├── graph/
│   │   ├── state.py            # SolvitaState TypedDict
│   │   └── workflow.py         # LangGraph workflow definition
│   ├── llm/
│   │   └── unified_client.py   # OpenAI-compatible LLM client
│   ├── memory/
│   │   ├── types.py            # MemoryItem, Observation, MemoryEvent
│   │   ├── store.py            # SQLite-backed item/event storage
│   │   ├── policy.py           # Contextual bandit policy
│   │   ├── featurizer.py       # Canonical problem -> feature keys
│   │   ├── client.py           # Unified MemoryClient interface
│   │   ├── skill_loader.py     # C++ skill snippets from skills/*.md
│   │   └── seeds/              # Initial strategy templates
│   ├── nodes/
│   │   ├── abstract_problem.py # Canonical abstraction + level-1/2 tags
│   │   ├── solver_skill_plan.py# Optional skill-graph rollout + LLM DAG/skills
│   │   ├── generate_code.py    # Code gen with SEARCH/REPLACE patching
│   │   ├── generate_tests.py   # Test suite generation
│   │   ├── compile_code.py     # Sandboxed compilation
│   │   ├── run_tests.py        # Sandboxed test execution
│   │   ├── unified_check.py    # Pass/fail determination
│   │   ├── analyze_feedback.py # Failure analysis + diagnostics
│   │   ├── hack_test.py        # Adversarial stress testing
│   │   ├── update_plan_memory.py
│   │   ├── update_solve_memory.py
│   │   └── routing.py          # Conditional edge logic
│   ├── solver_network/
│   │   ├── planner_input.py
│   │   ├── llm_skill_selection.py
│   │   └── adapter.py
│   ├── skill_graph_train/      # Offline skill-graph training pipeline package
│   └── utils/
│       ├── cpp_execution.py    # rlimit-sandboxed compile/run
│       └── patch_utils.py      # SEARCH/REPLACE block parser
├── skills/                     # C++ algorithm snippets (*.md)
├── artifacts/
│   ├── solver_network/latest/graph/
│   └── trainable_memory/latest/
├── tests/
├── main.py                     # CLI entry point
└── requirements.txt
```

---

## Installation

### Prerequisites

- **Python 3.10+**
- **g++ or clang++** (C++17 support)
- An OpenAI-compatible LLM API endpoint

### Steps

```bash
# 1. Clone
git clone https://github.com/S0lvita/solvita.git
cd solvita

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure LLM credentials (choose one method)

# Option A: config file
# Edit config/models.yaml with your base_url + api_key (+ optional llm.roles per node)

# Option B: environment variables
export SOLVITA_BASE_URL="https://api.openai.com/v1"
export SOLVITA_API_KEY="sk-..."
export SOLVITA_MODEL="gpt-4"
```

### Embedding Backend Configuration (Skill Graph Similarity)

`skill_graph/question_similarity.py` now supports two embedding backends, configured in `config/models.yaml`:

```yaml
embedding:
  provider: "azure_openai"         # or "sentence_transformers"
  model: "text-embedding-3-small"  # or local HF model id
```

#### Option 1: Azure OpenAI embeddings

```yaml
embedding:
  provider: "azure_openai"
  model: "text-embedding-3-small"
  azure:
    base_url: "https://<your-azure-openai-endpoint>"
    tenant_id: "..."
    scope: "..."
    api_version: "2025-04-01-preview"
```

#### Option 2: Local sentence-transformers embeddings

```yaml
embedding:
  provider: "sentence_transformers"
  model: "sentence-transformers/all-MiniLM-L6-v2"
  sentence_transformers:
    device: "cpu"   # or "cuda"
```

Install local embedding dependency when using `sentence_transformers`:

```bash
pip install sentence-transformers
```

> Note: the first run with a local model may take significantly longer due to model download and initialization. This is expected.

Environment variables still override YAML values:
- `SOLVITA_EMBEDDING_PROVIDER`
- `SOLVITA_EMBEDDING_MODEL`
- `SOLVITA_ST_DEVICE`
- `SOLVITA_EMBEDDING_AZURE_BASE_URL`, `SOLVITA_EMBEDDING_AZURE_TENANT_ID`, `SOLVITA_EMBEDDING_AZURE_SCOPE`, `SOLVITA_EMBEDDING_AZURE_API_VERSION`

---

## Quick Start

### Python API

```python
from src.graph.workflow import run_workflow

result = run_workflow(
    raw_problem={
        "description": "Given an array, find two numbers that sum to target...",
        "time_limit": 2000,
        "space_limit": 256,
        "public_tests": [
            {"input": "5\n1 2 3 4 5\n6", "output": "1 5"},
        ],
    },
    config={
        "max_iterations": 5,
        "solver_network": {"enabled": True},
        "trainable_memory": {"enabled": True},
    },
)

print(result["solution"]["code"])
print(f"Pass rate: {result['tests']['pass_rate']:.1%}")
```

### Command Line

```bash
python main.py --input problem.json --output solution.cpp
```

By default, runtime nested configs are loaded from:
- `config/solver_network.yaml`
- `config/trainable_memory.yaml`

You can still override any nested key at call time via `run_workflow(..., config=...)`.

---

## Memory System

See [docs/memory_architecture.md](docs/memory_architecture.md) for full details.

The trainable memory uses a **contextual bandit** that learns which strategies work for which problem types. Active namespaces include `plan`, `solve`, `oracle`, and `hack` (the legacy `test` settlement path has been retired). Each active namespace has:

- **SQLite store** for items and events
- **Sparse linear policy** with feature-item edge weights
- **Event logging** for offline analysis and batch training

Formal offline Hacker trainer:

```bash
python3 scripts/train_hacker.py --dataset data/solvita_train/solvita_train_tanh.jsonl --data-dir data/memory
```

`scripts/train_hacker_input.py` is retained only as a legacy auxiliary script and is not the formal trainer.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- [LangGraph](https://github.com/langchain-ai/langgraph) - Workflow orchestration
- [OpenAI](https://openai.com/) - GPT model support
- [Anthropic](https://www.anthropic.com/) - Claude model support
- [Codeforces](https://codeforces.com/) - Competitive programming platform

---
