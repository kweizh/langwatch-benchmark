import gzip
import http.server
import importlib
import json
import os
import re
import socket
import sys
import threading
import time

import pytest

PROJECT_DIR = "/home/user/project"

# Test data (derived from the guardrail regex spec, not magic numbers).
PII_QUERY = "Please email my report to jane.doe@example.com right away"
PII_SUBSTRING = "jane.doe@example.com"
CLEAN_QUERY = "What are your customer support hours on weekends"

# ---------------------------------------------------------------------------
# Independent reference implementation of the PII guardrail.
# ---------------------------------------------------------------------------
_REFERENCE_PATTERNS = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", re.IGNORECASE),
    "ssn": re.compile(r"\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b"),
    "phone": re.compile(r"\b[0-9]{3}-[0-9]{3}-[0-9]{4}\b"),
    "credit_card": re.compile(r"\b[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{4}\b"),
}


def reference_screen(text):
    categories = set()
    matched = set()
    for name, pattern in _REFERENCE_PATTERNS.items():
        for hit in pattern.findall(text):
            categories.add(name)
            matched.add(hit)
    return {
        "passed": len(categories) == 0,
        "categories": sorted(categories),
        "matched": sorted(matched),
    }


# ---------------------------------------------------------------------------
# Local in-process OTLP/HTTP collector.
# ---------------------------------------------------------------------------
RECEIVED_SPANS = []
_SPANS_LOCK = threading.Lock()


def _reset_spans():
    with _SPANS_LOCK:
        RECEIVED_SPANS.clear()


def _snapshot_spans():
    with _SPANS_LOCK:
        return list(RECEIVED_SPANS)


def _anyvalue(value):
    if value.HasField("string_value"):
        return value.string_value
    if value.HasField("bool_value"):
        return value.bool_value
    if value.HasField("int_value"):
        return value.int_value
    if value.HasField("double_value"):
        return value.double_value
    if value.HasField("array_value"):
        return [_anyvalue(v) for v in value.array_value.values]
    if value.HasField("kvlist_value"):
        return {kv.key: _anyvalue(kv.value) for kv in value.kvlist_value.values}
    if value.HasField("bytes_value"):
        return value.bytes_value
    return None


def _record_request(body):
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceRequest,
    )

    req = ExportTraceServiceRequest()
    req.ParseFromString(body)
    parsed = []
    for resource_spans in req.resource_spans:
        for scope_spans in resource_spans.scope_spans:
            for span in scope_spans.spans:
                attributes = {kv.key: _anyvalue(kv.value) for kv in span.attributes}
                events = []
                for event in span.events:
                    events.append(
                        {
                            "name": event.name,
                            "attributes": {
                                kv.key: _anyvalue(kv.value) for kv in event.attributes
                            },
                        }
                    )
                parsed.append(
                    {
                        "name": span.name,
                        "span_id": span.span_id.hex(),
                        "parent_span_id": span.parent_span_id.hex(),
                        "attributes": attributes,
                        "events": events,
                    }
                )
    with _SPANS_LOCK:
        RECEIVED_SPANS.extend(parsed)


class _CollectorHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence
        pass

    def _write_ok(self):
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
            ExportTraceServiceResponse,
        )

        payload = ExportTraceServiceResponse().SerializeToString()
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        if self.headers.get("Content-Encoding", "").lower() == "gzip":
            try:
                body = gzip.decompress(body)
            except Exception:
                pass
        try:
            _record_request(body)
        except Exception as exc:  # pragma: no cover - still ack to avoid retries storm
            print(f"collector failed to parse body: {exc}")
        self._write_ok()


@pytest.fixture(scope="session")
def collector():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _CollectorHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # Wait for the socket to accept connections.
    for _ in range(50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.1)

    yield f"http://127.0.0.1:{port}"

    server.shutdown()
    server.server_close()


@pytest.fixture(scope="session")
def agent(collector):
    os.environ["LANGWATCH_API_KEY"] = "sk-lw-test-key"
    os.environ["LANGWATCH_ENDPOINT"] = collector
    if PROJECT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_DIR)
    module = importlib.import_module("agent")
    return module


def _flush():
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush()
    except Exception:
        pass
    time.sleep(1.0)


def _find_span(spans, name):
    for span in spans:
        if span["name"] == name:
            return span
    return None


