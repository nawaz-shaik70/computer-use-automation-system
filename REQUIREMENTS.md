# Assessment requirement map

Source: *Assignment A - Computer-Use Automation System*, interface.ai, Sections 2-11. This checklist distinguishes implemented behavior, executed proof, design-only scope, and external delivery status.

## Core requirements

| Assessment requirement | Implementation / design | Validation / evidence | Status |
|---|---|---|---|
| 3.1 Accept natural-language goal and target entry point | `api.py:DiscoveryRequest`; `cli.py discover`; `engine.py:RunManager.start` | `tests/test_discovery.py`; `evidence/discovery/model_requests/` | Implemented; one reviewed savings-task domain. |
| 3.1 Live observe -> decide -> act loop | `engine.py:_discover`; `planner.py`; `surface.py` | Eight actual ChatGPT bridge exchanges and successful browser run in `evidence/discovery/` | Implemented and executed through the explicit bridge. |
| 3.1 Real clicks, typing, navigation/state reading | `surface.py:BrowserSurface`; `static/sandbox.js` | Real Chromium replay and handoff tests; actual live inline application | Executed for bundled browser-memory target; HTTP browser navigation unverified. |
| 3.1 Max steps, timeout, dead-end stopping | `engine.py:_discover/_execute`; `settings.py` | `test_discovery.py` step limit/model escalation; `test_browser.py` intervention timeout; repetition guard in engine | Implemented; not every timeout branch separately fault-injected. |
| 3.1 Bias toward no-clean-DOM surfaces | iframe scope, exact semantic matching, nested-table fallbacks; no test IDs | `profile.py`; genuine artifact locator metadata; `tests/test_browser.py` | Implemented and exercised. |
| 3.2 Typed, serializable, reusable artifact | `schema.py:Capability`, `Action`, `Parameter`, `Step` | JSON Schema in `docs/capability.schema.json`; actual `evidence/example-capability.json` | Implemented and validated. |
| 3.2 Ordered steps and robust target identities | before/after screens, logical controls, reviewed ordered locator strategies | Artifact steps and targets; uniqueness/version browser tests | Implemented. |
| 3.2 Typed input parameters | strict string member ID; parameter-reference fill actions | `tests/test_contract_policy.py`; changed-member replay evidence | Implemented; no literal member value in artifact. |
| 3.2 Typed output shape and extraction | decimal string balance and currency enum; extraction validation | browser output tests, invalid decimal test, caller API tests | Implemented and executed. |
| 3.2 Checkpoint / success condition | final savings screen plus every declared output | `_replay`, `_discover`, `_accept_output`; real run evidence | Implemented and executed. |
| 3.2 Versioned and human-reviewable | schema version, immutable revision, family/version, profile digest, purposes, risk/retry metadata | schema round trip; unsupported version/immutable revision tests | Implemented. |
| 3.3 Replay saved artifact with parameters, no LLM decisions | `_replay` cannot instantiate a planner | monkeypatched planner-constructor failure test; replay `llm_calls: 0` | Implemented and executed. |
| 3.3 Stable targeting and success verification | ordered unique visible locators, bounded waits, every-step and final screen checks | normal, slow, ambiguous, drift tests | Implemented and executed. |
| 3.3 Known business outcomes distinct from failure | `NOT_FOUND`, `VALIDATION_ERROR` -> `business_outcome` | `evidence/not-found/`, `evidence/validation/` | Implemented and executed. |
| 3.3 Recoverable runtime conditions | reviewed notice/retry controls; at most two recoveries | `evidence/recovery/`; notice/transient/slow/outage tests | Implemented and executed. |
| 3.3 Hard failures stop with useful details | permission/version/ambiguity/checkpoint/network errors intervene; bounded unresolved failures terminate | failure result expected/observed/step; `evidence/hard-failure/` | Implemented; cancellation preserves initiating cause in audit/snapshot. |
| 3.3 No blind duplicate application after timeout | reobserve expected destination before retrying safe click | `test_timeout_retry_does_not_double_apply_committed_click`, both branches | Implemented and executed with injected timing failures. |
| 3.4 Explicit configurable action/target allowlist | `config/policy.json`; `policy.py`; browser route interception | scheme/origin/path/query/verb/action policy tests; blocked browser fetch | Implemented; HTTP network delivery subject to environment limitation. |
| 3.4 Distinguish reversible and irreversible | target risk classes; human-only session restoration; forbidden closure for every actor | policy tests for operator and automation; real session restoration | Implemented; no financial mutation capability. |
| 3.4 Never persist secrets/raw sensitive values in artifact/log | parameter references; allowlisted audit fields; input clearing; output redaction; structural snapshots | redaction tests; evidence scan and `check_evidence.py` | Implemented and checked using synthetic sensitive-value probes. |
| 3.5 Structured action logs and why | ordered, timestamped, hash-linked JSONL; enumerated model reason and recovery codes | discovery/replay `events.jsonl`; model decisions | Implemented; no private reasoning transcript. |
| 3.5 Richer failure signal | actual redacted DOM topology and bounding boxes | `snapshot-*.dom.json` in exceptional-state evidence | Implemented; raw screenshot persistence deliberately forbidden. |
| 3.6 Detect and route intervention with context | `_handoff`; operator intervention queue; code/step/capability/current state/snapshot/session ID | live queue/API tests; `evidence/handoff/` | Implemented; routing is local operator queue, not external paging. |
| 3.6 Operate the same live session and hand it back | `ControlGate`; live screenshot and control endpoints; real console | same object/UUID assertions; `tests/test_console.py` and `tests/test_browser.py` | Implemented and executed. Console test transport limitation disclosed. |
| 3.6 Ownership, pause/resume, human action evidence | leased CAS claims, action/resume lock, idempotency, lease expiry -> paused | `tests/test_control.py`; human action/claim/resume audit | Implemented and executed; automated operator drivers are labelled. |
| 3.7 Surface abstraction for legacy/desktop | `Surface` port; logical target vocabulary; proposed future locator union | `REPORT.md: Heterogeneity & multi-tenant` | Required design delivered; desktop adapter intentionally not built. |
| 3.7 Multi-tenant vendor reuse, specialization and drift | proposed signed base binding + constrained tenant/version overlays; implemented version/digest guards | same REPORT section; version mismatch test | Required design delivered; no claim of implemented tenancy/overlays. |

