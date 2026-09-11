from flask import Blueprint, jsonify, session
from sqlalchemy import text
import os
import sys

# Đảm bảo import được config từ thư mục app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.config import SessionLocal

student_bp = Blueprint('student', __name__, url_prefix='/api/student')

@student_bp.route('/dashboard/summary', methods=['GET'])
def get_student_dashboard():
    # Giả sử lấy MaNguoiDung từ session (trong thực tế sẽ lấy sau khi login)
    user_id = session.get('user_id', 3) # Mặc định là 3 (Học sinh mẫu) để demo
    
    db = SessionLocal()
    try:
        # 1. Lấy thông tin cơ bản và Lớp
        user_query = text("""
            SELECT nd.HoTen, l.TenLop, nd.AnhDaiDien 
            FROM NguoiDung nd
            LEFT JOIN LopHoc l ON nd.MaLop = l.MaLop
            WHERE nd.MaNguoiDung = :uid
        """)
        user_info = db.execute(user_query, {"uid": user_id}).fetchone()
        
        # 2. Lấy tổng điểm XP từ Nhật ký nề nếp
        xp_query = text("SELECT ISNULL(SUM(DiemXP), 0) FROM NhatKyReNep WHERE MaHocSinh = :uid")
        total_xp = db.execute(xp_query, {"uid": user_id}).scalar()
        
        # 3. Lấy danh sách bài tập (Tasks) kèm trạng thái nộp bài
        tasks_query = text("""
            SELECT bt.MaBaiTap, bt.TieuDe, bt.NoiDung, bt.LinkGoogleForm, bt.FileDinhKem as FileBaiTap,
                   mh.TenMonHoc, bt.HanNop, bt.LoaiBai, 
                   bl.MaBaiLam, bl.NoiDungBaiLam as NoiDungHS, bl.FileDinhKem as FileHS
            FROM BaiTap bt
            JOIN PhanCongGiangDay pc ON bt.MaPhanCong = pc.MaPhanCong
            JOIN MonHoc mh ON pc.MaMonHoc = mh.MaMonHoc
            LEFT JOIN BaiLam bl ON bt.MaBaiTap = bl.MaBaiTap AND bl.MaHocSinh = :uid
            WHERE pc.MaLop = (SELECT MaLop FROM NguoiDung WHERE MaNguoiDung = :uid)
            ORDER BY bt.MaBaiTap DESC
        """)
        tasks_data = db.execute(tasks_query, {"uid": user_id}).fetchall()
        
        tasks_list = []
        pending_count = 0
        completed_count = 0
        
        for task in tasks_data:
            is_submitted = task.MaBaiLam is not None
            if is_submitted:
                completed_count += 1
            else:
                pending_count += 1
                
            tasks_list.append({
                "id": task.MaBaiTap,
                "title": f"[{task.TenMonHoc}] {task.TieuDe}",
                "description": task.NoiDung,
                "link_form": task.LinkGoogleForm,
                "file_tap": task.FileBaiTap,
                "is_file_tap_img": task.FileBaiTap.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) if task.FileBaiTap else False,
                "subject": task.TenMonHoc,
                "icon": "ph-exam" if task.LoaiBai == 'TracNghiem' else "ph-book-open",
                "color": "rose" if task.LoaiBai == 'TracNghiem' else "blue",
                "deadline": task.HanNop.strftime("%d/%m/%Y") if task.HanNop else "N/A",
                "deadline_iso": task.HanNop.isoformat() if task.HanNop else None,
                "status": "Đã nộp" if is_submitted else "Đang chờ",
                "is_submitted": is_submitted,
                "submitted_content": task.NoiDungHS,
                "submitted_file": task.FileHS,
                "is_submitted_img": task.FileHS.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) if task.FileHS else False,
                "action_text": "Xem lại" if is_submitted else "Nộp bài ngay"
            })

        # Cấu trúc trả về giống hệt mock data cũ để không làm hỏng Frontend
        real_data = {
            "success": True,
            "data": {
                "user": {
                    "name": user_info.HoTen if user_info else "N/A",
                    "first_name": user_info.HoTen.split()[-1] if user_info else "HS",
                    "class_name": user_info.TenLop if user_info else "N/A",
                    "avatar": user_info.AnhDaiDien if user_info and user_info.AnhDaiDien else "https://api.dicebear.com/7.x/avataaars/svg?seed=student",
                    "current_period": "Tiết 2",
                    "today_alert": "Chào mừng bạn quay lại hệ thống lớp học số!"
                },
                "stats": {
                    "xp": total_xp,
                    "total_tasks": len(tasks_list),
                    "pending_count": pending_count,
                    "completed_count": completed_count
                },
                "tasks": tasks_list,
                "badges": [
                    {"name": "Học sinh giỏi", "icon": "🏆", "color": "amber", "multiplier": "x3", "locked": False},
                    {"name": "Thiên tài Hóa", "icon": "🔬", "color": "blue", "multiplier": "", "locked": False}
                ]
            }
        }
        return jsonify(real_data)
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()