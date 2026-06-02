# LangGraph Optimization Design for Pass@1 / Benchmark

## Goal

Improve `pass@1` and benchmark score for the competitive-programming agent without turning every problem into a high-cost, full-pipeline run.

The design target is:

- increase first-attempt correctness on benchmark problems
- reduce false accepts that later fail on official tests
- keep cost growth moderate rather than unbounded
- preserve the current LangGraph-centered architecture

This design does **not** optimize for maximum robustness at any cost. It optimizes for benchmark effectiveness under moderate extra runtime budget.

## Current Problems

The current workflow has the right major stages, but it is suboptimal for `pass@1`:

1. `generate_tests` is too heavy and too early.
   Every problem pays the cost of generator/validator/checker/oracle construction even when a lightweight path would suffice.

2. success is decided too directly.
   After `codegen_phase`, the workflow can move to `hacker_phase` or end too quickly, without an independent acceptance layer.

3. generated auxiliaries are too correlated.
   Solver, oracle, checker, and generator are often derived from the same problem understanding and similar prompts, so they can fail together.

4. failure evidence is under-structured.
   The existing memory system learns strategy preference, but it does not maintain a strong reusable bank of concrete failures, counterexamples, and risk patterns.

5. heavy phases are not budgeted by risk.
   Test generation, skill planning, and hacker execution are mostly controlled by static toggles rather than per-problem runtime policy.

## Design Summary

The optimized workflow should be:

- light by default
- heavy only when risk signals justify it
- independently verified before acceptance
- continuously improved by concrete failure reuse

The workflow is changed by adding three primary modules and one support node:

1. `failure_bank`
2. `solve_controller`
3. `verifier_phase`
4. `bootstrap_tests`

`bootstrap_tests` is not a new intelligence module. It is a small support stage that ensures the workflow can skip full test generation without losing a valid execution path.

## Recommended Workflow Topology

```text
abstract_phase
-> failure_bank_lookup
-> pre_solve_controller
-> bootstrap_tests
-> { full_testgen_phase ? }
-> { solver_skill_plan ? }
-> codegen_phase
-> verifier_phase
-> post_verify_controller
   -> accept -> { hacker_phase | END }
   -> repair -> codegen_phase
   -> escalate_testgen -> full_testgen_phase -> codegen_phase

hacker_phase
-> { SAFE -> END, BREAK -> codegen_phase }
```

Interpretation:

- all problems run `abstract_phase`
- all problems receive failure-bank context
- all problems receive a low-cost runtime policy decision
- all problems get a minimal trusted test set from `bootstrap_tests`
- only risky problems run the current heavy `generate_tests` logic
- all candidate solutions go through an independent verifier before acceptance
- hacker is no longer a mandatory success tail

## Module 1: Bootstrap Tests

### Purpose

Provide a guaranteed minimal, high-trust executable test set before code generation.

### Why It Is Needed

Today, `run_tests_node` expects `tests.generated_tests` to exist. If the workflow skips the current heavy `generate_tests_node`, the codegen loop loses its evaluation substrate.

`bootstrap_tests` solves this by constructing a small trusted suite using only cheap and reliable sources.

### Inputs

- `problem.public_tests`
- local exact certification cases already derivable in Python
- high-trust counterexamples from `failure_bank_context`

### Outputs

Populate:

- `tests.generated_tests`
- `tests.total_tests`
- `tests.ready`
- `tests.trust_tiers`

### Trust Tier Contract

`bootstrap_tests` introduces explicit trust levels:

- `trusted`
  public tests, local exact certification tests, high-trust historical counterexamples
- `advisory`
  optional later tests from heavy oracle/testgen stages

This separation is required so later modules can distinguish strong negative evidence from weak suggestion.

### Scope Constraint

`bootstrap_tests` must remain:

- deterministic
- low-cost
- mostly Python/local
- free of heavy LLM usage

It is infrastructure, not a reasoning phase.

## Module 2: Failure Bank

### Purpose

Store and retrieve reusable failure evidence:

- concrete counterexamples
- recurring wrong-answer patterns
- recurring complexity mistakes
- successful repair summaries

### Why Existing Memory Is Not Enough

The current memory system is strategy-oriented. It is useful for biasing plan/solve/oracle/hack choices, but it is not the right place to store high-confidence failure artifacts.

The failure bank is evidence-oriented rather than policy-oriented.

### Core Records

#### `failure_case`

Concrete, reproducible failure evidence.

Suggested fields:

- `case_id`
- `problem_fingerprint`
- `canonical_objective`
- `tags_level1`
- `tags_level2`
- `constraint_bucket`
- `phase_found`
- `failure_type`
- `failure_subtype`
- `input_text`
- `expected_output`
- `actual_output`
- `checker_context`
- `trusted_level`
- `source_run_id`
- `source_solution_hash`
- `explanation`
- `minimized`
- `created_at`

#### `risk_pattern`

Abstract error pattern reusable across many problems.

Suggested fields:

