import importlib.util
import os
import shutil

PROJECT_DIR = "/home/user/project"


def test_project_dir_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_uv_available():
    assert shutil.which("uv") is not None, "uv is not installed or not found in PATH."


def test_langwatch_importable():
    spec = importlib.util.find_spec("langwatch")
    assert spec is not None, "The langwatch Python SDK is not importable in the environment."


def test_opentelemetry_sdk_importable():
    spec = importlib.util.find_spec("opentelemetry.sdk")
    assert spec is not None, "The OpenTelemetry SDK (a langwatch dependency) is not importable."
