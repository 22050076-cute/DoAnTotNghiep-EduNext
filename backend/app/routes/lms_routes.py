import traceback
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from sqlalchemy import text

from app.services.lms_service import LMSService
from app.config import SessionLocal
from app.utils.file_utils import save_upload_file

lms_bp = Blueprint('lms', __name__)

# ==========================================
# 1. QUẢN LÝ HỌC LIỆU (MATERIALS)
# ==========================================

@lms_bp.route('/teacher/materials', methods=['GET'])
def get_teacher_materials():
    user_id = session.get('user_id') or request.args.get('user_id')
    if not user_id: 
        return jsonify({"success": False, "message": "Yêu cầu đăng nhập hoặc cung cấp user_id"}), 401
    
    db = SessionLocal()
    try:
        materials = LMSService.get_teacher_materials(db, user_id)
        return jsonify({"success": True, "materials": materials})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@lms_bp.route('/teacher/materials/upload', methods=['POST'])
def upload_material():
    user_id = session.get('user_id') or request.form.get('user_id')
    if not user_id:
        return jsonify({"success": False, "message": "Yêu cầu đăng nhập hoặc cung cấp user_id"}), 401

    if 'file' not in request.files:
        return jsonify({"success": False, "message": "Bạn chưa chọn tệp để tải lên!"}), 400
    
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({"success": False, "message": "Tên tệp không hợp lệ!"}), 400

    db = SessionLocal()
    try:
        web_path = save_upload_file(file, folder='materials')
        if not web_path:
            return jsonify({"success": False, "message": "Định dạng tệp không hỗ trợ hoặc lỗi lưu tệp!"}), 400
        
        file_ext = file.filename.split('.')[-1].upper() if '.' in file.filename else 'FILE'
        data = {
            "ten": request.form.get('ten', file.filename),
            "mon": request.form.get('mon'),
            "khoi": request.form.get('khoi'),
            "trang_thai": request.form.get('trang_thai', 1),
            "user_id": user_id,
            "ma_lop": request.form.get('ma_lop'),
            "mota": request.form.get('mota', ''),
            "path": web_path,
            "loai": file_ext
        }

        LMSService.upload_material(db, data)
        db.commit()
        return jsonify({"success": True, "message": "Đăng học liệu thành công!"})
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@lms_bp.route('/teacher/materials/<int:material_id>', methods=['DELETE'])
def delete_material(material_id):
    db = SessionLocal()
    try:
        LMSService.delete_material(db, material_id)
        db.commit()
        return jsonify({"success": True, "message": "Đã gỡ học liệu!"})
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


# ==========================================
# 2. DASHBOARD & BÀI TẬP HỌC SINH (STUDENT)
# ==========================================

