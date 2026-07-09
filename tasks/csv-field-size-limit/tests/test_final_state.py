import csv
import hashlib
import json
import os
import random
import shutil
import string
import subprocess

import pytest

PROJECT_DIR = "/home/user/langwatch-csv-pipeline"
PIPELINE = os.path.join(PROJECT_DIR, "pipeline.py")

INPUT_JSON = os.path.join(PROJECT_DIR, "verify_input.json")
DATASET_CSV = os.path.join(PROJECT_DIR, "verify_dataset.csv")
OUTPUT_JSON = os.path.join(PROJECT_DIR, "verify_output.json")

REPORT_MARKER = "LANGWATCH_CSV_REPORT "
DEFAULT_CSV_LIMIT = 131072


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _pipeline_python():
    """Prefer the project's uv venv interpreter (which has langwatch installed)."""
    venv_py = os.path.join(PROJECT_DIR, ".venv", "bin", "python")
    if os.path.isfile(venv_py):
        return venv_py
    return shutil.which("python3") or shutil.which("python") or "python3"


def _compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _big_text(rng, n):
    # Pool intentionally includes CSV-hostile characters: commas, double
    # quotes, and newlines, to force correct quoting/escaping on round-trip.
    pool = string.ascii_letters + string.digits + '   ,."\n\t'
    return "".join(rng.choice(pool) for _ in range(n))


def _build_dataset():
    rng = random.Random(1234)
    records = []

    # Record 0: small, but with special characters.
    records.append({
        "index": 0,
        "question": 'What is "RAG", and how does it work, technically?',
        "expected_output": "Retrieval-Augmented Generation,\nwith citations.",
        "contexts": ['Doc A: "quoted, text"', "Doc B:\nmulti-line"],
        "conversation_history": [
            {"role": "user", "content": "hi, there"},
            {"role": "assistant", "content": 'sure — here\'s "help"'},
        ],
    })

    # Record 1: contexts is huge (serialized well above 200000 chars).
    big_ctx = [_big_text(rng, 120000), _big_text(rng, 120000)]
    records.append({
        "index": 1,
        "question": "Summarize the retrieved documents.",
        "expected_output": "A faithful summary.",
        "contexts": big_ctx,
        "conversation_history": [
            {"role": "user", "content": "Summarize, please."},
            {"role": "assistant", "content": _big_text(rng, 500)},
        ],
    })

    # Record 2: conversation_history is huge (serialized above 200000 chars).
    big_turns = []
    for i in range(20):
        big_turns.append({"role": "user", "content": _big_text(rng, 6000)})
        big_turns.append({"role": "assistant", "content": _big_text(rng, 6000)})
    records.append({
        "index": 2,
        "question": "Continue the long conversation.",
        "expected_output": "Coherent continuation.",
        "contexts": ["short context, with comma"],
        "conversation_history": big_turns,
    })

    # Record 3: both moderately large, heavy on quotes/newlines.
    records.append({
        "index": 3,
        "question": "Edge cases: commas, quotes, and newlines.",
        "expected_output": 'line1\nline2,"still going"',
        "contexts": [_big_text(rng, 40000), _big_text(rng, 40000)],
        "conversation_history": [
            {"role": "user", "content": _big_text(rng, 40000)},
            {"role": "assistant", "content": _big_text(rng, 40000)},
        ],
    })

    return records


def _expected_max_field_chars(records):
    longest = 0
    for rec in records:
        cells = [
            str(rec["index"]),
            rec["question"],
            rec["expected_output"],
            _compact(rec["contexts"]),
            _compact(rec["conversation_history"]),
        ]
        longest = max(longest, max(len(c) for c in cells))
    return longest


def _expected_checksums(records):
    out = {}
    for rec in records:
        out[str(rec["index"])] = {
            "contexts": _sha256(_compact(rec["contexts"])),
            "conversation_history": _sha256(_compact(rec["conversation_history"])),
        }
    return out


def _extract_report(stdout):
    report_line = None
    for line in stdout.splitlines():
        if line.startswith(REPORT_MARKER):
            report_line = line
    assert report_line is not None, (
        f"No stdout line starting with '{REPORT_MARKER}' was found. "
        f"stdout was:\n{stdout[-2000:]}"
    )
    payload = report_line[len(REPORT_MARKER):].strip()
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        pytest.fail(f"Report after marker is not valid JSON: {exc}\nPayload: {payload[:500]}")


# --------------------------------------------------------------------------- #
# Session fixture: generate data + run the pipeline once, reuse results.
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def pipeline_run():
    for path in (INPUT_JSON, DATASET_CSV, OUTPUT_JSON):
        if os.path.exists(path):
            os.remove(path)

    records = _build_dataset()

    # Sanity check on the generated fixture itself.
    assert len(_compact(records[1]["contexts"])) > 200000, (
        "Test fixture invalid: record 1 contexts should exceed 200000 serialized chars."
    )
    assert len(_compact(records[2]["conversation_history"])) > 200000, (
        "Test fixture invalid: record 2 conversation_history should exceed 200000 serialized chars."
    )

    with open(INPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)

    py = _pipeline_python()
    env = os.environ.copy()

    export_proc = subprocess.run(
        [py, PIPELINE, "export", "--input", INPUT_JSON, "--output", DATASET_CSV],
        capture_output=True, text=True, cwd=PROJECT_DIR, env=env,
    )
    import_proc = subprocess.run(
        [py, PIPELINE, "import", "--input", DATASET_CSV, "--output", OUTPUT_JSON],
        capture_output=True, text=True, cwd=PROJECT_DIR, env=env,
    )

    return {
        "records": records,
        "export": export_proc,
        "import": import_proc,
    }


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_pipeline_file_exists():
    assert os.path.isfile(PIPELINE), f"Expected pipeline entrypoint at {PIPELINE}."


