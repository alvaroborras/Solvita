# Full Pipeline Showcase Problem Design

Date: 2026-06-07
Topic: Add one naturally-triggered showcase problem that walks the main AlgoPilot solve pipeline

## Goal

Add a single problem file under `data/problem/` that is suitable for demonstrating the **main solve pipeline** end to end under default runtime behavior.

The desired demonstration outcome is:

1. the problem is loaded through the normal entrypoint
2. the workflow naturally visits the major mainline modules
3. no solver-network or trainable-memory features need to be enabled
4. no special “force this stage” config is required
5. final AC is not required

The emphasis is proving that the implemented modules are real and reachable, not proving maximum solve strength.

## Success Criteria

The design is successful when the new problem can, under ordinary execution, reach these stages at least once:

- `failure_bank_lookup`
- `bootstrap_tests`
- `generate_tests`
- `generate_code`
- `compile_code`
- `run_tests`
- `verifier_phase`
- `hacker_phase`

Acceptance does **not** require:

- `status == "success"`
- benchmark integration
- dashboard-specific packaging
- solver-network activation
- trainable-memory activation

## Scope

### In Scope

- one new problem JSON file in `data/problem/`
- wording and constraints chosen to naturally trigger the mainline pipeline
- validation by running the normal workflow and checking reached stages

### Out of Scope

- changes to `src/graph/workflow.py`
- changes to routing thresholds or solve-policy logic
- enabling `solver_network`
- enabling `trainable_memory`
- benchmark manifests or training scripts
- dashboard-only demo assets

## Current Constraints

The pipeline does not naturally visit every stage for every problem.

Current behavior that matters:

1. `bootstrap_tests` always runs, but `generate_tests` is gated by risk score.
2. `hacker_phase` is also risk-gated and will be skipped for low-risk problems.
3. simple showcase problems already in `data/problem/showcase_*.json` are intentionally easy and usually do not exercise the whole chain.
4. if a problem is too hard, the workflow can get stuck in repeated repair before it ever reaches verifier or hacker.

So the target problem must sit in a narrow band:

- risky enough to trigger the later stages
- still small enough that the agent can often produce at least one executable candidate that reaches verifier and hacker

## Recommended Approach

Use a **small-constraint variant** of the existing cyclic segment-counting problem family already represented in the repository.

This means the new problem should preserve the semantic shape of `codecontests_1575_C__Cyclic_Sum.json`, while shrinking the constraints so the showcase focuses on pipeline reachability rather than full-scale optimization.

This is the recommended approach because it aligns with logic that already exists in the codebase:

- `bootstrap_tests` has dedicated local certified cases for this family
- `generate_tests` contains specialized prompt guidance for this family
- `pre_solve_controller` treats this family as high-risk when the tags land on the expected cyclic DP/math pattern

The repository already contains the problem-specific scaffolding. The design should reuse that fact instead of inventing a synthetic trigger.

## Rejected Alternatives

### 1. Reuse an existing easy showcase problem

Rejected because:

- easy showcase files are designed to be straightforward
- they are less likely to trigger `generate_tests` and `hacker_phase`
- they do not demonstrate the richer pipeline behavior we want to prove

### 2. Use the original full-scale `Cyclic Sum` problem unchanged

Rejected because:

- it is likely too difficult for stable verifier/hacker reachability
- the workflow may spend most of its budget in repair loops
- the demo would become fragile and hard to reproduce

### 3. Add a special config or code path that forces stage traversal

Rejected because:

- the user explicitly wants natural triggering from the problem itself
- a forced path weakens the claim that the modules are truly implemented
- it would test orchestration overrides, not normal behavior

### 4. Invent a multi-tag synthetic puzzle unrelated to existing special cases

Rejected because:

- trigger behavior would depend too much on tag classification luck
- the problem would look engineered for the demo rather than naturally supported
- it would ignore family-specific scaffolding already present in the repository

## Problem Design

### File Location

Add:

- `data/problem/showcase_full_pipeline_cyclic_sum.json`

This keeps the asset easy to discover while clearly separating it from benchmark inputs and the simpler algorithm-family showcases.

### Problem Semantics

Keep the same core semantics as the cyclic-sum family:

- a cyclic sequence
- `m` concatenated copies of an array
- segment identity defined by the resulting set of indices on the cycle
- count segments whose sum is divisible by `k`

The problem text must explicitly preserve the phrases that current heuristics already recognize, including:

- `cyclic sequence`
- `concatenating m copies`
- `same set of indices`
- `sum of elements in the segment is divisible by k`

These phrases are not cosmetic. They are part of how current bootstrap/testgen helpers identify the family.

### Constraint Strategy

Use explicit showcase constraints:

- `1 <= n, m <= 20`
- `0 <= a_i <= 20`
- `1 <= k <= 23`, where `k = 1` or `k` is prime

