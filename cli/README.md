# Solvita CLI

Interactive terminal frontend for the Solvita agent, inspired by Claude Code's style.
Displays real-time phase progress while the Python backend solves competitive programming problems.

---

## Prerequisites

- **Node.js 18+** with npm  
  Download from https://nodejs.org/  (LTS recommended)
- **Python 3.10+** with Solvita dependencies installed  
  (`pip install -r ../requirements.txt` from the project root)
- A configured `../config/models.yaml` (see project README)

---

## Installation

```bash
# 1. From the cli/ directory:
npm install

# 2. Build TypeScript → JavaScript:
npm run build

# 3. (Optional) Link globally so `solvita` is available anywhere:
npm link
```

---

## Usage

### Interactive mode (no arguments)
```bash
solvita
# or, if not globally linked:
node bin/solvita.js
```

Presents a menu to:
- Select a problem from `data/problem/`
- Type a path to any problem JSON
- Paste a problem description directly

### Direct file mode
```bash
solvita solve data/problem/livecodebench_1873_A.json
solvita solve problem.json --output my_solution.cpp --max-iterations 8
```

### Options for `solvita solve`
| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output <path>` | `solution.cpp` | Output C++ file |
| `-n, --max-iterations <n>` | `5` | Max LLM refinement rounds |
| `-p, --python <bin>` | auto | Python executable (`python` / `python3`) |

---

## Development (without build)

```bash
npm run dev -- solve data/problem/livecodebench_1873_A.json
```

Uses `tsx` to run TypeScript directly.

---

## UI layout

```
╭──────────────────────────────────────────────────────╮
│  Solvita  —  livecodebench 1873 A                    │
│  Intelligent Competitive Programming Agent           │
╰──────────────────────────────────────────────────────╯

  ✔ Abstracting Problem         tags: math, greedy   conf: 88%
  ✔ Generating Tests            12 test cases
  ✔ Generating & Testing Code   iter 1  compiled  tests: 12/12 (100%)
  ✔ Adversarial Hack Testing    1 round(s) — all clear

╭──────────────────────────────────────────────────────╮
│  ✔ Solved!  solution.cpp  │ 12/12  100%  1 iter  9 LLM calls  │
╰──────────────────────────────────────────────────────╯

  Tokens: 4521 prompt + 1382 completion
```

---

## Problem JSON format

```json
{
  "description": "Given an array...",
  "time_limit": 2000,
  "space_limit": 256,
  "public_tests": [
    { "input": "5\n1 2 3 4 5\n9", "output": "1 3" }
  ]
}
```

Pre-built problems are in `../data/problem/`.

---

## Notes on Windows

The Python backend uses Linux `rlimit` for C++ sandboxing.
On Windows, compilation falls back to basic `subprocess.run()` — no resource limits.
The CLI displays a yellow warning when running on Windows.
For full sandbox support, run under WSL2.
