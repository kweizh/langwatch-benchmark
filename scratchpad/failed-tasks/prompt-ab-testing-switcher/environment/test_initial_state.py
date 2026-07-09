import os
import shutil

PROJECT_DIR = "/home/user/myproject"


def test_project_dir_exists():
    assert os.path.isdir(PROJECT_DIR), (
        f"Expected the project directory {PROJECT_DIR} to exist before the task starts."
    )


def test_node_available():
    assert shutil.which("node") is not None, (
        "node binary not found in PATH; a Node.js runtime is required for this TypeScript task."
    )


def test_npm_available():
    assert shutil.which("npm") is not None, (
        "npm binary not found in PATH; npm is required to install dependencies and run the 'switch' script."
    )


def test_langwatch_cli_available():
    assert shutil.which("langwatch") is not None, (
        "langwatch CLI not found in PATH; the LangWatch Prompts CLI is required to scaffold prompt variants."
    )
