# Trainable Memory System Guide

## Quick Start

The unified trainable memory system enables agents to learn from experience across multiple problem-solving sessions.

### Enable in Config

```python
config = {
    "trainable_memory": {
        "enabled": True,
        "data_dir": "data/memory",
        "plan_top_k": 5,    # Top-K items for plan agent
        "solve_top_k": 3,   # Top-K items for solve agent
        "test_top_k": 3,    # Top-K items for test agent
    },
    "oracle": {
        "mode": "safe",          # safe | balanced | legacy
        "accept_threshold": 0.95,
        "enable_fallback": False,
    },
}
```

For the redesigned oracle/testgen flow:

- `safe` is the default and prefers abstention when confidence is insufficient
- `balanced` allows a modestly looser threshold and optional fallback family use
- `legacy` preserves behavior close to the older oracle path for comparison

### Basic Usage

```python
from src.memory import MemoryClient, MemoryNamespace

# Initialize for specific agent
memory = MemoryClient(
    namespace=MemoryNamespace.PLAN,  # or SOLVE, TEST
    config=config,
    problem_desc=problem_description,
    canonical=canonical_problem,
)

# Get strategies to inject into prompt
advice_text, selected_item_ids = memory.get_injection(
    fsm_state="SOLVE_DRAFT",
    failure_type=None,
    attempt_count=0,
)

# ... inject advice_text into LLM prompt ...
# ... agent generates output ...

# Log outcome (updates policy + statistics)
obs = Observation(
    fsm_state="SOLVE_CHECK",
    canonical=canonical_problem,
)
memory.log_event(obs, selected_item_ids, reward=1.0, iteration=0)
```

## Architecture

### Three Isolated Namespaces

Each agent has its own memory space with different item types:

#### 1. Plan Agent (`namespace="plan"`)
**Stores**: Problem-type tags, required subfunctions, canonical hints

**Example item**:
```python
{
    "text": "Dynamic programming: identify optimal substructure",
    "tags": ["dp", "optimization"],
    "payload": {
        "problem_tags": ["dp", "memoization"],
        "subfunctions": ["define_dp_state", "identify_transitions"],
        "canonical_hints": "Look for optimal substructure...",
    }
}
```

#### 2. Solve Agent (`namespace="solve"`)
**Stores**: Step-level strategies, skill references, anti-patterns

**Example item**:
```python
{
    "text": "Implement careful index bounds checking",
    "tags": ["debugging", "bounds"],
    "payload": {
        "step_strategies": [
            "Check loop bounds: use <= vs < carefully",
            "Verify array indices within [0, n-1]",
        ],
        "skills": [{"skill_id": "quick_sort", "path": "skills/quick_sort.md"}],
        "anti_patterns": ["Mixing 0-indexed and 1-indexed logic"],
    }
}
```

#### 3. Test Agent (`namespace="test"`)
**Stores**: Constraint patterns, generation strategies, validator pitfalls

**Example item**:
```python
{
    "text": "Generate boundary tests (min/max values)",
    "tags": ["boundary", "constraints"],
    "payload": {
        "constraints_patterns": ["n=1", "n=max_n"],
        "generation_strategies": [
            "Include test with minimum n",
            "Include test with maximum n",
        ],
        "validator_pitfalls": ["Forgetting to check n >= min_n"],
    }
}
```

#### 4. Oracle Agent (`namespace="oracle"`)
**Stores**: Reference-solver strategy families used by `generate_tests` to build trusted supervision artifacts.

**Example item**:
```python
{
    "family_id": "oracle.dp.topdown",
    "text": "Top-down Memoized DP",
    "route_hint": "exact_single_answer",
    "tags": ["dp", "oracle"],
    "payload": {
        "brute_force_strategies": ["Exponential State Space to Polynomial via Top-Down DP"],
        "complexity_notes": ["O(StateSpace). Filters invalid states directly."],
    }
}
```

### How the Network Works

The system learns a **bipartite scoring graph**:

```
Feature Keys                Memory Items
(extracted from problem)    (strategies/skills)

TAG:dp         ────weight──→ Item1: DP strategy
CONSTR:n_1e5   ────weight──→ Item2: Efficient impl
FAIL:TIMEOUT   ────weight──→ Item3: Optimization hint
FSM:SOLVE      ────weight──→ Item4: Debug checklist
```

**Scoring formula**: `score(item) = bias[item] + Σ W[feature, item]`

**Learning rule**: `W[f, item] ← W[f, item] + α · reward`

### Feature Extraction

Features are automatically derived from:
- **FSM state**: `FSM:SOLVE_DRAFT`, `FSM:GEN_COMPILE`
- **Failure type**: `FAIL:TIMEOUT`, `FAIL:COMPILE_FAIL`
- **Problem canonical**:
  - `TYPE:dp`, `TYPE:graph`
  - `ELEM:prefix_sum`
  - `CONSTR:n_1e5`
  - `OBJ:count`, `OBJ:optimize`

### Reward Signal

```python
if status == "success":
    reward = +1.0
elif status == "max_iterations":
    reward = -1.0
else:
    reward = pass_rate - 0.5  # Partial success
```

