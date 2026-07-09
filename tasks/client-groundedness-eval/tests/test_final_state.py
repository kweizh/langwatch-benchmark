import gzip
import importlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

PROJECT_DIR = "/home/user/project"
QUERY = "What is LangWatch observability?"
EVAL_NAME = "groundedness"

EXPECTED_SPANS = {"rag_pipeline", "retrieve_context", "generate_answer"}

# Ensure a default API key exists even before the fixture runs, in case the
# agent's module touches langwatch at import time.
os.environ.setdefault("LANGWATCH_API_KEY", "sk-lw-test-key")

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)


# ---------------------------------------------------------------------------
# Independent reference implementation of the groundedness metric.
# The verifier NEVER trusts the agent's compute_groundedness for expected values.
# ---------------------------------------------------------------------------
STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "of", "to", "in", "on",
    "and", "or", "for", "with", "as", "at", "by", "it", "its", "this",
    "that", "these", "those", "be", "from",
}


def _tokens(text):
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS}


def reference_groundedness(answer, contexts):
    answer_tokens = _tokens(answer)
    context_tokens = _tokens(" ".join(contexts))
    if not answer_tokens:
        score = 0.0
    else:
        score = round(len(answer_tokens & context_tokens) / len(answer_tokens), 4)
    if score >= 0.75:
        passed, label = True, "grounded"
    elif score >= 0.4:
        passed, label = False, "weakly_grounded"
    else:
        passed, label = False, "hallucinated"
    return {"score": score, "passed": passed, "label": label}


# ---------------------------------------------------------------------------
# OTLP protobuf helpers
# ---------------------------------------------------------------------------
def _anyvalue_to_py(value):
    """Extract a Python scalar from an OTLP AnyValue message."""
    if value.HasField("string_value"):
        return value.string_value
    if value.HasField("bool_value"):
        return value.bool_value
    if value.HasField("int_value"):
        return value.int_value
    if value.HasField("double_value"):
        return value.double_value
    return None


def _attrs_to_dict(attributes):
    out = {}
    for kv in attributes:
        out[kv.key] = _anyvalue_to_py(kv.value)
    return out


def _make_collector():
    """Start a real local OTLP/HTTP collector that stands in for LangWatch.

    It decodes the OTLP protobuf payload and records, for every received span,
    its name, span id, parent span id, attributes and events. This is a genuine
    HTTP endpoint, not a mock of any LangWatch or OpenTelemetry dependency.
    """
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceRequest,
        ExportTraceServiceResponse,
    )

    received_spans = []

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
                            events = []
                            for ev in span.events:
                                events.append(
                                    {
                                        "name": ev.name,
                                        "attributes": _attrs_to_dict(ev.attributes),
                                    }
                                )
                            received_spans.append(
                                {
                                    "name": span.name,
                                    "span_id": span.span_id.hex(),
                                    "parent_span_id": span.parent_span_id.hex(),
                                    "attributes": _attrs_to_dict(span.attributes),
                                    "events": events,
                                }
                            )
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
    return httpd, received_spans, port


@pytest.fixture(scope="session")
def pipeline_execution():
    httpd, received_spans, port = _make_collector()

    # Point LangWatch's exporter at the local collector before the agent's code
    # initializes the SDK.
    os.environ["LANGWATCH_API_KEY"] = "sk-lw-test-key"
    os.environ["LANGWATCH_ENDPOINT"] = f"http://127.0.0.1:{port}"

    pipeline = importlib.import_module("pipeline")

    contexts = pipeline.retrieve(QUERY)
    answer = pipeline.run_pipeline(QUERY)

    # Flush the (LangWatch-managed) global provider so the batching exporter
    # delivers spans to the collector.
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush()
    except Exception:
        pass
    time.sleep(1.5)

    result = {
        "answer": answer,
        "contexts": contexts,
        "spans": list(received_spans),
    }

    yield result

    try:
        httpd.shutdown()
    except Exception:
        pass


