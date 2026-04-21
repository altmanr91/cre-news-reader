"""
Local HTTP server for CRE digest HTML files.
Run once; stays alive until killed. Serves the project directory on PORT.
"""
import http.server
import os

PORT = 8787
DIRECTORY = os.path.dirname(os.path.abspath(__file__))


class _Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def log_message(self, format, *args):
        pass  # suppress request logs


if __name__ == '__main__':
    with http.server.HTTPServer(('localhost', PORT), _Handler) as httpd:
        print(f"Serving {DIRECTORY} on http://localhost:{PORT}")
        httpd.serve_forever()