## Workflow Integration

### Plan Agent Flow
```
plan_solution_node
  ↓ (stores memory_item_ids in state['plan'])
generate_code + generate_tests (parallel)
  ↓
compile → run_tests → unified_check
  ↓
update_plan_memory_node (settles reward)
```

### Solve Agent Flow
```
generate_code_node
  ↓ (stores memory_item_ids in state['solution'])
compile → run_tests → unified_check
  ↓
update_solve_memory_node (settles reward)
```

### Test Agent Flow
```
generate_tests_node
  ↓ (logs events inline during generator/validator/checker loops)
  └─ immediate reward updates on compile/runtime failures
```

### Hacker Agent Flow
```
hack_test_node
  ↓ (stores hacker_memory_item_ids and raw hacker verdict evidence in state)
settle_hacker_memory
  ↓ (computes final reward and logs structured metadata)
```

## Skills System

The solve agent can reference reusable code skills from `skills/*.md`:

### Skill File Format
```markdown
## Skill: QuickSort_InPlace
- Tag: Quick_Sort
- Category: sorting
- Applicable_when: in-place, not stable
- Complexity: avg O(n log n), worst O(n^2)
- Pitfalls: recursion depth, RNG seeding

### Snippet (C++17)
<code block>
```

### Referencing Skills
Solve memory items include skill references:
```python
"skills": [{"skill_id": "quick_sort", "path": "skills/quick_sort.md"}]
```

When injected, the SkillLoader reads the file and includes the full snippet.

## On-Disk Structure

```
data/memory/
├── plan/
│   ├── memory.db         # SQLite items + events
│   └── policy.json       # Trainable weights
├── solve/
│   ├── memory.db
│   └── policy.json
├── oracle/
│   ├── memory.db
│   └── policy.json
└── hack/
    ├── memory.db
    └── policy.json
```

### items.jsonl Format
One item per line (JSONL):
```json
{"id": "abc123", "namespace": "plan", "text": "...", "payload": {...}, "uses": 5, "avg_reward": 0.8}
{"id": "def456", "namespace": "plan", "text": "...", "payload": {...}, "uses": 3, "avg_reward": -0.2}
```

### events / memory.db Event Fields
Events are stored in SQLite. Conceptually each event includes:
```json
{"timestamp": "...", "namespace": "hack", "observation": {...}, "selected_item_ids": [...], "reward": 1.0, "metadata": {"route_used": "semantic", "hack_result": "BREAK"}}
```

For HACK settlement, metadata may include:
- `route_used`
- `hack_result`
- `failure_type`
- `generator_failure_kind`
- `compile_failures`
- `validity_passed`
- `buggy_distinguished`

Formal offline Hacker trainer:

```bash
python3 scripts/train_hacker.py --dataset data/solvita_train/solvita_train_tanh.jsonl --data-dir data/memory
```

`scripts/train_hacker_input.py` is legacy and is not the formal trainer.

### policy.json Format
```json
{
    "bias": {"item1": 0.5, "item2": -0.1},
    "weights": {
        "FSM:SOLVE_DRAFT": {"item1": 0.3, "item2": 0.1},
        "TAG:dp": {"item1": 0.8, "item2": 0.0}
    },
    "learning_rate": 0.01,
    "epsilon": 0.1
}
```

## Advanced Usage

### Offline Training
Use event logs for batch updates:

```python
from src.memory import MemoryClient, MemoryNamespace

memory = MemoryClient(namespace=MemoryNamespace.PLAN, config=config)

# Load historical events
events = memory.store.get_events(limit=1000)

# Batch update policy
records = [
    {
        "observation": event.observation,
        "item_ids": event.selected_item_ids,
        "reward": event.reward,
    }
    for event in events
]
memory.policy.batch_update(records)
memory.policy.save()
```

### Adding New Items
```python
from src.memory.types import MemoryItem, MemoryNamespace

new_item = MemoryItem(
    id="custom_123",
    namespace=MemoryNamespace.SOLVE,
    text="Custom solving strategy",
    payload={
        "step_strategies": ["Step 1", "Step 2"],
        "skills": [],
        "anti_patterns": [],
    },
    tags=["custom", "optimization"],
)

memory.store.add_item(new_item)
memory.store.save_items()
```

### Deprecation
Items with consistently poor performance are auto-deprecated:
- After 20+ uses
- If avg_reward < -0.3
- Deprecated items are excluded from selection

## Testing

Run memory system tests:
```bash
pytest solvita/tests/memory/
```

Tests cover:
- Namespace isolation
- Item persistence
- Event logging
- Policy updates
- Feature extraction
- Client integration

## Future Enhancements

1. **Dense embeddings**: Replace sparse feature keys with sentence-transformers
2. **Graph structure**: Add explicit item→item edges for strategy composition
3. **Advanced bandits**: Thompson sampling, UCB, LinUCB
4. **Offline RL**: Policy gradient updates from event trajectories
5. **Memory tools CLI**: Inspect, export, analyze, visualize
