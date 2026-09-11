from app.config import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    res = db.execute(text('SELECT TrangThai, COUNT(*) as Count FROM KhoHocLieu GROUP BY TrangThai')).fetchall()
    print("Status | Count")
    print("-" * 15)
    for r in res:
        print(f"{r.TrangThai} | {r.Count}")
finally:
    db.close()
