import os
import shutil

PROJECT_DIR = "/home/user/myproject"

def test_python3_available():
    assert shutil.which("python3") is not None, "python3 binary not found in PATH."

def test_uv_available():
    assert shutil.which("uv") is not None, "uv binary not found in PATH."

def test_project_dir_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."