These values are intentionally small enough that brute-force or explicit enumeration remains plausible, while the cyclic identity rule still makes the problem semantically tricky.

The design requirement is:

- brute-force or explicit enumeration is plausible
- the agent is more likely to reach a runnable candidate
- the problem still looks nontrivial and semantically tricky

### Public Tests Policy

Set `public_tests` to an empty array.

Rationale:

1. the risk controller adds risk when public tests are absent
2. the cyclic bootstrap helper can still create trusted tests from the description
3. the problem statement can still include sample input/output in prose for human readability

This is intentional. The showcase is trying to demonstrate stage traversal, not sample-driven easy mode.

### Metadata

Include lightweight descriptive metadata with this minimum shape:

```json
"_metadata": {
  "source": "pipeline-showcase",
  "name": "Full Pipeline Showcase: Cyclic Sum",
  "showcase": true,
  "question_id": "showcase_full_pipeline_cyclic_sum"
}
```

This metadata is descriptive only and must not be required by the main solve logic.

## Why This Should Trigger The Desired Pipeline

### `failure_bank_lookup`

This node is part of the default top-level flow and will always be visited unless the workflow is changed. No extra work is needed beyond using the normal entrypoint.

### `bootstrap_tests`

This node is also unconditional in the main flow.

More importantly, the cyclic-sum description is expected to trigger the existing local certified test builder, so bootstrap should generate trusted tests even with no `public_tests`.

### `generate_tests`

The problem is designed to be high-risk enough that `pre_solve_controller` should select `run_testgen_initially = True`.

The main contributors are:

- likely lower abstraction confidence for the cyclic semantics
- high-risk level-1 tags such as `dp` and `math`
- a high-risk level-2 tag such as `cyclic_convolution`
- no `public_tests`

### `generate_code`, `compile_code`, `run_tests`

These are part of the ordinary codegen loop once the workflow advances past test generation.

The reduced constraints are specifically chosen so the model is more likely to produce an executable reference-style solution instead of failing exclusively in repair loops.

### `verifier_phase`

Verifier only becomes reachable if codegen produces a successful test pass on the currently trusted suite.

The reduced problem size is what makes verifier reachability plausible without any orchestration changes.

### `hacker_phase`

`post_verify_controller` only routes to hacker when the solve policy allows it.

The problem is intentionally designed to remain risky enough that `allow_hacker` should stay true under default logic, even though the reduced constraints make verifier reachability easier.

## Implementation Boundaries

Implementation should stay minimal:

1. add the new problem file
2. run the workflow against it
3. tune only the problem text and constraints if stage traversal misses the target

Implementation should not:

1. change workflow routing
2. change risk thresholds
3. add one-off stage forcing
4. modify existing benchmark problems

## Validation Plan

Validation happens in two layers.

### 1. Static validation

Before runtime testing, confirm that:

- the problem text still matches the cyclic-family detector phrases
- `public_tests` is empty
- the JSON shape matches normal loader expectations

### 2. Runtime validation

Run the normal workflow through the standard entrypoint and inspect the resulting events/logs for stage reachability.

The validation question is:

“Did the workflow naturally enter each target stage at least once?”

This should be checked against emitted events or logs, not by guessing from final status.

### Pass Condition

The problem is accepted when one ordinary run reaches:

- `failure_bank_lookup`
- `bootstrap_tests`
- `generate_tests`
- `generate_code`
- `compile_code`
- `run_tests`
- `verifier_phase`
- `hacker_phase`

### Adjustment Rule

If the first candidate problem does not reach the required stages, implementation may only adjust:

- constraint magnitudes
- wording clarity
- sample wording inside the description

The workflow itself must remain unchanged.

## Risks

### 1. Abstract tagging may drift

If the model fails to classify the problem into the intended cyclic high-risk family, `generate_tests` or `hacker_phase` may not trigger.

Mitigation:

- keep the wording close to the established cyclic-sum phrasing already used in the repo

### 2. Problem may still be too hard

Even at smaller constraints, the agent might fail to produce a verifier-reaching candidate.

Mitigation:

- reduce constraints further before changing anything else

### 3. Problem may become too easy

If constraints are reduced too far or wording becomes too explicit, the risk controller may stop treating it as a rich pipeline candidate.

Mitigation:

- preserve the semantically tricky cyclic identity rules
- keep `public_tests` empty
- keep the description aligned with the existing family-specific helpers

## Final Design Summary

Add one new problem file that reuses the repository’s existing cyclic-segment-counting semantics but scales the constraints down for stable pipeline traversal.

The file should be designed so that:

- it naturally triggers bootstrap and full test generation
- it remains risky enough to reach hacker
- it is still small enough that verifier becomes reachable in ordinary runs

The implementation should solve this entirely at the **problem-definition layer**, not by changing the workflow.
