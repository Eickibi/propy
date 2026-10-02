"""lib/services.py - all business logic. No print()/input(); failures raise ServiceError.

Used by both the Vercel API (api/index.py) and the local CLI (main.py).
"""
import os
import time

from . import auth, data_handler as dh, validators as V

MAX_FAILED, LOCK_SECONDS = 5, 300
MOVE_TYPES = ("INBOUND", "OUTBOUND", "ADJUSTMENT")
PO_STATUSES = ("DRAFT", "SENT", "RECEIVED", "CANCELLED")
STAFF_SORT = ("sku", "name", "category", "quantity_on_hand", "selling_price", "cost_price")
CUSTOMER_SORT = ("sku", "name", "category", "selling_price")
SAVE_COMMON = ("audit_log", "meta")


class ServiceError(Exception):
    def __init__(self, message, status=400, details=None):
        super().__init__(message)
        self.message, self.status, self.details = message, status, details or []


# ------------------------------------------------------------------ helpers
def _need(errors: list) -> None:
    if errors:
        raise ServiceError("Validation failed", 422, errors)


def _save(db: dict, *names: str) -> None:
    if not dh.persist(db, *names, *SAVE_COMMON):
        raise ServiceError("Could not save data", 503)


def _audit(db, user, action, entity, entity_id, before=None, after=None):
    dh.append_audit(db, user["username"], action, entity, entity_id, before, after)


def _qint(q: dict, key: str, default: int, lo: int, hi: int) -> int:
    try:
        return min(max(int(q.get(key, default)), lo), hi)
    except (TypeError, ValueError):
        return default


