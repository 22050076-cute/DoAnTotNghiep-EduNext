from sqlalchemy import text

class AcademicService:

    @staticmethod
    def get_subjects(db):
        query = text("SELECT MaMonHoc, TenMonHoc FROM dbo.MonHoc ORDER BY MaMonHoc ASC")
        rows = db.execute(query).fetchall()
        return [{"id": r.MaMonHoc, "name": r.TenMonHoc} for r in rows]

    @staticmethod
    def get_gradebook(db, class_id, subject_id, semester_id=1):
        if not class_id:
            return []

        query = text("""
            SELECT 
                nd.MaNguoiDung,
                nd.HoTen,
                MAX(CASE WHEN bd.MaLoai = 1 THEN bd.DiemSo END) AS M1,
                MAX(CASE WHEN bd.MaLoai = 2 THEN bd.DiemSo END) AS M2,
                MAX(CASE WHEN bd.MaLoai = 3 THEN bd.DiemSo END) AS M3,
                MAX(CASE WHEN bd.MaLoai = 4 THEN bd.DiemSo END) AS TX1,
                MAX(CASE WHEN bd.MaLoai = 5 THEN bd.DiemSo END) AS TX2,
                MAX(CASE WHEN bd.MaLoai = 6 THEN bd.DiemSo END) AS GK,
                MAX(CASE WHEN bd.MaLoai = 7 THEN bd.DiemSo END) AS CK
            FROM dbo.NguoiDung nd
            LEFT JOIN dbo.BangDiem bd ON nd.MaNguoiDung = bd.MaHocSinh 
                                      AND bd.MaMonHoc = :subject_id 
                                      AND bd.MaHocKy = :semester_id
            WHERE nd.MaLop = :class_id AND nd.VaiTro = 'Student'
            GROUP BY nd.MaNguoiDung, nd.HoTen
            ORDER BY nd.HoTen ASC
        """)
        
        rows = db.execute(query, {
            "class_id": class_id,
            "subject_id": subject_id,
            "semester_id": semester_id
        }).fetchall()
        
        result = []
        for r in rows:
            m1 = float(r.M1) if r.M1 is not None else None
            m2 = float(r.M2) if r.M2 is not None else None
            m3 = float(r.M3) if r.M3 is not None else None
            tx1 = float(r.TX1) if r.TX1 is not None else None
            tx2 = float(r.TX2) if r.TX2 is not None else None
            gk = float(r.GK) if r.GK is not None else None
            ck = float(r.CK) if r.CK is not None else None

            # Tính điểm trung bình môn theo hệ số: Miệng/TX hệ số 1, GK hệ số 2, CK hệ số 3
            tx_scores = [s for s in [m1, m2, m3, tx1, tx2] if s is not None]
            tb_val = None
            if tx_scores or gk is not None or ck is not None:
                sum_tx = sum(tx_scores)
                cnt_tx = len(tx_scores)
                gk_coef = 2 if gk is not None else 0
                ck_coef = 3 if ck is not None else 0
                
                total_coef = cnt_tx + gk_coef + ck_coef
                if total_coef > 0:
                    tb_val = round((sum_tx + (gk or 0) * 2 + (ck or 0) * 3) / total_coef, 1)

            result.append({
                "MaNguoiDung": r.MaNguoiDung,
                "HoTen": r.HoTen,
                "M1": m1,
                "M2": m2,
                "M3": m3,
                "TX1": tx1,
                "TX2": tx2,
                "GK": gk,
                "CK": ck,
                "TB": tb_val
            })
            
        return result

    @staticmethod
    def get_grades_classes(db, teacher_id=None):
        # Lấy danh sách lớp phân theo khối phục vụ bộ lọc Sổ điểm
        query = text("""
            SELECT k.MaKhoi, k.TenKhoi, l.MaLop, l.TenLop
            FROM dbo.LopHoc l
            LEFT JOIN dbo.KhoiHoc k ON l.MaKhoi = k.MaKhoi
            ORDER BY k.MaKhoi ASC, l.TenLop ASC
        """)
        rows = db.execute(query).fetchall()

        grades_dict = {}
        for r in rows:
            kid = r.MaKhoi or 1
            kname = r.TenKhoi or f"Khối {kid}"
            if kid not in grades_dict:
                grades_dict[kid] = {
                    "id": kid,
                    "name": kname,
                    "classes": []
                }
            grades_dict[kid]["classes"].append({
                "id": r.MaLop,
                "name": r.TenLop
            })

        return list(grades_dict.values())

    @staticmethod
    def get_teacher_schedule(db, class_id):
        query = text("""
            SELECT tkb.Thu, tkb.Tiet, tkb.MaMonHoc, mh.TenMonHoc, tkb.PhongHoc
            FROM dbo.ThoiKhoaBieu tkb
            LEFT JOIN dbo.MonHoc mh ON tkb.MaMonHoc = mh.MaMonHoc
            WHERE tkb.MaLop = :cid
            ORDER BY tkb.Thu ASC, tkb.Tiet ASC
        """)
        rows = db.execute(query, {"cid": class_id}).fetchall()
        return [dict(r._mapping) for r in rows]

    @staticmethod
    def update_schedule(db, class_id, schedule_data, teacher_id=None):
        db.execute(text("DELETE FROM dbo.ThoiKhoaBieu WHERE MaLop = :cid"), {"cid": class_id})
        for item in schedule_data:
            thu = item.get('Thu') or item.get('thu')
            tiet = item.get('Tiet') or item.get('tiet')
            mon_id = item.get('MaMonHoc') or item.get('mon_hoc_id')
            phong = item.get('PhongHoc') or item.get('phong_hoc', '')
            if thu and tiet and mon_id:
                db.execute(text("""
                    INSERT INTO dbo.ThoiKhoaBieu (MaLop, Thu, Tiet, MaMonHoc, PhongHoc)
                    VALUES (:cid, :thu, :tiet, :mid, :phong)
                """), {"cid": class_id, "thu": thu, "tiet": tiet, "mid": mon_id, "phong": phong})
        db.commit()

    @staticmethod
    def get_student_schedule_by_parent(db, parent_id):
        student = db.execute(text("SELECT MaLop FROM dbo.NguoiDung WHERE MaNguoiDung = (SELECT MaHocSinhLienKet FROM dbo.NguoiDung WHERE MaNguoiDung = :pid)"), {"pid": parent_id}).fetchone()
        if not student or not student.MaLop:
            return None
        return AcademicService.get_teacher_schedule(db, student.MaLop)

    @staticmethod
    def get_student_attendance_by_parent(db, parent_id):
        student = db.execute(text("SELECT MaNguoiDung FROM dbo.NguoiDung WHERE MaNguoiDung = (SELECT MaHocSinhLienKet FROM dbo.NguoiDung WHERE MaNguoiDung = :pid)"), {"pid": parent_id}).fetchone()
        if not student:
            return []
        return AcademicService.get_student_attendance(db, student.MaNguoiDung)

    @staticmethod
    def get_student_attendance(db, student_id):
        query = text("""
            SELECT NgayDiemDanh, TrangThai, GhiChu
            FROM dbo.DiemDanh
            WHERE MaHocSinh = :sid
            ORDER BY NgayDiemDanh DESC
        """)
        rows = db.execute(query, {"sid": student_id}).fetchall()
        return [{"Ngay": str(r.NgayDiemDanh), "TrangThai": r.TrangThai, "GhiChu": r.GhiChu or ""} for r in rows]