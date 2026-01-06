#!/usr/bin/env python3
"""
Debug script to understand the PDF structure
"""
import fitz
from pathlib import Path

pdf_path = Path("downloads/20235016815.pdf")

doc = fitz.open(pdf_path)
all_lines = []

print("=" * 80)
print("EXTRACTING ALL LINES FROM PDF")
print("=" * 80)

for page_num, page in enumerate(doc, 1):
    text = page.get_text("text")
    page_lines = text.split('\n')
    
    print(f"\n{'=' * 80}")
    print(f"PAGE {page_num} - {len(page_lines)} lines")
    print(f"{'=' * 80}")
    
    for i, line in enumerate(page_lines[:100], 1):  # First 100 lines
        line = line.strip()
        if line:
            all_lines.append(line)
            print(f"{i:3}: |{line}|")

doc.close()

print("\n" + "=" * 80)
print("SEARCHING FOR KEY PATTERNS")
print("=" * 80)

# Search for vehicle markers
vehicle_markers = ["UNIT #", "UNIT#", "OWNER NAME", "LP STATE", "LICENSE PLATE"]
for marker in vehicle_markers:
    matches = [i for i, line in enumerate(all_lines) if marker in line]
    if matches:
        print(f"\n✅ Found '{marker}' at lines: {matches[:5]}")
        for idx in matches[:3]:
            print(f"   Line {idx}: {all_lines[idx]}")
            if idx + 1 < len(all_lines):
                print(f"   Line {idx+1}: {all_lines[idx+1]}")

# Search for person markers
person_markers = ["INJURIES", "INJURED", "NAME: LAST, FIRST", "DATE OF BIRTH"]
for marker in person_markers:
    matches = [i for i, line in enumerate(all_lines) if marker in line]
    if matches:
        print(f"\n✅ Found '{marker}' at lines: {matches[:5]}")
        for idx in matches[:3]:
            print(f"   Line {idx}: {all_lines[idx]}")
            if idx + 1 < len(all_lines):
                print(f"   Line {idx+1}: {all_lines[idx+1]}")

print("\n" + "=" * 80)
print(f"TOTAL LINES: {len(all_lines)}")
print("=" * 80)