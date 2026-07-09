import importlib
import os
import shutil

import pytest

PROJECT_DIR = "/home/user/project"


def test_project_dir_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_uv_available():
    assert shutil.which("uv") is not None, "uv is not available in PATH."


def test_langwatch_importable():
    try:
        importlib.import_module("langwatch")
    except Exception as exc:  # pragma: no cover - failure path
        pytest.fail(f"Failed to import the langwatch SDK: {exc}")


def test_langwatch_domain_importable():
    try:
        importlib.import_module("langwatch.domain")
    except Exception as exc:  # pragma: no cover - failure path
        pytest.fail(f"Failed to import langwatch.domain (needed for exclude rules): {exc}")


def test_opentelemetry_sdk_importable():
    try:
        importlib.import_module("opentelemetry.trace")
        importlib.import_module("opentelemetry.sdk.trace")
    except Exception as exc:  # pragma: no cover - failure path
        pytest.fail(f"Failed to import the OpenTelemetry SDK: {exc}")


def test_otlp_http_exporter_importable():
    try:
        importlib.import_module(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter"
        )
    except Exception as exc:  # pragma: no cover - failure path
        pytest.fail(f"Failed to import the OTLP/HTTP trace exporter: {exc}")