@lms_bp.route('/student/dashboard/summary', methods=['GET'])
def student_dashboard():
    user_id = session.get('user_id') or request.args.get('user_id', 3)
    db = SessionLocal()
    try:
        query_tasks = text("""
            SELECT 
                bt.MaBaiTap,
                bt.TieuDe,
                bt.NoiDung,
                bt.HanNop,
                bt.FileDinhKem,
                bt.LoaiBai,
                ISNULL(bt.MaLoai, 0) AS MaLoai,
                ISNULL(ld.TenLoai, N'Bài tập') AS TenLoaiDiem,
                ISNULL(mh.TenMonHoc, N'Môn học') AS TenMonHoc,
                bl.MaBaiLam,
                bl.DiemSo,
                bl.LoiPhe AS NhanXet,
                bl.NoiDungBaiLam AS NoiDungNop,
                bl.FileDinhKem AS FileNop,
                CONVERT(VARCHAR(16), bl.NgayNop, 120) AS NgayNop
            FROM BaiTap bt
            LEFT JOIN LoaiDiem ld ON bt.MaLoai = ld.MaLoai
            LEFT JOIN PhanCongGiangDay pc ON bt.MaPhanCong = pc.MaPhanCong
            LEFT JOIN MonHoc mh ON pc.MaMonHoc = mh.MaMonHoc
            LEFT JOIN NguoiDung hs ON hs.MaNguoiDung = :uid
            LEFT JOIN BaiLam bl ON (bt.MaBaiTap = bl.MaBaiTap AND bl.MaHocSinh = :uid)
            WHERE (pc.MaLop = hs.MaLop OR bt.MaPhanCong = hs.MaLop)
            ORDER BY bt.MaBaiTap DESC
        """)
        tasks_records = db.execute(query_tasks, {"uid": user_id}).fetchall()

        tasks_list = []
        pending_count = 0
        completed_count = 0

        for t in tasks_records:
            is_submitted = t.MaBaiLam is not None
            if is_submitted:
                completed_count += 1
            else:
                pending_count += 1

            status_str = f"Đã chấm: {t.DiemSo}đ" if t.DiemSo is not None else ("Đã nộp" if is_submitted else "Chưa nộp")

            tasks_list.append({
                "id": t.MaBaiTap,
                "title": f"[{t.TenMonHoc}] {t.TieuDe}",
                "description": t.NoiDung,
                "file_tap": t.FileDinhKem,
                "is_file_tap_img": t.FileDinhKem.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) if t.FileDinhKem else False,
                "subject": t.TenMonHoc,
                "ma_loai": t.MaLoai,
                "ten_loai": t.TenLoaiDiem,
                "icon": "ph-exam" if t.LoaiBai == 'TracNghiem' else "ph-book-open",
                "color": "rose" if t.LoaiBai == 'TracNghiem' else "blue",
                "deadline": t.HanNop.strftime("%d/%m/%Y %H:%M") if t.HanNop else "Không có hạn nộp",
                "deadline_iso": t.HanNop.strftime("%Y-%m-%dT%H:%M:%S") if t.HanNop else None,
                "status": status_str,
                "is_submitted": is_submitted,
                "score": t.DiemSo,
                "comment": t.NhanXet,
                "submitted_content": t.NoiDungNop,
                "submitted_file": t.FileNop,
                "submitted_at": t.NgayNop
            })

        user_info = db.execute(text("""
            SELECT nd.HoTen, l.TenLop, nd.AnhDaiDien 
            FROM NguoiDung nd 
            LEFT JOIN LopHoc l ON nd.MaLop = l.MaLop 
            WHERE nd.MaNguoiDung = :uid
        """), {"uid": user_id}).fetchone()

        full_name = user_info.HoTen if user_info else "Học sinh"
        first_name = full_name.split()[-1] if full_name else "Bạn"

        return jsonify({
            "success": True,
            "data": {
                "user": {
                    "name": full_name,
                    "first_name": first_name,
                    "class_name": user_info.TenLop if user_info else "N/A",
                    "avatar": user_info.AnhDaiDien or "https://api.dicebear.com/7.x/avataaars/svg?seed=student",
                    "current_period": "Tiết 2",
                    "today_alert": "Chào mừng bạn quay lại hệ thống lớp học số!"
                },
                "stats": {
                    "xp": 0,
                    "total_tasks": len(tasks_list),
                    "pending_count": pending_count,
                    "completed_count": completed_count
                },
                "tasks": tasks_list,
                "badges": []
            }
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


# ==========================================
# 3. QUẢN LÝ & GIAO BÀI TẬP (TEACHER ASSIGNMENTS)
# ==========================================

@lms_bp.route('/teacher/assignments/classes', methods=['GET'])
def get_teacher_classes_lms():
    user_id = session.get('user_id') or request.args.get('user_id')
    if not user_id:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    db = SessionLocal()
    try:
        query = text("""
            SELECT 
                pc.MaPhanCong AS id,
                l.MaLop AS class_id,
                l.TenLop AS class_name,
                mh.MaMonHoc AS subject_id,
                mh.TenMonHoc AS subject_name,
                (l.TenLop + ' - ' + mh.TenMonHoc) AS name
            FROM PhanCongGiangDay pc
            JOIN LopHoc l ON pc.MaLop = l.MaLop
            JOIN MonHoc mh ON pc.MaMonHoc = mh.MaMonHoc
            WHERE pc.MaGiaoVien = :uid
        """)
        results = db.execute(query, {"uid": user_id}).fetchall()
        
        if not results:
            fallback_query = text("""
                SELECT l.MaLop AS id, l.MaLop AS class_id, l.TenLop AS class_name, 6 AS subject_id, N'Tin học' AS subject_name, (l.TenLop + N' - Lớp chủ nhiệm') AS name 
                FROM LopHoc l 
                WHERE l.MaGVCN = :uid
            """)
            results = db.execute(fallback_query, {"uid": user_id}).fetchall()

        classes = [dict(r._mapping) for r in results]
        return jsonify({'success': True, 'data': classes})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()

@lms_bp.route('/teacher/assignments/create', methods=['POST'])
def create_assignment_lms():
    user_id = session.get('user_id') or request.form.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'Vui lòng đăng nhập'}), 401

    json_data = request.get_json(silent=True) or {}
    class_id = request.form.get('class_id') or json_data.get('class_id')
    ma_loai = request.form.get('ma_loai') or json_data.get('ma_loai', 0)
    title = request.form.get('title') or json_data.get('title')
    content = request.form.get('content', '') or json_data.get('content', '')
    deadline_str = request.form.get('deadline') or json_data.get('deadline')

    if not class_id or not title:
        return jsonify({'success': False, 'message': 'Thiếu thông tin bắt buộc (Lớp học hoặc Tiêu đề)'}), 400

    try:
        class_id = int(class_id)
        ma_loai = int(ma_loai)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Mã lớp hoặc loại điểm không hợp lệ'}), 400

    deadline = None
    if deadline_str:
        try:
            deadline = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
        except Exception:
            try:
                deadline = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                deadline = None

    file_path_db = None
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename != '':
            file_path_db = save_upload_file(file, folder='assignments')

    db = SessionLocal()
    try:
        check_pc = db.execute(
            text("SELECT MaPhanCong FROM PhanCongGiangDay WHERE MaPhanCong = :id"),
            {"id": class_id}
        ).fetchone()
        
        target_ma_pc = class_id if check_pc else None
        
        if not target_ma_pc:
            find_pc = db.execute(
                text("SELECT MaPhanCong FROM PhanCongGiangDay WHERE MaLop = :lid AND MaGiaoVien = :uid"),
                {"lid": class_id, "uid": user_id}
            ).fetchone()
            target_ma_pc = find_pc[0] if find_pc else class_id

        query = text("""
            INSERT INTO BaiTap (TieuDe, NoiDung, HanNop, MaPhanCong, LoaiBai, MaLoai, FileDinhKem, NgayTao)
            VALUES (:title, :content, :deadline, :cid, 'TuLuan', :maloai, :file_path, GETDATE())
        """)
        db.execute(query, {
            "title": title,
            "content": content,
            "deadline": deadline,
            "cid": target_ma_pc,
            "maloai": ma_loai,
            "file_path": file_path_db
        })
        db.commit()
        return jsonify({'success': True, 'message': 'Đã giao bài tập thành công!'})
    except Exception as e:
        traceback.print_exc()
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()

