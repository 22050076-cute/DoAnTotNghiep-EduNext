from sqlalchemy import text
from datetime import datetime

class EventService:
    @staticmethod
    def get_public_events(db):
        query = text("""
            SELECT MaSuKien, TieuDe, NoiDung, NgayToChuc, DiaDiem, HinhAnh, PhamVi
            FROM SuKien
            WHERE (PhamVi = 'Truong' OR PhamVi = 'Public') 
              AND NgayToChuc >= CAST(GETDATE() AS DATE)
            ORDER BY NgayToChuc ASC
        """)
        results = db.execute(query).mappings().all()
        return [dict(r) for r in results]

    @staticmethod
    def register_event(db, data):
        event_id = data.get('event_id')
        user_id = data.get('user_id') # Có thể NULL nếu là khách
        
        # Thông tin khách (nếu có)
        guest_name = data.get('guest_name')
        guest_email = data.get('guest_email')
        guest_phone = data.get('guest_phone')

        # Kiểm tra xem đã đăng ký chưa (dành cho user có tài khoản)
        if user_id:
            check = db.execute(text("SELECT 1 FROM DangKySuKien WHERE MaSuKien = :eid AND MaNguoiDung = :uid"), 
                               {"eid": event_id, "uid": user_id}).fetchone()
            if check:
                return False, "Bạn đã đăng ký sự kiện này rồi!"

        # Chèn bản ghi mới
        # Chú ý: Cần đảm bảo các cột này tồn tại trong DB (sẽ chạy script SQL sau)
        query = text("""
            INSERT INTO DangKySuKien (MaSuKien, MaNguoiDung, NgayDangKy, HoTenKhach, EmailKhach, SdtKhach)
            VALUES (:eid, :uid, GETDATE(), :name, :email, :phone)
        """)
        db.execute(query, {
            "eid": event_id,
            "uid": user_id,
            "name": guest_name,
            "email": guest_email,
            "phone": guest_phone
        })
        db.commit()
        return True, "Đăng ký tham gia thành công!"
