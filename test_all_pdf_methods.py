import re
from pathlib import Path
import pdfplumber
import fitz  # PyMuPDF
from pypdf import PdfReader
from pdfminer.high_level import extract_text_to_fp, extract_text
from pdfminer.layout import LAParams
from io import StringIO

# Test PDF
PDF_PATH = Path("downloads/20235016815.pdf")

# Test patterns we're looking for
TEST_PATTERNS = {
    "LOCAL INFORMATION": r'LOCAL INFORMATION.*?([A-Z0-9\s\-]+)',
    "REPORT NUMBER": r'(?:LOCAL REPORT NUMBER|REPORT NUMBER)\s*\*?\s*([A-Z0-9\s\-]+)',
    "AGENCY NAME": r'REPORTING AGENCY NAME.*?\n?\s*([A-Za-z\s]+?)(?=\s+[A-Z]{3,}|\s+NCIC)',
    "Ohio State Highway Patrol": r'Ohio State Highway Patrol',
    "OHP08": r'OHP08',
    "Liberty": r'Liberty',
    "UNIT #": r'UNIT\s*#',
    "OWNER NAME": r'OWNER NAME',
    "INJURIES": r'INJURIES',
}

print("="*100)
print("🧪 COMPREHENSIVE PDF EXTRACTION TEST - ALL PAGES")
print("="*100)
print(f"\nTesting PDF: {PDF_PATH}")
print(f"File size: {PDF_PATH.stat().st_size:,} bytes\n")

# ============================================================================
# METHOD 1: pdfplumber with layout=True - ALL PAGES
# ============================================================================
print("\n" + "="*100)
print("📘 METHOD 1: pdfplumber with layout=True - ALL PAGES")
print("="*100)

try:
    with pdfplumber.open(PDF_PATH) as pdf:
        all_lines = []
        all_text = ""
        
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text(layout=True)
            page_lines = text.split('\n')
            all_lines.extend(page_lines)
            all_text += text + "\n"
            
            print(f"\n📄 PAGE {page_num} - {len(page_lines)} lines")
            print(f"    First 20 lines:")
            for i, line in enumerate(page_lines[:20], 1):
                print(f"    {i:3d}: |{line}|")
        
        print(f"\n✅ Total extracted: {len(all_lines)} lines from {len(pdf.pages)} pages")
        
        print("\n🔍 Pattern Matching Results (ALL PAGES):")
        for label, pattern in TEST_PATTERNS.items():
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            if matches:
                print(f"  ✅ {label}: Found {len(matches)} times - {matches[:3]}")
            else:
                print(f"  ❌ {label}: NOT FOUND")
        
        # Search for vehicle and person markers
        print("\n🔍 Searching for Vehicle/Person markers:")
        for i, line in enumerate(all_lines):
            if "UNIT #" in line:
                print(f"  📍 Line {i}: {line}")
                if i+1 < len(all_lines):
                    print(f"       +1: {all_lines[i+1]}")
                if i+2 < len(all_lines):
                    print(f"       +2: {all_lines[i+2]}")
            
            if "INJURIES" in line and i < 500:  # First occurrence
                print(f"  📍 Line {i}: {line}")
                if i+1 < len(all_lines):
                    print(f"       +1: {all_lines[i+1]}")
                if i+2 < len(all_lines):
                    print(f"       +2: {all_lines[i+2]}")
                
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# METHOD 2: PyMuPDF (fitz) - ALL PAGES
# ============================================================================
print("\n" + "="*100)
print("📕 METHOD 2: PyMuPDF (fitz) - ALL PAGES")
print("="*100)

