# API contract

Base address: `http://127.0.0.1:8000`. Run `cu-runner serve` from the repository root. All examples use synthetic data. The machine-readable contract is `openapi.json` in this directory, also served by the application.

## Authentication and boundaries

Caller endpoints require `Authorization: Bearer RUNNER_TOKEN`; operator endpoints require the distinct `OPERATOR_TOKEN`. These symbolic names refer to generated values in the ignored `.env`, not literal accepted credentials. Use a local secret-aware HTTP client; do not paste actual tokens into documentation or commit them.

Live operator mutations and screenshots additionally require `X-Control-Token` from the current claim and its `revision`. Revisions are not secrets; claim tokens are. The server applies constant-time token comparison, same-origin checks, a 64 KiB request-body limit, trusted localhost hosts, no permissive CORS, and 300 caller / 360 operator requests per minute. Poll at approximately 0.4 seconds or slower and respect `Retry-After`. Role limits are process-wide local limits, not per-user quotas.

Responses are `Cache-Control: no-store`. Health, the console shell/assets, and OpenAPI metadata are public locally; no member result is public. Rate limits or authentication failures do not create a browser. Invalid payload errors report a code and count rather than reflecting sensitive input.

## Caller endpoints

### GET /api/capabilities

Returns a `capabilities` list containing ID, typed inputs, typed outputs, and checkpoint. The currently supported profile is `read_savings_balance`. Its `member_id` is a five-digit string; `balance` is a finite two-decimal string; `currency` is `USD`.

### POST /api/capabilities

Import the complete serialized capability body. HTTP 201 returns `{"id":"read_savings_balance.v1"}`. Content must match the trusted profile, targets, risk model, contracts, and error handlers. Arbitrary selectors, weakened policy, or mutation of an existing revision are rejected. Identical re-imports are safe.

### GET /api/capabilities/{artifact_id}

Return a complete artifact. Unknown ID: HTTP 404. Invalid ID/contract: HTTP 422. IDs have the form `read_savings_balance.v1`.

### GET /api/schema

Return the JSON Schema for the complete capability contract.

### POST /api/discoveries

```json
{
  "goal": "Find the member using member_id and read their current savings balance and currency",
  "inputs": {"member_id": "10001"},
  "target": "sandbox://legacy"
}
```

The goal is required (6-1,200 characters), and `inputs` must exactly match the reviewed contract. `target` is optional and defaults to the configured bundled application. The server launches a model-led browser task and responds HTTP 202 with a generated `run_id` and `status: accepted`. Model/target/runtime failure is a structured asynchronous run result, not a fake successful artifact.

### POST /api/replays

```json
{
  "capability": "read_savings_balance.v1",
  "inputs": {"member_id": "10002"},
  "target": "sandbox://legacy"
}
```

HTTP 202 returns a new `run_id`. No planner is constructed and no model key is required. Unknown capability: HTTP 404. Unsupported target/action: HTTP 403. Invalid input or artifact: HTTP 422. Active-run limit reached: HTTP 429 `CAPACITY_EXCEEDED`.

### GET /api/runs/{run_id}

Returns `run_id`, `mode`, `capability`, original `session_id`, current step, safe observation, control state, and `result` (null while running). The caller can receive output values when the run succeeds. Operators cannot retrieve those values through their status endpoint.

Illustrative terminal success fields, with synthetic values and the generated ID omitted:

```json
{
  "status": "success",
  "code": "OK",
  "outputs": {"balance": "807.20", "currency": "USD"},
  "step": 7,
  "expected": "savings",
  "observed": ["screen:savings"],
  "llm_calls": 0,
  "interventions": 0,
  "artifact": "read_savings_balance.v1"
}
```

Actual results also contain `run_id`. Step is zero-based for replay. A discovery finish decision can have a different step count because it is not a browser action. A known missing member returns `business_outcome`, code `NOT_FOUND`, empty outputs, expected/observed context, and zero model calls on replay. A cancellation/timeout is a `failure`, never a business outcome or success.