def _find_spans(spans, name):
    return [s for s in spans if s["name"] == name]


def _eval_event(span):
    for ev in span["events"]:
        if ev["name"] == "langwatch.evaluation.custom":
            return ev
    return None


# ---------------------------------------------------------------------------
# 1. CLI smoke test
# ---------------------------------------------------------------------------
def test_cli_smoke():
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
        assert re.search(r"Groundedness:\s*\S", proc.stdout), (
            "Expected a line like 'Groundedness: <score> <label>' in stdout, "
            f"got: {proc.stdout!r}"
        )
    finally:
        try:
            httpd.shutdown()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 2. Scoring logic unit tests (independent of LangWatch)
# ---------------------------------------------------------------------------
SCORING_CASES = [
    # (answer, contexts, expected_score, expected_passed, expected_label)
    (
        "LangWatch observability platform",
        ["LangWatch is an observability platform for LLM applications."],
        1.0,
        True,
        "grounded",
    ),
    (
        "langwatch tracing rockets bananas",
        ["langwatch provides tracing dashboards"],
        0.5,
        False,
        "weakly_grounded",
    ),
    (
        "unicorns dragons wizards langwatch",
        ["langwatch observability"],
        0.25,
        False,
        "hallucinated",
    ),
    (
        "the is of and",
        ["langwatch observability"],
        0.0,
        False,
        "hallucinated",
    ),
]


@pytest.mark.parametrize(
    "answer,contexts,exp_score,exp_passed,exp_label", SCORING_CASES
)
def test_compute_groundedness_matches_reference(
    answer, contexts, exp_score, exp_passed, exp_label
):
    pipeline = importlib.import_module("pipeline")
    result = pipeline.compute_groundedness(answer, contexts)

    assert isinstance(result, dict), (
        f"compute_groundedness must return a dict, got {type(result)!r}"
    )
    for key in ("score", "passed", "label", "details"):
        assert key in result, f"compute_groundedness result missing key '{key}': {result}"

    ref = reference_groundedness(answer, contexts)
    # Sanity-check the hand-computed expectations against the reference impl.
    assert ref == {"score": exp_score, "passed": exp_passed, "label": exp_label}

    assert abs(float(result["score"]) - exp_score) < 1e-6, (
        f"Wrong score for answer={answer!r}, contexts={contexts!r}: "
        f"expected {exp_score}, got {result['score']}"
    )
    assert bool(result["passed"]) is exp_passed, (
        f"Wrong passed for answer={answer!r}: expected {exp_passed}, got {result['passed']}"
    )
    assert result["label"] == exp_label, (
        f"Wrong label for answer={answer!r}: expected {exp_label!r}, got {result['label']!r}"
    )
    assert isinstance(result["details"], str) and result["details"].strip(), (
        f"'details' must be a non-empty string, got {result['details']!r}"
    )


# ---------------------------------------------------------------------------
# 3. Deterministic retrieval
# ---------------------------------------------------------------------------
def test_retrieve_is_deterministic_and_non_empty():
    pipeline = importlib.import_module("pipeline")
    first = pipeline.retrieve(QUERY)
    second = pipeline.retrieve(QUERY)
    assert isinstance(first, list) and first, (
        f"retrieve() must return a non-empty list, got {first!r}"
    )
    assert all(isinstance(x, str) for x in first), (
        f"retrieve() must return a list of strings, got {first!r}"
    )
    assert first == second, (
        f"retrieve() must be deterministic. First: {first!r}, second: {second!r}"
    )


# ---------------------------------------------------------------------------
# 4. Pipeline returns an answer and emits spans
# ---------------------------------------------------------------------------
def test_run_pipeline_returns_non_empty_answer(pipeline_execution):
    answer = pipeline_execution["answer"]
    assert isinstance(answer, str) and answer.strip(), (
        f"run_pipeline() should return a non-empty answer string, got: {answer!r}"
    )


