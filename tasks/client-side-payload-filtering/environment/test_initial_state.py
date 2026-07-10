import os
import pytest

PROJECT_DIR = "/home/user/myproject"

def test_langwatch_sdk_importable():
    try:
        import langwatch
    except ImportError:
        pytest.fail("langwatch SDK is not importable.")

def test_project_dir_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."

def test_run_script_exists():
    script_path = os.path.join(PROJECT_DIR, "run.py")
    assert os.path.isfile(script_path), f"Script file {script_path} does not exist."
