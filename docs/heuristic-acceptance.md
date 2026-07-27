# Heuristic Optimization v1 Acceptance

This checklist maps the eight implementation requirements to executable
evidence. Runtime artifacts are intentionally written outside the repository.

## 1. OGC evaluator

- The immutable SDK and conservative baseline live under `problems/ogc/`.
- `docker/heuristic-cpp23.Dockerfile` pins GCC 13 Bookworm by digest.
- `validate-problem` compiles and runs the baseline in Docker, never through a
  native fallback:

  ```bash
  python -m src.heuristic.cli validate-problem --problem ogc
  ```

  Acceptance result: 40/40 feasible, objective range 36,495,517–3,779,551,151.
- `test_docker_evaluator_integration.py` executes compile, runtime, malformed
  output, checker infeasibility, flood, timeout, network, scorer-path, and
  validation-path attacks.

## 2. Persistence and scoring

- `HeuristicStore` uses WAL/FULL synchronization, immutable evaluation rows,
  content-addressed artifacts, run-scoped 10s/60s BKS snapshots, atomic
  proposal/epoch commits, and resumable RNG/archive/surrogate observations.
- Dynamic BKS activation recomputes archive and instance-conditioned DGS
  targets only at epoch boundaries.
- Validation uses stationary baseline-relative gain and a one-sided bootstrap
  lower confidence bound; infeasible candidates cannot become the final
  incumbent.

## 3–6. Search, GEPA, and knowledge

- The event-wise loop implements 16 independent seeds, 24 random-QD
  transitions, 160 guided actions, ten promotion boundaries, and the
  Planner/Solver/Oracle/Hacker cadence.
- The QD pool enforces 7/6/5/2 quotas. MiniLM, instance residuals, the
  five-head utility model, action transition models, fidelity embeddings,
  uncertainty/novelty/coverage acquisition, and the repair lane are covered
  by `tests/heuristic/test_dgs.py` and `test_scoring_archive.py`.
- The pinned GEPA OA API exposes `solvita_dgs` and `random_qd`; default GEPA
  runs through the upstream `gepa` engine.
- Strategy cards use a separate SQLite database. Incubator cards remain
  owner-problem-local; cross-family promotion requires positive evidence from
  two families or explicit human approval. Gains and negative transfers are
  labelled observational/non-causal.

## 7. Commands and exports

The public commands are implemented in `src/heuristic/cli.py`. Comparison
reports include validation LCB, best-so-far AUC, 10s/60s objectives,
bottom-tail quality, invalid/TLE rate, QD coverage, BKS improvements, tokens,
support/evaluation calls, wall time, and cost when supplied by the backend.
Trajectory export also materializes the validation-selected canonical bundle
and source tree.

## 8. OGC acceptance evidence

- Heuristic suite: 46 passed, including executable Docker isolation and
  multi-file candidate compilation tests.
- Exact-CP parity slice: 39 passed in both the implementation worktree and
  detached baseline commit `236152e977cd2ca61ac06e561e1dd534d968b05a`.
- The repository's complete suite has the same four pre-existing collection
  errors at baseline and in this worktree (missing legacy modules); the
  heuristic integration does not modify `src/graph`, `src/nodes`,
  `src/memory`, `src/utils`, or `scripts`.
- Full deterministic acceptance matrix: four engines × three replicates, each
  with exactly 200 programs, ten epochs, and 7,120 logical evaluations.
- The exported Solvita-DGS incumbent recompiles in the pinned image and is
  feasible on all 40 OGC instances.

The full-budget matrix uses `--smoke-seed` to verify orchestration and exact
accounting without API cost. It is **not** an optimization-quality claim.
Scientific comparisons must rerun the same matrix with a configured model or
solver bridge and without `--smoke-seed`.
