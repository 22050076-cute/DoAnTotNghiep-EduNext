import pyodbc
import os

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
        
        commands = sql_script.split('GO')
        
        for command in commands:
            if command.strip():
                cursor.execute(command)
                print(f"Executed command block.")
                
        conn.close()
        print("\n[SUCCESS] Migration completed!")
    except Exception as e:
        print(f"\n[ERROR]: {str(e)}")

if __name__ == "__main__":
    run_sql_script("update_social_features.sql")
