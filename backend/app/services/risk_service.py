"""Local threshold evaluation; no data is sent to external services."""
import json
import math
from decimal import Decimal
from datetime import date
from sqlalchemy import text

GROUPS = {'ToanLogic': 'Toán học & logic', 'NguVanDienDat': 'Ngữ văn & diễn đạt',
          'NgoaiNgu': 'Ngoại ngữ', 'KHTN': 'Khoa học tự nhiên', 'KHXH': 'Khoa học xã hội',
          'TinHocCongNghe': 'Tin học & công nghệ', 'TuHocQuanLy': 'Tự học & quản lý thời gian'}

def competency_scores(payload):
    try:
        data = json.loads(payload) if isinstance(payload, str) else payload
        values = data.get('chi_tiet_diem', {}) if isinstance(data, dict) else {}
        scores = {}
        for key, label in GROUPS.items():
            value = values.get(key, values.get(label))
            if value is None or isinstance(value, bool):
                continue
            try:
                score = float(value)
                if math.isfinite(score) and 0 <= score <= 100:
                    scores[label] = score
            except (ValueError, TypeError):
                pass
        return scores
    except (ValueError, TypeError, AttributeError):
        return {}

def evaluate_risk(m):
    rules, reasons, missing = [], [], []
    delta = None
    if m.get('hk1') is None or m.get('hk2') is None:
        missing.append('Chưa đủ điểm HK1 và HK2.')
    else:
        delta = Decimal(str(m['hk2'])) - Decimal(str(m['hk1']))
        if delta <= -1:
            rules.append('R1')
            reasons.append(f'HK2 giảm {abs(delta):.2f} điểm so với HK1 (≥ 1).')
    total, present, absent = m.get('attendance_total',0), m.get('attendance_present',0), m.get('unexcused',0)
    att = 100 * present / total if total else None
    parts = []
    if not total:
        missing.append('Chưa có dữ liệu chuyên cần.')
    elif present * 100 < total * 85:
        parts.append(f'Chuyên cần {att:.2f}% < 85%')
    if absent >= 3:
        parts.append(f'Vắng không phép {absent} buổi ≥ 3')
    if parts:
        rules.append('R2'); reasons.append('; '.join(parts))
    due, done = m.get('homework_due',0), m.get('homework_done',0)
    hw = 100 * done / due if due else None
    if not due:
        missing.append('Chưa có bài tập đến hạn.')
    elif done * 100 < due * 70:
        rules.append('R3'); reasons.append(f'Hoàn thành {done}/{due} bài ({hw:.2f}% < 70%).')
    scores = m.get('competencies',{})
    low = [(k,v) for k,v in scores.items() if v < 50]
    if len(scores) < 7:
        missing.append(f'Có dữ liệu {len(scores)}/7 nhóm năng lực.')
    if low:
        rules.append('R4'); reasons.append('Năng lực dưới 50/100: ' + '; '.join(f'{k}: {v:g}' for k,v in low))
    return {'CanhBaoSaSut': bool(rules), 'triggered_rules': rules, 'reasons': reasons, 'missing_data': missing,
            'metrics': {**m, 'delta': float(delta) if delta is not None else None, 'P_att': att, 'P_hw': hw}}

