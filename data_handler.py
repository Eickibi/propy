import json
import os

def load_json(filepath: str, default_type: str = "dict"):
    """อ่านข้อมูล JSON ป้องกันไฟล์เสียหรือไม่พบไฟล์"""
    try:
        if not os.path.exists(filepath):
            return {} if default_type == "dict" else []
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        # หากพังหรืออ่านไม่ได้ ให้คืนค่าเริ่มต้น
        return {} if default_type == "dict" else []

def save_json(filepath: str, data) -> bool:
    """บันทึกข้อมูล JSON ลงไฟล์"""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception:
        return False