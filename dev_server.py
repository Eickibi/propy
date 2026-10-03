"""dev_server.py - run the web UI + API locally:  python dev_server.py  ->  http://localhost:8000"""
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from api.index import handler as ApiHandler

PUBLIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")


class DevHandler(ApiHandler):
    def do_GET(self):
        if self.path.startswith("/api"):
            return self._go()
        try:
            with open(os.path.join(PUBLIC, "index.html"), "rb") as fh:
                body = fh.read()
        except OSError:
            body = b"public/index.html not found"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Serving on http://localhost:{port}  (Ctrl+C to stop)")
    try:
        HTTPServer(("0.0.0.0", port), DevHandler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