def test_export_succeeds_and_writes_csv(pipeline_run):
    proc = pipeline_run["export"]
    assert proc.returncode == 0, (
        f"'export' failed (exit {proc.returncode}).\nstdout:\n{proc.stdout[-1500:]}\n"
        f"stderr:\n{proc.stderr[-1500:]}"
    )
    assert os.path.isfile(DATASET_CSV), f"Export did not create {DATASET_CSV}."


def test_csv_header_is_exact(pipeline_run):
    with open(DATASET_CSV, "r", encoding="utf-8") as f:
        first_line = f.readline().rstrip("\r\n")
    assert first_line == "index,question,expected_output,contexts,conversation_history", (
        f"Unexpected CSV header line: {first_line!r}"
    )


def test_csv_exceeds_default_field_limit(pipeline_run):
    """The exported CSV must contain fields larger than the csv default limit."""
    original = csv.field_size_limit()
    try:
        csv.field_size_limit(DEFAULT_CSV_LIMIT)
        raised = False
        try:
            with open(DATASET_CSV, "r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                for _ in reader:
                    pass
        except csv.Error as exc:
            raised = "field larger than field limit" in str(exc)
        assert raised, (
            "Reading the exported CSV under Python's default field size limit "
            "(131072) did not raise the expected '_csv.Error: field larger than "
            "field limit' error. This means the oversized fields were not preserved."
        )
    finally:
        csv.field_size_limit(original)


def test_import_succeeds_and_writes_json(pipeline_run):
    proc = pipeline_run["import"]
    assert proc.returncode == 0, (
        f"'import' failed (exit {proc.returncode}).\nstdout:\n{proc.stdout[-1500:]}\n"
        f"stderr:\n{proc.stderr[-1500:]}"
    )
    assert os.path.isfile(OUTPUT_JSON), f"Import did not create {OUTPUT_JSON}."


def test_round_trip_is_lossless(pipeline_run):
    original = pipeline_run["records"]
    with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
        reconstructed = json.load(f)

    assert isinstance(reconstructed, list), "Reconstructed output must be a JSON array."
    assert len(reconstructed) == len(original), (
        f"Record count changed: expected {len(original)}, got {len(reconstructed)}."
    )

    for exp, got in zip(original, reconstructed):
        assert got.get("index") == exp["index"], (
            f"index mismatch: expected {exp['index']}, got {got.get('index')}."
        )
        assert isinstance(got.get("index"), int), (
            f"index for record {exp['index']} must be an integer, got {type(got.get('index'))}."
        )
        assert got.get("question") == exp["question"], (
            f"question mismatch for record {exp['index']}."
        )
        assert got.get("expected_output") == exp["expected_output"], (
            f"expected_output mismatch for record {exp['index']}."
        )
        assert got.get("contexts") == exp["contexts"], (
            f"contexts corrupted/truncated for record {exp['index']} "
            f"(expected len {len(_compact(exp['contexts']))} serialized chars)."
        )
        assert got.get("conversation_history") == exp["conversation_history"], (
            f"conversation_history corrupted/truncated for record {exp['index']}."
        )


def test_export_report_contents(pipeline_run):
    records = pipeline_run["records"]
    report = _extract_report(pipeline_run["export"].stdout)

    assert report.get("operation") == "export", (
        f"export report 'operation' should be 'export', got {report.get('operation')!r}."
    )
    assert report.get("record_count") == len(records), (
        f"export report 'record_count' should be {len(records)}, got {report.get('record_count')!r}."
    )

    expected_max = _expected_max_field_chars(records)
    assert report.get("max_field_chars") == expected_max, (
        f"export report 'max_field_chars' should be {expected_max}, got {report.get('max_field_chars')!r}."
    )

    limit = report.get("field_size_limit")
    assert isinstance(limit, int) and limit > expected_max, (
        f"export report 'field_size_limit' ({limit!r}) must be an integer greater "
        f"than max_field_chars ({expected_max})."
    )

    expected_checksums = _expected_checksums(records)
    assert report.get("checksums") == expected_checksums, (
        "export report 'checksums' do not match the SHA-256 digests of the "
        "compact-JSON field values computed from the input dataset."
    )


def test_import_report_contents(pipeline_run):
    records = pipeline_run["records"]
    report = _extract_report(pipeline_run["import"].stdout)

    assert report.get("operation") == "import", (
        f"import report 'operation' should be 'import', got {report.get('operation')!r}."
    )
    assert report.get("record_count") == len(records), (
        f"import report 'record_count' should be {len(records)}, got {report.get('record_count')!r}."
    )

    expected_checksums = _expected_checksums(records)
    assert report.get("checksums") == expected_checksums, (
        "import report 'checksums' do not match the SHA-256 digests computed from "
        "the reconstructed records; the values did not survive the CSV round-trip intact."
    )
