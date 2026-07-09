import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

PROJECT_DIR = "/home/user/project"
VENV_PYTHON = "/home/user/project/.venv/bin/python"
OUTPUT_LOG = "/home/user/project/output.log"
RUN_ID_FILE = "/logs/artifacts/run-id"

REQUIRED_PARAM_KEYS = {"bsize", "num_candidates", "max_steps", "max_demos"}


def _read_run_id():
    assert os.path.isfile(RUN_ID_FILE), f"run-id file {RUN_ID_FILE} does not exist."
    with open(RUN_ID_FILE) as f:
        return f.read().strip()


class _CollectorState:
    """Shared, thread-safe-enough storage for the stub LangWatch collector."""

    def __init__(self):
        self.init_bodies = []
        self.step_objects = []
        self.log_steps_calls = 0
        self.lock = threading.Lock()


def _make_handler(state: _CollectorState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args, **kwargs):  # silence noisy logging
            pass

        def _read_body(self):
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b""
            return raw

        def _respond(self, code, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            raw = self._read_body()
            if self.path.startswith("/api/experiment/init"):
                with state.lock:
                    try:
                        state.init_bodies.append(json.loads(raw.decode("utf-8")))
                    except Exception:
                        state.init_bodies.append({"_raw": raw.decode("utf-8", "replace")})
                self._respond(200, {"path": "/experiment/simba-test"})
            elif self.path.startswith("/api/dspy/log_steps"):
                with state.lock:
                    state.log_steps_calls += 1
                    try:
                        parsed = json.loads(raw.decode("utf-8"))
                        if isinstance(parsed, list):
                            state.step_objects.extend(parsed)
                        else:
                            state.step_objects.append(parsed)
                    except Exception:
                        pass
                self._respond(200, {})
            else:
                self._respond(404, {"error": "not found"})

    return Handler


@pytest.fixture(scope="session")
def cli_run():
    """Start the stub collector, run the agent's CLI once, capture everything."""
    state = _CollectorState()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(state))
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # Clean stale artifacts.
    if os.path.isfile(OUTPUT_LOG):
        os.remove(OUTPUT_LOG)

    env = os.environ.copy()
    env["LANGWATCH_ENDPOINT"] = f"http://127.0.0.1:{port}"
    env["LANGWATCH_API_KEY"] = "sk-lw-test-key"

    try:
        result = subprocess.run(
            [VENV_PYTHON, "run.py"],
            capture_output=True,
            text=True,
            cwd=PROJECT_DIR,
            env=env,
            timeout=600,
        )
    finally:
        server.shutdown()
        server.server_close()

    print("run.py stdout:\n" + result.stdout)
    print("run.py stderr:\n" + result.stderr)

    return {
        "result": result,
        "init_bodies": state.init_bodies,
        "step_objects": state.step_objects,
        "log_steps_calls": state.log_steps_calls,
        "run_id": _read_run_id(),
    }


def _validate_step(s):
    assert isinstance(s.get("index"), str), f"step index must be a string, got: {s.get('index')!r}"
    assert isinstance(s.get("label"), str), f"step label must be a string, got: {s.get('label')!r}"
    assert isinstance(s.get("score"), (int, float)) and not isinstance(s.get("score"), bool), (
        f"step score must be a number, got: {s.get('score')!r}"
    )
    optimizer = s.get("optimizer")
    assert isinstance(optimizer, dict), f"step optimizer must be an object, got: {optimizer!r}"
    assert optimizer.get("name") == "SIMBA", (
        f"step optimizer.name must be 'SIMBA', got: {optimizer.get('name')!r}"
    )
    params = optimizer.get("parameters")
    assert isinstance(params, dict), f"optimizer.parameters must be an object, got: {params!r}"
    missing = REQUIRED_PARAM_KEYS - set(params.keys())
    assert not missing, f"optimizer.parameters missing keys {missing}; got keys {set(params.keys())}"
    predictors = s.get("predictors")
    assert isinstance(predictors, list) and len(predictors) > 0, (
        f"step predictors must be a non-empty list, got: {predictors!r}"
    )


