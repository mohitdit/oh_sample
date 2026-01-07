import re
from pathlib import Path
import sys
import fitz  # PyMuPDF
import pdfplumber
from pypdf import PdfReader
from pdfminer.high_level import extract_text_to_fp, extract_text
from pdfminer.layout import LAParams
from io import StringIO

PDF_PATH = Path("downloads/20235016815.pdf")
output_file = Path("pdf_methods_comparison.txt")

# Redirect to file
sys.stdout = open(output_file, 'w', encoding='utf-8')

print("=" * 100)
print("🧪 COMPREHENSIVE PDF EXTRACTION METHOD COMPARISON - ALL METHODS")
print("=" * 100)
print(f"PDF: {PDF_PATH}")
print(f"Size: {PDF_PATH.stat().st_size:,} bytes\n")

# ============================================================================
# METHOD 1: pdfplumber with layout=True - ALL PAGES
# ============================================================================
print("\n" + "="*100)
print("📘 METHOD 1: pdfplumber with layout=True - ALL PAGES")
print("="*100)

try:
    with pdfplumber.open(PDF_PATH) as pdf:
        all_lines = []
        
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text(layout=True)
            page_lines = text.split('\n')
            all_lines.extend(page_lines)
            
            print(f"\n{'─'*100}")
            print(f"PAGE {page_num} - {len(page_lines)} lines")
            print(f"{'─'*100}")
            for i, line in enumerate(page_lines, 1):
                if line.strip():  # Only non-empty lines
                    print(f"  {i:4d}: {line}")
        
        print(f"\n✅ TOTAL: {len(all_lines)} lines from {len(pdf.pages)} pages")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# METHOD 2: pdfplumber with layout=False - ALL PAGES
# ============================================================================
print("\n" + "="*100)
print("📙 METHOD 2: pdfplumber with layout=False - ALL PAGES")
print("="*100)

try:
    with pdfplumber.open(PDF_PATH) as pdf:
        all_lines = []
        
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text(layout=False)
            page_lines = text.split('\n')
            all_lines.extend(page_lines)
            
            print(f"\n{'─'*100}")
            print(f"PAGE {page_num} - {len(page_lines)} lines")
            print(f"{'─'*100}")
            for i, line in enumerate(page_lines, 1):
                if line.strip():
                    print(f"  {i:4d}: {line}")
        
        print(f"\n✅ TOTAL: {len(all_lines)} lines from {len(pdf.pages)} pages")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# METHOD 3: pdfplumber COORDINATE-BASED (extract_words) - FIRST PAGE ONLY
# ============================================================================
print("\n" + "="*100)
print("📗 METHOD 3: pdfplumber COORDINATE-BASED (extract_words) - PAGE 1")
print("="*100)

try:
    with pdfplumber.open(PDF_PATH) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()
        
        print(f"✅ Extracted {len(words)} words with coordinates\n")
        print("First 100 words with positions:")
        for i, word in enumerate(words[:100], 1):
            print(f"  {i:3d}: '{word['text']}' at x={word['x0']:.1f}, y={word['top']:.1f}")
        
        print("\n🔍 Searching for key terms:")
        for term in ["LOCAL", "INFORMATION", "REPORT", "NUMBER", "OWNER", "NAME", "UNIT", "INJURIES"]:
            found = [w for w in words if term.lower() in w['text'].lower()]
            if found:
                positions = [(w['x0'], w['top']) for w in found[:5]]
                print(f"  ✅ '{term}': Found {len(found)} times at {positions}")
            else:
                print(f"  ❌ '{term}': NOT FOUND")
                
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# METHOD 4: PyMuPDF (fitz) - ALL PAGES
# ============================================================================
print("\n" + "="*100)
print("📕 METHOD 4: PyMuPDF (fitz) - ALL PAGES")
print("="*100)

try:
    doc = fitz.open(PDF_PATH)
    all_lines = []
    
    for page_num, page in enumerate(doc, 1):
        text = page.get_text("text")
        page_lines = text.split('\n')
        all_lines.extend(page_lines)
        
        print(f"\n{'─'*100}")
        print(f"PAGE {page_num} - {len(page_lines)} lines")
        print(f"{'─'*100}")
        for i, line in enumerate(page_lines, 1):
            if line.strip():
                print(f"  {i:4d}: {line}")
    
    doc.close()
    print(f"\n✅ TOTAL: {len(all_lines)} lines from {page_num} pages")
    
    # Also try blocks
    print("\n📦 PyMuPDF Blocks (structured extraction) - PAGE 1:")
    doc = fitz.open(PDF_PATH)
    blocks = doc[0].get_text("blocks")
    print(f"Found {len(blocks)} text blocks\n")
    for i, block in enumerate(blocks[:20], 1):
        print(f"  Block {i}: x={block[0]:.1f}, y={block[1]:.1f}, text='{block[4][:80]}'")
    doc.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# METHOD 5: pypdf2 - ALL PAGES
