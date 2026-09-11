from flask import Blueprint, request, jsonify, session
from app.services.social_service import SocialService
from app.config import SessionLocal
import traceback

social_bp = Blueprint('social', __name__)

@social_bp.route('/social/like', methods=['POST'])
def toggle_like():
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "Vui lòng đăng nhập"}), 401
            
        data = request.json
        object_type = data.get('type')
        object_id = data.get('id')
        
        print(f"[DEBUG] Social Like Request: User={user_id}, Type={object_type}, ID={object_id}")
        
        if not object_type or not object_id:
            return jsonify({"success": False, "message": "Thiếu thông tin đối tượng"}), 400
            
        action = SocialService.toggle_like(db, user_id, object_type, object_id)
        return jsonify({"success": True, "action": action})
    except Exception as e:
        traceback.print_exc() # In ra lỗi chi tiết ở terminal của bạn
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@social_bp.route('/social/comment', methods=['POST'])
def add_comment():
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "Vui lòng đăng nhập"}), 401
            
        data = request.json
        object_type = data.get('type')
        object_id = data.get('id')
        content = data.get('content')
        
        SocialService.add_comment(db, user_id, object_type, object_id, content)
        return jsonify({"success": True, "message": "Đã gửi bình luận"})
    except ValueError as ve:
        return jsonify({"success": False, "message": str(ve)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@social_bp.route('/social/interactions/<string:obj_type>/<int:obj_id>', methods=['GET'])
def get_interactions(obj_type, obj_id):
    db = SessionLocal()
    try:
        current_user_id = session.get('user_id')
        data = SocialService.get_interactions(db, obj_type, obj_id, current_user_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()
@social_bp.route('/social/notifications', methods=['GET'])
def get_user_notifications():
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "Vui lòng đăng nhập"}), 401
            
        notifications = SocialService.get_user_notifications(db, user_id)
        return jsonify({"success": True, "data": notifications})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()
@social_bp.route('/social/interactions/feedback/teacher', methods=['GET'])
def get_teacher_feedback():
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "Vui lòng đăng nhập"}), 401
            
        from app.services.communication_service import CommunicationService
        data = CommunicationService.get_teacher_feedbacks(db, user_id)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()