def paginate(items: list, q: dict, default_size: int = 10) -> dict:
    size = _qint(q, "page_size", default_size, 1, 100)
    pages = max(1, -(-len(items) // size))
    page = min(_qint(q, "page", 1, 1, 10**6), pages)
    start = (page - 1) * size
    return {"items": items[start:start + size], "page": page, "pages": pages,
            "total": len(items), "page_size": size}


def _sort_key(field):
    return lambda row: (row[field].lower() if isinstance(row.get(field), str) else row.get(field, 0))


def is_low(product: dict) -> bool:
    return product["active"] and product["quantity_on_hand"] <= product["reorder_point"]


def public_user(user: dict) -> dict:
    return {k: user.get(k) for k in ("username", "full_name", "role", "active", "created_at")}


def public_product(product: dict) -> dict:
    """What a customer may see: no cost, no exact quantity, no supplier."""
    view = {k: product[k] for k in ("sku", "name", "category", "unit", "selling_price")}
    view["in_stock"] = product["quantity_on_hand"] > 0
    return view


def _get_product(db, sku) -> dict:
    product = db["products"].get(str(sku).strip().upper())
    if product is None or not product["active"]:
        raise ServiceError(f"Product {sku} not found", 404)
    return product


def _get_supplier(db, supplier_id) -> dict:
    supplier = db["suppliers"].get(str(supplier_id))
    if supplier is None or not supplier["active"]:
        raise ServiceError(f"Supplier {supplier_id} not found", 404)
    return supplier


# ------------------------------------------------------------------ system
def health() -> dict:
    notes = []
    if dh.backend_name() == "tmp-files":
        notes.append("Using ephemeral /tmp storage: data resets on cold starts. Connect Upstash Redis (KV).")
    if auth.secret_is_default():
        notes.append("SECRET_KEY is not set: tokens use an insecure development key.")
    return {"status": "ok", "storage": dh.backend_name(), "warnings": notes}


def bootstrap(db: dict) -> bool:
    """First-run setup: default admin (+ optional demo data). Returns True if data was created."""
    changed = False
    if not db["users"]:
        password = os.environ.get("ADMIN_PASSWORD") or "Admin@123"
        db["users"]["admin"] = {
            "username": "admin", "password_hash": dh.hash_password(password), "role": "admin",
            "full_name": "System Administrator", "active": True, "created_at": dh.now_iso(),
        }
        dh.append_audit(db, "system", "CREATE", "user", "admin", None, {"role": "admin"})
        changed = True
    if os.environ.get("SEED_DEMO") == "1" and not db["products"] and not db["suppliers"]:
        _seed_demo(db)
        changed = True
    if changed:
        dh.persist(db)
    return changed


def _seed_demo(db: dict) -> None:
    system = {"username": "system", "role": "admin"}
    supplier_id = dh.next_id(db, "SUP")
    db["suppliers"][supplier_id] = {
        "id": supplier_id, "name": "Demo Trading Co.", "contact": "Somchai", "phone": "02-123-4567",
        "email": "sales@demo.example", "address": "Bangkok", "active": True, "created_at": dh.now_iso()}
    demo = (("DEMO-001", "USB-C Cable 1m", "Accessories", "pcs", 45, 99, 20, 50),
            ("DEMO-002", "Wireless Mouse", "Peripherals", "pcs", 180, 350, 10, 8),
            ("DEMO-003", "A4 Paper 500 sheets", "Stationery", "pack", 95, 140, 15, 40))
    for sku, name, cat, unit, cost, price, reorder, qty in demo:
        clean = {"sku": sku, "name": name, "category": cat, "unit": unit, "cost_price": float(cost),
                 "selling_price": float(price), "reorder_point": reorder, "supplier_id": supplier_id}
        db["products"][sku] = _new_product(clean, system)
        apply_movement(db, "system", db["products"][sku], "INBOUND", qty, "Opening stock", "SEED")


# ------------------------------------------------------------------ auth / users
def login(db: dict, username, password) -> dict:
    name = str(username or "").strip().lower()
    user = db["users"].get(name)
    now = time.time()
    if user is None or not user.get("active", False):
        raise ServiceError("Invalid username or password", 401)
    if user.get("locked_until", 0) > now:
        raise ServiceError("Account temporarily locked. Try again in a few minutes.", 429)
    if not dh.verify_password(str(password or ""), user["password_hash"]):
        user["failed_attempts"] = user.get("failed_attempts", 0) + 1
        if user["failed_attempts"] >= MAX_FAILED:
            user["failed_attempts"], user["locked_until"] = 0, now + LOCK_SECONDS
            dh.append_audit(db, name, "LOGIN_LOCKED", "user", name)
        _save(db, "users")
        raise ServiceError("Invalid username or password", 401)
    user["failed_attempts"], user["locked_until"] = 0, 0
    dh.append_audit(db, name, "LOGIN", "user", name)
    _save(db, "users")
    return {"token": auth.make_token(name, user["role"]), "user": public_user(user)}


def me(user: dict) -> dict:
    return {"user": public_user(user), "permissions": auth.permissions_for(user["role"])}


def change_password(db, user, payload) -> dict:
    errors = []
    new = V.validate_password(payload.get("new_password"), errors)
    _need(errors)
    if not dh.verify_password(str(payload.get("old_password") or ""), user["password_hash"]):
        raise ServiceError("Current password is incorrect", 403)
    user["password_hash"] = dh.hash_password(new)
    _audit(db, user, "UPDATE", "user", user["username"], None, {"password": "changed"})
    _save(db, "users")
    return {"ok": True}


def list_users(db, user, q) -> dict:
    rows = sorted((public_user(u) for u in db["users"].values()), key=_sort_key("username"))
    return paginate(rows, q, 20)


def create_user(db, user, payload) -> dict:
    errors = []
    username = str(payload.get("username") or "").strip().lower()
    if not V.USERNAME_RE.match(username):
        errors.append("username must be 3-30 chars: a-z, 0-9, '_' or '.'")
    password = V.validate_password(payload.get("password"), errors)
    role = V.to_choice(payload.get("role"), "role", V.ROLES, errors)
    full_name = V.to_str(payload.get("full_name"), "full_name", errors, 2, 60)
    _need(errors)
    if username in db["users"]:
        raise ServiceError("Username already exists", 409)
    db["users"][username] = {"username": username, "password_hash": dh.hash_password(password),
                             "role": role, "full_name": full_name, "active": True,
                             "created_at": dh.now_iso()}
    _audit(db, user, "CREATE", "user", username, None, {"role": role})
    _save(db, "users")
    return public_user(db["users"][username])


def update_user(db, user, username, payload) -> dict:
    target = db["users"].get(str(username).lower())
    if target is None:
        raise ServiceError("User not found", 404)
    errors, before = [], public_user(target)
    role = V.to_choice(payload["role"], "role", V.ROLES, errors) if "role" in payload else target["role"]
    active = payload["active"] in (True, "true", "1", 1) if "active" in payload else target["active"]
    full_name = V.to_str(payload["full_name"], "full_name", errors, 2, 60) if "full_name" in payload else target["full_name"]
    password = V.validate_password(payload["password"], errors) if payload.get("password") else ""
    _need(errors)
    if target["username"] == user["username"] and (role != "admin" or not active):
        raise ServiceError("You cannot demote or deactivate your own account", 409)
    target.update(role=role, active=active, full_name=full_name)
    if password:
        target["password_hash"] = dh.hash_password(password)
    _audit(db, user, "UPDATE", "user", target["username"], before, public_user(target))
    _save(db, "users")
    return public_user(target)


# ------------------------------------------------------------------ products
def _new_product(clean: dict, user: dict) -> dict:
    now = dh.now_iso()
    return {**clean, "quantity_on_hand": 0, "active": True, "created_at": now,
            "updated_at": now, "created_by": user["username"]}


def list_products(db, user, q) -> dict:
    staff = auth.can(user["role"], "products.view_cost")
    search, category = q.get("search", "").strip().lower(), q.get("category", "").strip().lower()
    low_only = staff and q.get("low_only") in ("1", "true")
    sort = q.get("sort", "sku")
    if sort not in (STAFF_SORT if staff else CUSTOMER_SORT):
        sort = "sku"
    rows, categories = [], set()
    for p in db["products"].values():
        if not p["active"]:
            continue
        categories.add(p["category"])
        matches_text = search == "" or search in p["sku"].lower() or search in p["name"].lower()
        matches_cat = category == "" or p["category"].lower() == category
        if matches_text and matches_cat and (not low_only or is_low(p)):
            rows.append(p)
    rows.sort(key=_sort_key(sort), reverse=q.get("order") == "desc")
    page = paginate(rows, q)
    page["items"] = [dict(p, low=is_low(p)) if staff else public_product(p) for p in page["items"]]
    page["categories"] = sorted(categories)
    return page


def get_product(db, user, sku) -> dict:
    p = _get_product(db, sku)
    return p if auth.can(user["role"], "products.view_cost") else public_product(p)


def create_product(db, user, payload) -> dict:
    clean, errors = V.validate_product(payload, creating=True)
    _need(errors)
    if clean["sku"] in db["products"]:
        raise ServiceError(f"SKU {clean['sku']} already exists", 409)
    if clean["supplier_id"]:
        _get_supplier(db, clean["supplier_id"])
    db["products"][clean["sku"]] = _new_product(clean, user)
    _audit(db, user, "CREATE", "product", clean["sku"], None, db["products"][clean["sku"]])
    _save(db, "products")
    return db["products"][clean["sku"]]


def update_product(db, user, sku, payload) -> dict:
    product = _get_product(db, sku)
    editable = ("name", "category", "unit", "cost_price", "selling_price", "reorder_point",
                "supplier_id", "allow_below_cost")
    merged = {**product, **{k: payload[k] for k in editable if k in payload}}
    clean, errors = V.validate_product(merged, creating=False)
    _need(errors)
    if clean["supplier_id"]:
        _get_supplier(db, clean["supplier_id"])
    before = dict(product)
    clean.pop("sku")
    product.update(clean, updated_at=dh.now_iso())
    _audit(db, user, "UPDATE", "product", product["sku"], before, product)
    _save(db, "products")
    return product


def delete_product(db, user, sku) -> dict:
    product = _get_product(db, sku)
    if product["quantity_on_hand"] != 0:
        raise ServiceError("Stock must be 0 before deleting (use an adjustment first)", 409)
    before = dict(product)
    product["active"], product["updated_at"] = False, dh.now_iso()
    _audit(db, user, "DELETE", "product", product["sku"], before, {"active": False})
    _save(db, "products")
    return {"ok": True}


# ------------------------------------------------------------------ suppliers
def list_suppliers(db, user, q) -> dict:
    search = q.get("search", "").strip().lower()
    rows = [s for s in db["suppliers"].values()
            if s["active"] and (search == "" or search in s["name"].lower() or search in s.get("contact", "").lower())]
    rows.sort(key=_sort_key("name"), reverse=q.get("order") == "desc")
    return paginate(rows, q)


def create_supplier(db, user, payload) -> dict:
    clean, errors = V.validate_supplier(payload)
    _need(errors)
    supplier_id = dh.next_id(db, "SUP")
    db["suppliers"][supplier_id] = {"id": supplier_id, **clean, "active": True, "created_at": dh.now_iso()}
    _audit(db, user, "CREATE", "supplier", supplier_id, None, db["suppliers"][supplier_id])
    _save(db, "suppliers")
    return db["suppliers"][supplier_id]


def update_supplier(db, user, supplier_id, payload) -> dict:
    supplier = _get_supplier(db, supplier_id)
    clean, errors = V.validate_supplier({**supplier, **payload})
    _need(errors)
    before = dict(supplier)
    supplier.update(clean)
    _audit(db, user, "UPDATE", "supplier", supplier["id"], before, supplier)
    _save(db, "suppliers")
    return supplier


def delete_supplier(db, user, supplier_id) -> dict:
    supplier = _get_supplier(db, supplier_id)
    in_use = any(p["active"] and p.get("supplier_id") == supplier["id"] for p in db["products"].values())
    open_po = any(po["supplier_id"] == supplier["id"] and po["status"] in ("DRAFT", "SENT")
                  for po in db["purchase_orders"].values())
    if in_use or open_po:
        raise ServiceError("Supplier is used by active products or open purchase orders", 409)
    supplier["active"] = False
    _audit(db, user, "DELETE", "supplier", supplier["id"], {"active": True}, {"active": False})
    _save(db, "suppliers")
    return {"ok": True}


# ------------------------------------------------------------------ stock operations
def apply_movement(db, username, product, mtype, delta, reason, reference="", unit_cost=None) -> dict:
    """Mutate stock + append movement + audit. Caller persists."""
    old_qty = product["quantity_on_hand"]
    new_qty = old_qty + delta
    if new_qty < 0:
        raise ServiceError(f"Insufficient stock for {product['sku']}: on hand {old_qty}, requested {-delta}", 409)
    if mtype == "INBOUND" and unit_cost is not None and new_qty > 0:      # moving-average cost
        product["cost_price"] = round((old_qty * product["cost_price"] + delta * unit_cost) / new_qty, 2)
    product["quantity_on_hand"], product["updated_at"] = new_qty, dh.now_iso()
    movement = {"id": dh.next_id(db, "MOV"), "timestamp": dh.now_iso(), "sku": product["sku"],
                "type": mtype, "qty_change": delta, "balance_after": new_qty, "unit_cost": unit_cost,
                "reason": reason, "reference": reference, "user": username}
    db["stock_movements"].append(movement)
    dh.append_audit(db, username, "STOCK_" + mtype, "product", product["sku"],
                    {"quantity_on_hand": old_qty}, {"quantity_on_hand": new_qty, "reason": reason})
    return movement


def stock_move(db, user, payload) -> dict:
    errors = []
    sku = V.to_sku(payload.get("sku"), errors)
    mtype = V.to_choice(payload.get("type"), "type", MOVE_TYPES, errors)
    reason = V.to_str(payload.get("reason"), "reason", errors, 3, 200)
    reference = V.to_str(payload.get("reference"), "reference", errors, 1, 40, required=False)
    if mtype == "ADJUSTMENT":
        qty = V.to_int(payload.get("quantity"), "quantity", errors, -1_000_000, 1_000_000)
        if qty == 0:
            errors.append("quantity must not be 0 for an adjustment")
    else:
        qty = V.to_int(payload.get("quantity"), "quantity", errors, 1, 1_000_000)
    unit_cost = None
    if mtype == "INBOUND" and payload.get("unit_cost") not in (None, ""):
        unit_cost = V.to_float(payload.get("unit_cost"), "unit_cost", errors)
    _need(errors)
    product = _get_product(db, sku)
    delta = -qty if mtype == "OUTBOUND" else qty
    movement = apply_movement(db, user["username"], product, mtype, delta, reason, reference, unit_cost)
    _save(db, "products", "stock_movements")
    return movement


def stock_card(db, user, sku, q) -> dict:
    product = _get_product(db, sku)
    moves = [m for m in db["stock_movements"] if m["sku"] == product["sku"]]
    moves.reverse()
    page = paginate(moves, q, 15)
    page["product"] = product
    return page


def low_stock_report(db, user) -> dict:
    rows = [dict(p, shortfall=p["reorder_point"] - p["quantity_on_hand"])
            for p in db["products"].values() if is_low(p)]
    rows.sort(key=lambda r: r["shortfall"], reverse=True)
    return {"items": rows, "total": len(rows)}


# ------------------------------------------------------------------ purchase orders
def list_pos(db, user, q) -> dict:
    status, search = q.get("status", "").upper(), q.get("search", "").strip().lower()
    rows = []
    for po in db["purchase_orders"].values():
        supplier_name = db["suppliers"].get(po["supplier_id"], {}).get("name", "")
        if (status == "" or po["status"] == status) and (search == "" or search in po["id"].lower() or search in supplier_name.lower()):
            rows.append(dict(po, supplier_name=supplier_name))
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return paginate(rows, q)


def create_po(db, user, payload) -> dict:
    errors = []
    supplier_id = V.to_str(payload.get("supplier_id"), "supplier_id", errors, 1, 20)
    raw_lines = payload.get("lines")
    lines = []
    if not isinstance(raw_lines, list) or not 1 <= len(raw_lines) <= 50:
        errors.append("lines must contain 1-50 items")
        raw_lines = []
    for index, line in enumerate(raw_lines, start=1):
        if not isinstance(line, dict):
            errors.append(f"line {index} is invalid")
            continue
        sub = []
        sku = V.to_sku(line.get("sku"), sub)
        qty = V.to_int(line.get("qty"), "qty", sub, 1, 1_000_000)
        cost = V.to_float(line.get("unit_cost"), "unit_cost", sub)
        if sku and sku not in db["products"]:
            sub.append(f"unknown SKU {sku}")
        errors.extend(f"line {index}: {m}" for m in sub)
        lines.append({"sku": sku, "qty": qty, "unit_cost": cost})
    _need(errors)
    _get_supplier(db, supplier_id)
    po_id = dh.next_id(db, "PO")
    total = round(sum(l["qty"] * l["unit_cost"] for l in lines), 2)
    db["purchase_orders"][po_id] = {"id": po_id, "supplier_id": supplier_id, "status": "DRAFT",
                                    "lines": lines, "total": total, "created_by": user["username"],
                                    "created_at": dh.now_iso(), "received_at": None}
    _audit(db, user, "CREATE", "purchase_order", po_id, None, db["purchase_orders"][po_id])
    _save(db, "purchase_orders")
    return db["purchase_orders"][po_id]


def po_action(db, user, po_id, action) -> dict:
    po = db["purchase_orders"].get(po_id)
    if po is None:
        raise ServiceError("Purchase order not found", 404)
    before, status = po["status"], po["status"]
    if action == "send" and status == "DRAFT":
        po["status"] = "SENT"
    elif action == "receive" and status == "SENT":
        for line in po["lines"]:
            product = db["products"].get(line["sku"])
            if product is not None and product["active"]:
                apply_movement(db, user["username"], product, "INBOUND", line["qty"],
                               f"Received against {po_id}", po_id, line["unit_cost"])
        po["status"], po["received_at"] = "RECEIVED", dh.now_iso()
    elif action == "cancel" and status in ("DRAFT", "SENT"):
        po["status"] = "CANCELLED"
    else:
        raise ServiceError(f"Cannot {action} a purchase order that is {status}", 409)
    _audit(db, user, "PO_" + action.upper(), "purchase_order", po_id, {"status": before}, {"status": po["status"]})
    _save(db, "purchase_orders", "products", "stock_movements")
    return po


# ------------------------------------------------------------------ reports
def valuation_report(db, user, q) -> dict:
    rows, by_category = [], {}
    total_cost = total_retail = 0.0
    for p in db["products"].values():
        if not p["active"]:
            continue
        cost_value = round(p["quantity_on_hand"] * p["cost_price"], 2)
        retail_value = round(p["quantity_on_hand"] * p["selling_price"], 2)
        total_cost += cost_value
        total_retail += retail_value
        bucket = by_category.setdefault(p["category"], {"units": 0, "cost_value": 0.0})
        bucket["units"] += p["quantity_on_hand"]
        bucket["cost_value"] = round(bucket["cost_value"] + cost_value, 2)
        rows.append({"sku": p["sku"], "name": p["name"], "category": p["category"], "unit": p["unit"],
                     "quantity_on_hand": p["quantity_on_hand"], "cost_price": p["cost_price"],
                     "cost_value": cost_value, "retail_value": retail_value})
    rows.sort(key=lambda r: r["cost_value"], reverse=True)
    page = paginate(rows, q)
    page.update(total_cost_value=round(total_cost, 2), total_retail_value=round(total_retail, 2),
                potential_margin=round(total_retail - total_cost, 2), by_category=by_category)
    return page


def dashboard(db, user) -> dict:
    active = [p for p in db["products"].values() if p["active"]]
    low = sorted((p for p in active if is_low(p)), key=lambda p: p["quantity_on_hand"] - p["reorder_point"])
    po_counts = {status: 0 for status in PO_STATUSES}
    for po in db["purchase_orders"].values():
        po_counts[po["status"]] += 1
    return {"products": len(active), "categories": len({p["category"] for p in active}),
            "suppliers": sum(1 for s in db["suppliers"].values() if s["active"]),
            "stock_units": sum(p["quantity_on_hand"] for p in active),
            "stock_value": round(sum(p["quantity_on_hand"] * p["cost_price"] for p in active), 2),
            "low_stock_count": len(low), "low_stock": low[:5], "po_by_status": po_counts,
            "recent_movements": db["stock_movements"][-8:][::-1]}


def list_audit(db, user, q) -> dict:
    who, entity, action = q.get("user", "").lower(), q.get("entity", "").lower(), q.get("action", "").upper()
    rows = [a for a in reversed(db["audit_log"])
            if (who == "" or who in a["user"].lower()) and (entity == "" or entity == a["entity"])
            and (action == "" or action in a["action"])]
    return paginate(rows, q, 20)
