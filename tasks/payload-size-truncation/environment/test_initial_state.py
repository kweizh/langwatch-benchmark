import importlib.util
import json
import os
import shutil

PROJECT_DIR = "/home/user/project"
CORPUS_PATH = os.path.join(PROJECT_DIR, "data", "documents.json")


def test_langwatch_sdk_importable():
    assert (
        importlib.util.find_spec("langwatch") is not None
    ), "The LangWatch Python SDK ('langwatch') must be importable in the environment."


def test_opentelemetry_sdk_importable():
    assert (
        importlib.util.find_spec("opentelemetry") is not None
    ), "The OpenTelemetry SDK ('opentelemetry') must be importable in the environment."


def test_uv_available():
    assert shutil.which("uv") is not None, "The 'uv' package manager must be available in PATH."


def test_project_dir_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_corpus_file_exists():
    assert os.path.isfile(CORPUS_PATH), f"Corpus file {CORPUS_PATH} does not exist."


def test_corpus_is_valid_document_list():
    with open(CORPUS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, list), "Corpus file must contain a JSON array of documents."
    assert len(data) >= 2, "Corpus must contain at least two documents."
    for item in data:
        assert isinstance(item, dict), "Each corpus entry must be a JSON object."
        for field in ("document_id", "chunk_id", "content"):
            assert field in item, f"Each corpus document must contain the '{field}' field."
            assert isinstance(item[field], str), f"Corpus field '{field}' must be a string."


def test_corpus_exceeds_collector_limit():
    with open(CORPUS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    total_bytes = sum(len(item["content"].encode("utf-8")) for item in data)
    assert total_bytes > 1_000_000, (
        "The combined raw document content must exceed the 1MB collector limit "
        f"so that truncation is required (got {total_bytes} bytes)."
    )
