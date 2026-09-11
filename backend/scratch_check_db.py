from app.config import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    res = db.execute(text('SELECT MaTaiLieu, TenTaiLieu, TrangThai FROM KhoHocLieu')).fetchall()
    print("ID | Title | Status")
    print("-" * 30)
    for r in res:
        print(f"{r.MaTaiLieu} | {r.TenTaiLieu} | {r.TrangThai}")
finally:
    db.close()