def _find_guardrail_child(spans, parent_span_id, name="pii_guardrail"):
    for span in spans:
        if span["name"] == name and span["parent_span_id"] == parent_span_id:
            return span
    return None


def _extract_logged_evaluation(spans, span_name="generate_answer", eval_name="pii_guardrail"):
    """Decode the guardrail result recorded via add_evaluation from the
    langwatch.evaluation.custom span event."""
    for span in spans:
        if span["name"] != span_name:
            continue
        for event in span["events"]:
            encoded = event["attributes"].get("json_encoded_event")
            if not encoded:
                continue
            try:
                obj = json.loads(encoded)
            except (TypeError, ValueError):
                continue
            if isinstance(obj, dict) and obj.get("name") == eval_name:
                return obj
    return None


# ---------------------------------------------------------------------------
# 1. CLI blocked path
# ---------------------------------------------------------------------------
def _run_cli(agent_env_query):
    import subprocess

    env = os.environ.copy()
    return subprocess.run(
        [sys.executable, "main.py", agent_env_query],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        env=env,
    )


def test_cli_blocked_path(agent):
    result = _run_cli(PII_QUERY)
    assert result.returncode == 0, f"CLI exited non-zero: {result.stderr}"
    stdout = result.stdout
    assert re.search(r"^Decision:\s*blocked\s*$", stdout, re.MULTILINE), (
        f"Expected 'Decision: blocked' for a PII query. stdout=\n{stdout}"
    )
    assert re.search(r"^Guardrail:\s*failed\s*$", stdout, re.MULTILINE), (
        f"Expected 'Guardrail: failed' for a PII query. stdout=\n{stdout}"
    )
    response_match = re.search(r"^Response:\s*(.+)$", stdout, re.MULTILINE)
    assert response_match, f"Expected a 'Response:' line. stdout=\n{stdout}"
    response_text = response_match.group(1).strip()
    assert response_text, "Blocked response text must be non-empty."
    assert PII_SUBSTRING not in response_text, (
        f"Blocked response leaked the PII substring '{PII_SUBSTRING}': {response_text}"
    )


def test_cli_allowed_path(agent):
    result = _run_cli(CLEAN_QUERY)
    assert result.returncode == 0, f"CLI exited non-zero: {result.stderr}"
    stdout = result.stdout
    assert re.search(r"^Decision:\s*allowed\s*$", stdout, re.MULTILINE), (
        f"Expected 'Decision: allowed' for a clean query. stdout=\n{stdout}"
    )
    assert re.search(r"^Guardrail:\s*passed\s*$", stdout, re.MULTILINE), (
        f"Expected 'Guardrail: passed' for a clean query. stdout=\n{stdout}"
    )
    response_match = re.search(r"^Response:\s*(.+)$", stdout, re.MULTILINE)
    assert response_match, f"Expected a 'Response:' line. stdout=\n{stdout}"
    assert response_match.group(1).strip(), "Allowed response text must be non-empty."


# ---------------------------------------------------------------------------
# 2. Guardrail scoring unit tests (independent of LangWatch)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected_categories",
    [
        ("contact me at bob@test.io", ["email"]),
        ("my ssn is 123-45-6789", ["ssn"]),
        ("call 415-555-0100 tomorrow", ["phone"]),
        ("card 4111-1111-1111-1111 on file", ["credit_card"]),
        ("email a@b.co and card 4111-1111-1111-1111", ["credit_card", "email"]),
        ("the weather is sunny today", []),
    ],
)
def test_screen_output_matches_reference(agent, text, expected_categories):
    result = agent.screen_output(text)
    reference = reference_screen(text)
    assert sorted(result["categories"]) == expected_categories, (
        f"categories mismatch for {text!r}: got {result['categories']}"
    )
    assert sorted(result["categories"]) == reference["categories"], (
        f"categories disagree with reference for {text!r}"
    )
    assert sorted(result["matched"]) == reference["matched"], (
        f"matched substrings disagree with reference for {text!r}"
    )
    assert result["passed"] is reference["passed"], (
        f"passed disagrees with reference for {text!r}"
    )
    assert isinstance(result["details"], str) and result["details"].strip(), (
        f"details must be a non-empty string for {text!r}"
    )
    if expected_categories:
        lowered = result["details"].lower()
        for category in expected_categories:
            assert category in lowered, (
                f"details for {text!r} should mention offending category '{category}': "
                f"{result['details']}"
            )
    else:
        assert re.search(r"no\b|clean|none", result["details"], re.IGNORECASE), (
            f"details for a clean input should indicate no PII: {result['details']}"
        )


