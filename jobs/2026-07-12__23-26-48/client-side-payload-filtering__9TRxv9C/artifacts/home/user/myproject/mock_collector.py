from http.server import BaseHTTPRequestHandler, HTTPServer
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from google.protobuf.json_format import MessageToJson

class MockCollector(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        try:
            # Try parsing as OTLP Protobuf
            request = ExportTraceServiceRequest()
            request.ParseFromString(post_data)
            decoded = MessageToJson(request)
        except Exception as e:
            # Fallback to UTF-8 decoding if it's already JSON
            try:
                decoded = post_data.decode('utf-8')
            except Exception:
                decoded = str(post_data)
        with open('/home/user/myproject/payload.json', 'w') as f:
            f.write(decoded)
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
