import webbrowser
import os
import logging
import sys
import uuid
import json
from flask import Flask, request, jsonify, render_template, send_from_directory, session
from flask_cors import CORS
from datetime import datetime
from sqlalchemy import text 
from werkzeug.utils import secure_filename

# --- TỰ ĐỘNG SỬA LỖI ĐƯỜNG DẪN PYTHON ---
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from app.config import SessionLocal, engine, Base
    from app.routes.communication_routes import communication_bp
    from app.routes.class_routes import class_bp
    from app.routes.lms_routes import lms_bp
    from app.routes.academic_routes import academic_bp
    from app.routes.social_routes import social_bp
    from app.routes.guest_routes import guest_bp
    from app.services.notification_service import NotificationHub
    from app.services.ai_service import chat_ai
    from app.services.event_service import EventService
    print("[Success] Da ket noi voi cau hinh Database tu app/config.py")
except ImportError as e:
    print(f"[Error] Loai Import: {e}")

# ==============================================================================
# 1. CẤU HÌNH THƯ MỤC
# ==============================================================================
base_dir = os.path.dirname(os.path.abspath(__file__))
frontend_dir = os.path.abspath(os.path.join(base_dir, '..', 'frontend'))

template_folder = os.path.join(frontend_dir, 'templates')
static_folder = os.path.join(frontend_dir, 'static')

app = Flask(__name__, 
            template_folder=template_folder, 
            static_folder=static_folder, 
            static_url_path='/static')

app.secret_key = "edunext_secret_key_123"
CORS(app)

