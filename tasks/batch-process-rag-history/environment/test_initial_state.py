import os
import shutil

PROJECT_DIR = "/home/user/myproject"

def test_project_dir_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."

def test_uv_binary_available():
    assert shutil.which("uv") is not None, "uv binary not found in PATH."

def test_rag_history_csv_exists():
    csv_path = os.path.join(PROJECT_DIR, "rag_history.csv")
    assert os.path.isfile(csv_path), f"CSV file {csv_path} does not exist."
