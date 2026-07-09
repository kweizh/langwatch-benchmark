# LangWatch: Client-Side Groundedness Evaluation on a RAG Span

## Background
You are building a Retrieval-Augmented Generation (RAG) pipeline in Python and want to attach a **custom, client-side groundedness evaluation** to the LangWatch span that produced the answer. Groundedness measures how much of the generated answer is actually supported by the retrieved context (a faithfulness / anti-hallucination proxy). LangWatch lets you log such custom evaluations directly onto the active span with `langwatch.get_current_span().add_evaluation(...)`, so the score, pass/fail decision, and a human-readable label all show up on the exact span that generated the answer.

Your job is to implement the pipeline, a **non-trivial, deterministic groundedness scorer**, and wire the computed evaluation onto the answer-generation span.

## Requirements
Work inside a Python project at `/home/user/project`. Implement a module named `pipeline.py` at the project root exposing these callables:

- `retrieve(query: str) -> list[str]`: Deterministically retrieve context passages for `query` from a fixed in-code document corpus (see the corpus described in Implementation Hints). Retrieval MUST be a pure function of the query and corpus (no randomness, no network).
- `compute_groundedness(answer: str, contexts: list[str]) -> dict`: Compute the groundedness of `answer` against the retrieved `contexts` and return a dict with keys `score` (float), `passed` (bool), `label` (str), and `details` (str). The metric and thresholds are specified precisely below and MUST be implemented exactly so the score is reproducible.
- `run_pipeline(query: str) -> str`: Run the end-to-end pipeline under a LangWatch trace, emit the spans described below, compute groundedness on the produced answer, log it as a custom evaluation on the **answer-generation span** via `langwatch.get_current_span().add_evaluation(...)`, and return the answer string.

Also provide a CLI entrypoint `main.py`.

### Groundedness metric specification (must be implemented exactly)
1. **Tokenize** a string by lowercasing it and extracting every maximal run matching the regular expression `[a-z0-9]+`.
2. **Drop stopwords** — remove any token contained in this exact stopword set:
   `{"a","an","the","is","are","was","were","of","to","in","on","and","or","for","with","as","at","by","it","its","this","that","these","those","be","from"}`.
3. Let `A` be the **set** of remaining tokens of `answer`, and `C` be the **set** of remaining tokens of the concatenation of all strings in `contexts` (joined with a single space).
4. If `A` is empty, `score = 0.0`. Otherwise `score = |A ∩ C| / |A|`, then round to 4 decimal places using Python's built-in `round(value, 4)`.
5. Map `score` to `passed` / `label`:
   - `score >= 0.75` → `passed = True`,  `label = "grounded"`
   - `0.4 <= score < 0.75` → `passed = False`, `label = "weakly_grounded"`
   - `score < 0.4` → `passed = False`, `label = "hallucinated"`
6. `details` must be a non-empty human-readable string that includes the numeric score.

### Span & evaluation wiring
- The trace root span must be named `rag_pipeline`.
- Retrieval happens in a child span named `retrieve_context`.
- Answer generation happens in a child span named `generate_answer`. No real LLM/network call is required — a deterministic answer derived from the retrieved context is acceptable (this task is about the evaluation wiring, not answer quality).
- The groundedness evaluation MUST be added while the `generate_answer` span is the current span, using `langwatch.get_current_span().add_evaluation(...)`, and the evaluation `name` MUST be exactly `groundedness`. The `passed`, `score`, `label`, and `details` passed to `add_evaluation` MUST equal the values returned by `compute_groundedness` for the produced answer and retrieved contexts.
- Read the LangWatch API key and endpoint from the environment (`LANGWATCH_API_KEY`, `LANGWATCH_ENDPOINT`). Do not hardcode credentials.

## Implementation Hints
- Install all Python dependencies with `uv` inside a virtual environment (some LangWatch-related packages misbehave with the system pip). LangWatch pulls in the OpenTelemetry SDK and OTLP/HTTP exporter transitively.
- Initialize the SDK with `langwatch.setup(...)`, reading the API key and endpoint from the environment.
- Use `langwatch.get_current_span().add_evaluation(name=..., passed=..., score=..., label=..., details=...)` — this attaches the evaluation to the active span. Calling it from inside the `generate_answer` span context is what binds it to the correct span.
- LangWatch exports over a batching processor; ensure spans are flushed before the process exits so nothing is lost.
- Keep `retrieve` and `compute_groundedness` pure and deterministic so the same query always yields the same score.
- Suggested fixed corpus (you may format it as you like, but retrieval must be deterministic): a small list of short factual passages about a handful of topics (e.g. LangWatch observability, OpenTelemetry tracing, RAG retrieval). A simple deterministic retrieval rule is to score each passage by token overlap with the query and return the top passages.

## Acceptance Criteria
- Project path: /home/user/project
- Command: `python main.py "<query>"`
  - Input argument: a single free-text `<query>` string.
  - The stdout MUST contain a line in the format `Answer: <text>` where `<text>` is a non-empty string.
  - The stdout MUST contain a line in the format `Groundedness: <score> <label>` where `<score>` is the numeric groundedness score and `<label>` is the computed label.
- Importable contract (used by the verifier), all in `pipeline.py`:
  - `retrieve(query: str) -> list[str]` returns a non-empty, deterministic list of context strings.
  - `compute_groundedness(answer: str, contexts: list[str]) -> dict` returns `{"score": float, "passed": bool, "label": str, "details": str}` computed exactly per the metric specification above.
  - `run_pipeline(query: str) -> str` returns a non-empty answer string, emits spans `rag_pipeline`, `retrieve_context`, and `generate_answer`, and internally retrieves context via the same logic as `retrieve`.
- Observable evaluation behavior (checked on the spans LangWatch exports to `POST {LANGWATCH_ENDPOINT}/api/otel/v1/traces`):
  - A custom evaluation named `groundedness` is attached to the `generate_answer` span (not to the root or retrieval span).
  - The attached evaluation's `passed`, `score`, and `label` equal the values returned by `compute_groundedness(answer, retrieve(query))` for the same query, and `details` is a non-empty string.

