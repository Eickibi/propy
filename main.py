from inventory_core import init_db, login, add_product, update_stock, get_paginated_products, get_dashboard

def main():
    init_db()
    print("="*40)
    print(" ระบบจัดการสต็อกสินค้า (Inventory V1) ")
    print("="*40)
    
    current_user = None
    user_role = None
    
    # Loop ที่ 1: Login
    while True:
        try:
            username = input("Username (admin/staff/guest): ").strip()
            password = input("Password (123): ").strip()
            is_valid, role = login(username, password)
            
            if is_valid:
                current_user = username
                user_role = role
                print(f"\n[+] เข้าสู่ระบบสำเร็จ! สิทธิ์ของคุณคือ: {user_role.upper()}")
                break
            else:
                print("[-] รหัสผ่านผิด หรือไม่มีผู้ใช้นี้ กรุณาลองใหม่")
        except Exception:
            print("[-] เกิดข้อผิดพลาดในการรับข้อมูล")

    # Loop ที่ 2: เมนูหลัก
    while True:
        try:
            print("\n--- เมนูหลัก ---")
            print("1. ดู Dashboard (สรุปข้อมูล)")
            print("2. ดูรายการสินค้า (ค้นหา/แบ่งหน้า)")
            if user_role in ("admin", "staff"):
                print("3. เพิ่มสินค้าใหม่")
                print("4. รับเข้า / เบิกออก สต็อก")
            print("0. ออกจากระบบ")
            
            choice = input("เลือกทำรายการ: ").strip()
            
            if choice == "0":
                print("ออกจากระบบ... ขอบคุณครับ")
                break
                
            elif choice == "1":
                dash = get_dashboard()
                print("\n[ Dashboard ]")
                print(f"สินค้าทั้งหมด: {dash['total_sku']} รายการ")
                print(f"มูลค่าสต็อกรวม: ฿{dash['total_value']:,.2f}")
                print(f"หมวดหมู่ทั้งหมด: {dash['total_categories']} หมวด")
                if dash['low_stock_alerts'] > 0:
                    print(f"!! แจ้งเตือน: มีสินค้า {dash['low_stock_alerts']} รายการต่ำกว่าจุดสั่งซื้อ !!")
                    
            elif choice == "2":
                search = input("ค้นหาชื่อ/SKU (เว้นว่างเพื่อดูทั้งหมด): ")
                page = int(input("หน้าที่ต้องการดู (เช่น 1): "))
                items = get_paginated_products(page, limit=3, search=search)
                print("\n[ รายการสินค้า ]")
                if not items:
                    print("ไม่พบข้อมูลในหน้านี้")
                else:
                    for sku, info in items.items():
                        print(f"SKU: {sku} | {info['name']} | คงเหลือ: {info['stock']} | หมวด: {info['cat']}")
                        
            elif choice == "3" and user_role in ("admin", "staff"):
                sku = input("รหัส SKU: ")
                name = input("ชื่อสินค้า: ")
                cat = input("หมวดหมู่: ")
                cost = float(input("ราคาทุน: "))
                price = float(input("ราคาขาย: "))
                stock = int(input("จำนวนเริ่มต้น: "))
                
                success, msg = add_product(sku, name, cat, cost, price, stock, current_user)
                print(f"[{'สำเร็จ' if success else 'ผิดพลาด'}] {msg}")
                
            elif choice == "4" and user_role in ("admin", "staff"):
                sku = input("รหัส SKU ที่ต้องการปรับปรุง: ")
                qty = int(input("จำนวน (ใส่ค่าบวกเพื่อรับเข้า, ค่าลบเพื่อเบิกออก): "))
                reason = input("เหตุผล (เช่น สั่งซื้อลอตใหม่, ของชำรุด): ")
                
                success, msg = update_stock(sku, qty, reason, current_user)
                print(f"[{'สำเร็จ' if success else 'ผิดพลาด'}] {msg}")
                
            else:
                print("[-] เมนูไม่ถูกต้อง หรือคุณไม่มีสิทธิ์เข้าถึงเมนูนี้")
                
        except ValueError:
            print("[-] กรุณากรอกรูปแบบตัวเลขให้ถูกต้อง!")
        except Exception:
            print("[-] เกิดข้อผิดพลาดของระบบ")

if __name__ == "__main__":
    main()