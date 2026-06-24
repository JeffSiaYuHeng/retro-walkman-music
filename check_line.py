import sys
try:
    with open('app.py', 'rb') as f:
        lines = f.readlines()
    output = f"Line 110: {repr(lines[109])}\n"
except Exception as e:
    output = f"Error: {e}\n"

with open('out.txt', 'w', encoding='utf-8') as f:
    f.write(output)
