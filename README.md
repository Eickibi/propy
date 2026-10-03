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
1. Import repo แล้ว Deploy ได้เลย — โปรเจกต์มี `api/index.py` และ `vercel.json` สำหรับ routing แล้ว
2. ตั้ง Environment Variables: `SECRET_KEY` เป็นค่าสุ่มยาว, `ADMIN_PASSWORD` เป็นรหัส admin ที่ต้องการ และ `SEED_DEMO=1` ถ้าต้องการข้อมูลตัวอย่าง
3. ต่อ Upstash Redis ผ่าน Vercel Marketplace/Storage แล้ว Redeploy เพื่อให้ users/products/stock/log อยู่ถาวร โดย Vercel จะเติม `KV_REST_API_URL` และ `KV_REST_API_TOKEN` ให้เมื่อเชื่อม integration สำเร็จ.
4. ตรวจ `/api/health` ต้องได้ `"status": "ok"` และ `"storage": "kv"`.
5. Login admin ครั้งแรกด้วย username `admin` และค่า `ADMIN_PASSWORD` (ถ้าไม่ตั้งใช้ `Admin@123`).

หมายเหตุ: Vercel Python runtime รองรับ `handler` ที่สืบทอด `BaseHTTPRequestHandler`; โปรเจกต์นี้ใช้รูปแบบดังกล่าว และ pin Python 3.12 เพื่อให้ deployment คงที่. 



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
