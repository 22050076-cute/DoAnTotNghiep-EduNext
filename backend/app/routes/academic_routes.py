from flask import Blueprint, request, jsonify, session
from app.services.academic_service import AcademicService
from app.services.class_service import ClassService
from app.config import SessionLocal

academic_bp = Blueprint('academic', __name__)

@academic_bp.route('/subjects', methods=['GET'])
def get_subjects():
    db = SessionLocal()
    try:
        data = AcademicService.get_subjects(db)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@academic_bp.route('/teacher/schedule', methods=['GET'])
def get_teacher_schedule():
    db = SessionLocal()
    try:
        class_id = request.args.get('class_id')
        if not class_id:
            user_id = session.get('user_id')
            class_id = ClassService.get_teacher_class_id(db, user_id)
            
        if not class_id:
            return jsonify({"success": False, "message": "Không tìm thấy thông tin lớp học"}), 404
            
        data = AcademicService.get_teacher_schedule(db, class_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@academic_bp.route('/teacher/schedule/update', methods=['POST'])
def update_teacher_schedule():
    db = SessionLocal()
    try:
        data = request.json
        class_id = data.get('class_id')
        schedule_data = data.get('schedule')
        teacher_id = session.get('user_id')
        AcademicService.update_schedule(db, class_id, schedule_data, teacher_id)
        return jsonify({"success": True, "message": "Cập nhật thời khóa biểu thành công!"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@academic_bp.route('/teacher/grades', methods=['GET'])
def get_teacher_gradebook():
    db = SessionLocal()
    try:
        class_id = request.args.get('class_id')
        subject_id = request.args.get('subject_id', 1, type=int)
        semester_id = request.args.get('semester_id', 1, type=int)
        
        if not class_id:
            user_id = session.get('user_id')
            class_id = ClassService.get_teacher_class_id(db, user_id)
            
        data = AcademicService.get_gradebook(db, class_id, subject_id, semester_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@academic_bp.route('/teacher/grades-classes', methods=['GET'])
def get_grades_classes():
    db = SessionLocal()
    try:
        teacher_id = request.args.get("teacher_id") or session.get('user_id')
        data = AcademicService.get_grades_classes(db, teacher_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@academic_bp.route('/parent/student/schedule', methods=['GET'])
def get_parent_student_schedule():
    db = SessionLocal()
    try:
        parent_id = session.get('user_id')
        if not parent_id:
            return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401
            
        data = AcademicService.get_student_schedule_by_parent(db, parent_id)
        if data is None:
            return jsonify({"success": False, "message": "Không tìm thấy dữ liệu học sinh liên kết"}), 404
            
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@academic_bp.route('/parent/student/attendance', methods=['GET'])
def get_student_attendance_parent():
    parent_id = session.get('user_id')
    if not parent_id: 
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    
    db = SessionLocal()
    try:
        data = AcademicService.get_student_attendance_by_parent(db, parent_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@academic_bp.route('/student/attendance', methods=['GET'])
def get_student_attendance():
    student_id = session.get('user_id')
    if not student_id: 
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    
    db = SessionLocal()
    try:
        data = AcademicService.get_student_attendance(db, student_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()