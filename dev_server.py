"""dev_server.py - run web UI + API locally:  python dev_server.py  ->  http://localhost:8000"""
import os
from http.server import HTTPServer

from api.index import handler

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Serving on http://localhost:{port}  (Ctrl+C to stop)")
    try:
        HTTPServer(("0.0.0.0", port), handler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
