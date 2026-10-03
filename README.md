# Inventory Management System (Python stdlib only)

ระบบจัดการสต็อก — Python มาตรฐานล้วน ทำงานเป็นเว็บบน Vercel และเป็น CLI ในเครื่องได้

ไม่มีโฟลเดอร์ ทุกไฟล์อยู่ที่ root:
```
index.py          Vercel entrypoint: หน้าเว็บที่ "/" และ API ที่ /api/*
ui.py             หน้าเว็บ (ฝังเป็นสตริง ไม่ต้องใช้ static file)
services.py       business logic · auth.py RBAC+token · validators.py · data_handler.py (storage)
cli.py            เมนู CLI แบบ while-loop (รันในเครื่อง)
```
รันในเครื่อง: `python index.py` (เว็บ) หรือ `python cli.py` (CLI)

## Deploy บน Vercel
1. Import repo → Framework Preset = Other → Deploy (ห้ามมี vercel.json และไฟล์ชื่อ main.py/app.py/server.py)
2. Environment Variables: `SECRET_KEY` (สตริงสุ่มยาว), `ADMIN_PASSWORD`, `SEED_DEMO=1` (ไม่บังคับ)
3. Storage: เพิ่ม Upstash Redis แล้ว Connect กับโปรเจกต์ → Redeploy (ไม่งั้นข้อมูลหายตอน function เริ่มใหม่)
4. ตรวจ `/api/health` ต้องได้ `"status": "ok"` และ `"storage": "kv"`

ล็อกอินครั้งแรก: `admin` / ค่าของ `ADMIN_PASSWORD` (ถ้าไม่ตั้งคือ `Admin@123`)


## Features added
- Separate Login / Register screens. Public self-registration creates **customer** accounts; only admin can create staff/admin.
- RBAC: admin, staff, customer.
- Multi-warehouse API: warehouse creation, warehouse stock and transfers.
- Lot/expiry tracking API with FEFO/FIFO ordering.
- Stock count with system-vs-counted difference.
- Demand forecast from historical outbound movements.
- CSV product import/export helpers.
- Existing weighted-average cost calculation remains in stock receiving.
- Audit log records important changes.
- Validation, pagination, sorting, filtering and friendly error handling remain enabled.
