import json
import os
import re
import subprocess

import pytest
import yaml

PROJECT_DIR = "/home/user/myproject"
HANDLE = "support-triage-agent"
MATERIALIZED_PATH = os.path.join(
    PROJECT_DIR, "prompts", ".materialized", f"{HANDLE}.prompt.yaml"
)
TRACE_SPANS_PATH = os.path.join(PROJECT_DIR, "trace_spans.jsonl")
RUN_SCRIPT = os.path.join(PROJECT_DIR, "run.py")

FULL_VARS = {
    "customer_name": "Alice Chen",
    "account_tier": "Enterprise",
    "issue_summary": "I was double charged for the annual plan",
    "priority": "P1",
}

TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _python_executable():
    venv_python = os.path.join(PROJECT_DIR, ".venv", "bin", "python")
    if os.path.isfile(venv_python):
        return venv_python
    return "python"


def _cleanup(*names):
    for name in names:
        path = os.path.join(PROJECT_DIR, name)
        if os.path.isfile(path):
            os.remove(path)


def _run(args):
    cmd = [_python_executable(), RUN_SCRIPT] + args
    return subprocess.run(
        cmd,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        timeout=300,
    )


def _materialized_model():
    with open(MATERIALIZED_PATH) as f:
        data = yaml.safe_load(f)
    return data.get("model", "")


def test_run_script_exists():
    assert os.path.isfile(
        RUN_SCRIPT
    ), f"Expected the generation service at {RUN_SCRIPT}."


