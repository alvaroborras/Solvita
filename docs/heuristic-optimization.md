# Heuristic optimization

Solvita's heuristic workflow is additive: it does not modify the existing
AC/WA LangGraph or exact-problem memories.

## OGC preflight

```bash
docker build -f docker/heuristic-cpp23.Dockerfile \
  -t solvita-heuristic-cpp23:latest .
python -m src.heuristic.cli validate-problem --problem ogc
```

The command verifies the frozen 32/8 split, trusted plugin hashes, Docker image,
and the conservative C++23 baseline. Generated candidates are never executed
natively; the host compilation used by `validate-problem` is limited to the
checked-in trusted baseline.

## Runs

```bash
python -m src.heuristic.cli run \
  --problem ogc --engine solvita_dgs --run-id ogc-dgs-1 \
  --solver-command "./solver_bridge"
python -m src.heuristic.cli resume \
  --problem ogc --engine solvita_dgs --run-id ogc-dgs-1 \
  --solver-command "./solver_bridge"
python -m src.heuristic.cli inspect --run-id ogc-dgs-1
python -m src.heuristic.cli export-trajectories --run-id ogc-dgs-1
python -m src.heuristic.cli compare \
  --experiment config/heuristic/ogc_comparison.yaml
# Add --execute after reviewing the twelve-run matrix and budget.
```

Normal runs apply the three-epoch stagnation rule. Add `--full-budget` to
`run`, `resume`, or executable `compare` commands when verifying exact
proposal/evaluation accounting without early stopping.

When no bridge is supplied, the run uses Solvita's configured
`UnifiedLLMClient` for Planner, Solver, Oracle, and Hacker calls. `solver_bridge`
receives one JSON request on stdin containing the selected
operator, parent bundles, and training-only context. It returns canonical
`CandidateBundleV1` JSON. Pass `--smoke-seed` to alternate two
semantics-preserving baseline variants for acceptance accounting; repeated
variants still spend proposal budget.

Production startup fails closed unless:

- the locked-down Docker image exists;
- GEPA's OA API from commit
  `f919db0a622e2e9f9204779b81fe00cc1b2d808f` is importable;
- `sentence-transformers/all-MiniLM-L6-v2` is available locally.

All mutable runtime data is stored under `.solvita/heuristic/`: SQLite metadata
in WAL mode, content-addressed artifacts, compilation cache, and trajectory
exports. Heuristic strategy cards use a separate database from exact-problem
memory.
