import csv
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

PROJECT_DIR = "/home/user/project"
DATASET_PATH = os.path.join(PROJECT_DIR, "data", "qa_dataset.csv")
KB_PATH = os.path.join(PROJECT_DIR, "data", "knowledge_base.json")
SUMMARY_PATH = os.path.join(PROJECT_DIR, "eval_summary.json")
RUN_ID_PATH = "/logs/artifacts/run-id"

EVALUATOR_SLUG = "legacy/ragas_context_utilization"


def _read_run_id():
    try:
        with open(RUN_ID_PATH) as f:
            return f.read().strip()
    except Exception:
        return ""


def _read_questions():
    with open(DATASET_PATH, newline="") as f:
        rows = list(csv.DictReader(f))
    return [str(r["question"]).strip() for r in rows]


def _read_kb_contents():
    with open(KB_PATH) as f:
        docs = json.load(f)
    return [str(d.get("content", "")) for d in docs]


def _make_langwatch_server():
    """Start a real local HTTP server that speaks the LangWatch batch-evaluation
    API. The agent's script talks to this genuine endpoint over HTTP; nothing in
    the LangWatch SDK or its dependencies is mocked."""

    captured = {
        "inits": [],
        "evaluate_calls": [],  # list of (slug, body)
        "batch_logs": [],
        "lock": threading.Lock(),
    }

    def _read_json(handler):
        length = int(handler.headers.get("Content-Length", 0) or 0)
        raw = handler.rfile.read(length) if length else b""
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    def _send_json(handler, code, payload):
        body = json.dumps(payload).encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        try:
            handler.wfile.write(body)
        except Exception:
            pass

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/api/experiment/init":
                body = _read_json(self)
                with captured["lock"]:
                    captured["inits"].append(body)
                slug = body.get("experiment_slug") or body.get("experiment_name") or "exp"
                _send_json(
                    self,
                    200,
                    {"path": f"/test-project/experiments/{slug}", "slug": slug},
                )
                return
            if path == "/api/evaluations/batch/log_results":
                body = _read_json(self)
                with captured["lock"]:
                    captured["batch_logs"].append(body)
                _send_json(self, 200, {})
                return
            if path.startswith("/api/evaluations/") and path.endswith("/evaluate"):
                slug = path[len("/api/evaluations/"):-len("/evaluate")]
                body = _read_json(self)
                with captured["lock"]:
                    captured["evaluate_calls"].append((slug, body))
                _send_json(
                    self,
                    200,
                    {
                        "status": "processed",
                        "passed": True,
                        "score": 0.83,
                        "details": "emulated",
                    },
                )
                return
            # Absorb OTLP trace exports and anything else with a 200.
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length:
                try:
                    self.rfile.read(length)
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            if "/results" in path and path.startswith("/api/evaluations/"):
                _send_json(self, 200, {"dataset": [], "evaluations": []})
                return
            _send_json(self, 404, {"error": "not found"})

        def log_message(self, *args):  # silence default logging
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, captured, port


