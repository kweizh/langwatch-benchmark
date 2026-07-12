import gzip
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from google.protobuf.json_format import MessageToDict
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest


class MockCollector(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        # Handle gzip-compressed payloads
        content_encoding = self.headers.get('Content-Encoding', '')
        if 'gzip' in content_encoding:
            post_data = gzip.decompress(post_data)

        # Decode protobuf to dict, then write as JSON
        request = ExportTraceServiceRequest()
        request.ParseFromString(post_data)
        payload = MessageToDict(request)

        with open('/home/user/myproject/payload.json', 'w') as f:
            json.dump(payload, f, indent=2)

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')


if __name__ == '__main__':
    server = HTTPServer(('localhost', 8080), MockCollector)
    server.serve_forever()