@lms_bp.route('/teacher/assignments/list', methods=['GET'])
def get_teacher_assignments_list():
    user_id = session.get('user_id') or request.args.get('user_id')
    if not user_id:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    
    db = SessionLocal()
    try:
        query = text("""
            SELECT DISTINCT 
                bt.MaBaiTap, 
                bt.TieuDe, 
                bt.NoiDung,
                bt.HanNop,
                bt.FileDinhKem,
                ISNULL(bt.MaLoai, 0) AS MaLoai,
                ISNULL(ld.TenLoai, N'Tự luyện') AS TenLoaiDiem,
                ISNULL(mh.TenMonHoc, N'Môn học') AS TenMonHoc,
                ISNULL(l.TenLop, N'Toàn khối') AS TenLop,
                pc.MaLop
            FROM BaiTap bt
            LEFT JOIN LoaiDiem ld ON bt.MaLoai = ld.MaLoai
            LEFT JOIN PhanCongGiangDay pc ON bt.MaPhanCong = pc.MaPhanCong
            LEFT JOIN MonHoc mh ON pc.MaMonHoc = mh.MaMonHoc
            LEFT JOIN LopHoc l ON (pc.MaLop = l.MaLop OR bt.MaPhanCong = l.MaLop)
            WHERE pc.MaGiaoVien = :tid OR l.MaGVCN = :tid OR bt.MaPhanCong IN (SELECT MaLop FROM LopHoc WHERE MaGVCN = :tid)
            ORDER BY bt.MaBaiTap DESC
        """)
        results = db.execute(query, {"tid": user_id}).fetchall()
        
        data = []
        for r in results:
            item = dict(r._mapping)
            if item.get('HanNop') and isinstance(item['HanNop'], datetime):
                item['HanNop'] = item['HanNop'].strftime("%Y-%m-%d %H:%M:%S")
            item['NgayTao'] = 'Mới giao'
            data.append(item)

        return jsonify({"success": True, "data": data})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