- `pattern_id`
- `title`
- `applicable_tags`
- `trigger_features`
- `anti_pattern_text`
- `recommended_checks`
- `evidence_case_ids`

#### `repair_outcome`

Structured summary of what eventually fixed a known failure mode.

Suggested fields:

- `repair_id`
- `linked_case_id`
- `repair_strategy`
- `repair_summary`
- `before_solution_hash`
- `after_solution_hash`
- `validated`

### Retrieval

The first version should prefer structured retrieval over a vector-only design.

Primary retrieval keys:

- `tags_level1 + failure_type`
- objective bucket
- constraint bucket
- high-risk structural tags such as cyclic/counting/overflow/graph edge-case/string corner
- phase where the problem was exposed
- failure subtype

Optional semantic retrieval can later be added over:

- objective
- required properties
- edge cases

### Read Paths

#### `failure_bank_lookup` after abstract

Returns:

- high-risk anti-patterns
- representative trusted counterexamples
- prior repair hints

Used by:

- `pre_solve_controller`
- `generate_code`
- `verifier_phase`

#### failure-type-specific lookup after verifier or feedback

Returns:

- close-match failures
- similar minimized counterexamples
- repair summaries for the same subtype

Used by:

- `analyze_feedback`
- later code repair prompts

### Write Paths

Write only from high-confidence sources:

1. verifier-discovered trusted failures
2. successful hacker breaks
3. official benchmark failures with formal evidence
4. fully validated repair completions

Do **not** write unverified speculative analysis directly into the main bank.

### Storage

Use a separate SQLite database, e.g.:

`artifacts/failure_bank/failure_bank.db`

This preserves a clean boundary from the existing trainable memory subsystem.

## Module 3: Solve Controller

### Purpose

Allocate runtime budget and choose the right path for each problem.

### Principle

The controller should be:

- cheap
- structured
- explainable
- mostly non-generative

The first version should be rule-based with a risk score. It should not depend on a new LLM call.

### Two Controller Calls

#### `pre_solve_controller`

Position:

- after `abstract_phase`
- after `failure_bank_lookup`
- before heavy test generation and skill planning

Responsibilities:

- decide whether to run full heavy test generation immediately
- decide whether to run solver skill planning
- set initial codegen budget
- choose verifier strictness
- decide whether hacker is allowed on success

Inputs:

- canonical problem summary
- selected tags
- abstract confidence
- constraint buckets
- public test availability/quality
- failure-bank matches
- benchmark mode flag
- remaining runtime budget

Outputs to `solve_policy`:

- `risk_score`
- `run_testgen_initially`
- `run_skill_plan`
- `initial_codegen_budget`
- `verifier_mode`
- `allow_hacker`
- `escalate_after_failures`
- `generated_test_target_scale`

#### `post_verify_controller`

Position:

- after `verifier_phase`
- before `hacker_phase` or terminal accept

Responsibilities:

- accept
- send back to repair
- escalate to full heavy test generation
- optionally run hacker

Inputs:

- verifier decision
- verifier confidence
- verifier risk flags
- whether new trusted tests were created
- whether full test generation has already run
- remaining repair budget
- benchmark mode flag

Outputs:

- `accept`
- `repair`
- `escalate_testgen`
- `run_hacker`

### Controller Separation Rule

- verifier provides evidence
- controller spends budget

This separation is important. It prevents one node from both judging correctness and allocating expensive downstream work.

## Module 4: Verifier Phase

### Purpose

Provide independent acceptance control before success is finalized.

### Why It Matters

This is the highest-value addition for `pass@1`.

The current workflow can reach `success` too quickly after internal generated tests. The verifier exists to reduce false accepts and to detect when a lightweight path must escalate.

### Position

Always run after `codegen_phase` reports success on its current suite.

### First-Version Architecture

One LangGraph node backed by several internal Python analyzers.

The first version should not be split into many workflow nodes. The priority is correctness of decisions, not graph complexity.

### Checks Performed

#### 1. `trusted_suite_check`

Run only high-trust tests:

- public tests
- local exact certification cases
- trusted historical counterexamples
- trusted hacker-derived regressions

If any fail, decision is `repair`.

#### 2. `complexity_audit`

Check whether the candidate implementation is plausibly valid under problem constraints.

This includes:

- likely asymptotic mismatch
- obviously unsafe recursion depth
- suspicious dense memory sizing
- clearly invalid algorithm/data-structure scaling

If invalid with high confidence, decision is `repair`.

#### 3. `micro_oracle_check`

On problems with cheap exact checking, generate a few small random or structured instances and compare:

- candidate program
- trusted local oracle / brute force

If mismatch occurs, convert the discovered input into a new trusted test and return `repair`.

#### 4. `risk_pattern_audit`

Use failure-bank anti-pattern hits to trigger targeted checks for:

- cyclic semantics
- duplicate counting
- modulo edge cases
- overflow
- ordering assumptions
- off-by-one boundaries
- graph representation pitfalls

If evidence is incomplete but risk remains high, decision is `escalate_testgen`.

