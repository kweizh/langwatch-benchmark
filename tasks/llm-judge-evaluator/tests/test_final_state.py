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
QUESTION = "How do I attach an evaluation to a LangWatch trace?"
EVAL_NAME = "answer-quality-judge"
JUDGE_RESULT_PATH = os.path.join(PROJECT_DIR, "judge_result.json")

EXPECTED_SPANS = {"qa_pipeline", "retrieve_context", "generate_answer"}

# Per-run fixed verdicts the local LangWatch stand-in returns. They are distinct
# so we can prove the pipeline records the evaluator's response (verdict B) and
# not a hardcoded/local value (verdict A).
VERDICT_A = {
    "status": "processed",
    "passed": True,
    "score": 0.86,
    "label": "pass",
    "details": "Answer is faithful to the retrieved context and addresses the question.",
}
VERDICT_B = {
    "status": "processed",
    "passed": False,
    "score": 0.12,
    "label": "fail",
    "details": "Answer is not supported by the retrieved context.",
}

# Ensure a default API key exists even before the fixture runs, in case the
# agent's module touches langwatch at import time.
os.environ.setdefault("LANGWATCH_API_KEY", "sk-lw-test-key")

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)


# ---------------------------------------------------------------------------
# OTLP protobuf helpers
# ---------------------------------------------------------------------------
def _anyvalue_to_py(value):
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


