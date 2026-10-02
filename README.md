# Capability Runner

**Ahmed Nawaz Shaik - Computer-Use Automation System**

A small, complete vertical slice: a model discovers a multi-screen task in a real browser, the successful run becomes a typed capability, and subsequent calls replay it without a model. When execution cannot safely proceed, an operator claims and controls the **same live browser session** before returning it to automation.

The supported task is **look up a synthetic member, open their accounts, select savings, and return the current balance and currency**. The target deliberately uses an iframe, nested tables, an unlabelled form field, and no test IDs. There is no business-data API for the agent to call.

## Verification status

The repository includes an actual successful **ChatGPT-driven discovery through an external decision bridge**, its eight observation/decision exchanges, the resulting artifact, and real-browser replay/error/handoff evidence. The bridge never chooses an action itself. See [evidence/PROVENANCE.md](evidence/PROVENANCE.md).

**Provider-backed proof:** on 2 October 2026, the OpenAI-compatible adapter completed a live `gpt-4o-mini` discovery in eight model decisions and saved `read_savings_balance.v2`. A replay with a different synthetic member then completed with `llm_calls: 0`. Redacted, hash-linked records are in `evidence/provider-discovery/` and `evidence/provider-replay/`; the original bridge evidence remains separately labelled.

The verification environment also blocks browser URL navigation by managed policy. That policy was not changed. The browser tests use the bundled application as an in-memory interactive document (`sandbox://legacy`). Actual localhost API requests were verified; ordinary HTTP browser navigation remains an environment-specific unverified path. [docs/VERIFICATION.md](docs/VERIFICATION.md) gives exact results, scope, and limitations.

## Quick start: no model key required

Run commands from the repository root. Python 3.13 is the verified runtime; the package declares Python 3.11-3.13 support. A Chromium installation is required.

```bash
python -m venv .venv
```
Create an isolated environment.

```bash
source .venv/bin/activate
```
Activate it on Linux/macOS. On Windows PowerShell use `.venv\Scripts\Activate.ps1` instead.

```bash
python -m pip install -e '.[test]'
```
Install the application and pinned direct testing dependencies. `requirements.txt` and `requirements-dev.txt` are equivalent dependency lists.

```bash
python -m playwright install chromium
```
Install the browser matching Playwright. On Linux machines missing browser libraries, use `python -m playwright install --with-deps chromium` with the appropriate administrator permission. Alternatively, set `CHROMIUM_EXECUTABLE` to an already installed Chromium executable.

```bash
python scripts/init_env.py
```
Create an ignored, permission-restricted `.env` with two independent random API tokens. Existing configuration is not overwritten. A system Chromium is detected when available.

```bash
python scripts/demo.py
```
Start the real local services, import the genuine discovered capability, replay it in Chromium with a different synthetic member, validate its checkpoint and typed outputs, assert zero model calls, and stop both services. Keep ports **8000** and **8765** free. This is deterministic replay, **not an offline imitation of discovery**.

Successful synthetic output includes `status: success`, `code: OK`, `balance: "807.20"`, `currency: "USD"`, and `llm_calls: 0`. Returned output values are visible to the authenticated caller but are redacted in persisted run results.

## Architecture

```text
Caller / AI agent
    -> authenticated FastAPI catalog and run API
        -> RunManager: bounded lifecycle, checkpoints, error taxonomy
            -> Discovery: Planner port -> typed model decision
            -> Replay: saved Capability -> ordered, checked actions [no Planner]
            -> ControlGate: automation / paused / leased human / finished
            -> Surface port -> Playwright browser and legacy iframe
        -> immutable JSON capability catalog + redacted, hash-linked evidence

Operator console -> separate operator authentication + per-claim lease
                 -> reviewed controls on that same live Surface
```

`schema.py` is the reusable contract. `profile.py` is the reviewed vendor binding, not a recorded transcript or a hardcoded discovery sequence. The model chooses among visible, permitted candidates on each observation. It can choose extraction order, escalate, or finish only when the engine verifies the declared checkpoint. The browser adapter knows how to locate and operate controls; the orchestration engine does not contain Playwright selectors.

There is one process and one independent browser/context per active run. Four active runs are allowed by default, including paused ones. Excess work is rejected with HTTP 429 rather than silently queued. Do not run multiple Uvicorn workers: live control ownership is intentionally in-process.

## Technology stack and selection

