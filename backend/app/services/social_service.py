from sqlalchemy import text
from datetime import datetime

class SocialService:
    @staticmethod
    def toggle_like(db, user_id, object_type, object_id):
        try:
            # Ép kiểu để đảm bảo an toàn dữ liệu
            u_id = int(user_id)
            o_id = int(object_id)
            
            # Kiểm tra xem đã like chưa
            check_query = text("""
                SELECT MaTuongTac FROM TuongTac 
                WHERE MaNguoiDung = :uid AND LoaiDoiTuong = :type AND MaDoiTuong = :oid
            """)
            existing = db.execute(check_query, {"uid": u_id, "type": object_type, "oid": o_id}).fetchone()
            
            if existing:
                # Nếu đã có thì xóa (Unlike)
                db.execute(text("DELETE FROM TuongTac WHERE MaTuongTac = :id"), {"id": existing[0]})
                action = "unliked"
            else:
                # Nếu chưa có thì thêm (Like)
                db.execute(text("""
                    INSERT INTO TuongTac (LoaiDoiTuong, MaDoiTuong, MaNguoiDung, LoaiTuongTac)
                    VALUES (:type, :oid, :uid, 'Like')
                """), {"type": object_type, "oid": o_id, "uid": u_id})
                action = "liked"
                
            db.commit()
            return action
        except Exception as e:
            db.rollback()
            print(f"[SocialService Error] toggle_like: {str(e)}")
            raise e

    @staticmethod
    def add_comment(db, user_id, object_type, object_id, content):
        try:
            if not content or not content.strip():
                raise ValueError("Nội dung bình luận không được để trống")
            
            u_id = int(user_id)
            o_id = int(object_id)
                
            db.execute(text("""
                INSERT INTO BinhLuan (LoaiDoiTuong, MaDoiTuong, MaNguoiDung, NoiDung)
                VALUES (:type, :oid, :uid, :content)
            """), {"type": object_type, "oid": o_id, "uid": u_id, "content": content})
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            print(f"[SocialService Error] add_comment: {str(e)}")
            raise e

    @staticmethod
    def get_interactions(db, object_type, object_id, current_user_id=None):
        try:
            o_id = int(object_id)
            # Lấy danh sách người like
            likers_query = text("""
                SELECT nd.HoTen 
                FROM TuongTac tt
                JOIN NguoiDung nd ON tt.MaNguoiDung = nd.MaNguoiDung
                WHERE tt.LoaiDoiTuong = :type AND tt.MaDoiTuong = :oid
            """)
            likers = db.execute(likers_query, {"type": object_type, "oid": o_id}).fetchall()
            liker_names = [r.HoTen for r in likers]
            
            # Kiểm tra user hiện tại đã like chưa
            is_liked = False
            if current_user_id:
                u_id = int(current_user_id)
                check_like = any(r.HoTen == db.execute(text("SELECT HoTen FROM NguoiDung WHERE MaNguoiDung = :uid"), {"uid": u_id}).scalar() for r in likers)
                # Tối ưu hơn: check_like trực tiếp bằng ID
                is_liked = any(db.execute(text("SELECT 1 FROM TuongTac WHERE MaNguoiDung = :uid AND LoaiDoiTuong = :type AND MaDoiTuong = :oid"), {"uid": u_id, "type": object_type, "oid": o_id}).fetchone() for _ in [1])

            # Lấy danh sách bình luận
            comments_query = text("""
                SELECT bl.*, nd.HoTen, nd.AnhDaiDien
                FROM BinhLuan bl
                JOIN NguoiDung nd ON bl.MaNguoiDung = nd.MaNguoiDung
                WHERE bl.LoaiDoiTuong = :type AND bl.MaDoiTuong = :oid
                ORDER BY bl.NgayBinhLuan DESC
            """)
            comments_res = db.execute(comments_query, {"type": object_type, "oid": o_id}).fetchall()
            comments = []
            for c in comments_res:
                comments.append({
                    "MaBinhLuan": c.MaBinhLuan, "HoTen": c.HoTen, "AnhDaiDien": c.AnhDaiDien,
                    "NoiDung": c.NoiDung, "NgayBinhLuan": c.NgayBinhLuan.isoformat() if c.NgayBinhLuan else None
                })
            
            return {
                "like_count": len(liker_names),
                "liker_names": liker_names,
                "is_liked": is_liked,
                "comments": comments
            }
        except Exception as e:
            print(f"[SocialService Error] get_interactions: {str(e)}")
            return {"like_count": 0, "liker_names": [], "is_liked": False, "comments": []}
        except Exception as e:
            print(f"[SocialService Error] get_interactions: {str(e)}")
            return {"like_count": 0, "is_liked": False, "comments": []}
    @staticmethod
    def get_user_notifications(db, user_id):
        try:
            uid = int(user_id)
            all_notifs = []
            
            # 1. Lấy thông báo từ ThongBao
            ann_query = text("""
                SELECT tt.MaTuongTac as SortID, nd.HoTen, nd.AnhDaiDien, 'liked' as Action, 'ThongBao' as ObjectType, tb.MaThongBao as ObjectID, tb.TieuDe as ObjectTitle
                FROM TuongTac tt
                JOIN NguoiDung nd ON tt.MaNguoiDung = nd.MaNguoiDung
                JOIN ThongBao tb ON tt.MaDoiTuong = tb.MaThongBao
                WHERE tb.MaNguoiGui = :uid AND tt.LoaiDoiTuong = 'ThongBao' AND tt.MaNguoiDung <> :uid
                UNION ALL
                SELECT bl.MaBinhLuan as SortID, nd.HoTen, nd.AnhDaiDien, 'commented' as Action, 'ThongBao' as ObjectType, tb.MaThongBao as ObjectID, tb.TieuDe as ObjectTitle
                FROM BinhLuan bl
                JOIN NguoiDung nd ON bl.MaNguoiDung = nd.MaNguoiDung
                JOIN ThongBao tb ON bl.MaDoiTuong = tb.MaThongBao
                WHERE tb.MaNguoiGui = :uid AND bl.LoaiDoiTuong = 'ThongBao' AND bl.MaNguoiDung <> :uid
            """)
            res_ann = db.execute(ann_query, {"uid": uid}).fetchall()
            for r in res_ann:
                all_notifs.append({
                    "SortID": r.SortID, "HoTen": r.HoTen, "AnhDaiDien": r.AnhDaiDien,
                    "Action": r.Action, "ObjectType": r.ObjectType, "ObjectID": r.ObjectID, "ObjectTitle": r.ObjectTitle,
                    "Time": datetime.now().isoformat() # Tạm thời lấy giờ hiện tại
                })

            # 2. Lấy thông báo từ SuKien
            ev_query = text("""
                SELECT tt.MaTuongTac as SortID, nd.HoTen, nd.AnhDaiDien, 'liked' as Action, 'SuKien' as ObjectType, sk.MaSuKien as ObjectID, sk.TieuDe as ObjectTitle
                FROM TuongTac tt
                JOIN NguoiDung nd ON tt.MaNguoiDung = nd.MaNguoiDung
                JOIN SuKien sk ON tt.MaDoiTuong = sk.MaSuKien
                WHERE sk.MaNguoiTao = :uid AND tt.LoaiDoiTuong = 'SuKien' AND tt.MaNguoiDung <> :uid
                UNION ALL
                SELECT bl.MaBinhLuan as SortID, nd.HoTen, nd.AnhDaiDien, 'commented' as Action, 'SuKien' as ObjectType, sk.MaSuKien as ObjectID, sk.TieuDe as ObjectTitle
                FROM BinhLuan bl
                JOIN NguoiDung nd ON bl.MaNguoiDung = nd.MaNguoiDung
                JOIN SuKien sk ON bl.MaDoiTuong = sk.MaSuKien
                WHERE sk.MaNguoiTao = :uid AND bl.LoaiDoiTuong = 'SuKien' AND bl.MaNguoiDung <> :uid
            """)
            res_ev = db.execute(ev_query, {"uid": uid}).fetchall()
            for r in res_ev:
                all_notifs.append({
                    "SortID": r.SortID, "HoTen": r.HoTen, "AnhDaiDien": r.AnhDaiDien,
                    "Action": r.Action, "ObjectType": r.ObjectType, "ObjectID": r.ObjectID, "ObjectTitle": r.ObjectTitle,
                    "Time": datetime.now().isoformat()
                })

            # Sắp xếp theo SortID giảm dần
            all_notifs.sort(key=lambda x: x['SortID'], reverse=True)
            return all_notifs[:15]
        except Exception as e:
            print(f"[SocialService Error] get_user_notifications: {str(e)}")
            return []
