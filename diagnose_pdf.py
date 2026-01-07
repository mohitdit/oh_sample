import fitz
from pathlib import Path

pdf_path = Path("downloads/20235016815.pdf")
doc = fitz.open(pdf_path)

print("=" * 100)
print("📄 COMPLETE PDF EXTRACTION - PAGE BY PAGE ANALYSIS")
print("=" * 100)

all_lines = []
page_boundaries = []  # Track where each page starts

for page_num, page in enumerate(doc, 1):
    text = page.get_text("text")
    page_lines = text.split('\n')
    
    page_start = len(all_lines)
    all_lines.extend(page_lines)
    page_boundaries.append((page_start, len(all_lines)))
    
    print(f"\n{'='*100}")
    print(f"📄 PAGE {page_num} - Lines {page_start} to {len(all_lines)-1} ({len(page_lines)} lines)")
    print(f"{'='*100}\n")
    
    # Show all lines for this page
    for i, line in enumerate(page_lines, start=page_start):
        clean_line = line.strip()
        if clean_line:  # Only show non-empty lines
            print(f"  {i:4d}: {clean_line}")

doc.close()

print(f"\n{'='*100}")
print("📊 SUMMARY")
print(f"{'='*100}")
print(f"Total Lines: {len(all_lines)}")
print(f"Total Pages: {len(page_boundaries)}")

# # Now find key sections
# print(f"\n{'='*100}")
# print("🔍 KEY SECTIONS DETECTED")
# print(f"{'='*100}")

# # Find vehicles
# print("\n🚗 VEHICLE SECTIONS:")
# for i, line in enumerate(all_lines):
#     if "OWNER NAME" in line and "SAME AS DRIVER" in line:
#         page_num = next(p for p, (start, end) in enumerate(page_boundaries, 1) if start <= i < end)
#         print(f"  Line {i:4d} (Page {page_num}): Vehicle section starts")
#         if i + 1 < len(all_lines):
#             print(f"       Owner: {all_lines[i+1]}")

# # Find persons
# print("\n👤 PERSON SECTIONS:")
# for i, line in enumerate(all_lines):
#     if line.strip() == "INJURIES":
#         if i + 1 < len(all_lines) and all_lines[i+1].strip().isdigit():
#             page_num = next(p for p, (start, end) in enumerate(page_boundaries, 1) if start <= i < end)
#             print(f"  Line {i:4d} (Page {page_num}): Person section starts")
#             if i + 2 < len(all_lines):
#                 print(f"       Injury code: {all_lines[i+1]}")

# Find key data points
print("\n📋 KEY DATA LOCATIONS:")

# for i, line in enumerate(all_lines):
#     # VIN
#     if "VEHICLE IDENTIFICATION" in line and i + 1 < len(all_lines):
#         page_num = next(p for p, (start, end) in enumerate(page_boundaries, 1) if start <= i < end)
#         vin = all_lines[i+1].strip()
#         if len(vin) == 17:
#             print(f"  Line {i:4d} (Page {page_num}): VIN = {vin}")
    
#     # Plate
#     if line.strip() == "LICENSE PLATE #" and i + 1 < len(all_lines):
#         page_num = next(p for p, (start, end) in enumerate(page_boundaries, 1) if start <= i < end)
#         plate = all_lines[i+1].strip()
#         print(f"  Line {i:4d} (Page {page_num}): Plate = {plate}")
    
#     # Insurance
#     if line.strip() == "INSURANCE COMPANY" and i + 1 < len(all_lines):
#         page_num = next(p for p, (start, end) in enumerate(page_boundaries, 1) if start <= i < end)
#         ins = all_lines[i+1].strip()
#         if ins and "POLICY" not in ins:
#             print(f"  Line {i:4d} (Page {page_num}): Insurance = {ins}")
    
#     # Person name
#     if line.strip() == "NAME: LAST, FIRST, MIDDLE" and i + 1 < len(all_lines):
#         page_num = next(p for p, (start, end) in enumerate(page_boundaries, 1) if start <= i < end)
#         name = all_lines[i+1].strip()
#         if name and name not in ["DATE OF BIRTH", "WITNESS", ""]:
#             print(f"  Line {i:4d} (Page {page_num}): Person name = {name}")

print(f"\n{'='*100}")