# Memory Architecture

## Overview

The unified trainable memory system provides a consistent framework for learning and selecting strategies across three agent namespaces: **plan**, **solve**, and **test**. Each namespace maintains its own:

- **SQLite store**: Persistent item + event storage with transactional writes
- **Policy network**: Trainable bandit-based scoring (bias + sparse feature weights)
- **Event log**: Append-only trajectory history for offline analysis

## Key Design Principles

### 1. Namespace Isolation

Each agent has its own memory space:

- **Plan**: Stores problem-type tags, required subfunctions, and canonical hints
- **Solve**: Stores step-level strategies, skill references, and anti-patterns
- **Test**: Stores constraint patterns, generation strategies, and validator pitfalls

### 2. Explicit Edge Weights

The "network" is a **bipartite graph**:

- **Left nodes**: Feature keys (e.g., `TAG:dp`, `CONSTR:n_1e5`, `FAIL:TIMEOUT`)
- **Right nodes**: Memory items
- **Edge weight**: `W[feature, item]` learned via contextual bandit updates

Scoring: `score(item) = bias[item] + sum(W[feature, item])`

### 3. Event-Based Learning

The system logs full events for each decision:

```json
{
  "timestamp": "...",
  "namespace": "plan",
  "observation": {
    "fsm_state": "SOLVE_DRAFT",
    "failure_type": "TIMEOUT",
    "canonical": {},
    "feature_keys": ["FSM:SOLVE_DRAFT", "TAG:dp", "FAIL:TIMEOUT"]
  },
  "selected_item_ids": ["item1", "item2"],
  "reward": 0.5
}
```

This enables:
- Trajectory-level analysis
- Offline batch training
- Debugging and auditing

## File Structure

```
solvita/
├── src/memory/
│   ├── __init__.py
│   ├── types.py          # MemoryNamespace, MemoryItem, MemoryEvent, Observation
│   ├── store.py          # MemoryStore (SQLite: memory.db)
│   ├── policy.py         # BanditPolicy (bias + sparse W, saved to policy.json)
│   ├── featurizer.py     # Featurizer (canonical -> feature keys)
│   ├── client.py         # MemoryClient (unified interface)
│   ├── skill_loader.py   # SkillLoader (for solve namespace)
│   └── seeds/
│       ├── plan_items.py
│       ├── solve_items.py
├── skills/
│   ├── README.md
│   └── quick_sort.md     # Example skill
├── data/memory/
│   ├── plan/
│   │   ├── memory.db     # SQLite: items + events tables
│   │   └── policy.json   # Bandit weights
│   ├── solve/
│   │   ├── memory.db
│   │   └── policy.json
│   └── test/
│       ├── memory.db
│       └── policy.json
└── tests/memory/
    └── test_memory_system.py
```

## SQLite Schema

### items table

| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PRIMARY KEY | Unique item identifier |
| namespace | TEXT | plan / solve / test |
| text | TEXT | Human-readable strategy description |
| tags_json | TEXT | JSON array of tag strings |
| payload_json | TEXT | JSON object with namespace-specific data |
| uses | INTEGER | Number of times selected |
| avg_reward | REAL | Running average reward |
| deprecated | INTEGER | 0 = active, 1 = retired |

### events table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PRIMARY KEY | Auto-increment |
| timestamp | TEXT | ISO 8601 timestamp |
| namespace | TEXT | plan / solve / test |
| observation_json | TEXT | Full observation context |
| selected_ids_json | TEXT | JSON array of selected item IDs |
| reward | REAL | Outcome reward signal |
| problem_hash | TEXT | Hash for deduplication |
| iteration | INTEGER | Workflow iteration number |

## Integration Points

### Plan Node

- **Injection**: `plan_solution_node` uses `MemoryClient(namespace="plan")` to inject planning strategies
- **Settlement**: `update_plan_memory_node` logs events after `unified_check`
- **Payload**: `{problem_tags, subfunctions, canonical_hints}`

### Solve Node

- **Injection**: `generate_code_node` uses `MemoryClient(namespace="solve")` to inject step strategies + skills
- **Settlement**: `update_solve_memory_node` logs events after `unified_check`
- **Payload**: `{step_strategies, skills: [{skill_id, path}], anti_patterns}`
- **Skills**: Loaded from `skills/*.md` via `SkillLoader`

### Test Node

- **Injection**: `generate_tests_node` uses `MemoryClient(namespace="test")` to inject test strategies
- **Settlement**: test-memory settlement has been retired; active settlement paths are plan / solve / oracle / hacker.
- **Payload**: `{constraints_patterns, generation_strategies, validator_pitfalls}`

## Reward Shaping

```python
if status == "success":
    reward = 1.0
elif status == "max_iterations":
    reward = -1.0
else:
    reward = pass_rate - 0.5  # Maps [0, 1] to [-0.5, 0.5]
```

## Feature Extraction

Features are derived from:

1. **FSM state**: `FSM:SOLVE_DRAFT`, `FSM:GEN_COMPILE`
2. **Failure type**: `FAIL:TIMEOUT`, `FAIL:COMPILE_FAIL`
3. **Attempt count**: `ATTEMPT:1`, `ATTEMPT:2`, ...
4. **Canonical problem**:
   - `TYPE:dp`, `TYPE:graph`
   - `ELEM:prefix_sum`, `ELEM:sliding_window`
   - `CONSTR:n_1e5`, `CONSTR:n_2e5`
   - `OBJ:count`, `OBJ:optimize`
   - `INPUT:array`, `OUTPUT:single`

## Usage Example

```python
from src.memory import MemoryClient, MemoryNamespace

# Initialize
memory = MemoryClient(
    namespace=MemoryNamespace.PLAN,
    config=config,
    problem_desc=problem_desc,
    canonical=canonical,
)

# Get injection
advice, item_ids = memory.get_injection(
    fsm_state="SOLVE_DRAFT",
    failure_type=None,
    attempt_count=0,
)

# ... agent generates output ...

# Log event (updates policy + item stats + event log)
obs = Observation(
    fsm_state="SOLVE_CHECK",
    canonical=canonical,
)
memory.log_event(obs, item_ids, reward=1.0, iteration=0)
```

## Configuration

Enable memory in config:

```python
config = {
    "trainable_memory": {
        "enabled": True,
        "data_dir": "data/memory",
        "plan_top_k": 5,
        "solve_top_k": 3,
        "test_top_k": 3,
    }
}
```

## Cold Start

On first run with `trainable_memory.enabled = True`, the system will:

1. Create the data directories
2. Seed items from namespace-specific templates
3. Initialize empty policy weights

Optionally run offline training script to populate from historical data.

## Future Extensions

- **Embeddings**: Replace sparse feature keys with dense embeddings
- **Graph structure**: Add explicit item-to-item edges for strategy composition
- **Thompson sampling**: Upgrade from epsilon-greedy to Thompson sampling or UCB
- **Offline RL**: Use event logs for batch policy gradient updates
