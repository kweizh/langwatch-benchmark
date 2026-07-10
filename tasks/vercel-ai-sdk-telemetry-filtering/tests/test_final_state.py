import os
import subprocess
import time
import socket
import pytest
from xprocess import ProcessStarter

PROJECT_DIR = "/home/user/myproject"
LOG_FILE = os.path.join(PROJECT_DIR, "telemetry.log")

MOCK_SERVER_CODE = """
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class RequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        with open('/home/user/myproject/telemetry.log', 'a') as f:
            f.write(post_data.decode('utf-8') + '\\n')
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

if __name__ == '__main__':
    server = HTTPServer(('localhost', 8080), RequestHandler)
    print("Starting mock server on port 8080")
    server.serve_forever()
"""

@pytest.fixture(scope="session", autouse=True)
def setup_environment():
    """Run npm install before tests."""
    subprocess.run(["npm", "install"], cwd=PROJECT_DIR, capture_output=True)

@pytest.fixture(scope="session")
def start_mock_server(xprocess):
    with open("/tmp/mock_server.py", "w") as f:
        f.write(MOCK_SERVER_CODE)

    class Starter(ProcessStarter):
        name = "mock_server"
        args = ["python3", "/tmp/mock_server.py"]
        env = os.environ.copy()
        timeout = 30
        terminate_on_interrupt = True

        def startup_check(self):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                return s.connect_ex(("localhost", 8080)) == 0

    xprocess.ensure(Starter.name, Starter)
    yield
    xprocess.getinfo(Starter.name).terminate()

def run_script(prompt: str):
    env = os.environ.copy()
    env["LANGWATCH_ENDPOINT"] = "http://localhost:8080"
    env["LANGWATCH_API_KEY"] = "dummy-api-key"
    env["LANGWATCH_PROJECT_ID"] = "dummy-project"

    result = subprocess.run(
        ["npx", "tsx", "run.ts", "--prompt", prompt],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True
    )
    return result

def test_safe_prompt(start_mock_server):
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)

    result = run_script("Hello world")
    assert result.returncode == 0, f"Script failed with error: {result.stderr}"

    # Wait for telemetry to be written
    time.sleep(1)

    assert os.path.exists(LOG_FILE), "Telemetry log file was not created by the mock server."
    with open(LOG_FILE, "r") as f:
        log_content = f.read()

    assert "Hello world" in log_content, "Expected safe prompt text 'Hello world' not found in telemetry logs."

def test_sensitive_prompt(start_mock_server):
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)

    result = run_script("My password is SECRET_TOKEN")
    assert result.returncode == 0, f"Script failed with error: {result.stderr}"

    # Wait for telemetry to be written
    time.sleep(1)

    assert os.path.exists(LOG_FILE), "Telemetry log file was not created by the mock server."
    with open(LOG_FILE, "r") as f:
        log_content = f.read()

    assert "SECRET_TOKEN" not in log_content, "Sensitive data 'SECRET_TOKEN' was found in telemetry logs. Filtering failed."
    assert "[REDACTED]" in log_content, "Expected redaction marker '[REDACTED]' not found in telemetry logs."
