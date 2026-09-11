# -*- coding: utf-8 -*-
import google.generativeai as genai  # Sử dụng thư viện chuẩn liên thông mượt mà với Flask
from app.config import GEMINI_API_KEY

# ===== CONFIG GEMINI KEY =====
genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.0-flash"  # Chuyển về dòng 2.0 Flash theo đúng thiết kế hệ thống v4.0

print(f"✅ EduNext AI Service Ready ({MODEL_NAME})")

# =================================================================
# 🛡️ SYSTEM PROMPTS (Cải tiến bám sát dữ liệu thực tế)
# =================================================================
SYSTEM_INSTRUCTIONS = {
    "guest": """
        Bạn là Chuyên viên Tư vấn Tuyển sinh ảo của EduNext.
        Nhiệm vụ: Chào đón khách, tư vấn về lịch tuyển sinh, học phí, cơ sở vật chất và các ngành đào tạo.
        Phong cách: Chuyên nghiệp, lịch sự, hiếu khách. 
        Câu mở đầu hay: "Xin chào! 🌟 Mình là trợ lý tuyển sinh EduNext. Rất vui được hỗ trợ bạn tìm hiểu về môi trường học tập tại đây!"
    """,
    "student": """
        Bạn là Gia sư AI thông minh hỗ trợ 12 môn học phổ thông tại hệ thống EduNext.
        Nguyên tắc vàng: KHÔNG BAO GIỜ cho đáp án trực tiếp ngay lập tức.
        Nhiệm vụ: 
        1. Phân tích đề bài.
        2. Gợi ý kiến thức liên quan (công thức, ngữ pháp, sự kiện...).
        3. Hướng dẫn các bước tư duy.
        4. Luôn kết thúc bằng một câu hỏi gợi mở để học sinh tự tìm ra lời giải.
        Phong cách: Kiên nhẫn, khích lệ.
    """,
    "parent": """
        Bạn là Chuyên gia Tư vấn Giáo dục từ hệ thống EduNext.
        Nhiệm vụ: Phân tích kết quả học tập rèn luyện nội bộ của học sinh (Điểm số học kỳ, chuyên cần, tình hình hoàn thành bài tập) để đưa ra lời khuyên thiết thực cho phụ huynh[cite: 20, 26, 129].
        Phong cách: Chuyên sâu, thấu hiểu, mang tính định hướng, dựa hoàn toàn trên số liệu thực[cite: 13, 145].
    """,
    "teacher": """
        Bạn là Trợ lý Quản lý Giáo vụ chuyên nghiệp đồng hành cùng Giáo viên chủ nhiệm THCS[cite: 13, 127].
        Nhiệm vụ: Hỗ trợ giáo viên soạn giáo án, phân tích bảng điểm, tổng hợp tình trạng nề nếp vắng học/thiếu bài tập và soạn tin nhắn trao đổi với phụ huynh[cite: 22, 23, 134, 136].
        Khả năng: Xử lý dữ liệu lớp học, đưa ra lời khuyên sư phạm dựa trên tâm lý học.
        Phong cách: Gọn gàng, logic, hỗ trợ đắc lực.
    """
}

# =================================================================
# 📚 UTILS
# =================================================================
def detect_subject(message):
    subjects = {
        "toán": "Toán học", "văn": "Ngữ văn", "anh": "Tiếng Anh",
        "lý": "Vật lý", "hóa": "Hóa học", "sinh": "Sinh học",
        "sử": "Lịch sử", "địa": "Địa lý", "gdcd": "GDCD",
        "tin": "Tin học", "công nghệ": "Công nghệ", "nhạc": "Âm nhạc"
    }
    msg = message.lower()
    for key, val in subjects.items():
        if key in msg: return val
    return "Kiến thức chung"

# =================================================================
# 🤖 CORE CHAT FUNCTION (Phục vụ phân hệ Chat Bong Bóng nội bộ)
# =================================================================
def chat_ai(role, message, history=None):
    """
    Hàm xử lý hội thoại chat thông thường qua cơ chế sinh text của Gemini
    """
    try:
        instruction = SYSTEM_INSTRUCTIONS.get(role, "Bạn là trợ lý ảo đa năng.")

        if role == "student":
            subject = detect_subject(message)
            instruction += f"\nHiện tại bạn đang hỗ trợ môn: {subject}."
            
            keywords = ["cho đáp án", "giải hộ", "kết quả là bao nhiêu", "đáp án là gì"]
            if any(k in message.lower() for k in keywords):
                return "Mình rất sẵn lòng hướng dẫn bạn cách giải, nhưng để bạn giỏi hơn, mình sẽ gợi ý từng bước thay vì đưa đáp án ngay nhé! Chúng ta bắt đầu từ bước đầu tiên được không?"

        # Gọi mô hình với cú pháp generate_content chuẩn của google.generativeai
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            system_instruction=instruction
        )
        
        response = model.generate_content(message)
        
        if response and response.text:
            return response.text
        return "AI đang suy nghĩ, bạn chờ chút nhé."

    except Exception as e:
        print(f"❌ ERROR AI SERVICE ({role}):", e)
        return "Hệ thống đang bận một chút, bạn thử lại sau vài giây nhé!"