| Component | Choice | Reason |
|---|---|---|
| Application | Python, FastAPI, Pydantic, AsyncIO | Explicit contracts, input validation, and asynchronous browser/control operations. |
| Computer use | Playwright + Chromium | Real UI interaction, iframe support, visibility/uniqueness checks, controlled network boundaries, and live browser ownership. |
| Discovery | OpenAI-compatible structured-output adapter; explicit external-LLM bridge | Typed model decisions and a narrow planner interface without an unnecessary orchestration framework. |
| Operator UI | HTML, CSS, vanilla JavaScript | A real minimal console without a separate frontend build or deployment pipeline. |
| Testing | Pytest, pytest-asyncio, HTTPX, real Playwright browser tests | Unit, contract, API, browser, failure-path, and control-transfer coverage. |
| Persistence | Versioned JSON files + JSONL audit records | The artifact is the central durable object. PostgreSQL, Redis, queues, and migrations would be unnecessary infrastructure for this single-process slice. |
| Quality | Packaged Python wheel, pinned direct dependencies, GitHub Actions workflow | Reproducible development and CI without cloud credentials. |

No Docker configuration is included because the verified local workflow is sufficient for this single-process implementation. Kubernetes, Terraform, cloud deployment, LangGraph, RAG, and vector databases would add infrastructure without strengthening the core execution model.

## Repository layout

```text
README.md                   Setup, exact demo commands, decisions, limitations
REPORT.md                   The seven requested design sections
REQUIREMENTS.md              Every requirement mapped to implementation and proof
config/policy.json           Explicit target/route/action allowlist
src/capability_runner/
  schema.py                 Typed capability, locators, parameters, outputs, results
  profile.py                Reviewed vendor controls and runtime-state rules
  engine.py                 Discovery, replay, bounded execution, error recovery
  surface.py                Surface port and real Playwright implementation
  planner.py                Hosted-provider and external decision transports
  control.py                Same-session handoff, claims, leases, idempotency
  policy.py                 Target and action authorization
  storage.py                Atomic immutable artifacts; redacted audit chains
  api.py                    Caller/operator APIs and security boundaries
  sandbox.py                HTML delivery of the same synthetic interactive UI
  cli.py                    Service, discovery, replay, import/export commands
  static/                   Operator console and synthetic banking application
scripts/                    Environment initialization, demo, evidence validation
tests/                      Contract, policy, browser, API, planner, handoff tests
docs/                       API reference, schemas, bridge guide, verification
evidence/                   Actual discovery, replay, exceptional-state evidence
.github/workflows/          CI configuration
```

## Configuration

Copying `.env.example` manually is supported, but use `scripts/init_env.py` to generate tokens. Never commit `.env` or paste real financial data into a command line.

| Variable | Default / purpose |
|---|---|
| `RUNNER_TOKEN` | Required independent random caller secret, minimum 32 characters. |
| `OPERATOR_TOKEN` | Required different operator secret, minimum 32 characters. |
| `RUNNER_HOST`, `RUNNER_PORT` | `127.0.0.1`, `8000`; localhost only by default. |
| `SANDBOX_HOST`, `SANDBOX_PORT` | `127.0.0.1`, `8765`. |
| `DEFAULT_TARGET` | `sandbox://legacy`, the bundled, network-free interactive UI. |
| `TARGET_ORIGIN` | `http://127.0.0.1:8765`; must match the explicit policy. |
| `POLICY_FILE` | `config/policy.json`. Change trusted bindings and tests deliberately, not through a model prompt. |
| `DATA_DIR` | `.runtime`; immutable capabilities and redacted run evidence. |
| `CHROMIUM_EXECUTABLE` | Blank uses Playwright's browser; otherwise an installed Chromium path. |
| `HEADLESS` | `true`; the operator uses the live screenshot/control console. |
| `ACTION_TIMEOUT_MS` | `3000`; locator/load boundary before intervention. |
| `RUN_TIMEOUT_SECONDS` | `180`; total execution budget, including handoff. |
| `INTERVENTION_TIMEOUT_SECONDS` | `90`; maximum paused interval; renewal does not extend this overall budget. |
| `HUMAN_LEASE_SECONDS` | `60`; exclusive operator claim, renewable while the run is still within budget. |
| `MAX_STEPS`, `MAX_ACTIVE_RUNS` | `24`, `4`. |
| `MODEL_PROVIDER` | `openai` for unattended API access, or explicitly `bridge`. |
| `MODEL_BASE_URL` | `https://api.openai.com/v1`; TLS required except a loopback local provider. |
| `MODEL_NAME` | `gpt-4o-mini`; select a model supporting the configured strict JSON response format. |
| `MODEL_API_KEY` | Required for non-local provider discovery, never for replay. |
| `MODEL_TIMEOUT_SECONDS` | `45` per decision; increase for an interactive bridge. |
| `BRIDGE_DIR` | `.bridge`; ignored, local external-model mailbox. |

