from sqlalchemy import text
from datetime import datetime

class LMSService:
    @staticmethod
    def get_teacher_materials(db, teacher_id):
        query = text("""
            SELECT kl.*, mh.TenMonHoc,
                   ISNULL(kl.SoLuotTai, 0) as SoLuotTai,
                   (SELECT COUNT(*) FROM TuongTac WHERE MaDoiTuong = kl.MaTaiLieu AND LoaiDoiTuong = 'HocLieu') as LikeCount,
                   ISNULL((SELECT AVG(CAST(SoSao AS FLOAT)) FROM DanhGiaHocLieu WHERE MaTaiLieu = kl.MaTaiLieu), 0) as AvgStars,
                   ISNULL((SELECT COUNT(*) FROM DanhGiaHocLieu WHERE MaTaiLieu = kl.MaTaiLieu), 0) as StarCount
            FROM KhoHocLieu kl
            LEFT JOIN MonHoc mh ON kl.MaMonHoc = mh.MaMonHoc
            WHERE kl.MaNguoiDang = :uid
            ORDER BY kl.NgayDang DESC
        """)
        results = db.execute(query, {"uid": teacher_id}).mappings().all()
        return [dict(r) for r in results]

    @staticmethod
    def upload_material(db, data):
        new_material = text("""
            INSERT INTO [dbo].[KhoHocLieu] 
            (TenTaiLieu, LoaiFile, DuongDan, MaMonHoc, MaNguoiDang, NgayDang, MoTa, MaKhoi, TrangThai, MaLop)
            VALUES (:ten, :loai, :path, :mon, :uid, GETDATE(), :mota, :khoi, :tt, :ml)
        """)
        db.execute(new_material, {
            "ten": data.get('ten'),
            "loai": data.get('loai', 'PDF'),
            "path": data.get('path', '#'),
            "mon": data.get('mon'),
            "uid": data.get('user_id'),
            "mota": data.get('mota'),
            "khoi": data.get('khoi'),
            "tt": data.get('trang_thai', 1),
            "ml": data.get('ma_lop')
        })
        db.commit()
        return True

    @staticmethod
    def delete_material(db, material_id):
        db.execute(text("DELETE FROM [dbo].[KhoHocLieu] WHERE MaTaiLieu = :id"), {"id": material_id})
        db.commit()
        return True

    @staticmethod
    def increment_download_count(db, material_id):
        try:
            db.execute(text("UPDATE [dbo].[KhoHocLieu] SET SoLuotTai = ISNULL(SoLuotTai, 0) + 1 WHERE MaTaiLieu = :id"), {"id": material_id})
            db.commit()
            return True
        except Exception as e:
            print(f"[LMSService Error] {e}")
            return False

    @staticmethod
    def get_student_dashboard_summary(db, student_id):
        # Logic từ student.py
        # 1. Thông tin user
        user_query = text("""
            SELECT nd.HoTen, l.TenLop, nd.AnhDaiDien 
            FROM NguoiDung nd
            LEFT JOIN LopHoc l ON nd.MaLop = l.MaLop
            WHERE nd.MaNguoiDung = :uid
        """)
        user_info = db.execute(user_query, {"uid": student_id}).mappings().first()
        
        # 2. XP
        xp_query = text("SELECT ISNULL(SUM(DiemXP), 0) FROM NhatKyReNep WHERE MaHocSinh = :uid")
        total_xp = db.execute(xp_query, {"uid": student_id}).scalar()
        
        # 3. Tasks
        tasks_query = text("""
            SELECT bt.MaBaiTap, bt.TieuDe, bt.NoiDung, bt.LinkGoogleForm, bt.FileDinhKem as FileBaiTap,
                   ISNULL(mh.TenMonHoc, N'Bài tập chung') as TenMonHoc, bt.HanNop, bt.LoaiBai, 
                   bl.MaBaiLam, bl.NoiDungBaiLam as NoiDungHS, bl.FileDinhKem as FileHS
            FROM BaiTap bt
            LEFT JOIN PhanCongGiangDay pc ON bt.MaPhanCong = pc.MaPhanCong
            LEFT JOIN MonHoc mh ON pc.MaMonHoc = mh.MaMonHoc
            LEFT JOIN BaiLam bl ON bt.MaBaiTap = bl.MaBaiTap AND bl.MaHocSinh = :uid
            WHERE pc.MaLop = (SELECT MaLop FROM NguoiDung WHERE MaNguoiDung = :uid)
               OR bt.MaPhanCong = (SELECT MaLop FROM NguoiDung WHERE MaNguoiDung = :uid)
            ORDER BY bt.MaBaiTap DESC
        """)
        tasks_data = db.execute(tasks_query, {"uid": student_id}).mappings().all()
        
        return {
            "user": user_info,
            "total_xp": total_xp,
            "tasks": tasks_data
        }
