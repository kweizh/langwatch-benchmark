import os
import subprocess

import pytest

PROJECT_DIR = "/home/user/project"
VENV_PYTHON = "/home/user/project/.venv/bin/python"


def test_project_dir_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_venv_python_exists():
    assert os.path.isfile(VENV_PYTHON), (
        f"Virtual environment interpreter {VENV_PYTHON} does not exist. "
        "The task expects langwatch/dspy installed in a uv-managed venv at "
        "/home/user/project/.venv."
    )


def test_langwatch_importable_in_venv():
    result = subprocess.run(
        [VENV_PYTHON, "-c", "import langwatch"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "Failed to `import langwatch` using the project venv interpreter. "
        f"stderr:\n{result.stderr}"
    )


def test_dspy_importable_in_venv():
    result = subprocess.run(
        [VENV_PYTHON, "-c", "import dspy"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "Failed to `import dspy` using the project venv interpreter. "
        f"stderr:\n{result.stderr}"
    )


def test_langwatch_dspy_visualizer_available():
    # The task is specifically about the langwatch.dspy visualizer, so the
    # submodule must be importable in the starting environment.
    result = subprocess.run(
        [VENV_PYTHON, "-c", "import langwatch.dspy"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "Failed to `import langwatch.dspy` using the project venv interpreter. "
        f"stderr:\n{result.stderr}"
    )


def test_simba_bug_reproduces_in_initial_state():
    # Baseline: without any fix, initializing the langwatch DSPy tracker with a
    # SIMBA optimizer must raise the documented ValueError. This confirms the
    # starting environment actually contains the bug the task must fix.
    script = (
        "import dspy\n"
        "from dspy.teleprompt import SIMBA\n"
        "import langwatch.dspy\n"
        "opt = SIMBA(metric=lambda example, pred, trace=None: 1.0)\n"
        "try:\n"
        "    langwatch.dspy.langwatch_dspy.patch_optimizer(opt)\n"
        "except ValueError as e:\n"
        "    assert 'SIMBA is not supported' in str(e), str(e)\n"
        "    print('REPRODUCED')\n"
        "else:\n"
        "    raise SystemExit('SIMBA unexpectedly supported in initial state')\n"
    )
    result = subprocess.run(
        [VENV_PYTHON, "-c", script],
        capture_output=True,
        text=True,
        cwd=PROJECT_DIR,
    )
    assert result.returncode == 0 and "REPRODUCED" in result.stdout, (
        "Expected the SIMBA ValueError to reproduce in the initial state. "
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
