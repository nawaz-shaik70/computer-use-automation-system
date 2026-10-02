# External model decision bridge

## What it is

`MODEL_PROVIDER=bridge` delegates each live choice to an external LLM capable of reading and writing the local mailbox. It is a **transport**, not a planner that knows the solution: it writes one observation request, waits, validates one response, and returns that response to the common execution engine. Without an external response it times out and escalates. It never substitutes a canned action sequence.

The included run was conducted by ChatGPT using its filesystem tools. For each of eight sequential requests, ChatGPT received the fresh observation and offered candidates, chose one, and wrote its response. The browser then executed that choice before the next observation was generated. This is actual LLM-led live UI interaction, not a transcript manufactured after a scripted run.

It is **not a hosted OpenAI API run**. The local transport cannot independently attest the model or person that wrote a file. A malicious local writer could spoof a response; file permissions, request challenges, and reviewed actions constrain the effect but do not prove authorship. The provenance states how this run was produced, without inventing billing records, provider response IDs, or token usage.

## Running it with an external model

Create `.env` using `python scripts/init_env.py`, set `MODEL_PROVIDER=bridge`, and increase `MODEL_TIMEOUT_SECONDS` (for example 300) and `RUN_TIMEOUT_SECONDS` (for example 900) for interactive decisions. These remain bounded. Start `cu-runner serve`, then issue the README discovery command with `--no-wait` to obtain its run ID.

The service creates `.bridge/RUN_ID/001.request.json`. It contains:

- the system instructions and sanitized goal;
- the current browser-derived observation, required outputs, and recent safe action history;
- a unique `request_id`, permitted candidates, and the exact response schema.

Give this complete request to the external LLM. The LLM selects **one offered candidate**, preserving the current `request_id`, and supplies a short reason from the schema's enum. Atomically write the response to `.bridge/RUN_ID/001.response.json` with `capability_runner.storage.atomic_json`. Do not pre-fill later responses: their request challenges and live observations do not exist yet.

After the engine validates and executes the choice, read the next numbered request and repeat. Decisions can fill by parameter reference, click an observed reviewed control, extract a declared output, request intervention, or finish when offered. The output values themselves are withheld from the model. A stale request ID or unoffered action is rejected before it becomes accepted decision evidence.

A successful run returns a saved capability ID. Replay that artifact with the ordinary `cu-runner replay` command. Replay does not read the mailbox or contact a model.

## What gets retained

Accepted requests and decisions are copied into the run's `model_requests/` and `model_decisions/` evidence subdirectories. Values, raw page text, and secrets are not included. The artifact captures the observed action path, targets, contracts, and checkpoints, not the model conversation. `events.jsonl` records the enum reason, action IDs, safe observations, and ownership transitions.

The bridge is deliberately explicit because offline scripted discovery would misrepresent a model-driven run. For unattended discovery, use `MODEL_PROVIDER=openai`; direct-provider evidence is retained separately from bridge evidence.