# ============================================================================
print("\n" + "="*100)
print("📔 METHOD 5: pypdf2 - ALL PAGES")
print("="*100)

try:
    reader = PdfReader(PDF_PATH)
    all_lines = []
    
    for page_num, page in enumerate(reader.pages, 1):
        text = page.extract_text()
        page_lines = text.split('\n')
        all_lines.extend(page_lines)
        
        print(f"\n{'─'*100}")
        print(f"PAGE {page_num} - {len(page_lines)} lines")
        print(f"{'─'*100}")
        for i, line in enumerate(page_lines, 1):
            if line.strip():
                print(f"  {i:4d}: {line}")
    
    print(f"\n✅ TOTAL: {len(all_lines)} lines from {len(reader.pages)} pages")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# METHOD 6: REGEX EXTRACTION on pdfplumber text
# ============================================================================
print("\n" + "="*100)
print("📓 METHOD 6: REGEX EXTRACTION (on pdfplumber layout=True)")
print("="*100)

try:
    with pdfplumber.open(PDF_PATH) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text(layout=True) + "\n"
        
        print("🎯 Testing regex patterns:\n")
        
        # Test patterns
        patterns = {
            "Case Number": r'LOCAL INFORMATION\s+([A-Z0-9]+)',
            "Report Number": r'LOCAL REPORT NUMBER.*?\n\s*([0-9\-]+)',
            "Agency": r'REPORTING AGENCY NAME.*?\n\s*([A-Za-z\s]+?)(?=\s+NCIC)',
            "NCIC": r'NCIC.*?\n\s*([A-Z0-9]+)',
            "Owner Name": r'OWNER NAME.*?DRIVER\)\s+([A-Z,\s]+)',
            "VIN": r'VEHICLE IDENTIFICATION.*?\n\s*([A-HJ-NPR-Z0-9]{17})',
            "Person Name": r'NAME: LAST, FIRST, MIDDLE\s+([A-Z,\s]+)',
        }
        
        for label, pattern in patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                print(f"  ✅ {label}: {matches[:3]}")
            else:
                print(f"  ❌ {label}: NOT FOUND")
                
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# METHOD 7: pdfminer.six - ALL PAGES
# ============================================================================
print("\n" + "="*100)
print("📐 METHOD 7: pdfminer.six - ALL PAGES")
print("="*100)

try:
    # Default extraction
    text = extract_text(str(PDF_PATH))
    lines = text.split('\n')
    
    print(f"✅ Extracted {len(lines)} lines\n")
    print("First 100 lines:")
    for i, line in enumerate(lines[:100], 1):
        if line.strip():
            print(f"  {i:3d}: {line}")
    
    # With LAParams
    print("\n📐 With LAParams (layout-aware):")
    output = StringIO()
    with open(PDF_PATH, 'rb') as f:
        extract_text_to_fp(f, output, laparams=LAParams())
    text_layout = output.getvalue()
    lines_layout = text_layout.split('\n')
    
    print(f"Extracted {len(lines_layout)} lines with layout\n")
    print("First 100 lines:")
    for i, line in enumerate(lines_layout[:100], 1):
        if line.strip():
            print(f"  {i:3d}: {line}")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# FINAL COMPARISON
# ============================================================================
print("\n" + "="*100)
print("📊 COMPARISON SUMMARY")
print("="*100)

print("""
REVIEW ABOVE OUTPUTS AND DETERMINE:

1. Which method gave cleanest line-by-line extraction?
2. Which method correctly separated field labels from values?
3. Which method extracted:
   - Owner name: "FLINDERS, LARRY"
   - VIN: "3C6UR5FL6MG630586"
   - Plate: "2802GB"
   - Person name: "FLINDERS, JENNIFER, A"
   - Date of birth: "07/24/1972"
4. Which method handled multi-line fields best?
5. Which method preserved proper spacing/structure?

RECOMMENDATION:
- Choose the method that extracts all fields correctly
- Use that method's line structure in the parser
- Update _extract_single_vehicle() and _extract_single_person() accordingly
""")

print(f"\n{'='*100}")
print("COMPARISON COMPLETE - Review pdf_methods_comparison.txt")
print(f"{'='*100}")

sys.stdout.close()
sys.stdout = sys.__stdout__
print(f"✅ Analysis complete! Check: {output_file}")
print(f"   File size: {output_file.stat().st_size:,} bytes")