## Scope and deliverables

| Assessment item | Location / proof | Status |
|---|---|---|
| Section 4: pick a safe, non-trivial proxy, no real credentials/PII | local synthetic multi-screen application; three explicitly synthetic records | Delivered; no external bank was accessed. |
| Section 4: genuine LLM-led discovery and evidence | `evidence/discovery/`, `evidence/provider-discovery/`, `evidence/PROVENANCE.md` | Genuine bridge and direct OpenAI API runs included; each made eight live decisions. |
| Section 4: own model API access | `evidence/provider-discovery/`; `gpt-4o-mini`; `read_savings_balance.v2` | Executed successfully on 2 October 2026; changed-input replay recorded with zero model calls. |
| Section 5: end-to-end vertical slice across all core capabilities | model discovery -> artifact -> zero-model replay -> outcomes -> same-session handoff | Executed on bundled browser-memory UI; scope caveats are explicit. |
| Section 6.1: source + `/README.md`, setup/keys/offline mode | complete source; README; `.env.example`; initialization/demo scripts | Delivered locally. |
| Section 6.1: exact goal discovery and resulting-artifact replay commands | README provider-backed discovery section; bridge guide; import/replay demo | Delivered; revision selection explicitly documented. |
| Section 6.2: `/REPORT.md` with all seven exact headings | Architecture; Artifact schema; Determinism & error handling; Heterogeneity & multi-tenant; Escalation & handoff; Safety; Cuts | Delivered, approximately 1,500 words. |
| Section 6.3: `/evidence/` saved artifact, discovery and replay logs | `example-capability.json`, `discovery/`, `replay/` | Delivered from actual runs. |
| Section 6.3: exceptional replay evidence | `not-found/`, `validation/`, `recovery/`, `handoff/`, `hard-failure/` | Delivered with redacted snapshots where relevant. |
| Section 8: optional agent-callable catalog | typed catalog + import/export/invoke endpoints | One optional stretch delivered. Other stretches intentionally omitted. |
| Section 9: explainable AI-assisted engineering, no inappropriate targets/secrets | README/REPORT/PROVENANCE; policy; tests; package secret scan | Delivered with explicit architecture, trade-offs, provenance, and limitations. |
| Section 11: public GitHub repository and email URL, not ZIP | External delivery step | Not part of the local implementation or verification record. |

## Engineering quality

| Requested item | Disposition |
|---|---|
| Working backend/API and operator frontend | FastAPI + static JavaScript console; real live-session test. |
| Models/schema/migrations/seed | Typed capability/result/ownership contracts; JSON Schema; synthetic fixture records. SQL database and SQL migrations are not necessary and are not fabricated. |
| Authentication, authorization, validation, errors | Separate caller/operator tokens, per-claim lease, strict payloads, action policy, non-echoing validation errors, typed outcomes. |
| Configuration, `.env.example`, dependencies | Pinned direct dependencies; validated environment; random-token initializer; runtime closure check. |
| Unit/integration/API/browser tests | `tests/`; actual results in `evidence/verification/`; scope in `docs/VERIFICATION.md`. |
| Install/build/start and important flows | Editable installation, wheel build/install check, localhost services, real Chromium interactions, demo script. |
| Docker verification | Not applicable: the verified implementation uses a direct local Python/Playwright workflow. |
| API docs, design, decisions, trade-offs, limitations | README, REPORT, API guide, OpenAPI/JSON Schema, provenance, verification report. |
| No missing dependencies, unfinished endpoints, hidden mock behavior | Real adapters and browser path; test doubles and the synthetic target are explicitly identified. |
| `.gitignore`, cleanup, no secrets, ZIP | Build/runtime caches, real `.env`, temporary files, and source PDFs excluded; package verification and checksum recorded. |

## Evaluation priorities

System design is concentrated in the schema, trusted binding, replay contract, and ownership state machine. Correctness is demonstrated by actual live discovery and changed-input replay. Robustness is demonstrated by business/recovery/hard-failure scenarios, not only the happy path. Handoff keeps one browser and one owner. Generalization is a design extension rather than premature infrastructure. Safety evidence is minimized and redacted. Communication uses the assessment's exact requested report structure and openly separates executed proof from unverified integrations.