Completed results are in-memory only and expire after roughly 15 minutes plus cleanup scheduling, or sooner at the retention cap. Persisted `result.json` replaces all output values with `[REDACTED]`; it is not a durable API-result cache. Process restart loses live/in-memory run records but preserves safe evidence and artifacts.

### POST /api/runs/{run_id}/cancel

Cancel the task, revoke control, close the browser, and clear input state. Returns `{"status":"cancelled"}`. Unknown run: HTTP 404. Cancellation of an already terminal run does not restart it.

## Operator endpoints

### GET /api/operator/interventions

Return an `interventions` list for PAUSED or HUMAN runs. Each item includes capability, step, same-session ID, control revision, deadline context, and intervention cause/observation/snapshot. There is no external paging integration.

### GET /api/operator/runs/{run_id}

Return the safe run view, redacting output values. The current control revision is needed when claiming.

### POST /api/operator/runs/{run_id}/claim

Body: `{"revision":1}` using the **actual current revision**, not a hardcoded assumption. Returns `revision`, a secret `control_token`, and `lease_seconds`. Ownership must be PAUSED and the revision must match. A competing claimant is rejected with HTTP 409.

### GET /api/operator/runs/{run_id}/screenshot?revision=2

Requires operator bearer and current `X-Control-Token`. Returns the actual current browser PNG in memory with `no-store`. The application does not save it. Substitute the actual revision; numbers shown are illustrative.

### GET /api/operator/runs/{run_id}/controls?revision=2

Requires the same lease. Returns visible reviewed controls, their logical keys, labels, action kinds, risk, and enabled/unique status. It does not expose raw DOM, input values, or arbitrary selector execution.

### POST /api/operator/runs/{run_id}/actions

Headers: operator bearer, current claim token, JSON content type. Body:

```json
{
  "revision": 2,
  "request_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "action": {"kind": "click", "target": "restore_session"}
}
```

Generate a fresh 32-character hexadecimal request ID for each intended action; reuse it only to retry that same action under the same lease. The example repeated-letter identifier is documentation, not a production idempotency strategy. Duplicate same-action requests return the prior acknowledgement without applying again. Reusing an ID for a different action is an `IDEMPOTENCY_CONFLICT`.

Fill actions reference the invocation's `member_id` parameter rather than sending a new arbitrary value. Human-only session restoration is allowed; irreversible closure is forbidden for all actors. The endpoint cannot run JavaScript, inject selectors, upload files, or bypass permissions. It operates on the original surface under a lock.

### POST /api/operator/runs/{run_id}/renew

Body contains current `revision`; current claim token required. Extend the ownership lease, but not the enclosing intervention/run deadline.

### POST /api/operator/runs/{run_id}/resume

Same authorization and revision body. Return ownership to AUTOMATION, revoke the claim token, increment revision, and wake the waiting engine. The engine observes again before acting. A stale or expired lease cannot resume a run.

### POST /api/operator/runs/{run_id}/cancel

Requires operator bearer, not a claim. Safely terminate an unrecoverable or unwanted run and close its browser.

### GET /api/operator/runs/{run_id}/evidence/{name}

Requires operator bearer. `name` must exactly match `snapshot-NNN.dom.json`. Return a value-redacted structural snapshot from that run; path traversal/symlinks and unrelated files are rejected. For final historical review after in-memory eviction, inspect the local safe evidence directory, not the live API.

## Common HTTP errors

| HTTP | Meaning |
|---|---|
| 401 | Missing/wrong token, wrong caller/operator role. |
| 403 | Cross-origin request or policy denial. |
| 404 | Missing run, artifact, or allowed evidence file. |
| 409 | Stale/competing control, surface conflict, unresolved run operation. |
| 411 | Missing/invalid Content-Length on a write request. |
| 413 | Write request exceeds 64 KiB. |
| 422 | Invalid typed body, input, or immutable/unauthorized artifact contract. |
| 429 | Rate limit or concurrent-run capacity exceeded. |

Authentication/not-found HTTP exceptions use FastAPI's `detail.code` envelope; custom boundary/validation/control handlers use a top-level `code`. Run outcomes use the separate `result` contract. The console handles both HTTP error envelopes. Internal errors do not echo raw request bodies or provider responses.
