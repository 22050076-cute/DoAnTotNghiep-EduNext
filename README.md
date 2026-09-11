# 🎓 EDUNEXT - NỀN TẢNG LỚP HỌC SỐ THÔNG MINH
> **Giải pháp chuyển đổi số toàn diện hỗ trợ công tác chủ nhiệm & quản trị trường học THCS.**

<p align="center">
  <img src="logo.png" alt="EduNext Logo" width="150">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Digital_Classroom-blue?style=for-the-badge&logo=google-classroom" alt="Platform">
  <img src="https://img.shields.io/badge/Backend-Flask-red?style=for-the-badge&logo=flask" alt="Flask">
  <img src="https://img.shields.io/badge/AI-Gemini_2.5_Flash-orange?style=for-the-badge&logo=google-gemini" alt="Gemini AI">
  <img src="https://img.shields.io/badge/Database-SQL_Server-blue?style=for-the-badge&logo=microsoft-sql-server" alt="SQL Server">
</p>

---

## 🌟 Tổng quan dự án
**EduNext** là một hệ sinh thái giáo dục số hiện đại, được thiết kế để tối ưu hóa công tác quản lý của nhà trường, hỗ trợ giảng dạy của giáo viên và tăng cường sự kết nối giữa gia đình - nhà trường. Hệ thống áp dụng mô hình quản trị tập trung với phân quyền đa vai trò (RBAC), đảm bảo tính bảo mật và hiệu quả vận hành.

### 🚀 Vai trò và Tính năng chính
Hệ thống được thiết kế riêng biệt cho 5 nhóm người dùng:

1.  **🛡️ QUẢN TRỊ VIÊN (ADMIN):**
    *   **Quản lý hạ tầng:** Khởi tạo khối học, lớp học và phân công giáo viên chủ nhiệm.
    *   **Quản trị tài khoản:** Quản lý danh định toàn bộ nhân sự (GV, HS, PH), cấp quyền và đặt lại mật khẩu.
    *   **Giám sát hệ thống:** Theo dõi Log hoạt động thời gian thực và thống kê chuyên cần, thi đua toàn trường.
    *   **Cấu hình hệ thống:** Thiết lập các thông số vận hành chung của nhà trường.

2.  **👩‍🏫 GIÁO VIÊN CHỦ NHIỆM:**
    *   **Điểm danh thông minh:** Ghi nhận chuyên cần và đồng bộ đơn xin nghỉ phép từ phụ huynh.
    *   **Quản lý nề nếp:** Ghi nhật ký thi đua, cộng/trừ điểm XP tích hợp hệ thống Gamification.
    *   **Trợ lý AI:** Sử dụng Gemini AI để viết nhận xét học sinh tự động và phân tích kết quả học tập.

3.  **👨‍👩‍👧 PHỤ HUYNH:**
    *   **Sổ liên lạc điện tử:** Theo dõi điểm số, chuyên cần và nhận xét của giáo viên ngay lập tức.
    *   **Tương tác AI:** Tư vấn tâm lý giáo dục và lộ trình học tập cho con em thông qua AI Mentor.

4.  **🎓 HỌC SINH:**
    *   **Dashboard học tập:** Xem thời khóa biểu, bài tập và kho tài liệu số phong phú.
    *   **Bảng xếp hạng (Leaderboard):** Thúc đẩy thi đua thông qua hệ thống tích lũy điểm XP.

5.  **🌐 KHÁCH (GUEST):**
    *   **Thông tin công khai:** Xem tin tức, sự kiện và các hoạt động nổi bật của nhà trường.
    *   **Kho học liệu mở:** Truy cập các tài liệu giảng dạy được giáo viên chia sẻ công khai.

---

## 🏗️ Kiến trúc hệ thống
Hệ thống được xây dựng trên mô hình **3-Layer Architecture** đảm bảo tính tách biệt giữa giao diện, logic và dữ liệu:

*   **Tầng trình diễn (Frontend):** HTML5, CSS3, JavaScript (ES6+), Phosphor Icons.
*   **Tầng nghiệp vụ (Backend):** Python Flask Web Server.
*   **Tầng dữ liệu:** Microsoft SQL Server.
*   **AI Integration:** Google Gemini 2.5 Flash API.

---

## 📂 Cấu trúc thư mục
```text
chuyende2/
├── backend/                # Xử lý logic và API phía máy chủ
│   ├── app/                
│   │   ├── routes/         # API Endpoints (Academic, Social, LMS, Admin)
│   │   ├── services/       # Business Logic & AI Integration
│   │   └── config.py       # Cấu hình DB và AI Key
│   ├── main.py             # Entry point của ứng dụng
│   └── LopHocSo.sql        # Script khởi tạo Database
├── frontend/               # Giao diện người dùng
│   ├── static/             # Tài nguyên tĩnh (CSS, JS, Images)
│   └── templates/          
│       ├── Admin/          # Dashboard Quản trị viên
│       ├── GV/             # Giao diện Giáo viên
│       ├── HS/             # Giao diện Học sinh
│       └── PH/             # Giao diện Phụ huynh
└── README.md               # Tài liệu dự án
```

---

## ⚡ Cài đặt và Khởi chạy

### 1. Cơ sở dữ liệu
*   Cài đặt **SQL Server** và tạo Database `LopHocSo`.
*   Chạy script `backend/LopHocSo.sql` để tạo cấu trúc và dữ liệu mẫu.

### 2. Môi trường Python
```bash
pip install flask flask-cors sqlalchemy pyodbc google-genai
```

### 3. Khởi chạy
```bash
cd backend
python main.py
```
Truy cập: **[http://localhost:5000](http://localhost:5000)**

---

## ✍️ Đội ngũ thực hiện
*   **Hạ Văn Minh** - MSSV: *22050076*
*   **Quách Thị Thu** - MSSV: *22050034*
*   **Giảng viên hướng dẫn:** ThS. Nguyễn Thanh Sơn
*   **Trường:** Đại học Bình Dương - Khoa CNTT, Robot & AI.

---
*© 2026 EduNext Platform - Nền tảng số vì sự nghiệp giáo dục.*
