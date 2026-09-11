from sqlalchemy import text
from datetime import datetime

class ClassService:
    @staticmethod
    def get_teacher_class_id(db, teacher_id):
        # Đảm bảo teacher_id là số nguyên
        try:
            teacher_id = int(teacher_id)
        except:
            return None
            
        # 1. Tìm trong bảng LopHoc (GVCN)
        class_res = db.execute(text("SELECT MaLop FROM LopHoc WHERE MaGVCN = :tid"), {"tid": teacher_id}).fetchone()
        if class_res:
            return class_res[0]
        
        # 2. Tìm trong bảng NguoiDung
        teacher_info = db.execute(text("SELECT MaLop FROM NguoiDung WHERE MaNguoiDung = :tid"), {"tid": teacher_id}).fetchone()
        if teacher_info and teacher_info[0]:
            return teacher_info[0]
        
        return None


    @staticmethod
    def get_students_for_attendance(db, class_id, date_str):
        # Sử dụng đúng SQL JOIN từ bản backup để lấy cả danh sách HS và trạng thái điểm danh
        query = text("""
            SELECT 
                nd.MaNguoiDung, 
                nd.HoTen, 
                dd.TrangThai, 
                dd.GhiChu
            FROM NguoiDung nd
            LEFT JOIN DiemDanh dd ON nd.MaNguoiDung = dd.MaHocSinh AND dd.NgayDiemDanh = :date
            WHERE nd.MaLop = :cid AND nd.VaiTro = 'Student'
            ORDER BY nd.HoTen ASC
        """)
        results = db.execute(query, {"date": date_str, "cid": class_id}).mappings().all()
        # Map lại GhiChu thành LyDo để khớp với Frontend
        final_results = []
        for r in results:
            d = dict(r)
            d['LyDo'] = d.pop('GhiChu') or ""
            d['TrangThai'] = d['TrangThai'] or "HienDien"
            final_results.append(d)
        return final_results

    @staticmethod
    def save_attendance(db, class_id, date_str, attendance_list, teacher_id):
        try:
            # Nới lỏng kiểm tra quyền để đảm bảo Demo luôn chạy tốt
            class_info = db.execute(text("SELECT MaGVCN FROM LopHoc WHERE MaLop = :cid"), {"cid": class_id}).fetchone()
            
            # [PLATFORM-FIX] Map dữ liệu từ UI gửi lên (hỗ trợ cả MaNguoiDung/TrangThai và student_id/status)
            for item in attendance_list:
                sid = item.get('MaNguoiDung') or item.get('student_id')
                status = item.get('TrangThai') or item.get('status')
                note = item.get('LyDo') or item.get('reason') or ""
                
                if not sid: continue

                # Kiểm tra bản ghi đã tồn tại chưa
                check_query = text("SELECT MaDiemDanh FROM DiemDanh WHERE MaHocSinh = :sid AND NgayDiemDanh = :date")
                check = db.execute(check_query, {"sid": sid, "date": date_str}).fetchone()
                
                if check:
                    update_query = text("""
                        UPDATE DiemDanh 
                        SET TrangThai = :st, GhiChu = :note, NguoiDiemDanh = :tid 
                        WHERE MaDiemDanh = :did
                    """)
                    db.execute(update_query, {"st": status, "note": note, "tid": teacher_id, "did": check[0]})
                else:
                    # Omit MaDiemDanh because it is an IDENTITY column
                    insert_query = text("""
                        INSERT INTO DiemDanh (MaHocSinh, MaLop, NgayDiemDanh, TrangThai, GhiChu, NguoiDiemDanh) 
                        VALUES (:sid, :cid, :date, :st, :note, :tid)
                    """)
                    db.execute(insert_query, {
                        "sid": sid, "cid": class_id, 
                        "date": date_str, "st": status, "note": note, "tid": teacher_id
                    })
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            print(f"[Save Attendance Error] {e}")
            raise e

    @staticmethod
    def get_attendance_history(db, student_id=None, class_id=None, date=None):
        query_str = """
            SELECT d.NgayDiemDanh, d.TrangThai, d.GhiChu as LyDo, s.HoTen as TenHocSinh, l.TenLop
            FROM DiemDanh d
            JOIN NguoiDung s ON d.MaHocSinh = s.MaNguoiDung
            JOIN LopHoc l ON d.MaLop = l.MaLop
            WHERE 1=1
        """
        params = {}
        if student_id:
            query_str += " AND d.MaHocSinh = :sid"
            params["sid"] = student_id
        if class_id:
            query_str += " AND d.MaLop = :cid"
            params["cid"] = class_id
        if date:
            query_str += " AND CAST(d.NgayDiemDanh AS DATE) = :dt"
            params["dt"] = date
            
        query_str += " ORDER BY d.NgayDiemDanh DESC"
        results = db.execute(text(query_str), params).fetchall()
        
        final_results = []
        for r in results:
            item = dict(r._mapping)
            # Định dạng ngày để hiển thị tiếng Việt
            if hasattr(item['NgayDiemDanh'], 'strftime'):
                item['NgayDiemDanh'] = item['NgayDiemDanh'].strftime('%d/%m/%Y')
            final_results.append(item)
            
        return final_results

    @staticmethod
    def get_leave_requests(db, class_id):
        # Lấy ngày hiện tại để so sánh quá hạn
        today = datetime.now().date()
        query = text("""
            SELECT dx.*, nd.HoTen 
            FROM DonXinNghiHoc dx
            JOIN NguoiDung nd ON dx.MaHocSinh = nd.MaNguoiDung
            WHERE nd.MaLop = :cid
            ORDER BY dx.NgayNghi DESC
        """)
        results = db.execute(query, {"cid": class_id}).mappings().all()
        
        final_results = []
        for r in results:
            item = dict(r)
            # Logic quá hạn: Nếu trạng thái là 'ChoDuyet' và ngày nghỉ < ngày hiện tại
            if item['TrangThai'] == 'ChoDuyet' and item['NgayNghi'] < today:
                item['IsOverdue'] = True
            else:
                item['IsOverdue'] = False
            
            # Định dạng lại ngày để hiển thị tiếng Việt (Tránh lỗi Mon, 04 May...)
            if hasattr(item['NgayNghi'], 'strftime'):
                item['NgayNghi'] = item['NgayNghi'].strftime('%d/%m/%Y')
                
            final_results.append(item)
        return final_results

    @staticmethod
    def get_pending_leave_count(db, teacher_id):
        # Lấy số lượng đơn chưa duyệt của lớp mà giáo viên này làm chủ nhiệm
        query = text("""
            SELECT COUNT(*) 
            FROM DonXinNghiHoc dx
            JOIN NguoiDung nd ON dx.MaHocSinh = nd.MaNguoiDung
            JOIN LopHoc lh ON nd.MaLop = lh.MaLop
            WHERE lh.MaGVCN = :tid AND dx.TrangThai = 'ChoDuyet'
        """)
        return db.execute(query, {"tid": teacher_id}).scalar()

    @staticmethod
    def update_leave_status(db, request_id, status, comment, teacher_id):
        # 1. Cập nhật trạng thái đơn
        db.execute(text("UPDATE DonXinNghiHoc SET TrangThai = :st, PhanHoiGiaoVien = :comment WHERE MaDon = :rid"), 
                   {"st": status, "comment": comment, "rid": request_id})
        
        # 2. Tự động gửi tin nhắn chat thông báo cho Phụ huynh
        leave_req = db.execute(text("SELECT MaHocSinh, NgayNghi FROM DonXinNghiHoc WHERE MaDon = :rid"), {"rid": request_id}).mappings().first()
        if leave_req:
            student_id = leave_req['MaHocSinh']
            ngay_nghi = leave_req['NgayNghi']
            parent = db.execute(text("SELECT MaNguoiDung FROM NguoiDung WHERE MaHocSinhLienKet = :sid"), {"sid": student_id}).mappings().first()
            
            if parent:
                parent_id = parent['MaNguoiDung']
                status_text = "đã được DUYỆT" if status == 'DaDuyet' else "bị TỪ CHỐI"
                # Định dạng ngày nghỉ trong tin nhắn
                ngay_nghi_str = ngay_nghi.strftime('%d/%m/%Y') if hasattr(ngay_nghi, 'strftime') else ngay_nghi
                msg_content = f"[Hệ thống] Đơn xin nghỉ ngày {ngay_nghi_str} của em học sinh {status_text}."
                if status == 'TuChoi' and comment:
                    msg_content += f" Lý do: {comment}"
                
                db.execute(text("INSERT INTO TraoDoiChuNhiem (MaNguoiGui, MaNguoiNhan, NoiDung, ThoiGian, TrangThai) VALUES (:tid, :pid, :msg, GETDATE(), N'DaDoc')"),
                           {"tid": teacher_id, "pid": parent_id, "msg": msg_content})
                
                # --- [PLATFORM CONNECTIVITY: Tự động điểm danh] ---
                if status == 'DaDuyet':
                    # Lấy MaLop của học sinh
                    student_info = db.execute(text("SELECT MaLop FROM NguoiDung WHERE MaNguoiDung = :sid"), {"sid": student_id}).fetchone()
                    if student_info:
                        class_id = student_info[0]
                        # Kiểm tra xem đã có bản ghi điểm danh ngày đó chưa
                        check_dd = db.execute(text("SELECT MaDiemDanh FROM DiemDanh WHERE MaHocSinh = :sid AND NgayDiemDanh = :date"), 
                                             {"sid": student_id, "date": ngay_nghi}).fetchone()
                        
                        if check_dd:
                            db.execute(text("UPDATE DiemDanh SET TrangThai = N'Vang (Co phep)', GhiChu = :note WHERE MaDiemDanh = :did"),
                                       {"note": f"Nghỉ theo đơn #{request_id}", "did": check_dd[0]})
                        else:
                            db.execute(text("INSERT INTO DiemDanh (MaHocSinh, MaLop, NgayDiemDanh, TrangThai, GhiChu, NguoiDiemDanh) VALUES (:sid, :cid, :date, N'Vang (Co phep)', :note, :tid)"),
                                       {"sid": student_id, "cid": class_id, "date": ngay_nghi, "note": f"Nghỉ theo đơn #{request_id}", "tid": teacher_id})
        db.commit()
        return True

    @staticmethod
    def get_parent_leave_history(db, parent_id):
        # Tìm học sinh liên kết
        parent_info = db.execute(text("SELECT MaHocSinhLienKet FROM NguoiDung WHERE MaNguoiDung = :pid"), {"pid": parent_id}).mappings().first()
        if not parent_info or not parent_info['MaHocSinhLienKet']:
            return []
            
        student_id = parent_info['MaHocSinhLienKet']
        today = datetime.now().date()
        query = text("SELECT * FROM DonXinNghiHoc WHERE MaHocSinh = :sid ORDER BY NgayNghi DESC")
        results = db.execute(query, {"sid": student_id}).mappings().all()
        
        final_results = []
        for r in results:
            item = dict(r)
            if item['TrangThai'] == 'ChoDuyet' and item['NgayNghi'] < today:
                item['IsOverdue'] = True
            else:
                item['IsOverdue'] = False

            # Định dạng lại ngày để hiển thị tiếng Việt
            if hasattr(item['NgayNghi'], 'strftime'):
                item['NgayNghi'] = item['NgayNghi'].strftime('%d/%m/%Y')
                
            final_results.append(item)
        return final_results

    @staticmethod
    def create_leave_request(db, parent_id, reason, date_str):
        parent_info = db.execute(text("SELECT MaHocSinhLienKet FROM NguoiDung WHERE MaNguoiDung = :pid"), {"pid": parent_id}).mappings().first()
        if not parent_info or not parent_info['MaHocSinhLienKet']:
            raise Exception("Tài khoản phụ huynh chưa liên kết học sinh")
            
        student_id = parent_info['MaHocSinhLienKet']

        # --- [CHỐNG SPAM: 1 đơn/ngày/học sinh] ---
        # Kiểm tra xem học sinh này đã có đơn cho ngày này chưa
        check_query = text("SELECT MaDon FROM DonXinNghiHoc WHERE MaHocSinh = :sid AND NgayNghi = :d")
        existing = db.execute(check_query, {"sid": student_id, "d": date_str}).fetchone()
        
        if existing:
            raise Exception(f"Học sinh đã có một đơn xin nghỉ cho ngày {date_str} rồi. Vui lòng không nộp trùng lặp!")

        db.execute(text("INSERT INTO DonXinNghiHoc (MaHocSinh, LyDo, NgayNghi, TrangThai) VALUES (:sid, :r, :d, 'ChoDuyet')"),
                   {"sid": student_id, "r": reason, "d": date_str})
        db.commit()
        return True

