# User-Supplied Problem Forced TestGen/Hack Design

Date: 2026-06-08
Topic: Force stronger safety policy for user-supplied problems

## Goal

When the user provides a problem manually rather than selecting a built-in repository problem, the system should apply a stricter solve policy:

- always run full test generation
- enable the hacker phase by default
- but still respect an explicit `workflow.hacker_enabled: false` configuration

This is a safety and robustness change, not a UI feature.

## User Intent

The user wants manually supplied problems to receive stronger verification by default, because:

- repository-curated problems already have known structure and supporting artifacts
- user-supplied problems are less trusted
- the system should compensate by generating more tests and running adversarial checks

The user explicitly chose this policy boundary:

1. user-supplied problems must **always** force full test generation
2. user-supplied problems should also enable hacker by default
3. if the runtime config explicitly says `workflow.hacker_enabled: false`, that explicit disable still wins

## Scope

### In Scope

- identify user-supplied problems through a stable metadata marker
- mark all relevant user-input entry points consistently
- force `run_testgen_initially = true` in the pre-solve controller for those problems
- force `allow_hacker = true` for those problems unless the workflow config explicitly disables hacker
- add tests for the entry-point markers and controller behavior

### Out of Scope

- changing repository-built problem metadata
- changing benchmark dataset behavior
- changing built-in showcase problem behavior
- changing the risk-score formula for normal problems
- changing dashboard or CLI UX beyond what is needed to attach the metadata marker

## Core Design

### 1. Represent “user supplied” explicitly

The system should not infer this policy only from file paths.

Instead, all relevant entry points should attach:

```json
"_metadata": {
  "user_supplied": true
}
```

This turns the decision into an explicit contract instead of an implicit guess.

That matters because user-provided problems can enter through multiple routes:

- direct text input
- custom dashboard authoring
- CLI path mode with arbitrary external JSON
- CLI paste mode

Using a stable metadata flag means the downstream controller logic stays simple and centralized.

### 2. Centralize policy override in `pre_solve_controller_node`

The forcing logic belongs in the pre-solve controller, not in each entry point.

Reason:

- the controller already owns `run_testgen_initially`
- the controller already owns `allow_hacker`
- the controller is the single point where solve-policy decisions are assembled

So the entry points only mark problems, and the controller applies the policy.

## Entry-Point Rules

### `main.py --problem-description`

Problems built from raw text are always user-supplied.

`build_problem_from_description()` should include:

```python
"_metadata": {
    "user_supplied": True,
    "source": "cli_description",
}
```

### CLI paste mode

The temporary JSON generated for pasted problems is always user-supplied.

The generated payload should include:

```python
"_metadata": {
    "user_supplied": True,
    "source": "cli_paste",
}
```

### CLI path mode / direct file mode

If the user launches a problem from an arbitrary external JSON file that is not one of the repository-managed problems under `data/problem/`, it should be treated as user-supplied.

That means the CLI should attach:

```python
"_metadata": {
    "user_supplied": True,
    "source": "cli_path",
}
```

for non-library files only.

Repository-managed problems selected from the built-in library should remain unmarked.

### Dashboard custom problems

Dashboard custom problems already carry custom metadata.

They should additionally include:

```python
"_metadata": {
    "custom": True,
    "user_supplied": True,
    "source": "custom",
}
```

### Repository-built problems

Problems already stored in the repository’s curated `data/problem/` set should not gain `user_supplied: true`.

That includes:

- built-in sample problems
- showcase problems
- benchmark/problem-corpus files already managed by the repository

## Solve-Policy Override Rules

The controller should apply the following logic when:

```python
raw_problem.get("_metadata", {}).get("user_supplied") is True
```

### Rule A: full test generation is mandatory

For user-supplied problems:

```python
run_testgen_initially = True
```

This is unconditional.

It overrides the normal risk-based choice.

### Rule B: hacker is enabled by default

For user-supplied problems:

```python
allow_hacker = True
```

but only if the workflow is not explicitly disabled.

### Rule C: explicit hacker disable still wins

If config contains:

```python
workflow.hacker_enabled = False
```

then:

```python
allow_hacker = False
```

even for user-supplied problems.

This preserves the user’s chosen precedence rule:

- strong default for user-supplied problems
- explicit config override still respected

## Configuration Precedence

The final precedence model should be:

1. explicit `workflow.hacker_enabled: false` disables hacker
2. otherwise, `user_supplied: true` forces hacker on
3. otherwise, normal risk-driven hacker policy applies

For full test generation:

1. `user_supplied: true` forces `run_testgen_initially = true`
2. otherwise, normal risk-driven testgen policy applies

There is no “explicit disable full testgen” override in this design.

That is intentional: the user explicitly asked for user-supplied problems to always force full test generation.

## Implementation Shape

The change should be split into two parts:

### Part 1: entry-point marking

Touch only the places that construct or adapt problem payloads:

- `main.py`
- CLI input-path/paste adapters
- dashboard custom-problem persistence path

### Part 2: policy enforcement

Touch only the controller logic:

- `src/nodes/solve_controller.py`

Avoid spreading user-supplied policy checks across unrelated workflow nodes.

## Testing Strategy

### Entry-point tests

Add focused tests proving that:

1. `--problem-description` problems are marked `user_supplied: true`
2. CLI paste-generated problems are marked `user_supplied: true`
3. CLI external path problems are marked `user_supplied: true`
4. repository-managed picker/library problems are not marked
5. dashboard custom problems are marked `user_supplied: true`

### Controller policy tests

Add tests proving that:

1. `user_supplied: true` forces `run_testgen_initially == True`
2. `user_supplied: true` forces `allow_hacker == True` when hacker is not explicitly disabled
3. `user_supplied: true` plus `workflow.hacker_enabled == False` yields `allow_hacker == False`
4. non-user-supplied problems still use the normal risk-based policy path

### Regression tests

Keep one regression proving that ordinary built-in problems are not accidentally forced into the stronger policy.

## Risks

### Risk: path-based detection is inconsistent

Mitigation:

Use explicit metadata rather than only checking the path at controller time.

### Risk: repository-managed but user-owned files are misclassified

Mitigation:

Only library-selected problems should bypass marking.
Arbitrary user-provided file paths should be explicitly marked before solve launch.

### Risk: benchmark and curated runs get unexpectedly slower

Mitigation:

Do not mark repository-curated and benchmark-provided problems as user-supplied.

### Risk: policy logic becomes duplicated

Mitigation:

Keep all forcing logic centralized in `pre_solve_controller_node`.

## Success Criteria

This feature is complete when:

1. every user-input problem entry path produces `user_supplied: true`
2. the pre-solve controller always forces full test generation for such problems
3. the pre-solve controller enables hacker by default for such problems
4. explicit `workflow.hacker_enabled: false` still disables hacker
5. built-in repository problems keep their existing behavior
6. tests cover both metadata marking and controller policy forcing
