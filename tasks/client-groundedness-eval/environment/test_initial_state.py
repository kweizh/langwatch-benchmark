import importlib
import os
import shutil

import pytest

PROJECT_DIR = "/home/user/project"


def test_project_dir_exists():
    assert os.path.isdir(PROJECT_DIR), f"Project directory {PROJECT_DIR} does not exist."


def test_uv_available():
    assert shutil.which("uv") is not None, "uv is not available in PATH."


def test_pipeline_stub_present():
    stub = os.path.join(PROJECT_DIR, "pipeline.py")
    assert os.path.isfile(stub), f"Expected stub module {stub} to be present."


def test_main_stub_present():
    stub = os.path.join(PROJECT_DIR, "main.py")
    assert os.path.isfile(stub), f"Expected CLI entrypoint {stub} to be present."


def test_langwatch_importable():
    try:
        importlib.import_module("langwatch")
    except Exception as exc:  # pragma: no cover - failure path
        pytest.fail(f"Failed to import the langwatch SDK: {exc}")


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


def test_opentelemetry_proto_importable():
    try:
        importlib.import_module(
            "opentelemetry.proto.collector.trace.v1.trace_service_pb2"
        )
    except Exception as exc:  # pragma: no cover - failure path
        pytest.fail(
            f"Failed to import opentelemetry-proto (needed to decode OTLP exports): {exc}"
        )
