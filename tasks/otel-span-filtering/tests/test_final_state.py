import gzip
import importlib
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

PROJECT_DIR = "/home/user/project"
QUERY = "What is LangWatch?"

EXPECTED_ALL_SPANS = {
    "rag_pipeline",
    "GET /health_check",
    "db.query.documents",
    "rag.retrieve",
    "llm.generate",
}
EXCLUDED_FROM_LANGWATCH = {"GET /health_check", "db.query.documents"}
INCLUDED_IN_LANGWATCH = {"rag_pipeline", "rag.retrieve", "llm.generate"}

# Ensure a default API key is present even before the fixture runs, in case the
# agent's module touches langwatch at import time.
os.environ.setdefault("LANGWATCH_API_KEY", "sk-lw-test-key")

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)


def _make_collector():
    """Start a real local OTLP/HTTP collector that stands in for LangWatch.

    It records the names of every span POSTed to /api/otel/v1/traces by decoding
    the OTLP protobuf payload. This is a genuine HTTP endpoint, not a mock of any
    LangWatch or OpenTelemetry dependency.
    """
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceRequest,
        ExportTraceServiceResponse,
    )

    received_names = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""
            if self.headers.get("Content-Encoding") == "gzip" and body:
                try:
                    body = gzip.decompress(body)
                except Exception:
                    pass
            try:
                req = ExportTraceServiceRequest()
                req.ParseFromString(body)
                for rs in req.resource_spans:
                    scope_spans = list(rs.scope_spans)
                    if not scope_spans:
                        scope_spans = list(
                            getattr(rs, "instrumentation_library_spans", [])
                        )
                    for ss in scope_spans:
                        for span in ss.spans:
                            received_names.append(span.name)
            except Exception:
                pass
            resp = ExportTraceServiceResponse().SerializeToString()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            try:
                self.wfile.write(resp)
            except Exception:
                pass

        def log_message(self, *args):  # silence default logging
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, received_names, port


def _force_set_global_provider(provider):
    """Force `provider` to be the global OpenTelemetry TracerProvider.

    OpenTelemetry only allows the global provider to be set once per process;
    resetting the guard mirrors what the LangWatch SDK itself does and ensures
    spans emitted via the global tracer flow through our provider.
    """
    import opentelemetry.trace as ot
    from opentelemetry import trace
    from opentelemetry.util._once import Once

    ot._TRACER_PROVIDER = None  # type: ignore[attr-defined]
    ot._TRACER_PROVIDER_SET_ONCE = Once()  # type: ignore[attr-defined]
    trace.set_tracer_provider(provider)


@pytest.fixture(scope="session")
def pipeline_execution():
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    httpd, received_names, port = _make_collector()

    # Point LangWatch's exporter at the local collector BEFORE configuring it.
    os.environ["LANGWATCH_API_KEY"] = "sk-lw-test-key"
    os.environ["LANGWATCH_ENDPOINT"] = f"http://127.0.0.1:{port}"

    # Pre-existing global OpenTelemetry setup: a provider already exporting to
    # the team's existing backend (here captured in-memory so we can inspect it).
    memory_exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory_exporter))
    _force_set_global_provider(provider)
    assert trace.get_tracer_provider() is provider, (
        "Failed to install the pre-existing global TracerProvider for the test."
    )

    observability = importlib.import_module("observability")

    # Agent integrates LangWatch alongside the existing global provider.
    observability.configure_langwatch(provider)

    answer = observability.run_pipeline(QUERY)

    # Flush so the batching LangWatch exporter delivers to the collector.
    provider.force_flush()
    time.sleep(1.5)

    memory_names = [s.name for s in memory_exporter.get_finished_spans()]
    langwatch_names = list(received_names)

    result = {
        "answer": answer,
        "memory_names": memory_names,
        "langwatch_names": langwatch_names,
    }

    yield result

    try:
        httpd.shutdown()
    except Exception:
        pass
    try:
        provider.shutdown()
    except Exception:
        pass


def test_run_pipeline_returns_non_empty_answer(pipeline_execution):
    answer = pipeline_execution["answer"]
    assert isinstance(answer, str) and answer.strip(), (
        f"run_pipeline() should return a non-empty answer string, got: {answer!r}"
    )


def test_all_spans_reach_existing_exporter(pipeline_execution):
    """The pre-existing (non-LangWatch) exporter must still receive every span,
    proving the health-check/db spans were actually emitted and that
    configure_langwatch did not remove the existing span processor."""
    memory_names = set(pipeline_execution["memory_names"])
    missing = EXPECTED_ALL_SPANS - memory_names
    assert not missing, (
        "The pre-existing in-memory exporter is missing spans "
        f"{sorted(missing)}. Captured: {sorted(memory_names)}. Either the pipeline "
        "did not emit them, or the existing span processor was removed when "
        "attaching LangWatch."
    )


def test_excluded_spans_not_exported_to_langwatch(pipeline_execution):
    langwatch_names = set(pipeline_execution["langwatch_names"])
    leaked = EXCLUDED_FROM_LANGWATCH & langwatch_names
    assert not leaked, (
        f"Spans {sorted(leaked)} were exported to LangWatch but should have been "
        f"excluded. LangWatch received: {sorted(langwatch_names)}"
    )
    db_leaks = [n for n in langwatch_names if n.startswith("db.")]
    assert not db_leaks, (
        f"Database spans starting with 'db.' leaked to LangWatch: {db_leaks}"
    )


def test_included_spans_exported_to_langwatch(pipeline_execution):
    langwatch_names = set(pipeline_execution["langwatch_names"])
    missing = INCLUDED_IN_LANGWATCH - langwatch_names
    assert not missing, (
        f"Spans {sorted(missing)} should have been exported to LangWatch but were "
        f"not received. LangWatch received: {sorted(langwatch_names)}"
    )


def test_cli_smoke():
    """`python main.py \"<query>\"` should run the pipeline and print an answer."""
    httpd, _received, port = _make_collector()
    try:
        env = os.environ.copy()
        env["LANGWATCH_API_KEY"] = "sk-lw-test-key"
        env["LANGWATCH_ENDPOINT"] = f"http://127.0.0.1:{port}"
        env["OTEL_EXPORTER_OTLP_TRACES_TIMEOUT"] = "5"
        proc = subprocess.run(
            [sys.executable, "main.py", QUERY],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        assert proc.returncode == 0, (
            f"'python main.py' exited with {proc.returncode}. stderr: {proc.stderr}"
        )
        assert re.search(r"Answer:\s*\S", proc.stdout), (
            f"Expected a line like 'Answer: <text>' in stdout, got: {proc.stdout!r}"
        )
    finally:
        try:
            httpd.shutdown()
        except Exception:
            pass