def test_generate_is_deterministic(agent):
    first = agent.generate(CLEAN_QUERY)
    second = agent.generate(CLEAN_QUERY)
    assert isinstance(first, str) and first.strip(), "generate must return a non-empty string."
    assert first == second, "generate must be deterministic for the same query."


# ---------------------------------------------------------------------------
# 3. Blocked path enforces the fallback and records a failing guardrail
# ---------------------------------------------------------------------------
def test_run_agent_blocked_path(agent):
    _flush()
    _reset_spans()

    result = agent.run_agent(PII_QUERY)
    _flush()

    assert result["decision"] == "blocked", f"Expected blocked decision, got {result}"
    assert result["response"] == agent.SAFE_FALLBACK, (
        "Blocked response must be exactly SAFE_FALLBACK."
    )

    reference = reference_screen(agent.generate(PII_QUERY))
    assert reference["passed"] is False, (
        "Test precondition failed: generate(PII_QUERY) must contain PII."
    )
    for pii in reference["matched"]:
        assert pii not in agent.SAFE_FALLBACK, (
            f"SAFE_FALLBACK must not contain PII substring '{pii}'."
        )

    assert result["guardrail"]["passed"] is False, "Guardrail should have failed on PII output."
    assert result["guardrail"]["passed"] == reference["passed"], (
        "run_agent guardrail verdict disagrees with the reference implementation."
    )

    spans = _snapshot_spans()
    assert _find_span(spans, "guardrail_pipeline") is not None, (
        "Expected an exported span named 'guardrail_pipeline'."
    )
    generate_span = _find_span(spans, "generate_answer")
    assert generate_span is not None, "Expected an exported span named 'generate_answer'."

    guardrail_span = _find_guardrail_child(spans, generate_span["span_id"])
    assert guardrail_span is not None, (
        "Expected a 'pii_guardrail' child span of the 'generate_answer' span."
    )
    assert guardrail_span["attributes"].get("langwatch.span.type") == "guardrail", (
        "The pii_guardrail span must have langwatch.span.type == 'guardrail' "
        f"(got {guardrail_span['attributes'].get('langwatch.span.type')})."
    )

    logged = _extract_logged_evaluation(spans)
    assert logged is not None, (
        "Expected a langwatch.evaluation.custom event named 'pii_guardrail' on generate_answer."
    )
    assert logged.get("passed") is False, (
        f"The recorded guardrail verdict should be a failure, got {logged.get('passed')}."
    )


# ---------------------------------------------------------------------------
# 4. Allowed path returns the model output and records a passing guardrail
# ---------------------------------------------------------------------------
def test_run_agent_allowed_path(agent):
    _flush()
    _reset_spans()

    result = agent.run_agent(CLEAN_QUERY)
    _flush()

    assert result["decision"] == "allowed", f"Expected allowed decision, got {result}"
    expected_answer = agent.generate(CLEAN_QUERY)
    assert result["response"] == expected_answer, (
        "Allowed response must equal the raw model output from generate()."
    )
    assert result["response"].strip(), "Allowed response must be non-empty."
    assert result["guardrail"]["passed"] is True, "Guardrail should pass on clean output."

    spans = _snapshot_spans()
    generate_span = _find_span(spans, "generate_answer")
    assert generate_span is not None, "Expected an exported span named 'generate_answer'."

    guardrail_span = _find_guardrail_child(spans, generate_span["span_id"])
    assert guardrail_span is not None, (
        "Expected a 'pii_guardrail' child span of the 'generate_answer' span."
    )
    assert guardrail_span["attributes"].get("langwatch.span.type") == "guardrail", (
        "The pii_guardrail span must have langwatch.span.type == 'guardrail'."
    )

    logged = _extract_logged_evaluation(spans)
    assert logged is not None, (
        "Expected a langwatch.evaluation.custom event named 'pii_guardrail' on generate_answer."
    )
    assert logged.get("passed") is True, (
        f"The recorded guardrail verdict should be a pass, got {logged.get('passed')}."
    )
