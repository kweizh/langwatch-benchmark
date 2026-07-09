import os
import subprocess

import pytest

PROJECT_DIR = "/home/user/dspy-serialization"
VENV_PYTHON = os.path.join(PROJECT_DIR, ".venv", "bin", "python")

REPRO_SNIPPET = (
    "import json, sys\n"
    "sys.path.insert(0, '/home/user/dspy-serialization')\n"
    "import qa_program\n"
    "from langwatch.dspy import SerializableAndPydanticEncoder\n"
    "step = qa_program.build_optimizer_step()\n"
    "assert all(hasattr(step, f) for f in ['name','predictor','demos','records']), 'missing fields'\n"
    "try:\n"
    "    json.dumps(step, cls=SerializableAndPydanticEncoder)\n"
    "    print('NO_ERROR')\n"
    "except TypeError as e:\n"
    "    print('MOCKVALSER' if 'MockValSer' in str(e) else 'OTHER:' + str(e))\n"
)


def test_project_directory_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"Expected project directory {PROJECT_DIR} to exist before the task starts."
    )


def test_uv_venv_python_exists():
    assert os.path.isfile(VENV_PYTHON), (
        f"Expected a uv-managed virtual environment interpreter at {VENV_PYTHON}. "
        "langwatch/dspy/pydantic must be installed into a uv venv (per the research plan)."
    )


def test_langwatch_importable_in_venv():
    result = subprocess.run(
        [VENV_PYTHON, "-c", "import langwatch"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"The 'langwatch' SDK is not importable in the project's uv venv. stderr:\n{result.stderr}"
    )


def test_dspy_importable_in_venv():
    result = subprocess.run(
        [VENV_PYTHON, "-c", "import dspy"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"The 'dspy' library is not importable in the project's uv venv. stderr:\n{result.stderr}"
    )


def test_pydantic_v2_in_venv():
    result = subprocess.run(
        [VENV_PYTHON, "-c", "import pydantic; print(pydantic.VERSION)"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"The 'pydantic' package is not importable in the project's uv venv. stderr:\n{result.stderr}"
    )
    assert result.stdout.strip().startswith("2."), (
        f"Pydantic v2 is required to reproduce the bug, found {result.stdout.strip()!r}."
    )


def test_buggy_encoder_present_in_venv():
    result = subprocess.run(
        [VENV_PYTHON, "-c", "from langwatch.dspy import SerializableAndPydanticEncoder"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "langwatch.dspy.SerializableAndPydanticEncoder must exist; it is the encoder under repair. "
        f"stderr:\n{result.stderr}"
    )


def test_qa_program_fixture_present():
    path = os.path.join(PROJECT_DIR, "qa_program.py")
    assert os.path.isfile(path), f"Reproduction fixture {path} does not exist."


def test_initial_state_reproduces_mockvalser_bug():
    """The environment starts broken: LangWatch's stock encoder crashes with MockValSer."""
    result = subprocess.run(
        [VENV_PYTHON, "-c", REPRO_SNIPPET],
        capture_output=True, text=True, cwd=PROJECT_DIR,
    )
    assert result.returncode == 0, (
        f"The reproduction probe itself failed to run.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "MOCKVALSER" in result.stdout, (
        "Expected the stock encoder to fail with the MockValSer TypeError from Issue #468, "
        f"but the probe reported: {result.stdout.strip()!r}"
    )
