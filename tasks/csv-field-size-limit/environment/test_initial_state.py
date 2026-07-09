import os
import subprocess

import pytest

PROJECT_DIR = "/home/user/langwatch-csv-pipeline"
VENV_PYTHON = os.path.join(PROJECT_DIR, ".venv", "bin", "python")


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"Expected project directory {PROJECT_DIR} to exist before the task starts."
    )


def test_uv_venv_python_exists():
    assert os.path.isfile(VENV_PYTHON), (
        f"Expected a uv-managed virtual environment interpreter at {VENV_PYTHON}. "
        "LangWatch must be installed into a uv venv (per the research plan)."
    )


def test_langwatch_importable_in_venv():
    result = subprocess.run(
        [VENV_PYTHON, "-c", "import langwatch"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "The 'langwatch' SDK is not importable in the project's uv venv. "
        f"stderr:\n{result.stderr}"
    )


def test_pandas_importable_in_venv():
    result = subprocess.run(
        [VENV_PYTHON, "-c", "import pandas"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "The 'pandas' package is not importable in the project's uv venv; "
        f"LangWatch datasets are pandas-backed. stderr:\n{result.stderr}"
    )
