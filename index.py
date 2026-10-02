import json
from http.server import BaseHTTPRequestHandler
from inventory_core import init_db, get_dashboard

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            init_db() # สั่งสร้างไฟล์ฐานข้อมูลเริ่มต้น
            dashboard_data = get_dashboard()
            
            # ตั้งค่า Header ให้เป็น JSON
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            # ส่งข้อมูล Dashboard ออกไปหน้าเว็บ
            response = {
                "project_name": "Inventory Management System",
                "status": "online",
                "dashboard": dashboard_data
            }
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            error_msg = {"error": "Internal Server Error"}
            self.wfile.write(json.dumps(error_msg).encode('utf-8'))