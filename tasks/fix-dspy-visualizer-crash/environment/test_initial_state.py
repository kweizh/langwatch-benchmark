import os
import pytest

PROJECT_DIR = "/home/user/myproject"

def test_dspy_and_langwatch_available():
    try:
        import dspy
    except ImportError:
        pytest.fail("dspy is not installed or importable.")

    try:
        import langwatch
    except ImportError:
        pytest.fail("langwatch is not installed or importable.")

def test_project_dir_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."

def test_script_exists():
    script_path = os.path.join(PROJECT_DIR, "optimize.py")
    assert os.path.isfile(script_path), f"Script file {script_path} does not exist."

def test_initial_script_uses_simba():
    script_path = os.path.join(PROJECT_DIR, "optimize.py")
    with open(script_path, "r") as f:
        content = f.read()
    assert "SIMBA" in content, "Expected initial optimize.py to use the SIMBA optimizer."
