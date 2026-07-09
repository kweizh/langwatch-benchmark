# LangWatch: OpenTelemetry Integration with Selective Span Export Filtering

## Background
A Python service already has its own **global OpenTelemetry `TracerProvider`** wired up for internal observability (spans are exported to the team's existing tracing backend). The team now wants to add **LangWatch** for LLM observability, but they must NOT send noisy internal spans (health checks and low-level database queries) to LangWatch, while still sending the meaningful LLM and RAG spans.

LangWatch is OpenTelemetry-native: when `langwatch.setup()` attaches its exporter to a `TracerProvider`, **every** span managed by that provider is exported to LangWatch by default — including spans created directly with the OpenTelemetry API. LangWatch supports server-side selective filtering of its own export path via `span_exclude_rules`, which drop spans **before** they reach LangWatch **without** affecting any other exporter/processor attached to the same provider.

Your job is to integrate LangWatch alongside the pre-existing global provider and apply span exclusion rules so that internal health-check and database spans never reach LangWatch, while LLM and RAG spans do.

## Requirements
- Work inside a Python module named `observability.py` at the project root.
- Implement `configure_langwatch(tracer_provider)`:
  - Attach LangWatch to the **already-existing** `tracer_provider` that is passed in (this provider is the current global provider; do NOT create a brand-new provider and do NOT replace the global one).
  - It must NOT remove, replace, or disturb any span processors/exporters already attached to that provider.
  - Configure LangWatch's export filtering so the following spans are **excluded** from being exported to LangWatch:
    - Any span whose name is exactly `GET /health_check`.
    - Any span whose name **starts with** `db.` (internal database operations).
  - All other spans must still be exported to LangWatch.
  - Read the LangWatch API key and endpoint from the environment (`LANGWATCH_API_KEY`, `LANGWATCH_ENDPOINT`). Do not hardcode credentials.
- Implement `run_pipeline(query)`:
  - Using the **global** OpenTelemetry tracer (i.e. spans created through the shared global provider), execute a small RAG-style pipeline that produces the following spans, nested under a single root span:
    - Root span named `rag_pipeline`.
    - A span named `GET /health_check` (an internal health probe).
    - A span named `db.query.documents` (a database lookup).
    - A span named `rag.retrieve` (document retrieval).
    - A span named `llm.generate` (the LLM generation step).
  - Return a non-empty answer string derived from `query`. (No real LLM/network call is required — the `llm.generate` span merely represents that step.)
- Provide a CLI entrypoint `main.py` that: builds/sets the application's global OpenTelemetry provider, calls `configure_langwatch(...)` with it, runs `run_pipeline(<query>)`, and prints the result.

## Implementation Hints
- Install all Python dependencies with `uv` inside a virtual environment (some LangWatch-related packages misbehave with the system pip). LangWatch pulls in the OpenTelemetry SDK and the OTLP/HTTP exporter transitively.
- Look at `langwatch.setup(...)`: it accepts an existing `tracer_provider` and a `span_exclude_rules` list. Passing the existing provider makes LangWatch attach its own filtered export processor to it rather than creating a new one.
- Exclusion rules are expressed with `SpanProcessingExcludeRule` from `langwatch.domain`, matching on `span_name` with operations such as `exact_match` and `starts_with`.
- Because LangWatch exports via a batching processor, make sure spans are flushed (e.g. force-flush the provider) before the process ends so nothing is lost.
- Emit the pipeline spans with the plain OpenTelemetry API (`opentelemetry.trace.get_tracer(...).start_as_current_span(...)`) so they flow through whatever provider is currently global. Nest the child spans inside the `rag_pipeline` root span.

## Acceptance Criteria
- Project path: /home/user/project
- Command: `python main.py "<query>"`
  - Input argument: a single free-text `<query>` string.
  - The stdout must contain a line in the format: `Answer: <text>` where `<text>` is a non-empty string.
- Importable module contract (used by the verifier):
  - `observability.configure_langwatch(tracer_provider)` attaches LangWatch, with span exclusion, to the provider passed in, and preserves any pre-existing span processors on that provider.
  - `observability.run_pipeline(query: str) -> str` emits, through the current global OpenTelemetry provider, spans named `rag_pipeline`, `GET /health_check`, `db.query.documents`, `rag.retrieve`, and `llm.generate`, and returns a non-empty answer string.
- Export filtering behavior (observed on LangWatch's OTLP export endpoint `POST {LANGWATCH_ENDPOINT}/api/otel/v1/traces`):
  - Spans named `rag_pipeline`, `rag.retrieve`, and `llm.generate` ARE exported to LangWatch.
  - Spans named `GET /health_check` and `db.query.documents` are NOT exported to LangWatch.
  - All five spans still reach other (non-LangWatch) exporters attached to the same global provider.

