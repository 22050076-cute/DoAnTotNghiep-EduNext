from flask import Blueprint, request, jsonify, session
from app.services.class_service import ClassService
from app.config import SessionLocal
from datetime import datetime
from sqlalchemy import text

class_bp = Blueprint('class', __name__)

@class_bp.route('/teacher/attendance', methods=['GET', 'POST'])
@class_bp.route('/teacher/attendance/save', methods=['POST'])
def handle_attendance():
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "Vui lòng đăng nhập"}), 401
            
        user_id = int(user_id) # Đảm bảo là số nguyên

        if request.method == 'GET':
            date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
            class_id_raw = request.args.get('class_id')
            
            class_id = None
            if class_id_raw and class_id_raw not in ['undefined', 'null', '']:
                try:
                    class_id = int(class_id_raw)
                except:
                    class_id = None
            
            if not class_id:
                class_id = ClassService.get_teacher_class_id(db, user_id)
                
            print(f"[Debug Attendance] GET - user_id: {user_id}, class_id: {class_id}, date: {date_str}")
            
            if not class_id:
                print(f"[Debug Attendance] Error: Cannot determine class_id for user_id {user_id}")
                return jsonify({"success": False, "message": "Không xác định được lớp học"}), 400
                
            students = ClassService.get_students_for_attendance(db, class_id, date_str)
            print(f"[Debug Attendance] Found {len(students)} students")
            return jsonify({"success": True, "data": students, "class_id": class_id})
            
        else: # POST
            data = request.json
            print(f"[Debug Attendance] Received POST Data: {data}")
            
            class_id = data.get('class_id')
            date_str = data.get('date')
            attendance_list = data.get('records') or data.get('attendance') or []
            
            # [SAFETY] Nếu thiếu class_id, thử tìm lớp chủ nhiệm của GV
            if not class_id:
                class_id = ClassService.get_teacher_class_id(db, user_id)
                print(f"[Debug Attendance] Auto-filled class_id: {class_id}")

            if not class_id or not date_str:
                print(f"[Debug Attendance] Error: Missing class_id ({class_id}) or date ({date_str})")
                return jsonify({"success": False, "message": f"Thiếu thông tin: class_id={class_id}, date={date_str}"}), 400
                
            ClassService.save_attendance(db, class_id, date_str, attendance_list, user_id)
            return jsonify({"success": True, "message": "Lưu điểm danh thành công"})
            
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@class_bp.route('/teacher/attendance-history', methods=['GET'])
def teacher_attendance_history():
    db = SessionLocal()
    try:
        class_id = request.args.get('class_id')
        date = request.args.get('date')
        history = ClassService.get_attendance_history(db, class_id=class_id, date=date)
        return jsonify({"success": True, "data": history})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@class_bp.route('/parent/attendance-history', methods=['GET'])
def parent_attendance_history():
    db = SessionLocal()
    try:
        parent_id = session.get('user_id')
        # Tìm con của phụ huynh
        child_res = db.execute(text("SELECT MaHocSinhLienKet FROM NguoiDung WHERE MaNguoiDung = :pid"), {"pid": parent_id}).fetchone()
        student_id = child_res[0] if child_res else None
        
        history = ClassService.get_attendance_history(db, student_id=student_id)
        return jsonify({"success": True, "data": history})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@class_bp.route('/student/attendance-history', methods=['GET'])
def student_attendance_history():
    db = SessionLocal()
    try:
        student_id = session.get('user_id')
        history = ClassService.get_attendance_history(db, student_id=student_id)
        return jsonify({"success": True, "data": history})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@class_bp.route('/teacher/leave-requests', methods=['GET'])
def get_leave_requests():
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        class_id = request.args.get('class_id')
        if not class_id:
            class_id = ClassService.get_teacher_class_id(db, user_id)
            
        data = ClassService.get_leave_requests(db, class_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@class_bp.route('/teacher/leave-requests/update', methods=['POST'])
def update_leave_status():
    db = SessionLocal()
    try:
        data = request.json
        request_id = data.get('id')
        status = data.get('status')
        comment = data.get('comment', '')
        teacher_id = session.get('user_id')
        
        ClassService.update_leave_status(db, request_id, status, comment, teacher_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@class_bp.route('/parent/leave-request', methods=['POST', 'GET'])
def handle_parent_leave():
    db = SessionLocal()
    try:
        parent_id = session.get('user_id')
        if request.method == 'POST':
            data = request.json
            reason = data.get('reason')
            date_str = data.get('date')
            ClassService.create_leave_request(db, parent_id, reason, date_str)
            return jsonify({"success": True})
        else:
            data = ClassService.get_parent_leave_history(db, parent_id)
            return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@class_bp.route('/teacher/pending-leaves-count', methods=['GET'])
def get_pending_leaves_count():
    teacher_id = session.get('user_id')
    if not teacher_id: return jsonify({"success": False, "message": "Unauthorized"}), 401
    
    db = SessionLocal()
    try:
        from app.services.class_service import ClassService
        count = ClassService.get_pending_leave_count(db, teacher_id)
        return jsonify({"success": True, "count": count})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

