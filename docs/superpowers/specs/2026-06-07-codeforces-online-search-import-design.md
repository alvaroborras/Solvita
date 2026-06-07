# Codeforces Online Search Import Design

Date: 2026-06-07
Topic: Add Codeforces online search and import to the dashboard problem picker

## Goal

Extend the dashboard problem picker so users can search public Codeforces problems online, import one into the local problem library, and immediately solve it through the existing AlgoPilot run flow.

The feature should feel like an extension of the current local-library workflow, not a separate product.

## Product Outcome

After this change, a dashboard user should be able to:

1. open the existing `Start Solve` modal
2. switch to a `Codeforces` tab
3. search for a Codeforces problem by contest/id or keyword
4. choose a result and click `Import and Solve`
5. have the backend fetch the statement, normalize it into the existing local problem JSON shape, save it under `data/problem/`, and start a normal solve run

The imported problem should then behave like any other local problem in the system.

## Scope

### In Scope

- dashboard support for Codeforces search and import
- backend Codeforces search endpoint
- backend Codeforces import endpoint
- local metadata cache for Codeforces searchable problem summaries
- statement fetch and normalization into current local problem JSON schema
- imported problems written into `data/problem/`
- immediate reuse of existing `/api/runs` solve flow after import
- focused backend/frontend tests for the new flow

### Out of Scope

- support for non-Codeforces sources
- multi-source federation or ranking
- authenticated or private problem access
- editorial / solution import
- auto-sync background daemon
- bulk import
- direct “solve remote problem without saving locally”
- replacing the existing local problem library

## Current State

Today the dashboard problem picker is strictly local:

- backend `/api/problems` scans `data/problem/*.json`
- frontend `ProblemPanel` loads only that local list
- solving already works once a problem exists in local JSON form

This means the missing capability is not the solve path. The missing capability is a source-specific ingestion path that can produce valid local problem JSON on demand.

## Recommended Approach

Use a two-stage Codeforces integration:

1. **Search from a lightweight local cache of Codeforces metadata**
2. **Import by fetching and parsing the selected problem statement page**

This is the recommended approach because:

- it preserves the current local-library architecture
- it keeps search fast and cheap after the cache exists
- it avoids tying every keystroke in the UI to a live remote request
- it confines HTML parsing to import time rather than search time
- it makes the imported problem immediately compatible with the existing run stack

## Rejected Alternatives

### 1. Pure live remote search with no cache

Rejected because:

- search latency would be tied to remote availability
- repeated user typing would create unnecessary remote traffic
- it complicates debouncing and error handling for little product value

### 2. Direct remote solve without saving a local JSON file

Rejected because:

- it bypasses the architecture the dashboard already expects
- replay/history and later reuse become less consistent
- it creates a second problem representation path instead of reusing the existing one

### 3. Build a generic multi-platform provider system in version one

Rejected because:

- the user only asked for Codeforces now
- source abstraction can still exist internally without broadening the shipped scope
- the first implementation should prove the flow on one platform before generalizing

### 4. Search via HTML scraping only

Rejected because:

- title/id/rating/tag metadata is a better fit for structured indexing than full-page scraping
- scraping full problem pages just to populate a search list is unnecessary work

## Architecture

The architecture should preserve the current separation:

- **problem browsing/import** happens in dashboard backend + frontend
- **problem execution** continues through the existing run API

Add one new source-specific pipeline:

`Codeforces metadata cache -> dashboard search result -> statement fetch -> local JSON problem file -> existing solve flow`

### Core Modules

#### 1. `CodeforcesCatalog`

Responsibility:

- maintain a searchable local cache of Codeforces problem summaries

Inputs:

- remote Codeforces metadata response

Outputs:

- normalized searchable records containing only lightweight fields

Required fields per record:

- `contest_id`
- `index`
- `name`
- `rating`
- `tags`
- `url`
- `problem_id` for local/internal use

Non-goals:

- no statement text
- no sample parsing
- no solve-specific normalization

#### 2. `CodeforcesStatementFetcher`

Responsibility:

- fetch the selected Codeforces problem page
- extract statement text, examples, and limits

Inputs:

- `contest_id + index` or canonical Codeforces URL

Outputs:

- normalized import payload fields:
  - `description`
  - `time_limit`
  - `space_limit`
  - `public_tests`

This module is the only place that should know about Codeforces HTML structure.

#### 3. `CodeforcesImportService`

Responsibility:

- transform fetched Codeforces data into the project’s existing problem JSON schema
- persist the imported problem under `data/problem/`

Required JSON shape:

- `problem_id`
- `description`
- `public_tests`
- `constraints`
- `time_limit`
- `space_limit`
- `types`
- `_metadata`

Required metadata additions:

- `_metadata.source = "codeforces"`
- `_metadata.platform = "codeforces"`
- `_metadata.question_id = "codeforces_<contestId>_<index>"`
- `_metadata.name =` the exact parsed Codeforces title text
- `_metadata.cf_contest_id`
- `_metadata.cf_index`
- optional `_metadata.difficulty`

#### 4. Dashboard API Layer

Responsibility:

- expose search/import endpoints for the frontend
- keep local problem listing unchanged

