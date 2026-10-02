# Execution and verification record

Verified on **28 September 2026**, macOS, Python **3.13.9**, Playwright **1.57.0**, and Chromium **143.0.7499.4**. See `evidence/verification/summary.json` for the machine-readable environment, exact test duration, and result scope.

## Final results

**107 tests passed; 0 failed; 0 skipped. Core-library statement coverage: 89% (rounded).** The final regression run completed in 43.09 seconds. Coverage covers the core package; `cli.py` and the sandbox HTML-delivery wrapper are excluded by the committed coverage configuration and have separate service/HTML smoke checks. No claim of 100% coverage or complete deployment verification is made.

The actual command was:

```bash
python -m pytest -q --cov=capability_runner --cov-report=markdown:evidence/verification/pytest.txt --junitxml=evidence/verification/tests.xml
```

The human-readable coverage result is `evidence/verification/pytest.txt`; JUnit XML with the test result, duration, timestamp, and host is `evidence/verification/tests.xml`.

## Executed checks

| Check | Actual outcome |
|---|---|
| Install application and test dependencies | `pip install --no-index --no-build-isolation -e '.[test]'` succeeded using already available dependencies. No fresh network downloads are claimed. |
| Compile Python / import modules | Every Python source/script/test parses and compiles; all package modules import. |
| JavaScript syntax | `node --check` passed for console and sandbox JavaScript. |
| Dependency consistency | All 22 distributions in the runtime dependency closure satisfy their declared requirements. |
| Build package | Setuptools produced `capability_runner-1.0.0-py3-none-any.whl`. |
| Install built wheel | Installed into a separate virtual environment and imported outside the source directory. Required static assets and HTML generation verified. Existing verified dependency packages were explicitly reused, not freshly installed from the internet. |
| Start services | Real runner and sandbox HTTP services started, responded to localhost requests, and stopped cleanly in the one-command demo. |
| Real discovery | Eight genuine ChatGPT-selected bridge decisions and, separately, eight direct OpenAI API `gpt-4o-mini` decisions each drove the live browser to a successful artifact. |
| Real replay | Changed-input replay returned correct typed outputs, checked the final screen, and recorded zero model calls. |
| API integration | Authenticated localhost POST/GET calls drove six real replay/error/handoff evidence cases. |
| Operator frontend integration | Actual console HTML/CSS/JavaScript, actual FastAPI routes, actual screenshot, actual browser action, same session before/after resume. Test-only in-process fetch transport was used because URL navigation is blocked. |
| Ownership | Competing claim rejection, stale revision/lease rejection, lease expiry, renewal, manual-action idempotency, serialization, resume, cancellation, and timeout behavior tested. |
| Runtime conditions | Not-found, input rejection, known interstitial, temporary failure, sustained failure, slow rendering, permission denial, session expiry, unexpected dialog, version mismatch, and ambiguous targets tested. |
| Retry correctness | Both pre-commit timeout and already-committed click cases tested; a completed click is not blindly applied twice. |
| Safety/data handling | Target/action allowlists, immutable profile binding, forbidden actions, invalid model choices, input/output validation, role separation, non-echoing validation errors, and sensitive-value redaction tested. |
| Evidence | Complete artifact, eight request/decision links, and seven audit chains validated; persisted outputs are redacted. |
| UI review | Disconnected console screenshot reviewed for clipping/layout; `docs/operator-console.png` contains no live credentials or customer data. |
| CI configuration | GitHub Actions YAML parsed and required steps inspected; remote GitHub execution not performed. |
| One-command demo | `python scripts/demo.py` passed with real services/browser, checked output values in memory, confirmed zero model calls, and cleaned up its subprocesses. |

During verification, a console dependency on secure-context-only `crypto.randomUUID` was replaced with `crypto.getRandomValues` for the network-free document. The evidence harness was slowed to respect the API's real rate limit. A test-only wait budget was enlarged to allow the instrumented sustained-failure scenario to reach its intended intervention; production limits were not weakened. The complete suite was rerun after these corrections.

## Environment restrictions and unverified paths

**Hosted model API:** a live `gpt-4o-mini` discovery through the OpenAI-compatible adapter succeeded on 2 October 2026 with eight model calls, producing `read_savings_balance.v2`. Its changed-input replay succeeded with zero model calls. The redacted audit records are preserved under `evidence/provider-discovery/` and `evidence/provider-replay/`; the original bridge run remains separately labelled.

**Browser HTTP navigation:** managed Chromium policy blocks URL navigation. No policy was removed or changed. The bundled `sandbox://legacy` target loads only this project's own interactive HTML/JavaScript into browser memory and is fully exercised. Its clicks, typing, iframe screens, extraction, failure states, and handoff are real UI behavior. Ordinary HTTP browser delivery and CSP behavior under that delivery mode remain unverified. Localhost API traffic was tested independently with HTTPX.

**Fresh network install and platform matrix:** package construction and installation succeeded using installed dependencies. A clean machine fetching all dependencies, other operating systems, Python 3.11, and GitHub-hosted CI were not executed here. CI configuration is provided for Python 3.11 and 3.13. Use the README prerequisites and browser installation step on a new machine.

**Docker/database/cloud:** no Docker files, SQL database, migrations, cloud resources, or tenant infrastructure are part of this deliberately small implementation. There is nothing in those categories asserted to have been tested. JSON schema/version validation and synthetic seed data are implemented and tested instead.

**External delivery:** repository publication and email delivery are outside this local execution record.

## Evidence inspection

`evidence/PROVENANCE.md` distinguishes genuine model choices, deterministic replay, and automated operator stand-ins. `scripts/check_evidence.py` checks schema, model decision/request linkage, artifact action correspondence, hash-chain consistency, and output redaction. It is not cryptographic model-authorship attestation.

The packaging script uses an explicit source/document/evidence allowlist, excludes runtime directories and `.env`, checks for the actual local credential values and common private-key patterns, and includes a per-file SHA-256 manifest. ZIP integrity and the manifest are checked again after extraction before delivery.
