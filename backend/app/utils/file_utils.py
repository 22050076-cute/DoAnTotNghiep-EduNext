import os
import uuid
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_upload_file(file, folder='general'):
    """
    Lưu file upload vào thư mục frontend/static/uploads/{folder}
    để Flask có thể serve qua URL /static/uploads/...
    """
    if not file or not allowed_file(file.filename):
        return None
    
    # Tạo tên file duy nhất
    ext = file.filename.rsplit('.', 1)[1].lower()
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    
    # Lấy đường dẫn thư mục backend/
    # file_utils.py đang ở backend/app/utils/file_utils.py
    current_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))
    
    # Thư mục frontend/static nằm cùng cấp với backend/
    # Project Root -> backend/
    #             -> frontend/
    project_root = os.path.abspath(os.path.join(backend_dir, '..'))
    target_dir = os.path.join(project_root, 'frontend', 'static', 'uploads', folder)
    
    # Log đường dẫn để debug nếu cần
    print(f"[Debug] Saving file to: {target_dir}")
    
    if not os.path.exists(target_dir):
        os.makedirs(target_dir, exist_ok=True)
    
    file_path = os.path.join(target_dir, unique_filename)
    file.save(file_path)
    
    # Trả về URL path (dùng dấu / cho web)
    return f"/static/uploads/{folder}/{unique_filename}"