## API Design

### `GET /api/sources/codeforces/search`

Purpose:

- return lightweight search results from the local Codeforces cache

Query params:

- `q` required search query
- `limit` optional max result count

Response shape:

```json
{
  "results": [
    {
      "contest_id": 1575,
      "index": "C",
      "name": "Cyclic Sum",
      "rating": 2100,
      "tags": ["math", "dp"],
      "url": "https://codeforces.com/contest/1575/problem/C"
    }
  ],
  "cache_status": "ready"
}
```

Behavior:

- if cache exists, search it immediately
- if cache is missing or stale, either refresh it on demand or return a clear recoverable status for the frontend

### `POST /api/sources/codeforces/import`

Purpose:

- fetch a single Codeforces problem and store it locally in project problem format

Accepted request body:

```json
{
  "contest_id": 1575,
  "index": "C"
}
```

or:

```json
{
  "url": "https://codeforces.com/contest/1575/problem/C"
}
```

Response shape:

```json
{
  "problem_id": "codeforces_1575_C",
  "filename": "codeforces_1575_C.json",
  "problem": { "...normalized local problem json..." }
}
```

Behavior:

- normalize into local schema
- write to `data/problem/`
- if the same imported problem already exists, either reuse it or overwrite predictably using stable identity rules

### Existing `/api/problems` and `/api/runs`

No contract changes required.

Imported Codeforces problems should appear through the existing `/api/problems` listing automatically after they are written locally.

## Cache Strategy

The Codeforces search path should not depend on live HTML fetches.

Use one cache file for searchable summaries, for example under a dashboard-owned data path such as:

- `dashboard/data/codeforces/cache.json`

Requirements:

- startup does not require the cache to already exist
- cache can be built lazily on the first search request
- cache format should be explicit and versioned enough to replace later
- stale or failed refresh must not break local problem browsing

First version cache management can stay simple:

- load if present
- refresh on explicit demand or first miss
- no scheduler required

## Problem Identity Rules

Imported Codeforces problems need stable local ids.

Recommended format:

- `codeforces_<contestId>_<index>`

Examples:

- `codeforces_1575_C`
- `codeforces_1873_A`

This identity should be used consistently across:

- filename
- `problem_id`
- `_metadata.question_id`

## Statement Normalization Rules

The imported `description` should remain plain text, matching the current project convention.

Normalization requirements:

- preserve the statement body
- preserve input/output sections
- preserve examples in readable text form
- extract example pairs into `public_tests`
- append or preserve time/memory limits in structured fields when available

Do not attempt first-version semantic rewriting.

The imported text should be faithful and minimal.

## Frontend Design

Add a new `Codeforces` tab to `ProblemPanel`.

### UI Flow

1. user opens `Start Solve`
2. user switches to `Codeforces`
3. user enters search text
4. frontend calls `GET /api/sources/codeforces/search`
5. user selects one result
6. user clicks `Import and Solve`
7. frontend calls `POST /api/sources/codeforces/import`
8. frontend immediately hands the returned local `problem` object into the existing `onSubmit(...)`

### UI Scope

Version one UI only needs:

- search input
- results list
- loading state
- error state
- import/solve action

No advanced table/grid behavior is required.

## Error Handling

The system must clearly separate these failure classes:

- cache unavailable / cache refresh failed
- search query returned no results
- remote statement fetch failed
- statement parse failed
- local write failed
- solve launch failed after a successful import

The user should always know whether the failure happened during:

- search
- import
- solve

## Testing Strategy

### Backend

Add tests for:

- Codeforces cache record normalization
- search endpoint behavior with populated cache
- import endpoint behavior from a mocked problem page
- example extraction into `public_tests`
- stable `problem_id` / filename generation
- imported problem appears in normal `/api/problems` listing

### Frontend

Add tests for:

- `Codeforces` tab rendering
- search request + result rendering
- import request + handoff into existing solve submit path
- error messaging when search/import fails

## Risks

### 1. HTML parser fragility

Codeforces statement HTML can change.

Mitigation:

- isolate parsing logic into one backend module
- keep parser focused on stable structural selectors
- test using stored representative HTML fixtures

### 2. Search cache freshness

A stale cache may hide very recent problems.

Mitigation:

- expose clear cache status
- allow explicit refresh
- prefer predictable behavior over pretending results are live when they are not

### 3. Imported statement quality

Some imported pages may contain formatting quirks that do not map cleanly to plain text.

Mitigation:

- prioritize readable plain text over perfect formatting fidelity
- keep first version narrow and test with representative examples

## Delivery Recommendation

Build in this order:

1. `CodeforcesStatementFetcher`
2. `CodeforcesImportService`
3. `POST /api/sources/codeforces/import`
4. `CodeforcesCatalog` cache
5. `GET /api/sources/codeforces/search`
6. `ProblemPanel` Codeforces tab

This order gives a working import path first, then layers search on top.

## Final Design Summary

The dashboard should remain local-library-centric.

Codeforces integration should work by:

- searching a local cache of Codeforces problem metadata
- importing one selected problem into the existing local JSON schema
- immediately reusing the current solve flow

This gives users access to a public problem source without creating a second execution architecture.
