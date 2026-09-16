from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import urllib.parse

USERNAME = 'sa'
PASSWORD = '123456'
SERVER = '127.0.0.1'
PORT = '50667' 
DATABASE = 'LopHocSo'
DRIVER = 'ODBC Driver 17 for SQL Server' 

params = urllib.parse.quote_plus(
    f"DRIVER={{{DRIVER}}};SERVER={SERVER},{PORT};DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD};Encrypt=yes;TrustServerCertificate=yes;"
)

SQLALCHEMY_DATABASE_URL = f"mssql+pyodbc:///?odbc_connect={params}"

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- CẤU HÌNH GỬI MAIL THẬT (SMTP) ---
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_EMAIL = "thcsedunext@gmail.com" 
SMTP_PASSWORD = "weybmhnnlcwplrlc"  # Mật khẩu ứng dụng của bạn

# --- CẤU HÌNH AI (GEMINI) ---
# Sử dụng Key từ dự án THCS đang chạy tốt
GEMINI_API_KEY = "AQ.Ab8RN6JHIQCVKUkxJJK4fzGjgD9GN1vn1fw_vHuTtaCXlpbSGw"