### Outputs

Write to `verification`:

- `decision`
- `confidence`
- `risk_flags`
- `new_tests`
- `feedback_summary`
- `trusted_failures`

### Verifier Decisions

- `accept`
  trusted checks passed and no strong unresolved risk signal remains
- `repair`
  high-confidence evidence of wrongness was found
- `escalate_testgen`
  candidate is not proven wrong, but current evidence quality is insufficient for acceptance

## Recommended State Additions

Add these fields to the LangGraph state schema:

### `solve_policy`

- `risk_score`
- `run_testgen_initially`
- `run_skill_plan`
- `initial_codegen_budget`
- `verifier_mode`
- `allow_hacker`
- `escalate_after_failures`
- `generated_test_target_scale`

### `verification`

- `decision`
- `confidence`
- `risk_flags`
- `new_tests`
- `feedback_summary`
- `trusted_failures`

### `failure_bank_context`

- `matched_patterns`
- `retrieved_counterexamples`
- `anti_patterns`
- `repair_summaries`
- `source_case_ids`

### `tests.trust_tiers`

Per-test or per-bucket trust metadata distinguishing:

- `trusted`
- `advisory`

## Workflow-Level Routing Changes

### Current Problem

Today, the transition from successful code generation to final acceptance or hacking is too direct.

### New Routing

Change:

`codegen_phase -> { to_hacker | end }`

To:

`codegen_phase -> verifier_phase -> post_verify_controller`

Then:

- `accept -> hacker_phase` if allowed
- `accept -> END` if hacker is skipped
- `repair -> codegen_phase`
- `escalate_testgen -> full_testgen_phase -> codegen_phase`

This makes success conditional on explicit acceptance, not merely local internal success.

## Implementation Order

### Phase A: Split Test Generation

Deliver:

- `bootstrap_tests_node`
- trusted/advisory test metadata
- minimal workflow support for skipping heavy test generation

Reason:

This is foundational. Without it, the controller and verifier cannot safely create a light path.

### Phase B: Add Verifier Phase

Deliver:

- `verifier_phase`
- routing from `codegen_phase` through verifier
- new `verification` state fields

Reason:

This yields the highest direct benchmark value by reducing false accepts.

### Phase C: Add Failure Bank

Deliver:

- bank schema
- lookup after abstract
- writes from verifier/hacker/benchmark

Reason:

This improves both prevention and repair quality with reusable evidence.

### Phase D: Add Solve Controller

Deliver:

- pre-solve decision node
- post-verify decision node
- `solve_policy` state

Reason:

Once trusted signals exist, routing them through a budget controller becomes valuable and stable.

### Phase E: Learned Risk Prior

Optional later stage:

- fit a lightweight learned model using benchmark/verifier/hacker logs
- replace or augment rule-based risk scoring

Reason:

Only useful after enough structured evidence exists.

## Evaluation Plan

Track the following metrics:

- `pass@1`
- false accept rate
- verifier-triggered repair rate
- verifier-triggered escalation-to-full-testgen rate
- average prompt tokens per problem
- average wall time per problem
- hacker incremental utility

Definitions:

- false accept rate:
  fraction of cases accepted by the internal workflow but still failing official benchmark tests
- hacker incremental utility:
  fraction of hacker runs that discover useful new trusted regressions

The design succeeds only if `pass@1` improves while cost growth remains moderate.

## Risks and Mitigations

### Risk: verifier becomes a second heavy solve phase

Mitigation:

- keep verifier mostly local/Python
- cap LLM verifier usage tightly
- prefer `escalate_testgen` over repeated verifier token burn

### Risk: failure bank becomes polluted

Mitigation:

- only promote high-confidence evidence
- require reproducibility and clear expected/actual mismatch
- keep a staging area for low-confidence findings

### Risk: controller overfits early heuristics

Mitigation:

- make first version rule-based and transparent
- log every routing reason
- evaluate controller decisions against benchmark outcomes before learning from them

### Risk: too many new states and routes make the graph harder to reason about

Mitigation:

- add only one new acceptance phase
- keep bootstrap tests small
- avoid turning verifier into a deep subgraph in version 1

## Non-Goals

This design intentionally does not include:

- a large multi-candidate solve ensemble as the primary path
- a new LLM super-controller
- a much more complex hacker generator family
- immediate replacement of the existing trainable memory subsystem

Those may be useful later, but they are not first-order drivers of `pass@1` under moderate cost growth.

## Final Recommendation

The most effective path is:

1. split heavy test generation into `bootstrap_tests` and `full_testgen`
2. add `verifier_phase` as an independent acceptance layer
3. add `failure_bank` for reusable high-confidence failures
4. add `solve_controller` to allocate heavy phases by risk

This keeps LangGraph as the controlling architecture while making the workflow:

- lighter on easy problems
- stricter before acceptance
- better at reusing past failures
- more selective about where it spends budget

That combination is the best fit for improving benchmark `pass@1` without uncontrolled cost growth.