def test_expected_spans_emitted(pipeline_execution):
    names = {s["name"] for s in pipeline_execution["spans"]}
    missing = EXPECTED_SPANS - names
    assert not missing, (
        f"Expected spans {sorted(missing)} were not exported. Received: {sorted(names)}"
    )


# ---------------------------------------------------------------------------
# 5. Evaluation is attached to the generate_answer span
# ---------------------------------------------------------------------------
def test_evaluation_attached_to_generate_answer_span(pipeline_execution):
    spans = pipeline_execution["spans"]
    gen_spans = _find_spans(spans, "generate_answer")
    assert gen_spans, "No 'generate_answer' span was exported."
    gen = gen_spans[0]

    # Signal A: the custom evaluation event lives on the generate_answer span.
    event = _eval_event(gen)
    assert event is not None, (
        "The 'generate_answer' span carries no 'langwatch.evaluation.custom' event; "
        "the evaluation was not attached to the answer span. Events found: "
        f"{[e['name'] for e in gen['events']]}"
    )
    raw = event["attributes"].get("json_encoded_event")
    assert raw, "The evaluation event has no 'json_encoded_event' attribute."
    payload = json.loads(raw)
    assert payload.get("name") == EVAL_NAME, (
        f"Evaluation name must be '{EVAL_NAME}', got {payload.get('name')!r}"
    )

    # Signal B: the exported evaluation child span is parented to generate_answer.
    eval_spans = _find_spans(spans, EVAL_NAME)
    assert eval_spans, (
        f"No exported child span named '{EVAL_NAME}' (type=evaluation) was found."
    )
    parented = [e for e in eval_spans if e["parent_span_id"] == gen["span_id"]]
    assert parented, (
        f"The '{EVAL_NAME}' evaluation span is not a child of 'generate_answer'. "
        f"generate_answer span_id={gen['span_id']}, "
        f"evaluation parents={[e['parent_span_id'] for e in eval_spans]}"
    )
    assert parented[0]["attributes"].get("langwatch.span.type") == "evaluation", (
        "The evaluation span's 'langwatch.span.type' attribute must be 'evaluation', "
        f"got {parented[0]['attributes'].get('langwatch.span.type')!r}"
    )

    # The evaluation must NOT be attached to the root or retrieval span.
    for other_name in ("rag_pipeline", "retrieve_context"):
        for s in _find_spans(spans, other_name):
            assert _eval_event(s) is None, (
                f"The groundedness evaluation event was wrongly attached to the "
                f"'{other_name}' span; it must be on 'generate_answer'."
            )


# ---------------------------------------------------------------------------
# 6. Logged evaluation fields equal the independently computed groundedness
# ---------------------------------------------------------------------------
def test_logged_evaluation_fields_match_reference(pipeline_execution):
    answer = pipeline_execution["answer"]
    contexts = pipeline_execution["contexts"]
    expected = reference_groundedness(answer, contexts)

    spans = pipeline_execution["spans"]
    gen = _find_spans(spans, "generate_answer")[0]
    event = _eval_event(gen)
    assert event is not None, "Missing evaluation event on 'generate_answer' span."
    payload = json.loads(event["attributes"]["json_encoded_event"])

    assert bool(payload.get("passed")) is expected["passed"], (
        f"Logged 'passed' ({payload.get('passed')}) does not match the "
        f"independently computed value ({expected['passed']}) for answer={answer!r}."
    )
    assert payload.get("label") == expected["label"], (
        f"Logged 'label' ({payload.get('label')!r}) does not match the "
        f"computed label ({expected['label']!r}) for answer={answer!r}."
    )
    assert payload.get("score") is not None, "Logged evaluation has no 'score'."
    assert abs(float(payload["score"]) - expected["score"]) < 1e-6, (
        f"Logged 'score' ({payload.get('score')}) does not match the computed "
        f"groundedness ({expected['score']}) for answer={answer!r}, contexts={contexts!r}."
    )
    assert isinstance(payload.get("details"), str) and payload["details"].strip(), (
        f"Logged evaluation 'details' must be a non-empty string, got {payload.get('details')!r}"
    )
