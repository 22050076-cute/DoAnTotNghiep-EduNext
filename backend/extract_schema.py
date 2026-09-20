import pyodbc
import urllib.parse

USERNAME = 'sa'
PASSWORD = '12345678'
SERVER = 'localhost'
DATABASE = 'LopHocSo'
DRIVER = 'ODBC Driver 17 for SQL Server'

connection_string = f"DRIVER={{{DRIVER}}};SERVER={SERVER};DATABASE={DATABASE};UID={USERNAME};PWD={PASSWORD};Encrypt=yes;TrustServerCertificate=yes;"

def get_schema():
    try:
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        sql_output = []
        sql_output.append(f"USE [{DATABASE}];")
        sql_output.append("GO\n")
        
        # Get all tables
        cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'")
        tables = [row[0] for row in cursor.fetchall()]
        
        for table in tables:
            sql_output.append(f"-- Table: {table}")
            sql_output.append(f"CREATE TABLE [{table}] (")
            
            # Get columns
            cursor.execute(f"SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE, COLUMN_DEFAULT FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{table}' ORDER BY ORDINAL_POSITION")
            cols = cursor.fetchall()
            
            col_defs = []
            for col in cols:
                name, dtype, length, nullable, default = col
                type_def = f"[{name}] {dtype}"
                if length:
                    if length == -1: type_def += "(MAX)"
                    else: type_def += f"({length})"
                
                type_def += " NULL" if nullable == 'YES' else " NOT NULL"
                if default:
                    type_def += f" DEFAULT {default}"
                
                col_defs.append("    " + type_def)
            
            sql_output.append(",\n".join(col_defs))
            sql_output.append(");\nGO\n")
            
        conn.close()
        return "\n".join(sql_output)
    except Exception as e:
        return f"-- Error: {str(e)}"

if __name__ == "__main__":
    schema_sql = get_schema()
    with open("LopHocSo.sql", "w", encoding="utf-8") as f:
        f.write(schema_sql)
    print("Backup completed: LopHocSo.sql")
