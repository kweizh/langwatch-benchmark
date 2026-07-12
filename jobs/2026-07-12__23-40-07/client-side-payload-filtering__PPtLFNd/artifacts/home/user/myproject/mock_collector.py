from http.server import BaseHTTPRequestHandler, HTTPServer

class MockCollector(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        with open('/home/user/myproject/payload.json', 'w') as f:
            f.write(post_data.decode('utf-8'))
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
