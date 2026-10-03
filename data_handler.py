"""lib/data_handler.py - storage layer.

Backends (chosen automatically):
  * kv         : Upstash Redis / Vercel KV over REST (urllib, stdlib only) -> persistent on Vercel
  * tmp-files  : JSON files in /tmp on Vercel (EPHEMERAL - resets on cold start)
  * files      : JSON files in ./data when running locally
"""
import hashlib
import hmac
import http.client
import json
import os
import secrets
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
ON_VERCEL = bool(os.environ.get("VERCEL"))
DATA_DIR = os.environ.get("INVENTORY_DATA_DIR") or (
    "/tmp/inventory" if ON_VERCEL else os.path.join(ROOT, "data"))
KV_URL = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL") or ""
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN") or ""
KV_PREFIX = "inventory:"
PBKDF2_ROUNDS = 200_000
MAX_AUDIT = 5000

COLLECTIONS = {
    "users": dict, "products": dict, "suppliers": dict, "purchase_orders": dict,
    "stock_movements": list, "audit_log": list,
    "meta": lambda: {"counters": {}},
    # Advanced inventory collections: warehouses, transfers, lots and stock counts.
    "warehouses": dict, "warehouse_stock": dict, "transfers": dict,
    "stock_counts": dict, "lots": dict,
}


class StorageError(Exception):
    """Raised when data cannot be read or written safely."""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def backend_name() -> str:
    if KV_URL and KV_TOKEN:
        return "kv"
    return "tmp-files" if ON_VERCEL else "files"


# ------------------------------------------------------------ raw backends
def _kv(command: list):
    request = urllib.request.Request(
        KV_URL, data=json.dumps(command).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {KV_TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=8) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise StorageError(f"KV request failed: {exc}")
    if not isinstance(body, dict) or "error" in body:
        raise StorageError("KV returned an error")
    return body.get("result")


def _read_raw(names: list) -> list:
    if backend_name() == "kv":
        result = _kv(["MGET"] + [KV_PREFIX + n for n in names])
        if not isinstance(result, list) or len(result) != len(names):
            raise StorageError("Unexpected KV response")
        return result
    out = []
    for name in names:
        try:
            with open(os.path.join(DATA_DIR, name + ".json"), "r", encoding="utf-8") as fh:
                out.append(fh.read())
        except FileNotFoundError:
            out.append(None)
        except OSError as exc:
            raise StorageError(f"Cannot read {name}: {exc}")
    return out


def _write_raw(name: str, text: str) -> None:
    if backend_name() == "kv":
        _kv(["SET", KV_PREFIX + name, text])
        return
    path = os.path.join(DATA_DIR, name + ".json")
    tmp = path + ".tmp"
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)                      # atomic swap
    except OSError as exc:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise StorageError(f"Cannot write {name}: {exc}")


# ------------------------------------------------------------ public API
def load_all():
    """Return (db, warnings). Raises StorageError if storage is unreachable
    (so we never overwrite real data with empty defaults after a read failure)."""
    names = list(COLLECTIONS)
    raws = _read_raw(names)
    db, warnings = {}, []
    for name, raw in zip(names, raws):
        default = COLLECTIONS[name]()
        if raw is None:
            db[name] = default
            continue
        try:
            data = json.loads(raw)
            if not isinstance(data, type(default)):
                raise ValueError("wrong type")
            db[name] = data
        except ValueError:
            warnings.append(f"'{name}' was corrupt and was backed up to '{name}.corrupt'.")
            try:
                _write_raw(name + ".corrupt", raw)
            except StorageError:
                pass
            db[name] = default
    return db, warnings


def persist(db: dict, *names: str) -> bool:
    """Save the named collections (all if none given). True only if all saved."""
    targets = names if names else tuple(COLLECTIONS)
    try:
        for name in targets:
            _write_raw(name, json.dumps(db[name], ensure_ascii=False))
        return True
    except (StorageError, TypeError, ValueError, KeyError):
        return False


def next_id(db: dict, prefix: str, width: int = 4) -> str:
    counters = db["meta"].setdefault("counters", {})
    counters[prefix] = int(counters.get(prefix, 0)) + 1
    return f"{prefix}-{counters[prefix]:0{width}d}"


# ------------------------------------------------------------ passwords
def hash_password(password: str, salt_hex: str = "") -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2${PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, _, salt_hex, _ = stored.split("$")
        return hmac.compare_digest(hash_password(password, salt_hex), stored)
    except (ValueError, AttributeError):
        return False


# ------------------------------------------------------------ audit
def append_audit(db: dict, username: str, action: str, entity: str,
                 entity_id: str, before=None, after=None) -> None:
    db["audit_log"].append({
        "id": next_id(db, "AUD"), "timestamp": now_iso(), "user": username,
        "action": action, "entity": entity, "entity_id": entity_id,
        "before": before, "after": after,
    })
    if len(db["audit_log"]) > MAX_AUDIT:
        del db["audit_log"][: len(db["audit_log"]) - MAX_AUDIT]