Settings are validated on startup. Configuration is loaded from `.env` without overwriting environment variables. The policy additionally permits only the documented `scenario` query values; it is not a broad domain-only allowlist.

### Persistence and database setup

There is **no database to initialize, migrate, or seed**. The three synthetic records are defined in the sandbox JavaScript. The catalog creates its directory automatically and writes new revisions atomically. Re-importing the same revision/content is idempotent; changing an existing revision is rejected. The schema rejects unsupported versions. Schema evolution would require an explicit migration/review tool, not silent JSON coercion.

Live browsers, input values, control leases, and returned outputs are not durable job state. Inputs are cleared when a run ends. Completed outputs are retained in process memory for at most approximately 15 minutes plus the cleanup interval, or less when the retention cap is exceeded; they are redacted on disk. Restarting the process ends live sessions and loses in-memory results. The artifact and safe audit files survive.

## Run the services manually

In one terminal:

```bash
cu-runner serve
```
Start the API and operator console. Leave this process running for the commands below.

For an HTTP-delivered target, in another terminal:

```bash
cu-runner sandbox
```
Start the synthetic application at `http://127.0.0.1:8765/legacy`. This second service is optional for `sandbox://legacy`; inline and HTTP modes render the same HTML and JavaScript. HTTP browser navigation must be verified on an unrestricted developer machine before relying on that delivery path.

### Replay the supplied capability

```bash
cu-runner import evidence/example-capability.json
```
Validate the entire artifact against the reviewed profile and import its immutable revision.

```bash
cu-runner replay --capability read_savings_balance.v1 --inputs '{"member_id":"10002"}' --target sandbox://legacy
```
Execute the saved flow without constructing a planner. The CLI waits and prints the structured result. `--no-wait` returns a run ID immediately; `cu-runner status RUN_ID` retrieves it. `cu-runner cancel RUN_ID` stops it and closes its browser. Exit codes are 0 for success, 2 for a known business outcome, 1 for failure, and 130 for an interrupted waiting command.

### Genuine provider-backed discovery, then replay

Set `MODEL_PROVIDER=openai`, `MODEL_API_KEY`, and a compatible `MODEL_NAME` in your ignored `.env`, then restart `cu-runner serve`. Do not commit the key. The sample flow uses synthetic input only:

```bash
cu-runner discover --goal 'Find the member using member_id and read their current savings balance and currency' --inputs '{"member_id":"10001"}' --target sandbox://legacy
```
The API performs live observe/decide/act calls and prints the saved artifact ID on success. On a fresh catalog this is `read_savings_balance.v1`; if the supplied artifact was already imported, the new discovery is a later revision. **Use the exact ID returned by discovery** in the following commands (replace `read_savings_balance.v2` when different):

```bash
cu-runner export read_savings_balance.v2 --out evidence/provider-capability.json
```
Export the real provider-discovered artifact for review.

```bash
cu-runner replay --capability read_savings_balance.v2 --inputs '{"member_id":"10003"}' --target sandbox://legacy
```
Replay the new artifact with a different input. The response must report `llm_calls: 0` and the final checkpoint must pass.

Copy the corresponding **redacted** `.runtime/runs/RUN_ID/` directories to clearly named subdirectories of `evidence/`, record provider/model/date in the provenance file, and run `python scripts/check_evidence.py`. Do not copy `.env`, credentials, raw screenshots, raw provider transcripts, or `.bridge` wholesale. The bundled bridge discovery is explained in [docs/BRIDGE.md](docs/BRIDGE.md); it is an explicit alternative model transport, not a fake fallback when credentials are absent.

## Human takeover demonstration

[Operator console preview](docs/operator-console.png) shows the disconnected workspace; it contains no live data or credentials.