# ==========================================
# 4. HỌC SINH NỘP BÀI & XEM BÀI NỘP
# ==========================================

@lms_bp.route('/assignment/submit', methods=['POST'])
def submit_assignment_lms():
    student_id = session.get('user_id') or request.form.get('user_id')
    if not student_id:
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    
    assignment_id = request.form.get('assignment_id')
    content = request.form.get('content', '')
    
    if not assignment_id:
        return jsonify({'success': False, 'message': 'Thiếu ID bài tập'}), 400
        
    db = SessionLocal()
    try:
        check_query = text("SELECT MaBaiLam FROM BaiLam WHERE MaBaiTap = :aid AND MaHocSinh = :sid")
        exists = db.execute(check_query, {"aid": assignment_id, "sid": student_id}).fetchone()
        
        file = request.files.get('file')
        file_path = None
        if file and file.filename != '':
            file_path = save_upload_file(file, folder='submissions')
        
        if exists:
            db.execute(text("""
                UPDATE BaiLam 
                SET NoiDungBaiLam = :c, 
                    FileDinhKem = COALESCE(:fp, FileDinhKem), 
                    NgayNop = GETDATE() 
                WHERE MaBaiTap = :aid AND MaHocSinh = :sid
            """), {"c": content, "fp": file_path, "aid": assignment_id, "sid": student_id})
        else:
            db.execute(text("""
                INSERT INTO BaiLam (MaBaiTap, MaHocSinh, NoiDungBaiLam, FileDinhKem, NgayNop) 
                VALUES (:aid, :sid, :c, :fp, GETDATE())
            """), {"aid": assignment_id, "sid": student_id, "c": content, "fp": file_path})
        
        db.commit()
        return jsonify({'success': True, 'message': 'Đã nộp bài thành công'})
    except Exception as e:
        traceback.print_exc()
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()

@lms_bp.route('/teacher/assignments/<int:assignment_id>/submissions', methods=['GET'])
def get_assignment_submissions(assignment_id):
    user_id = session.get('user_id') or request.args.get('user_id')
    if not user_id:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    db = SessionLocal()
    try:
        query = text("""
            SELECT 
                bl.MaBaiLam,
                bl.MaBaiTap,
                bl.MaHocSinh,
                nd.HoTen,
                bl.DiemSo,
                bl.LoiPhe AS NhanXet,
                bl.NoiDungBaiLam AS NoiDungNop,
                bl.FileDinhKem,
                CONVERT(VARCHAR(16), bl.NgayNop, 120) AS NgayNop,
                CASE 
                    WHEN bl.FileDinhKem LIKE '%.png' 
                      OR bl.FileDinhKem LIKE '%.jpg' 
                      OR bl.FileDinhKem LIKE '%.jpeg' 
                      OR bl.FileDinhKem LIKE '%.webp' 
                    THEN bl.FileDinhKem 
                    ELSE NULL 
                END AS HinhAnh
            FROM BaiLam bl
            JOIN NguoiDung nd ON bl.MaHocSinh = nd.MaNguoiDung
            WHERE bl.MaBaiTap = :aid
            ORDER BY bl.NgayNop DESC
        """)
        results = db.execute(query, {"aid": assignment_id}).fetchall()
        return jsonify({"success": True, "data": [dict(r._mapping) for r in results]})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()