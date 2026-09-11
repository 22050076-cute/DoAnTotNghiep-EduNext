from app.config import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    print("--- [TABLE: ThongBao] ---")
    res = db.execute(text("SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'ThongBao'")).fetchall()
    for r in res:
        print(f"Col: {r[0]}, Type: {r[1]}")
    
    print("\n--- [USER: gv.6a1] ---")
    res = db.execute(text("SELECT MaNguoiDung, HoTen, VaiTro, MaLop FROM NguoiDung WHERE Email = 'gv.6a1@teacher.edunext.vn'")).fetchone()
    print(f"Result: {res}")
    
    print("\n--- [CLASS_ID for Teacher] ---")
    from app.services.class_service import ClassService
    if res:
        class_id = ClassService.get_teacher_class_id(db, res[0])
        print(f"Resolved ClassID: {class_id}")
finally:
    db.close()