Open `http://127.0.0.1:8000/` on your machine. Enter `OPERATOR_TOKEN` from your local `.env` and press **Connect**. The token is cleared from the input and retained only in page memory.

```bash
cu-runner replay --capability read_savings_balance.v1 --inputs '{"member_id":"10002"}' --target 'sandbox://legacy?scenario=session' --no-wait
```
Trigger a real session-expired UI state. In the console, select the `SESSION_EXPIRED` intervention, press **Claim control**, select **Restore session / click**, and press **Perform action**. The screenshot and buttons operate the original browser context, not a clone. Press **Resume automation** and inspect the final result with `cu-runner status RUN_ID`.

A separate operator token alone does not grant mutation rights: each action also needs the current revision and a short-lived claim token. A second claim or stale action is rejected. If a lease expires, ownership returns to **PAUSED**, never silently to automation. Renew before expiry, or reclaim after expiry. The overall intervention/run timeout still applies.

The palette exposes only reviewed controls. It is not arbitrary JavaScript evaluation, VNC, or an unrestricted remote browser. Irreversible account closure remains blocked even for an operator. `tests/test_console.py` verifies the actual console JavaScript against the actual FastAPI app and live browser, with a clearly labelled in-process HTTP substitute required by the verification environment.

## Runtime conditions and result contract

| Invocation | Classification and behavior |
|---|---|
| Reviewer number | Expected result |
|---|---|
| `10001`, `10002` | Standard successful lookup. |
| `10003` | Successful lookup with a zero balance. |
| `90001` | Live UI `PERMISSION_DENIED`; automation stops and requests human intervention. |
| `99999` | Live UI `NOT_FOUND`; `business_outcome`, not a crash. |
| `00000` | Live UI `VALIDATION_ERROR`; `business_outcome`. |
| Invalid input shape, e.g. four digits | API 422 before launching a browser. |
| `?scenario=notice` | Detect known interstitial, click its reviewed Continue control, recheck. |
| `?scenario=transient` | Detect temporary load problem, click Retry, recheck; bounded recovery. |
| `?scenario=slow` | Wait for a delayed render within the action budget. |
| `?scenario=outage` | Exhaust the two recovery attempts, then request an operator. |
| `?scenario=session` | Request an operator; Restore session is human-only. |
| `?scenario=dialog` | Dismiss unexpected JavaScript dialog without accepting it; operator acknowledges the reviewed warning. |
| `?scenario=permission` | Stop automatic progress and request an operator; no attempt to bypass permissions. |
| `?scenario=drift` | Version guard mismatch; fail closed and request review. |
| `?scenario=ambiguous` | Duplicate target; fail closed instead of choosing the first match. |

Every run returns `success`, `business_outcome`, or `failure`, plus `code`, step, expected screen, observed screen/signals, model-call count, intervention count, and artifact ID when successful. Failures have value-redacted structural DOM evidence. If an operator cancels a permission-denied run, the terminal code is `RUN_CANCELLED`; the preceding `PERMISSION_DENIED` event and snapshot explain its cause. A timeout is never reported as success.

## API reference and examples

The API supports a small agent-facing catalog with typed invocation contracts. Full request/response and operator examples are in [docs/API.md](docs/API.md). The exported machine-readable documents are [docs/openapi.json](docs/openapi.json) and [docs/capability.schema.json](docs/capability.schema.json).

| Method | Endpoint | Authorization |
|---|---|---|
| GET | `/health`, `/`, `/openapi.json` | Public local health, console assets, schema only. |
| GET | `/api/schema`, `/api/capabilities`, `/api/capabilities/{id}` | Caller token. |
| POST | `/api/capabilities`, `/api/discoveries`, `/api/replays` | Caller token. |
| GET / POST | `/api/runs/{id}` / `/api/runs/{id}/cancel` | Caller token. |
| GET | `/api/operator/interventions`, `/api/operator/runs/{id}` | Operator token; output values redacted. |
| POST | `/api/operator/runs/{id}/claim` | Operator token + current revision. |
| POST | `.../renew`, `.../actions`, `.../resume` | Operator token + revision + claim token. |
| GET | `.../screenshot`, `.../controls` | Operator token + revision + claim token. |
| POST / GET | `.../cancel` / `.../evidence/{snapshot}` | Operator token; evidence is already redacted. |

Example replay using a `RUNNER_TOKEN` exported into your shell (the CLI reads `.env` automatically; curl does not):