def test_registration_removes_valueerror():
    """After register_langwatch_simba(), patch_optimizer must accept a SIMBA optimizer."""
    script = (
        "import dspy\n"
        "from dspy.teleprompt import SIMBA\n"
        "import langwatch.dspy\n"
        "import simba_support\n"
        "simba_support.register_langwatch_simba()\n"
        "opt = SIMBA(metric=lambda example, pred, trace=None: 1.0)\n"
        "langwatch.dspy.langwatch_dspy.patch_optimizer(opt)\n"
        "assert isinstance(opt, SIMBA), 'patched optimizer is no longer a SIMBA subclass'\n"
        "assert type(opt).__name__ != 'SIMBA', 'optimizer class was not swapped to a tracking subclass'\n"
        "print('REGISTERED_OK')\n"
    )
    result = subprocess.run(
        [VENV_PYTHON, "-c", script],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
    )
    assert result.returncode == 0 and "REGISTERED_OK" in result.stdout, (
        "register_langwatch_simba() did not make SIMBA a supported optimizer.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_cli_runs_successfully(cli_run):
    result = cli_run["result"]
    assert result.returncode == 0, (
        f"`python3 run.py` exited with {result.returncode}.\nstderr:\n{result.stderr}"
    )
    assert "ValueError" not in result.stderr, (
        f"run.py raised a ValueError:\n{result.stderr}"
    )


def test_collector_received_init_and_steps(cli_run):
    assert len(cli_run["init_bodies"]) == 1, (
        f"Expected exactly one experiment-init POST, got {len(cli_run['init_bodies'])}."
    )
    assert cli_run["log_steps_calls"] >= 1, (
        "Expected at least one POST to /api/dspy/log_steps, got none."
    )
    assert len(cli_run["step_objects"]) >= 1, (
        "Expected the collector to receive at least one step object."
    )


def test_received_steps_structure(cli_run):
    steps = cli_run["step_objects"]
    assert len(steps) >= 1, "No steps were delivered to the collector."
    for s in steps:
        _validate_step(s)


def test_output_log_steps_json(cli_run):
    assert os.path.isfile(OUTPUT_LOG), f"Output log {OUTPUT_LOG} was not created."
    with open(OUTPUT_LOG) as f:
        lines = f.read().splitlines()

    json_lines = [ln for ln in lines if ln.startswith("Steps JSON: ")]
    assert len(json_lines) == 1, (
        f"Expected exactly one 'Steps JSON: ' line in output.log, found {len(json_lines)}."
    )
    logged = json.loads(json_lines[0][len("Steps JSON: "):])
    assert isinstance(logged, list) and len(logged) >= 1, (
        "The 'Steps JSON:' line must contain a non-empty JSON array of steps."
    )
    for s in logged:
        _validate_step(s)

    assert len(logged) == len(cli_run["step_objects"]), (
        "Number of steps in output.log does not match the number delivered to the collector: "
        f"{len(logged)} vs {len(cli_run['step_objects'])}."
    )


def test_candidate_programs_count_matches(cli_run):
    with open(OUTPUT_LOG) as f:
        content = f.read()
    import re

    m = re.search(r"^Candidate programs:\s*(\d+)\s*$", content, re.MULTILINE)
    assert m is not None, "output.log must contain a line 'Candidate programs: <n>'."
    n = int(m.group(1))

    json_lines = [ln for ln in content.splitlines() if ln.startswith("Steps JSON: ")]
    logged = json.loads(json_lines[0][len("Steps JSON: "):])
    assert n == len(logged), (
        f"Number of candidate programs ({n}) must equal the number of emitted steps ({len(logged)})."
    )


def test_run_id_scoping(cli_run):
    run_id = cli_run["run_id"]
    assert run_id, "run-id read from /logs/artifacts/run-id is empty."

    slugs = [str(s.get("experiment_slug", "")) for s in cli_run["step_objects"]]
    init_blob = json.dumps(cli_run["init_bodies"])
    found = any(run_id in slug for slug in slugs) or (run_id in init_blob)
    assert found, (
        f"run-id '{run_id}' was not found in any step experiment_slug or the init payload. "
        f"slugs={slugs}"
    )
