# Inventory Management System (Python stdlib only)

ระบบจัดการสต็อกสินค้า — Python มาตรฐานล้วน (ไม่มี pip package) ทำงานได้ทั้งแบบ CLI, เว็บ และ Vercel Serverless

## โครงสร้าง
```
api/index.py        Vercel serverless function (ทุก route /api/*)
lib/                data_handler (storage) · validators · auth (RBAC+token) · services (business logic)
public/index.html   หน้าเว็บ (Dashboard, Products, Stock, Suppliers, PO, Valuation, Audit, Users)
main.py             CLI แบบ while-loop menu (รันในเครื่อง)
dev_server.py       รันเว็บ+API ในเครื่อง
vercel.json         rewrites /api/* -> api/index.py
```

## รันในเครื่อง
```
python dev_server.py     # เปิด http://localhost:8000
python main.py           # โหมด CLI
```
ล็อกอินครั้งแรก: `admin` / `Admin@123` (หรือค่าจาก `ADMIN_PASSWORD`) — เปลี่ยนรหัสผ่านทันที

## Deploy บน Vercel
1. `git init && git add . && git commit -m "init"` แล้ว push ขึ้น GitHub
2. Vercel → **Add New Project** → เลือก repo → Framework Preset = **Other** → Deploy
3. Settings → **Environment Variables** ใส่:
   - `SECRET_KEY` = สตริงสุ่มยาวๆ (จำเป็น ใช้เซ็น token)
   - `ADMIN_PASSWORD` = รหัสผ่าน admin เริ่มต้น
   - `SEED_DEMO` = `1` (ไม่บังคับ ใส่ข้อมูลตัวอย่างตอนเริ่ม)
4. **Storage** (สำคัญ): Vercel ลบไฟล์ในเครื่องทุกครั้งที่ function เริ่มใหม่ จึงต้องต่อฐานข้อมูล
   Vercel → Storage / Marketplace → เพิ่ม **Upstash Redis** แล้วกด Connect กับโปรเจกต์
   (ระบบจะได้ `KV_REST_API_URL` และ `KV_REST_API_TOKEN` อัตโนมัติ) → **Redeploy**
5. ตรวจสอบ: เปิด `https://<โดเมนของคุณ>/api/health` ต้องได้ `"storage": "kv"`

## Roles
- **admin** ทุกอย่าง · **staff** สินค้า/สต็อก/ซัพพลายเออร์/PO/รายงาน · **customer** ดูสินค้าและราคาขายเท่านั้น