# =================================================================
# 🎯 NEW FUNCTION: PLACEMENT TEST ANALYSIS (Xử lý định lượng 100%)
# =================================================================
def analyze_placement_test(grade, scores):
    """
    Hàm tiếp nhận bộ điểm thật từ bài làm trắc nghiệm Frontend gửi lên,
    bọc cấu trúc dữ liệu nghiêm ngặt truyền sang Gemini để sinh nhận xét[cite: 40, 139].
    grade: Khối lớp (6, 7, 8, 9)
    scores: Dictionary chứa điểm thật của học sinh (ToanLogic, NgoaiNgu, NguVanDienDat, KHTN)
    """
    try:
        model = genai.GenerativeModel(model_name=MODEL_NAME)
        
        # Áp dụng bản đồ dịch tên nhóm năng lực hiển thị sư phạm [cite: 41]
        name_mapping = {
            "ToanLogic": "Toán học & Tư duy logic",
            "NgoaiNgu": "Năng lực Ngoại ngữ",
            "NguVanDienDat": "Ngữ văn & Diễn đạt",
            "KHTN": "Khoa học Tự nhiên",
            "KHXH": "Khoa học Xã hội",
            "TinHocCongNghe": "Tin học & Công nghệ",
            "TuHocQuanLy": "Tự học & Quản lý thời gian"
        }
        
        # Xây dựng chuỗi Context định lượng sạch [cite: 139]
        score_context = ""
        for key, val in scores.items():
            display_name = name_mapping.get(key, key)
            score_context += f"- Nhóm năng lực {display_name}: {val}/100 điểm.\n"
            
        # Thiết lập Prompt Engineering bọc quy tắc phân lớp và áp lực tuyển sinh 10 [cite: 139, 145]
        prompt = f"""
        Bạn là Chuyên gia khảo thí và Cố vấn giáo dục cao cấp của hệ thống trường THCS EduNext.
        Hãy đưa ra báo cáo phân tích, nhận xét sư phạm dựa HOÀN TOÀN trên kết quả điểm số thực tế thu được từ bài kiểm tra năng lực đầu vào dưới đây của học sinh đăng ký vào Khối {grade}. 
        Tuyệt đối không tự bịa đặt thông số hoặc suy diễn nằm ngoài ngữ cảnh dữ liệu[cite: 145].

        [KẾ TRÚC ĐIỂM SỐ ĐỊNH LƯỢNG THỰC TẾ CỦA HỌC SINH]
        {score_context}

        [YÊU CẦU ĐẦU RA]
        Hãy trả về nội dung bằng tiếng Việt dưới định dạng HTML sạch (chỉ sử dụng các thẻ <p>, <b>, <ul>, <li> để hệ thống hiển thị trực quan lên Dashboard, tuyệt đối không bao bọc trong block code ```html):
        
        1. <b>Đề xuất phân lớp học tập:</b> Gợi ý phân lớp phù hợp với năng lực (Ví dụ: Điểm Toán/Anh từ 80 trở lên xếp vào lớp Chọn mũi nhọn chất lượng cao; nếu có môn dưới 60 xếp vào lớp Tăng cường bổ trợ để lấy lại căn bản kiến thức).
        2. <b>Chỉ ra lỗ hổng kiến thức cốt lõi:</b> Dựa vào nhóm năng lực có điểm số thấp nhất để cảnh báo chi tiết các phần hổng.
        3. <b>Chiến lược hành động hướng tới Tuyển sinh lớp 10:</b> Đề xuất giải pháp ôn tập bứt phá dài hạn, các kỹ năng tự quản lý hoặc khai thác học liệu hệ thống để học sinh bứt phá điểm số.
        """
        
        response = model.generate_content(prompt)
        
        if response and response.text:
            return response.text
        return "<p>Hệ thống AI đang phân tích dữ liệu, vui lòng bấm thử lại.</p>"
        
    except Exception as e:
        print(f"❌ ERROR AT PLACEMENT TEST AI SERVICE:", e)
        return "<p>Dịch vụ phân tích AI đang gặp gián đoạn kết nối trục dữ liệu.</p>"