def scan_class(db, cls):
    semesters = db.execute(text('SELECT MaHocKy, NgayBatDau, NgayKetThuc FROM HocKy WHERE MaNamHoc=:year ORDER BY NgayBatDau'), {'year':cls.MaNamHoc}).mappings().all()
    if len(semesters)!=2 or any(not s['NgayBatDau'] or not s['NgayKetThuc'] for s in semesters):
        raise ValueError('Cần cấu hình đủ hai học kỳ và thời gian năm học.')
    start, end = semesters[0]['NgayBatDau'], min(semesters[-1]['NgayKetThuc'],date.today())
    students = db.execute(text("SELECT MaNguoiDung, HoTen FROM NguoiDung WHERE MaLop=:cid AND VaiTro='Student'"),{'cid':cls.MaLop}).mappings().all()
    reports=[]
    for st in students:
        params={'sid':st['MaNguoiDung'],'cid':cls.MaLop,'start':start,'end':end}
        averages=[]
        for sem in semesters:
            value=db.execute(text("""
                SELECT AVG(subject_avg) FROM (
                  SELECT SUM(CAST(DiemSo AS decimal(18,6))*CASE MaLoai WHEN 6 THEN 2 WHEN 7 THEN 3 ELSE 1 END)
                    /SUM(CASE MaLoai WHEN 6 THEN 2 WHEN 7 THEN 3 ELSE 1 END) AS subject_avg
                  FROM BangDiem WHERE MaHocSinh=:sid AND MaHocKy=:semester AND DiemSo IS NOT NULL AND MaLoai BETWEEN 1 AND 7
                  GROUP BY MaMonHoc
                ) scores
            """),{**params,'semester':sem['MaHocKy']}).scalar()
            averages.append(float(value) if value is not None else None)
        att=db.execute(text("""
            SELECT COUNT(*) AS total,COALESCE(SUM(present),0) AS present,COALESCE(SUM(unexcused),0) AS unexcused FROM (
              SELECT CAST(NgayDiemDanh AS date) AS day,
                MIN(CASE WHEN TrangThai IN (N'HienDien',N'Có mặt',N'Muon') THEN 1 ELSE 0 END) AS present,
                MAX(CASE WHEN TrangThai IN (N'VangKP',N'Vang (Khong phep)') THEN 1 ELSE 0 END) AS unexcused
              FROM DiemDanh WHERE MaHocSinh=:sid AND MaLop=:cid AND CAST(NgayDiemDanh AS date) BETWEEN :start AND :end
                AND TrangThai IN (N'HienDien',N'Có mặt',N'Muon',N'VangCP',N'VangKP',N'Vang (Co phep)',N'Vang (Khong phep)')
              GROUP BY CAST(NgayDiemDanh AS date)
            ) days
        """),params).mappings().one()
        hw=db.execute(text("""
            SELECT COUNT(*) AS total,COALESCE(SUM(done),0) AS done FROM (
              SELECT bt.MaBaiTap,CASE WHEN EXISTS(SELECT 1 FROM BaiLam bl WHERE bl.MaBaiTap=bt.MaBaiTap AND bl.MaHocSinh=:sid
                 AND bl.NgayNop<DATEADD(day,1,CAST(:end AS date))) THEN 1 ELSE 0 END AS done
              FROM BaiTap bt JOIN PhanCongGiangDay pc ON bt.MaPhanCong=pc.MaPhanCong
              WHERE pc.MaLop=:cid AND CAST(bt.HanNop AS date) BETWEEN :start AND :end AND bt.HanNop<=GETDATE()
            ) tasks
        """),params).mappings().one()
        payload=db.execute(text("""SELECT TOP 1 DanhGiaAI FROM KetQuaTestNangLuc WHERE MaNguoiDung=:sid
            AND NgayLam<DATEADD(day,1,CAST(:end AS date)) ORDER BY NgayLam DESC,MaKetQua DESC"""),params).scalar()
        metrics={'hk1':averages[0],'hk2':averages[1],'attendance_total':att['total'],'attendance_present':att['present'],
                 'unexcused':att['unexcused'],'homework_due':hw['total'],'homework_done':hw['done'],'competencies':competency_scores(payload)}
        reports.append({'student_id':st['MaNguoiDung'],'ho_ten':st['HoTen'],**evaluate_risk(metrics)})
    return {'success':True,'class_name':cls.TenLop,'scanned_count':len(reports),'period':{'start':str(start),'end':str(end)},
            'has_risk':any(r['CanhBaoSaSut'] for r in reports),'risk_students':[r for r in reports if r['CanhBaoSaSut']],
            'students':reports,'incomplete_count':sum(bool(r['missing_data']) for r in reports)}
