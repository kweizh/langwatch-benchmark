import os
import time
from typing import Sequence

# ---------------------------------------------------------------------------
# Patch the OpenTelemetry OTLP span exporter so that spans are serialised as
# JSON instead of protobuf. The local mock collector (`mock_collector.py`)
# writes the request body verbatim to `payload.json`; if it receives binary
# protobuf the file will not be valid JSON and the trace will effectively be
# dropped. Sending JSON keeps the payload human readable and matches what
# LangWatch's real collector accepts.
# ---------------------------------------------------------------------------
from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
    OTLPSpanExporter as _OtlpSpanExporter,
    encode_spans,
)
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from google.protobuf.json_format import MessageToJson


class JsonOtlpSpanExporter(_OtlpSpanExporter):
    """OTLPSpanExporter that serialises spans as JSON for the mock collector."""

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if self._shutdown:
            return SpanExportResult.FAILURE

        serialized = encode_spans(spans)
        json_body = MessageToJson(serialized).encode("utf-8")

        try:
            response = self._session.post(
                url=self._endpoint,
                data=json_body,
                headers={"Content-Type": "application/json"},
                timeout=self._timeout,
            )
        except Exception:
            return SpanExportResult.FAILURE

        if response.status_code not in (200, 202):
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS


# Replace the OTLP exporter class used by langwatch.client BEFORE langwatch
# is imported/setup, so its `_setup_otel` picks up our JSON variant.
import langwatch.client as _langwatch_client  # noqa: E402

_langwatch_client.OTLPSpanExporter = JsonOtlpSpanExporter

import langwatch  # noqa: E402

langwatch.setup(
    api_key=os.getenv("LANGWATCH_API_KEY", "dummy_key"),
    endpoint_url=os.getenv("LANGWATCH_ENDPOINT", "http://localhost:8080"),
)


@langwatch.trace(name="RAG Pipeline")
def run_rag_pipeline(question: str):
    answer = "The capital of France is Paris."
    retrieved_context = "A" * 2000000  # 2MB document

    # Client-side payload filtering: truncate the retrieved document to
    # 1000 characters before logging it to the span so the trace payload
    # stays below LangWatch's 1MB collector body limit.
    truncated_context = retrieved_context[:1000]

    with langwatch.span(name="Document Retrieval", type="rag_retrieval") as span:
        span.update(
            input={"query": question},
            output={"documents": [truncated_context]}
        )
    return answer


if __name__ == "__main__":
    run_rag_pipeline("What is the capital of France?")
    # allow time for background telemetry to flush
    time.sleep(2)