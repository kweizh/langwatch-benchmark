import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)


class MockCollector(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        # The LangWatch SDK exports traces using the OpenTelemetry OTLP
        # protocol, which sends protobuf-encoded data.  Decode the protobuf
        # payload and convert it to a JSON dictionary so it can be written
        # to disk and inspected by the test harness.
        try:
            otlp_request = ExportTraceServiceRequest()
            otlp_request.ParseFromString(post_data)
            payload_dict = MessageToDict(otlp_request)
        except Exception:
            # Fallback: if the data is not protobuf (e.g. plain JSON),
            # decode it as UTF-8 text.
            payload_dict = json.loads(post_data.decode("utf-8"))

        with open("/home/user/myproject/payload.json", "w") as f:
            json.dump(payload_dict, f, indent=2)

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')


if __name__ == "__main__":
    server = HTTPServer(("localhost", 8080), MockCollector)
    server.serve_forever()