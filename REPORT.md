# Computer-Use Automation System

Ahmed Nawaz Shaik

## Architecture

The system separates a capability contract, reviewed vendor binding, surface adapter, execution engine, model planner, and control gate. FastAPI exposes discovery, a typed capability catalog, deterministic invocation, run status, and a separately authenticated operator interface. One process owns a bounded set of independent browser sessions. Atomic JSON artifacts are the durable product; live credentials, inputs, outputs, and browser objects are not database records.

The concrete target is a synthetic servicing application with an iframe, nested tables, an unlabelled member field, and no test IDs. Its multi-step task is member lookup, member detail, accounts, savings, then typed balance/currency extraction. It exposes no business API to the agent. Both delivery modes execute the same real HTML/JavaScript. `sandbox://legacy` renders that bundled UI in browser memory; HTTP delivery exists for ordinary developer machines. The verification environment blocks URL navigation by managed policy, which was left unchanged.

Discovery sends a sanitized goal and current visible affordances to a planner, executes one validated choice, observes again, and stops only on a checked success condition or bounded failure. The model does not receive a prescribed action sequence. Replay uses the saved actions directly and never constructs a planner. The OpenAI-compatible adapter and external-model decision bridge implement the same port. Evidence includes both the original ChatGPT bridge run and a later direct OpenAI API run, with their transports labelled separately.

Python, FastAPI, Pydantic, AsyncIO, JavaScript, Pytest, and Playwright provide explicit contracts, asynchronous execution, real browser interaction, and focused verification. PostgreSQL, Redis, LangGraph, React, Kubernetes, and cloud infrastructure would add dependencies without strengthening this vertical slice.

## Artifact schema

`Capability` is strict, serializable, versioned, and independently reviewable. It contains schema version, immutable capability revision, application family/version, reviewed binding digest, typed inputs, typed outputs, target definitions, ordered actions with before/after screens, exception handlers, and a final checkpoint. An action is one of navigate, fill, click, or extract, with a shape validated for that action. Fill references `member_id`, never a recorded literal. Decimal money is a finite, pattern-validated string to avoid floating-point rounding.

Targets are logical names resolved through iframe scope and an ordered locator strategy. Exact role/name or label targeting is preferred. The intentionally unlabelled input falls back to the nearest table row whose text is exactly the reviewed label. Each target carries purpose, risk, action kind, and retry safety. This makes robustness reasoning visible in the artifact without recording raw page HTML or model deliberation.

Replay checks the entire binding, error rules, input/output contracts, and digest against trusted code. An imported JSON file cannot declare a destructive control safe or introduce an exfiltration locator. New adaptations need a reviewed profile release, not just an artifact edit. The recorded path can vary within that approved vocabulary; targets and output contracts cannot self-authorize. Existing revisions are immutable, and unsupported schema versions fail validation.

## Determinism & error handling

Replay follows ordered steps, checks preconditions, resolves a unique visible control, performs the action, then verifies the recorded destination. Locator fallbacks are ordered and used only when a preceding strategy finds no visible matches. Multiple matches stop progress. Browser waiting is bounded; screen markers, output types, and the final checkpoint are all verified rather than inferring success from a click.

Runtime rules distinguish three classes. Not found and application validation errors are legitimate `business_outcome` results. Known interstitials and transient-load screens have reviewed recovery controls and a maximum of two recoveries. Permission denial, unexpected dialogs, session expiry, exhausted recovery, unknown checkpoints, version mismatch, and ambiguity stop automatic progress and request intervention. A JavaScript confirmation is dismissed, not accepted blindly. Operator-only restoration is a separate authority decision.

A timed-out click first checks whether its destination already appeared, preventing blind duplicate application. Only reviewed read-only/reversible operations are retryable; irreversible account closure is forbidden. Overall runtime, model calls, repeated ineffective choices, action duration, and intervention count are bounded. Outputs are validated again at extraction. Invalid output shapes terminate rather than returning untrusted data.

Results distinguish success, business outcome, and failure, with step, expected screen, observed screen/signals, model-call count, and intervention count. Redacted structural DOM snapshots accompany failures and exceptional states. Cancellation and timeouts have explicit terminal codes; prior exceptional-state events retain the initiating cause. Tests monkeypatch planner construction to raise during replay, proving that the production execution path is model-free.