```bash
curl -X POST http://127.0.0.1:8000/api/replays \
  -H "Authorization: Bearer $RUNNER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"capability":"read_savings_balance.v1","inputs":{"member_id":"10002"},"target":"sandbox://legacy"}'
```
The response is HTTP 202 with `run_id`. Poll `/api/runs/{run_id}` using the same caller token. For sensitive invocation inputs outside the synthetic demo, use `--inputs -` to read JSON through standard input rather than shell history. This project is not authorized for real banking systems or real customer data.

## Tests and build

```bash
python -m pytest -q --cov=capability_runner --cov-report=term-missing
```
Run unit, contract, policy, API, live-browser, deterministic replay, model-transport, and operator-console tests. No paid model key or external target is needed. Provider unit tests use explicitly labelled HTTPX transport doubles; discovery tests use test-only planners and are not counted as genuine discovery evidence. Coverage is configured for the core library, excluding service/CLI launch wrappers and HTML-delivery wrapper, which have separate smoke checks.

```bash
python -m compileall -q src scripts tests
```
Compile every Python module to catch syntax/import packaging issues alongside the executable tests.

```bash
python scripts/check_dependencies.py
```
Check all installed distributions in the runtime dependency closure against their declared version constraints.

```bash
python scripts/check_evidence.py
```
Validate the saved capability and each evidence audit chain; verify persisted outputs remain redacted.

```bash
python -m pip install 'setuptools>=82.0.1,<83'
```
Install the explicit build backend into the active environment before using a non-isolated build.

```bash
python -m pip wheel --no-deps --no-build-isolation . -w dist
```
Build the distributable package. Static UI assets are packaged in the wheel. `python scripts/demo.py` additionally exercises package entry points and real localhost services end to end.

With the runner service already running, `python scripts/record_replay_evidence.py` regenerates six real replay/API evidence cases. Its operator is explicitly an automated stand-in, not claimed to be a person. It never regenerates or fabricates the genuine discovery evidence.

The included GitHub Actions workflow runs these checks in CI. Remote CI has not been executed in this environment.

## Safety and operational limits

The browser acts only on explicitly allowed origins, routes, query values, action kinds, and reviewed target bindings. Requests, unexpected popups, downloads, service workers, and WebSockets are constrained or blocked. Artifact selectors and risk classifications cannot self-authorize new operations: the engine compares the complete contract and binding digest against trusted code. Model output is strictly typed and must reference an offered candidate and current request challenge.

Only known static screen/control names, counts, booleans, and a sanitized goal go to the model. Actual member IDs, balances, names, credentials, and arbitrary page text are excluded. Inputs live in memory and are injected by parameter reference. The structured logger does not accept arbitrary bodies, goals, raw exception messages, or output values. Failure snapshots retain tag names and geometry but replace unreviewed text with `[REDACTED]`; no input values or HTML attributes are stored. Hash-linked logs make accidental modification detectable, not tamper-proof or independently attested.

The authorized operator can see a live unredacted screenshot in memory. It is served `no-store` and not saved by the application; the system cannot prevent an authorized human from saving or photographing their screen. Use only synthetic data here. Secrets use environment configuration and separate caller/operator roles, but there is no enterprise identity, institutional tenancy, TLS termination, vault integration, or regulatory certification. Browser-side restrictions are defense in depth, not a replacement for an OS/network isolation boundary when targeting hostile systems.

## Design decisions, assumptions, and next work

The design intentionally goes deep on artifacts, replay outcomes, and safe control transfer rather than cloud plumbing. The reviewed vocabulary is a narrow product adapter for one read-only savings capability; this is not a general browser agent for arbitrary websites or natural-language tasks. The model discovers the path within that allowed surface, not the universe of possible browser actions.

Artifact locators prefer exact semantic controls and fall back to nearest table-row relationships. Ambiguity stops the run; coordinates are not guessed. Desktop/accessibility adapters, tenant binding overlays, authenticated human identity, independently signed artifacts, encrypted evidence retention, a durable worker/session registry, and additional reviewed capabilities are future extensions described in [REPORT.md](REPORT.md), not unfinished endpoints hidden in this implementation.

Provider-backed discovery and zero-model replay are verified in `evidence/provider-discovery/` and `evidence/provider-replay/`. The next engineering priorities are authenticated operator identity, tenant/version bindings, durable session ownership, and independently signed artifacts.