@pytest.fixture(scope="session")
def evaluation_run():
    # Clean up any stale artifact from a previous run.
    if os.path.isfile(SUMMARY_PATH):
        os.remove(SUMMARY_PATH)

    httpd, captured, port = _make_langwatch_server()
    try:
        env = os.environ.copy()
        env["LANGWATCH_API_KEY"] = "sk-lw-test-key"
        env["LANGWATCH_ENDPOINT"] = f"http://127.0.0.1:{port}"
        env["LANGWATCH_PROJECT_ID"] = "proj-test"
        env["OTEL_EXPORTER_OTLP_TRACES_TIMEOUT"] = "5"

        proc = subprocess.run(
            [sys.executable, "run_evaluation.py"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,
        )

        result = {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "inits": list(captured["inits"]),
            "evaluate_calls": list(captured["evaluate_calls"]),
            "batch_logs": list(captured["batch_logs"]),
        }
        yield result
    finally:
        try:
            httpd.shutdown()
        except Exception:
            pass


def test_script_runs_successfully(evaluation_run):
    assert evaluation_run["returncode"] == 0, (
        "`python run_evaluation.py` exited with "
        f"{evaluation_run['returncode']}.\nstdout:\n{evaluation_run['stdout']}\n"
        f"stderr:\n{evaluation_run['stderr']}"
    )


def test_single_batch_evaluation_run_initialized(evaluation_run):
    inits = evaluation_run["inits"]
    assert len(inits) == 1, (
        f"Expected exactly one batch evaluation run to be initialized, got {len(inits)}: {inits}"
    )
    init = inits[0]
    assert init.get("experiment_type") == "BATCH_EVALUATION_V2", (
        f"Expected experiment_type 'BATCH_EVALUATION_V2', got: {init.get('experiment_type')!r}"
    )
    run_id = _read_run_id()
    assert run_id, f"run-id could not be read from {RUN_ID_PATH}."
    name = str(init.get("experiment_name", ""))
    assert run_id in name, (
        f"Evaluation run name {name!r} must contain the run-id {run_id!r}."
    )


def test_evaluator_called_once_per_row(evaluation_run):
    questions = _read_questions()
    n = len(questions)
    ragas_calls = [
        body for (slug, body) in evaluation_run["evaluate_calls"]
        if slug == EVALUATOR_SLUG
    ]
    assert len(ragas_calls) == n, (
        f"Expected exactly {n} calls to the built-in evaluator '{EVALUATOR_SLUG}' "
        f"(one per dataset row), got {len(ragas_calls)}. "
        f"All evaluator slugs seen: {[s for s, _ in evaluation_run['evaluate_calls']]}"
    )


def test_evaluator_payload_shape(evaluation_run):
    ragas_calls = [
        body for (slug, body) in evaluation_run["evaluate_calls"]
        if slug == EVALUATOR_SLUG
    ]
    assert ragas_calls, f"No calls to evaluator '{EVALUATOR_SLUG}' were captured."
    for body in ragas_calls:
        data = body.get("data") or {}
        inp = data.get("input")
        out = data.get("output")
        contexts = data.get("contexts")
        assert isinstance(inp, str) and inp.strip(), (
            f"Evaluator call 'data.input' must be a non-empty string, got: {inp!r}"
        )
        assert isinstance(out, str) and out.strip(), (
            f"Evaluator call 'data.output' must be a non-empty string, got: {out!r}"
        )
        assert isinstance(contexts, list) and len(contexts) > 0, (
            f"Evaluator call 'data.contexts' must be a non-empty list, got: {contexts!r}"
        )
        assert all(isinstance(c, str) for c in contexts), (
            f"Every element of 'data.contexts' must be a string, got: {contexts!r}"
        )


def test_all_questions_covered_exactly_once(evaluation_run):
    questions = sorted(_read_questions())
    inputs = sorted(
        str((body.get("data") or {}).get("input", "")).strip()
        for (slug, body) in evaluation_run["evaluate_calls"]
        if slug == EVALUATOR_SLUG
    )
    assert inputs == questions, (
        "The set of evaluator 'input' values must equal the exact set of dataset "
        f"questions.\nExpected: {questions}\nGot:      {inputs}"
    )


def test_contexts_grounded_in_knowledge_base(evaluation_run):
    kb_contents = _read_kb_contents()
    ragas_calls = [
        body for (slug, body) in evaluation_run["evaluate_calls"]
        if slug == EVALUATOR_SLUG
    ]
    grounded = False
    for body in ragas_calls:
        contexts = (body.get("data") or {}).get("contexts") or []
        for ctx in contexts:
            ctx_s = str(ctx).strip()
            if not ctx_s:
                continue
            for content in kb_contents:
                if ctx_s in content or content.strip() in ctx_s:
                    grounded = True
                    break
            if grounded:
                break
        if grounded:
            break
    assert grounded, (
        "None of the evaluator 'contexts' matched any knowledge-base document "
        "content; contexts must be really retrieved from data/knowledge_base.json."
    )


def test_summary_artifact(evaluation_run):
    assert os.path.isfile(SUMMARY_PATH), f"Summary artifact {SUMMARY_PATH} was not created."
    with open(SUMMARY_PATH) as f:
        summary = json.load(f)
    n = len(_read_questions())
    assert summary.get("rows_evaluated") == n, (
        f"eval_summary.json 'rows_evaluated' must equal {n}, got: {summary.get('rows_evaluated')!r}"
    )
    assert summary.get("evaluator") == EVALUATOR_SLUG, (
        f"eval_summary.json 'evaluator' must equal {EVALUATOR_SLUG!r}, got: {summary.get('evaluator')!r}"
    )
    run_id = _read_run_id()
    assert run_id and run_id in str(summary.get("experiment_name", "")), (
        f"eval_summary.json 'experiment_name' must contain the run-id {run_id!r}, "
        f"got: {summary.get('experiment_name')!r}"
    )


def test_stdout_reports_row_count(evaluation_run):
    n = len(_read_questions())
    assert re.search(rf"Rows evaluated:\s*{n}\b", evaluation_run["stdout"]), (
        f"Expected a line matching 'Rows evaluated: {n}' in stdout, got:\n{evaluation_run['stdout']}"
    )
