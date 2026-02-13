# Implementation Summary: Storage + Sandbox + Feedback + Patch

## Overview
Completed comprehensive upgrade to the Solvita agent system with four major improvements:
1. SQLite-backed memory persistence
2. rlimit-based secure C++ execution
3. Enhanced feedback with 10 counterexamples
4. Patch-based code generation using SEARCH/REPLACE

---

## 1. SQLite Memory Persistence

### What Changed
- **Before**: `items.jsonl` + `events.jsonl` (line-delimited JSON files)
- **After**: SQLite database with transactional writes and indexed queries

### Storage Structure
```
data/memory/
├── plan/
│   ├── memory.db          # SQLite database (items + events tables)
│   └── policy.json        # Trainable weights (with file locking)
├── solve/
│   ├── memory.db
│   └── policy.json
└── test/
    ├── memory.db
    └── policy.json
```

### Database Schema

**items table:**
- `id` (TEXT PRIMARY KEY): Strategy ID
- `namespace` (TEXT): plan/solve/test
- `text` (TEXT): Strategy description
- `payload_json` (TEXT): Namespace-specific data
- `tags_json` (TEXT): Tags array
- `uses` (INTEGER): Usage count
- `avg_reward` (REAL): Average reward
- `deprecated` (INTEGER): Deprecation flag
- `created_at`, `last_used` (TEXT): Timestamps

**events table:**
- `id` (INTEGER PK AUTOINCREMENT): Auto-increment ID
- `timestamp` (TEXT): ISO timestamp
- `namespace` (TEXT): plan/solve/test
- `observation_json` (TEXT): Full observation state
- `selected_item_ids_json` (TEXT): Selected strategy IDs
- `reward` (REAL): Outcome reward
- `problem_hash` (TEXT): Problem identifier
- `iteration` (INTEGER): Attempt number

### Migration
- Automatically detects existing `items.jsonl` and `events.jsonl`
- Imports data into SQLite on first run
- Renames old files to `.jsonl.migrated`

### Files Modified
- `src/memory/store.py`: Complete rewrite to use SQLite
- `src/memory/client.py`: Removed dual-backend logic
- `src/memory/policy.py`: Added `fcntl` file locking for `policy.json`

---

## 2. Secure C++ Execution with Resource Limits

### What Changed
- **Before**: Plain `subprocess.run()` with only timeout
- **After**: Linux `rlimit`-based sandboxing with comprehensive resource caps

### ExecutionLimits Profiles

**Default Compile:**
- CPU: 30s, Wall: 35s
- Memory: 2GB
- File size: 50MB
- Max processes: 50, Max open files: 100

**Default Run:**
- CPU: 2s, Wall: 3s
- Memory: 512MB
- File size: 10MB
- Max processes: 1, Max open files: 50

**Diagnostic Compile (with sanitizers):**
- CPU: 60s, Wall: 70s
- Memory: 4GB (sanitizers need more)
- File size: 100MB
- Max processes: 50, Max open files: 100

### Security Features
- `RLIMIT_AS`: Address space (memory) limit
- `RLIMIT_CPU`: CPU time limit
- `RLIMIT_FSIZE`: Output file size limit
- `RLIMIT_NPROC`: Process count limit
- `RLIMIT_NOFILE`: Open file descriptor limit
- Minimal environment variables (PATH, HOME, LC_ALL only)
- Execution in restricted temp directory

### Compilation Modes
- **Normal**: `-O2 -std=c++17` (performance)
- **Diagnostic**: `-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer` (debugging UB/memory errors)

### Files Modified
- `src/utils/cpp_execution.py`: Complete rewrite with `ExecutionLimits` and `preexec_fn`
- `src/nodes/generate_code.py`: Updated to use new limits API
- `src/nodes/generate_tests.py`: Uses default limits
- `src/nodes/run_tests.py`: Uses default limits

---

## 3. Enhanced Feedback: 10 Counterexamples

### What Changed
- **Before**: Max 3 representative failures shown to LLM
- **After**: Up to 10 failures with intelligent selection

### Selection Strategy
Smart selector picks failures covering:
1. **Different error types**: Timeout, Runtime Error, Wrong Answer, Checker failures
2. **Shortest inputs**: Easiest to trace and debug
3. **Largest numeric errors**: Most significant deviations
4. **Different input scales**: Small and large test cases

### Failure Information Structure
Each failure now includes:
- `type`: timeout/runtime_error/wrong_answer/checker
- `input`: Test input (truncated if > 300 chars)
- `expected`: Expected output (truncated if > 200 chars)
- `actual`: Actual output (truncated if > 200 chars)
- `details`: stderr, exit code, checker message

