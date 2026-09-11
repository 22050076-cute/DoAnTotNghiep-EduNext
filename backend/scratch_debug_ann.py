from sqlalchemy import text
import sys
import os

# Thêm đường dẫn để import được cấu hình
sys.path.append(os.getcwd())

try:
    from app.config import SessionLocal
    db = SessionLocal()
    
    print("--- 10 THÔNG BÁO MỚI NHẤT ---")
    query = text("SELECT TOP 10 MaThongBao, TieuDe, PhamVi, MaLop, NgayGui FROM ThongBao ORDER BY MaThongBao DESC")
    results = db.execute(query).fetchall()
    for r in results:
        print(f"ID: {r.MaThongBao} | Tiêu đề: {r.TieuDe} | Phạm vi: {r.PhamVi} | MaLop: {r.MaLop} | Ngày: {r.NgayGui}")
    
    print("\n--- KIỂM TRA LỚP CỦA HỌC SINH ID 30 (Demo) ---")
    u_query = text("SELECT MaNguoiDung, HoTen, MaLop FROM NguoiDung WHERE MaNguoiDung = 30")
    u = db.execute(u_query).fetchone()
    if u:
        print(f"User: {u.HoTen} | MaLop: {u.MaLop}")
    else:
        print("Không tìm thấy User ID 30")
        
    db.close()
except Exception as e:
    print(f"Lỗi: {e}")
