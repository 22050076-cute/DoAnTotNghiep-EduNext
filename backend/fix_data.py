from sqlalchemy import create_engine, text
import urllib.parse

# DB Config
USERNAME = 'sa'
PASSWORD = '123'
SERVER = '127.0.0.1'
PORT = '1433' 
DATABASE = 'LopHocSo'
DRIVER = 'ODBC Driver 17 for SQL Server' 

params = urllib.parse.quote_plus(
    f"DRIVER={{{DRIVER}}};SERVER={SERVER},{PORT};DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD};Encrypt=yes;TrustServerCertificate=yes;"
)
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")

sql_script = """
SET IDENTITY_INSERT [dbo].[KhoHocLieu] ON;
IF NOT EXISTS (SELECT 1 FROM [dbo].[KhoHocLieu] WHERE [MaTaiLieu] = 30)
    INSERT INTO [dbo].[KhoHocLieu] ([MaTaiLieu], [TenTaiLieu], [LoaiFile], [MaMonHoc], [MaNguoiDang], [NgayDang], [MoTa]) 
    VALUES (30, N'Hệ sinh thái EduNext v4.0', 'PDF', 1, 1, GETDATE(), N'Tài liệu hướng dẫn sử dụng nền tảng số.');
IF NOT EXISTS (SELECT 1 FROM [dbo].[KhoHocLieu] WHERE [MaTaiLieu] = 31)
    INSERT INTO [dbo].[KhoHocLieu] ([MaTaiLieu], [TenTaiLieu], [LoaiFile], [MaMonHoc], [MaNguoiDang], [NgayDang], [MoTa]) 
    VALUES (31, N'Cẩm nang Phụ huynh hiện đại', 'PDF', 2, 1, GETDATE(), N'Bí quyết đồng hành cùng con trong kỷ nguyên số.');
SET IDENTITY_INSERT [dbo].[KhoHocLieu] OFF;

UPDATE [dbo].[KhoHocLieu] SET [NgayDang] = GETDATE();
"""

with engine.connect() as conn:
    print("Final attempt with Admin ID...")
    for statement in sql_script.split(';'):
        stmt = statement.strip()
        if stmt:
            try:
                conn.execute(text(stmt))
            except Exception as e:
                print(f"Error: {str(e)[:100]}")
    conn.commit()
    print("Done.")