### Files Modified
- `src/nodes/analyze_feedback.py`: 
  - `_select_representative_failures()` upgraded to select 10 with diversity
  - Added `_run_diagnostic_sanitizer()` for RE/unstable failures
- `src/nodes/generate_code.py`: 
  - `_build_prompt()` now renders up to 10 failures with truncation

---

## 4. Patch-Based Code Generation (SEARCH/REPLACE)

### What Changed
- **Before**: Every iteration generates complete new code
- **After**: 
  - **First iteration**: Generate complete code
  - **Subsequent iterations**: Generate SEARCH/REPLACE patches

### SEARCH/REPLACE Format
```text
<<<<<<< SEARCH
<exact contiguous code snippet from previous version>
=======
<replacement code with fix>
>>>>>>> REPLACE
```

### Rules
1. SEARCH block must match **exactly once** in previous code
2. Multiple blocks can be applied sequentially
3. Preserves indentation and formatting
4. Failed patches → retain previous code (no crash)

### Benefits
- **Surgical fixes**: Only change what's broken
- **Traceability**: Unified diff logged for each patch
- **Reduced hallucination**: LLM focuses on specific buggy lines
- **Better learning**: Memory system learns "bug → fix" patterns

### Implementation
- `src/utils/patch_utils.py`: Parser and applicator for SEARCH/REPLACE blocks
- `src/nodes/generate_code.py`: 
  - `_build_initial_prompt()`: For first-time generation
  - `_build_patch_prompt()`: For subsequent iterations with SEARCH/REPLACE format
  - Main logic detects `iteration == 0` vs patch mode
  - Logs unified diff for every successful patch

---

## 5. Diagnostic Sanitizer Support

### What Changed
When runtime errors or unstable failures occur:
- Automatically recompile with `-fsanitize=address,undefined`
- Run smallest failing test case
- Capture sanitizer output (memory errors, undefined behavior, stack traces)
- Inject sanitizer output into LLM analysis prompt

### Trigger Conditions
- Runtime errors detected in test results
- Unstable pass rate (0 < pass_rate < 1.0 with few failures)

### Files Modified
- `src/nodes/analyze_feedback.py`: Added `_run_diagnostic_sanitizer()` function

---

## Verification

All features tested and verified:
- ✅ SQLite MemoryStore: CRUD, persistence, reload
- ✅ Patch utilities: Parse, apply, reject invalid patches
- ✅ Execution limits: Compile/run with resource caps
- ✅ MemoryClient integration: End-to-end workflow

Test script: `verify_implementation.py`

---

## Configuration

No config changes required. Default behavior:
```python
config = {
    "trainable_memory": {
        "enabled": True,
        "data_dir": "data/memory",
        "plan_top_k": 3,
        "solve_top_k": 3,
        "test_top_k": 3,
    }
}
```

SQLite is now the **only** storage backend (no dual-mode complexity).

---

## Files Summary

### New Files
- `src/utils/patch_utils.py`: SEARCH/REPLACE parser and applicator
- `verify_implementation.py`: Verification test script

### Modified Files
- `src/memory/store.py`: Complete rewrite for SQLite
- `src/memory/client.py`: Simplified to use SQLite only
- `src/memory/policy.py`: Added file locking
- `src/utils/cpp_execution.py`: Complete rewrite with rlimit sandboxing
- `src/nodes/generate_code.py`: Patch-based generation + initial mode
- `src/nodes/generate_tests.py`: Use ExecutionLimits API
- `src/nodes/run_tests.py`: Use ExecutionLimits API
- `src/nodes/analyze_feedback.py`: 10 counterexamples + diagnostic sanitizer
- `requirements.txt`: Removed unused deps (neo4j, chromadb, faiss, sentence-transformers, pandas)

### Removed Dependencies
- Knowledge Graph libraries (neo4j, chromadb, faiss-cpu, sentence-transformers)
- pandas (not used after KG removal)

---

## Next Steps

1. **Offline Training**: Use `scripts/train_plan_policy.py` to pre-train from historical data
2. **Skill Library**: Populate `skills/` directory with more `.md` snippets
3. **Production Run**: Test on real competitive programming problems
4. **Analysis**: Query `events` table to understand learning dynamics

## Migration Notes

Existing users with jsonl data:
- Data will auto-migrate on first run with new code
- Old files renamed to `.jsonl.migrated` (safe backup)
- No manual intervention needed
