from flask import Blueprint, request, jsonify, session
from app.services.event_service import EventService
from app.services.lms_service import LMSService
from app.config import SessionLocal

guest_bp = Blueprint('guest', __name__)

@guest_bp.route('/public/events', methods=['GET'])
def get_public_events():
    db = SessionLocal()
    try:
        events = EventService.get_public_events(db)
        return jsonify({"success": True, "data": events})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        db.close()

@guest_bp.route('/public/events/register', methods=['POST'])
def register_event_guest():
    data = request.json
    db = SessionLocal()
    try:
        # Nếu đã đăng nhập thì lấy user_id từ session, nếu không thì lấy từ payload (khách)
        user_id = session.get('user_id')
        data['user_id'] = user_id
        
        success, message = EventService.register_event(db, data)
        return jsonify({"success": success, "message": message})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        db.close()

@guest_bp.route('/public/materials/download/<int:id>', methods=['POST'])
def track_download(id):
    db = SessionLocal()
    try:
        LMSService.increment_download_count(db, id)
        return jsonify({"success": True, "message": "Download tracked"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        db.close()
