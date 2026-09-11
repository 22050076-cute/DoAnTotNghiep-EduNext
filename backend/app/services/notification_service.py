from sqlalchemy import text
from app.utils.notification_utils import RealEmailDispatcher

class NotificationHub:
    @staticmethod
    def dispatch_announcement_to_class(db, announcement_data, class_id):
        """
        Gửi thông báo đến toàn bộ học sinh trong lớp qua nhiều kênh (Chạy ngầm)
        """
        import threading
        title = announcement_data.get('title')
        content = announcement_data.get('content')
        
        # 1. Tìm toàn bộ học sinh trong lớp để lấy Email (Thực hiện đồng bộ để đảm bảo có dữ liệu)
        query = text("""
            SELECT Email, HoTen 
            FROM NguoiDung 
            WHERE MaLop = :cid AND UPPER(VaiTro) = 'STUDENT'
        """)
        students = db.execute(query, {"cid": class_id}).mappings().all()
        
        # Chuyển đổi sang list dictionary để luồng ngầm có thể đọc độc lập
        students_list = [dict(s) for s in students]
        
        print(f"\n\033[93m[HUB ACTIVE]\033[0m Starting background dispatch to {len(students_list)} recipients in Class {class_id}...")
        
        # 2. Định nghĩa hàm gửi mail ngầm
        def background_dispatch(recipients, ann_title, ann_content):
            try:
                for student in recipients:
                    email = student.get('Email')
                    name = student.get('HoTen')
                    
                    if not email: continue
                    
                    subject = f"[EduNext] Thông báo mới: {ann_title}"
                    body = f"Chào {name},\n\nGiáo viên chủ nhiệm vừa gửi một thông báo mới:\n\n---\n{ann_content}\n---\n\nVui lòng đăng nhập hệ thống để xem chi tiết."
                    
                    # Gọi Dispatcher gửi thật
                    RealEmailDispatcher.send(email, subject, body)
            except Exception as e:
                print(f"\n\033[91m[HUB ERROR]\033[0m Background Dispatcher failed: {str(e)}")

        # 3. Kích hoạt luồng ngầm và trả về kết quả ngay lập tức
        thread = threading.Thread(target=background_dispatch, args=(students_list, title, content))
        thread.daemon = True # Luồng này sẽ tự kết thúc khi main thread kết thúc
        thread.start()
        
        return True

    @staticmethod
    def notify_parent_conduct_event(db, student_id, xp, reason, teacher_id=None):
        try:
            # 1. Lấy tên học sinh và ID Giáo viên chủ nhiệm
            query = text("""
                SELECT nd.HoTen, l.MaGVCN 
                FROM NguoiDung nd
                LEFT JOIN LopHoc l ON nd.MaLop = l.MaLop
                WHERE nd.MaNguoiDung = :sid
            """)
            res = db.execute(query, {"sid": student_id}).fetchone()
            
            child_name = res.HoTen if res else f"Học sinh (ID: {student_id})"
            real_teacher_id = res.MaGVCN if (res and res.MaGVCN) else (teacher_id or 1)
            
            # 2. Tạo nội dung dựa trên loại điểm (Cộng hay Trừ)
            if xp > 0:
                title = f"📢 [NỀ NẾP] Thành tích mới: {child_name}"
                message = f"Chúc mừng! Học sinh {child_name} vừa được khen thưởng {xp} XP. \nLý do: {reason}"
            else:
                title = f"⚠️ [NỀ NẾP] Nhắc nhở vi phạm: {child_name}"
                message = f"Thông báo: Học sinh {child_name} vừa bị trừ {abs(xp)} XP do vi phạm nề nếp. \nLý do: {reason}"
            
            # 3. Insert vào bảng ThongBao (Chế độ Cá nhân: PhamVi='CaNhan', MaLop lưu ID học sinh)
            ins_query = text("""
                INSERT INTO ThongBao (TieuDe, NoiDung, NgayGui, MaLop, MaNguoiGui, PhamVi)
                VALUES (:title, :content, GETDATE(), :sid, :tid, 'CaNhan')
            """)
            db.execute(ins_query, {"title": title, "content": message, "sid": student_id, "tid": real_teacher_id})
            db.commit()
            
            print(f"\033[92m[PLATFORM SUCCESS]\033[0m Created conduct notification for {child_name}")
            return True
        except Exception as e:
            print(f"\033[91m[PLATFORM ERROR]\033[0m {e}")
            return False

