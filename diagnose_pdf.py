import fitz
from pathlib import Path

pdf_path = Path("downloads/20235016815.pdf")
doc = fitz.open(pdf_path)

all_lines = []
for page in doc:
    text = page.get_text("text")
    all_lines.extend(text.split('\n'))
doc.close()

print(f"Total lines: {len(all_lines)}\n")

# Find vehicle section
print("=" * 80)
print("VEHICLE SECTION DETECTION")
print("=" * 80)
for i, line in enumerate(all_lines):
    if "OWNER NAME" in line and "SAME AS DRIVER" in line:
        print(f"\n✅ VEHICLE STARTS at line {i}")
        for offset in range(0, 30):
            if i + offset < len(all_lines):
                print(f"  {i+offset}: {all_lines[i+offset]}")
        break

# Find person section
print("\n" + "=" * 80)
print("PERSON SECTION DETECTION")
print("=" * 80)
for i, line in enumerate(all_lines):
    if line == "INJURIES" and i + 1 < len(all_lines) and all_lines[i+1].strip().isdigit():
        print(f"\n✅ PERSON STARTS at line {i}")
        for offset in range(0, 40):
            if i + offset < len(all_lines):
                print(f"  {i+offset}: {all_lines[i+offset]}")
        break