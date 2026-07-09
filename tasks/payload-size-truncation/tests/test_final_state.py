import gzip
import http.server
import importlib
import json
import os
import re
import sys
import threading
import time

import pytest

PROJECT_DIR = "/home/user/project"
CORPUS_PATH = os.path.join(PROJECT_DIR, "data", "documents.json")

# Make the agent's module importable for the pure-function unit test.
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Prefer the project virtualenv interpreter (created with uv) for the CLI run so
# that the LangWatch SDK is importable exactly as the agent installed it.
_VENV_PY = os.path.join(PROJECT_DIR, ".venv", "bin", "python")
PYTHON = _VENV_PY if os.path.exists(_VENV_PY) else sys.executable

COLLECTOR_LIMIT_BYTES = 1_000_000

# OTLP protobuf request type (provided transitively by the OTLP/HTTP exporter).
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (  # noqa: E402
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)


class _OTLPCollector:
    """A minimal in-process OTLP/HTTP collector that records exported spans."""

    def __init__(self):
        self.bodies = []  # decoded (uncompressed) protobuf request bodies
        self.requests = []  # parsed ExportTraceServiceRequest objects
        self.server = None
        self.thread = None
        self.port = None

    def start(self):
        collector = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):  # silence logging
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0) or 0)
                body = self.rfile.read(length)
                if (self.headers.get("Content-Encoding", "") or "").lower() == "gzip":
                    try:
                        body = gzip.decompress(body)
                    except OSError:
                        pass
                collector.bodies.append(body)
                try:
                    req = ExportTraceServiceRequest()
                    req.ParseFromString(body)
                    collector.requests.append(req)
                except Exception:
                    pass
                payload = ExportTraceServiceResponse().SerializeToString()
                self.send_response(200)
                self.send_header("Content-Type", "application/x-protobuf")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()

    def span_names(self):
        names = []
        for req in self.requests:
            for rs in req.resource_spans:
                for ss in rs.scope_spans:
                    for span in ss.spans:
                        names.append(span.name)
        return names

    def attribute_blob(self):
        """Concatenate every string attribute value across all exported spans/events."""
        parts = []

        def _drain(attributes):
            for kv in attributes:
                value = kv.value
                try:
                    if value.HasField("string_value"):
                        parts.append(value.string_value)
                    else:
                        parts.append(str(value))
                except Exception:
                    parts.append(str(value))

        for req in self.requests:
            for rs in req.resource_spans:
                for ss in rs.scope_spans:
                    for span in ss.spans:
                        _drain(span.attributes)
                        for event in span.events:
                            _drain(event.attributes)
        return "\n".join(parts)

    def total_payload_bytes(self):
        return sum(len(b) for b in self.bodies)

    def max_payload_bytes(self):
        return max((len(b) for b in self.bodies), default=0)


