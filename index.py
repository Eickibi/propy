"""index.py - Vercel entrypoint (BaseHTTPRequestHandler). Serves the UI at / and the API at /api/*."""
import json
import os
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, unquote, urlsplit

import auth
import data_handler as dh
import services as svc
import ui

MAX_BODY = 1_000_000


class Ctx:
    def __init__(self, db, user, args, query, body):
        self.db, self.user, self.args, self.query, self.body = db, user, args, query, body


# (method, path regex, permission | "nodb" | "public" | "auth", handler)
ROUTES = [
    ("GET", r"/health", "nodb", lambda c: svc.health()),
    ("POST", r"/login", "public", lambda c: svc.login(c.db, c.body.get("username"), c.body.get("password"))),
    ("GET", r"/me", "auth", lambda c: svc.me(c.user)),
    ("POST", r"/password", "auth", lambda c: svc.change_password(c.db, c.user, c.body)),
    ("GET", r"/dashboard", "reports.view", lambda c: svc.dashboard(c.db, c.user)),
    ("GET", r"/products", "products.view", lambda c: svc.list_products(c.db, c.user, c.query)),
    ("POST", r"/products", "products.write", lambda c: svc.create_product(c.db, c.user, c.body)),
    ("GET", r"/products/([^/]+)", "products.view", lambda c: svc.get_product(c.db, c.user, c.args[0])),
    ("PUT", r"/products/([^/]+)", "products.write", lambda c: svc.update_product(c.db, c.user, c.args[0], c.body)),
    ("DELETE", r"/products/([^/]+)", "products.delete", lambda c: svc.delete_product(c.db, c.user, c.args[0])),
    ("GET", r"/products/([^/]+)/card", "stock.card", lambda c: svc.stock_card(c.db, c.user, c.args[0], c.query)),
    ("POST", r"/stock", "stock.move", lambda c: svc.stock_move(c.db, c.user, c.body)),
    ("GET", r"/low-stock", "reports.view", lambda c: svc.low_stock_report(c.db, c.user)),
    ("GET", r"/suppliers", "suppliers.view", lambda c: svc.list_suppliers(c.db, c.user, c.query)),
    ("POST", r"/suppliers", "suppliers.write", lambda c: svc.create_supplier(c.db, c.user, c.body)),
    ("PUT", r"/suppliers/([^/]+)", "suppliers.write", lambda c: svc.update_supplier(c.db, c.user, c.args[0], c.body)),
    ("DELETE", r"/suppliers/([^/]+)", "suppliers.delete", lambda c: svc.delete_supplier(c.db, c.user, c.args[0])),
    ("GET", r"/purchase-orders", "po.view", lambda c: svc.list_pos(c.db, c.user, c.query)),
    ("POST", r"/purchase-orders", "po.write", lambda c: svc.create_po(c.db, c.user, c.body)),
    ("POST", r"/purchase-orders/([^/]+)/(send|receive|cancel)", "po.write",
     lambda c: svc.po_action(c.db, c.user, c.args[0], c.args[1])),
    ("GET", r"/reports/valuation", "reports.view", lambda c: svc.valuation_report(c.db, c.user, c.query)),
    ("GET", r"/audit", "audit.view", lambda c: svc.list_audit(c.db, c.user, c.query)),
    ("GET", r"/users", "users.manage", lambda c: svc.list_users(c.db, c.user, c.query)),
    ("POST", r"/users", "users.manage", lambda c: svc.create_user(c.db, c.user, c.body)),
    ("PUT", r"/users/([^/]+)", "users.manage", lambda c: svc.update_user(c.db, c.user, c.args[0], c.body)),
]
COMPILED = [(m, re.compile("^" + p + "$"), perm, fn) for m, p, perm, fn in ROUTES]


def _parse_body(raw: bytes) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise svc.ServiceError("Request body must be valid JSON", 400)
    if not isinstance(data, dict):
        raise svc.ServiceError("Request body must be a JSON object", 400)
    return data


def _authenticate(db: dict, header: str) -> dict:
    token = header[7:] if header.startswith("Bearer ") else ""
    data = auth.read_token(token)
    user = db["users"].get(data["u"]) if data else None
    if user is None or not user.get("active") or user.get("role") != data["r"]:
        raise svc.ServiceError("Authentication required", 401)
    return user


def _run(perm, fn, match, query, auth_header, raw_body):
    try:
        body = _parse_body(raw_body)
        if perm == "nodb":
            return 200, fn(Ctx(None, None, match.groups(), query, body))
        db, _warnings = dh.load_all()
        svc.bootstrap(db)
        user = None
        if perm != "public":
            user = _authenticate(db, auth_header)
            if perm != "auth" and not auth.can(user["role"], perm):
                raise svc.ServiceError("Forbidden", 403)
        return 200, fn(Ctx(db, user, match.groups(), query, body))
    except svc.ServiceError as exc:
        return exc.status, {"error": exc.message, "details": exc.details}
    except dh.StorageError:
        return 503, {"error": "Storage unavailable"}
    except Exception:                                   # never leak a traceback
        return 500, {"error": "Internal server error"}


def dispatch(method: str, raw_path: str, auth_header: str, raw_body: bytes):
    parts = urlsplit(raw_path)
    path = unquote(parts.path)
    for prefix in ("/api/index", "/api"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break
    path = path.rstrip("/") or "/"
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    path_exists = False
    for route_method, rx, perm, fn in COMPILED:
        match = rx.match(path)
        if match is None:
            continue
        path_exists = True
        if route_method == method:
            return _run(perm, fn, match, query, auth_header, raw_body)
    return (405, {"error": "Method not allowed"}) if path_exists else (404, {"error": "Not found"})


def _index_html() -> bytes:
    return ui.HTML.encode("utf-8")


class handler(BaseHTTPRequestHandler):
    def _page(self):
        body = _index_html()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _go(self):
        if self.command == "GET" and not urlsplit(self.path).path.startswith("/api"):
            return self._page()
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            status, payload = 413, {"error": "Request body too large"}
        else:
            raw = self.rfile.read(length) if length else b""
            status, payload = dispatch(self.command, self.path, self.headers.get("Authorization", ""), raw)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_DELETE = _go


if __name__ == "__main__":                      # local run: python index.py
    from http.server import HTTPServer
    port = int(os.environ.get("PORT", "8000"))
    print(f"Serving on http://localhost:{port}  (Ctrl+C to stop)")
    try:
        HTTPServer(("0.0.0.0", port), handler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
