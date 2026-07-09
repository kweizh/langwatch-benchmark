# LangWatch: Client-Side RAG Payload Truncation to Survive the 1MB Collector Limit

## Background
The LangWatch ingestion gateway (the `/api/collector` and OTLP `/api/otel/v1/traces` endpoints) enforces a strict **~1MB body size limit** on incoming trace payloads. A Retrieval-Augmented-Generation (RAG) service retrieves several large documents per query and logs them as span context. When the retrieved documents are large, the exported trace exceeds the limit and the backend rejects it with `HTTP 413 Payload Too Large` (or the SDK silently drops the trace).

Your job is to build a RAG pipeline instrumented with the **LangWatch Python SDK** that performs **client-side truncation** of the retrieved documents *before* they are logged to the active span, so that the exported trace stays safely under the collector limit while still preserving the trace structure and the essential identifying fields of every retrieved document.

## Provided Environment
- A corpus file already exists at `/home/user/project/data/documents.json`.
- It is a JSON array of retrieved documents. Each element is an object with the string fields `document_id`, `chunk_id`, and `content`.
- The combined size of the raw `content` fields is deliberately **larger than 1MB**, so logging them verbatim would exceed the collector limit.

## Requirements
Implement a Python module named `rag_payload.py` at the project root that exposes the following importable contract:

1. `truncate_contexts(documents, max_total_bytes, max_document_bytes)` -> `list[dict]`
   - Input `documents` is a list of dicts each having `document_id`, `chunk_id`, and `content`.
   - Return a new list, **one entry per input document (never drop a document)**, where each entry keeps the original `document_id` and `chunk_id` unchanged, exposes a (possibly shortened) `content`, and additionally records the original content size in bytes under the key `original_bytes`.
   - Any `content` whose UTF-8 byte length exceeds `max_document_bytes` MUST be shortened so its UTF-8 byte length is `<= max_document_bytes`, keeping the **beginning** of the original text and ending the shortened value with the marker substring `[truncated]`.
   - Content already within `max_document_bytes` MUST be returned unchanged (no marker added).
   - The whole returned list, when JSON-serialized, MUST have a UTF-8 byte length `<= max_total_bytes` (shorten further if the per-document cap alone is not enough to fit the total budget).

2. `run_pipeline(query)` -> `str`
   - Emit, through the LangWatch SDK, a trace whose root span is named `rag_pipeline`, containing a nested retrieval span named `rag.retrieve` (span type `rag`) and a nested generation span named `llm.generate` (span type `llm`).
   - The `rag.retrieve` span must load the documents from the corpus file, truncate them with `truncate_contexts`, and log the **truncated** documents as the span's RAG context. It MUST NOT log the raw, untruncated documents to the span.
   - The `llm.generate` span must produce and record a non-empty answer derived from `query` (no real network or LLM call is required — the span merely represents that step).
   - Return the non-empty answer string.
   - Ensure the trace is flushed/exported before the function's effect is relied upon.

3. A CLI entrypoint `main.py` that initializes LangWatch (reading credentials/endpoint from the environment), runs the pipeline for the query passed as the first CLI argument, and prints the answer.

## Implementation Hints
- Install dependencies with `uv` inside a virtual environment (the LangWatch SDK misbehaves under the system `pip`). LangWatch pulls in the OpenTelemetry SDK and OTLP/HTTP exporter transitively.
- Read `LANGWATCH_API_KEY` and `LANGWATCH_ENDPOINT` from environment variables; never hardcode credentials or the endpoint.
- Look at `langwatch.setup(...)`, `langwatch.trace(...)`, and `langwatch.span(...)`. RAG context can be attached to a span via its `contexts` argument (see `RAGChunk` in `langwatch.domain`) or `span.update(...)`.
- Byte length matters, not character count: size limits are on the UTF-8 encoded payload. Truncate on encoded bytes and take care not to split a multi-byte character in a way that corrupts the value.
- Because LangWatch exports spans through a batching processor, force-flush the tracer provider before the process exits so nothing is lost (e.g. flush the global OpenTelemetry tracer provider).
- Pick internal budgets (per-document and total) that leave clear headroom below the 1MB collector limit.

## Acceptance Criteria
- Project path: /home/user/project
- Command: `python main.py "<query>"`
  - Input argument: a single free-text `<query>` string.
  - The stdout MUST contain a line in the format `Answer: <text>` where `<text>` is a non-empty string.
- Importable contract (used by the verifier):
  - `rag_payload.truncate_contexts(documents, max_total_bytes, max_document_bytes)` returns one entry per input document, preserves each `document_id` and `chunk_id`, records `original_bytes`, enforces the per-document UTF-8 byte cap, appends the `[truncated]` marker only to shortened content, keeps content already within the cap unchanged, and keeps the JSON-serialized total within `max_total_bytes`.
  - `rag_payload.run_pipeline(query: str) -> str` returns a non-empty string and exports a LangWatch trace containing spans named `rag_pipeline`, `rag.retrieve`, and `llm.generate`.
- Exported trace behavior (observed on LangWatch's OTLP export endpoint `POST {LANGWATCH_ENDPOINT}/api/otel/v1/traces`):
  - The exported (decoded) OTLP trace payload for a single pipeline run is well under the 1MB collector limit.
  - Every retrieved document's `document_id` from the corpus still appears in the exported span data (essential identifiers are retained).
  - The truncation marker `[truncated]` appears in the exported span data.
  - The beginning of each document is retained, while the tail (end) of the oversized documents does not appear in the exported span data.

