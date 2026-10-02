from data_handler import load_json, save_json
from datetime import datetime

DB_PROD = "data/products.json"
DB_LOG = "data/logs.json"
DB_USER = "data/users.json"
ROLES = ("admin", "staff", "customer") # ใช้ Tuple สำหรับข้อมูลที่ไม่เปลี่ยนแปลง

def init_db():
    """สร้างบัญชีผู้ใช้เริ่มต้นหากยังไม่มี"""
    users = load_json(DB_USER, "dict")
    if not users:
        users = {
            "admin": {"password": "123", "role": "admin"},
            "staff": {"password": "123", "role": "staff"},
            "guest": {"password": "123", "role": "customer"}
        }
        save_json(DB_USER, users)

def login(username, password) -> tuple:
    """ตรวจสอบการเข้าสู่ระบบ"""
    users = load_json(DB_USER, "dict") # ใช้ Dict เก็บข้อมูลหลัก
    if username in users and users[username]["password"] == password:
        return True, users[username]["role"]
    return False, None

def log_action(action: str, detail: str, user: str):
    """เกณฑ์: เก็บ log การแก้ไขข้อมูลสำคัญ"""
    logs = load_json(DB_LOG, "list") # ใช้ List เก็บประวัติ
    entry = {"time": str(datetime.now()), "action": action, "detail": detail, "user": user}
    logs.append(entry)
    save_json(DB_LOG, logs)

def add_product(sku: str, name: str, cat: str, cost: float, price: float, stock: int, user: str) -> tuple:
    """เกณฑ์: CRUD พร้อม Validation นำเข้า"""
    prods = load_json(DB_PROD, "dict")
    
    if sku in prods:
        return False, "รหัส SKU นี้มีในระบบแล้ว"
    # การใช้ if/else ประกอบ (and/or)
    if cost < 0 or price < 0 or stock < 0:
        return False, "ค่าตัวเลขราคาสินค้าหรือสต็อกห้ามติดลบ"
        
    prods[sku] = {"name": name, "cat": cat, "cost": cost, "price": price, "stock": stock}
    if save_json(DB_PROD, prods):
        log_action("ADD_PRODUCT", f"เพิ่ม {name} จำนวน {stock}", user)
        return True, "บันทึกสำเร็จ"
    return False, "ระบบไฟล์มีปัญหา"

def update_stock(sku: str, qty: int, reason: str, user: str) -> tuple:
    """ปรับลดยอดสต็อก (รับเข้า/เบิกออก)"""
    prods = load_json(DB_PROD, "dict")
    if sku not in prods:
        return False, "ไม่พบ SKU"
        
    new_stock = prods[sku]["stock"] + qty
    if new_stock < 0:
        return False, "สต็อกคงเหลือไม่พอให้เบิก"
        
    prods[sku]["stock"] = new_stock
    save_json(DB_PROD, prods)
    log_action("UPDATE_STOCK", f"SKU: {sku} ปรับ {qty} เหตุผล: {reason}", user)
    return True, "อัปเดตสต็อกสำเร็จ"

def get_paginated_products(page: int, limit: int, search: str = "") -> dict:
    """เกณฑ์: ค้นหา, เรียงลำดับ และแบ่งหน้า"""
    prods = load_json(DB_PROD, "dict")
    
    # 1. ค้นหา (Search/Filter)
    filtered = {k: v for k, v in prods.items() if search.lower() in v["name"].lower() or search.lower() in k.lower()}
    
    # 2. เรียงลำดับ (Sort)
    sorted_keys = sorted(filtered.keys())
    
    # 3. แบ่งหน้า (Pagination)
    start = (page - 1) * limit
    end = start + limit
    paginated_keys = sorted_keys[start:end]
    
    return {k: filtered[k] for k in paginated_keys}

def get_dashboard() -> dict:
    """เกณฑ์: Dashboard สรุปข้อมูล"""
    prods = load_json(DB_PROD, "dict")
    total_items = len(prods)
    total_value = sum(p["cost"] * p["stock"] for p in prods.values())
    low_stock = [sku for sku, p in prods.items() if p["stock"] <= 10] # Reorder point
    
    # ใช้ Set รวบรวมหมวดหมู่แบบไม่ซ้ำ
    categories = set(p["cat"] for p in prods.values())
    
    return {
        "total_sku": total_items,
        "total_value": total_value,
        "low_stock_alerts": len(low_stock),
        "total_categories": len(categories)
    }