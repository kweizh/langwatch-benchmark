# LangWatch: Blocking PII Guardrail in an LLM Pipeline

## Background
You are building a Python LLM assistant and must enforce a **hard safety guardrail** before any model output is returned to the end user. LangWatch models a guardrail as a special evaluation: you attach it to the active span with `langwatch.get_current_span().add_evaluation(..., is_guardrail=True)`, which records a child span of type `guardrail` on the trace. A guardrail whose `passed` is `False` means the check FAILED and the output must be blocked.

Your pipeline must run a **deterministic PII (personally identifiable information) guardrail** on the generated answer and branch on the result: if the guardrail fails, the pipeline must NOT leak the raw model output — it must return a fixed safe fallback message instead. If the guardrail passes, it returns the model output unchanged. Either way, the guardrail decision must be logged onto the active LangWatch trace so it is auditable.

This task is about the **guardrail wiring and the blocking control flow**, not about answer quality — a deterministic, offline "model" is acceptable.

## Requirements
Work inside a Python project at `/home/user/project`. Implement a module named `agent.py` at the project root that exposes:

- `screen_output(text: str) -> dict`: the deterministic PII guardrail. It returns a dict with keys `passed` (bool), `categories` (list[str]), `matched` (list[str]), and `details` (str). The exact detection rules and thresholds are specified below and MUST be implemented precisely so the verdict is reproducible.
- `generate(query: str) -> str`: produce a deterministic, non-empty "model" answer for `query`. No network or real LLM call is required; the answer MUST be a pure function of the query.
- `run_agent(query: str) -> dict`: run the end-to-end pipeline under a LangWatch trace, generate the answer, run the guardrail on it, log the guardrail to the active span, and BRANCH on the guardrail verdict. It returns a dict with keys `decision` (`"allowed"` or `"blocked"`), `response` (str), and `guardrail` (the dict returned by `screen_output`).
- `SAFE_FALLBACK` (module-level `str` constant): the fixed safe fallback message returned when output is blocked. It MUST NOT itself contain any PII.

Also provide a CLI entrypoint `main.py`.

### PII guardrail specification (must be implemented exactly)
Detect the following categories with these exact, case-insensitive regular expressions applied to the input text:
- `email`   → `[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`
- `ssn`     → `\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b`
- `phone`   → `\b[0-9]{3}-[0-9]{3}-[0-9]{4}\b`
- `credit_card` → `\b[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{4}\b`

Rules:
1. `categories`: the sorted, de-duplicated list of category names (from the four above) that produced at least one match.
2. `matched`: the sorted, de-duplicated list of the raw matched substrings across all categories.
3. `passed`: `True` if and only if `categories` is empty (no PII found). Otherwise `False`.
4. `details`: a non-empty, human-readable string. When PII is found it MUST mention the offending category names; when clean it MUST clearly indicate no PII was found.

### Guardrail wiring & blocking control flow
- The trace root span MUST be named `guardrail_pipeline`.
- Answer generation MUST happen inside a child span named `generate_answer`.
- While `generate_answer` is the active span, the guardrail MUST be logged via `langwatch.get_current_span().add_evaluation(...)` with `name="pii_guardrail"`, `is_guardrail=True`, and `passed` equal to `screen_output(answer)["passed"]`. This produces a child span of type `guardrail` bound to the answer span.
- Blocking behavior: if the guardrail's `passed` is `False`, `run_agent` MUST set `decision="blocked"` and `response=SAFE_FALLBACK` (the raw model output MUST NOT be returned). If `passed` is `True`, `decision="allowed"` and `response` equals the raw model output from `generate`.
- Read the LangWatch API key and endpoint from the environment (`LANGWATCH_API_KEY`, `LANGWATCH_ENDPOINT`). Do NOT hardcode credentials.

## Implementation Hints
- Install all Python dependencies with `uv` inside a virtual environment (some LangWatch-related packages misbehave with the system pip). LangWatch pulls in the OpenTelemetry SDK and OTLP/HTTP exporter transitively.
- Initialize the SDK with `langwatch.setup(...)`, reading the API key and endpoint from the environment.
- The guardrail is a *client-side* guardrail: `add_evaluation(name=..., passed=..., is_guardrail=True, details=..., label=...)` attaches to whichever span is active when it is called, so it must be called from inside the `generate_answer` span context. `is_guardrail=True` is what makes LangWatch record the child span as a `guardrail` (rather than a plain `evaluation`).
- Keep `screen_output` and `generate` pure and deterministic so the same query always yields the same verdict and answer.
- Design `generate` so the model answer can plausibly echo content from the query — that is how sensitive input data ends up in an output that the guardrail must catch.
- LangWatch exports over a batching processor; ensure spans are flushed before the process exits so nothing is lost.
- When printing structured output for the CLI, remember that other logs may be interleaved on stdout/stderr; make the required lines easy to parse.

## Acceptance Criteria
- Project path: /home/user/project
- Command: `python main.py "<query>"`
  - Input argument: a single free-text `<query>` string.
  - The stdout MUST contain a line in the format `Decision: <allowed|blocked>`.
  - The stdout MUST contain a line in the format `Response: <text>` where `<text>` is a non-empty string.
  - The stdout MUST contain a line in the format `Guardrail: <passed|failed>`.
- Importable contract (used by the verifier), all in `agent.py`:
  - `screen_output(text: str) -> dict` returns `{"passed": bool, "categories": list[str], "matched": list[str], "details": str}` computed exactly per the PII guardrail specification above.
  - `generate(query: str) -> str` returns a non-empty, deterministic string (same query ⇒ same output).
  - `run_agent(query: str) -> dict` returns `{"decision": "allowed"|"blocked", "response": str, "guardrail": dict}`, emits spans `guardrail_pipeline` and `generate_answer`, and enforces the blocking control flow described above.
  - `SAFE_FALLBACK` is a non-empty module-level string containing no PII.
- Observable guardrail behavior (checked on the spans LangWatch exports to `POST {LANGWATCH_ENDPOINT}/api/otel/v1/traces`):
  - A guardrail named `pii_guardrail` is recorded as a child span of the `generate_answer` span, and that child span's `langwatch.span.type` attribute equals `guardrail`.
  - The recorded guardrail `passed` value equals `screen_output(generate(query))["passed"]` for the same query.
  - When the guardrail fails, `run_agent(...)["response"]` equals `SAFE_FALLBACK` and does not contain the raw model output; when it passes, the response equals `generate(query)`.