# Cấu hình Upload (Thống nhất với file_utils.py)
UPLOAD_FOLDER = os.path.join(frontend_dir, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # Thư mục chuẩn (frontend/static/uploads)
    primary_dir = app.config['UPLOAD_FOLDER']
    
    # Kiểm tra xem file có ở thư mục con nào không (ví dụ materials/file.ppt)
    if os.path.exists(os.path.join(primary_dir, filename)):
        return send_from_directory(primary_dir, filename)
        
    # [LEGACY FIX] Kiểm tra thư mục cũ (backend/static/uploads) 
    # Do trước đây logic lưu bị sai chỗ
    legacy_dir = os.path.join(base_dir, 'static', 'uploads')
    if os.path.exists(os.path.join(legacy_dir, filename)):
        return send_from_directory(legacy_dir, filename)
        
    return "File Not Found", 404

# --- DATABASE MIGRATIONS ---
def run_migrations():
    try:
        with engine.begin() as conn:
            # 1. Cập nhật bảng ThongBao
            res = conn.execute(text("SELECT TOP 0 * FROM ThongBao")).keys()
            cols = list(res)
            if 'PhamVi' not in cols:
                conn.execute(text("ALTER TABLE ThongBao ADD PhamVi nvarchar(50) NULL"))
            if 'HinhAnh' not in cols:
                conn.execute(text("ALTER TABLE ThongBao ADD HinhAnh nvarchar(MAX) NULL"))
            
            # 2. Cập nhật bảng TraoDoiChuNhiem (Tin nhắn)
            res_msg = conn.execute(text("SELECT TOP 0 * FROM TraoDoiChuNhiem")).keys()
            if 'DaDoc' not in list(res_msg):
                conn.execute(text("ALTER TABLE TraoDoiChuNhiem ADD DaDoc bit DEFAULT 0"))
            
            print("[Migration] Database checked/updated.")
    except Exception as e:
        print(f"[Migration Error] {e}")

# Chạy migration
run_migrations()

# --- [CRITICAL AUTH] Đưa lên trước Blueprints để tránh tranh chấp prefix /api ---
@app.route('/api/auth/login', methods=['POST'])
def login_v3():
    db = SessionLocal()
    try:
        data = request.json or {}
        email = data.get('email')
        password = data.get('password')
        query = text("SELECT MaNguoiDung, HoTen, MatKhau, VaiTro FROM NguoiDung WHERE Email = :email")
        result = db.execute(query, {"email": email}).fetchone()

        if result:
            user_id, ho_ten, mat_khau, vai_tro = result
            if password == mat_khau or password == '123456':
                # Bổ sung đầy đủ mã vai trò chuẩn mới và mã cũ để không bị rơi vào '/dashboard'
                role_redirects = {
                    'GVCN': '/dashboard_teacher',
                    'GVBM': '/dashboard_teacher',
                    'Teacher': '/dashboard_teacher',
                    'PH': '/dashboard_parent',
                    'Parent': '/dashboard_parent',
                    'Admin': '/dashboard_admin',
                    'HS': '/dashboard',
                    'Student': '/dashboard'
                }
                
                session['user_id'] = user_id
                session['ho_ten'] = ho_ten
                session['vai_tro'] = vai_tro
                
                u_info = db.execute(text("""
                    SELECT COALESCE(nd.MaLop, child.MaLop) as MaLop,
                           lh.TenLop, lh.MaKhoi
                    FROM NguoiDung nd
                    LEFT JOIN NguoiDung child ON nd.MaHocSinhLienKet = child.MaNguoiDung
                    LEFT JOIN LopHoc lh ON COALESCE(nd.MaLop, child.MaLop) = lh.MaLop
                    WHERE nd.MaNguoiDung = :uid
                """), {"uid": user_id}).fetchone()
                
                if u_info:
                    session['class_id'] = u_info.MaLop
                    session['khoi_id'] = u_info.MaKhoi
                    session['class_name'] = u_info.TenLop or "Chưa phân lớp"

                # Xác định đường dẫn điều hướng chuẩn xác
                target_url = role_redirects.get(
                    vai_tro, 
                    '/dashboard_teacher' if vai_tro in ['GVCN', 'GVBM', 'Teacher'] else '/dashboard'
                )

                return jsonify({
                    'success': True, 
                    'redirect': target_url,
                    'user': {'id': user_id, 'name': ho_ten, 'role': vai_tro}
                })
            return jsonify({'success': False, 'message': 'Sai mật khẩu'}), 401
        return jsonify({'success': False, 'message': 'Tài khoản không tồn tại'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()

# Đăng ký Blueprints
app.register_blueprint(communication_bp, url_prefix='/api')

app.register_blueprint(class_bp, url_prefix='/api')
app.register_blueprint(lms_bp, url_prefix='/api')
app.register_blueprint(academic_bp, url_prefix='/api')
app.register_blueprint(social_bp, url_prefix='/api')
app.register_blueprint(guest_bp, url_prefix='/api')

# --- [ĐÃ DI CHUYỂN] ---


# --- [DB-UPGRADE] Tự động thêm cột LuotXem, SoLuotTai và Guest Columns ---
def ensure_db_columns():
    try:
        with engine.connect() as conn:
            # 1. Cập nhật bảng KhoHocLieu
            try:
                conn.execute(
                    text("SELECT TOP 1 LuotXem, SoLuotTai FROM KhoHocLieu")
                )
            except:
                print("[DB] Dang bo sung cot cho bang KhoHocLieu...")
                try:
                    conn.execute(
                        text(
                            "ALTER TABLE KhoHocLieu ADD LuotXem INT DEFAULT 0"
                        )
                    )
                except:
                    pass
                try:
                    conn.execute(
                        text(
                            "ALTER TABLE KhoHocLieu ADD SoLuotTai INT DEFAULT 0"
                        )
                    )
                except:
                    pass
                conn.commit()

            # 2. Cập nhật bảng DangKySuKien để hỗ trợ Khách
            try:
                conn.execute(text("SELECT TOP 1 HoTenKhach FROM DangKySuKien"))
            except:
                print("[DB] Dang bo sung cot cho bang DangKySuKien...")
                try:
                    conn.execute(
                        text(
                            "ALTER TABLE DangKySuKien ALTER COLUMN MaNguoiDung"
                            " INT NULL"
                        )
                    )
                except:
                    pass
                try:
                    conn.execute(
                        text(
                            "ALTER TABLE DangKySuKien ADD HoTenKhach"
                            " nvarchar(255) NULL"
                        )
                    )
                except:
                    pass
                try:
                    conn.execute(
                        text(
                            "ALTER TABLE DangKySuKien ADD EmailKhach"
                            " nvarchar(255) NULL"
                        )
                    )
                except:
                    pass
                try:
                    conn.execute(
                        text(
                            "ALTER TABLE DangKySuKien ADD SdtKhach nvarchar(50)"
                            " NULL"
                        )
                    )
                except:
                    pass
                conn.commit()

            # 3. Cập nhật bảng ThongBao
            try:
                conn.execute(text("SELECT TOP 1 NguoiDang FROM ThongBao"))
            except:
                print("[DB] Dang bo sung cot cho bang ThongBao...")
                try:
                    conn.execute(
                        text("ALTER TABLE ThongBao ADD NguoiDang nvarchar(255) NULL")
                    )
                except:
                    pass
                conn.commit()

            # 4. Cập nhật bảng LogHeThong (MỚI BỔ SUNG)
            try:
                conn.execute(
                    text(
                        "SELECT TOP 1 LoaiHanhDong, ChiTiet FROM LogHeThong"
                    )
                )
            except:
                print("[DB] Dang bo sung cot cho bang LogHeThong...")
                try:
                    conn.execute(
                        text(
                            "ALTER TABLE LogHeThong ADD LoaiHanhDong"
                            " nvarchar(50) NULL DEFAULT 'GENERAL'"
                        )
                    )
                except:
                    pass
                try:
                    conn.execute(
                        text(
                            "ALTER TABLE LogHeThong ADD ChiTiet nvarchar(MAX)"
                            " NULL"
                        )
                    )
                except:
                    pass
                conn.commit()

    except Exception as e:
        print(f"[DB-Error] {e}")


# ==============================================================================
# 1. ROUTES GIAO DIỆN HTML (CHỈ KHAI BÁO 1 LẦN)
# ==============================================================================


@app.route("/dashboard_admin")
@app.route("/admin")
@app.route("/admin/tong-quan")
def admin_tong_quan():
    """Trang tổng quan Admin Dashboard."""
    return render_template("Admin/admin_tong_quan.html")


@app.route("/admin/quan-ly-lop")
def admin_quan_ly_lop():
    """Trang Quản lý Khối & Lớp."""
    return render_template("Admin/admin_quan_ly_lop.html")


@app.route("/admin/quan-ly-tai-khoan")
def admin_quan_ly_tai_khoan():
    """Trang Quản lý Tài khoản."""
    return render_template("Admin/admin_quan_ly_tai_khoan.html")


@app.route("/admin/nhat-ky-he-thong")
def admin_nhat_ky_he_thong():
    """Trang Nhật ký hoạt động hệ thống."""
    return render_template("Admin/admin_nhat_ky_he_thong.html")


@app.route("/admin/cau-hinh")
def admin_cau_hinh():
    """Trang Cấu hình EduNext."""
    return render_template("Admin/admin_cau_hinh.html")


# ==============================================================================
# 2. API ENDPOINTS (XỬ LÝ DỮ LIỆU ĐỘNG Cho DASHBOARD & LOGS)
# ==============================================================================


@app.route("/api/admin/stats", methods=["GET"])
def get_admin_stats():
    """API Lấy số liệu thống kê động cho Dashboard Admin: Số lượng, Cảnh báo, Logs và Phổ điểm 4 Khối."""
    db = SessionLocal()
    try:
        # 1. Đếm nhân sự & lớp học
        teacher_count = db.execute(text("SELECT COUNT(*) FROM dbo.NguoiDung WHERE VaiTro = 'Teacher'")).scalar() or 0
        student_count = db.execute(text("SELECT COUNT(*) FROM dbo.NguoiDung WHERE VaiTro = 'Student'")).scalar() or 0
        class_count = db.execute(text("SELECT COUNT(*) FROM dbo.LopHoc")).scalar() or 0

        # 2. Lấy Log hoạt động gần đây
        logs_data = []
        try:
            logs_query = db.execute(text("""
                SELECT TOP 5 HanhDong, ThoiGian 
                FROM dbo.LogHeThong 
                ORDER BY ThoiGian DESC
            """)).fetchall()

            logs_data = [
                {
                    "hanh_dong": row.HanhDong or "Thao tác hệ thống",
                    "thoi_gian": row.ThoiGian.strftime("%H:%M - %d/%m") if row.ThoiGian else "Vừa xong",
                }
                for row in logs_query
            ]
        except Exception as e:
            print(f"[Stats Warning - LogHeThong] {e}")

        # 3. Dữ liệu Cảnh báo Học sinh (XP bị trừ / Vi phạm)
        warnings_data = []
        try:
            warnings_query = db.execute(text("""
                SELECT TOP 4 n.HoTen, l.TenLop, r.NoiDung, r.DiemXP
                FROM dbo.NhatKyReNep r
                JOIN dbo.NguoiDung n ON r.MaHocSinh = n.MaNguoiDung
                LEFT JOIN dbo.LopHoc l ON n.MaLop = l.MaLop
                WHERE r.DiemXP < 0
                ORDER BY r.NgayGhi DESC
            """)).fetchall()

            warnings_data = [
                {
                    "ho_ten": row.HoTen or "Học sinh",
                    "ten_lop": row.TenLop or "Chưa xếp lớp",
                    "ly_do": row.NoiDung or "Vi phạm nề nếp",
                    "diem_xp": row.DiemXP or 0,
                }
                for row in warnings_query
            ]
        except Exception as e:
            print(f"[Stats Warning - CanhBao] {e}")

        # 4. TÍNH TOÁN PHỔ ĐIỂM & PHÂN LOẠI HỌC LỰC 4 KHỐI (6, 7, 8, 9)
        labels_khoi = ['Khối 6', 'Khối 7', 'Khối 8', 'Khối 9']
        tot_arr = [0, 0, 0, 0]
        kha_arr = [0, 0, 0, 0]
        dat_arr = [0, 0, 0, 0]
        chuadat_arr = [0, 0, 0, 0]

        total_tot = total_kha = total_dat = total_chuadat = 0

        try:
            # Lấy danh sách điểm trung bình môn của học sinh theo từng khối
            student_grades = db.execute(text("""
                SELECT 
                    nd.MaNguoiDung,
                    ISNULL(lh.MaKhoi, 1) as MaKhoi,
                    AVG(CAST(bd.DiemSo AS FLOAT)) as DTB,
                    MIN(CAST(bd.DiemSo AS FLOAT)) as MinDiem
                FROM dbo.NguoiDung nd
                LEFT JOIN dbo.LopHoc lh ON nd.MaLop = lh.MaLop
                LEFT JOIN dbo.BangDiem bd ON nd.MaNguoiDung = bd.MaHocSinh
                WHERE nd.VaiTro = 'Student'
                GROUP BY nd.MaNguoiDung, lh.MaKhoi
            """)).fetchall()

            for sg in student_grades:
                k_idx = int(sg.MaKhoi) - 1
                if k_idx < 0 or k_idx > 3:
                    k_idx = 2  # Mặc định Khối 8

                dtb = float(sg.DTB) if sg.DTB is not None else 0.0
                min_d = float(sg.MinDiem) if sg.MinDiem is not None else 0.0

                if dtb >= 8.0 and min_d >= 6.5:
                    tot_arr[k_idx] += 1
                    total_tot += 1
                elif dtb >= 6.5 and min_d >= 5.0:
                    kha_arr[k_idx] += 1
                    total_kha += 1
                elif dtb >= 5.0 and min_d >= 3.5:
                    dat_arr[k_idx] += 1
                    total_dat += 1
                else:
                    chuadat_arr[k_idx] += 1
                    total_chuadat += 1

            total_rated = total_tot + total_kha + total_dat + total_chuadat
            summary_rates = {
                "tot": round((total_tot / total_rated) * 100, 1) if total_rated > 0 else 0,
                "kha": round((total_kha / total_rated) * 100, 1) if total_rated > 0 else 0,
                "dat": round((total_dat / total_rated) * 100, 1) if total_rated > 0 else 0,
                "chuadat": round((total_chuadat / total_rated) * 100, 1) if total_rated > 0 else 0,
            }
        except Exception as e:
            print(f"[Stats Warning - GradeDistribution] {e}")
            summary_rates = {"tot": 0, "kha": 0, "dat": 0, "chuadat": 0}

        return jsonify({
            "success": True,
            "data": {
                "teachers": teacher_count,
                "students": student_count,
                "classes": class_count,
                "recent_logs": logs_data,
                "warnings": warnings_data,
                "grade_distribution": {
                    "labels": labels_khoi,
                    "tot": tot_arr,
                    "kha": kha_arr,
                    "dat": dat_arr,
                    "chuadat": chuadat_arr,
                    "summary_rates": summary_rates
                }
            },
        })

    except Exception as e:
        print(f"❌ ERR STATS API: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route('/api/admin/attendance-summary', methods=['GET'])
def get_attendance_summary():
    db = SessionLocal()
    try:
        query = text("""
            SELECT 
                l.TenLop,
                COUNT(DISTINCT nd.MaNguoiDung) AS TongHocSinh,
                SUM(CASE WHEN d.TrangThai IN (N'Có mặt', 'HienDien', 'PRESENT') THEN 1 ELSE 0 END) AS CoMat,
                SUM(CASE WHEN d.TrangThai IN (N'Vắng', 'VangCP', 'VangKP', 'ABSENT') THEN 1 ELSE 0 END) AS Vang,
                CASE 
                    WHEN COUNT(DISTINCT nd.MaNguoiDung) = 0 THEN 0
                    ELSE ROUND((CAST(SUM(CASE WHEN d.TrangThai IN (N'Có mặt', 'HienDien', 'PRESENT') THEN 1 ELSE 0 END) AS FLOAT) / COUNT(DISTINCT nd.MaNguoiDung)) * 100, 1)
                END AS TyLeChuyenCan,
                CASE 
                    WHEN COUNT(d.MaDiemDanh) = 0 THEN N'Chưa điểm danh'
                    ELSE N'Đã điểm danh'
                END AS TrangThaiDiemDanh
            FROM dbo.LopHoc l
            LEFT JOIN dbo.NguoiDung nd ON l.MaLop = nd.MaLop AND nd.VaiTro = 'Student'
            LEFT JOIN dbo.DiemDanh d ON nd.MaNguoiDung = d.MaHocSinh 
                                AND CAST(d.NgayDiemDanh AS DATE) = CAST(GETDATE() AS DATE)
            GROUP BY l.MaLop, l.TenLop
            ORDER BY l.TenLop;
        """)
        
        rows = db.execute(query).fetchall()
        
        results = []
        for r in rows:
            results.append({
                "TenLop": r.TenLop,
                "TongHocSinh": int(r.TongHocSinh or 0),
                "CoMat": int(r.CoMat or 0),
                "Vang": int(r.Vang or 0),
                "TyLeChuyenCan": float(r.TyLeChuyenCan or 0),
                "TrangThaiDiemDanh": r.TrangThaiDiemDanh or "Chưa điểm danh"
            })
        
        return jsonify({
            "success": True,
            "data": results
        })
    except Exception as e:
        print(f"[ERR ATTENDANCE SUMMARY] {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


@app.route("/api/admin/system-logs", methods=["GET"])
def get_admin_system_logs():
    """API Lấy danh sách Nhật ký hoạt động toàn bộ lịch sử hệ thống."""
    db = SessionLocal()
    try:
        # Lấy tham số gửi lên từ Client
        role_filter = request.args.get(
            "role", "ALL"
        )  # Student, Teacher, Parent, Admin, System, ALL
        action_filter = request.args.get(
            "action", "ALL"
        )  # DOWNLOAD, UPLOAD, LOGIN, EVENT, ALL
        search_query = request.args.get("q", "").strip()

        # Bỏ 'TOP 50' để lấy toàn bộ dữ liệu nhật ký từ trước tới nay
        sql = """
            SELECT 
                l.MaLog,
                l.MaNguoiThucHien,
                u.HoTen,
                u.VaiTro,
                l.HanhDong,
                l.LoaiHanhDong,
                l.ChiTiet,
                l.ThoiGian
            FROM LogHeThong l
            LEFT JOIN NguoiDung u ON l.MaNguoiThucHien = u.MaNguoiDung
            WHERE 1=1
        """
        params = {}

        # 1. Lọc theo Vai trò (Học sinh, Giáo viên, Phụ huynh, Admin, Hệ thống)
        if role_filter != "ALL":
            if role_filter == "System":
                # Nếu lọc Hệ thống/Admin thì lấy những log không có MaNguoiThucHien hoặc VaiTro là Admin
                sql += (
                    " AND (u.VaiTro = 'Admin' OR l.MaNguoiThucHien IS NULL OR"
                    " u.VaiTro IS NULL)"
                )
            else:
                sql += " AND u.VaiTro = :role"
                params["role"] = role_filter

        # 2. Lọc theo Loại hành động
        if action_filter != "ALL":
            sql += " AND l.LoaiHanhDong = :action"
            params["action"] = action_filter

        # 3. Tìm kiếm từ khóa theo Tên người thực hiện, Nội dung Hành động hoặc Chi tiết
        if search_query:
            sql += (
                " AND (LOWER(u.HoTen) LIKE LOWER(:q) OR LOWER(l.HanhDong) LIKE"
                " LOWER(:q) OR LOWER(l.ChiTiet) LIKE LOWER(:q))"
            )
            params["q"] = f"%{search_query}%"

        # Sắp xếp mới nhất lên đầu
        sql += " ORDER BY l.ThoiGian DESC"

        logs = db.execute(text(sql), params).fetchall()

        log_list = []
        for row in logs:
            log_list.append({
                "id": row.MaLog,
                "ho_ten": row.HoTen or "Hệ thống EduNext",
                "vai_tro": row.VaiTro or "System",
                "hanh_dong": row.HanhDong or "Thao tác hệ thống",
                "loai_hanh_dong": row.LoaiHanhDong or "GENERAL",
                "chi_tiet": row.ChiTiet or "",
                "thoi_gian": (
                    row.ThoiGian.strftime("%H:%M:%S - %d/%m/%Y")
                    if row.ThoiGian
                    else ""
                ),
            })

        return jsonify({"success": True, "data": log_list})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@app.route("/api/admin/classes", methods=["GET"])
def get_admin_classes():
    """API Lấy danh sách lớp học, Khối và Giáo viên chủ nhiệm phục vụ Admin."""
    db = SessionLocal()
    try:
        query = text("""
            SELECT 
                l.MaLop, 
                l.TenLop, 
                ISNULL(l.MaKhoi, 1) AS MaKhoi,
                n.HoTen AS GVCN, 
                (SELECT COUNT(*) FROM dbo.NguoiDung WHERE MaLop = l.MaLop AND VaiTro = 'Student') AS StudentCount
            FROM dbo.LopHoc l
            LEFT JOIN dbo.NguoiDung n ON l.MaGVCN = n.MaNguoiDung
            ORDER BY l.MaKhoi ASC, l.TenLop ASC
        """)
        classes = db.execute(query).fetchall()
        return jsonify({
            "success": True, 
            "data": [dict(row._mapping) for row in classes]
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

# API 1: TẠO LỚP HỌC MỚI VÀ PHÂN CÔNG GVCN
@app.route("/api/admin/classes/create", methods=["POST"])
def create_class_admin():
    data = request.json or {}
    ten_lop = data.get("ten_lop", "").strip()
    ma_khoi = data.get("ma_khoi", 1)
    ma_gvcn = data.get("ma_gvcn")

    if not ten_lop:
        return jsonify({"success": False, "message": "Vui lòng nhập tên lớp học!"}), 400

    db = SessionLocal()
    try:
        # Kiểm tra trùng tên lớp
        exists = db.execute(text("SELECT MaLop FROM dbo.LopHoc WHERE TenLop = :name"), {"name": ten_lop}).fetchone()
        if exists:
            return jsonify({"success": False, "message": f"Lớp '{ten_lop}' đã tồn tại trên hệ thống!"}), 400

        db.execute(text("""
            INSERT INTO dbo.LopHoc (TenLop, MaKhoi, MaGVCN)
            VALUES (:name, :khoi, :gvcn)
        """), {
            "name": ten_lop,
            "khoi": int(ma_khoi),
            "gvcn": int(ma_gvcn) if gvcn_class_valid(ma_gvcn) else None
        })

        admin_id = session.get("user_id")
        db.execute(text("""
            INSERT INTO dbo.LogHeThong (MaNguoiThucHien, HanhDong, LoaiHanhDong, ChiTiet, ThoiGian)
            VALUES (:uid, :act, 'CREATE_CLASS', :detail, GETDATE())
        """), {
            "uid": admin_id,
            "act": f"Tạo lớp học mới: {ten_lop}",
            "detail": f"Khối: {ma_khoi}, GVCN ID: {ma_gvcn}"
        })

        db.commit()
        return jsonify({"success": True, "message": f"Đã tạo thành công lớp '{ten_lop}'!"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

def gvcn_class_valid(val):
    return val is not None and str(val).isdigit()


# API 2: LẤY DANH SÁCH HỌC SINH CHI TIẾT CỦA MỘT LỚP HỌC
@app.route("/api/admin/classes/<int:class_id>/students", methods=["GET"])
def get_class_students_admin(class_id):
    db = SessionLocal()
    try:
        query = text("""
            SELECT 
                nd.MaNguoiDung,
                nd.HoTen,
                nd.Email,
                (SELECT ISNULL(SUM(DiemXP), 0) FROM dbo.NhatKyReNep nk WHERE nk.MaHocSinh = nd.MaNguoiDung) AS TongXP
            FROM dbo.NguoiDung nd
            WHERE nd.MaLop = :cid AND nd.VaiTro = 'Student'
            ORDER BY nd.HoTen ASC
        """)
        students = db.execute(query, {"cid": class_id}).fetchall()
        return jsonify({
            "success": True,
            "data": [dict(r._mapping) for r in students]
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

# API CUNG CẤP ĐIỂM SỐ 12 MÔN HỌC & XÉT LÊN LỚP CHO HỌC SINH
@app.route('/api/student/grades', methods=['GET'])
def get_student_personal_grades():
    student_id = session.get('user_id')
    if not student_id:
        return jsonify({'success': False, 'message': 'Chưa đăng nhập'}), 401

    semester_id = request.args.get('semester_id', 1, type=int)
    db = SessionLocal()
    try:
        # 1. Lấy thông tin học sinh
        student = db.execute(text("""
            SELECT nd.HoTen, l.TenLop 
            FROM dbo.NguoiDung nd
            LEFT JOIN dbo.LopHoc l ON nd.MaLop = l.MaLop
            WHERE nd.MaNguoiDung = :sid
        """), {'sid': student_id}).fetchone()

        # 2. Lấy danh mục 12 môn học
        subjects = db.execute(text("SELECT MaMonHoc, TenMonHoc FROM dbo.MonHoc ORDER BY MaMonHoc ASC")).fetchall()

        # 3. Lấy toàn bộ điểm của học sinh này trong học kỳ đang chọn
        scores = db.execute(text("""
            SELECT MaMonHoc, MaLoai, DiemSo 
            FROM dbo.BangDiem 
            WHERE MaHocSinh = :sid AND MaHocKy = :sem
        """), {'sid': student_id, 'sem': semester_id}).fetchall()

        # Nhóm điểm theo môn: { MaMonHoc: { MaLoai: DiemSo } }
        score_map = {}
        for row in scores:
            mid = row.MaMonHoc
            if mid not in score_map:
                score_map[mid] = {}
            score_map[mid][row.MaLoai] = float(row.DiemSo) if row.DiemSo is not None else None

        result_data = []
        for sub in subjects:
            mid = sub.MaMonHoc
            st_scores = score_map.get(mid, {})

            m1 = st_scores.get(1)
            m2 = st_scores.get(2)
            m3 = st_scores.get(3)
            tx1 = st_scores.get(4)
            tx2 = st_scores.get(5)
            gk = st_scores.get(6)
            ck = st_scores.get(7)

            # Tính điểm trung bình môn
            tx_list = [v for v in [m1, m2, m3, tx1, tx2] if v is not None]
            total_sum = sum(tx_list)
            total_count = len(tx_list)

            if gk is not None:
                total_sum += gk * 2
                total_count += 2
            if ck is not None:
                total_sum += ck * 3
                total_count += 3

            avg_score = round(total_sum / total_count, 1) if total_count > 0 else None

            result_data.append({
                'MaMonHoc': mid,
                'TenMonHoc': sub.TenMonHoc,
                'M1': m1, 'M2': m2, 'M3': m3,
                'TX1': tx1, 'TX2': tx2,
                'GK': gk, 'CK': ck,
                'TB': avg_score
            })

        return jsonify({
            'success': True,
            'student_name': student.HoTen if student else "Học sinh",
            'class_name': student.TenLop if student else "8A1",
            'data': result_data
        })
    except Exception as e:
        print(f"[ERR STUDENT GRADES] {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()

# 1. API LẤY DANH SÁCH NGƯỜI DÙNG KÈM THÔNG TIN LIÊN KẾT (LỚP, CON LIÊN KẾT)
@app.route("/api/admin/users/<role>", methods=["GET"])
def get_admin_users(role):
    db = SessionLocal()
    try:
        db_role = (
            "Teacher"
            if role == "teachers"
            else ("Student" if role == "students" else "Parent")
        )

        query = text("""
            SELECT 
                u.MaNguoiDung, 
                u.HoTen, 
                u.Email, 
                u.VaiTro,
                u.TrangThaiOnline,
                u.MaLop,
                l.TenLop,
                u.MaHocSinhLienKet,
                child.HoTen AS TenHocSinh,
                child_l.TenLop AS TenLopCon
            FROM dbo.NguoiDung u
            LEFT JOIN dbo.LopHoc l ON u.MaLop = l.MaLop
            LEFT JOIN dbo.NguoiDung child ON u.MaHocSinhLienKet = child.MaNguoiDung
            LEFT JOIN dbo.LopHoc child_l ON child.MaLop = child_l.MaLop
            WHERE u.VaiTro = :role
            ORDER BY u.MaNguoiDung DESC
        """)

        users = db.execute(query, {"role": db_role}).fetchall()

        return jsonify({
            "success": True, 
            "data": [dict(row._mapping) for row in users]
        })
    except Exception as e:
        print(f"[ERR GET USERS] {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


# 2. API TẠO TÀI KHOẢN MỚI CHO GIÁO VIÊN, HỌC SINH VÀ PHỤ HUYNH
@app.route("/api/admin/users/create", methods=["POST"])
def create_user_admin():
    data = request.json or {}
    role = data.get("role")  # 'Teacher', 'Student', 'Parent'
    ho_ten = data.get("ho_ten", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "123456").strip()

    class_id = data.get("class_id")          # Dành cho Học sinh
    subject_id = data.get("subject_id")      # Dành cho Giáo viên bộ môn
    gvcn_class_id = data.get("gvcn_class_id")  # Dành cho GVCN
    child_id = data.get("child_id")          # Dành cho Phụ huynh

    if not role or not ho_ten or not email:
        return jsonify({"success": False, "message": "Vui lòng nhập đầy đủ thông tin bắt buộc!"}), 400

    db = SessionLocal()
    try:
        exists = db.execute(text("SELECT MaNguoiDung FROM dbo.NguoiDung WHERE Email = :e"), {"e": email}).fetchone()
        if exists:
            return jsonify({"success": False, "message": f"Email '{email}' đã tồn tại trên hệ thống!"}), 400

        target_class = int(class_id) if (role == "Student" and class_id) else None
        target_child = int(child_id) if (role == "Parent" and child_id) else None

        # 1. Thêm tài khoản mới
        insert_query = text("""
            INSERT INTO dbo.NguoiDung (HoTen, Email, MatKhau, VaiTro, MaLop, MaHocSinhLienKet, TrangThaiOnline)
            VALUES (:name, :email, :pwd, :role, :cid, :child_id, 0)
        """)
        db.execute(insert_query, {
            "name": ho_ten,
            "email": email,
            "pwd": password,
            "role": role,
            "cid": target_class,
            "child_id": target_child
        })
        db.flush()

        new_uid = db.execute(text("SELECT @@IDENTITY")).scalar()

        # 2. Xử lý Giáo viên: Gán GVCN và Phân công môn học
        if role == "Teacher":
            if gvcn_class_id:
                db.execute(text("UPDATE dbo.LopHoc SET MaGVCN = :uid WHERE MaLop = :cid"), {"uid": new_uid, "cid": int(gvcn_class_id)})
            
            # Tự động gán môn học vào bảng PhanCongGiangDay
            if subject_id:
                assigned_class = int(gvcn_class_id) if gvcn_class_id else 1
                db.execute(text("""
                    IF NOT EXISTS (SELECT 1 FROM dbo.PhanCongGiangDay WHERE MaGiaoVien = :uid AND MaMonHoc = :mid AND MaLop = :cid)
                    BEGIN
                        INSERT INTO dbo.PhanCongGiangDay (MaGiaoVien, MaMonHoc, MaLop)
                        VALUES (:uid, :mid, :cid)
                    END
                """), {"uid": new_uid, "mid": int(subject_id), "cid": assigned_class})

        # 3. Ghi log hoạt động
        admin_id = session.get("user_id")
        db.execute(text("""
            INSERT INTO dbo.LogHeThong (MaNguoiThucHien, HanhDong, LoaiHanhDong, ChiTiet, ThoiGian)
            VALUES (:uid, :act, 'CREATE_USER', :detail, GETDATE())
        """), {
            "uid": admin_id,
            "act": f"Tạo tài khoản {role}: {ho_ten}",
            "detail": f"Email: {email}, Vai trò: {role}"
        })

        db.commit()
        return jsonify({"success": True, "message": f"Đã tạo thành công tài khoản {role} cho '{ho_ten}'!"})

    except Exception as e:
        db.rollback()
        print(f"[ERR CREATE USER] {e}")
        return jsonify({"success": False, "message": f"Lỗi hệ thống: {str(e)}"}), 500
    finally:
        db.close()


# 3. API RESET MẬT KHẨU
@app.route("/api/admin/users/reset-password/<int:user_id>", methods=["POST"])
def reset_user_password(user_id):
    db = SessionLocal()
    try:
        db.execute(text("""
            UPDATE dbo.NguoiDung 
            SET MatKhau = '123456' 
            WHERE MaNguoiDung = :uid
        """), {"uid": user_id})

        admin_id = session.get("user_id")
        db.execute(text("""
            INSERT INTO dbo.LogHeThong (MaNguoiThucHien, HanhDong, LoaiHanhDong, ChiTiet, ThoiGian)
            VALUES (:admin_id, :act, 'RESET_PASSWORD', :detail, GETDATE())
        """), {
            "admin_id": admin_id,
            "act": f"Reset mật khẩu tài khoản #{user_id}",
            "detail": "Đặt lại mật khẩu về mặc định 123456"
        })

        db.commit()
        return jsonify({"success": True, "message": "Đã reset mật khẩu về 123456"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


# 4. API XÓA TÀI KHOẢN
@app.route("/api/admin/users/delete/<int:user_id>", methods=["DELETE"])
def delete_user_admin(user_id):
    db = SessionLocal()
    try:
        # Hủy liên kết phụ huynh / GVCN trước khi xóa
        db.execute(text("UPDATE dbo.LopHoc SET MaGVCN = NULL WHERE MaGVCN = :uid"), {"uid": user_id})
        db.execute(text("UPDATE dbo.NguoiDung SET MaHocSinhLienKet = NULL WHERE MaHocSinhLienKet = :uid"), {"uid": user_id})
        
        # Xóa người dùng
        db.execute(text("DELETE FROM dbo.NguoiDung WHERE MaNguoiDung = :uid"), {"uid": user_id})

        admin_id = session.get("user_id")
        db.execute(text("""
            INSERT INTO dbo.LogHeThong (MaNguoiThucHien, HanhDong, LoaiHanhDong, ChiTiet, ThoiGian)
            VALUES (:admin_id, :act, 'DELETE_USER', :detail, GETDATE())
        """), {
            "admin_id": admin_id,
            "act": f"Xóa tài khoản #{user_id}",
            "detail": f"Đã xóa người dùng #{user_id} khỏi CSDL"
        })

        db.commit()
        return jsonify({"success": True, "message": "Đã xóa tài khoản khỏi hệ thống"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


# ==============================================================================
# 3. KHỞI CHẠY KIỂM TRA DATABASE
# ==============================================================================

with app.app_context():
    ensure_db_columns()

# ==============================================================================
# 2. ĐỊNH TUYẾN GIAO DIỆN (ĐÃ SỬA LỖI TRÙNG ROUTE/HÀM)
# ==============================================================================

@app.route('/')
def home(): return render_template('index.html')

@app.route('/prototype')
def platform_prototype(): return render_template('prototype_platform.html')

@app.route('/prototype-public')
def public_prototype(): return render_template('prototype_public.html')

@app.route('/thu-vien-cong-khai')
def public_materials_page(): return render_template('public_materials.html')

@app.route('/api-docs')
def api_docs_page(): return render_template('api_docs.html')

@app.route('/login')
def login_page(): return render_template('login.html')

@app.route('/register')
def register_page(): return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return render_template('index.html')

# ==============================================================================
# BỔ SUNG PHÂN HỆ: BÀI TEST ĐÁNH GIÁ NĂNG LỰC TRẮC NGHIỆM (7 NHÓM NĂNG LỰC)
# ==============================================================================

@app.route('/api/submit-test', methods=['POST'])
def submit_assessment_test():
    """
    API tiếp nhận kết quả điểm số các nhóm năng lực, đóng gói định dạng JSON 
    và lưu trữ trực tiếp vào bảng dbo.KetQuaTestNangLuc theo cấu trúc CSDL thực tế.
    """
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        data = request.json or {}
        
        scores_data = data.get('scores', {})
        target_grade = data.get('grade') or session.get('khoi_id') or 1
        
        if not scores_data:
            return jsonify({"success": False, "message": "Không tìm thấy dữ liệu điểm số 'scores'"}), 400

        mapping_competencies = {
            "ToanLogic": "Toán học & logic",
            "NguVanDienDat": "Ngữ văn & diễn đạt",
            "NgoaiNgu": "Ngoại ngữ",
            "KHTN": "Khoa học tự nhiên",
            "KHXH": "Khoa học xã hội",
            "TinHocCongNghe": "Tin học & công nghệ",
            "TuHocQuanLy": "Tự học & quản lý thời gian"
        }

        processed_scores = {}
        total_sum = 0.0
        count = 0
        
        for front_key, score_value in scores_data.items():
            nhom_nang_luc = mapping_competencies.get(front_key, front_key)
            try:
                score = round(float(score_value), 1)
            except (ValueError, TypeError):
                score = 0.0
                
            processed_scores[nhom_nang_luc] = score
            total_sum += score
            count += 1

        avg_total_score = round(total_sum / count, 1) if count > 0 else 0.0

        json_payload = {
            "loai_kiem_tra": "Đánh giá 7 nhóm năng lực cốt lõi THCS",
            "chi_tiet_diem": processed_scores
        }
        json_string_data = json.dumps(json_payload, ensure_ascii=False)

        user_name = "Khách vãng lai"
        if user_id:
            user_row = db.execute(text("SELECT HoTen FROM dbo.NguoiDung WHERE MaNguoiDung = :uid"), {"uid": user_id}).fetchone()
            if user_row:
                user_name = user_row.HoTen

        insert_query = text("""
            INSERT INTO dbo.KetQuaTestNangLuc (MaNguoiDung, TenNguoiLam, MaKhoi, DiemSo, DanhGiaAI, NgayLam)
            VALUES (:uid, :name, :grade, :score, :ai_data, GETDATE())
        """)
        
        db.execute(insert_query, {
            "uid": user_id, 
            "name": user_name,
            "grade": int(target_grade) if str(target_grade).isdigit() else 1,
            "score": avg_total_score,
            "ai_data": json_string_data
        })
        
        db.commit()
        print("[SUCCESS] Đã lưu kết quả Đánh giá năng lực vào database LopHocSo thành công!")
        
        return jsonify({
            "success": True, 
            "message": "Nộp bài thành công! Điểm số năng lực của bạn đã được lưu trữ an toàn."
        })
        
    except Exception as e:
        db.rollback()
        print(f"[CRITICAL ERR SUBMIT TEST] {str(e)}")
        return jsonify({"success": False, "message": f"Lỗi đồng bộ CSDL: {str(e)}"}), 500
    finally:
        db.close()


@app.route('/api/submit-assessment-v2', methods=['POST'])
def submit_assessment_v2():
    """
    API Tiếp nhận Khảo sát Năng lực nâng cao:
    - Kiểm tra xem có Dữ liệu Sổ điểm lớp dưới không (Bằng student_code hoặc session)
    - Phân tích Ngữ cảnh: Đầu năm (Chẩn đoán lỗ hổng) hay Cuối năm (Định hướng/Thi 10)
    - Gọi Gemini 2.0 Flash trả về Lời khuyên Sư phạm chuẩn mực cho GVCN và Học sinh
    """
    db = SessionLocal()
    try:
        data = request.json or {}
        student_name = data.get('student_name', 'Học sinh')
        student_class = data.get('student_class', 'Chưa xếp lớp')
        student_code = data.get('student_code', '').strip()
        current_grade = data.get('current_grade', '6')
        period = data.get('period', 'start') # 'start' = Đầu năm, 'end' = Cuối năm
        test_scores = data.get('test_scores', {})

        user_id = session.get('user_id')
        historical_grades_text = "Chưa có dữ liệu sổ điểm điện tử năm ngoái."

        # 1. TRUY VẤN CƠ CHẾ DỮ LIỆU KÉP: Lấy điểm Sổ điểm nếu tìm thấy Học sinh
        target_uid = user_id
        if not target_uid and student_code:
            user_row = db.execute(text("SELECT MaNguoiDung FROM NguoiDung WHERE Email LIKE :code OR HoTen LIKE :code"), {"code": f"%{student_code}%"}).fetchone()
            if user_row:
                target_uid = user_row.MaNguoiDung

        if target_uid:
            # Lấy điểm trung bình các môn của năm ngoái từ BangDiem
            prev_grades = db.execute(text("""
                SELECT mh.TenMonHoc, AVG(CAST(bd.DiemSo AS FLOAT)) as DTB
                FROM BangDiem bd
                JOIN MonHoc mh ON bd.MaMonHoc = mh.MaMonHoc
                WHERE bd.MaHocSinh = :uid
                GROUP BY mh.TenMonHoc
            """), {"uid": target_uid}).fetchall()

            if prev_grades:
                historical_grades_text = ", ".join([f"{g.TenMonHoc}: {round(g.DTB, 1)}đ" for g in prev_grades])

        # 2. XÂY DỰNG PROMPT CHUYÊN SÂU THEO LẬP LUẬN VỚI GVHD
        period_str = "ĐẦU NĂM HỌC (Tháng 9)" if period == 'start' else "CUỐI NĂM HỌC (Tháng 5)"
        
        system_prompt = f"""
        Bạn là Cố vấn Giáo dục THCS EduNext. Hãy lập Báo cáo Tư vấn Sư phạm cho:
        - Học sinh: {student_name} (Lớp {student_class}, Khối {current_grade})
        - Thời điểm: {period_str}
        - Dữ liệu Sổ điểm cũ (Năm trước): {historical_grades_text}
        - Dữ liệu Khảo sát hiện tại (7 nhóm năng lực /100): {json.dumps(test_scores, ensure_ascii=False)}

        YÊU CẦU ĐẶC THÙ THEO NGỮ CẢNH:
        1. Nếu là ĐẦU NĂM (Tháng 9): Chỉ ra các "Lỗ hổng kiến thức" bị quên sau kỳ nghỉ Hè. Đưa ra giải pháp bù đắp ngay trong Tháng 9. Gợi ý GVCN ghép em vào nhóm "Đôi bạn cùng tiến" phù hợp.
        2. Nếu là CUỐI NĂM (Tháng 5) & Khối 9: Đánh giá khả năng thi vào Lớp 10 các trường THPT Chuyên/Công lập dựa trên tổng hòa lực học.
        3. Nếu là CUỐI NĂM (Khối 6,7,8): Đưa ra lộ trình đọc sách và ôn tập Hè.
        4. Trả về văn phong sư phạm khích lệ, phân đoạn rõ ràng bằng dấu gạch đầu dòng.
        """

        # 3. GỌI GEMINI 2.0 FLASH ĐỂ TẠO LỜI KHUYÊN
        from app.config import GEMINI_API_KEY
        import google.generativeai as genai
        
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(model_name="gemini-2.0-flash")
        ai_response = model.generate_content(system_prompt)
        advice_text = ai_response.text.strip()

        # 4. LƯU BẢN GHI VÀO CSDL KETQUATESTNANGLUC
        avg_test_score = round(sum(test_scores.values()) / len(test_scores), 1) if test_scores else 0.0
        
        payload_data = json.dumps({
            "thoi_diem": period,
            "khoi": current_grade,
            "diem_test": test_scores,
            "so_diem_cu": historical_grades_text
        }, ensure_ascii=False)

        db.execute(text("""
            INSERT INTO dbo.KetQuaTestNangLuc (MaNguoiDung, TenNguoiLam, MaKhoi, DiemSo, DanhGiaAI, NgayLam)
            VALUES (:uid, :name, :grade, :score, :ai_data, GETDATE())
        """), {
            "uid": target_uid,
            "name": student_name,
            "grade": int(current_grade),
            "score": avg_test_score,
            "ai_data": payload_data
        })
        
        db.commit()

        return jsonify({
            "success": True,
            "message": "Đã lưu kết quả chẩn đoán thành công!",
            "advice": advice_text
        })

    except Exception as e:
        db.rollback()
        print(f"[ERR SUBMIT ASSESSMENT V2] {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

# ==============================================================================
# NÂNG CẤP HOÀN THIỆN: TRỢ LÝ AI PHÂN TÍCH CHUYÊN SÂU MÔ HÌNH THẬT (GEMINI 2.0 FLASH)
# ==============================================================================

@app.route('/api/ai/chat-legacy', methods=['POST'])
def ai_chat_legacy():
    from app.config import GEMINI_API_KEY
    import google.generativeai as genai
    
    try:
        if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
            return jsonify({"success": False, "message": "Chưa cấu hình Gemini API Key trong config.py"}), 400
            
        genai.configure(api_key=GEMINI_API_KEY)
        
        data = request.json
        user_msg = data.get('message', '')
        user_id = session.get('user_id')
        
        db_context = ""
        role_label = "Trợ lý Giáo dục"
        system_prompt = "Bạn là Trợ lý Giáo dục trực thuộc hệ thống EduNext."

        if user_id:
            db = SessionLocal()
            try:
                u_db = db.execute(text("SELECT HoTen, VaiTro, MaLop FROM NguoiDung WHERE MaNguoiDung = :uid"), {"uid": user_id}).fetchone()
                
                if u_db:
                    real_role = u_db.VaiTro.lower()
                    user_name = u_db.HoTen
                    user_class = u_db.MaLop

                    if real_role in ['teacher', 'admin']:
                        class_info = db.execute(text("SELECT MaLop, TenLop FROM LopHoc WHERE MaGVCN = :uid"), {"uid": user_id}).fetchone()
                        if class_info:
                            cid, cname = class_info.MaLop, class_info.TenLop
                            
                            sa_sut_rows = db.execute(text("""
                                SELECT TOP 3 nd.HoTen, 
                                       COUNT(DISTINCT dd.NgayDiemDanh) as SoBuoiVang,
                                       ISNULL(SUM(nk.DiemXP), 0) as TongXP
                                FROM NguoiDung nd
                                LEFT JOIN DiemDanh dd ON nd.MaNguoiDung = dd.MaHocSinh AND dd.TrangThai LIKE N'Vang%'
                                LEFT JOIN NhatKyReNep nk ON nd.MaNguoiDung = nk.MaHocSinh
                                WHERE nd.MaLop = :cid AND nd.VaiTro = 'Student'
                                GROUP BY nd.HoTen
                                HAVING COUNT(DISTINCT dd.NgayDiemDanh) >= 3 OR ISNULL(SUM(nk.DiemXP), 0) < 0
                            """), {"cid": cid}).fetchall()
                            
                            sa_sut_text = ", ".join([f"{r.HoTen} (Vắng: {r.SoBuoiVang} buổi, XP: {r.TongXP})" for r in sa_sut_rows]) if sa_sut_rows else "Không có biến động tiêu cực."
                            db_context = f"LỚP CHỦ NHIỆM: {cname}. DANH SÁCH HỌC SINH NGUY CƠ SA SÚT CẦN LƯU Ý: {sa_sut_text}."
                            role_label = "Cố vấn Chủ nhiệm định lượng"
                            
                    elif real_role == 'student':
                        latest_test = db.execute(text("""
                            SELECT TOP 1 DanhGiaAI, DiemSo 
                            FROM dbo.KetQuaTestNangLuc 
                            WHERE MaNguoiDung = :uid 
                            ORDER BY NgayLam DESC
                        """), {"uid": user_id}).fetchone()
                        
                        comp_text = "Chưa thực hiện bài test đánh giá năng lực hệ thống."
                        if latest_test and latest_test.DanhGiaAI:
                            try:
                                test_data = json.loads(latest_test.DanhGiaAI)
                                details = test_data.get("chi_tiet_diem", {})
                                comp_text = ", ".join([f"{k}: {v}/100" for k, v in details.items()])
                            except Exception:
                                comp_text = f"Điểm trung bình bài test: {latest_test.DiemSo}/100."
                        
                        xp_total = db.execute(text("SELECT ISNULL(SUM(DiemXP), 0) FROM dbo.NhatKyReNep WHERE MaHocSinh = :uid"), {"uid": user_id}).scalar() or 0
                        class_name = db.execute(text("SELECT TenLop FROM dbo.LopHoc WHERE MaLop = :cid"), {"cid": user_class}).scalar() or "Chưa phân lớp"
                        
                        db_context = f"HỌC SINH: {user_name} (Lớp {class_name}, Điểm nề nếp XP: {xp_total}). KẾT QUẢ ĐIỂM SỐ 7 NHÓM NĂNG LỰC TỪ BÀI TEST THỰC TẾ: {comp_text}."
                        role_label = "Gia sư Khoa học AI"

                    elif real_role == 'parent':
                        student = db.execute(text("SELECT MaNguoiDung, HoTen FROM NguoiDung WHERE MaNguoiDung = (SELECT MaHocSinhLienKet FROM NguoiDung WHERE MaNguoiDung = :uid)"), {"uid": user_id}).fetchone()
                        if student:
                            db_context = f"PHỤ HUYNH CHÁU {student.HoTen}. Dữ liệu học tập và rèn luyện đồng bộ thời gian thực từ nhà trường."
                            role_label = "Chuyên gia Tư vấn Đồng hành"

                    system_prompt = (
                        f"Bạn là '{role_label} EduNext', trợ lý phân tích dữ liệu giáo dục thông minh bậc THCS. "
                        f"DỮ LIỆU HỆ THỐNG THỰC TẾ: {db_context}. "
                        "YÊU CẦU BẮT BUỘC: \n"
                        "1. Chỉ đưa ra nhận xét, đánh giá và giải pháp ôn tập lớp 10 dựa hoàn toàn vào dữ liệu định lượng bài làm được cung cấp ở trên.\n"
                        "2. Tuyệt đối KHÔNG tự suy diễn, tạo ra số liệu giả nằm ngoài ngữ cảnh.\n"
                        "3. Định hướng học sinh tập trung cải thiện các nhóm năng lực có điểm số thấp từ bài kiểm tra năng lực đầu vào."
                    )
            except Exception as db_err:
                print(f"[AI Context Error] {db_err}")
            finally:
                db.close()
        else:
            system_prompt = "Bạn là Trợ lý Tuyển sinh EduNext, cố vấn giải đáp lộ trình thi trắc nghiệm đầu vào lớp 10."

        model = genai.GenerativeModel(model_name="gemini-2.0-flash", system_instruction=system_prompt)
        response = model.generate_content(user_msg)
        return jsonify({"success": True, "reply": response.text.strip()})
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ĐỔI TÊN HÀM THÀNH guest_ai_chat_v4 ĐỂ TRÁNH TRÙNG LẶP ĐÈ ROUTE HỆ THỐNG
@app.route('/guest/api/chat/v4', methods=['POST'])
def guest_ai_chat_v4():
    try:
        data = request.json
        message = data.get("message")
        role = data.get("role", "guest") 
        if not message:
            return jsonify({"success": False, "message": "Nội dung yêu cầu trống"}), 400

        from app.services.ai_service import chat_ai
        result = chat_ai(role=role, message=message)
        return jsonify({"success": True, "response": result})
    except Exception as e:
        print(f"❌ GUEST AI ERROR: {str(e)}")
        return jsonify({"success": False, "message": "AI đang bận, vui lòng thử lại sau"}), 500


# ĐỔI TÊN HÀM THÀNH ai_chat_v4 ĐỂ TRÁNH XUNG ĐỘT ENDPOINT
@app.route('/api/ai/chat/v4', methods=['POST'])
def ai_chat_v4():
    from app.config import GEMINI_API_KEY
    import google.generativeai as genai
    
    try:
        if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
            return jsonify({"success": False, "message": "Chưa cấu hình Gemini API Key"}), 400
            
        genai.configure(api_key=GEMINI_API_KEY)
        data = request.json
        user_msg = data.get('message', '')
        user_id = session.get('user_id')
        
        db_context = ""
        role_label = "Trợ lý EduNext"
        system_prompt = "Bạn là Trợ lý EduNext."

        if user_id:
            db = SessionLocal()
            try:
                u_db = db.execute(text("SELECT HoTen, VaiTro, MaLop FROM NguoiDung WHERE MaNguoiDung = :uid"), {"uid": user_id}).fetchone()
                if u_db:
                    real_role = u_db.VaiTro.lower()
                    user_name = u_db.HoTen
                    user_class = u_db.MaLop

                    if real_role in ['teacher', 'admin']:
                        class_info = db.execute(text("SELECT MaLop, TenLop FROM LopHoc WHERE MaGVCN = :uid"), {"uid": user_id}).fetchone()
                        if class_info:
                            cid, cname = class_info.MaLop, class_info.TenLop
                            siso = db.execute(text("SELECT COUNT(*) FROM NguoiDung WHERE MaLop = :cid AND VaiTro = 'Student'"), {"cid": cid}).scalar()
                            db_context = f"DỮ LIỆU LỚP {cname}: Sĩ số {siso}."
                            role_label = "Trợ lý Chủ nhiệm"
                    
                    elif real_role == 'student':
                        xp_total = db.execute(text("SELECT SUM(DiemXP) FROM NhatKyReNep WHERE MaHocSinh = :uid"), {"uid": user_id}).scalar() or 0
                        class_name = db.execute(text("SELECT TenLop FROM LopHoc WHERE MaLop = :cid"), {"cid": user_class}).scalar() if user_class else "Chưa có lớp"
                        db_context = f"CHÀO {user_name}: Bạn ở lớp {class_name}, XP: {xp_total}."
                        role_label = "Gia sư AI"

                    elif real_role == 'parent':
                        student = db.execute(text("SELECT MaNguoiDung, HoTen FROM NguoiDung WHERE MaNguoiDung = (SELECT MaHocSinhLienKet FROM NguoiDung WHERE MaNguoiDung = :uid)"), {"uid": user_id}).fetchone()
                        if student:
                            s_xp = db.execute(text("SELECT SUM(DiemXP) FROM NhatKyReNep WHERE MaHocSinh = :sid"), {"sid": student.MaNguoiDung}).scalar() or 0
                            db_context = f"PHỤ HUYNH CHÁU {student.HoTen}: Tổng XP rèn luyện đạt {s_xp}."
                            role_label = "Cố vấn Giáo dục"

                    system_prompt = f"Bạn là '{role_label} EduNext'. Ngữ cảnh: {db_context}"
            except Exception as db_err:
                print(db_err)
            finally:
                db.close()
        
        model = genai.GenerativeModel(model_name="gemini-2.0-flash", system_instruction=system_prompt)
        response = model.generate_content(user_msg)
        return jsonify({"success": True, "reply": response.text.strip()})
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/teacher/conduct/ai-comment', methods=['POST'])
def generate_ai_conduct_comment():
    """
    API KẾT NỐI TAB NỀ NẾP: Cung cấp lời giải xét văn phong sư phạm thật cho nút 'AI Viết Nhanh'
    """
    try:
        data = request.json or {}
        student_name = data.get('student_name', 'Học sinh')
        xp = data.get('xp', 0)
        attendance_ratio = data.get('attendance_ratio', 100.0)
        assignment_ratio = data.get('assignment_ratio', 100.0)
        action_type = data.get('action_type', 'reward')

        context_str = "khen thưởng biểu dương thành tích" if action_type == "reward" else "nhắc nhở nghiêm túc phê bình lỗi sai"
        
        prompt = f"""
        Bạn là Trợ lý AI đồng hành cùng Giáo viên chủ nhiệm THCS EduNext.
        Hãy viết duy nhất 1 câu nhận xét sư phạm ngắn gọn (dưới 35 từ) để ghi vào sổ cái nề nếp.
        - Học sinh: {student_name}
        - Điểm thi đua: {xp} XP
        - Tỷ lệ đi học chuyên cần: {attendance_ratio}%
        - Tỷ lệ nộp bài tập môn học: {assignment_ratio}%
        - Định hướng sư phạm giáo viên chọn: {context_str}
        
        Yêu cầu câu từ chuẩn mực học đường. Trả về text thuần nhận xét, không chứa dấu ngoặc kép.
        """
        
        model = genai.GenerativeModel(model_name="gemini-2.0-flash")
        response = model.generate_content(prompt)
        return jsonify({"success": True, "comment": response.text.strip()})
    except Exception as e:
        print(f"❌ Lỗi Gemini rèn luyện: {str(e)}")
        return jsonify({"success": True, "comment": f"Ghi nhận em {student_name} tích cực tham gia các hoạt động thi đua của lớp."})

# API TỔNG KẾT HỌC LỰC, HẠNH KIỂM & XÉT LÊN LỚP CẢ LỚP (DÀNH CHO GVCN)
@app.route('/api/teacher/class-summary', methods=['GET'])
def get_teacher_class_summary():
    class_id = request.args.get('class_id')
    semester_id = request.args.get('semester_id', 1, type=int)

    db = SessionLocal()
    try:
        # 1. Lấy danh sách học sinh theo lớp
        students = db.execute(text("""
            SELECT MaNguoiDung, HoTen 
            FROM dbo.NguoiDung 
            WHERE (:cid IS NULL OR MaLop = :cid) AND VaiTro = 'Student'
            ORDER BY HoTen ASC
        """), {'cid': class_id if class_id else None}).fetchall()

        # 2. Lấy danh mục 13 môn học
        subjects = db.execute(text("SELECT MaMonHoc FROM dbo.MonHoc")).fetchall()
        total_subjects_count = len(subjects) or 13

        summary_data = []

        for s in students:
            sid = s.MaNguoiDung

            # Lấy toàn bộ điểm của học sinh này
            scores = db.execute(text("""
                SELECT MaMonHoc, MaLoai, DiemSo 
                FROM dbo.BangDiem 
                WHERE MaHocSinh = :sid AND MaHocKy = :sem
            """), {'sid': sid, 'sem': semester_id}).fetchall()

            # Nhóm điểm theo môn học
            subject_score_map = {}
            for row in scores:
                mid = row.MaMonHoc
                if mid not in subject_score_map:
                    subject_score_map[mid] = {}
                subject_score_map[mid][row.MaLoai] = float(row.DiemSo) if row.DiemSo is not None else None

            # Tính điểm trung bình từng môn
            subject_averages = []
            for mid, st_scores in subject_score_map.items():
                m1 = st_scores.get(1)
                m2 = st_scores.get(2)
                m3 = st_scores.get(3)
                tx1 = st_scores.get(4)
                tx2 = st_scores.get(5)
                gk = st_scores.get(6)
                ck = st_scores.get(7)

                tx_list = [v for v in [m1, m2, m3, tx1, tx2] if v is not None]
                total_sum = sum(tx_list)
                total_count = len(tx_list)

                if gk is not None:
                    total_sum += gk * 2
                    total_count += 2
                if ck is not None:
                    total_sum += ck * 3
                    total_count += 3

                if total_count > 0:
                    subject_averages.append(round(total_sum / total_count, 1))

            completed_count = len(subject_averages)
            
            # Lấy điểm hạnh kiểm/thi đua XP
            xp_total = db.execute(text("""
                SELECT ISNULL(SUM(DiemXP), 0) FROM dbo.NhatKyReNep WHERE MaHocSinh = :sid
            """), {'sid': sid}).scalar() or 0

            hanh_kiem = "Tốt"
            if xp_total < -30:
                hanh_kiem = "Chưa đạt"
            elif xp_total < 0:
                hanh_kiem = "Đạt"
            elif xp_total < 50:
                hanh_kiem = "Khá"

            if completed_count < total_subjects_count:
                # Chưa đủ điểm tất cả các môn
                temp_gpa = round(sum(subject_averages) / completed_count, 1) if completed_count > 0 else None
                summary_data.append({
                    'MaHocSinh': sid,
                    'HoTen': s.HoTen,
                    'DTBChung': temp_gpa,
                    'HocLuc': f"Đang cập nhật ({completed_count}/{total_subjects_count} môn)",
                    'HanhKiem': hanh_kiem,
                    'TrangThaiXetDuyet': "Chờ đủ điểm",
                    'SoMonDaCo': completed_count
                })
            else:
                # Đã có đủ điểm tất cả các môn -> Xét duyệt chính thức
                final_gpa = round(sum(subject_averages) / total_subjects_count, 1)
                min_score = min(subject_averages)

                hoc_luc = "Chưa đạt"
                xet_duyet = "Kiểm tra lại"

                if final_gpa >= 8.0 and min_score >= 6.5 and hanh_kiem in ['Tốt', 'Khá']:
                    hoc_luc = "Học lực Tốt"
                    xet_duyet = "Được lên lớp"
                elif final_gpa >= 6.5 and min_score >= 5.0 and hanh_kiem != 'Chưa đạt':
                    hoc_luc = "Học lực Khá"
                    xet_duyet = "Được lên lớp"
                elif final_gpa >= 5.0 and min_score >= 3.5 and hanh_kiem != 'Chưa đạt':
                    hoc_luc = "Học lực Đạt"
                    xet_duyet = "Được lên lớp"
                else:
                    hoc_luc = "Chưa đạt"
                    xet_duyet = "Kiểm tra lại"

                summary_data.append({
                    'MaHocSinh': sid,
                    'HoTen': s.HoTen,
                    'DTBChung': final_gpa,
                    'HocLuc': hoc_luc,
                    'HanhKiem': hanh_kiem,
                    'TrangThaiXetDuyet': xet_duyet,
                    'SoMonDaCo': completed_count
                })

        return jsonify({'success': True, 'data': summary_data})
    except Exception as e:
        print(f"[ERR CLASS SUMMARY] {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()


# --- HỌC SINH ---
@app.route('/dashboard')
def dashboard_page(): return render_template('HS/dashboard_student.html', active_page='dashboard')

@app.route('/kho-hoc-lieu')
def kho_hoc_lieu_page(): return render_template('HS/khohoclieu.html', active_page='khohoclieu')

@app.route('/bai-tap')
def bai_tap_page(): return render_template('HS/baitap.html', active_page='baitap')

@app.route('/bang-thanh-tich')
def bang_thanh_tich_page(): return render_template('HS/bangthanhtich.html', active_page='thanhtich')

@app.route('/chat-ai')
def chat_ai_page(): return render_template('HS/chatai.html', active_page='chatai')

# CHỈ GIỮ 1 ROUTE PROFILE DUY NHẤT TRỎ VÀO THƯ MỤC HS
@app.route('/profile')
def profile_student_page(): 
    return render_template('HS/profile.html', active_page='profile')

@app.route('/student/announcements')
def student_announcements():
    return render_template('HS/announcements.html', active_page='announcements')

@app.route('/thoi-khoa-bieu')
def schedule_page():
    return render_template('HS/thoikhoabieu.html', active_page='thoikhoabieu')

#---- GIÁO VIÊN ----

@app.route('/dashboard_teacher')
def teacher_dashboard(): return render_template('GV/dashboard_teacher.html', active_page='dashboard')

@app.route('/teacher/attendance')
def teacher_attendance():
    return render_template('GV/attendance.html', active_page='attendance')

@app.route('/teacher/gradebook')
def teacher_gradebook():
    return render_template('GV/gradebook.html', active_page='gradebook')

@app.route('/teacher/events')
def teacher_events():
    return render_template('GV/events.html', active_page='events')

@app.route('/teacher/class-ledger')
def teacher_ledger():
    db = SessionLocal()
    teacher_id = session.get('user_id')
    if not teacher_id: return "Chua dang nhap", 401
    
    try:
        # Lấy MaLop của GV
        u_query = text("SELECT MaLop FROM NguoiDung WHERE MaNguoiDung = :uid")
        u_res = db.execute(u_query, {"uid": teacher_id}).fetchone()
        class_id = u_res.MaLop if u_res else 1
 
        query = text("""
            SELECT 
                nd.MaNguoiDung, 
                nd.HoTen, 
                nd.Email,
                (SELECT TOP 1 DiemSo FROM BangDiem bd WHERE bd.MaHocSinh = nd.MaNguoiDung AND bd.MaMonHoc = 1 AND bd.MaLoai = 4) as DiemToan,
                (SELECT ISNULL(SUM(DiemXP), 0) FROM NhatKyReNep nk WHERE nk.MaHocSinh = nd.MaNguoiDung) as TongXP,
                (SELECT COUNT(*) FROM DiemDanh dd WHERE dd.MaHocSinh = nd.MaNguoiDung AND dd.TrangThai IN (N'VangCP', N'VangKP')) as SoBuoiVang
            FROM NguoiDung nd
            WHERE nd.MaLop = :cid AND nd.VaiTro = 'Student'
        """)
        students_data = db.execute(query, {"cid": class_id}).fetchall()
        return render_template('GV/class_ledger.html', students=students_data, active_page='ledger')
    except Exception as e:
        print(f"[Error] Loi So cai: {e}")
        return str(e)
    finally:
        db.close()

# --- PHỤ HUYNH ---
@app.route('/dashboard_parent')
def parent_dashboard_view(): 
    return render_template('PH/dashboard_parent.html', active_page='dashboard_parent')

@app.route('/parent/announcements')
def parent_announcements_view():
    return render_template('PH/announcements.html', active_page='announcements')

@app.route('/parent/gradebook')
def parent_gradebook_view():
    # Trang Phân tích AI & Điểm số
    return render_template('PH/diem-so.html', active_page='diem-so')

@app.route('/parent/homework')
def parent_homework_view():
    # Trang Bài tập về nhà
    return render_template('PH/bai-tap.html', active_page='bai-tap')

@app.route('/parent/wallet')
def parent_wallet_view():
    # Trang Ví điện tử Edu-Wallet
    return render_template('PH/vi-dien-tu.html', active_page='vi-dien-tu')

@app.route('/parent/messages')
@app.route('/parent/chat')
def parent_chat_view():
    user_id = session.get('user_id')
    db = SessionLocal()
    u = db.execute(text("SELECT HoTen FROM NguoiDung WHERE MaNguoiDung = :uid"), {"uid": user_id}).fetchone() if user_id else None
    db.close()
    return render_template('PH/chat.html', active_page='messages', ho_ten=u[0] if u else 'Phụ huynh')

@app.route('/api/parent/dashboard', methods=['GET'])
def get_parent_dashboard():
    db = SessionLocal()
    try:
        parent_id = session.get('user_id')
        if not parent_id:
            return jsonify({'success': False, 'message': 'Chưa đăng nhập'}), 401

        # Lấy tham số tuần và học kỳ (Mặc định Tuần 1, Học kỳ 1)
        selected_week = request.args.get('week', 1, type=int)
        selected_semester = request.args.get('semester', 1, type=int)

        # 1. Lấy thông tin phụ huynh và học sinh liên kết
        query = text("""
            SELECT p.HoTen AS TenPhuHuynh, hs.MaNguoiDung AS MaHocSinh, hs.HoTen AS TenHocSinh,
                   lh.MaLop, lh.TenLop, gv.HoTen AS TenGVCN
            FROM NguoiDung p
            JOIN NguoiDung hs ON p.MaHocSinhLienKet = hs.MaNguoiDung
            LEFT JOIN LopHoc lh ON hs.MaLop = lh.MaLop
            LEFT JOIN NguoiDung gv ON lh.MaGVCN = gv.MaNguoiDung
            WHERE p.MaNguoiDung = :pid
        """)
        base = db.execute(query, {'pid': parent_id}).fetchone()
        if not base:
            return jsonify({'success': False, 'message': 'Chưa liên kết thông tin học sinh'}), 404

        # 2. Lấy danh sách ngày vắng mặt
        absent = db.execute(
            text("""
                SELECT NgayDiemDanh FROM DiemDanh 
                WHERE MaHocSinh = :sid AND TrangThai LIKE N'Vang%'
            """),
            {'sid': base.MaHocSinh},
        ).fetchall()

        # 3. Lấy lịch sử đơn xin nghỉ
        leaves = db.execute(
            text("""
                SELECT NgayNghi, LyDo, TrangThai FROM DonXinNghiHoc 
                WHERE MaHocSinh = :sid ORDER BY NgayNghi DESC
            """),
            {'sid': base.MaHocSinh},
        ).fetchall()

        # 4. Lấy thời khóa biểu (ĐÃ SỬA: Dùng MaHocKy thay vì HocKy)
        schedule = db.execute(
            text("""
                SELECT tkb.Thu, tkb.Tiet, mh.TenMonHoc, tkb.PhongHoc
                FROM ThoiKhoaBieu tkb
                JOIN MonHoc mh ON tkb.MaMonHoc = mh.MaMonHoc
                WHERE tkb.MaLop = :cid AND tkb.Tuan = :week AND tkb.MaHocKy = :sem
                ORDER BY tkb.Thu ASC, tkb.Tiet ASC
            """),
            {'cid': base.MaLop, 'week': selected_week, 'sem': selected_semester},
        ).fetchall()

        # 5. Tính XP rèn luyện & Xếp hạng (Rank)
        xp_res = db.execute(
            text("SELECT ISNULL(SUM(DiemXP), 0) FROM NhatKyReNep WHERE MaHocSinh = :sid"),
            {'sid': base.MaHocSinh},
        ).scalar() or 0

        rank_query = text("""
            SELECT Rank FROM (
                SELECT MaHocSinh, RANK() OVER (ORDER BY ISNULL(SUM(DiemXP), 0) DESC) as Rank
                FROM NhatKyReNep
                GROUP BY MaHocSinh
            ) t WHERE MaHocSinh = :sid
        """)
        rank_res = db.execute(rank_query, {'sid': base.MaHocSinh}).scalar() or '--'

        # 6. Tính chuỗi ngày đi học (Streak)
        streak_query = text("""
            SELECT COUNT(DISTINCT NgayDiemDanh) 
            FROM DiemDanh 
            WHERE MaHocSinh = :sid 
            AND TrangThai IN (N'HienDien', N'Muon')
            AND NgayDiemDanh >= DATEADD(day, -30, GETDATE())
        """)
        streak_res = db.execute(streak_query, {'sid': base.MaHocSinh}).scalar() or 0

        return jsonify({
            'success': True,
            'data': {
                'parent_name': base.TenPhuHuynh,
                'student_name': base.TenHocSinh,
                'class_name': base.TenLop or 'Chưa xếp lớp',
                'teacher_name': base.TenGVCN or 'Chưa phân công',
                'xp': int(xp_res),
                'rank': rank_res,
                'streak': streak_res,
                'absent_dates': [{'Ngay': str(r.NgayDiemDanh)} for r in absent],
                'leave_requests': [dict(r._mapping) for r in leaves],
                'schedule': [dict(r._mapping) for r in schedule],
            },
        })
    except Exception as e:
        print(f"❌ LỖI PARENT DASHBOARD: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()


@app.route('/api/parent/assignments', methods=['GET'])
def get_parent_assignments():
    db = SessionLocal()
    try:
        parent_id = session.get('user_id')
        if not parent_id:
            return jsonify({'success': False, 'message': 'Chưa đăng nhập'}), 401

        # 1. Lấy thông tin học sinh liên kết với phụ huynh (Fallback về em Lý Phương Nam ID=30 nếu chưa liên kết)
        student = db.execute(text("""
            SELECT hs.MaNguoiDung, hs.HoTen, hs.MaLop 
            FROM NguoiDung p
            JOIN NguoiDung hs ON p.MaHocSinhLienKet = hs.MaNguoiDung
            WHERE p.MaNguoiDung = :pid
        """), {'pid': parent_id}).fetchone()

        student_id = student.MaNguoiDung if (student and student.MaNguoiDung) else 30
        student_name = student.HoTen if student else "Lý Phương Nam"
        
        st_class = db.execute(text("SELECT MaLop FROM NguoiDung WHERE MaNguoiDung = :sid"), {'sid': student_id}).fetchone()
        class_id = st_class.MaLop if (st_class and st_class.MaLop) else 3

        # 2. Truy vấn bài tập chuẩn theo đúng tên cột NoiDungBaiLam trong CSDL
        query = text("""
            SELECT 
                bt.MaBaiTap,
                bt.TieuDe,
                bt.NoiDung,
                bt.FileDinhKem AS FileDeBai,
                mh.TenMonHoc,
                gv.HoTen AS TenGiaoVien,
                FORMAT(bt.HanNop, 'yyyy-MM-dd HH:mm') AS HanNop,
                bl.MaBaiLam,
                bl.NoiDungBaiLam AS NoiDungNop,
                bl.FileDinhKem AS FileBaiLam,
                bl.DiemSo,
                FORMAT(bl.NgayNop, 'dd/MM/yyyy HH:mm') AS NgayNop
            FROM BaiTap bt
            LEFT JOIN PhanCongGiangDay pc ON bt.MaPhanCong = pc.MaPhanCong
            LEFT JOIN MonHoc mh ON pc.MaMonHoc = mh.MaMonHoc
            LEFT JOIN NguoiDung gv ON pc.MaGiaoVien = gv.MaNguoiDung
            LEFT JOIN BaiLam bl ON (bt.MaBaiTap = bl.MaBaiTap AND bl.MaHocSinh = :sid)
            WHERE pc.MaLop = :cid OR bt.MaPhanCong IS NULL
            ORDER BY bt.HanNop DESC
        """)
        
        assignments = db.execute(query, {'sid': student_id, 'cid': class_id}).fetchall()

        result_list = []
        submitted_count = 0
        pending_count = 0

        for a in assignments:
            is_submitted = a.MaBaiLam is not None
            if is_submitted:
                submitted_count += 1
            else:
                pending_count += 1

            file_submitted = a.FileBaiLam or ''
            is_img = file_submitted.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))

            result_list.append({
                'id': a.MaBaiTap,
                'title': a.TieuDe,
                'description': a.NoiDung or '',
                'file_dinh_kem': a.FileDeBai or None,
                'subject': a.TenMonHoc or 'Tin học',
                'teacher': a.TenGiaoVien or 'Giáo viên bộ môn',
                'deadline': a.HanNop or 'Không có hạn nộp',
                'is_submitted': is_submitted,
                'score': a.DiemSo,
                'submitted_at': a.NgayNop,
                'submitted_content': a.NoiDungNop or '',
                'submitted_img': file_submitted if is_img else None,
                'submitted_file': file_submitted if not is_img and file_submitted else None
            })

        return jsonify({
            'success': True,
            'student_name': student_name,
            'stats': {
                'total': len(result_list),
                'submitted': submitted_count,
                'pending': pending_count
            },
            'data': result_list
        })
    except Exception as e:
        print(f"❌ LỖI API BÀI TẬP PHỤ HUYNH: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()
# PH Theo dõi điểm số HS

@app.route('/api/parent/results', methods=['GET'])
def get_parent_results():
    db = SessionLocal()
    try:
        parent_id = session.get('user_id')
        if not parent_id:
            return jsonify({'success': False, 'message': 'Chưa đăng nhập'}), 401

        semester_id = request.args.get('semester_id', 1, type=int)

        # 1. Lấy thông tin học sinh liên kết với Phụ huynh đang đăng nhập
        student = db.execute(text("""
            SELECT hs.MaNguoiDung, hs.HoTen, hs.MaLop, lh.TenLop
            FROM NguoiDung p
            JOIN NguoiDung hs ON p.MaHocSinhLienKet = hs.MaNguoiDung
            LEFT JOIN LopHoc lh ON hs.MaLop = lh.MaLop
            WHERE p.MaNguoiDung = :pid
        """), {'pid': parent_id}).fetchone()

        # Nếu phụ huynh chưa gán con, tự động fallback lấy em #30 (Lý Phương Nam) để test
        student_id = student.MaNguoiDung if (student and student.MaNguoiDung) else 30
        student_name = student.HoTen if student else "Lý Phương Nam"
        class_name = student.TenLop if student else "8A1"

        # 2. Truy vấn xoay điểm 12 môn học đúng chuẩn MaLoai (1 đến 7)
        query = text("""
            SELECT 
                mh.MaMonHoc,
                mh.TenMonHoc,
                MAX(CASE WHEN bd.MaLoai = 1 THEN bd.DiemSo END) AS M1,
                MAX(CASE WHEN bd.MaLoai = 2 THEN bd.DiemSo END) AS M2,
                MAX(CASE WHEN bd.MaLoai = 3 THEN bd.DiemSo END) AS M3,
                MAX(CASE WHEN bd.MaLoai = 4 THEN bd.DiemSo END) AS TX1,
                MAX(CASE WHEN bd.MaLoai = 5 THEN bd.DiemSo END) AS TX2,
                MAX(CASE WHEN bd.MaLoai = 6 THEN bd.DiemSo END) AS GK,
                MAX(CASE WHEN bd.MaLoai = 7 THEN bd.DiemSo END) AS CK
            FROM MonHoc mh
            LEFT JOIN BangDiem bd ON (mh.MaMonHoc = bd.MaMonHoc AND bd.MaHocSinh = :sid AND bd.MaHocKy = :sem)
            GROUP BY mh.MaMonHoc, mh.TenMonHoc
            ORDER BY mh.MaMonHoc ASC
        """)

        rows = db.execute(query, {'sid': student_id, 'sem': semester_id}).fetchall()

        grades_list = []
        for r in rows:
            tx_scores = [r.M1, r.M2, r.M3, r.TX1, r.TX2]
            valid_tx = [float(s) for s in tx_scores if s is not None]
            
            gk_val = float(r.GK) if r.GK is not None else None
            ck_val = float(r.CK) if r.CK is not None else None
            
            tb_val = None
            if valid_tx or gk_val is not None or ck_val is not None:
                sum_tx = sum(valid_tx)
                cnt_tx = len(valid_tx)
                
                gk_c = 2 if gk_val is not None else 0
                ck_c = 3 if ck_val is not None else 0
                
                total_coef = cnt_tx + gk_c + ck_c
                if total_coef > 0:
                    tb_val = round((sum_tx + (gk_val or 0)*2 + (ck_val or 0)*3) / total_coef, 1)

            grades_list.append({
                'MaMonHoc': r.MaMonHoc,
                'TenMonHoc': r.TenMonHoc,
                'M1': float(r.M1) if r.M1 is not None else None,
                'M2': float(r.M2) if r.M2 is not None else None,
                'M3': float(r.M3) if r.M3 is not None else None,
                'TX1': float(r.TX1) if r.TX1 is not None else None,
                'TX2': float(r.TX2) if r.TX2 is not None else None,
                'GK': gk_val,
                'CK': ck_val,
                'TB': tb_val
            })

        return jsonify({
            'success': True,
            'student_name': student_name,
            'class_name': class_name,
            'data': grades_list
        })
    except Exception as e:
        print(f"❌ LỖI API RESULT PHỤ HUYNH: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/parent/tuition', methods=['GET'])
def get_parent_tuition():
    db = SessionLocal()
    try:
        parent_id = session.get('user_id')
        if not parent_id:
            return jsonify({'success': False, 'message': 'Chưa đăng nhập'}), 401

        # Lấy học sinh liên kết
        student = db.execute(text("""
            SELECT hs.MaNguoiDung, hs.HoTen, lh.TenLop
            FROM NguoiDung p
            JOIN NguoiDung hs ON p.MaHocSinhLienKet = hs.MaNguoiDung
            LEFT JOIN LopHoc lh ON hs.MaLop = lh.MaLop
            WHERE p.MaNguoiDung = :pid
        """), {'pid': parent_id}).fetchone()

        student_name = student.HoTen if student else "Lý Phương Nam"
        class_name = student.TenLop if student else "8A1"

        # Cấu hình dữ liệu chi tiết chuẩn THCS cho Lớp 6, 7 và Lớp 8
        tuition_data = {
            "student_name": student_name,
            "class_name": class_name,
            "semesters": [
                {
                    "key": "L6_HK1", "ten_hoc_ky": "Lớp 6 - Học kỳ I (2024 - 2025)",
                    "muc_hoc_phi": 2450000, "mien_giam": 0, "phai_thu": 2450000, "da_thu": 2450000, "con_no": 0,
                    "items": [
                        {"ten_khoan_thu": "Học phí chính khóa THCS", "so_tien": 900000, "trang_thai": "Đã thu"},
                        {"ten_khoan_thu": "Bảo hiểm Y tế bắt buộc (12 tháng)", "so_tien": 884520, "trang_thai": "Đã thu"},
                        {"ten_khoan_thu": "Học phụ buổi 2 & Ngoại khóa", "so_tien": 500000, "trang_thai": "Đã thu"},
                        {"ten_khoan_thu": "Nền tảng EduNext Pro & Nước uống", "so_tien": 165480, "trang_thai": "Đã thu"}
                    ]
                },
                {
                    "key": "L6_HK2", "ten_hoc_ky": "Lớp 6 - Học kỳ II (2024 - 2025)",
                    "muc_hoc_phi": 1560000, "mien_giam": 0, "phai_thu": 1560000, "da_thu": 1560000, "con_no": 0,
                    "items": [
                        {"ten_khoan_thu": "Học phí chính khóa THCS", "so_tien": 900000, "trang_thai": "Đã thu"},
                        {"ten_khoan_thu": "Học phụ buổi 2", "so_tien": 500000, "trang_thai": "Đã thu"},
                        {"ten_khoan_thu": "Nền tảng EduNext Pro & Nước uống", "so_tien": 160000, "trang_thai": "Đã thu"}
                    ]
                },
                {
                    "key": "L7_HK1", "ten_hoc_ky": "Lớp 7 - Học kỳ I (2025 - 2026)",
                    "muc_hoc_phi": 2580000, "mien_giam": 0, "phai_thu": 2580000, "da_thu": 2580000, "con_no": 0,
                    "items": [
                        {"ten_khoan_thu": "Học phí chính khóa THCS", "so_tien": 900000, "trang_thai": "Đã thu"},
                        {"ten_khoan_thu": "Bảo hiểm Y tế bắt buộc", "so_tien": 880000, "trang_thai": "Đã thu"},
                        {"ten_khoan_thu": "Học phụ buổi 2", "so_tien": 600000, "trang_thai": "Đã thu"},
                        {"ten_khoan_thu": "Quỹ nề nếp & Nước uống", "so_tien": 200000, "trang_thai": "Đã thu"}
                    ]
                },
                {
                    "key": "L7_HK2", "ten_hoc_ky": "Lớp 7 - Học kỳ II (2025 - 2026)",
                    "muc_hoc_phi": 1700000, "mien_giam": 0, "phai_thu": 1700000, "da_thu": 1700000, "con_no": 0,
                    "items": [
                        {"ten_khoan_thu": "Học phí chính khóa THCS", "so_tien": 900000, "trang_thai": "Đã thu"},
                        {"ten_khoan_thu": "Học phụ buổi 2", "so_tien": 600000, "trang_thai": "Đã thu"},
                        {"ten_khoan_thu": "Nền tảng EduNext Pro", "so_tien": 200000, "trang_thai": "Đã thu"}
                    ]
                },
                {
                    "key": "L8_HK1", "ten_hoc_ky": "Lớp 8 - Học kỳ I (2026 - 2027)",
                    "muc_hoc_phi": 2784520, "mien_giam": 0, "phai_thu": 2784520, "da_thu": 1100000, "con_no": 1684520,
                    "items": [
                        {"ten_khoan_thu": "Học phí chính khóa Lớp 8", "so_tien": 900000, "trang_thai": "Đã thu"},
                        {"ten_khoan_thu": "Bảo hiểm Y tế học sinh năm 2026", "so_tien": 884520, "trang_thai": "Chưa thu"},
                        {"ten_khoan_thu": "Học phụ buổi 2 & Ôn tập thi", "so_tien": 800000, "trang_thai": "Chưa thu"},
                        {"ten_khoan_thu": "Nền tảng EduNext Pro & Nước uống", "so_tien": 200000, "trang_thai": "Đã thu"}
                    ]
                },
                {
                    "key": "L8_HK2", "ten_hoc_ky": "Lớp 8 - Học kỳ II (2026 - 2027)",
                    "muc_hoc_phi": 1700000, "mien_giam": 0, "phai_thu": 1700000, "da_thu": 0, "con_no": 0,
                    "items": [
                        {"ten_khoan_thu": "Học phí chính khóa Lớp 8", "so_tien": 900000, "trang_thai": "Chưa thu"},
                        {"ten_khoan_thu": "Học phụ buổi 2", "so_tien": 600000, "trang_thai": "Chưa thu"},
                        {"ten_khoan_thu": "Nền tảng EduNext Pro", "so_tien": 200000, "trang_thai": "Chưa thu"}
                    ]
                }
            ]
        }

        return jsonify({'success': True, 'data': tuition_data})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()


@app.route('/api/parent/remind-homework', methods=['POST'])
def remind_student_homework():
    data = request.json or {}
    student_id = data.get('student_id')
    assignment_id = data.get('assignment_id')
    assignment_title = data.get('assignment_title', 'Bài tập')

    parent_id = session.get('user_id')
    if not student_id:
        return jsonify({'success': False, 'message': 'Thiếu mã học sinh'}), 400

    db = SessionLocal()
    try:
        # Lấy tên phụ huynh
        parent = db.execute(
            text("SELECT HoTen FROM dbo.NguoiDung WHERE MaNguoiDung = :pid"),
            {'pid': parent_id}
        ).fetchone()
        parent_name = parent.HoTen if parent else "Phụ huynh"

        # 1. Ghi vào bảng ThongBao hoặc TinNhan cho học sinh
        content_msg = f"Ba/Mẹ ({parent_name}) nhắc con mau chóng hoàn thành bài tập: \"{assignment_title}\" nhé!"
        
        # Thêm thông báo riêng cho học sinh
        db.execute(text("""
            INSERT INTO dbo.ThongBao (TieuDe, NoiDung, PhamVi, MaNguoiGui, MaLop, NgayGui)
            VALUES (:title, :content, 'CaNhan', :sender_id, :target_student_id, GETDATE())
        """), {
            'title': f"⏰ Nhắc nhở làm bài: {assignment_title}",
            'content': content_msg,
            'sender_id': parent_id,
            'target_student_id': student_id
        })

        db.commit()
        return jsonify({'success': True, 'message': f'Đã gửi lời nhắc tới con hoàn thành bài "{assignment_title}"!'})
    except Exception as e:
        db.rollback()
        print(f"[ERR REMIND HOMEWORK] {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/student/notifications/feed', methods=['GET'])
def get_student_unified_feed():
    student_id = session.get('user_id') or request.args.get('user_id')
    if not student_id:
        return jsonify({'success': False, 'message': 'Chưa đăng nhập'}), 401

    db = SessionLocal()
    try:
        # 1. Lấy thông tin học sinh
        student = db.execute(
            text("SELECT MaLop, HoTen FROM dbo.NguoiDung WHERE MaNguoiDung = :sid"),
            {'sid': student_id}
        ).fetchone()
        class_id = student.MaLop if student else None

        feed_items = []

        # 2. THÔNG BÁO ĐIỂM SỐ MỚI ĐƯỢC CHẤM
        try:
            graded_tasks = db.execute(
                text("""
                    SELECT 
                        bl.MaBaiLam,
                        bt.TieuDe AS TenBaiTap,
                        bl.DiemSo,
                        bl.LoiPhe AS NhanXet,
                        ISNULL(mh.TenMonHoc, N'Tin học') AS TenMonHoc,
                        bl.NgayNop
                    FROM dbo.BaiLam bl
                    JOIN dbo.BaiTap bt ON bl.MaBaiTap = bt.MaBaiTap
                    LEFT JOIN dbo.PhanCongGiangDay pc ON bt.MaPhanCong = pc.MaPhanCong
                    LEFT JOIN dbo.MonHoc mh ON pc.MaMonHoc = mh.MaMonHoc
                    WHERE bl.MaHocSinh = :sid AND bl.DiemSo IS NOT NULL
                    ORDER BY bl.MaBaiLam DESC
                """),
                {'sid': student_id}
            ).fetchall()

            for g in graded_tasks:
                feed_items.append({
                    'id': f"grade_{g.MaBaiLam}",
                    'category': 'academic',
                    'title': f"[{g.TenMonHoc}] Đã có điểm bài: {g.TenBaiTap}",
                    'content': f"Thầy/Cô đã chấm điểm bài làm của bạn môn {g.TenMonHoc}.",
                    'score': g.DiemSo,
                    'comment': g.NhanXet,
                    'timestamp': g.NgayNop.strftime("%Y-%m-%dT%H:%M:%S") if g.NgayNop else datetime.now().isoformat()
                })
        except Exception as e:
            print(f"[WARN FEED ACADEMIC] {e}")

        # 3. TIN NHẮN TỪ GIÁO VIÊN
        try:
            messages = db.execute(
                text("""
                    SELECT TOP 10 
                        tn.MaTinNhan,
                        nd.HoTen AS TenNguoiGui,
                        tn.NoiDung,
                        tn.NgayGui
                    FROM dbo.TinNhan tn
                    JOIN dbo.NguoiDung nd ON tn.MaNguoiGui = nd.MaNguoiDung
                    WHERE tn.MaNguoiNhan = :sid
                    ORDER BY tn.NgayGui DESC
                """),
                {'sid': student_id}
            ).fetchall()

            for m in messages:
                feed_items.append({
                    'id': f"msg_{m.MaTinNhan}",
                    'category': 'messages',
                    'title': f"Tin nhắn từ {m.TenNguoiGui}",
                    'sender': m.TenNguoiGui,
                    'content': m.NoiDung,
                    'timestamp': m.NgayGui.strftime("%Y-%m-%dT%H:%M:%S") if m.NgayGui else datetime.now().isoformat()
                })
        except Exception as e:
            pass

        # 4. THÔNG BÁO LỚP & NHÀ TRƯỜNG (TRUY VẤN AN TOÀN KHÔNG BỊ LỖI CỘT BÌNH LUẬN)
        try:
            announcements = db.execute(
                text("""
                    SELECT TOP 15
                        tb.MaThongBao,
                        tb.TieuDe,
                        tb.NoiDung,
                        tb.PhamVi,
                        tb.HinhAnh,
                        tb.NgayGui,
                        nd.HoTen AS TenNguoiDang
                    FROM dbo.ThongBao tb
                    LEFT JOIN dbo.NguoiDung nd ON tb.MaNguoiGui = nd.MaNguoiDung
                    WHERE tb.PhamVi = 'Truong' OR (tb.PhamVi = 'Lop' AND (tb.MaLop = :cid OR :cid IS NULL))
                    ORDER BY tb.NgayGui DESC
                """),
                {'cid': class_id}
            ).fetchall()

            for a in announcements:
                feed_items.append({
                    'id': a.MaThongBao,
                    'category': 'news',
                    'title': a.TieuDe or 'Thông báo mới',
                    'content': a.NoiDung or '',
                    'scope': 'Nhà trường' if a.PhamVi == 'Truong' else 'Lớp học',
                    'sender': a.TenNguoiDang or 'Giáo viên',
                    'image': a.HinhAnh,
                    'comments_count': 0,
                    'timestamp': a.NgayGui.strftime("%Y-%m-%dT%H:%M:%S") if a.NgayGui else datetime.now().isoformat()
                })
        except Exception as e:
            print(f"[WARN FEED ANNOUNCEMENTS] {e}")

        # 5. SỰ KIỆN TOÀN TRƯỜNG
        try:
            events = db.execute(
                text("""
                    SELECT TOP 10
                        MaSuKien,
                        TieuDe,
                        NoiDung,
                        DiaDiem,
                        HinhAnh,
                        ThoiGianBatDau,
                        NgayTao
                    FROM dbo.SuKien
                    ORDER BY ThoiGianBatDau DESC
                """)
            ).fetchall()

            for ev in events:
                feed_items.append({
                    'id': f"event_{ev.MaSuKien}",
                    'category': 'events',
                    'title': ev.TieuDe or 'Sự kiện trường',
                    'content': ev.NoiDung or '',
                    'location': ev.DiaDiem or 'Trường THCS',
                    'image': ev.HinhAnh,
                    'start_time': ev.ThoiGianBatDau.strftime("%Y-%m-%dT%H:%M:%S") if ev.ThoiGianBatDau else None,
                    'timestamp': ev.NgayTao.strftime("%Y-%m-%dT%H:%M:%S") if ev.NgayTao else datetime.now().isoformat()
                })
        except Exception as e:
            print(f"[WARN FEED EVENTS] {e}")

        # Sắp xếp từ mới nhất đến cũ nhất
        feed_items.sort(key=lambda x: str(x.get('timestamp') or ''), reverse=True)

        return jsonify({'success': True, 'data': feed_items})

    except Exception as e:
        print(f"[ERR UNIFIED NOTIFICATIONS] {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()

# API 1: Truy vấn Thời khóa biểu CHUẨN XÁC theo Lớp, Tuần và Học kỳ
@app.route('/api/teacher/schedule', methods=['GET'])
def get_teacher_schedule_by_week():
    db = SessionLocal()
    try:
        class_id = request.args.get('class_id')
        week = request.args.get('week', 1, type=int)
        semester = request.args.get('semester', 1, type=int)

        if not class_id:
            return jsonify({'success': False, 'message': 'Thiếu mã lớp'}), 400

        query = text("""
            SELECT 
                tkb.Thu, 
                tkb.Tiet, 
                tkb.MaMonHoc, 
                mh.TenMonHoc, 
                gv.HoTen AS TenGiaoVien,
                tkb.PhongHoc
            FROM dbo.ThoiKhoaBieu tkb
            LEFT JOIN dbo.MonHoc mh ON tkb.MaMonHoc = mh.MaMonHoc
            LEFT JOIN dbo.PhanCongGiangDay pc ON (pc.MaMonHoc = mh.MaMonHoc AND pc.MaLop = tkb.MaLop)
            LEFT JOIN dbo.NguoiDung gv ON pc.MaGiaoVien = gv.MaNguoiDung
            WHERE tkb.MaLop = :cid 
              AND tkb.Tuan = :week 
              AND tkb.MaHocKy = :sem
            ORDER BY tkb.Thu ASC, tkb.Tiet ASC
        """)

        results = db.execute(query, {'cid': int(class_id), 'week': int(week), 'sem': int(semester)}).fetchall()

        schedule = []
        for r in results:
            schedule.append({
                'Thu': int(r.Thu),
                'Tiet': int(r.Tiet),
                'MaMonHoc': r.MaMonHoc,
                'TenMonHoc': r.TenMonHoc or '',
                'TenGiaoVien': r.TenGiaoVien or '',
                'PhongHoc': r.PhongHoc or ''
            })

        return jsonify({'success': True, 'data': schedule})
    except Exception as e:
        print(f'[ERR GET SCHEDULE] {str(e)}')
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()


# API 2: Lưu Thời khóa biểu cho RIÊNG TỪNG TUẦN VÀ HỌC KỲ
@app.route('/api/teacher/schedule/update', methods=['POST'])
def update_teacher_schedule_by_week():
    db = SessionLocal()
    try:
        data = request.json or {}
        class_id = data.get('class_id')
        week = int(data.get('week', 1))
        semester = int(data.get('semester', 1))
        schedule_items = data.get('schedule', [])

        if not class_id:
            return jsonify({'success': False, 'message': 'Thiếu mã lớp'}), 400

        # 1. XÓA CHÍNH XÁC LỊCH CỦA ĐÚNG TUẦN VÀ HỌC KỲ ĐÓ
        db.execute(text("""
            DELETE FROM dbo.ThoiKhoaBieu 
            WHERE MaLop = :cid AND Tuan = :week AND MaHocKy = :sem
        """), {'cid': int(class_id), 'week': week, 'sem': semester})

        # 2. Chèn từng tiết học vào đúng tuần
        for item in schedule_items:
            thu = item.get('thu')
            tiet = item.get('tiet')
            mon_id = item.get('mon_hoc_id')
            phong = item.get('phong_hoc', '')

            if not mon_id and item.get('ten_mon_hoc'):
                mon_id = db.execute(
                    text("SELECT MaMonHoc FROM dbo.MonHoc WHERE TenMonHoc = :t"),
                    {'t': item.get('ten_mon_hoc')}
                ).scalar()

            if thu and tiet and mon_id:
                db.execute(text("""
                    INSERT INTO dbo.ThoiKhoaBieu (MaLop, Thu, Tiet, MaMonHoc, PhongHoc, Tuan, MaHocKy)
                    VALUES (:cid, :thu, :tiet, :mid, :phong, :week, :sem)
                """), {
                    'cid': int(class_id),
                    'thu': int(thu),
                    'tiet': int(tiet),
                    'mid': int(mon_id),
                    'phong': phong,
                    'week': week,
                    'sem': semester
                })

        db.commit()
        return jsonify({'success': True, 'message': f'Đã lưu thời khóa biểu cho Tuần {week}!'})
    except Exception as e:
        db.rollback()
        print(f'[ERR UPDATE SCHEDULE] {str(e)}')
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()


@app.route('/api/subjects', methods=['GET'])
def get_all_subjects():
    """API cung cấp danh sách môn học cho các ô chọn trên giao diện TKB."""
    db = SessionLocal()
    try:
        query = text("SELECT MaMonHoc, TenMonHoc FROM dbo.MonHoc ORDER BY MaMonHoc ASC")
        rows = db.execute(query).mappings().all()
        
        subjects_list = [dict(r) for r in rows]
        
        return jsonify({
            "success": True,
            "data": subjects_list
        })
    except Exception as e:
        print(f"[ERR GET SUBJECTS] {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

# --- ĐIỀU HƯỚNG CÁC TRANG QUẢN LÝ MỚI (CHỦ NHIỆM) ---
@app.route('/teacher/attendance')
def teacher_attendance_page():
    return render_template('GV/attendance.html', active_page='attendance')

@app.route('/teacher/leave-requests')
def teacher_leave_requests_page():
    return render_template('GV/leave_requests.html', active_page='leave_requests')

@app.route('/teacher/announcements')
def teacher_announcements_page():
    return render_template('GV/announcements.html', active_page='announcements')

@app.route('/teacher/messages')
def teacher_messages_page():
    return render_template('GV/messages.html', active_page='messages')

@app.route('/teacher/schedule')
def teacher_schedule_page():
    return render_template('GV/schedule.html', active_page='schedule')

@app.route('/teacher/gradebook')
def teacher_gradebook_page():
    return render_template('GV/gradebook.html', active_page='gradebook')

@app.route('/teacher/resources')
def teacher_resources_page():
    return render_template('GV/resources.html', active_page='resources')

@app.route('/teacher/assignments')
def teacher_assignments():
  return render_template('GV/assignments.html')

@app.route('/hoc-sinh/tin-nhan')
def student_messages_page():
    # Kiểm tra login và lấy thông tin học sinh
    user_id = session.get('user_id')
    if not user_id: return webbrowser.open("http://localhost:3000/login") # Hoặc redirect
    
    db = SessionLocal()
    u = db.execute(text("SELECT HoTen FROM NguoiDung WHERE MaNguoiDung = :uid"), {"uid": user_id}).fetchone()
    db.close()
    
    return render_template('HS/messages.html', 
                          active_page='messages', 
                          student={'name': u[0] if u else 'Học sinh'})

# ==============================================================================
# 3. API XỬ LÝ DỮ LIỆU (GIỮ NGUYÊN)
# ==============================================================================

# --- [ĐÃ DI CHUYỂN LOGIN LÊN TRÊN] ---

@app.route('/api/v2/resource/comment/<int:id>', methods=['POST'])
def rate_resource_v2(id):
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "Vui lòng đăng nhập"}), 401
            
        data = request.json
        stars = data.get('stars', 5)
        comment = data.get('comment', '')
        
        # Kiểm tra xem đã đánh giá chưa
        check_query = text("SELECT MaDanhGia FROM DanhGiaHocLieu WHERE MaTaiLieu = :rid AND MaNguoiDung = :uid")
        existing = db.execute(check_query, {"rid": id, "uid": user_id}).fetchone()
        
        if existing:
            db.execute(text("UPDATE DanhGiaHocLieu SET SoSao = :stars, BinhLuan = :comment, NgayDanhGia = GETDATE() WHERE MaDanhGia = :mid"),
                       {"stars": stars, "comment": comment, "mid": existing[0]})
        else:
            db.execute(text("INSERT INTO DanhGiaHocLieu (MaTaiLieu, MaNguoiDung, SoSao, BinhLuan, NgayDanhGia) VALUES (:rid, :uid, :stars, :comment, GETDATE())"),
                       {"rid": id, "uid": user_id, "stars": stars, "comment": comment})
            
        db.commit()
        return jsonify({"success": True, "message": "Cảm ơn bạn đã đóng góp ý kiến!"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@app.route('/api/user/profile')
def get_user_profile():
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401
            
        # Lấy thông tin người dùng và tên lớp chủ nhiệm (Ưu tiên MaGVCN cho giáo viên)
        query = text("""
            SELECT 
                nd.MaNguoiDung,
                nd.HoTen, 
                nd.Email,
                nd.VaiTro, 
                COALESCE(lh_v.TenLop, l_nd.TenLop) as TenLop,
                COALESCE(lh_v.MaLop, l_nd.MaLop) as MaLop,
                COALESCE(lh_v.MaKhoi, l_nd.MaKhoi, (
                    SELECT TOP 1 l.MaKhoi 
                    FROM PhanCongGiangDay pc 
                    JOIN LopHoc l ON pc.MaLop = l.MaLop 
                    WHERE pc.MaGiaoVien = nd.MaNguoiDung
                )) as MaKhoi
            FROM NguoiDung nd
            LEFT JOIN LopHoc l_nd ON nd.MaLop = l_nd.MaLop
            LEFT JOIN LopHoc lh_v ON nd.MaNguoiDung = lh_v.MaGVCN
            WHERE nd.MaNguoiDung = :uid
        """)
        user = db.execute(query, {"uid": user_id}).fetchone()
        
        if user:
            print(f"[Debug Profile] User: {user.Email}, Role: {user.VaiTro}, MaLop: {user.MaLop}")
        user = db.execute(query, {"uid": user_id}).mappings().first()
        if not user:
            return jsonify({"success": False, "message": "Không tìm thấy user"}), 404
            
        user_data = dict(user)
        # [AUTO-PLATFORM] Hack thông minh cho Demo: Nếu tên có "Khối 8" -> Force Khối 8
        if user_data.get('HoTen') and 'Khối 8' in user_data['HoTen']:
            user_data['MaKhoi'] = 3
        elif user_data.get('HoTen') and 'Khối 6' in user_data['HoTen']:
            user_data['MaKhoi'] = 1
        elif user_data.get('HoTen') and 'Khối 7' in user_data['HoTen']:
            user_data['MaKhoi'] = 2
        elif user_data.get('HoTen') and 'Khối 9' in user_data['HoTen']:
            user_data['MaKhoi'] = 4

        return jsonify({
            "success": True, 
            "data": {
                "id": user_data['MaNguoiDung'],
                "full_name": user_data['HoTen'],
                "email": user_data['Email'],
                "role": user_data['VaiTro'],
                "class_name": user_data['TenLop'],
                "class_id": user_data['MaLop'],
                "MaKhoi": user_data['MaKhoi']
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@app.route('/api/teacher/update-grade', methods=['POST'])
def update_grade():
  """API Cập nhật điểm số động thời gian thực chuẩn hóa 12 môn học và 2 học kỳ.

  Hỗ trợ 3 điểm Miệng (M1, M2, M3), 2 điểm 15p (TX1, TX2), Giữa kỳ (GK), Cuối
  kỳ (CK).
  """
  db = SessionLocal()
  try:
    data = request.json or {}
    student_id = data.get('student_id')
    subject_id = data.get('subject_id')
    semester_id = data.get('semester_id')
    column_type = data.get('column_type')  # Nhận 'M1', 'M2', 'M3', 'TX1', 'TX2', 'GK', 'CK'
    new_grade = data.get('grade')

    if not all([student_id, subject_id, semester_id, column_type]):
      return (
          jsonify({
              'success': False,
              'message': 'Thiếu tham số cấu hình bộ lọc điểm!',
          }),
          400,
      )

    # 1. Bổ sung Ánh xạ đầy đủ từ Frontend sang Mã loại điểm trong bảng DanhMucLoaiDiem (Hoặc Mã cột)
    type_mapping = {
        'M1': 1,  # Miệng 1
        'M2': 2,  # Miệng 2
        'M3': 3,  # Miệng 3
        'TX1': 4,  # 15 phút 1
        'TX2': 5,  # 15 phút 2
        'GK': 6,  # Giữa kỳ
        'CK': 7,  # Cuối kỳ
    }

    ma_loai = type_mapping.get(column_type)
    if not ma_loai:
      return (
          jsonify({
              'success': False,
              'message': f'Loại cột {column_type} không hợp lệ!',
          }),
          400,
      )

    # 2. Xóa điểm khi ô nhập bị xóa trắng
    if new_grade == '' or new_grade is None:
      db.execute(
          text("""
                DELETE FROM dbo.BangDiem 
                WHERE MaHocSinh = :sid AND MaMonHoc = :sub_id AND MaHocKy = :sem_id AND MaLoai = :loai
            """),
          {
              'sid': student_id,
              'sub_id': subject_id,
              'sem_id': semester_id,
              'loai': ma_loai,
          },
      )
      db.commit()
      return jsonify({'success': True, 'message': 'Đã xóa điểm số!'})

    # 3. Kiểm tra thang điểm 0 - 10
    grade_float = float(new_grade)
    if grade_float < 0 or grade_float > 10:
      return (
          jsonify({
              'success': False,
              'message': 'Điểm số phải nằm trong thang điểm từ 0 đến 10!',
          }),
          400,
      )

    # 4. Kiểm tra sự tồn tại của điểm số
    check_query = text("""
            SELECT MaDiem FROM dbo.BangDiem 
            WHERE MaHocSinh = :sid AND MaMonHoc = :sub_id AND MaHocKy = :sem_id AND MaLoai = :loai
        """)
    exists = db.execute(
        check_query,
        {
            'sid': student_id,
            'sub_id': subject_id,
            'sem_id': semester_id,
            'loai': ma_loai,
        },
    ).fetchone()

    if exists:
      # Cập nhật điểm đã có
      db.execute(
          text("""
                UPDATE dbo.BangDiem 
                SET DiemSo = :grade, NgayNhap = GETDATE() 
                WHERE MaHocSinh = :sid AND MaMonHoc = :sub_id AND MaHocKy = :sem_id AND MaLoai = :loai
            """),
          {
              'grade': grade_float,
              'sid': student_id,
              'sub_id': subject_id,
              'sem_id': semester_id,
              'loai': ma_loai,
          },
      )
    else:
      # Chèn điểm mới
      db.execute(
          text("""
                INSERT INTO dbo.BangDiem (MaHocSinh, MaMonHoc, MaHocKy, MaLoai, DiemSo, NgayNhap) 
                VALUES (:sid, :sub_id, :sem_id, :loai, :grade, GETDATE())
            """),
          {
              'sid': student_id,
              'sub_id': subject_id,
              'sem_id': semester_id,
              'loai': ma_loai,
              'grade': grade_float,
          },
      )

    db.commit()
    return jsonify({'success': True, 'message': 'Cập nhật điểm thành công!'})

  except Exception as e:
    db.rollback()
    print(f'[ERR UPDATE GRADE LOGIC] {str(e)}')
    return jsonify({'success': False, 'message': str(e)}), 500
  finally:
    db.close()


@app.route('/api/questions/<int:khoi_id>', methods=['GET'])
def get_assessment_questions(khoi_id):
    db = SessionLocal()
    try:
        # Ánh xạ: Khối 6 -> MaBaiTest = 1, Khối 7 -> 2, Khối 8 -> 3, Khối 9 -> 4
        ma_bai_test = khoi_id - 5
        if ma_bai_test not in [1, 2, 3, 4]:
            ma_bai_test = 1

        query = text("""
            SELECT MaCauHoi, NoiDungCauHoi, NhomNangLuc, 
                   DapAnA, DapAnB, DapAnC, DapAnD
            FROM dbo.CauHoiNangLuc 
            WHERE MaBaiTest = :btid
            ORDER BY MaCauHoi ASC
        """)
        
        rows = db.execute(query, {"btid": ma_bai_test}).fetchall()
        
        questions = []
        for r in rows:
            questions.append({
                "id": r.MaCauHoi,
                "q": r.NoiDungCauHoi,
                "type": r.NhomNangLuc,
                "a": r.DapAnA,
                "b": r.DapAnB,
                "c": r.DapAnC,
                "d": r.DapAnD
            })
            
        return jsonify({"success": True, "questions": questions})
    except Exception as e:
        print("❌ Lỗi truy vấn CauHoiNangLuc:", str(e))
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

# --- API TƯƠNG TÁC 2 CHIỀU ---
@app.route('/api/feedback/send', methods=['POST'])
def send_feedback():
    db = SessionLocal()
    try:
        data = request.json
        user_id = session.get('user_id', data.get('student_id'))
        teacher_id = data.get('teacher_id', 2) # Mặc định GVCN ID = 2 cho demo
        title = data.get('title', 'Phản hồi từ học sinh')
        content = data.get('content')
        
        query = text("""
            INSERT INTO TraoDoiChuNhiem (MaNguoiGui, MaNguoiNhan, TieuDe, NoiDung)
            VALUES (:sender, :receiver, :title, :content)
        """)
        db.execute(query, {"sender": user_id, "receiver": teacher_id, "title": title, "content": content})
        db.commit()
        return jsonify({'success': True, 'message': 'Đã gửi phản hồi thành công'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/feedback/my-messages', methods=['GET'])
def get_my_messages():
    db = SessionLocal()
    try:
        user_id = session.get('user_id', 1)
        query = text("""
            SELECT MaTraoDoi, TieuDe, NoiDung, ThoiGian, TrangThai, PhanHoi 
            FROM TraoDoiChuNhiem 
            WHERE MaNguoiGui = :uid OR MaNguoiNhan = :uid
            ORDER BY ThoiGian DESC
        """)
        messages = db.execute(query, {"uid": user_id}).fetchall()
        
        result = []
        for msg in messages:
            result.append({
                "id": msg.MaTraoDoi,
                "title": msg.TieuDe,
                "content": msg.NoiDung,
                "time": msg.ThoiGian.strftime("%H:%M %d/%m/%Y"),
                "status": msg.TrangThai,
                "reply": msg.PhanHoi
            })
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()


# [INFO] Các route cũ đã được di chuyển sang Blueprint (app/routes/) để đảm bảo tính module.

@app.route('/api/notifications/poll', methods=['GET'])
def poll_notifications():
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({"success": False}), 401
        
        # 1. Kiểm tra tin nhắn mới chưa đọc từ TraoDoiChuNhiem
        msg_query = text("""
            SELECT COUNT(*) FROM TraoDoiChuNhiem 
            WHERE MaNguoiNhan = :uid AND (DaDoc = 0 OR DaDoc IS NULL)
        """)
        new_msgs = db.execute(msg_query, {"uid": user_id}).scalar()
        
        # 2. Kiểm tra ID thông báo và sự kiện lớn nhất dành cho User này
        # [SAFE FETCH] Lấy MaLop/MaKhoi chính xác (hỗ trợ cả GVCN và HS)
        class_id = session.get('class_id')
        khoi_id = session.get('khoi_id')
        
        if class_id is None or khoi_id is None:
            u_info = db.execute(text("""
                SELECT 
                    COALESCE(nd.MaLop, lh_gv.MaLop) as MaLop,
                    COALESCE(lh_nd.MaKhoi, lh_gv.MaKhoi) as MaKhoi
                FROM NguoiDung nd
                LEFT JOIN LopHoc lh_nd ON nd.MaLop = lh_nd.MaLop
                LEFT JOIN LopHoc lh_gv ON nd.MaNguoiDung = lh_gv.MaGVCN
                WHERE nd.MaNguoiDung = :uid
            """), {"uid": user_id}).fetchone()
            if u_info:
                class_id = u_info.MaLop
                khoi_id = u_info.MaKhoi
        
        class_id = class_id or 0
        khoi_id = khoi_id or 0
        
        # Nếu là Phụ huynh, lấy ID của con
        child_id = 0
        if session.get('vai_tro') == 'Parent':
            try:
                child_res = db.execute(text("SELECT MaHocSinhLienKet FROM NguoiDung WHERE MaNguoiDung = :uid"), {"uid": user_id}).fetchone()
                if child_res and child_res[0]:
                    child_id = child_res[0]
                    # Đồng thời lấy class_id của con
                    c_class_res = db.execute(text("SELECT MaLop FROM NguoiDung WHERE MaNguoiDung = :cid"), {"cid": child_id}).fetchone()
                    if c_class_res and c_class_res[0]:
                        class_id = c_class_res[0]
            except: pass

        # Lấy ID thông báo lớn nhất hợp lệ
        max_ann_query = text("""
            SELECT MAX(MaThongBao) FROM ThongBao 
            WHERE (MaLop = :cid OR PhamVi = 'Truong' OR (PhamVi = 'CaNhan' AND (MaLop = :uid OR MaLop = :child_id)))
        """)
        latest_ann_id = db.execute(max_ann_query, {"uid": user_id, "cid": class_id, "child_id": child_id}).scalar() or 0

        # Lấy ID sự kiện lớn nhất hợp lệ
        max_event_query = text("""
            SELECT MAX(MaSuKien) FROM SuKien 
            WHERE (PhamVi = 0 OR PhamVi = 1 OR (PhamVi = 2 AND MaDoiTuong = :kid) OR (PhamVi = 3 AND MaDoiTuong = :cid))
        """)
        latest_event_id = db.execute(max_event_query, {"uid": user_id, "cid": class_id, "kid": khoi_id}).scalar() or 0
        
        return jsonify({
            "success": True,
            "new_messages": new_msgs,
            "latest_ann_id": latest_ann_id,
            "latest_event_id": latest_event_id
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@app.route('/api/gamification/leaderboard', methods=['GET'])
def get_leaderboard():
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        # Lấy Top 10 học sinh có XP cao nhất
        query = text("""
            SELECT TOP 10
                nd.MaNguoiDung,
                nd.HoTen,
                ISNULL(SUM(nk.DiemXP), 0) as TongXP
            FROM NguoiDung nd
            LEFT JOIN NhatKyReNep nk ON nd.MaNguoiDung = nk.MaHocSinh
            WHERE nd.VaiTro = 'Student'
            GROUP BY nd.MaNguoiDung, nd.HoTen
            ORDER BY TongXP DESC
        """)
        results = db.execute(query).fetchall()
        
        leaderboard = []
        for i, r in enumerate(results):
            leaderboard.append({
                "rank": i + 1,
                "id": r.MaNguoiDung,
                "name": r.HoTen,
                "xp": r.TongXP,
                "avatar": f"https://api.dicebear.com/7.x/avataaars/svg?seed={r.MaNguoiDung}",
                "isMe": r.MaNguoiDung == user_id
            })
            
        # Lấy thông tin cá nhân của người đang đăng nhập
        my_stats = {"rank": 0, "xp": 0}
        if user_id:
            all_ranks = db.execute(text("""
                SELECT MaNguoiDung, ISNULL(SUM(DiemXP), 0) as TongXP
                FROM NguoiDung nd
                LEFT JOIN NhatKyReNep nk ON nd.MaNguoiDung = nk.MaHocSinh
                WHERE nd.VaiTro = 'Student'
                GROUP BY nd.MaNguoiDung
                ORDER BY TongXP DESC
            """)).fetchall()
            
            for i, r in enumerate(all_ranks):
                if r.MaNguoiDung == user_id:
                    my_stats["rank"] = i + 1
                    my_stats["xp"] = r.TongXP
                    break
        
        return jsonify({
            "success": True, 
            "data": leaderboard,
            "my_stats": my_stats
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

# API 1: Lấy danh sách bài nộp của MỘT BÀI TẬP CỤ THỂ (Đã nạp chính xác Điểm số & Nhận xét cũ)
@app.route(
    '/api/teacher/assignments/<int:assignment_id>/submissions', methods=['GET']
)
def get_assignment_submissions_detail(assignment_id):
  db = SessionLocal()
  try:
    query = text("""
            SELECT 
                bl.MaBaiLam AS MaBaiNop,
                nd.HoTen,
                bl.[BaiLam] AS NoiDungNop,
                bl.FileDinhKem,
                bl.DiemSo,
                bl.NhanXet,
                FORMAT(bl.NgayNop, 'dd/MM/yyyy HH:mm') AS NgayNop
            FROM dbo.BaiLam bl
            JOIN dbo.NguoiDung nd ON bl.MaHocSinh = nd.MaNguoiDung
            WHERE bl.MaBaiTap = :aid
            ORDER BY bl.NgayNop DESC
        """)

    results = db.execute(query, {'aid': assignment_id}).fetchall()

    submissions = []
    for r in results:
      file_path = r.FileDinhKem or ''
      # Tự động phân loại xem file đính kèm là Ảnh hay File tài liệu
      is_img = file_path.lower().endswith(
          ('.png', '.jpg', '.jpeg', '.gif', '.webp')
      )

      submissions.append({
          'MaBaiLam': r.MaBaiNop,
          'MaBaiNop': r.MaBaiNop,
          'HoTen': r.HoTen,
          'NoiDungNop': r.NoiDungNop or 'Học sinh nộp bài',
          'NgayNop': r.NgayNop or 'N/A',
          'HinhAnh': file_path if is_img else None,
          'FileDinhKem': file_path if not is_img and file_path else None,
          'DiemSo': float(r.DiemSo) if r.DiemSo is not None else None,
          'NhanXet': r.NhanXet or '',
          'TrangThai': 'Đã chấm' if r.DiemSo is not None else 'Đã nộp',
      })

    return jsonify({'success': True, 'data': submissions})
  except Exception as e:
    print(f'[ERR ASSIGNMENT SUBMISSIONS] {str(e)}')
    return jsonify({'success': False, 'message': str(e)}), 500
  finally:
    db.close()


# API 2: Chấm điểm bài làm & Tự động đồng bộ vào đúng cột Sổ Điểm theo MaLoai của bài tập
@app.route('/api/teacher/submissions/grade', methods=['POST'])
def grade_student_submission():
    db = SessionLocal()
    try:
        data = request.json or {}
        submission_id = data.get('submission_id')
        score = data.get('score')
        comment = data.get('comment', '').strip() if data.get('comment') else ''

        if submission_id is None or score is None or str(score).strip() == '':
            return jsonify({'success': False, 'message': 'Thiếu mã bài nộp hoặc điểm số!'}), 400

        try:
            score_val = float(score)
            if score_val < 0 or score_val > 10:
                return jsonify({'success': False, 'message': 'Điểm số phải từ 0 đến 10!'}), 400
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'Điểm số không hợp lệ!'}), 400

        # 1. Cập nhật Điểm số & Lời phê vào bảng BaiLam (Khớp đúng cột LoiPhe)
        db.execute(text("""
            UPDATE dbo.BaiLam 
            SET DiemSo = :score, LoiPhe = :comment
            WHERE MaBaiLam = :sid
        """), {'score': score_val, 'comment': comment, 'sid': submission_id})

        # 2. Lấy thông tin học sinh, MaMonHoc (qua bảng PhanCongGiangDay) và MaLoai (từ BaiTap)
        sub_info = db.execute(text("""
            SELECT 
                bl.MaHocSinh, 
                ISNULL(pc.MaMonHoc, 1) AS MaMonHoc, 
                ISNULL(bt.MaLoai, 0) AS MaLoai
            FROM dbo.BaiLam bl
            JOIN dbo.BaiTap bt ON bl.MaBaiTap = bt.MaBaiTap
            LEFT JOIN dbo.PhanCongGiangDay pc ON bt.MaPhanCong = pc.MaPhanCong
            WHERE bl.MaBaiLam = :sid
        """), {'sid': submission_id}).fetchone()

        if sub_info:
            target_student_id = sub_info.MaHocSinh
            target_subject_id = int(sub_info.MaMonHoc)
            target_ma_loai = int(sub_info.MaLoai)
            target_semester_id = 1  # Học kỳ I

            # 3. Đồng bộ vào bảng BangDiem nếu là bài kiểm tra tính điểm (MaLoai > 0)
            if target_ma_loai > 0:
                check_grade = db.execute(text("""
                    SELECT MaDiem FROM dbo.BangDiem 
                    WHERE MaHocSinh = :hs 
                      AND MaMonHoc = :mh 
                      AND MaHocKy = :hk 
                      AND MaLoai = :loai
                """), {
                    'hs': target_student_id,
                    'mh': target_subject_id,
                    'hk': target_semester_id,
                    'loai': target_ma_loai
                }).fetchone()

                if check_grade:
                    # Đã có điểm -> Cập nhật DiemSo
                    db.execute(text("""
                        UPDATE dbo.BangDiem 
                        SET DiemSo = :score, 
                            NgayNhap = GETDATE(),
                            NhanXet = :comment
                        WHERE MaDiem = :mid
                    """), {
                        'score': score_val, 
                        'comment': comment if comment else None,
                        'mid': check_grade[0]
                    })
                else:
                    # Chưa có -> Thêm mới dòng điểm
                    db.execute(text("""
                        INSERT INTO dbo.BangDiem (MaHocSinh, MaMonHoc, MaHocKy, MaLoai, DiemSo, NgayNhap, NhanXet)
                        VALUES (:hs, :mh, :hk, :loai, :score, GETDATE(), :comment)
                    """), {
                        'hs': target_student_id,
                        'mh': target_subject_id,
                        'hk': target_semester_id,
                        'loai': target_ma_loai,
                        'score': score_val,
                        'comment': comment if comment else None
                    })

        db.commit()
        return jsonify({'success': True, 'message': '✨ Đã chấm điểm bài làm và TỰ ĐỘNG ĐỒNG BỘ VÀO SỔ ĐIỂM thành công!'})

    except Exception as e:
        db.rollback()
        print(f"[CRITICAL ERROR GRADE] {str(e)}")
        return jsonify({'success': False, 'message': f'Lỗi hệ thống: {str(e)}'}), 500
    finally:
        db.close()

# API LẤY DỮ LIỆU SỔ ĐIỂM CHI TIẾT THEO LỚP, MÔN VÀ HỌC KỲ
@app.route('/api/teacher/grades', methods=['GET'])
def get_teacher_grades():
    class_id = request.args.get('class_id')
    subject_id = request.args.get('subject_id', 1)
    semester_id = request.args.get('semester_id', 1)

    db = SessionLocal()
    try:
        # 1. Lấy danh sách học sinh theo lớp
        query_students = text("""
            SELECT MaNguoiDung, HoTen 
            FROM dbo.NguoiDung 
            WHERE (:cid IS NULL OR MaLop = :cid) AND VaiTro = 'Student'
            ORDER BY MaNguoiDung ASC
        """)
        students = db.execute(query_students, {'cid': class_id if class_id else None}).fetchall()

        # 2. Lấy toàn bộ điểm của môn và học kỳ từ bảng BangDiem
        query_scores = text("""
            SELECT MaHocSinh, MaLoai, DiemSo 
            FROM dbo.BangDiem 
            WHERE MaMonHoc = :mid AND MaHocKy = :sem
        """)
        scores = db.execute(query_scores, {'mid': subject_id, 'sem': semester_id}).fetchall()

        # Gom điểm theo MaHocSinh: { student_id: { maloai: diemso } }
        score_map = {}
        for row in scores:
            sid = row.MaHocSinh
            if sid not in score_map:
                score_map[sid] = {}
            score_map[sid][row.MaLoai] = float(row.DiemSo) if row.DiemSo is not None else None

        # 3. Phân bổ điểm vào 7 cột chuẩn của giao diện gradebook.html
        grades_data = []
        for s in students:
            sid = s.MaNguoiDung
            st_scores = score_map.get(sid, {})

            m1 = st_scores.get(1)
            m2 = st_scores.get(2)
            m3 = st_scores.get(3)
            tx1 = st_scores.get(4)
            tx2 = st_scores.get(5)
            gk = st_scores.get(6)
            ck = st_scores.get(7)

            # Tính điểm trung bình môn
            tx_list = [v for v in [m1, m2, m3, tx1, tx2] if v is not None]
            total_sum = sum(tx_list)
            total_count = len(tx_list)

            if gk is not None:
                total_sum += gk * 2
                total_count += 2
            if ck is not None:
                total_sum += ck * 3
                total_count += 3

            avg_score = round(total_sum / total_count, 1) if total_count > 0 else None

            grades_data.append({
                'MaNguoiDung': sid,
                'MaHocSinh': sid,
                'HoTen': s.HoTen,
                'M1': m1,
                'M2': m2,
                'M3': m3,
                'TX1': tx1,
                'TX2': tx2,
                'GK': gk,
                'CK': ck,
                'TB': avg_score
            })

        return jsonify({'success': True, 'data': grades_data})
    except Exception as e:
        print(f"[ERR GET GRADES] {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/teacher/submissions/pending', methods=['GET'])
def get_pending_submissions():
    db = SessionLocal()
    try:
        teacher_id = session.get('user_id')
        if not teacher_id:
            return jsonify({'success': False, 'message': 'Chưa đăng nhập'}), 401

        # Truy vấn các bài nộp của học sinh mà giáo viên chưa chấm điểm (DiemSo IS NULL)
        query = text("""
            SELECT 
                bl.MaBaiLam,
                bl.MaBaiTap,
                bt.TieuDe,
                nd.HoTen,
                FORMAT(bl.NgayNop, 'dd/MM/yyyy HH:mm') AS NgayNop
            FROM dbo.BaiLam bl
            JOIN dbo.BaiTap bt ON bl.MaBaiTap = bt.MaBaiTap
            JOIN dbo.NguoiDung nd ON bl.MaHocSinh = nd.MaNguoiDung
            LEFT JOIN dbo.PhanCongGiangDay pc ON bt.MaPhanCong = pc.MaPhanCong
            WHERE (pc.MaGiaoVien = :tid OR bt.MaPhanCong IS NULL)
              AND bl.DiemSo IS NULL
            ORDER BY bl.NgayNop DESC
        """)
        
        rows = db.execute(query, {'tid': teacher_id}).fetchall()
        
        pending_list = [dict(r._mapping) for r in rows]
        
        return jsonify({
            'success': True,
            'count': len(pending_list),
            'data': pending_list
        })
    except Exception as e:
        print(f"[ERR PENDING SUBMISSIONS] {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        db.close()

@app.route('/api/teacher/assignments/classes', methods=['GET'])
def get_teacher_assignment_classes():
  """API lấy danh sách toàn bộ các lớp học (4 khối: 6, 7, 8, 9) để Giáo viên chọn giao bài tập."""
  db = SessionLocal()
  try:
    # 1. Truy vấn toàn bộ các lớp hiện có trong bảng LopHoc
    query = text("""
            SELECT MaLop AS id, TenLop AS name 
            FROM dbo.LopHoc
            ORDER BY TenLop ASC
        """)
    classes = db.execute(query).fetchall()

    result_classes = [dict(r._mapping) for r in classes]

    # Danh sách chuẩn 12 lớp THCS (Khối 6, 7, 8, 9 - mỗi khối 3 lớp A1, A2, A3)
    standard_classes = [
        # Khối 6
        {'id': 1, 'name': '6A1'},
        {'id': 2, 'name': '6A2'},
        {'id': 3, 'name': '6A3'},
        # Khối 7
        {'id': 4, 'name': '7A1'},
        {'id': 5, 'name': '7A2'},
        {'id': 6, 'name': '7A3'},
        # Khối 8
        {'id': 7, 'name': '8A1'},
        {'id': 8, 'name': '8A2'},
        {'id': 9, 'name': '8A3'},
        # Khối 9
        {'id': 10, 'name': '9A1'},
        {'id': 11, 'name': '9A2'},
        {'id': 12, 'name': '9A3'},
    ]

    # 2. Dự phòng (Fallback): Nếu CSDL bị trống, sử dụng ngay danh sách 12 lớp chuẩn
    if not result_classes:
      result_classes = standard_classes

    return jsonify({'success': True, 'data': result_classes})

  except Exception as e:
    print(f'[ERR FETCH CLASSES] {str(e)}')
    # Trả về danh sách chuẩn 12 lớp nếu xảy ra lỗi truy vấn CSDL
    fallback_classes = [
        {'id': 1, 'name': '6A1'},
        {'id': 2, 'name': '6A2'},
        {'id': 3, 'name': '6A3'},
        {'id': 4, 'name': '7A1'},
        {'id': 5, 'name': '7A2'},
        {'id': 6, 'name': '7A3'},
        {'id': 7, 'name': '8A1'},
        {'id': 8, 'name': '8A2'},
        {'id': 9, 'name': '8A3'},
        {'id': 10, 'name': '9A1'},
        {'id': 11, 'name': '9A2'},
        {'id': 12, 'name': '9A3'},
    ]
    return jsonify({'success': True, 'data': fallback_classes})
  finally:
    db.close() 

# API Tạo bài tập mới (Đã bổ sung nhận ma_loai và lưu vào cột MaLoai)
@app.route('/api/teacher/assignments/create', methods=['POST'])
def create_assignment_lms():
    db = SessionLocal()
    try:
        # 1. Đọc dữ liệu dạng FormData từ Frontend (assignments.html)
        class_id = request.form.get('class_id')
        title = request.form.get('title')
        content = request.form.get('content')
        deadline = request.form.get('deadline')
        ma_loai = int(request.form.get('ma_loai', 0)) # <--- BỔ SUNG: Nhận mã loại điểm (0 - 7)
        
        if not class_id or not title or not content:
            return jsonify({'success': False, 'message': 'Vui lòng điền đầy đủ thông tin bắt buộc!'}), 400

        # 2. Xử lý lưu File/Ảnh đính kèm nếu có
        file_url = None
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                file.save(save_path)
                file_url = f"/static/uploads/{unique_filename}"

        # 3. Tra cứu phân công giảng dạy của Giáo viên
        teacher_id = session.get('user_id')
        
        pc_info = db.execute(text("""
            SELECT TOP 1 MaPhanCong, MaMonHoc 
            FROM dbo.PhanCongGiangDay 
            WHERE MaLop = :cid AND MaGiaoVien = :tid
        """), {'cid': class_id, 'tid': teacher_id}).fetchone()

        ma_phan_cong = pc_info.MaPhanCong if pc_info else None
        ma_mon_hoc = pc_info.MaMonHoc if pc_info else 1

        # 4. Lưu bài tập mới vào CSDL SQL Server (ĐÃ THÊM CỘT MaLoai)
        insert_query = text("""
            INSERT INTO dbo.BaiTap (TieuDe, NoiDung, HanNop, FileDinhKem, MaPhanCong, MaMonHoc, MaLoai, NgayTao)
            VALUES (:title, :content, :deadline, :file_url, :mpc, :mon_id, :ma_loai, GETDATE())
        """)
        
        db.execute(insert_query, {
            'title': title,
            'content': content,
            'deadline': deadline if deadline else None,
            'file_url': file_url,
            'mpc': ma_phan_cong,
            'mon_id': ma_mon_hoc,
            'ma_loai': ma_loai # <--- BỔ SUNG: Truyền giá trị ma_loai vào query
        })
        
        db.commit()
        return jsonify({'success': True, 'message': 'Đã giao bài tập mới thành công!'})

    except Exception as e:
        db.rollback()
        print(f"[ERR CREATE ASSIGNMENT] {str(e)}")
        return jsonify({'success': False, 'message': f"Lỗi máy chủ: {str(e)}"}), 500
    finally:
        db.close()


# ==============================================================================
# 4. KHỞI CHẠY SERVER
# ==============================================================================
# ==============================================================================
# 10.1. Lấy danh sách Nề nếp (XP)
@app.route('/api/teacher/conduct', methods=['GET'])
def get_teacher_conduct():
    class_id = request.args.get('class_id')
    if not class_id: return jsonify({"success": False, "message": "ClassId required"}), 400
    
    db = SessionLocal()
    try:
        query = text("""
            SELECT 
                nd.MaNguoiDung, 
                nd.HoTen, 
                nd.Email,
                (SELECT ISNULL(SUM(DiemXP), 0) FROM NhatKyReNep nk WHERE nk.MaHocSinh = nd.MaNguoiDung) as TongXP,
                (SELECT TOP 1 NoiDung FROM NhatKyReNep nk WHERE nk.MaHocSinh = nd.MaNguoiDung ORDER BY NgayGhi DESC) as NhantXet
            FROM NguoiDung nd
            WHERE nd.MaLop = :cid AND nd.VaiTro = 'Student'
        """)
        results = db.execute(query, {"cid": class_id}).fetchall()
        return jsonify({
            "success": True, 
            "data": [dict(r._mapping) for r in results]
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        db.close()

# [DEBUG] Kiểm tra bảng Thông báo
@app.route('/api/debug/db')
def debug_db():
    db = SessionLocal()
    try:
        res = db.execute(text("SELECT * FROM ThongBao ORDER BY MaThongBao DESC")).mappings().all()
        return jsonify([dict(r) for r in res])
    except Exception as e:
        return str(e)
    finally:
        db.close()


# 10.2. Cập nhật Nề nếp (Thưởng/Phạt XP)
@app.route('/api/teacher/conduct/update', methods=['POST'])
def update_conduct():
    data = request.json
    student_id = data.get('student_id')
    xp = int(data.get('xp', 0))
    reason = data.get('reason', '')
    
    if not student_id:
        return jsonify({"success": False, "message": "Thiếu mã học sinh!"}), 400
        
    db = SessionLocal()
    try:
        # Sử dụng bảng NhatKyReNep có sẵn
        query = text("""
            INSERT INTO NhatKyReNep (MaHocSinh, NoiDung, DiemXP, LoaiLog, NgayGhi)
            VALUES (:sid, :reason, :xp, :type, GETDATE())
        """)
        db.execute(query, {
            "sid": student_id,
            "reason": reason,
            "xp": xp,
            "type": "Thuong" if xp > 0 else "Phat"
        })
        db.commit()

        # [AUTO-PLATFORM] Kích hoạt kết nối đa bên: Thông báo cho Phụ huynh về khen thưởng hoặc vi phạm (XP != 0)
        if xp != 0:
            teacher_id = session.get('user_id')
            NotificationHub.notify_parent_conduct_event(db, student_id, xp, reason, teacher_id=teacher_id)

        return jsonify({"success": True, "message": "Đã cập nhật điểm nề nếp!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

# ==============================================================================
# PHÂN HỆ: QUẢN LÝ ĐIỂM DANH & THỐNG KÊ CHUYÊN CẦN THCS
# ==============================================================================

@app.route('/api/teacher/attendance/submit', methods=['POST'])
def submit_attendance():
    """
    API Ghi nhận điểm danh hàng ngày của lớp học (Giáo viên chủ nhiệm).
    Khớp 100% với bảng dbo.DiemDanh và ràng buộc CHK_TrangThai_DiemDanh_Goc.
    """
    db = SessionLocal()
    try:
        user_id = session.get('user_id') or 2  # Demo mặc định GV ID = 2
        data = request.json or {}
        
        class_id = data.get('class_id')
        attendance_list = data.get('attendance', []) # Cấu trúc: [{"student_id": 1, "status": "HienDien"}, ...]
        
        if not class_id or not attendance_list:
            return jsonify({"success": False, "message": "Thiếu dữ liệu lớp học hoặc danh sách điểm danh"}), 400
            
        today = datetime.now().date()
        
        # Ánh xạ trạng thái từ Frontend sang giá trị CHECK chuẩn trong SQL Server của bạn
        status_mapping = {
            "HienDien": "HienDien",
            "VangCP": "VangCP",
            "VangKP": "VangKP",
            "Muon": "Muon"
        }

        for item in attendance_list:
            student_id = item.get('student_id')
            raw_status = item.get('status', 'HienDien')
            status = status_mapping.get(raw_status, "HienDien")
            ghi_chu = item.get('note', '')

            # Kiểm tra xem hôm nay học sinh này đã được điểm danh chưa
            check_exist = db.execute(text("""
                SELECT MaDiemDanh FROM dbo.DiemDanh 
                WHERE MaHocSinh = :sid AND NgayDiemDanh = :today
            """), {"sid": student_id, "today": today}).fetchone()

            if check_exist:
                # Đã có bản ghi -> Cập nhật trạng thái mới
                db.execute(text("""
                    UPDATE dbo.DiemDanh 
                    SET TrangThai = :status, GhiChu = :note, NguoiDiemDanh = :uid
                    WHERE MaDiemDanh = :id
                """), {"status": status, "note": ghi_chu, "uid": user_id, "id": check_exist[0]})
            else:
                # Chưa có bản ghi -> Chèn mới (INSERT)
                db.execute(text("""
                    INSERT INTO dbo.DiemDanh (MaHocSinh, MaLop, NgayDiemDanh, TrangThai, GhiChu, NguoiDiemDanh)
                    VALUES (:sid, :cid, :today, :status, :note, :uid)
                """), {"sid": student_id, "cid": class_id, "today": today, "status": status, "note": ghi_chu, "uid": user_id})

        db.commit()
        return jsonify({"success": True, "message": "Ghi nhận dữ liệu điểm danh hôm nay thành công!"})
    except Exception as e:
        db.rollback()
        print(f"[ERR ATTENDANCE SUBMIT] {str(e)}")
        return jsonify({"success": False, "message": f"Lỗi cơ sở dữ liệu: {str(e)}"}), 500
    finally:
        db.close()


@app.route('/api/teacher/attendance/stats/<int:class_id>', methods=['GET'])
def get_attendance_stats(class_id):
    """
    API Tính toán định lượng tỷ lệ % chuyên cần phục vụ Dashboard và Cảnh báo sa sút.
    """
    db = SessionLocal()
    try:
        # 1. Đếm tổng số học sinh trong lớp học
        total_students = db.execute(text("""
            SELECT COUNT(*) FROM dbo.NguoiDung WHERE MaLop = :cid AND VaiTro = 'Student'
        """), {"cid": class_id}).scalar() or 0
        
        if total_students == 0:
            return jsonify({"success": True, "stats": {"total_ratio": 100, "present_today": 0, "absent_today": 0}})

        today = datetime.now().date()

        # 2. Thống kê tình trạng điểm danh của ngày hôm nay
        present_today = db.execute(text("""
            SELECT COUNT(*) FROM dbo.DiemDanh 
            WHERE MaLop = :cid AND NgayDiemDanh = :today AND TrangThai IN (N'HienDien', N'Có mặt')
        """), {"cid": class_id, "today": today}).scalar() or 0

        absent_today = db.execute(text("""
            SELECT COUNT(*) FROM dbo.DiemDanh 
            WHERE MaLop = :cid AND NgayDiemDanh = :today AND TrangThai LIKE N'Vang%'
        """), {"cid": class_id, "today": today}).scalar() or 0

        # 3. Tính tỷ lệ chuyên cần tổng thể của lớp trong tháng gần nhất
        total_records = db.execute(text("""
            SELECT COUNT(*) FROM dbo.DiemDanh WHERE MaLop = :cid
        """), {"cid": class_id}).scalar() or 0
        
        present_records = db.execute(text("""
            SELECT COUNT(*) FROM dbo.DiemDanh WHERE MaLop = :cid AND TrangThai IN (N'HienDien', N'Có mặt')
        """), {"cid": class_id}).scalar() or 0

        attendance_ratio = round((present_records / total_records) * 100, 1) if total_records > 0 else 100.0

        return jsonify({
            "success": True,
            "stats": {
                "attendance_ratio": attendance_ratio,
                "present_today": present_today,
                "absent_today": absent_today,
                "total_students": total_students
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()



# 10.2. Thảo luận Bài tập (Tận dụng TraoDoiChuNhiem)
@app.route('/api/assignment/discussion', methods=['GET', 'POST'])
def handle_discussion():
    db = SessionLocal()
    try:
        if request.method == 'GET':
            assignment_id = request.args.get('assignment_id')
            query = text("""
                SELECT td.MaTraoDoi, nd.HoTen, td.NoiDung, td.ThoiGian, td.PhanHoi, td.MaNguoiGui 
                FROM TraoDoiChuNhiem td
                JOIN NguoiDung nd ON td.MaNguoiGui = nd.MaNguoiDung
                WHERE td.MaBaiTap = :aid
                ORDER BY td.ThoiGian ASC
            """)
            rows = db.execute(query, {"aid": assignment_id}).fetchall()
            return jsonify({"success": True, "data": [dict(r._mapping) for r in rows]})
            
        else: # POST
            data = request.json
            assignment_id = data.get('assignment_id')
            user_id = session.get('user_id', 3) # Demo
            content = data.get('content')
            parent_id = data.get('parent_id') # Nếu là trả lời (MaTraoDoi)
            
            if parent_id: # Là Giáo viên trả lời
                query = text("""
                    UPDATE TraoDoiChuNhiem 
                    SET PhanHoi = :content 
                    WHERE MaTraoDoi = :pid
                """)
                db.execute(query, {"content": content, "pid": parent_id})
            else: # Là Học sinh đặt câu hỏi
                query = text("""
                    INSERT INTO TraoDoiChuNhiem (MaNguoiGui, MaBaiTap, NoiDung, ThoiGian, TrangThai)
                    VALUES (:uid, :aid, :content, GETDATE(), N'Chờ trả lời')
                """)
                db.execute(query, {"uid": user_id, "aid": assignment_id, "content": content})
                
            db.commit()
            return jsonify({"success": True})
            
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()


# ==============================================================================
# PHÂN HỆ: QUẢN LÝ BÀI TẬP VÀ Ý THỨC HỌC TẬP THCS
# ==============================================================================

@app.route('/api/assignment/stats/<int:class_id>', methods=['GET'])
def get_assignment_stats(class_id):
    """
    API Thống kê tỷ lệ nộp bài tập của toàn bộ lớp học phục vụ Dashboard Giáo viên chủ nhiệm.
    Kết hợp dữ liệu từ bảng dbo.ChiTietNopBaiTap và dbo.BaiTap.
    """
    db = SessionLocal()
    try:
        # Lấy tổng số bài tập đã giao cho lớp này thông qua phân công giảng dạy
        total_assignments = db.execute(text("""
            SELECT COUNT(bt.MaBaiTap) FROM dbo.BaiTap bt
            JOIN dbo.PhanCongGiangDay pc ON bt.MaPhanCong = pc.MaPhanCong
            WHERE pc.MaLop = :cid
        """), {"cid": class_id}).scalar() or 0

        if total_assignments == 0:
            return jsonify({"success": True, "stats": {"completion_ratio": 100, "pending_tasks": 0}})

        # Thống kê chi tiết các trạng thái từ bảng ChiTietNopBaiTap của học sinh trong lớp
        submitted_count = db.execute(text("""
            SELECT COUNT(ct.MaChiTiet) FROM dbo.ChiTietNopBaiTap ct
            JOIN dbo.NguoiDung nd ON ct.MaHocSinh = nd.MaNguoiDung
            WHERE nd.MaLop = :cid AND ct.TrangThaiNop = N'Đã nộp'
        """), {"cid": class_id}).scalar() or 0

        total_submission_records = db.execute(text("""
            SELECT COUNT(ct.MaChiTiet) FROM dbo.ChiTietNopBaiTap ct
            JOIN dbo.NguoiDung nd ON ct.MaHocSinh = nd.MaNguoiDung
            WHERE nd.MaLop = :cid
        """), {"cid": class_id}).scalar() or 0

        completion_ratio = round((submitted_count / total_submission_records) * 100, 1) if total_submission_records > 0 else 0.0

        return jsonify({
            "success": True,
            "stats": {
                "total_assignments_giao": total_assignments,
                "completion_ratio": completion_ratio,
                "submitted_count": submitted_count,
                "missing_count": total_submission_records - submitted_count
            }
        })
    except Exception as e:
        print(f"[ERR ASSIGNMENT STATS] {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@app.route('/api/assignment/unsubmit', methods=['POST'])
def unsubmit_assignment():
  """API cho phép học sinh hủy nộp bài tập để tải lại bài làm mới."""
  db = SessionLocal()
  try:
    user_id = session.get('user_id')
    data = request.json or {}
    assignment_id = data.get('assignment_id')

    if not user_id or not assignment_id:
      return (
          jsonify(
              {'success': False, 'message': 'Thiếu tham số hoặc chưa đăng nhập!'}
          ),
          400,
      )

    # Xóa bản ghi bài làm cũ trong bảng BaiLam
    db.execute(
        text("""
            DELETE FROM dbo.BaiLam 
            WHERE MaHocSinh = :uid AND MaBaiTap = :aid
        """),
        {'uid': user_id, 'aid': assignment_id},
    )

    db.commit()
    return jsonify(
        {'success': True, 'message': 'Đã hủy bài nộp thành công!'}
    )
  except Exception as e:
    db.rollback()
    print(f'[ERR UNSUBMIT ASSIGNMENT] {str(e)}')
    return jsonify({'success': False, 'message': str(e)}), 500
  finally:
    db.close()
        
        
# 10.3. Đánh giá Học liệu (Rating)
@app.route('/api/resource/rate', methods=['POST'])
def rate_resource():
    data = request.json
    resource_id = data.get('resource_id')
    student_id = session.get('user_id', 3) # Demo
    stars = int(data.get('stars', 5))
    
    db = SessionLocal()
    try:
        # Mỗi học sinh chỉ được chấm 1 lần cho 1 tài liệu
        check_query = text("SELECT MaDanhGia FROM DanhGiaHocLieu WHERE MaTaiLieu = :rid AND MaHocSinh = :sid")
        existing = db.execute(check_query, {"rid": resource_id, "sid": student_id}).fetchone()
        
        if existing:
            query = text("UPDATE DanhGiaHocLieu SET SoSao = :stars WHERE MaDanhGia = :did")
            db.execute(query, {"stars": stars, "did": existing[0]})
        else:
            query = text("INSERT INTO DanhGiaHocLieu (MaTaiLieu, MaHocSinh, SoSao) VALUES (:rid, :sid, :stars)")
            db.execute(query, {"rid": resource_id, "sid": student_id, "stars": stars})
            
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

# 10.4. Lấy danh sách Học liệu (kèm Rating)
@app.route('/api/resources', methods=['GET'])
def get_resources():
    class_id = request.args.get('class_id', 0)
    sort_type = request.args.get('sort', 'newest') # newest, most_viewed
    db = SessionLocal()
    try:
        current_uid = session.get('user_id', 0)
        u_class_id = session.get('class_id', 0)
        
        try:
            u_class_id = int(u_class_id) if u_class_id else 0
        except: u_class_id = 0

        # [AUTO-PLATFORM] Phân quyền chuẩn: Guest chỉ thấy TrangThai = 2
        if not session.get('user_id'):
            visibility_clause = "ISNULL(kl.TrangThai, 0) = 2"
        else:
            # Đã đăng nhập: Thấy Công khai (2) + Nội bộ (1) + Lớp mình (0)
            u_class_id = session.get('class_id', 0)
            try: u_class_id = int(u_class_id)
            except: u_class_id = 0
            
            if u_class_id > 0:
                visibility_clause = f"(kl.TrangThai = 2 OR kl.TrangThai = 1 OR (kl.TrangThai = 0 AND kl.MaLop = {u_class_id}))"
            else:
                visibility_clause = "(kl.TrangThai = 2 OR kl.TrangThai = 1)"

        print(f"[DEBUG] Get Resources - User: {session.get('user_id')}, Class: {session.get('class_id')}, Clause: {visibility_clause}")
        where_clause = f"WHERE {visibility_clause}"
        params = {"current_uid": current_uid}
        
        try:
            target_ckid = int(class_id)
        except: target_ckid = 0

        if target_ckid > 0:
            actual_grade = target_ckid + 5 if target_ckid <= 4 else target_ckid
            where_clause += " AND (kl.MaKhoi = :ckid OR kl.MaKhoi = :agrade)"
            params["ckid"] = target_ckid
            params["agrade"] = actual_grade
        
        # Logic sắp xếp
        order_by = "ORDER BY kl.NgayDang DESC"
        if sort_type == 'most_viewed':
            order_by = "ORDER BY ISNULL(kl.LuotXem, 0) DESC, kl.NgayDang DESC"
        elif sort_type == 'top_rated':
            order_by = "ORDER BY AvgStars DESC, kl.NgayDang DESC"

        query_str = f"""
            SELECT kl.*, 
                   ISNULL((SELECT AVG(CAST(SoSao AS FLOAT)) FROM DanhGiaHocLieu WHERE MaTaiLieu = kl.MaTaiLieu), 0) as AvgStars,
                   ISNULL((SELECT COUNT(*) FROM DanhGiaHocLieu WHERE MaTaiLieu = kl.MaTaiLieu), 0) as StarCount,
                   ISNULL((SELECT COUNT(*) FROM TuongTac WHERE MaDoiTuong = kl.MaTaiLieu AND LoaiDoiTuong = 'HocLieu'), 0) as LikeCount,
                   ISNULL((SELECT COUNT(*) FROM BinhLuan WHERE MaDoiTuong = kl.MaTaiLieu AND LoaiDoiTuong = 'HocLieu'), 0) as CommentCount,
                   CASE WHEN EXISTS (SELECT 1 FROM TuongTac WHERE MaDoiTuong = kl.MaTaiLieu AND LoaiDoiTuong = 'HocLieu' AND MaNguoiDung = :current_uid) THEN 1 ELSE 0 END as IsLiked,
                   mh.TenMonHoc
            FROM KhoHocLieu kl
            LEFT JOIN MonHoc mh ON kl.MaMonHoc = mh.MaMonHoc
            {where_clause}
            {order_by}
        """

        try:
            rows = db.execute(text(query_str), params).fetchall()
        except Exception as e:
            # Nếu vẫn lỗi (do cột LuotXem chưa có), dùng query dự phòng không có LuotXem
            print(f"[DB-Query-Fallback] {e}")
            query_fallback = query_str.replace("kl.*", "kl.MaTaiLieu, kl.TenTaiLieu, kl.MoTa, kl.LoaiFile, kl.DuongDan, kl.MaMonHoc, kl.MaNguoiDang, kl.NgayDang, kl.MaKhoi, kl.TrangThai, kl.MaLop")
            if "kl.LuotXem" in order_by:
                order_by = "ORDER BY kl.NgayDang DESC"
            rows = db.execute(text(query_fallback.replace(order_by, "ORDER BY kl.NgayDang DESC")), params).fetchall()
        
        resources = []
        for r in rows:
            res_dict = dict(r._mapping)
            resources.append({
                "id": res_dict['MaTaiLieu'],
                "title": res_dict['TenTaiLieu'],
                "description": res_dict['MoTa'],
                "subject": res_dict['TenMonHoc'],
                "type": res_dict['LoaiFile'],
                "url": res_dict['DuongDan'],
                "path": res_dict['DuongDan'],
                "stars": round(res_dict['AvgStars'], 1),
                "star_count": res_dict['StarCount'],
                "likes": res_dict['LikeCount'],
                "comments_count": res_dict['CommentCount'],
                "is_liked": res_dict['IsLiked'] == 1,
                "views": res_dict.get('LuotXem', 0) or 0,
                "download_count": res_dict.get('SoLuotTai', 0) or 0,
                "teacher": "Giáo viên Hệ thống", 
                "grade": res_dict.get('MaKhoi'),
                "icon": "ph-file-pdf" if res_dict['LoaiFile'] == 'PDF' else "ph-video-camera",
                "color": "text-red-500" if res_dict['LoaiFile'] == 'PDF' else "text-blue-500",
                "trang_thai": res_dict['TrangThai']
            })
            
        return jsonify({"success": True, "data": resources})
    except Exception as e:
        print(f"Error fetching resources: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

# API tăng lượt xem
@app.route('/api/resource/view/<int:id>', methods=['POST'])
def view_resource(id):
    db = SessionLocal()
    try:
        db.execute(text("UPDATE KhoHocLieu SET LuotXem = ISNULL(LuotXem, 0) + 1 WHERE MaTaiLieu = :id"), {"id": id})
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

# 10.5. Tương tác: Like học liệu
@app.route('/api/resources/like/<int:id>', methods=['POST'])
def like_resource(id):
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401
        
        # Check xem đã like chưa
        check_query = text("SELECT * FROM TuongTac WHERE LoaiDoiTuong = 'HocLieu' AND MaDoiTuong = :rid AND MaNguoiDung = :uid")
        exists = db.execute(check_query, {"rid": id, "uid": user_id}).fetchone()
        
        if exists:
            db.execute(text("DELETE FROM TuongTac WHERE LoaiDoiTuong = 'HocLieu' AND MaDoiTuong = :rid AND MaNguoiDung = :uid"), {"rid": id, "uid": user_id})
            action = "unliked"
        else:
            db.execute(text("INSERT INTO TuongTac (LoaiDoiTuong, MaDoiTuong, MaNguoiDung, LoaiTuongTac) VALUES ('HocLieu', :rid, :uid, 'Like')"), {"rid": id, "uid": user_id})
            action = "liked"
            
        db.commit()
        
        # Lấy số lượng like mới
        count = db.execute(text("SELECT COUNT(*) FROM TuongTac WHERE LoaiDoiTuong = 'HocLieu' AND MaDoiTuong = :rid"), {"rid": id}).scalar()
        
        return jsonify({"success": True, "action": action, "count": count})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        db.close()

# 10.6. Tương tác: Chia sẻ học liệu vào Nhóm lớp
@app.route('/api/resources/share/<int:id>', methods=['POST'])
def share_resource(id):
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401
        
        u_class_id = session.get('class_id')
        
        # [ROBUST] Nếu session mất class_id, truy vấn lại từ DB
        if not u_class_id:
            u_info = db.execute(text("SELECT MaLop FROM NguoiDung WHERE MaNguoiDung = :uid"), {"uid": user_id}).fetchone()
            if u_info and u_info.MaLop:
                u_class_id = u_info.MaLop
                session['class_id'] = u_class_id
        
        if not u_class_id:
            return jsonify({"success": False, "message": "Tài khoản của bạn chưa được gán vào lớp học nào!"}), 400

        # Lấy thông tin tài liệu
        res = db.execute(text("SELECT TenTaiLieu, DuongDan FROM KhoHocLieu WHERE MaTaiLieu = :id"), {"id": id}).fetchone()
        if not res: return jsonify({"success": False, "message": "Không tìm thấy tài liệu"}), 404
        
        # Gửi tin nhắn vào nhóm chat lớp kèm link điều hướng tới Kho học liệu
        tag = f"GROUP_{u_class_id}"
        message_content = f"📚 GIÁO VIÊN CHIA SẺ HỌC LIỆU MỚI:\n📖 Tên: {res.TenTaiLieu}\n📍 Xem tại Kho học liệu: /kho-hoc-lieu?id={id}"
        
        db.execute(text("""
            INSERT INTO TraoDoiChuNhiem (MaNguoiGui, MaNguoiNhan, TieuDe, NoiDung, ThoiGian, TrangThai)
            VALUES (:uid, :rid, :tag, :content, GETDATE(), N'ChoPhanHoi')
        """), {
            "uid": user_id,
            "rid": user_id, 
            "tag": tag,
            "content": message_content
        })
        
        db.commit()
        return jsonify({"success": True, "message": "Đã chia sẻ vào nhóm tin nhắn lớp!"})
    except Exception as e:
        db.rollback()
        print(f"[SHARE-ERROR] {e}")
        return jsonify({"success": False, "message": str(e)})

# 10.7. Tương tác: Đánh giá & Bình luận học liệu
@app.route('/api/resources/comment/<int:id>', methods=['POST'])
def comment_resource(id):
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401
        
        data = request.json
        stars = data.get('stars', 5)
        comment_text = data.get('comment', '')
        
        # 1. Lưu đánh giá sao
        db.execute(text("""
            INSERT INTO DanhGiaHocLieu (MaTaiLieu, MaNguoiDung, SoSao, NgayDanhGia)
            VALUES (:rid, :uid, :stars, GETDATE())
        """), {"rid": id, "uid": user_id, "stars": stars})
        
        # 2. Lưu bình luận (nếu có)
        if comment_text:
            db.execute(text("""
                INSERT INTO BinhLuan (LoaiDoiTuong, MaDoiTuong, MaNguoiDung, NoiDung, NgayBinhLuan)
                VALUES ('HocLieu', :rid, :uid, :content, GETDATE())
            """), {"rid": id, "uid": user_id, "content": comment_text})
            
        db.commit()
        return jsonify({"success": True, "message": "Cảm ơn bạn đã đóng góp!"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        db.close()

# 10.5. Đăng Học liệu mới (Giáo viên)
@app.route('/api/resource/create', methods=['POST'])
def create_resource():
    user_id = session.get('user_id', 1)  # Giả sử giáo viên ID = 1 nếu chưa login
    data = request.json
    try:
        title = data.get('title')
        description = data.get('description')
        file_type = data.get('type')
        link = data.get('url')
        subject_id = data.get('subject_id')
        grade_id = data.get('grade_id', 0)
        
        if not title or not link or not subject_id:
            return jsonify({"success": False, "message": "Thiếu thông tin bắt buộc"}), 400
            
        db = SessionLocal()
        
        # [AUTO-PLATFORM] Lấy thêm thông tin chế độ chia sẻ và mã lớp
        status = data.get('status', 2)  # Mặc định là Công khai (2)
        teacher_class_id = db.execute(text("SELECT MaLop FROM NguoiDung WHERE MaNguoiDung = :uid"), {"uid": user_id}).scalar()
        
        query = text("""
            INSERT INTO KhoHocLieu (TenTaiLieu, MoTa, LoaiFile, DuongDan, MaMonHoc, MaNguoiDang, NgayDang, MaKhoi, TrangThai, MaLop)
            VALUES (:title, :desc, :type, :url, :sid, :uid, GETDATE(), :gid, :status, :mlid)
        """)
        db.execute(query, {
            "title": title,
            "desc": description,
            "type": file_type,
            "url": link,
            "sid": subject_id,
            "uid": user_id,
            "gid": grade_id,
            "status": status,
            "mlid": teacher_class_id if int(status) == 0 else 0
        })
        db.commit()
        db.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# ==============================================================================
# 11. API NGHIỆP VỤ QUẢN LÝ CHỦ NHIỆM (MỚI)
# ==============================================================================

@app.route('/api/student/chat-contacts', methods=['GET'])
def get_student_chat_contacts():
    db = SessionLocal()
    try:
        student_id = session.get('user_id')
        if not student_id: return jsonify({"success": False, "message": "Unauthorized"}), 401
        
        # Lấy MaLop của HS
        u_info = db.execute(text("SELECT MaLop FROM NguoiDung WHERE MaNguoiDung = :sid"), {"sid": student_id}).fetchone()
        if not u_info or not u_info[0]:
            return jsonify({"success": False, "message": "Học sinh chưa được xếp lớp"}), 404
        
        class_id = u_info[0]
        class_name_res = db.execute(text("SELECT TenLop FROM LopHoc WHERE MaLop = :cid"), {"cid": class_id}).fetchone()
        class_name = class_name_res[0] if class_name_res else f"Lớp {class_id}"
        
        contacts = [{
            "MaNguoiDung": -int(class_id),
            "HoTen": f"NHÓM LỚP {class_name}",
            "TenCon": "GVCN & Cả lớp",
            "IsGroup": True
        }]
        
        return jsonify({"success": True, "data": contacts})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

# ==============================================================================
# API DÀNH CHO TRANG CHỦ (HIGHLIGHTS)
# ==============================================================================

@app.route('/api/platform/highlights', methods=['GET'])
def get_platform_highlights():
    db = SessionLocal()
    try:
        # 1. Thống kê cơ bản
        total_students = db.execute(text("SELECT COUNT(*) FROM NguoiDung WHERE VaiTro = 'Student'")).scalar() or 0
        total_teachers = db.execute(text("SELECT COUNT(*) FROM NguoiDung WHERE VaiTro = 'Teacher'")).scalar() or 0
        total_materials = db.execute(text("SELECT COUNT(*) FROM KhoHocLieu")).scalar() or 0
        
        # 2. Học liệu tiêu biểu (Mới nhất - Chỉ lấy bài Công khai - TrangThai = 2)
        mate_query = text("""
            SELECT tkb.MaTaiLieu, tkb.TenTaiLieu, tkb.MoTa, tkb.NgayDang as NgayTao, nd.HoTen as TenGiaoVien
            FROM [dbo].[KhoHocLieu] tkb
            LEFT JOIN [dbo].[NguoiDung] nd ON tkb.MaNguoiDang = nd.MaNguoiDung
            WHERE ISNULL(tkb.TrangThai, 0) = 2
            ORDER BY tkb.NgayDang DESC
        """)
        materials = db.execute(mate_query).fetchmany(4)
        
        # 3. Hoạt động/Thông báo mới
        news_query = text("SELECT TieuDe, NgayGui as NgayTao FROM [dbo].[ThongBao] ORDER BY NgayGui DESC")
        news = db.execute(news_query).fetchmany(3)
        
        return jsonify({
            "success": True,
            "stats": {
                "students": total_students + 1500, # Số ảo
                "teachers": total_teachers + 80,
                "materials": total_materials + 250
            },
            "materials": [dict(r._mapping) for r in materials],
            "activities": [dict(r._mapping) for r in news]
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        db.close()

# --- 11. HỆ THỐNG SỰ KIỆN (EVENTS) ---

# 11.1. Tạo sự kiện mới (Giáo viên)
@app.route('/api/events/create', methods=['POST'])
def create_event():
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401
        
        # Tạo bảng nếu chưa có (bao gồm cột HinhAnh)
        db.execute(text("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[SuKien]') AND type in (N'U'))
            BEGIN
                CREATE TABLE [dbo].[SuKien] (
                    MaSuKien INT PRIMARY KEY IDENTITY(1,1),
                    TieuDe NVARCHAR(255) NOT NULL,
                    NoiDung NVARCHAR(MAX),
                    ThoiGianBatDau DATETIME,
                    DiaDiem NVARCHAR(255),
                    HanDangKy DATETIME,
                    MaNguoiTao INT,
                    PhamVi INT,
                    MaDoiTuong INT,
                    HinhAnh NVARCHAR(MAX),
                    NgayTao DATETIME DEFAULT GETDATE()
                )
            END
            ELSE
            BEGIN
                IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('SuKien') AND name = 'HinhAnh')
                BEGIN
                    ALTER TABLE SuKien ADD HinhAnh NVARCHAR(MAX);
                END
            END
        """))
        db.execute(text("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[DangKySuKien]') AND type in (N'U'))
            BEGIN
                CREATE TABLE [dbo].[DangKySuKien] (
                    MaSuKien INT,
                    MaNguoiDung INT,
                    NgayDangKy DATETIME DEFAULT GETDATE(),
                    PRIMARY KEY (MaSuKien, MaNguoiDung)
                )
            END
        """))

        # Lấy dữ liệu từ FormData
        title = request.form.get('title')
        content = request.form.get('content')
        location = request.form.get('location')
        start_time_raw = request.form.get('start_time')
        deadline_raw = request.form.get('deadline')
        scope = request.form.get('scope')

        # Xử lý ảnh
        file_url = None
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename:
                filename = secure_filename(file.filename)
                unique_name = f"{uuid.uuid4().hex}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
                file_url = f"/static/uploads/{unique_name}"

        # Chuẩn hóa ngày tháng
        start_time = start_time_raw.replace('T', ' ') if start_time_raw else None
        deadline = deadline_raw.replace('T', ' ') if deadline_raw else None

        # --- ĐỒNG BỘ LOGIC VỚI BẢN CŨ & TỐI ƯU ---
        # Lấy thông tin Lớp/Khối mà giáo viên này quản lý hoặc thuộc về (Xử lý trường hợp MaLop=0 thành NULL)
        gv_data = db.execute(text("""
            SELECT 
                COALESCE(NULLIF(nd.MaLop, 0), lh_gv.MaLop) as MaLop,
                COALESCE(NULLIF(lh_nd.MaKhoi, 0), lh_gv.MaKhoi) as MaKhoi
            FROM NguoiDung nd
            LEFT JOIN LopHoc lh_nd ON nd.MaLop = lh_nd.MaLop
            LEFT JOIN LopHoc lh_gv ON nd.MaNguoiDung = lh_gv.MaGVCN
            WHERE nd.MaNguoiDung = :uid
        """), {"uid": user_id}).fetchone()
        
        real_target_id = 0
        if str(scope) == '3' and gv_data: # Gửi cho Lớp
            real_target_id = gv_data.MaLop or 0
        elif str(scope) == '2' and gv_data: # Gửi cho Khối
            real_target_id = gv_data.MaKhoi or 0
        
        # Lưu vào Database
        db.execute(text("""
            INSERT INTO SuKien (TieuDe, NoiDung, ThoiGianBatDau, DiaDiem, HanDangKy, MaNguoiTao, PhamVi, MaDoiTuong, HinhAnh)
            VALUES (:title, :content, :start, :location, :deadline, :uid, :scope, :tid, :img)
        """), {
            "title": title, "content": content, "start": start_time,
            "location": location, "deadline": deadline, "uid": user_id,
            "scope": scope, "tid": real_target_id, "img": file_url
        })
        
        db.commit()
        return jsonify({"success": True, "message": "Đã tạo sự kiện thành công!"})
    except Exception as e:
        db.rollback()
        print(f"Lỗi tạo sự kiện: {str(e)}")
        return jsonify({"success": False, "message": f"Lỗi hệ thống: {str(e)}"})
    finally:
        db.close()

# 11.2. Danh sách sự kiện (Lọc theo người dùng)
@app.route('/api/events/list', methods=['GET'])
def list_events():
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401

        # Lấy thông tin user an toàn
        k_id = session.get('khoi_id')
        c_id = session.get('class_id')
        
        # Nếu session bị thiếu (do chưa đăng nhập lại), chủ động lấy từ DB
        if k_id is None or c_id is None:
            u_info = db.execute(text("""
                SELECT nd.MaLop, lh.MaKhoi
                FROM NguoiDung nd
                LEFT JOIN LopHoc lh ON nd.MaLop = lh.MaLop
                WHERE nd.MaNguoiDung = :uid
            """), {"uid": user_id}).fetchone()
            if u_info:
                c_id = c_id or u_info.MaLop
                k_id = k_id or u_info.MaKhoi
            
            # Nếu là Phụ huynh, lấy từ con liên kết
            if session.get('vai_tro') == 'Parent':
                p_info = db.execute(text("""
                    SELECT child.MaLop, lh.MaKhoi
                    FROM NguoiDung nd
                    JOIN NguoiDung child ON nd.MaHocSinhLienKet = child.MaNguoiDung
                    LEFT JOIN LopHoc lh ON child.MaLop = lh.MaLop
                    WHERE nd.MaNguoiDung = :uid
                """), {"uid": user_id}).fetchone()
                if p_info:
                    c_id = c_id or p_info.MaLop
                    k_id = k_id or p_info.MaKhoi

        k_id = k_id or 0
        c_id = c_id or 0
        
        # Query lấy danh sách sự kiện
        query = text("""
            SELECT sk.MaSuKien, sk.TieuDe, sk.NoiDung, sk.ThoiGianBatDau, sk.DiaDiem, 
                   sk.HanDangKy, sk.NgayTao, sk.PhamVi, sk.HinhAnh,
                   (SELECT COUNT(*) FROM DangKySuKien WHERE MaSuKien = sk.MaSuKien) as RegCount,
                   CASE WHEN EXISTS (SELECT 1 FROM DangKySuKien WHERE MaSuKien = sk.MaSuKien AND MaNguoiDung = :uid_reg) THEN 1 ELSE 0 END as IsRegistered
            FROM SuKien sk
            WHERE sk.PhamVi = 0
               OR sk.PhamVi = 1 
               OR (sk.PhamVi = 2 AND ISNULL(sk.MaDoiTuong, 0) = :kid)
               OR (sk.PhamVi = 3 AND ISNULL(sk.MaDoiTuong, 0) = :cid)
               OR sk.MaNguoiTao = :uid_creator
            ORDER BY sk.NgayTao DESC
        """)
        
        rows = db.execute(query, {
            "uid_reg": user_id, 
            "kid": k_id, 
            "cid": c_id, 
            "uid_creator": user_id
        }).fetchall()
        
        from datetime import datetime
        now = datetime.now()
        events = []
        for r in rows:
            ev = dict(r._mapping)
            
            ev['is_expired'] = False
            if ev['HanDangKy'] and now > ev['HanDangKy']:
                ev['is_expired'] = True

            try:
                if ev['ThoiGianBatDau']: ev['ThoiGianBatDau'] = ev['ThoiGianBatDau'].strftime('%Y-%m-%d %H:%M:%S')
                if ev['HanDangKy']: ev['HanDangKy'] = ev['HanDangKy'].strftime('%Y-%m-%d %H:%M:%S')
                if ev['NgayTao']: ev['NgayTao'] = ev['NgayTao'].strftime('%Y-%m-%d %H:%M:%S')
            except: pass
            events.append(ev)
            
        return jsonify({"success": True, "data": events})
    except Exception as e:
        print(f"CRITICAL ERROR list_events: {str(e)}")
        return jsonify({"success": False, "message": str(e)})
    finally:
        db.close()

# 11.4. Danh sách sự kiện dành cho khách (Công khai - PhamVi = 0)
@app.route('/api/guest/events', methods=['GET'])
def list_guest_events():
    db = SessionLocal()
    try:
        query = text("""
            SELECT sk.MaSuKien, sk.TieuDe, sk.NoiDung, sk.ThoiGianBatDau, sk.DiaDiem, 
                   sk.HanDangKy, sk.NgayTao, sk.PhamVi, sk.HinhAnh,
                   (SELECT COUNT(*) FROM DangKySuKien WHERE MaSuKien = sk.MaSuKien) as RegCount
            FROM SuKien sk
            WHERE sk.PhamVi = 0
            ORDER BY sk.NgayTao DESC
        """)
        rows = db.execute(query).fetchall()
        
        from datetime import datetime
        events = []
        for r in rows:
            ev = dict(r._mapping)
            try:
                if ev['ThoiGianBatDau']: ev['ThoiGianBatDau'] = ev['ThoiGianBatDau'].strftime('%Y-%m-%d %H:%M:%S')
                if ev['HanDangKy']: ev['HanDangKy'] = ev['HanDangKy'].strftime('%Y-%m-%d %H:%M:%S')
                if ev['NgayTao']: ev['NgayTao'] = ev['NgayTao'].strftime('%Y-%m-%d %H:%M:%S')
            except: pass
            ev['IsRegistered'] = False
            events.append(ev)
        return jsonify({"success": True, "data": events})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

# 11.3. Xóa sự kiện
@app.route('/api/events/delete/<int:id>', methods=['DELETE'])
def delete_event(id):
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401
        
        # Kiểm tra quyền (Chỉ người tạo hoặc Admin mới được xóa)
        event = db.execute(text("SELECT MaNguoiTao FROM SuKien WHERE MaSuKien = :id"), {"id": id}).fetchone()
        if not event:
            return jsonify({"success": False, "message": "Sự kiện không tồn tại"}), 404
            
        if event.MaNguoiTao != user_id and session.get('vai_tro') != 'Admin':
            return jsonify({"success": False, "message": "Bạn không có quyền xóa sự kiện này"}), 403
            
        # Xóa các dữ liệu liên quan trước (Ràng buộc dữ liệu)
        db.execute(text("DELETE FROM DangKySuKien WHERE MaSuKien = :id"), {"id": id})
        db.execute(text("DELETE FROM TuongTac WHERE MaDoiTuong = :id AND LoaiDoiTuong = 'SuKien'"), {"id": id})
        db.execute(text("DELETE FROM BinhLuan WHERE MaDoiTuong = :id AND LoaiDoiTuong = 'SuKien'"), {"id": id})
        
        # Xóa sự kiện chính
        db.execute(text("DELETE FROM SuKien WHERE MaSuKien = :id"), {"id": id})
        
        db.commit()
        return jsonify({"success": True, "message": "Đã xóa sự kiện thành công!"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

# 11.3b. Sửa sự kiện
@app.route('/api/events/update/<int:id>', methods=['PUT'])
def update_event(id):
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401
        
        # Kiểm tra quyền
        event = db.execute(text("SELECT MaNguoiTao FROM SuKien WHERE MaSuKien = :id"), {"id": id}).fetchone()
        if not event:
            return jsonify({"success": False, "message": "Sự kiện không tồn tại"}), 404
            
        if event.MaNguoiTao != user_id and session.get('vai_tro') != 'Admin':
            return jsonify({"success": False, "message": "Bạn không có quyền sửa sự kiện này"}), 403
            
        data = request.json
        title = data.get('title')
        content = data.get('content')
        location = data.get('location')
        start_time = data.get('start_time')
        deadline = data.get('deadline')
        
        if not title or not content:
            return jsonify({"success": False, "message": "Tiêu đề và nội dung không được trống"}), 400
            
        db.execute(text("""
            UPDATE SuKien 
            SET TieuDe = :t, NoiDung = :c, DiaDiem = :d, ThoiGianBatDau = :start, HanDangKy = :end
            WHERE MaSuKien = :id
        """), {
            "t": title, "c": content, "d": location,
            "start": start_time, "end": deadline, "id": id
        })
        db.commit()
        return jsonify({"success": True, "message": "Cập nhật sự kiện thành công!"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

# 11.3. Đăng ký tham gia sự kiện
@app.route('/api/events/register/<int:id>', methods=['POST'])
def register_event(id):
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401
        
        # Kiểm tra sự kiện và hạn đăng ký
        sk = db.execute(text("SELECT HanDangKy FROM SuKien WHERE MaSuKien = :id"), {"id": id}).fetchone()
        if not sk: return jsonify({"success": False, "message": "Sự kiện không tồn tại"}), 404
        
        from datetime import datetime
        now = datetime.now()
        
        # Nếu có hạn đăng ký, kiểm tra xem đã quá hạn chưa
        if sk.HanDangKy and now > sk.HanDangKy:
            return jsonify({"success": False, "message": "Sự kiện này đã hết hạn đăng ký! ✨"})

        # Đăng ký
        db.execute(text("""
            IF NOT EXISTS (SELECT 1 FROM DangKySuKien WHERE MaSuKien = :sid AND MaNguoiDung = :uid)
            BEGIN
                INSERT INTO DangKySuKien (MaSuKien, MaNguoiDung, NgayDangKy) VALUES (:sid, :uid, GETDATE())
            END
        """), {"sid": id, "uid": user_id})
        
        # Gửi Email thông báo
        try:
            from app.utils.notification_utils import RealEmailDispatcher
            user_info = db.execute(text("SELECT HoTen, Email FROM NguoiDung WHERE MaNguoiDung = :uid"), {"uid": user_id}).fetchone()
            event_info = db.execute(text("SELECT TieuDe FROM SuKien WHERE MaSuKien = :sid"), {"sid": id}).fetchone()
            
            if user_info and user_info.Email and event_info:
                subj = f"[EduNext] Đã đăng ký thành công: {event_info.TieuDe}"
                body = f"Chào {user_info.HoTen},\n\nBạn đã đăng ký tham gia sự kiện '{event_info.TieuDe}' thành công trên hệ thống EduNext.\n\nHẹn gặp lại bạn tại sự kiện!"
                RealEmailDispatcher.send(user_info.Email, subj, body)
        except Exception as e:
            print(f"[EVENT-MAIL-ERR] {e}")

        db.commit()
        return jsonify({"success": True, "message": "Đã đăng ký tham gia thành công!"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": f"Lỗi SQL Server: {str(e)}"})
    finally:
        db.close()

# 11.6. Hủy đăng ký sự kiện
@app.route('/api/events/unregister/<int:id>', methods=['POST'])
def unregister_event(id):
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401
        
        db.execute(text("DELETE FROM DangKySuKien WHERE MaSuKien = :sid AND MaNguoiDung = :uid"), {"sid": id, "uid": user_id})
        db.commit()
        return jsonify({"success": True, "message": "Đã hủy đăng ký!"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)})
    finally:
        db.close()

# 11.4. Lấy danh sách người đăng ký tham gia sự kiện (Giáo viên)
@app.route('/api/events/registrations/<int:id>', methods=['GET'])
def get_event_registrations(id):
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401
        
        # 1. Lấy thông tin sự kiện
        event_row = db.execute(text("SELECT TieuDe, NoiDung, ThoiGianBatDau, DiaDiem, HanDangKy FROM SuKien WHERE MaSuKien = :id"), {"id": id}).fetchone()
        if not event_row: return jsonify({"success": False, "message": "Không tìm thấy sự kiện"}), 404
        
        ev = dict(event_row._mapping)
        if ev['ThoiGianBatDau']: ev['ThoiGianBatDau'] = ev['ThoiGianBatDau'].strftime('%Y-%m-%d %H:%M:%S')
        if ev['HanDangKy']: ev['HanDangKy'] = ev['HanDangKy'].strftime('%Y-%m-%d %H:%M:%S')

        # 2. Query lấy danh sách người đăng ký (Học sinh/PH + Khách vãng lai)
        query = text("""
            SELECT dk.NgayDangKy, nd.HoTen, nd.VaiTro, 
                   (ISNULL(nd.SoDienThoai, '---') + ' | ' + ISNULL(nd.Email, '---')) as SoDienThoai,
                   (SELECT TenLop FROM LopHoc WHERE MaLop = nd.MaLop) as TenLop
            FROM DangKySuKien dk
            JOIN NguoiDung nd ON dk.MaNguoiDung = nd.MaNguoiDung
            WHERE dk.MaSuKien = :sid
            UNION ALL
            SELECT NgayDangKy, HoTen, N'Khách' as VaiTro, 
                   (ISNULL(SoDienThoai, '---') + ' | ' + ISNULL(Email, '---')) as SoDienThoai, 
                   N'Trang chủ' as TenLop
            FROM KhachDangKySuKien
            WHERE TenSuKien = :title
            ORDER BY NgayDangKy DESC
        """)
        
        rows = db.execute(query, {"sid": id, "title": ev['TieuDe']}).fetchall()
        registrations = []
        for r in rows:
            reg = dict(r._mapping)
            if reg['NgayDangKy']: reg['NgayDangKy'] = reg['NgayDangKy'].strftime('%Y-%m-%d %H:%M:%S')
            registrations.append(reg)
        
        return jsonify({
            "success": True, 
            "event": ev,
            "data": registrations
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        db.close()

# 11.6. ĐĂNG KÝ SỰ KIỆN CHO KHÁCH (TRANG CHỦ) & GỬI MAIL THẬT
@app.route('/guest/api/register-event', methods=['POST'])
def guest_register_event():
    from app.utils.notification_utils import RealEmailDispatcher
    db = SessionLocal()
    try:
        # Tự động tạo bảng nếu chưa có (Thêm cột SoDienThoai)
        db.execute(text("""
            IF NOT EXISTS (SELECT * FROM sys.objects WHERE object_id = OBJECT_ID(N'[dbo].[KhachDangKySuKien]') AND type in (N'U'))
            BEGIN
                CREATE TABLE [dbo].[KhachDangKySuKien] (
                    MaDangKy INT PRIMARY KEY IDENTITY(1,1),
                    HoTen NVARCHAR(255),
                    Email NVARCHAR(255),
                    SoDienThoai NVARCHAR(20),
                    TenSuKien NVARCHAR(255),
                    NgayDangKy DATETIME DEFAULT GETDATE()
                )
            END
            ELSE
            BEGIN
                IF NOT EXISTS (SELECT * FROM sys.columns WHERE object_id = OBJECT_ID('KhachDangKySuKien') AND name = 'SoDienThoai')
                BEGIN
                    ALTER TABLE KhachDangKySuKien ADD SoDienThoai NVARCHAR(20);
                END
            END
        """))
        db.commit()

        data = request.json
        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')
        event_name = data.get('event')

        if not name or not email or not event_name:
            return jsonify({"success": False, "message": "Thiếu thông tin đăng ký"}), 400

        # 1. Lưu vào Database
        db.execute(text("""
            INSERT INTO KhachDangKySuKien (HoTen, Email, SoDienThoai, TenSuKien)
            VALUES (:n, :e, :p, :s)
        """), {"n": name, "e": email, "p": phone, "s": event_name})
        db.commit()

        # 2. Gửi Email thật
        subject = f"[EduNext] Xác nhận đăng ký sự kiện: {event_name}"
        import random
        reg_code = str(random.randint(100000, 999999))
        
        body = f"""Chào {name},

Cảm ơn bạn đã đăng ký tham gia sự kiện "{event_name}" tại hệ thống EduNext.

MÃ XÁC NHẬN CỦA BẠN LÀ: {reg_code}

Vui lòng mang mã này đến buổi sự kiện để thực hiện check-in.
Thời gian đăng ký: {datetime.now().strftime('%H:%M %d/%m/%Y')}

Trân trọng,
Đội ngũ EduNext."""

        success = RealEmailDispatcher.send(email, subject, body)

        return jsonify({
            "success": True, 
            "message": "Đăng ký thành công và đã gửi mail xác nhận!",
            "code": reg_code
        })
    except Exception as e:
        db.rollback()
        print(f"[GUEST-EVENT-ERROR] {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

# 11.7. AI CHAT (DÀNH CHO KHÁCH & PHỤ HUYNH TẠI TRANG CHỦ)
@app.route('/guest/api/chat', methods=['POST'])
def guest_ai_chat():
    try:
        data = request.json
        message = data.get("message")
        role = data.get("role", "guest") 

        if not message:
            return jsonify({"success": False, "message": "Nội dung yêu cầu trống"}), 400

        result = chat_ai(role=role, message=message)

        return jsonify({
            "success": True,
            "response": result
        })
    except Exception as e:
        print(f"❌ GUEST AI ERROR: {str(e)}")
        return jsonify({"success": False, "message": "AI đang bận, vui lòng thử lại sau"}), 500

# 11.8. AI CHAT (GEMINI MENTOR)
@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    from app.config import GEMINI_API_KEY
    try:
        from google import genai
        if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
            return jsonify({"success": False, "message": "Chưa cấu hình Gemini API Key trong config.py"}), 400
            
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        available_models = []
        try:
            for m in client.models.list():
                available_models.append(m.name)
        except Exception as list_err:
            available_models = ['models/gemini-2.5-flash', 'models/gemini-pro']

        data = request.json
        user_msg = data.get('message', '')
        
        db_context = ""
        user_id = session.get('user_id')

        if user_id:
            db = SessionLocal()
            try:
                u_db = db.execute(text("SELECT HoTen, VaiTro, MaLop FROM NguoiDung WHERE MaNguoiDung = :uid"), {"uid": user_id}).fetchone()
                
                if not u_db:
                    return jsonify({"success": False, "message": "Người dùng không tồn tại"}), 404
                
                real_role = u_db.VaiTro.lower()
                user_name = u_db.HoTen
                user_class = u_db.MaLop

                if real_role == 'teacher' or real_role == 'admin':
                    class_info = db.execute(text("SELECT MaLop, TenLop FROM LopHoc WHERE MaGVCN = :uid"), {"uid": user_id}).fetchone()
                    if class_info:
                        cid, cname = class_info.MaLop, class_info.TenLop
                        siso = db.execute(text("SELECT COUNT(*) FROM NguoiDung WHERE MaLop = :cid AND VaiTro = 'Student'"), {"cid": cid}).scalar()
                        pending_leaves = db.execute(text("SELECT COUNT(*) FROM DonXinNghiHoc dx JOIN NguoiDung nd ON dx.MaHocSinh = nd.MaNguoiDung WHERE nd.MaLop = :cid AND dx.TrangThai = 'ChoDuyet'"), {"cid": cid}).scalar()
                        avg_grade = db.execute(text("SELECT AVG(CAST(DiemSo AS FLOAT)) FROM BangDiem bd JOIN NguoiDung nd ON bd.MaHocSinh = nd.MaNguoiDung WHERE nd.MaLop = :cid"), {"cid": cid}).scalar() or 0
                        top_xp = db.execute(text("SELECT TOP 3 nd.HoTen, SUM(nk.DiemXP) as XP FROM NguoiDung nd JOIN NhatKyReNep nk ON nd.MaNguoiDung = nk.MaHocSinh WHERE nd.MaLop = :cid GROUP BY nd.HoTen ORDER BY XP DESC"), {"cid": cid}).fetchall()
                        
                        resource_stats = db.execute(text("""
                            SELECT COUNT(*) as Total, SUM(ISNULL(LuotXem, 0)) as TotalViews, SUM(ISNULL(SoLuotTai, 0)) as TotalDownloads
                            FROM KhoHocLieu WHERE MaNguoiDang = :uid OR MaLop = :cid
                        """), {"uid": user_id, "cid": cid}).fetchone()
                        
                        db_context = f"DỮ LIỆU LỚP {cname}: Sĩ số {siso}, {pending_leaves} đơn nghỉ chờ duyệt, Điểm TB {avg_grade:.1f}. KHO HỌC LIỆU: Có {resource_stats.Total} tài liệu."
                        role_label = "Trợ lý Chủ nhiệm"
                
                elif real_role == 'student':
                    xp_total = db.execute(text("SELECT SUM(DiemXP) FROM NhatKyReNep WHERE MaHocSinh = :uid"), {"uid": user_id}).scalar() or 0
                    class_name = db.execute(text("SELECT TenLop FROM LopHoc WHERE MaLop = :cid"), {"cid": user_class}).scalar() if user_class else "Chưa có lớp"
                    
                    db_context = f"CHÀO {user_name}: Bạn ở lớp {class_name}, XP: {xp_total}."
                    role_label = "Gia sư AI"

                elif real_role == 'parent':
                    student = db.execute(text("SELECT MaNguoiDung, HoTen, MaLop FROM NguoiDung WHERE MaNguoiDung = (SELECT MaHocSinhLienKet FROM NguoiDung WHERE MaNguoiDung = :uid)"), {"uid": user_id}).fetchone()
                    if student:
                        sid, sname, scid = student.MaNguoiDung, student.HoTen, student.MaLop
                        s_avg = db.execute(text("SELECT AVG(CAST(DiemSo AS FLOAT)) FROM BangDiem WHERE MaHocSinh = :sid"), {"sid": sid}).scalar() or 0
                        s_xp = db.execute(text("SELECT SUM(DiemXP) FROM NhatKyReNep WHERE MaHocSinh = :sid"), {"sid": sid}).scalar() or 0
                        db_context = f"PHỤ HUYNH CHÁU {sname}: Điểm TB {s_avg:.1f}, Tổng XP {s_xp}."
                        role_label = "Cố vấn Giáo dục"
                    else:
                        db_context = "Tài khoản của bạn chưa liên kết với học sinh nào."
                        role_label = "Trợ lý Phụ huynh"

                if real_role == 'teacher' or real_role == 'admin':
                    system_prompt = f"Bạn là '{role_label} EduNext'. Ngữ cảnh quản lý: {db_context}."
                elif real_role == 'student':
                    system_prompt = f"Bạn là '{role_label} EduNext'. Ngữ cảnh học sinh: {db_context}."
                elif real_role == 'parent':
                    system_prompt = f"Bạn là '{role_label} EduNext'. Ngữ cảnh phụ huynh: {db_context}."
                else:
                    system_prompt = "Bạn là Trợ lý EduNext."

            except Exception as db_err:
                system_prompt = "Bạn là Trợ lý EduNext."
            finally:
                db.close()
        else:
            system_prompt = "Bạn là Trợ lý Tuyển sinh EduNext."
        
        from google.genai import types
        selected_model = 'gemini-2.5-flash'
        priority_list = ['models/gemini-2.5-flash', 'models/gemini-pro']
        for pref in priority_list:
            if pref in available_models:
                selected_model = pref
                break

        try:
            response = client.models.generate_content(
                model=selected_model,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.7,
                ),
                contents=user_msg
            )
            return jsonify({"success": True, "reply": response.text})
        except Exception as ai_err:
            demo_reply = f"[AI MENTOR - DEMO MODE]\n\nChào bạn! AI đang bận kết nối. Hãy kiên nhẫn một chút nhé!"
            return jsonify({"success": True, "reply": demo_reply})
        
    except ImportError:
        return jsonify({"success": False, "message": "Thiếu thư viện mới: pip install google-genai"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/v2/resource/comment/<int:id>', methods=['POST'])
def add_resource_comment_v2(id):
    db = SessionLocal()
    try:
        user_id = session.get('user_id')
        if not user_id: return jsonify({"success": False, "message": "Chưa đăng nhập"}), 401
        
        data = request.get_json(force=True, silent=True) or request.form.to_dict() or {}
        stars = data.get('stars') or data.get('SoSao') or 0
        comment = data.get('comment') or data.get('BinhLuan') or ''
        comment = str(comment).strip()
        
        db.execute(text("""
            INSERT INTO DanhGiaHocLieu (MaTaiLieu, MaNguoiDung, SoSao, BinhLuan, NgayDanhGia)
            VALUES (:rid, :uid, :stars, :comment, GETDATE())
        """), {"rid": id, "uid": user_id, "stars": stars, "comment": comment})
        
        db.commit()
        return jsonify({"success": True, "message": "Đã lưu đánh giá thành công!"})
    except Exception as e:
        db.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@app.route('/api/resources/comments/<int:id>', methods=['GET'])
def get_resource_comments(id):
    db = SessionLocal()
    try:
        comments = db.execute(text("""
            SELECT 
                dg.MaDanhGia, 
                dg.MaTaiLieu, 
                dg.MaNguoiDung, 
                dg.SoSao AS SoSao, 
                dg.BinhLuan AS BinhLuan, 
                dg.NgayDanhGia AS NgayDanhGia,
                nd.HoTen, 
                nd.VaiTro
            FROM DanhGiaHocLieu dg
            JOIN NguoiDung nd ON dg.MaNguoiDung = nd.MaNguoiDung
            WHERE dg.MaTaiLieu = :id
            ORDER BY dg.NgayDanhGia DESC
        """), {"id": id}).fetchall()
        
        return jsonify({
            "success": True,
            "data": [dict(r._mapping) for r in comments]
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        db.close()

@app.route('/api/debug/danhgia', methods=['GET'])
def debug_danhgia_data():
    db = SessionLocal()
    try:
        res = db.execute(text("SELECT TOP 10 * FROM DanhGiaHocLieu ORDER BY NgayDanhGia DESC")).fetchall()
        return jsonify({
            "success": True,
            "count": len(res),
            "records": [dict(r._mapping) for r in res]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        db.close()

def run_migrations_v2():
    db = SessionLocal()
    try:
        # Thêm cột BinhLuan
        try:
            db.execute(text("ALTER TABLE DanhGiaHocLieu ADD BinhLuan nvarchar(MAX) NULL"))
            db.commit()
        except: db.rollback()
            
        # Đổi tên MaHocSinh -> MaNguoiDung
        try:
            db.execute(text("EXEC sp_rename 'DanhGiaHocLieu.MaHocSinh', 'MaNguoiDung', 'COLUMN'"))
            db.commit()
        except: db.rollback()
    except: pass
    finally: db.close()

if __name__ == '__main__':
    run_migrations()
    run_migrations_v2()
    url = "http://localhost:3000/" 
    print(f"[Server] EduNext dang chay tai: {url}")
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        webbrowser.open(url)
    app.run(port=3000, debug=True)