try:
    doc = fitz.open(PDF_PATH)
    all_lines = []
    all_text = ""
    
    for page_num, page in enumerate(doc, 1):
        text = page.get_text("text")
        page_lines = text.split('\n')
        all_lines.extend(page_lines)
        all_text += text + "\n"
        
        print(f"\n📄 PAGE {page_num} - {len(page_lines)} lines")
        print(f"    First 20 lines:")
        for i, line in enumerate(page_lines[:20], 1):
            print(f"    {i:3d}: |{line}|")
    
    print(f"\n✅ Total extracted: {len(all_lines)} lines from {len(doc)} pages")
    
    print("\n🔍 Pattern Matching Results (ALL PAGES):")
    for label, pattern in TEST_PATTERNS.items():
        matches = re.findall(pattern, all_text, re.IGNORECASE)
        if matches:
            print(f"  ✅ {label}: Found {len(matches)} times - {matches[:3]}")
        else:
            print(f"  ❌ {label}: NOT FOUND")
    
    # Search for vehicle and person markers with context
    print("\n🔍 Searching for Vehicle/Person markers with context:")
    
    # Find UNIT # markers
    unit_indices = [i for i, line in enumerate(all_lines) if "UNIT #" in line or "UNIT#" in line]
    print(f"\n  🚗 Found 'UNIT #' at {len(unit_indices)} locations:")
    for idx in unit_indices[:5]:
        print(f"    Line {idx}: {all_lines[idx]}")
        for offset in range(1, 5):
            if idx+offset < len(all_lines):
                print(f"         +{offset}: {all_lines[idx+offset]}")
    
    # Find OWNER NAME markers
    owner_indices = [i for i, line in enumerate(all_lines) if "OWNER NAME" in line]
    print(f"\n  👤 Found 'OWNER NAME' at {len(owner_indices)} locations:")
    for idx in owner_indices[:5]:
        print(f"    Line {idx}: {all_lines[idx]}")
        for offset in range(1, 5):
            if idx+offset < len(all_lines):
                print(f"         +{offset}: {all_lines[idx+offset]}")
    
    # Find INJURIES markers
    injury_indices = [i for i, line in enumerate(all_lines) if "INJURIES" in line]
    print(f"\n  🏥 Found 'INJURIES' at {len(injury_indices)} locations:")
    for idx in injury_indices[:5]:
        print(f"    Line {idx}: {all_lines[idx]}")
        for offset in range(1, 5):
            if idx+offset < len(all_lines):
                print(f"         +{offset}: {all_lines[idx+offset]}")
    
    # Find NAME: LAST, FIRST markers
    name_indices = [i for i, line in enumerate(all_lines) if "NAME: LAST, FIRST" in line]
    print(f"\n  📝 Found 'NAME: LAST, FIRST' at {len(name_indices)} locations:")
    for idx in name_indices[:5]:
        print(f"    Line {idx}: {all_lines[idx]}")
        for offset in range(1, 5):
            if idx+offset < len(all_lines):
                print(f"         +{offset}: {all_lines[idx+offset]}")
    
    doc.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# METHOD 3: pdfplumber - Find Vehicle/Person Section Boundaries
# ============================================================================
print("\n" + "="*100)
print("📗 METHOD 3: Section Boundary Analysis")
print("="*100)

try:
    with pdfplumber.open(PDF_PATH) as pdf:
        all_lines = []
        
        for page in pdf.pages:
            text = page.extract_text(layout=False)
            all_lines.extend(text.split('\n'))
        
        print(f"✅ Extracted {len(all_lines)} lines total")
        
        # Analyze the structure
        print("\n📋 Analyzing document structure:")
        
        section_markers = {
            "CRASH REPORT": [],
            "UNIT": [],
            "MOTORIST": [],
            "OCCUPANT": [],
            "WITNESS": []
        }
        
        for i, line in enumerate(all_lines):
            if "TRAFFIC CRASH REPORT" in line:
                section_markers["CRASH REPORT"].append(i)
            if "UNIT #" in line or "UNIT#" in line:
                section_markers["UNIT"].append(i)
            if "MOTORIST / NON-MOTORIST" in line:
                section_markers["MOTORIST"].append(i)
            if "OCCUPANT / WITNESS" in line or "OCCUPANT" in line:
                section_markers["OCCUPANT"].append(i)
        
        for section, indices in section_markers.items():
            print(f"\n  📍 {section} section(s): {len(indices)} found")
            for idx in indices[:3]:
                print(f"      Line {idx}: {all_lines[idx]}")
        
        # Check what comes after "UNIT #"
        print("\n🔍 What comes after 'UNIT #':")
        for i, line in enumerate(all_lines):
            if ("UNIT #" in line or "UNIT#" in line) and i < len(all_lines) - 10:
                print(f"\n  At line {i}:")
                for offset in range(0, 10):
                    if i+offset < len(all_lines):
                        text = all_lines[i+offset][:80]
                        print(f"    {i+offset}: {text}")
                break  # Just show first occurrence
        
        # Check what comes after "INJURIES"
        print("\n🔍 What comes after 'INJURIES':")
        for i, line in enumerate(all_lines):
            if "INJURIES" in line and "INJURED" not in line and i < len(all_lines) - 10:
                print(f"\n  At line {i}:")
                for offset in range(0, 10):
                    if i+offset < len(all_lines):
                        text = all_lines[i+offset][:80]
                        print(f"    {i+offset}: {text}")
                break  # Just show first occurrence
                
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "="*100)
print("📊 ANALYSIS COMPLETE")
print("="*100)
print("""
Now review the output above and identify:

1. Which method gave the cleanest line-by-line extraction?
2. At which line numbers do vehicles start? (look for UNIT # + OWNER NAME pattern)
3. At which line numbers do persons start? (look for INJURIES pattern)
4. What pattern reliably indicates a new vehicle section?
5. What pattern reliably indicates a new person section?

Share this output and I'll write the correct parser logic!
""")