def _make_server():
    """Start one local HTTP endpoint standing in for LangWatch.

    It serves two routes used by the SDK:
      * ``POST /api/evaluations/{slug}/evaluate`` — records the request and
        replies with a controllable, EvaluationResultModel-shaped verdict.
      * ``POST /api/otel/v1/traces`` — decodes the OTLP protobuf export and
        records every span (name, ids, attributes).
    This is a genuine HTTP server, not a mock of any LangWatch/OTel dependency.
    """
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceRequest,
        ExportTraceServiceResponse,
    )

    state = {
        "eval_requests": [],
        "spans": [],
        "verdict": dict(VERDICT_A),
    }

    class Handler(BaseHTTPRequestHandler):
        def _read_body(self):
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""
            if self.headers.get("Content-Encoding") == "gzip" and body:
                try:
                    body = gzip.decompress(body)
                except Exception:
                    pass
            return body

        def do_GET(self):  # noqa: N802
            payload = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except Exception:
                pass

        def do_POST(self):  # noqa: N802
            body = self._read_body()
            path = self.path

            if "evaluate" in path:
                try:
                    parsed = json.loads(body.decode("utf-8")) if body else {}
                except Exception:
                    parsed = {}
                state["eval_requests"].append({"path": path, "body": parsed})
                payload = json.dumps(state["verdict"]).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                try:
                    self.wfile.write(payload)
                except Exception:
                    pass
                return

            if "traces" in path:
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
                                state["spans"].append(
                                    {
                                        "name": span.name,
                                        "span_id": span.span_id.hex(),
                                        "parent_span_id": span.parent_span_id.hex(),
                                        "trace_id": span.trace_id.hex(),
                                        "attributes": _attrs_to_dict(span.attributes),
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
                return

            payload = b"{}"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except Exception:
                pass

        def log_message(self, *args):  # silence default logging
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, state, port


def _flush_spans():
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush()
    except Exception:
        pass
    time.sleep(1.5)


def _read_judge_result():
    if not os.path.isfile(JUDGE_RESULT_PATH):
        return None
    with open(JUDGE_RESULT_PATH) as f:
        return json.load(f)


def _find_spans(spans, name):
    return [s for s in spans if s["name"] == name]


def _eval_requests(state):
    return [r for r in state["eval_requests"] if "evaluate" in r["path"]]


@pytest.fixture(scope="session")
def runs():
    """Run the agent's pipeline twice against distinct evaluator verdicts."""
    httpd, state, port = _make_server()

    os.environ["LANGWATCH_API_KEY"] = "sk-lw-test-key"
    os.environ["LANGWATCH_ENDPOINT"] = f"http://127.0.0.1:{port}"

    qa_pipeline = importlib.import_module("qa_pipeline")

    def _do_run(verdict):
        state["verdict"] = dict(verdict)
        state["eval_requests"].clear()
        state["spans"].clear()
        if os.path.isfile(JUDGE_RESULT_PATH):
            try:
                os.remove(JUDGE_RESULT_PATH)
            except Exception:
                pass
        result = qa_pipeline.run_pipeline(QUESTION)
        _flush_spans()
        return {
            "result": result,
            "eval_requests": [dict(r) for r in _eval_requests(state)],
            "spans": list(state["spans"]),
            "judge_json": _read_judge_result(),
        }

    contexts_1 = qa_pipeline.retrieve(QUESTION)
    contexts_2 = qa_pipeline.retrieve(QUESTION)

    run_a = _do_run(VERDICT_A)
    run_b = _do_run(VERDICT_B)

    data = {
        "run_a": run_a,
        "run_b": run_b,
        "contexts_1": contexts_1,
        "contexts_2": contexts_2,
    }

    yield data

    try:
        httpd.shutdown()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 1. CLI smoke test
# ---------------------------------------------------------------------------
def test_cli_smoke():
    httpd, _state, port = _make_server()
    try:
        env = os.environ.copy()
        env["LANGWATCH_API_KEY"] = "sk-lw-test-key"
        env["LANGWATCH_ENDPOINT"] = f"http://127.0.0.1:{port}"
        env["OTEL_EXPORTER_OTLP_TRACES_TIMEOUT"] = "5"
        proc = subprocess.run(
            [sys.executable, "main.py", QUESTION],
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
        assert re.search(r"Judgement:\s*\S", proc.stdout), (
            "Expected a line like 'Judgement: <passed> <score> <label>' in stdout, "
            f"got: {proc.stdout!r}"
        )
    finally:
        try:
            httpd.shutdown()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 2. Deterministic retrieval
# ---------------------------------------------------------------------------
def test_retrieve_is_deterministic_and_non_empty(runs):
    first = runs["contexts_1"]
    second = runs["contexts_2"]
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
# 3. Pipeline returns an answer + verdict A
# ---------------------------------------------------------------------------
def test_run_pipeline_returns_answer_and_verdict(runs):
    result = runs["run_a"]["result"]
    assert isinstance(result, dict), (
        f"run_pipeline() must return a dict, got {type(result)!r}"
    )
    answer = result.get("answer")
    assert isinstance(answer, str) and answer.strip(), (
        f"run_pipeline() result must contain a non-empty 'answer' string, got: {answer!r}"
    )
    judgement = result.get("judgement")
    assert isinstance(judgement, dict), (
        f"run_pipeline() result must contain a 'judgement' dict, got: {judgement!r}"
    )
    assert bool(judgement.get("passed")) is VERDICT_A["passed"], (
        f"Returned judgement 'passed' should equal the evaluator verdict "
        f"{VERDICT_A['passed']}, got {judgement.get('passed')!r}"
    )
    assert abs(float(judgement.get("score")) - VERDICT_A["score"]) < 1e-6, (
        f"Returned judgement 'score' should equal {VERDICT_A['score']}, "
        f"got {judgement.get('score')!r}"
    )
    assert judgement.get("label") == VERDICT_A["label"], (
        f"Returned judgement 'label' should equal {VERDICT_A['label']!r}, "
        f"got {judgement.get('label')!r}"
    )
    assert judgement.get("details") == VERDICT_A["details"], (
        "Returned judgement 'details' should equal the evaluator's returned details."
    )


# ---------------------------------------------------------------------------
# 4. Evaluator was invoked correctly
# ---------------------------------------------------------------------------
def test_llm_judge_evaluator_invoked(runs):
    reqs = runs["run_a"]["eval_requests"]
    assert len(reqs) == 1, (
        f"Expected exactly one evaluator call to the evaluations API, got {len(reqs)}: "
        f"{[r['path'] for r in reqs]}"
    )
    req = reqs[0]
    assert "langevals/llm_boolean" in req["path"], (
        "The evaluator call must target the built-in LLM-as-a-Judge Boolean evaluator "
        f"(slug 'langevals/llm_boolean'); got path {req['path']!r}"
    )
    assert req["path"].rstrip("/").endswith("/evaluate"), (
        f"Evaluator call must hit the '/evaluate' endpoint; got {req['path']!r}"
    )

    body = req["body"]
    data = body.get("data") or {}
    answer = runs["run_a"]["result"]["answer"]

    assert data.get("input") == QUESTION, (
        f"Evaluator 'data.input' must equal the question {QUESTION!r}, "
        f"got {data.get('input')!r}"
    )
    assert isinstance(data.get("output"), str) and data.get("output").strip(), (
        f"Evaluator 'data.output' must be a non-empty string, got {data.get('output')!r}"
    )
    assert data.get("output") == answer, (
        "Evaluator 'data.output' must be the produced answer that run_pipeline returned."
    )
    contexts = data.get("contexts")
    assert isinstance(contexts, list) and len(contexts) > 0, (
        f"Evaluator 'data.contexts' must be a non-empty list, got {contexts!r}"
    )

    assert body.get("name") == EVAL_NAME, (
        f"Evaluation 'name' must be {EVAL_NAME!r}, got {body.get('name')!r}"
    )

    trace_id = body.get("trace_id")
    assert isinstance(trace_id, str) and trace_id.strip(), (
        "Evaluator call must be bound to the active trace via a non-empty 'trace_id', "
        f"got {trace_id!r}"
    )

    settings = body.get("settings")
    assert isinstance(settings, dict) and settings, (
        f"A custom rubric must be supplied via evaluator 'settings'; got {settings!r}"
    )
    settings_text = json.dumps(settings).lower()
    assert len(settings_text) > 30, (
        f"The custom rubric in 'settings' looks too small to be a real rubric: {settings!r}"
    )
    assert "question" in settings_text, (
        "The rubric must reference directly answering the question. "
        f"Settings: {settings!r}"
    )
    assert ("context" in settings_text) or ("faithful" in settings_text), (
        "The rubric must reference faithfulness to the provided context. "
        f"Settings: {settings!r}"
    )


# ---------------------------------------------------------------------------
# 5. Spans emitted and verdict attached to the answer span
# ---------------------------------------------------------------------------
def test_spans_emitted_and_evaluation_bound_to_answer_span(runs):
    spans = runs["run_a"]["spans"]
    names = {s["name"] for s in spans}
    missing = EXPECTED_SPANS - names
    assert not missing, (
        f"Expected spans {sorted(missing)} were not exported. Received: {sorted(names)}"
    )

    gen_spans = _find_spans(spans, "generate_answer")
    assert gen_spans, "No 'generate_answer' span was exported."
    gen = gen_spans[0]

    eval_children = [
        s
        for s in spans
        if s["parent_span_id"] == gen["span_id"]
        and s["attributes"].get("langwatch.span.type") == "evaluation"
    ]
    assert eval_children, (
        "No evaluation-type span is parented to 'generate_answer'; the verdict was not "
        "attached to the answer span. generate_answer span_id="
        f"{gen['span_id']}, exported spans="
        f"{[(s['name'], s['parent_span_id'], s['attributes'].get('langwatch.span.type')) for s in spans]}"
    )

    # The evaluate call's trace_id must correspond to the answer span's trace.
    trace_id = runs["run_a"]["eval_requests"][0]["body"].get("trace_id")
    assert int(trace_id, 16) == int(gen["trace_id"], 16), (
        "The evaluate call's trace_id does not match the trace of the 'generate_answer' "
        f"span. eval trace_id={trace_id!r}, generate_answer trace_id={gen['trace_id']!r}"
    )

    # The evaluation must NOT be bound to the root or retrieval span.
    for other_name in ("qa_pipeline", "retrieve_context"):
        for s in _find_spans(spans, other_name):
            wrong = [
                c
                for c in spans
                if c["parent_span_id"] == s["span_id"]
                and c["attributes"].get("langwatch.span.type") == "evaluation"
            ]
            assert not wrong, (
                f"An evaluation span was wrongly attached to the '{other_name}' span; "
                "it must be a child of 'generate_answer'."
            )


# ---------------------------------------------------------------------------
# 6. Verdict persisted to judge_result.json
# ---------------------------------------------------------------------------
def test_judge_result_persisted(runs):
    payload = runs["run_a"]["judge_json"]
    assert payload is not None, (
        f"Expected {JUDGE_RESULT_PATH} to be written by run_pipeline()."
    )
    assert bool(payload.get("passed")) is VERDICT_A["passed"], (
        f"judge_result.json 'passed' must equal the evaluator verdict "
        f"{VERDICT_A['passed']}, got {payload.get('passed')!r}"
    )
    assert abs(float(payload.get("score")) - VERDICT_A["score"]) < 1e-6, (
        f"judge_result.json 'score' must equal {VERDICT_A['score']}, "
        f"got {payload.get('score')!r}"
    )
    assert payload.get("label") == VERDICT_A["label"], (
        f"judge_result.json 'label' must equal {VERDICT_A['label']!r}, "
        f"got {payload.get('label')!r}"
    )
    assert payload.get("details") == VERDICT_A["details"], (
        "judge_result.json 'details' must equal the evaluator's returned details."
    )


# ---------------------------------------------------------------------------
# 7. Anti-hardcoding: the recorded verdict must track the evaluator response
# ---------------------------------------------------------------------------
def test_verdict_tracks_evaluator_response(runs):
    result_b = runs["run_b"]["result"]
    judgement_b = result_b.get("judgement", {})
    json_b = runs["run_b"]["judge_json"]

    assert bool(judgement_b.get("passed")) is VERDICT_B["passed"], (
        "When the evaluator returns a different verdict, the returned judgement must "
        f"change accordingly. Expected passed={VERDICT_B['passed']}, "
        f"got {judgement_b.get('passed')!r}"
    )
    assert abs(float(judgement_b.get("score")) - VERDICT_B["score"]) < 1e-6, (
        f"Returned judgement 'score' must equal {VERDICT_B['score']} for the second run, "
        f"got {judgement_b.get('score')!r}"
    )
    assert judgement_b.get("label") == VERDICT_B["label"], (
        f"Returned judgement 'label' must equal {VERDICT_B['label']!r} for the second run, "
        f"got {judgement_b.get('label')!r}"
    )

    assert json_b is not None, (
        f"Expected {JUDGE_RESULT_PATH} to be rewritten on the second run."
    )
    assert bool(json_b.get("passed")) is VERDICT_B["passed"], (
        "judge_result.json must be rewritten with the evaluator's new verdict; "
        f"expected passed={VERDICT_B['passed']}, got {json_b.get('passed')!r}"
    )
    assert abs(float(json_b.get("score")) - VERDICT_B["score"]) < 1e-6, (
        f"judge_result.json 'score' must equal {VERDICT_B['score']} on the second run, "
        f"got {json_b.get('score')!r}"
    )
    assert json_b.get("label") == VERDICT_B["label"], (
        f"judge_result.json 'label' must equal {VERDICT_B['label']!r} on the second run, "
        f"got {json_b.get('label')!r}"
    )

    # Sanity: the two runs actually differ, proving no hardcoding.
    assert judgement_b.get("passed") != VERDICT_A["passed"], (
        "The second run's verdict is identical to the first; the pipeline appears to "
        "hardcode the judgement instead of using the evaluator's response."
    )
