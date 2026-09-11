import codecs

file_path = r'd:\CHUYEN_DE\chuyende2\dataset.txt'
try:
    with codecs.open(file_path, 'r', 'utf-16') as f:
        content = f.readlines()
        
    for i, line in enumerate(content):
        if 'CREATE TABLE [dbo].[DangKySuKien]' in line or 'CREATE TABLE [dbo].[KhoHocLieu]' in line:
            print(f"Line {i+1}: {line.strip()}")
            for j in range(i+1, i+20):
                if j < len(content):
                    print(content[j].strip())
except Exception as e:
    print(f"Error: {e}")
