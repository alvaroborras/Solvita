# Memory System Migration Report

## Date: 2026-02-13

## Summary

Successfully migrated from fragmented memory v1/v2 system to a **unified trainable memory architecture** with namespace isolation for plan/solve/test agents.

## Changes Made

### 1. Deleted Old Memory System (v1)
- ❌ Removed `src/memory/` (10 files, ~1200 lines)
  - Old MemoryClient, PlanMemoryClient, MemoryGraph, PolicyNetwork
  - Separate plan/test implementations with duplicated logic
- ❌ Removed `tests/memory/` (old v1 tests)
- ❌ Removed `scripts/verify_memory_manual.py` (obsolete verification script)

### 2. Renamed memory_v2 → memory
- ✅ `src/memory_v2/` → `src/memory/`
- ✅ `tests/memory_v2/` → `tests/memory/`
- ✅ `docs/memory_v2_architecture.md` → `docs/memory_architecture.md`

### 3. Updated Class Names (removed V2 suffix)
- `MemoryClientV2` → `MemoryClient`
- `BanditPolicyV2` → `BanditPolicy`
- `FeaturizerV2` → `Featurizer`
- `ObservationV2` → `Observation`

### 4. Removed Obsolete KG Module
- ❌ Deleted `src/knowledge/` (empty directory)
- ❌ Deleted `src/nodes/retrieve_knowledge.py`
- ✅ Removed `retrieve_knowledge_node` from `nodes/__init__.py`

### 5. Unified Configuration
- Changed config key: `trainable_memory_v2` → `trainable_memory`
- Changed default data dir: `data/memory_v2` → `data/memory`

### 6. State Schema Cleanup
- Updated `PlanData.memory_strategy_ids` → `memory_item_ids`
- Added `SolutionData.memory_item_ids` field

## New Architecture

### Unified Memory Module (`src/memory/`)
```
src/memory/
├── __init__.py           # Public API exports
├── types.py              # MemoryNamespace, MemoryItem, MemoryEvent, Observation
├── store.py              # MemoryStore (items.jsonl, events.jsonl)
├── policy.py             # BanditPolicy (bias + sparse feature weights)
├── featurizer.py         # Featurizer (canonical → feature keys)
├── client.py             # MemoryClient (namespace-aware unified interface)
├── skill_loader.py       # SkillLoader (for solve namespace)
└── seeds/                # Cold-start seed items
    ├── __init__.py
    ├── plan_items.py     # Planning strategies
    ├── solve_items.py    # Solving strategies + skill refs
    └── test_items.py     # Test generation strategies
```

### Namespace Isolation
Each agent (plan/solve/test) has its own:
- **Item store**: Namespace-specific memory items
- **Policy params**: Trainable weights (bias + sparse W)
- **Event log**: Append-only trajectory history

### Edge Weights Definition
The "network" is a bipartite graph:
- **Left nodes**: Feature keys (e.g., `TAG:dp`, `CONSTR:n_1e5`, `FAIL:TIMEOUT`)
- **Right nodes**: Memory items
- **Edge weight**: `W[feature, item]` learned via contextual bandit

Scoring: `score(item) = bias[item] + Σ W[feature, item]`

### Integration Points
1. **plan_solution_node**: Injects planning strategies → stores item IDs
2. **generate_code_node**: Injects solve strategies + skills → stores item IDs
3. **generate_tests_node**: Injects test strategies → logs events inline
4. **update_plan_memory_node**: Settles plan rewards post-evaluation
5. **update_solve_memory_node**: Settles solve rewards post-evaluation

## Verification Results

### Clean grep results
- ✅ No references to `memory_v2`, `MemoryClientV2`, `BanditPolicyV2`, etc.
- ✅ No references to `retrieve_knowledge`, `knowledge` module
- ✅ No references to `trainable_memory_v2` config key

### Linter status
- ✅ No linter errors in memory module
- ✅ No linter errors in nodes
- ⚠️  2 warnings in workflow.py (external dependency resolution - not a code issue)

### Files Removed
Total: ~18 files deleted
- 10 files from old `src/memory/`
- 1 file from `tests/memory/`
- 1 file `scripts/verify_memory_manual.py`
- 1 directory `src/knowledge/`
- 1 file `src/nodes/retrieve_knowledge.py`
- Plus intermediate v2 files during rename

### Files Created/Modified
- 11 files in new unified `src/memory/` module
- 2 test files in `tests/memory/`
- 1 skill file in `skills/`
- 5 node files updated (plan, generate_code, generate_tests, update_plan/solve_memory)
- 1 state file updated
- 1 architecture doc updated

## Configuration Example

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

## Benefits

1. **Single source of truth**: One memory system, not three separate implementations
2. **Namespace isolation**: Each agent learns independently while sharing infrastructure
3. **Event logging**: Full trajectory history for offline analysis and debugging
4. **Explicit edge weights**: Clear bipartite graph structure (feature → item)
5. **Skill system**: Solve agent can reference reusable code snippets from `skills/`
6. **Cleaner codebase**: ~15 fewer files, no v1/v2 confusion

## Breaking Changes

- Old memory files (`strategies.jsonl`, `policy_params.json`) are **ignored**
- Config key changed from `trainable_memory_v2` to `trainable_memory`
- System cold-starts with seed items on first run

## Next Steps (Optional)

1. Add `scripts/memory_tools.py` for inspecting event logs
2. Consolidate reward computation utils (currently duplicated in update nodes)
3. Create offline training script using event logs
4. Add more skills to `skills/` directory
5. Enhance featurizer with embeddings for richer features
