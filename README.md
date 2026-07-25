<p align="center">
  <img src="image.png" alt="Solvita" width="100%" style="max-width: 1200px; background: #ffffff;"/>
</p>

<h1 align="center">Solvita</h1>

<p align="center">
  <strong>Enhancing Large Language Models for Competitive Programming via Agentic Evolution</strong>
</p>

<p align="center">
  <a href="https://arxiv.org/abs/2605.15301"><img src="https://img.shields.io/badge/arXiv-2605.15301-b31b1b.svg?logo=arxiv" alt="arXiv"></a>
  <a href="https://nju-link.github.io/Solvita/"><img src="https://img.shields.io/badge/Project-Page-2ea44f.svg?logo=githubpages&logoColor=white" alt="Project Page"></a>
  <a href="https://nju-link.github.io/Solvita/api.html"><img src="https://img.shields.io/badge/API-Docs-0A7AFF.svg?logo=readthedocs&logoColor=white" alt="API Docs"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-success.svg" alt="MIT License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white" alt="Python 3.10+"></a>
  <a href="https://pytest.org/"><img src="https://img.shields.io/badge/tests-pytest-0A9EDC.svg?logo=pytest&logoColor=white" alt="pytest"></a>
</p>

<p align="center">
  <a href="https://arxiv.org/abs/2605.15301">Paper</a> |
  <a href="https://nju-link.github.io/Solvita/">Pages</a> |
  <a href="https://nju-link.github.io/Solvita/api.html">API Docs</a> |
  <a href="cli/README.md">CLI</a> |
  <a href="docs/MEMORY_SYSTEM_GUIDE.md">Memory Guide</a> |
  <a href="#citation">Citation</a>
</p>

---

## Overview

Solvita is an open-source agentic evolution framework for competitive programming. It turns a frozen LLM into a continuously improving problem-solving system by coordinating four role-specialized agents: a Planner for problem abstraction and strategy selection, a Solver for program synthesis and patch-based repair, an Oracle for certified internal-test construction, and a Hacker for adversarial validation.

Instead of relying on static retrieval, each agent is backed by a trainable graph-structured knowledge network. Pass/fail verdicts, test quality signals, and adversarial vulnerabilities are converted into reinforcement-style updates, allowing Solvita to reuse lessons from previous solving and debugging episodes on future problems.

<p align="center">
  <img src="docs/assets/solvita-overview.png" alt="Solvita overview" width="92%">
</p>

The paper evaluates Solvita across CodeContests, APPS, AetherCode, and live Codeforces rounds, where the agentic loop improves over single-pass and stateless multi-agent baselines while keeping the LLM backbone unchanged.

## Installation

### Requirements

- Python 3.10+
- g++ or clang++ with C++17 support
- An OpenAI-compatible LLM endpoint, or Azure OpenAI with AAD authentication
- Node.js 18+ only if you use the terminal CLI or dashboard frontend

### Setup

```bash
git clone https://github.com/NJU-LINK/Solvita.git
cd Solvita

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp config/models.yaml.example config/models.yaml
export OPENAI_API_KEY="<set-in-your-shell-only>"
```

Edit `config/models.yaml` with your endpoint and model name. Keep credentials outside the repository; the SDK reads OPENAI_API_KEY from your shell environment.

```yaml
llm:
  base_url: "https://api.openai.com/v1"
  model: "gpt-4"
  temperature: 0.1
  max_tokens: 128000
```

More provider and runtime examples are in the [API docs](https://nju-link.github.io/Solvita/api.html).

## Quick Start

### Python API

```python
from src.graph.workflow import run_workflow

problem = {
    "description": "Given an array, find two numbers that sum to target.",
    "time_limit": 2000,
    "space_limit": 256,
    "public_tests": [
        {"input": "5\n1 2 3 4 5\n6", "output": "1 5"},
    ],
}

result = run_workflow(
    problem,
    config={
        "max_iterations": 5,
        "max_hack_rounds": 3,
        "solver_network": {"enabled": True},
        "trainable_memory": {"enabled": True},
    },
)

print(result["solution"]["code"])
print(result["status"])
```

### Command Line

```bash
python main.py --input examples/problem_input_example.json --output solution.cpp

python main.py \
  --problem-description "Given N, print N." \
  --output solution.cpp \
  --max-iterations 5
```

### Terminal CLI

```bash
cd cli
npm install && npm run build && npm link
cd ..

solvita solve examples/problem_input_example.json
```

See [cli/README.md](cli/README.md) and [USAGE.zh-CN.md](USAGE.zh-CN.md) for the interactive Codeforces workflow.

## Documentation

| Topic | Link |
| --- | --- |
| Project page source and GitHub Pages notes | [docs/index.md](docs/index.md), [docs/pages.md](docs/pages.md) |
| Python, CLI, model, REST, and WebSocket API calls | [API docs](https://nju-link.github.io/Solvita/api.html) ([source](docs/api.md)) |
| Trainable memory and role-specific knowledge networks | [docs/MEMORY_SYSTEM_GUIDE.md](docs/MEMORY_SYSTEM_GUIDE.md) |
| Chinese trainable-memory guide | [docs/trainable-memory-network-guide.zh-CN.md](docs/trainable-memory-network-guide.zh-CN.md) |
| Contribution and secret-safety workflow | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Repository Layout

```text
Solvita/
|-- src/                  # LangGraph workflow, agents, memory, LLM client, utilities
|-- skill_graph/          # Skill graph data structure, retrieval, inference, and training
|-- skills/               # Reusable competitive-programming skill snippets
|-- cli/                  # Ink/React terminal frontend
|-- dashboard/            # FastAPI backend and React/Vite dashboard
|-- docs/                 # Project pages, API docs, and memory-system guides
|-- examples/             # Sample problem JSON
|-- scripts/              # Training, benchmark, and dataset utilities
|-- tests/                # pytest suite
|-- main.py               # Python command-line entry point
`-- requirements.txt
```

## Open Source

Solvita is released under the [MIT License](LICENSE). Contributions are welcome through issues and pull requests; please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting changes. The repository includes a pre-commit hook installer that helps prevent accidental LLM API-key leaks.

## Citation

If Solvita is useful for your research or engineering work, please cite:

```bibtex
@misc{li2026solvita,
  title         = {Solvita: Enhancing Large Language Models for Competitive Programming via Agentic Evolution},
  author        = {Han Li and Jinyu Tian and Rili Feng and Yuqiao Du and Chong Zheng and Chenyu Wang and Chenchen Liu and Shihao Li and Xinping Lei and Yifan Yao and Weihao Xie and Letian Zhu and Jiaheng Liu},
  year          = {2026},
  eprint        = {2605.15301},
  archivePrefix = {arXiv},
  primaryClass  = {cs.AI},
  url           = {https://arxiv.org/abs/2605.15301}
}
```

## Acknowledgments

Solvita builds on the broader open-source ecosystem around LangGraph, OpenAI-compatible model serving, pytest, FastAPI, React, and competitive-programming platforms such as Codeforces.
