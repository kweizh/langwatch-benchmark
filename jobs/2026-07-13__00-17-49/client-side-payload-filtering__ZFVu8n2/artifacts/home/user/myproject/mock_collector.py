from http.server import BaseHTTPRequestHandler, HTTPServer
import json

from opentelemetry.proto.collector.trace.v1 import trace_service_pb2


def _any_value_to_python(av):
    """Convert an AnyValue protobuf message to a Python object."""
    kind = av.WhichOneof("value")
    if kind == "string_value":
        return av.string_value
    elif kind == "bool_value":
        return av.bool_value
    elif kind == "int_value":
        return av.int_value
    elif kind == "double_value":
        return av.double_value
    elif kind == "array_value":
        return [_any_value_to_python(v) for v in av.array_value.values]
    elif kind == "kvlist_value":
        return {kv.key: _any_value_to_python(kv.value) for kv in av.kvlist_value.values}
    elif kind == "bytes_value":
        return av.bytes_value.hex()
    return None


def _kv_list_to_dict(kv_list):
    return {kv.key: _any_value_to_python(kv.value) for kv in kv_list}


def otlp_request_to_dict(export_request):
    result = {"resource_spans": []}
    for resource_span in export_request.resource_spans:
        rs_dict = {
            "resource": {
                "attributes": _kv_list_to_dict(resource_span.resource.attributes)
            },
            "scope_spans": []
        }
        for scope_span in resource_span.scope_spans:
            ss_dict = {
                "scope": {
                    "name": scope_span.scope.name,
                    "version": scope_span.scope.version,
                },
                "spans": []
            }
            for span in scope_span.spans:
                span_dict = {
                    "trace_id": span.trace_id.hex(),
                    "span_id": span.span_id.hex(),
                    "parent_span_id": span.parent_span_id.hex(),
                    "name": span.name,
                    "kind": span.kind,
                    "start_time_unix_nano": span.start_time_unix_nano,
                    "end_time_unix_nano": span.end_time_unix_nano,
                    "attributes": _kv_list_to_dict(span.attributes),
                    "status": {
                        "code": span.status.code,
                        "message": span.status.message,
                    }
                }
                ss_dict["spans"].append(span_dict)
            rs_dict["scope_spans"].append(ss_dict)
        result["resource_spans"].append(rs_dict)
    return result


class MockCollector(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        try:
            export_request = trace_service_pb2.ExportTraceServiceRequest()
            export_request.ParseFromString(post_data)
            payload = otlp_request_to_dict(export_request)
        except Exception:
            # Fallback: try raw decode
            payload = {"raw": post_data.decode('utf-8', errors='replace')}

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

    def log_message(self, format, *args):
        pass  # suppress request logs


if __name__ == '__main__':
    server = HTTPServer(('localhost', 8080), MockCollector)
    server.serve_forever()
