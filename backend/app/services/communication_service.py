from sqlalchemy import text
from datetime import datetime
from app.services.notification_service import NotificationHub

class CommunicationService:
    @staticmethod
    @staticmethod
    def get_chat_history(db, current_user_id, with_user_id):
        current_user_id = int(current_user_id)
        other_user_id = int(with_user_id)
        
        results = []
        if other_user_id < 0:
            # TIN NHẮN NHÓM
            if other_user_id <= -10000:
                event_id = abs(other_user_id) - 10000
                group_tag = f"EVENT_{event_id}"
            else:
                group_class_id = abs(other_user_id)
                group_tag = f"GROUP_{group_class_id}"

            query = text("""
                SELECT t.*, t.ThoiGian as NgayGui, n.HoTen as TenNguoiGui 
                FROM TraoDoiChuNhiem t
                JOIN NguoiDung n ON t.MaNguoiGui = n.MaNguoiDung
                WHERE t.TieuDe = :group_tag
                ORDER BY t.ThoiGian ASC
            """)
            results = db.execute(query, {"group_tag": group_tag}).fetchall()

            # ĐÁNH DẤU ĐÃ ĐỌC cho tin nhắn NHÓM
            db.execute(text("""
                UPDATE TraoDoiChuNhiem 
                SET DaDoc = 1 
                WHERE TieuDe = :tag AND MaNguoiNhan = :uid
            """), {"tag": group_tag, "uid": current_user_id})
            db.commit()
        else:
            # TIN NHẮN CÁ NHÂN
            query = text("""
                SELECT t.*, t.ThoiGian as NgayGui, n.HoTen as TenNguoiGui
                FROM TraoDoiChuNhiem t
                JOIN NguoiDung n ON t.MaNguoiGui = n.MaNguoiDung
                WHERE (ISNULL(t.TieuDe, '') = '' OR (t.TieuDe NOT LIKE 'GROUP_%' AND t.TieuDe NOT LIKE 'EVENT_%'))
                AND ((t.MaNguoiGui = :c AND t.MaNguoiNhan = :o) OR (t.MaNguoiGui = :o AND t.MaNguoiNhan = :c))
                ORDER BY t.ThoiGian ASC
            """)
            results = db.execute(query, {"c": current_user_id, "o": other_user_id}).fetchall()
            
            # ĐÁNH DẤU ĐÃ ĐỌC cho tin nhắn CÁ NHÂN
            db.execute(text("""
                UPDATE TraoDoiChuNhiem 
                SET DaDoc = 1 
                WHERE MaNguoiGui = :o AND MaNguoiNhan = :c AND (ISNULL(TieuDe, '') = '')
            """), {"o": other_user_id, "c": current_user_id})
            db.commit()
        
        return results

    @staticmethod
    def send_private_message(db, sender_id, receiver_id, content):
        sender_id = int(sender_id)
        receiver_id = int(receiver_id)
        
        target_receiver_id = receiver_id
        tag = None

        if receiver_id < 0:
            if receiver_id <= -10000:
                # TIN NHẮN NHÓM SỰ KIỆN
                event_id = abs(receiver_id) - 10000
                # Lấy người tạo sự kiện để gán làm người nhận chính (quy tắc bảng TraoDoiChuNhiem)
                creator_res = db.execute(text("SELECT MaNguoiTao FROM SuKien WHERE MaSuKien = :eid"), {"eid": event_id}).fetchone()
                target_receiver_id = creator_res[0] if creator_res else sender_id
                tag = f"EVENT_{event_id}"
            else:
                # TIN NHẮN NHÓM LỚP
                class_id = abs(receiver_id)
                gvcn_res = db.execute(text("SELECT MaGVCN FROM LopHoc WHERE MaLop = :cid"), {"cid": class_id}).fetchone()
                if gvcn_res and gvcn_res[0]:
                    target_receiver_id = gvcn_res[0]
                else:
                    # Sửa lỗi: Thêm FROM NguoiDung
                    gv_res = db.execute(text("SELECT MaNguoiDung FROM NguoiDung WHERE MaLop = :cid AND VaiTro = 'Teacher'"), {"cid": class_id}).fetchone()
                    target_receiver_id = gv_res[0] if gv_res else sender_id
                tag = f"GROUP_{class_id}"

        if tag is None and sender_id == target_receiver_id:
            # Cho phép gửi tin nhắn cho chính mình nếu là bản nháp (không chặn quá gắt)
            pass

        db.execute(text("""
            INSERT INTO TraoDoiChuNhiem (MaNguoiGui, MaNguoiNhan, TieuDe, NoiDung, ThoiGian, TrangThai) 
            VALUES (:s, :r, :t, :c, GETDATE(), N'ChoPhanHoi')
        """), {"s": sender_id, "r": target_receiver_id, "t": tag, "c": content})
        db.commit()
        return True

    @staticmethod
    def get_parent_chat_contacts(db, parent_id):
        parent_id = int(parent_id)
        contacts = []
        
        # 1. Lấy giáo viên chủ nhiệm (Liên hệ cá nhân)
        child_info = db.execute(text("""
            SELECT s.MaLop 
            FROM NguoiDung p 
            JOIN NguoiDung s ON p.MaHocSinhLienKet = s.MaNguoiDung 
            WHERE p.MaNguoiDung = :pid
        """), {"pid": parent_id}).fetchone()
        
        if child_info and child_info.MaLop:
            # Lấy GVCN của lớp con
            teacher = db.execute(text("""
                SELECT nd.MaNguoiDung, nd.HoTen
                FROM NguoiDung nd
                JOIN LopHoc lh ON nd.MaNguoiDung = lh.MaGVCN
                WHERE lh.MaLop = :cid
            """), {"cid": child_info.MaLop}).fetchone()
            
            if teacher:
                # Lấy số tin nhắn chưa đọc
                unread = db.execute(text("SELECT COUNT(*) FROM TraoDoiChuNhiem WHERE MaNguoiGui = :o AND MaNguoiNhan = :c AND ISNULL(DaDoc, 0) = 0 AND (ISNULL(TieuDe, '') = '')"), 
                                   {"o": teacher.MaNguoiDung, "c": parent_id}).scalar()
                contacts.append({
                    "MaNguoiDung": teacher.MaNguoiDung, 
                    "HoTen": teacher.HoTen, 
                    "Role": "GVCN", 
                    "TenCon": "Giáo viên chủ nhiệm",
                    "IsGroup": False,
                    "UnreadCount": unread or 0
                })

        # 2. Lấy NHÓM SỰ KIỆN đã đăng ký
        event_groups = db.execute(text("""
            SELECT sk.MaSuKien, sk.TieuDe
            FROM DangKySuKien dk
            JOIN SuKien sk ON dk.MaSuKien = sk.MaSuKien
            WHERE dk.MaNguoiDung = :uid
        """), {"uid": parent_id}).fetchall()
        
        for eg in event_groups:
            contacts.append({
                "MaNguoiDung": -10000 - eg.MaSuKien,
                "HoTen": f"NHÓM: {eg.TieuDe}",
                "Role": "Sự kiện",
                "TenCon": "Thành viên sự kiện",
                "IsGroup": True
            })
            
        contacts.sort(key=lambda x: x.get('UnreadCount', 0), reverse=True)
        return contacts

    @staticmethod
    def get_student_chat_contacts(db, student_id):
        student_id = int(student_id)
        contacts = []
        
        # 1. Lấy thông tin lớp và giáo viên của học sinh
        u_info = db.execute(text("""
            SELECT nd.MaLop, lh.TenLop, gv.MaNguoiDung as MaGV, gv.HoTen as TenGV
            FROM NguoiDung nd
            LEFT JOIN LopHoc lh ON nd.MaLop = lh.MaLop
            LEFT JOIN NguoiDung gv ON lh.MaGVCN = gv.MaNguoiDung
            WHERE nd.MaNguoiDung = :sid
        """), {"sid": student_id}).fetchone()
        
        if u_info and u_info.MaLop:
            # Thêm nhóm lớp
            contacts.append({
                "MaNguoiDung": -int(u_info.MaLop),
                "HoTen": f"NHÓM LỚP {u_info.TenLop}",
                "Role": "Nhóm Lớp",
                "TenCon": "GVCN & Bạn học",
                "IsGroup": True
            })
            # Thêm GVCN
            if u_info.MaGV:
                unread = db.execute(text("SELECT COUNT(*) FROM TraoDoiChuNhiem WHERE MaNguoiGui = :o AND MaNguoiNhan = :c AND ISNULL(DaDoc, 0) = 0 AND (ISNULL(TieuDe, '') = '')"), 
                                   {"o": u_info.MaGV, "c": student_id}).scalar()
                contacts.append({
                    "MaNguoiDung": u_info.MaGV,
                    "HoTen": u_info.TenGV,
                    "Role": "GVCN",
                    "TenCon": "Giáo viên chủ nhiệm",
                    "IsGroup": False,
                    "UnreadCount": unread or 0
                })

        # 2. Lấy NHÓM SỰ KIỆN đã đăng ký
        event_groups = db.execute(text("""
            SELECT sk.MaSuKien, sk.TieuDe
            FROM DangKySuKien dk
            JOIN SuKien sk ON dk.MaSuKien = sk.MaSuKien
            WHERE dk.MaNguoiDung = :uid
        """), {"uid": student_id}).fetchall()
        
        for eg in event_groups:
            contacts.append({
                "MaNguoiDung": -10000 - eg.MaSuKien,
                "HoTen": f"NHÓM: {eg.TieuDe}",
                "Role": "Sự kiện",
                "TenCon": "Thành viên sự kiện",
                "IsGroup": True
            })
            
        contacts.sort(key=lambda x: x.get('UnreadCount', 0), reverse=True)
        return contacts

    @staticmethod
    def get_teacher_chat_contacts(db, teacher_id):
        teacher_id = int(teacher_id)
        contacts = []
        
        # 1. NHÓM LỚP (Nếu là GVCN)
        class_res = db.execute(text("SELECT MaLop, TenLop FROM LopHoc WHERE MaGVCN = :tid"), {"tid": teacher_id}).fetchone()
        if class_res:
            group_tag = f"GROUP_{class_res.MaLop}"
            unread_group = db.execute(text("SELECT COUNT(*) FROM TraoDoiChuNhiem WHERE TieuDe = :tag AND MaNguoiNhan = :uid AND ISNULL(DaDoc, 0) = 0"), 
                                     {"tag": group_tag, "uid": teacher_id}).scalar()
            contacts.append({
                "MaNguoiDung": -int(class_res.MaLop),
                "HoTen": f"NHÓM LỚP {class_res.TenLop}",
                "Role": "Chủ nhiệm",
                "TenCon": "GVCN & Phụ huynh",
                "IsGroup": True,
                "UnreadCount": unread_group or 0
            })
            # Danh sách phụ huynh cá nhân
            p_results = db.execute(text("""
                SELECT p.MaNguoiDung, p.HoTen as ParentName, s.HoTen as StudentName
                FROM NguoiDung p
                JOIN NguoiDung s ON p.MaHocSinhLienKet = s.MaNguoiDung
                WHERE s.MaLop = :cid AND p.VaiTro = 'Parent'
            """), {"cid": class_res.MaLop}).fetchall()
            for r in p_results:
                unread = db.execute(text("SELECT COUNT(*) FROM TraoDoiChuNhiem WHERE MaNguoiGui = :o AND MaNguoiNhan = :c AND ISNULL(DaDoc, 0) = 0 AND (ISNULL(TieuDe, '') = '')"), 
                                   {"o": r.MaNguoiDung, "c": teacher_id}).scalar()
                contacts.append({"MaNguoiDung": r.MaNguoiDung, "HoTen": r.ParentName, "TenCon": f"PH em {r.StudentName}", "IsGroup": False, "UnreadCount": unread or 0})

            # Danh sách học sinh cá nhân
            s_results = db.execute(text("""
                SELECT MaNguoiDung, HoTen FROM NguoiDung WHERE MaLop = :cid AND VaiTro = 'Student'
            """), {"cid": class_res.MaLop}).fetchall()
            for r in s_results:
                unread = db.execute(text("SELECT COUNT(*) FROM TraoDoiChuNhiem WHERE MaNguoiGui = :o AND MaNguoiNhan = :c AND ISNULL(DaDoc, 0) = 0 AND (ISNULL(TieuDe, '') = '')"), 
                                   {"o": r.MaNguoiDung, "c": teacher_id}).scalar()
                contacts.append({"MaNguoiDung": r.MaNguoiDung, "HoTen": r.HoTen, "TenCon": "Học sinh lớp", "IsGroup": False, "UnreadCount": unread or 0})

        # 2. NHÓM SỰ KIỆN (Bao gồm cả sự kiện tạo và sự kiện tham gia)
        event_groups = db.execute(text("""
            SELECT DISTINCT sk.MaSuKien, sk.TieuDe 
            FROM SuKien sk
            LEFT JOIN DangKySuKien dk ON sk.MaSuKien = dk.MaSuKien
            WHERE sk.MaNguoiTao = :tid OR dk.MaNguoiDung = :tid
        """), {"tid": teacher_id}).fetchall()
        
        for eg in event_groups:
            tag = f"EVENT_{eg.MaSuKien}"
            unread_ev = db.execute(text("SELECT COUNT(*) FROM TraoDoiChuNhiem WHERE TieuDe = :tag AND MaNguoiNhan = :uid AND ISNULL(DaDoc, 0) = 0"), 
                                  {"tag": tag, "uid": teacher_id}).scalar()
            # Tránh trùng lặp nếu đã có trong danh sách
            if not any(c.get('MaNguoiDung') == (-10000 - eg.MaSuKien) for c in contacts):
                contacts.append({
                    "MaNguoiDung": -10000 - eg.MaSuKien,
                    "HoTen": f"SỰ KIỆN: {eg.TieuDe}",
                    "Role": "Thành viên/Quản lý",
                    "TenCon": "Nhóm sự kiện",
                    "IsGroup": True,
                    "UnreadCount": unread_ev or 0
                })

        # 3. TRUY QUÉT TIN NHẮN "LẠ" (Người ngoài lớp hiện tại gửi tới)
        others = db.execute(text("""
            SELECT DISTINCT nd.MaNguoiDung, nd.HoTen, nd.VaiTro
            FROM TraoDoiChuNhiem t
            JOIN NguoiDung nd ON t.MaNguoiGui = nd.MaNguoiDung
            WHERE t.MaNguoiNhan = :uid AND ISNULL(t.DaDoc, 0) = 0 AND (ISNULL(t.TieuDe, '') = '')
        """), {"uid": teacher_id}).fetchall()
        
        for o in others:
            # Nếu người này chưa có trong danh sách thì thêm vào
            if not any(c.get('MaNguoiDung') == o.MaNguoiDung for c in contacts):
                unread = db.execute(text("SELECT COUNT(*) FROM TraoDoiChuNhiem WHERE MaNguoiGui = :o AND MaNguoiNhan = :c AND ISNULL(DaDoc, 0) = 0 AND (ISNULL(TieuDe, '') = '')"), 
                                   {"o": o.MaNguoiDung, "c": teacher_id}).scalar()
                contacts.append({
                    "MaNguoiDung": o.MaNguoiDung, 
                    "HoTen": o.HoTen, 
                    "Role": "Khác", 
                    "TenCon": f"Liên hệ ngoài lớp ({o.VaiTro})", 
                    "IsGroup": False, 
                    "UnreadCount": unread or 0
                })
            
        contacts.sort(key=lambda x: x.get('UnreadCount', 0), reverse=True)
        return contacts

    @staticmethod
    def get_announcements(db, class_id, current_user_id=None):
        try:
            uid = int(current_user_id) if current_user_id else 0
            cid = int(class_id) if class_id else 0
            
            # Lấy ID con liên kết nếu là Phụ huynh
            child_id = 0
            if uid:
                try:
                    child_res = db.execute(text("SELECT MaHocSinhLienKet FROM NguoiDung WHERE MaNguoiDung = :uid"), {"uid": uid}).fetchone()
                    child_id = child_res[0] if (child_res and child_res[0]) else 0
                except: pass

            query = text("""
                SELECT tb.*, 
                       CONVERT(VARCHAR, tb.NgayGui, 120) as NgayGui,
                       nd.HoTen as TenNguoiDang,
                       ISNULL((SELECT COUNT(*) FROM TuongTac WHERE MaDoiTuong = tb.MaThongBao AND LoaiDoiTuong = 'ThongBao'), 0) as LikeCount,
                       ISNULL((SELECT COUNT(*) FROM BinhLuan WHERE MaDoiTuong = tb.MaThongBao AND LoaiDoiTuong = 'ThongBao'), 0) as CommentCount,
                       CASE WHEN EXISTS (SELECT 1 FROM TuongTac WHERE MaDoiTuong = tb.MaThongBao AND LoaiDoiTuong = 'ThongBao' AND MaNguoiDung = :uid) THEN 1 ELSE 0 END as IsLiked
                FROM ThongBao tb
                LEFT JOIN NguoiDung nd ON tb.MaNguoiGui = nd.MaNguoiDung
                WHERE 
                    tb.PhamVi = 'Truong' 
                    OR (tb.PhamVi = 'Lop' AND (tb.MaLop = :cid OR tb.MaLop IS NULL OR tb.MaLop = 0))
                    OR (tb.PhamVi = 'CaNhan' AND (tb.MaLop = :sid OR tb.MaLop = :uid))
                    OR (tb.MaLop = :cid)
                    OR (tb.PhamVi IS NULL AND (tb.MaLop = :cid OR tb.MaLop IS NULL OR tb.MaLop = 0))
                ORDER BY tb.NgayGui DESC
            """)
            results = db.execute(query, {"cid": cid, "uid": uid, "sid": child_id}).mappings().all()
            return [dict(r) for r in results]
        except Exception as e:
            print(f"[SQL Error Announcements] {e}")
            return []


    @staticmethod
    def create_announcement(db, data, teacher_id):
        title = data.get('title', 'Thông báo từ GVCN')
        content = data.get('content')
        class_id = data.get('class_id')
        pham_vi = data.get('pham_vi', 'Lop') # 'Lop' hoặc 'Truong'
        hinh_anh = data.get('hinh_anh') # URL ảnh đính kèm
        
        # Đảm bảo teacher_id là số nguyên
        try:
            teacher_id = int(teacher_id)
        except:
            raise ValueError("ID giáo viên không hợp lệ")

        # Nếu phạm vi là Trường, không cần gán class_id cụ thể
        if pham_vi == 'Truong':
            class_id = None
        else:
            # Ép kiểu class_id sang int an toàn
            try:
                if class_id and str(class_id) not in ['undefined', 'null', '']:
                    class_id = int(class_id)
                else:
                    class_id = None
            except:
                class_id = None
                
            if not class_id:
                from app.services.class_service import ClassService
                class_id = ClassService.get_teacher_class_id(db, teacher_id)
                
            if not class_id:
                raise ValueError("Hệ thống không xác định được lớp học của bạn để gửi thông báo")
            
        if not content:
            raise ValueError("Nội dung thông báo không được để trống")
            
        from datetime import datetime
        now = datetime.now()

        db.execute(text("""
            INSERT INTO ThongBao (TieuDe, NoiDung, NgayGui, MaNguoiGui, MaLop, PhamVi, HinhAnh)
            VALUES (:t, :c, :now, :tid, :cid, :pv, :img)
        """), {"t": title, "c": content, "now": now, "tid": teacher_id, "cid": class_id, "pv": pham_vi, "img": hinh_anh})


        
        # --- [GOLD STANDARD UPGRADE] ---
        # Kích hoạt Notification Hub để gửi thông báo đa kênh (Simulated Email)
        try:
            NotificationHub.dispatch_announcement_to_class(db, {"title": title, "content": content}, class_id)
        except Exception as hub_err:
            print(f"[ERROR] NotificationHub failed: {str(hub_err)}")
            
        db.commit()
        return True

    @staticmethod
    def get_total_unread_count(db, user_id):
        try:
            # 1. Đếm tin nhắn cá nhân gửi ĐẾN user_id
            private_unread = db.execute(text("""
                SELECT COUNT(*) FROM TraoDoiChuNhiem 
                WHERE MaNguoiNhan = :uid AND ISNULL(DaDoc, 0) = 0 AND (ISNULL(TieuDe, '') = '' OR TieuDe IS NULL)
            """), {"uid": user_id}).scalar() or 0

            # 2. Đếm tin nhắn nhóm (Dành cho Giáo viên trong nhóm lớp mình chủ nhiệm)
            group_unread = db.execute(text("""
                SELECT COUNT(*) FROM TraoDoiChuNhiem 
                WHERE MaNguoiNhan = :uid AND ISNULL(DaDoc, 0) = 0 AND (TieuDe LIKE 'GROUP_%' OR TieuDe LIKE 'EVENT_%')
            """), {"uid": user_id}).scalar() or 0

            return private_unread + group_unread
        except:
            return 0

    @staticmethod
    def delete_announcement(db, ann_id, user_id):
        try:
            # Kiểm tra quyền
            res = db.execute(text("SELECT MaNguoiGui FROM ThongBao WHERE MaThongBao = :id"), {"id": ann_id}).fetchone()
            if not res: return False, "Thông báo không tồn tại"
            if int(res[0]) != int(user_id): return False, "Bạn không có quyền xóa thông báo này"
            
            # Xóa bình luận và tương tác trước
            db.execute(text("DELETE FROM BinhLuan WHERE MaDoiTuong = :id AND LoaiDoiTuong = 'ThongBao'"), {"id": ann_id})
            db.execute(text("DELETE FROM TuongTac WHERE MaDoiTuong = :id AND LoaiDoiTuong = 'ThongBao'"), {"id": ann_id})
            
            # Xóa thông báo
            db.execute(text("DELETE FROM ThongBao WHERE MaThongBao = :id"), {"id": ann_id})
            db.commit()
            return True, "Xóa thành công"
        except Exception as e:
            db.rollback()
            return False, str(e)

    @staticmethod
    def update_announcement(db, ann_id, data, user_id):
        try:
            # Kiểm tra quyền
            res = db.execute(text("SELECT MaNguoiGui FROM ThongBao WHERE MaThongBao = :id"), {"id": ann_id}).fetchone()
            if not res: return False, "Thông báo không tồn tại"
            if int(res[0]) != int(user_id): return False, "Bạn không có quyền sửa thông báo này"
            
            title = data.get('title')
            content = data.get('content')
            if not title or not content:
                return False, "Tiêu đề và nội dung không được trống"
                
            db.execute(text("""
                UPDATE ThongBao 
                SET TieuDe = :t, NoiDung = :c
                WHERE MaThongBao = :id
            """), {"t": title, "c": content, "id": ann_id})
            db.commit()
            return True, "Cập nhật thành công"
        except Exception as e:
            db.rollback()
            return False, str(e)

    @staticmethod
    def get_teacher_feedbacks(db, teacher_id):
        try:
            query = text("""
                SELECT TOP 10 t.NoiDung, t.ThoiGian, n.HoTen
                FROM TraoDoiChuNhiem t
                JOIN NguoiDung n ON t.MaNguoiGui = n.MaNguoiDung
                WHERE t.MaNguoiNhan = :tid AND n.VaiTro = 'Parent'
                ORDER BY t.ThoiGian DESC
            """)
            results = db.execute(query, {"tid": teacher_id}).fetchall()
            return [dict(r._mapping) for r in results]
        except Exception as e:
            print(f"[Error get_teacher_feedbacks] {e}")
            return []
