import json
import os
import shutil
import subprocess

import pytest

PROJECT_DIR = "/home/user/dspy-serialization"
RUN_SCRIPT = os.path.join(PROJECT_DIR, "run.py")
QA_PROGRAM = os.path.join(PROJECT_DIR, "qa_program.py")


def _project_python():
    """Prefer the project's uv venv interpreter (which has langwatch/dspy installed)."""
    venv_py = os.path.join(PROJECT_DIR, ".venv", "bin", "python")
    if os.path.isfile(venv_py):
        return venv_py
    return shutil.which("python3") or shutil.which("python") or "python3"


def _parse_last_json_line(stdout):
    """Return the JSON object printed on the last non-empty stdout line."""
    for line in reversed([ln for ln in stdout.splitlines() if ln.strip()]):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


@pytest.fixture(scope="session")
def run_result():
    assert os.path.isfile(RUN_SCRIPT), f"Expected entrypoint script at {RUN_SCRIPT}."
    py = _project_python()
    proc = subprocess.run(
        [py, "run.py"],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
        env=os.environ.copy(),
    )
    return proc


@pytest.fixture(scope="session")
def parsed_json(run_result):
    obj = _parse_last_json_line(run_result.stdout)
    assert obj is not None, (
        "Could not parse a JSON object from the final non-empty stdout line.\n"
        f"stdout tail:\n{run_result.stdout[-2000:]}\n"
        f"stderr tail:\n{run_result.stderr[-2000:]}"
    )
    return obj


def test_run_exits_successfully(run_result):
    assert run_result.returncode == 0, (
        f"`python run.py` exited with {run_result.returncode}.\n"
        f"stdout tail:\n{run_result.stdout[-1500:]}\n"
        f"stderr tail:\n{run_result.stderr[-1500:]}"
    )


def test_no_mockvalser_crash(run_result):
    combined = run_result.stdout + "\n" + run_result.stderr
    assert "MockValSer" not in combined, (
        "The serialization still triggers the MockValSer failure from Issue #468.\n"
        f"stderr tail:\n{run_result.stderr[-1500:]}"
    )
    assert "Traceback (most recent call last)" not in combined, (
        "run.py produced an unhandled traceback; serialization did not complete cleanly.\n"
        f"stderr tail:\n{run_result.stderr[-1500:]}"
    )


def test_top_level_shape(parsed_json):
    for key in ("name", "predictor", "demos", "records"):
        assert key in parsed_json, f"Serialized JSON is missing top-level key '{key}'."
    assert parsed_json["name"] == "generate_answer", (
        f"Expected top-level 'name' == 'generate_answer', got {parsed_json['name']!r}."
    )
    assert isinstance(parsed_json["predictor"], dict), "'predictor' must serialize to a JSON object."
    assert isinstance(parsed_json["demos"], list), "'demos' must serialize to a JSON array."
    assert isinstance(parsed_json["records"], list), "'records' must serialize to a JSON array."


def test_predictor_serialized_structurally(parsed_json):
    predictor = parsed_json["predictor"]
    blob = json.dumps(predictor)
    assert "Predict" in blob, (
        "The serialized 'predictor' object must identify the dspy Predict class "
        "(a class marker whose value contains 'Predict')."
    )
    assert "signature" in predictor, "The serialized 'predictor' must include a 'signature'."
    assert "question" in blob and "answer" in blob, (
        "The predictor's signature must reference the 'question' and 'answer' fields."
    )


def test_demos_preserved(parsed_json):
    demos = parsed_json["demos"]
    assert len(demos) == 2, f"Expected 2 serialized demos, got {len(demos)}."
    blob = json.dumps(demos)
    assert "What is the capital of France?" in blob and "Paris" in blob, (
        "The first training demo (capital of France -> Paris) was not preserved in the demos array."
    )
    assert "What is 2 + 2?" in blob and '"4"' in blob, (
        "The second training demo (2 + 2 -> 4) was not preserved in the demos array."
    )


def test_records_with_nested_predictor(parsed_json):
    records = parsed_json["records"]
    assert len(records) == 2, f"Expected 2 serialized records, got {len(records)}."

    answers = []
    for rec in records:
        assert isinstance(rec, dict), "Each record must serialize to a JSON object."
        assert "answer" in rec and isinstance(rec["answer"], str), (
            "Each record must expose a string 'answer' field."
        )
        answers.append(rec["answer"])
        assert "source_predictor" in rec, "Each record must expose a 'source_predictor' field."
        sp = rec["source_predictor"]
        assert isinstance(sp, dict), (
            "'source_predictor' must serialize to a nested JSON object, not an opaque string; "
            "this is the core of the Issue #468 fix."
        )
        assert "Predict" in json.dumps(sp), (
            "The nested 'source_predictor' object must identify the dspy Predict class."
        )

    assert set(answers) == {"Paris", "4"}, (
        f"Expected record answers {{'Paris', '4'}}, got {set(answers)!r}."
    )


def test_qa_program_fixture_intact():
    assert os.path.isfile(QA_PROGRAM), f"{QA_PROGRAM} must remain in the project."
    with open(QA_PROGRAM, "r", encoding="utf-8") as f:
        source = f.read()
    assert "model_construct" in source, (
        "qa_program.py must still build AnswerRecord instances via model_construct "
        "(the reproduction fixture must not be stubbed out to dodge the bug)."
    )
    assert "source_predictor" in source and "Predict" in source, (
        "qa_program.py must still nest a dspy.Predict inside the AnswerRecord fixture."
    )
