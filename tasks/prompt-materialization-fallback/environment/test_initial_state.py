import os
import shutil

PROJECT_DIR = "/home/user/myproject"


def test_project_dir_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"Project directory {PROJECT_DIR} does not exist."
    )


def test_langwatch_cli_available():
    assert shutil.which("langwatch") is not None, (
        "The 'langwatch' CLI was not found in PATH."
    )


def test_uv_available():
    assert shutil.which("uv") is not None, (
        "The 'uv' package manager was not found in PATH. "
        "It is required to install LangWatch Python packages."
    )


def test_node_available():
    assert shutil.which("node") is not None, (
        "Node.js runtime was not found in PATH; it is required by the LangWatch CLI."
    )