def _load_corpus():
    with open(CORPUS_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def collector():
    c = _OTLPCollector()
    c.start()
    yield c
    c.stop()


@pytest.fixture(scope="session")
def pipeline_run(collector):
    """Run the agent CLI once, exporting to the local collector, and capture stdout."""
    env = os.environ.copy()
    env["LANGWATCH_API_KEY"] = "sk-lw-test-key"
    env["LANGWATCH_ENDPOINT"] = f"http://127.0.0.1:{collector.port}"
    result = subprocess_run(
        [PYTHON, "main.py", "Summarize the onboarding documents"],
        cwd=PROJECT_DIR,
        env=env,
    )
    # Allow any late/batched export to arrive at the collector.
    for _ in range(20):
        if collector.requests:
            break
        time.sleep(0.5)
    return result


def subprocess_run(cmd, cwd, env):
    import subprocess

    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


# ---------------------------------------------------------------------------
# 1. Pure-function correctness of truncate_contexts
# ---------------------------------------------------------------------------
def test_truncate_contexts_behaviour():
    rag_payload = importlib.import_module("rag_payload")

    content_a = "HEAD_A " + ("x" * 100000) + " TAIL_A"
    content_b = "HEAD_B " + ("y" * 100000) + " TAIL_B"
    content_c = "tiny content C"
    docs = [
        {"document_id": "A", "chunk_id": "a0", "content": content_a},
        {"document_id": "B", "chunk_id": "b0", "content": content_b},
        {"document_id": "C", "chunk_id": "c0", "content": content_c},
    ]

    result = rag_payload.truncate_contexts(docs, max_total_bytes=90000, max_document_bytes=25000)

    assert isinstance(result, list), "truncate_contexts must return a list."
    assert len(result) == 3, "truncate_contexts must return one entry per input document."

    for original, entry in zip(docs, result):
        assert entry["document_id"] == original["document_id"], "document_id must be preserved."
        assert entry["chunk_id"] == original["chunk_id"], "chunk_id must be preserved."
        assert "content" in entry, "Each entry must expose a 'content' field."
        assert "original_bytes" in entry, "Each entry must record 'original_bytes'."
        assert entry["original_bytes"] == len(
            original["content"].encode("utf-8")
        ), "original_bytes must equal the UTF-8 byte length of the original content."
        assert (
            len(entry["content"].encode("utf-8")) <= 25000
        ), "Each content must respect the per-document byte cap."

    # Oversized documents: head retained, marker present, tail dropped.
    assert result[0]["content"].startswith("HEAD_A"), "The beginning of document A must be retained."
    assert "[truncated]" in result[0]["content"], "Truncated content must contain the marker."
    assert "TAIL_A" not in result[0]["content"], "The tail of the oversized document A must be dropped."
    assert result[1]["content"].startswith("HEAD_B"), "The beginning of document B must be retained."
    assert "[truncated]" in result[1]["content"], "Truncated content must contain the marker."
    assert "TAIL_B" not in result[1]["content"], "The tail of the oversized document B must be dropped."

    # Small document: unchanged, no marker.
    assert result[2]["content"] == content_c, "Content within the cap must be returned unchanged."
    assert "[truncated]" not in result[2]["content"], "Untruncated content must not carry the marker."

    total = len(json.dumps(result).encode("utf-8"))
    assert total <= 90000, f"Serialized result must respect max_total_bytes (got {total})."


# ---------------------------------------------------------------------------
# 2. CLI smoke test
# ---------------------------------------------------------------------------
def test_cli_prints_answer(pipeline_run):
    result = pipeline_run
    assert result.returncode == 0, f"CLI exited non-zero. stderr:\n{result.stderr}"
    match = re.search(r"Answer:\s*(\S.*)", result.stdout)
    assert match is not None, f"stdout must contain a non-empty 'Answer: <text>' line. stdout:\n{result.stdout}"
    assert match.group(1).strip(), "The answer text must be non-empty."


# ---------------------------------------------------------------------------
# 3. Trace structure preserved
# ---------------------------------------------------------------------------
def test_trace_structure_exported(pipeline_run, collector):
    names = collector.span_names()
    assert names, f"The collector received no spans. CLI stderr:\n{pipeline_run.stderr}"
    for expected in ("rag_pipeline", "rag.retrieve", "llm.generate"):
        assert expected in names, f"Expected span '{expected}' in exported trace, got: {sorted(set(names))}"


# ---------------------------------------------------------------------------
# 4. Exported payload is under the collector limit
# ---------------------------------------------------------------------------
def test_payload_under_collector_limit(pipeline_run, collector):
    assert collector.requests, f"No OTLP payload captured. CLI stderr:\n{pipeline_run.stderr}"
    raw_total = sum(len(item["content"].encode("utf-8")) for item in _load_corpus())
    assert raw_total > COLLECTOR_LIMIT_BYTES, (
        "Sanity check: the raw corpus must exceed the collector limit so a small "
        f"exported payload proves truncation (raw={raw_total})."
    )
    assert collector.max_payload_bytes() < COLLECTOR_LIMIT_BYTES, (
        "Each exported OTLP body must be under the 1MB collector limit "
        f"(max body={collector.max_payload_bytes()})."
    )
    assert collector.total_payload_bytes() < 600_000, (
        "The exported trace payload must be far below the limit after truncation "
        f"(total={collector.total_payload_bytes()})."
    )


# ---------------------------------------------------------------------------
# 5. Essential identifiers retained + marker present
# ---------------------------------------------------------------------------
def test_document_ids_and_marker_retained(pipeline_run, collector):
    blob = collector.attribute_blob()
    assert blob, f"No span attributes captured. CLI stderr:\n{pipeline_run.stderr}"
    for item in _load_corpus():
        assert item["document_id"] in blob, (
            f"Essential identifier '{item['document_id']}' must be retained in the exported span data."
        )
    assert "[truncated]" in blob, "The truncation marker '[truncated]' must appear in the exported span data."


# ---------------------------------------------------------------------------
# 6. Heads retained, tails dropped
# ---------------------------------------------------------------------------
def test_heads_retained_tails_dropped(pipeline_run, collector):
    blob = collector.attribute_blob()
    corpus = _load_corpus()
    for i in range(len(corpus)):
        head_token = f"HEAD_CANARY_{i}"
        tail_token = f"TAIL_CANARY_{i}"
        assert head_token in blob, f"The head token '{head_token}' must be retained in the exported span data."
        assert tail_token not in blob, (
            f"The tail token '{tail_token}' must be truncated away and absent from the exported span data."
        )
