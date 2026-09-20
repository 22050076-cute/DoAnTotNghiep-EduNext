import pyodbc
import urllib.parse
import os

# Cấu hình kết nối từ config.py (giả định chạy từ thư mục backend)
USERNAME = 'sa'
PASSWORD = '12345678'
SERVER = 'localhost'
DATABASE = 'LopHocSo'
DRIVER = 'ODBC Driver 17 for SQL Server'

connection_string = f"DRIVER={{{DRIVER}}};SERVER={SERVER};DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD};Encrypt=yes;TrustServerCertificate=yes;"

def run_sql_script(script_path):
    try:
        conn = pyodbc.connect(connection_string, autocommit=True)
        cursor = conn.cursor()
        
        with open(script_path, 'r', encoding='utf-8') as f:
            sql_script = f.read()
        
        # SQL Server scripts often contain 'GO' which pyodbc doesn't support directly
        commands = sql_script.split('GO')
        
        for command in commands:
            if command.strip():
                cursor.execute(command)
                print(f"Executed command block.")
                
        conn.close()
        print("\n[SUCCESS] Da cap nhat database thanh cong!")
    except Exception as e:
        print(f"\n[ERROR] Co loi xay ra: {str(e)}")

if __name__ == "__main__":
    script_file = "update_social_tables.sql"
    if os.path.exists(script_file):
        run_sql_script(script_file)
    else:
        print(f"Khong tim thay file {script_file}")
