# LangWatch Prompt A/B Variant Switcher (TypeScript)

## Background
You are building the experimentation layer of a customer-support assistant that runs on [LangWatch Prompt Management](https://langwatch.ai/docs/prompt-management/getting-started). The product team maintains several competing **prompt variants** for the same task and wants to run an online A/B test: on every request the runtime should pick a variant by **weighted random sampling**, compile it with the request variables, build the ready-to-execute model payload, and **record which variant was chosen on the LangWatch trace** so that per-variant performance can be analyzed later (see [Link to Traces](https://langwatch.ai/docs/prompt-management/features/advanced/link-to-traces)).

The selection must be **reproducible**: given the same seed, the runtime must always produce the exact same sequence of variant choices, so experiments can be replayed and audited. This is a TypeScript project.

## Requirements
- Scaffold a LangWatch prompts project (the tracking file `prompts.json` must exist at the project root) and define **three** local prompt variants as LangWatch `.prompt.yaml` files under `prompts/`:
  - `support-reply-concise` (variant id `concise`)
  - `support-reply-empathetic` (variant id `empathetic`)
  - `support-reply-detailed` (variant id `detailed`)
  - Every variant must use a `model` identifier of the form `openai/<model>`, contain at least a `system` and a `user` message, reference the two template variables `{{customer_name}}` and `{{question}}` (LangWatch mustache `{{...}}` syntax), and its `system` message must contain its own variant id as a literal marker token (e.g. the string `concise`) so the active variant is identifiable in the compiled output.
- Implement a TypeScript runtime, runnable via the npm script `switch`, that performs an A/B sampling loop with these variant sampling weights: `concise = 0.2`, `empathetic = 0.5`, `detailed = 0.3`.
- For each iteration the runtime must:
  - Select one variant via **deterministic, seed-driven weighted random sampling** (the same `--seed` must always yield the same ordered sequence of selections; the empirical selection frequencies over many iterations must converge to the configured weights).
  - Load the selected variant through LangWatch prompt management (`langwatch.prompts.get(...)`) and compile it with the provided runtime variables. Compilation must replace every `{{...}}` placeholder; a request that is missing a required template variable must fail loudly.
  - Open a real LangWatch span (via a LangWatch tracer) representing the execution, attach the chosen variant to that span so it is recorded on the trace, and emit the finished span to a local span log for auditing.
- Do NOT mock LangWatch, OpenTelemetry, or any transitive dependency, and do NOT call any external LLM API. Read any credentials (such as `LANGWATCH_API_KEY`) from environment variables. The runtime must exit cleanly with all output files fully flushed.

## Implementation Hints
- Use the LangWatch Prompts CLI (`langwatch prompt init`, `langwatch prompt create <name>`) to scaffold the project and the variant YAML files locally; creating prompts is a local operation. Materialized/local prompts are resolved from the workspace, so `langwatch.prompts.get(...)` works without a live backend.
- Implement a small seeded pseudo-random generator (a fixed seed must be fully reproducible); do not use unseeded `Math.random()`. Map a uniform draw onto the cumulative weight intervals to pick the variant.
- Use `getLangWatchTracer()` / `withActiveSpan()` (or `startActiveSpan`) to create spans, `setType("prompt")` to type them, and attach the selected prompt to the span (for example with `setSelectedPrompt(...)`). Also set explicit span attributes for the chosen variant so the choice is machine-inspectable on the exported span.
- To make the recorded trace auditable offline, register a real OpenTelemetry span processor/exporter that appends every finished span to the `--spanlog` file as newline-delimited JSON; genuine span export is required (no mocking).
- The runtime should be a TypeScript source file executed through a tool such as `tsx` (wired to the `switch` npm script). Ensure spans are flushed (e.g. await the observability shutdown) before the process exits so the span log is complete.
- Prompt log lines may be interleaved with other stdout; write structured results only to the `--out` and `--spanlog` files so they can be parsed as JSON.

## Acceptance Criteria
- Project path: /home/user/myproject
- Command: `npm run switch -- --iterations <int> --seed <int> --vars <json_object> --out <path> --spanlog <path>`
  - `--iterations`: number of A/B sampling iterations to run.
  - `--seed`: integer seed controlling the deterministic selection sequence.
  - `--vars`: a JSON object string mapping template variable names to string values.
  - `--out`: path to write the run summary JSON.
  - `--spanlog`: path to write the newline-delimited JSON span log.
- The `--out` file must be a JSON object of this shape:
  ```json
  {
    "seed": integer,
    "iterations": integer,
    "variants": [ { "id": string, "handle": string, "weight": number } ],
    "distribution": { "<variantId>": integer },
    "selections": [
      {
        "iteration": integer,
        "variantId": string,
        "handle": string,
        "version": integer,
        "traceId": string,
        "spanId": string,
        "model": string,
        "messages": [ { "role": string, "content": string } ]
      }
    ]
  }
  ```
  - `selections` has exactly `iterations` entries; `distribution` maps each variant id to the count of its selections and the counts sum to `iterations`.
  - Each selection's `messages` are the compiled messages: they must contain the selection's `variantId` as a substring, must contain every provided `--vars` value, and must not contain any `{{` substring.
  - `model` must start with `openai/`; `version` must be an integer.
- The `--spanlog` file must contain one JSON object per line for each exported span. For every selection there must be a corresponding span line whose `spanId` matches the selection and that carries machine-readable attributes recording the chosen variant id, handle, and integer version, plus a `prompt` span type.
- Determinism: two runs with the same `--seed` and `--iterations` must produce identical ordered `variantId` sequences in `selections`.
- Statistical behavior: over a large number of iterations the observed selection frequency of each variant must be close to its configured weight (`concise` 0.2, `empathetic` 0.5, `detailed` 0.3).
- Error handling: if a required template variable is not present in `--vars`, the command must exit with a non-zero status and must not write a fully compiled successful `--out` summary.
- Required artifacts at the project root: `prompts.json` and the three variant files under `prompts/` (e.g. `prompts/support-reply-concise.prompt.yaml`, `prompts/support-reply-empathetic.prompt.yaml`, `prompts/support-reply-detailed.prompt.yaml`).