## Heterogeneity & multi-tenant

The `Surface` port owns perception, locator resolution, actions, richer evidence, and live-session lifetime. The engine owns goals, artifacts, checkpoints, outcomes, and control ownership. A desktop adapter would map logical controls to accessibility roles/names or reviewed visual anchors, and return the same sanitized observation structure. A future schema version could use a discriminated locator union for web, accessibility, and visual strategies. It should record scale/window/anchor constraints, not unqualified absolute coordinates. That adapter is designed, not implemented.

For institutional scale, separate vendor capability semantics from signed, tenant/version-specific bindings. A vendor base artifact should declare supported versions and contract compatibility. Tenant overlays should contain only allowlisted target/branding mappings and entry points, not arbitrary script or weaker safety rules. Validate overlays against schema, profile digest, policy, and replay canaries before activation; roll back by immutable revision. A version/uniqueness/checkpoint mismatch should disable unattended execution and request review rather than silently rerecord a new flow.

Production routing would select the tenant's compatible binding and isolated worker/session identity. Queues, tenant quotas, artifact approval, encrypted tenant-scoped evidence, and a durable lease registry belong outside the surface adapter. This implementation demonstrates an application-version guard and immutable profile binding, but does not claim real multi-tenancy, overlay management, or cross-tenant execution.

## Escalation & handoff

Ownership is explicit: AUTOMATION -> PAUSED -> HUMAN -> AUTOMATION, or FINISHED. An intervention includes capability, step, safe current observation, expected screen, redacted snapshot reference, and the original session ID. The operator queue is a real API-backed route, not a log message pretending to page someone. The browser stays open while the automation task waits at a checked boundary.

A claim uses a compare-and-set revision and produces a short-lived random lease. A lock serializes manual actions and resume; stale claims/actions are rejected. Manual action request IDs are idempotent, preventing duplicate application on retry. A lease expiry returns to PAUSED, not automation. Renewal extends ownership only within the overall intervention/run deadline. Cancellation closes the browser and revokes control.

The minimal console renders a current screenshot and a palette of reviewed controls on the same live browser. An operator can restore an expired session or acknowledge a warning, then return control. The engine observes again before continuing. It does not assume that the human solved the problem. Human actions, claims, expiry, and resume are audited without input values. The console and direct API tests verify the same session identifier before and after handoff. Automated operator test drivers are explicitly labelled as such; the control-transfer mechanism itself is real.

## Safety

A trusted policy constrains origins, exact routes/methods, query values, and action types; trusted bindings constrain controls and risk. Network requests are inspected, and popups, downloads, service workers, and WebSockets are restricted. The browser is not permitted to widen policy. The model only chooses currently offered, reversible candidates; request challenges and typed decisions prevent stale or invented choices. Destructive account closure remains forbidden even for humans.

Data minimization is stronger than regex-only redaction. Model observations contain approved static identifiers, counts, and booleans, not raw text, member values, or extracted balances. Goals are parameterized and vocabulary-filtered. Persisted results redact every output; snapshots discard all attributes/values and unreviewed text. Runtime inputs are cleared at completion and outputs expire from memory. Secrets are external configuration, caller/operator tokens differ, and validation errors do not echo request bodies. Hash-linked evidence detects modification but is not cryptographically authenticated provenance.

An authorized human can see sensitive live pixels; the application does not persist screenshots, but cannot prevent operator capture. This local, synthetic-only application is not a regulated-bank production deployment. OS/network isolation, TLS, institutional identity, tenant authorization, key management, tamper-evident external storage, and retention governance are necessary before such deployment.

## Cuts

Only one reviewed read-only capability and one real browser adapter are implemented. Desktop support, general visual reasoning, arbitrary manual remote desktop, tenant overlays, cloud deployment, durable session recovery, SQL storage, SSO, and artifact approval are intentional cuts, not hidden partial endpoints. The callable capability catalog is the only optional extension. Docker is omitted because the verified local workflow is sufficient for this single-process system.

Genuine model-led bridge discovery, direct OpenAI API discovery, zero-model replay, exceptional outcomes, and same-session handoff are included. Normal HTTP browser navigation remains unverified in the managed browser environment; local HTTP APIs and network-free browser interaction were verified separately. Stronger deployment isolation, authenticated operator identity, and tenant/version bindings take priority over additional feature breadth.
