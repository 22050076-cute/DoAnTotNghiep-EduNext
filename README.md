# 🎓 EDUNEXT - NỀN TẢNG HỖ TRỢ CÔNG TÁC CHỦ NHIỆM TẠI TRƯỜNG THCS
> **Đồ án tốt nghiệp Khoa Công nghệ Thông tin, Robot và Trí tuệ Nhân tạo - Trường Đại học Bình Dương.**

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Digital_Classroom-blue?style=for-the-badge&logo=google-classroom" alt="Platform">
  <img src="https://img.shields.io/badge/Backend-Flask-red?style=for-the-badge&logo=flask" alt="Flask">
  <img src="https://img.shields.io/badge/AI-Gemini_2.0_Flash-orange?style=for-the-badge&logo=google-gemini" alt="Gemini AI">
  <img src="https://img.shields.io/badge/Database-SQL_Server-blue?style=for-the-badge&logo=microsoft-sql-server" alt="SQL Server">
</p>

---

## 🌟 Tổng quan dự án
**EduNext** là nền tảng quản trị lớp học tập trung và hỗ trợ công tác chủ nhiệm tại trường Trung học cơ sở (THCS). Hệ thống được xây dựng nhằm giảm tải thủ tục hành chính thủ công cho giáo viên, chuẩn hóa kênh trao đổi giữa nhà trường - gia đình, đồng thời tích hợp mô hình ngôn ngữ lớn **Gemini 2.0 Flash** để phân tích dữ liệu định lượng và phát hiện sớm các trường hợp học sinh có nguy cơ sa sút học lực.

### 🚀 Phân hệ và Vai trò người dùng
Hệ thống được phân quyền bảo mật chặt chẽ theo mô hình **RBAC** (Role-Based Access Control) phục vụ 5 nhóm tác nhân chính:

1.  **🛡️ QUẢN TRỊ VIÊN (ADMIN):**
    *   Quản lý danh sách tài khoản người dùng và phân quyền hệ thống.
    *   Quản lý danh mục năm học, học kỳ, khối lớp, lớp học và phân công giảng dạy.
    *   Giám sát nhật ký hoạt động (System Logs) toàn hệ thống.

2.  **👩‍🏫 GIÁO VIÊN CHỦ NHIỆM & BỘ MÔN:**
    *   **Điểm danh & Nề nếp:** Số hóa quy trình điểm danh chuyên cần hàng ngày và xét duyệt đơn xin nghỉ học trực tuyến của phụ huynh.
    *   **Quản lý học tập:** Giao bài tập, chấm điểm trực tuyến và đồng bộ tự động vào sổ điểm điện tử theo Thông tư 22/2021/TT-BGDĐT.
    *   **Trợ lý AI Gemini 2.0 Flash:** Ứng dụng kỹ thuật Prompt trên dữ liệu có cấu trúc để sinh nhận xét rèn luyện tự động và kích hoạt Rule Engine cảnh báo nguy cơ sa sút.

3.  **👨‍👩‍👧 PHỤ HUYNH:**
    *   Theo dõi thời gian thực tình hình chuyên cần, biểu đồ xu hướng điểm số học kỳ và tình trạng nộp bài tập của con em[cite: 3].
    *   Gửi đơn xin nghỉ học trực tuyến và nhận thông báo/cảnh báo tự động từ nhà trường[cite: 3].

4.  **🎓 HỌC SINH:**
    *   Tra cứu thời khóa biểu, nộp bài tập về nhà và thực hiện bài kiểm tra khảo sát trực tuyến đánh giá **7 nhóm năng lực cốt lõi THCS**[cite: 3].
    *   Theo dõi tiến trình rèn luyện cá nhân hóa và bảng thành tích thi đua (XP)[cite: 3].

5.  **🌐 KHÁCH (GUEST):**
    *   Truy cập cổng thông tin công khai xem tin tức sự kiện và kho học liệu mở của nhà trường[cite: 3].

---

## 🏗️ Kiến trúc & Công nghệ
Hệ thống áp dụng mô hình kiến trúc phân tầng (Layered Architecture) chuẩn mực:
*   **Tầng Giao diện (Frontend):** HTML5, CSS3, JavaScript (ES6+), Bootstrap 5, Chart.js / ApexCharts.
*   **Tầng Nghiệp vụ (Backend):** Python 3.10, Flask Micro-framework RESTful API.
*   **Tầng Dữ liệu (Database):** Microsoft SQL Server (38 bảng thực thể quan hệ chuẩn hóa)[cite: 3].
*   **Tầng Trí tuệ Nhân tạo (AI Engine):** Google Gemini 2.0 Flash SDK (Structured-Data Prompting)[cite: 3].
*   **Dịch vụ thời gian thực & thông báo:** Flask-SocketIO (WebSockets) và Flask-Mail (SMTP Protocol)[cite: 3].

---

## 📂 Cấu trúc thư mục dự án
```text
ATN_BDU/
├── backend/                # Xử lý logic, API và kết nối CSDL
│   ├── app/                
│   │   ├── routes/         # RESTful API Endpoints (Admin, Academic, LMS, Social)
│   │   ├── services/       # Business Logic & Gemini AI Integration
│   │   └── config.py       # Cấu hình chuỗi kết nối MS SQL Server & API Key
│   ├── main.py             # Entry point ứng dụng Flask Web Server
│   └── LopHocSo.sql        # Script khởi tạo Cơ sở dữ liệu (38 bảng thực thể)
├── frontend/               # Giao diện người dùng (Templates & Static)
│   ├── static/             # Tài nguyên tĩnh (CSS, JS, Uploads)
│   └── templates/          # Giao diện HTML theo 4 phân hệ (Admin, GV, HS, PH)
└── README.md               # Tài liệu mô tả đồ án

⚡ Cài đặt và Hướng dẫn Khởi chạy
1. Cơ sở dữ liệu
Cài đặt Microsoft SQL Server và mở công cụ SSMS.

Chạy tệp kịch bản backend/LopHocSo.sql để khởi tạo toàn bộ CSDL LopHocSo (38 bảng thực thể kèm dữ liệu mẫu)[cite: 3].

2. Cài đặt môi trường Python
Điều hướng vào thư mục backend và cài đặt các thư viện phụ thuộc:

cd backend
python -m venv venv
venv\Scripts\activate
pip install flask flask-cors sqlalchemy pyodbc werkzeug google-generativeai flask-socketio flask-mail

3. Khởi chạy ứng dụng

python main.py

Truy cập hệ thống trên trình duyệt tại địa chỉ: http://localhost:3000


✍️ Tác giả và Giảng viên hướng dẫn

Sinh viên thực hiện: Hạ Văn Minh

Mã số sinh viên: 22050076

Lớp: 25TH01

Giảng viên hướng dẫn: ThS. Dương Anh Tuấn

Đơn vị: Viện Trí tuệ Nhân tạo và Chuyển đổi số — Khoa Công nghệ Thông tin, Robot và Trí tuệ Nhân tạo, Trường Đại học Bình Dương.

© 2026 EduNext Platform - Đồ án tốt nghiệp cử nhân Công nghệ Thông tin.