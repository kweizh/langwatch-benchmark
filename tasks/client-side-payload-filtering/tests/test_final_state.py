import os
import subprocess
import json
import pytest
import time
import requests

PROJECT_DIR = "/home/user/myproject"
PAYLOAD_FILE = os.path.join(PROJECT_DIR, "payload.json")

@pytest.fixture(scope="module", autouse=True)
def mock_collector():
    """Start the mock collector server."""
    collector_script = os.path.join(PROJECT_DIR, "mock_collector.py")
    if os.path.exists(PAYLOAD_FILE):
        os.remove(PAYLOAD_FILE)

    proc = subprocess.Popen(["python3", collector_script], cwd=PROJECT_DIR)

    # Wait for server to start
    for _ in range(10):
        try:
            r = requests.get("http://localhost:8080/health")
            if r.status_code == 200:
                break
        except requests.exceptions.ConnectionError:
            time.sleep(0.5)

    yield
    proc.terminate()
    proc.wait()

def test_run_script_executes_successfully():
    """Run the script and verify it exits with 0."""
    result = subprocess.run(
        ["python3", "run.py"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True
    )
    assert result.returncode == 0, f"Script failed to execute. stderr: {result.stderr}"

def test_payload_file_exists():
    """Check that the mock collector created the payload.json file."""
    assert os.path.isfile(PAYLOAD_FILE), f"Expected payload file at {PAYLOAD_FILE} was not created."

def test_payload_document_is_truncated():
    """Parse payload.json and ensure the large document string is truncated to 1000 characters."""
    with open(PAYLOAD_FILE, "r") as f:
        payload_content = f.read()

    expected_truncated = "A" * 1000
    unexpected_large = "A" * 1001

    assert expected_truncated in payload_content, "The truncated document string ('A' * 1000) was not found in the payload."
    assert unexpected_large not in payload_content, "The document string was not truncated correctly; found a string larger than 1000 characters."
