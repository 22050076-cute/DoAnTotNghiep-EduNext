from flask import Blueprint, request, jsonify, session
from sqlalchemy import text
from app.services.communication_service import CommunicationService
from app.config import SessionLocal

communication_bp = Blueprint('communication', __name__)

@communication_bp.route('/messages/delete/<int:id>', methods=['DELETE'])
def delete_message(id):
    user_id = session.get('user_id')
    if not user_id: return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401
    
    db = SessionLocal()
    try:
        # Kiểm tra quyền sở hữu tin nhắn
        msg = db.execute(text("SELECT MaNguoiGui FROM TraoDoiChuNhiem WHERE MaTraoDoi = :id"), {"id": id}).fetchone()
        if not msg:
            return jsonify({"success": False, "message": "Không tìm thấy tin nhắn"}), 404
            
        if int(msg.MaNguoiGui) != int(user_id):
            return jsonify({"success": False, "message": "Bạn không có quyền xóa tin nhắn này!"}), 403
            
        db.execute(text("DELETE FROM TraoDoiChuNhiem WHERE MaTraoDoi = :id"), {"id": id})
        db.commit()
        return jsonify({"success": True, "message": "Đã xóa tin nhắn"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@communication_bp.route('/messages/check-signals', methods=['GET'])
def check_signals():
    # Dummy endpoint để dập tắt lỗi 404 từ một số kịch bản cũ hoặc library
    return jsonify({"success": True, "signal": False})

@communication_bp.route('/messages/history', methods=['GET'])
def get_chat_history():
    db = SessionLocal()
    try:
        current_user_id = session.get('user_id')
        if not current_user_id:
            return jsonify({"success": False, "message": "Vui lòng đăng nhập"}), 401
        
        with_user_id = request.args.get('with_user_id')
        if not with_user_id:
            return jsonify({"success": False, "message": "Thiếu ID người nhận"}), 400
            
        history = CommunicationService.get_chat_history(db, current_user_id, with_user_id)
        
        return jsonify({
            "success": True, 
            "data": [dict(r._mapping) for r in history],
            "current_user_id": int(current_user_id)
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@communication_bp.route('/messages/send', methods=['POST'])
def send_message():
    db = SessionLocal()
    try:
        data = request.json
        sender_id = session.get('user_id')
        if not sender_id:
            return jsonify({"success": False, "message": "Vui lòng đăng nhập lại"}), 401
            
        receiver_id = data.get('receiver_id')
        content = data.get('content')
        
        CommunicationService.send_private_message(db, sender_id, receiver_id, content)
        return jsonify({"success": True})
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@communication_bp.route('/parent/chat-contacts', methods=['GET'])
def parent_chat_contacts():
    db = SessionLocal()
    try:
        parent_id = session.get('user_id')
        if not parent_id:
            return jsonify({"success": False, "message": "Vui lòng đăng nhập"}), 401
            
        contacts = CommunicationService.get_parent_chat_contacts(db, parent_id)
        if contacts is None:
            return jsonify({"success": False, "message": "Không tìm thấy thông tin lớp học của con"}), 404
            
        return jsonify({"success": True, "data": contacts})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@communication_bp.route('/teacher/chat-contacts', methods=['GET'])
def teacher_chat_contacts():
    db = SessionLocal()
    try:
        teacher_id = session.get('user_id')
        if not teacher_id:
            return jsonify({"success": False, "message": "Vui lòng đăng nhập"}), 401
            
        contacts = CommunicationService.get_teacher_chat_contacts(db, teacher_id)
        if contacts is None:
            return jsonify({"success": False, "message": "Không tìm thấy thông tin giáo viên"}), 404
            
        return jsonify({"success": True, "data": contacts})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@communication_bp.route('/student/chat-contacts', methods=['GET'])
def student_chat_contacts():
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        role = session.get('vai_tro')
        if not user_id:
            return jsonify({"success": False, "message": "Vui lòng đăng nhập"}), 401
            
        if role == 'Parent':
            contacts = CommunicationService.get_parent_chat_contacts(db, user_id)
        else:
            contacts = CommunicationService.get_student_chat_contacts(db, user_id)
            
        return jsonify({"success": True, "data": contacts})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@communication_bp.route('/teacher/announcements', methods=['GET', 'POST'])
def handle_announcements():
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "Vui lòng đăng nhập"}), 401
            
        if request.method == 'GET':
            class_id = request.args.get('class_id')
            if not class_id:
                from app.services.class_service import ClassService
                class_id = ClassService.get_teacher_class_id(db, user_id)
                
            data = CommunicationService.get_announcements(db, class_id, user_id)
            return jsonify({"success": True, "data": data})
        else:
            # --- [GOLD STANDARD UPGRADE: RBAC] ---
            # Chỉ Giáo viên mới được phép đăng thông báo
            user_role = session.get('vai_tro')
            if user_role != 'Teacher':
                return jsonify({"success": False, "message": "Bạn không có quyền đăng thông báo"}), 403
                
            # Hỗ trợ cả JSON và Form Data (cho upload ảnh)
            if request.is_json:
                data = request.json
            else:
                data = request.form.to_dict()
                
            # Xử lý file ảnh nếu có
            if 'file' in request.files:
                from app.utils.file_utils import save_upload_file
                file = request.files['file']
                file_url = save_upload_file(file, folder='announcements')
                if file_url:
                    data['hinh_anh'] = file_url

            CommunicationService.create_announcement(db, data, user_id)
            return jsonify({"success": True, "message": "Gửi thông báo thành công"})
    except ValueError as ve:
        # Lỗi nghiệp vụ (Vd: thiếu class_id, nội dung trống)
        print(f"\033[91m[BUSINESS ERROR]\033[0m {str(ve)}")
        return jsonify({"success": False, "message": str(ve)}), 400
    except Exception as e:
        # Lỗi hệ thống nghiêm trọng
        import traceback
        print("\033[91m[SYSTEM CRITICAL ERROR]\033[0m")
        traceback.print_exc()
        return jsonify({"success": False, "message": "Lỗi hệ thống khi xử lý thông báo"}), 500
    finally:
        db.close()

@communication_bp.route('/student/announcements', methods=['GET'])
def get_student_announcements():
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "Vui lòng đăng nhập"}), 401
            
        from app.services.class_service import ClassService
        user_role = session.get('vai_tro')
        class_id = None
        
        if user_role == 'Parent':
            # Phụ huynh: Lấy MaLop của con liên kết
            try:
                child_query = text("SELECT MaLop FROM NguoiDung WHERE MaNguoiDung = (SELECT MaHocSinhLienKet FROM NguoiDung WHERE MaNguoiDung = :pid)")
                child_res = db.execute(child_query, {"pid": user_id}).fetchone()
                class_id = child_res[0] if child_res else 0
            except:
                class_id = 0
        elif user_role == 'Student':
            # Học sinh: Lấy trực tiếp MaLop từ tài khoản của mình
            user_query = text("SELECT MaLop FROM NguoiDung WHERE MaNguoiDung = :uid")
            user_res = db.execute(user_query, {"uid": user_id}).fetchone()
            class_id = user_res[0] if user_res else 0
        else:
            # Giáo viên hoặc Vai trò khác: Lấy lớp quản lý
            class_id = ClassService.get_teacher_class_id(db, user_id)
        
        # Lấy thông báo dựa trên class_id đã xác định đúng
        data = CommunicationService.get_announcements(db, class_id, user_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": "Lỗi khi tải thông báo"}), 500
    finally:
        db.close()
@communication_bp.route('/messages/unread-count', methods=['GET'])
def get_unread_count():
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": True, "count": 0})
            
        count = CommunicationService.get_total_unread_count(db, user_id)
        return jsonify({"success": True, "count": count})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()
@communication_bp.route('/teacher/announcements/delete/<int:id>', methods=['DELETE'])
def delete_announcement(id):
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401
        
        success, message = CommunicationService.delete_announcement(db, id, user_id)
        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"success": False, "message": message}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@communication_bp.route('/teacher/announcements/update/<int:id>', methods=['PUT'])
def update_announcement(id):
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401
        
        data = request.json
        success, message = CommunicationService.update_announcement(db, id, data, user_id)
        if success:
            return jsonify({"success": True, "message": message})
        else:
            return jsonify({"success": False, "message": message}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()