def test_happy_path_explicit_version():
    _cleanup("result.json", "trace_spans.jsonl")
    out_path = os.path.join(PROJECT_DIR, "result.json")
    proc = _run(
        [
            "--handle",
            HANDLE,
            "--version",
            "2",
            "--vars",
            json.dumps(FULL_VARS),
            "--out",
            out_path,
        ]
    )
    assert proc.returncode == 0, (
        f"Expected exit code 0 for the happy path.\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert os.path.isfile(out_path), f"Expected result file {out_path} to be written."

    with open(out_path) as f:
        result = json.load(f)

    assert result.get("handle") == HANDLE, f"Expected handle '{HANDLE}'."
    assert result.get("version") == 2, "Expected resolved version 2."

    model = result.get("model", "")
    assert model == _materialized_model(), (
        "Result 'model' must equal the model declared in the materialized prompt "
        f"('{_materialized_model()}'), got '{model}'."
    )
    assert model.startswith(
        "openai/"
    ), f"Result 'model' must keep its provider prefix, got '{model}'."

    trace_id = result.get("trace_id", "")
    assert isinstance(trace_id, str) and TRACE_ID_RE.match(
        trace_id
    ), f"trace_id must be a 32-char lowercase hex string, got '{trace_id}'."

    messages = result.get("messages", [])
    roles = [m.get("role") for m in messages]
    assert "system" in roles, "Compiled messages must include a system message."
    assert "user" in roles, "Compiled messages must include a user message."

    combined = "".join(m.get("content", "") for m in messages)
    for value in FULL_VARS.values():
        assert value in combined, (
            f"Compiled messages must contain the substituted value '{value}'. "
            f"Combined content:\n{combined}"
        )
    assert "{{" not in combined, (
        "Compiled messages must not contain any unresolved '{{' placeholder. "
        f"Combined content:\n{combined}"
    )

    response = result.get("response", "")
    assert (
        isinstance(response, str) and response.strip() != ""
    ), "Result 'response' must be the non-empty text returned by LiteLLM completion."


def test_trace_linkage_artifact():
    # Depends on the happy-path run having produced the trace artifact.
    _cleanup("result.json", "trace_spans.jsonl")
    out_path = os.path.join(PROJECT_DIR, "result.json")
    proc = _run(
        [
            "--handle",
            HANDLE,
            "--version",
            "2",
            "--vars",
            json.dumps(FULL_VARS),
            "--out",
            out_path,
        ]
    )
    assert proc.returncode == 0, (
        f"Expected exit code 0 before checking the trace artifact.\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert os.path.isfile(
        TRACE_SPANS_PATH
    ), f"Expected trace artifact {TRACE_SPANS_PATH} to be written."

    with open(out_path) as f:
        result = json.load(f)
    result_trace_id = result.get("trace_id", "")

    spans = []
    with open(TRACE_SPANS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            span = json.loads(line)
            for field in ("name", "trace_id", "span_id", "parent_span_id"):
                assert field in span, (
                    f"Each captured span line must include field '{field}'. "
                    f"Got: {span}"
                )
            spans.append(span)

    assert spans, "The trace artifact must contain at least one captured span."

    trace_ids = {s["trace_id"] for s in spans}
    assert len(trace_ids) == 1, (
        f"All captured spans must share a single trace id, found: {trace_ids}"
    )
    shared_trace_id = next(iter(trace_ids))
    assert shared_trace_id == result_trace_id, (
        "The span trace id must equal the result trace_id "
        f"('{result_trace_id}'), got '{shared_trace_id}'."
    )

    llm_spans = [s for s in spans if s["name"] == "llm_generation"]
    assert (
        len(llm_spans) >= 1
    ), "The trace artifact must contain a span named 'llm_generation'."
    llm_span = llm_spans[0]

    parent_id = llm_span.get("parent_span_id")
    assert parent_id, "The 'llm_generation' span must have a non-empty parent_span_id."
    span_ids = {s["span_id"] for s in spans}
    assert parent_id in span_ids, (
        "The 'llm_generation' span must be nested under another captured span "
        "(its parent span must be present in the trace artifact)."
    )


def test_default_version_resolution():
    _cleanup("result_default.json")
    out_path = os.path.join(PROJECT_DIR, "result_default.json")
    default_vars = {
        "customer_name": "Bob Diaz",
        "account_tier": "Free",
        "issue_summary": "App crashes on login",
        "priority": "P3",
    }
    proc = _run(
        [
            "--handle",
            HANDLE,
            "--vars",
            json.dumps(default_vars),
            "--out",
            out_path,
        ]
    )
    assert proc.returncode == 0, (
        f"Expected exit code 0 when --version is omitted.\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert os.path.isfile(out_path), f"Expected result file {out_path} to be written."
    with open(out_path) as f:
        result = json.load(f)
    assert (
        result.get("version") == 2
    ), "With --version omitted, the version must resolve to 2 from the lock file."
    combined = "".join(m.get("content", "") for m in result.get("messages", []))
    for value in default_vars.values():
        assert value in combined, f"Compiled messages must contain '{value}'."
    assert "{{" not in combined, "Compiled messages must not contain '{{' placeholders."


def test_version_mismatch_fails():
    _cleanup("result_bad.json")
    out_path = os.path.join(PROJECT_DIR, "result_bad.json")
    proc = _run(
        [
            "--handle",
            HANDLE,
            "--version",
            "5",
            "--vars",
            json.dumps(FULL_VARS),
            "--out",
            out_path,
        ]
    )
    assert proc.returncode != 0, (
        "Requesting a version that does not match the resolved prompt version "
        "must fail with a non-zero exit code."
    )
    combined_output = (proc.stdout + proc.stderr).lower()
    assert "version" in combined_output, (
        "The error output must mention a version mismatch. "
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    if os.path.isfile(out_path):
        with open(out_path) as f:
            content = f.read().strip()
        assert content == "" or "5" not in content, (
            "A successful compiled result must NOT be produced on version mismatch."
        )


def test_missing_variable_fails():
    _cleanup("result_missing.json")
    out_path = os.path.join(PROJECT_DIR, "result_missing.json")
    proc = _run(
        [
            "--handle",
            HANDLE,
            "--version",
            "2",
            "--vars",
            json.dumps({"customer_name": "Alice Chen"}),
            "--out",
            out_path,
        ]
    )
    assert proc.returncode != 0, (
        "Omitting required template variables must fail with a non-zero exit code."
    )
    combined_output = (proc.stdout + proc.stderr).lower()
    assert any(
        var in combined_output for var in ("account_tier", "issue_summary", "priority")
    ), (
        "The error output must name at least one missing variable. "
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert not os.path.isfile(out_path), (
        "A successful compiled result must NOT be produced when a required "
        "variable is missing."
    )
