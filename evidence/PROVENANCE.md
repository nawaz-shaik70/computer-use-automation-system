# Evidence provenance and scope

The original bridge discovery record was captured on **23 September 2026**. Replay, exceptional-state, handoff, demo, and regression evidence was refreshed on **28 September 2026** on macOS using Python 3.13.9, Playwright 1.57.0, and Chromium 143.0.7499.4. A direct OpenAI API discovery and changed-input replay were captured on **2 October 2026**.

## Genuine discovery

`discovery/` is an actual successful model-driven run, ID `760407fa18f24d9192f8a558e312f24c`. ChatGPT chose each next action through the explicit external decision bridge. The service and live browser were running during those exchanges. Each response preserves the unique challenge from the corresponding fresh observation request. Eight calls selected input fill, search, member detail, accounts, savings, balance extraction, currency extraction, and finish. The initial allowlisted navigation is an engine entry operation, not a fabricated model choice.

The discovery timestamps are intentionally preserved because changing them would misrepresent when the model interaction occurred. All replay evidence directories and `replay-manifest.json` were regenerated from the saved artifact on 28 September 2026.

`discovery/model_requests/001.json` through `008.json` contain the sanitized live requests. `discovery/model_decisions/` contains the corresponding model-selected responses. `discovery/events.jsonl` records execution. `discovery/artifact.json` is the successful structured capability, also copied as `example-capability.json`. The model received candidates based on visible controls, not a preassigned full solution script. `llm_calls: 8` counts external bridge decisions, not paid-provider API requests.

## Direct OpenAI API discovery

`provider-discovery/` records run `c22a19952d5344bb8b6615ae26e98cca`, a successful live OpenAI-compatible API discovery using `gpt-4o-mini`. Eight model decisions drove the same live Chromium surface and produced `read_savings_balance.v2`. The log includes per-call token usage, model decisions, action execution, the artifact, and a redacted result. No API key, authorization header, raw input value, or raw output value is persisted.

`provider-replay/` records run `5b4dcd03005246269800f67ba1790756`, which invoked that new artifact with a different synthetic member. It returned the expected balance and currency to the authenticated caller, persisted redacted outputs, and reported `llm_calls: 0`. `provider-capability.json` is the exported artifact.

The local bridge format cannot cryptographically prove who generated a file. Authorship here is a transparent account of this tool-assisted session, not independent attestation. Hash-linked audit logs detect changed/missing/reordered records within the chain; a party controlling all files could regenerate the chain. They are not signed third-party proof.

## Live application, not a recorded response fixture

The target is the project's own synthetic multi-screen HTML/JavaScript application. The browser genuinely types, clicks, opens detail screens, reads table values, and encounters injected runtime states. It uses an iframe, nested tables, an unlabelled member input, and no test IDs. The agent does not read a business API or directly consult the JavaScript record store.

Managed Chromium policy blocks URL navigation in the verification environment. The policy was **not modified**. Instead, the explicitly supported `sandbox://legacy` target renders the bundled application with Playwright's in-memory document API and an iframe `srcdoc`. It makes no network navigation request. Both target delivery modes use the same HTML/JavaScript source. Normal HTTP browser navigation is a separate unverified delivery path, not claimed to have passed.

## Replay and exceptional states

The other evidence directories use the exact artifact from the genuine discovery. `scripts/record_replay_evidence.py` invokes the real localhost FastAPI API and the real Chromium surface, asserts result/output contracts in memory, and copies only safe run evidence. `replay-manifest.json` maps directory, run ID, outcome, transport, and operator-test role.

| Directory | What was executed |
|---|---|
| `replay/` | Successful parameterized replay with a different synthetic member; zero model calls. |
| `not-found/` | Missing member produces the business outcome `NOT_FOUND`, not a crash. |
| `validation/` | Syntactically valid but application-rejected input produces `VALIDATION_ERROR`. |
| `recovery/` | Real temporary-load UI, reviewed Retry action, successful continuation. |
| `handoff/` | Session-expired UI, exclusive claim, manual-control API action, resume on the same session, success. |
| `hard-failure/` | Permission-denied UI, automatic progress stopped, intervention created, operator cancellation, failure. |

The human-side API calls in this evidence harness are driven by an **automated operator stand-in**, not a claim that a person clicked the console. Browser/session control is real. Separately, `tests/test_console.py` executes the actual console JavaScript and user-interface actions against the real API and live browser. Because HTTP browser navigation is restricted, that test uses an explicitly labelled test-only `fetch` bridge to ASGI; it returns actual API responses, not canned ones. HTTP UI delivery itself remains unverified.

## Redaction and reproducibility

Persisted result values are `[REDACTED]`. Actual synthetic output correctness is asserted in the harness and tests. Browser snapshots store only reviewed static text, node types, and geometry; dynamic text is redacted and attributes/values are excluded. Live screenshots are not persisted. Run/session/request identifiers are random technical identifiers, not member IDs or access tokens.

The application source necessarily contains plainly labelled synthetic seed values; no real member data or banking credentials were used. Test names and test inputs also contain synthetic probes. Provider transport test credentials are nonfunctional labelled test values. Real local caller/operator secrets are excluded from the delivered project.

Run `python scripts/check_evidence.py` to validate the capability, request/decision linkage, audit chains, and persisted output redaction. Tests and package verification are summarized in `docs/VERIFICATION.md`; machine-readable test results are in `verification/`. No public repository publication, external email, Docker execution, or regulatory certification is asserted by these files.
