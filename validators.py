"""lib/validators.py - strict, pure input validation + type casting (no I/O).

Every helper appends a human-readable message to `errors` and returns None / ""
when the value is invalid, so callers can collect all problems in one pass.
"""
import math
import re

SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-]{2,19}$")
USERNAME_RE = re.compile(r"^[a-z0-9_.]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
PHONE_RE = re.compile(r"^[0-9+\-\s()]{6,20}$")
UNITS = ("pcs", "box", "kg", "litre", "pack")
ROLES = ("admin", "staff", "customer")


def to_str(value, label, errors, min_len=1, max_len=100, required=True) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            errors.append(f"{label} is required")
        return ""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        errors.append(f"{label} must be text")
        return ""
    text = str(value).strip()
    if len(text) < min_len or len(text) > max_len:
        errors.append(f"{label} must be {min_len}-{max_len} characters")
        return ""
    return text


def to_int(value, label, errors, lo=0, hi=1_000_000):
    number = None
    if isinstance(value, bool) or value is None:
        pass
    elif isinstance(value, int):
        number = value
    elif isinstance(value, (float, str)):
        try:
            as_float = float(str(value).strip())
            if math.isfinite(as_float) and as_float.is_integer():
                number = int(as_float)
        except ValueError:
            pass
    if number is None:
        errors.append(f"{label} must be a whole number")
        return None
    if number < lo or number > hi:
        errors.append(f"{label} must be between {lo} and {hi}")
        return None
    return number


def to_float(value, label, errors, lo=0.0, hi=1e9):
    number = None
    if isinstance(value, bool) or value is None:
        pass
    elif isinstance(value, (int, float, str)):
        try:
            number = float(str(value).strip())
        except ValueError:
            pass
    if number is None or not math.isfinite(number):
        errors.append(f"{label} must be a number")
        return None
    if number < lo or number > hi:
        errors.append(f"{label} must be between {lo} and {hi}")
        return None
    return round(number, 2)


def to_choice(value, label, choices, errors) -> str:
    lookup = {c.lower(): c for c in choices}
    key = str(value).strip().lower() if value is not None else ""
    if key in lookup:
        return lookup[key]
    errors.append(f"{label} must be one of: {', '.join(choices)}")
    return ""


def to_sku(value, errors, label="sku") -> str:
    text = str(value if value is not None else "").strip().upper()
    if SKU_RE.match(text):
        return text
    errors.append(f"{label} must be 3-20 chars: A-Z, 0-9 or '-'")
    return ""


def to_optional_pattern(value, label, pattern, errors) -> str:
    text = str(value if value is not None else "").strip()
    if text == "":
        return ""
    if pattern.match(text):
        return text
    errors.append(f"{label} is not valid")
    return ""


def validate_password(password, errors) -> str:
    text = password if isinstance(password, str) else ""
    if len(text) < 8 or len(text) > 128 or not (any(c.isalpha() for c in text) and any(c.isdigit() for c in text)):
        errors.append("password must be 8-128 chars and contain letters and digits")
        return ""
    return text


def validate_product(data: dict, creating: bool = True):
    """Return (clean_dict, errors)."""
    errors = []
    clean = {
        "sku": to_sku(data.get("sku"), errors) if creating else str(data.get("sku", "")),
        "name": to_str(data.get("name"), "name", errors, 2, 80),
        "category": to_str(data.get("category"), "category", errors, 2, 40),
        "unit": to_choice(data.get("unit"), "unit", UNITS, errors),
        "cost_price": to_float(data.get("cost_price"), "cost_price", errors),
        "selling_price": to_float(data.get("selling_price"), "selling_price", errors),
        "reorder_point": to_int(data.get("reorder_point"), "reorder_point", errors),
        "supplier_id": to_str(data.get("supplier_id"), "supplier_id", errors, 1, 20, required=False) or None,
    }
    cost, sell = clean["cost_price"], clean["selling_price"]
    override = data.get("allow_below_cost") in (True, "true", "1", 1)
    if cost is not None and sell is not None:
        if sell == 0 and cost > 0:
            errors.append("selling_price must be greater than 0 when cost_price is positive")
        elif sell < cost and not override and not (cost == 0):
            errors.append("selling_price is below cost (send allow_below_cost=true to confirm)")
    return clean, errors


def validate_supplier(data: dict):
    errors = []
    clean = {
        "name": to_str(data.get("name"), "name", errors, 2, 80),
        "contact": to_str(data.get("contact"), "contact", errors, 1, 60, required=False),
        "phone": to_optional_pattern(data.get("phone"), "phone", PHONE_RE, errors),
        "email": to_optional_pattern(data.get("email"), "email", EMAIL_RE, errors),
        "address": to_str(data.get("address"), "address", errors, 1, 200, required=False),
    }
    return clean, errors
