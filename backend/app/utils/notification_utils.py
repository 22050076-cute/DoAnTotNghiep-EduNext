import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from app.config import SMTP_SERVER, SMTP_PORT, SMTP_EMAIL, SMTP_PASSWORD

class RealEmailDispatcher:
    @staticmethod
    def send(receiver_email, subject, content):
        """Gửi email thật qua SMTP server"""
        if not SMTP_EMAIL or "your-email" in SMTP_EMAIL:
            print("\033[93m[EMAIL WARNING]\033[0m Chưa cấu hình email thật. Đang dùng Mock thay thế.")
            return MockEmailDispatcher.send(receiver_email, subject, content)

        try:
            msg = MIMEMultipart()
            msg['From'] = f"EduNext System <{SMTP_EMAIL}>"
            msg['To'] = receiver_email
            msg['Subject'] = subject

            msg.attach(MIMEText(content, 'plain', 'utf-8'))

            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            text = msg.as_string()
            server.sendmail(SMTP_EMAIL, receiver_email, text)
            server.quit()
            
            print(f"\033[92m[EMAIL SUCCESS]\033[0m Đã gửi mail thật tới: {receiver_email}")
            return True
        except Exception as e:
            print(f"\033[91m[EMAIL ERROR]\033[0m Lỗi gửi mail thật: {str(e)}")
            # Fallback về Mock để ít nhất vẫn có log
            return MockEmailDispatcher.send(receiver_email, subject, content)

class MockEmailDispatcher:
    @staticmethod
    def send(receiver_email, subject, content):
        # Sử dụng đường dẫn tuyệt đối tương đối với file này
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.abspath(os.path.join(current_file_dir, "..", ".."))
        log_dir = os.path.join(backend_dir, "logs")
        
        try:
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
                
            log_file = os.path.join(log_dir, "notifications.log")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            log_entry = f"[{timestamp}] SENDING EMAIL TO: {receiver_email}\nSUBJECT: {subject}\nCONTENT: {content}\nStatus: SUCCESS (Simulated)\n" + ("-"*50) + "\n"
            
            # Ghi vào file log
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
                
            # Hiển thị ra terminal để giáo viên thấy lúc demo
            print(f"\n\033[92m[NOTIFICATION HUB]\033[0m Simulated Email sent to: \033[94m{receiver_email}\033[0m")
            print(f"Subject: {subject}\n")
        except Exception as e:
            print(f"\n\033[91m[NOTIFICATION ERROR]\033[0m Failed to send simulation: {str(e)}")


