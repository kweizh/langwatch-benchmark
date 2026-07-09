import csv
import importlib
import json
import os
import shutil

import pytest

PROJECT_DIR = "/home/user/project"
DATASET_PATH = os.path.join(PROJECT_DIR, "data", "qa_dataset.csv")
KB_PATH = os.path.join(PROJECT_DIR, "data", "knowledge_base.json")


def test_project_dir_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_uv_available():
    assert shutil.which("uv") is not None, "uv is not available in PATH."


def test_langwatch_importable():
    try:
        importlib.import_module("langwatch")
    except Exception as exc:  # pragma: no cover - failure path
        pytest.fail(f"Failed to import the langwatch SDK: {exc}")


def test_langwatch_evaluation_module_importable():
    try:
        importlib.import_module("langwatch.evaluation")
    except Exception as exc:  # pragma: no cover - failure path
        pytest.fail(f"Failed to import langwatch.evaluation (batch evaluation API): {exc}")


def test_dataset_csv_exists_and_has_questions():
    assert os.path.isfile(DATASET_PATH), f"Seeded dataset {DATASET_PATH} does not exist."
    with open(DATASET_PATH, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) > 0, f"Dataset {DATASET_PATH} should contain at least one row."
    assert "question" in rows[0], (
        f"Dataset {DATASET_PATH} must have a 'question' column; got {list(rows[0].keys())}."
    )


def test_knowledge_base_json_exists_and_has_documents():
    assert os.path.isfile(KB_PATH), f"Seeded knowledge base {KB_PATH} does not exist."
    with open(KB_PATH) as f:
        docs = json.load(f)
    assert isinstance(docs, list) and len(docs) > 0, (
        f"Knowledge base {KB_PATH} should be a non-empty JSON list of documents."
    )
    assert "content" in docs[0], (
        f"Each knowledge base document must have a 'content' field; got {list(docs[0].keys())}."
    )
