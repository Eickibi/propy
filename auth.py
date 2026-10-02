"""lib/auth.py - stateless signed tokens + role-based access control."""
import base64
import hashlib
import hmac
import json
import os
import time

SECRET = os.environ.get("SECRET_KEY", "")
TOKEN_TTL = 8 * 3600

PERMISSIONS = {
    "products.view": ("admin", "staff", "customer"),
    "products.view_cost": ("admin", "staff"),
    "products.write": ("admin", "staff"),
    "products.delete": ("admin",),
    "stock.move": ("admin", "staff"),
    "stock.card": ("admin", "staff"),
    "suppliers.view": ("admin", "staff"),
    "suppliers.write": ("admin", "staff"),
    "suppliers.delete": ("admin",),
    "po.view": ("admin", "staff"),
    "po.write": ("admin", "staff"),
    "reports.view": ("admin", "staff"),
    "audit.view": ("admin",),
    "users.manage": ("admin",),
}


def secret_is_default() -> bool:
    return SECRET == ""


def can(role: str, permission: str) -> bool:
    return role in PERMISSIONS.get(permission, ())


def permissions_for(role: str) -> list:
    return sorted(p for p, roles in PERMISSIONS.items() if role in roles)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload_b64: str) -> str:
    key = (SECRET or "dev-only-secret-change-me").encode("utf-8")
    return _b64(hmac.new(key, payload_b64.encode("ascii"), hashlib.sha256).digest())


def make_token(username: str, role: str) -> str:
    payload = _b64(json.dumps({"u": username, "r": role, "exp": int(time.time()) + TOKEN_TTL}).encode())
    return f"{payload}.{_sign(payload)}"


def read_token(token: str):
    """Return {'u','r','exp'} or None if invalid/expired."""
    try:
        payload_b64, signature = token.split(".")
        if not hmac.compare_digest(signature, _sign(payload_b64)):
            return None
        data = json.loads(_unb64(payload_b64))
        if not isinstance(data, dict) or data.get("exp", 0) < time.time():
            return None
        return data
    except (ValueError, AttributeError, TypeError):
        return None
