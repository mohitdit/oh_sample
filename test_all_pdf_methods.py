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
}

print("="*100)
print("🧪 COMPREHENSIVE PDF EXTRACTION TEST")
print("="*100)
print(f"\nTesting PDF: {PDF_PATH}")
print(f"File size: {PDF_PATH.stat().st_size:,} bytes\n")

# ============================================================================
# METHOD 1: pdfplumber with layout=True
# ============================================================================
print("\n" + "="*100)
print("📘 METHOD 1: pdfplumber with layout=True")
print("="*100)

try:
    with pdfplumber.open(PDF_PATH) as pdf:
        page = pdf.pages[0]
        text = page.extract_text(layout=True)
        lines = text.split('\n')
        
        print(f"✅ Extracted {len(lines)} lines")
        print("\n📄 First 30 lines:")
        for i, line in enumerate(lines[:30], 1):
            print(f"  {i:3d}: |{line}|")
        
        print("\n🔍 Pattern Matching Results:")
        for label, pattern in TEST_PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                print(f"  ✅ {label}: {matches[0][:50]}")
            else:
                print(f"  ❌ {label}: NOT FOUND")
                
except Exception as e:
    print(f"❌ Error: {e}")

# ============================================================================
# METHOD 2: pdfplumber with layout=False
# ============================================================================
print("\n" + "="*100)
print("📙 METHOD 2: pdfplumber with layout=False")
print("="*100)

try:
    with pdfplumber.open(PDF_PATH) as pdf:
        page = pdf.pages[0]
        text = page.extract_text(layout=False)
        lines = text.split('\n')
        
        print(f"✅ Extracted {len(lines)} lines")
        print("\n📄 First 30 lines:")
        for i, line in enumerate(lines[:30], 1):
            print(f"  {i:3d}: |{line}|")
        
        print("\n🔍 Pattern Matching Results:")
        for label, pattern in TEST_PATTERNS.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                print(f"  ✅ {label}: {matches[0][:50]}")
            else:
                print(f"  ❌ {label}: NOT FOUND")
                
except Exception as e:
    print(f"❌ Error: {e}")

# ============================================================================
# METHOD 3: pdfplumber COORDINATE-BASED (extract_words)
# ============================================================================
print("\n" + "="*100)
print("📗 METHOD 3: pdfplumber COORDINATE-BASED (extract_words)")
print("="*100)

try:
    with pdfplumber.open(PDF_PATH) as pdf:
        page = pdf.pages[0]
        words = page.extract_words()
        
        print(f"✅ Extracted {len(words)} words with coordinates")
        print("\n📄 First 30 words with positions:")
        for i, word in enumerate(words[:30], 1):
            print(f"  {i:3d}: '{word['text']}' at x={word['x0']:.1f}, y={word['top']:.1f}")
        
        # Try to find specific words
        print("\n🔍 Searching for key terms:")
        for term in ["LOCAL", "INFORMATION", "REPORT", "NUMBER", "Ohio", "Patrol", "Liberty"]:
            found = [w for w in words if term.lower() in w['text'].lower()]
            if found:
                print(f"  ✅ '{term}': Found {len(found)} times at positions {[(w['x0'], w['top']) for w in found[:3]]}")
            else:
                print(f"  ❌ '{term}': NOT FOUND")
        
        # Try to extract "REPORT NUMBER" value using coordinates
        print("\n🎯 Attempting coordinate-based extraction:")
        report_label = [w for w in words if 'REPORT' in w['text'] and 'NUMBER' in words[words.index(w)+1]['text'] if words.index(w)+1 < len(words)]
        if report_label:
            label_idx = words.index(report_label[0])
            label_y = report_label[0]['top']
            print(f"  📍 Found 'REPORT NUMBER' label at y={label_y:.1f}")
            
            # Find words on next line (y > label_y and y < label_y + 20)
            next_line_words = [w for w in words if label_y < w['top'] < label_y + 20 and w['x0'] > report_label[0]['x0'] - 50]
            if next_line_words:
                next_line_words.sort(key=lambda w: w['x0'])
                value = ' '.join([w['text'] for w in next_line_words[:5]])
                print(f"  ✅ Extracted value: '{value}'")
            else:
                print(f"  ❌ No words found on next line")
        else:
            print(f"  ❌ Could not locate 'REPORT NUMBER' label")
                
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# METHOD 4: PyMuPDF (fitz)
# ============================================================================
print("\n" + "="*100)
print("📕 METHOD 4: PyMuPDF (fitz)")
print("="*100)

try:
    doc = fitz.open(PDF_PATH)
    page = doc[0]
    
    # Extract text
    text = page.get_text("text")
    lines = text.split('\n')
    
    print(f"✅ Extracted {len(lines)} lines")
    print("\n📄 First 30 lines:")
    for i, line in enumerate(lines[:30], 1):
        print(f"  {i:3d}: |{line}|")
    
    print("\n🔍 Pattern Matching Results:")
    for label, pattern in TEST_PATTERNS.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            print(f"  ✅ {label}: {matches[0][:50]}")
        else:
            print(f"  ❌ {label}: NOT FOUND")
    
    # Try blocks extraction (structured)
    print("\n📦 PyMuPDF Blocks (structured extraction):")
    blocks = page.get_text("blocks")
    print(f"  Found {len(blocks)} text blocks")
    for i, block in enumerate(blocks[:10], 1):
        print(f"  Block {i}: x={block[0]:.1f}, y={block[1]:.1f}, text='{block[4][:50]}'")
    
    doc.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# METHOD 5: pypdf2
# ============================================================================
print("\n" + "="*100)
print("📔 METHOD 5: pypdf2")
print("="*100)

try:
    reader = PdfReader(PDF_PATH)
    page = reader.pages[0]
    text = page.extract_text()
    lines = text.split('\n')
    
    print(f"✅ Extracted {len(lines)} lines")
    print("\n📄 First 30 lines:")
    for i, line in enumerate(lines[:30], 1):
        print(f"  {i:3d}: |{line}|")
    
    print("\n🔍 Pattern Matching Results:")
    for label, pattern in TEST_PATTERNS.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            print(f"  ✅ {label}: {matches[0][:50]}")
        else:
            print(f"  ❌ {label}: NOT FOUND")
            
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# METHOD 6: REGEX EXTRACTION (on compressed lines from pdfplumber)
# ============================================================================
print("\n" + "="*100)
print("📓 METHOD 6: REGEX EXTRACTION (compressed lines)")
print("="*100)

try:
    with pdfplumber.open(PDF_PATH) as pdf:
        page = pdf.pages[0]
        text = page.extract_text(layout=True)
        
        print("🎯 Testing aggressive regex patterns on compressed text:\n")
        
        # Pattern 1: LOCAL INFORMATION value
        match = re.search(r'LOCAL INFORMATION\s+([A-Z0-9\-\s]+?)(?=\s+\d{2}-\d{4})', text)
        if match:
            print(f"  ✅ Case Number (LOCAL INFORMATION): '{match.group(1).strip()}'")
        else:
            print(f"  ❌ Case Number: NOT FOUND")
        
        # Pattern 2: REPORT NUMBER (try multiple patterns)
        patterns = [
            r'REPORT NUMBER\s*\*?\s*\n?\s*([A-Z0-9\-\s]+?)(?=\s+X|PHOTOS)',
            r'LOCAL REPORT NUMBER\s*\*?\s*\n?\s*([A-Z0-9\-\s]+?)(?=\s+X|PHOTOS)',
            r'(?:LOCAL REPORT NUMBER|REPORT NUMBER).*?\n\s*([A-Z0-9\-\s]+)',
        ]
        found = False
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                print(f"  ✅ Report Number: '{match.group(1).strip()}'")
                found = True
                break
        if not found:
            print(f"  ❌ Report Number: NOT FOUND")
        
        # Pattern 3: Agency Name
        match = re.search(r'REPORTING AGENCY NAME\s*\*?\s*\n?\s*([A-Za-z\s]+?)(?=\s+NCIC|\s+OHP)', text)
        if match:
            print(f"  ✅ Agency Name: '{match.group(1).strip()}'")
        else:
            print(f"  ❌ Agency Name: NOT FOUND")
        
        # Pattern 4: NCIC code
        match = re.search(r'NCIC\s*\*?\s*\n?\s*([A-Z0-9]+)', text)
        if match:
            print(f"  ✅ NCIC: '{match.group(1).strip()}'")
        else:
            print(f"  ❌ NCIC: NOT FOUND")
        
        # Pattern 5: County
        match = re.search(r'COUNTY\s*\*?\s*\n?\s*([A-Za-z\s]+?)(?=\s+CITY|\s+LOCALITY)', text)
        if match:
            print(f"  ✅ County: '{match.group(1).strip()}'")
        else:
            print(f"  ❌ County: NOT FOUND")
        
        # Pattern 6: Location (City/Village/Township)
        match = re.search(r'LOCATION:\s*CITY,\s*VILLAGE,\s*TOWNSHIP\s*\*?\s*\n?\s*([A-Za-z\s]+?)(?=\s+CRASH DATE)', text)
        if match:
            print(f"  ✅ Location: '{match.group(1).strip()}'")
        else:
            print(f"  ❌ Location: NOT FOUND")
            
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# METHOD 7: pdfminer.six
# ============================================================================
print("\n" + "="*100)
print("📐 METHOD 7: pdfminer.six")
print("="*100)

try:
    # Extract with default settings
    text = extract_text(str(PDF_PATH))
    lines = text.split('\n')
    
    print(f"✅ Extracted {len(lines)} lines")
    print("\n📄 First 30 lines:")
    for i, line in enumerate(lines[:30], 1):
        print(f"  {i:3d}: |{line}|")
    
    print("\n🔍 Pattern Matching Results:")
    for label, pattern in TEST_PATTERNS.items():
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            print(f"  ✅ {label}: {matches[0][:50]}")
        else:
            print(f"  ❌ {label}: NOT FOUND")
    
    # Try with LAParams for better layout
    print("\n📐 pdfminer.six with LAParams (layout-aware):")
    output = StringIO()
    with open(PDF_PATH, 'rb') as f:
        extract_text_to_fp(f, output, laparams=LAParams())
    text_layout = output.getvalue()
    lines_layout = text_layout.split('\n')
    
    print(f"  Extracted {len(lines_layout)} lines with layout preservation")
    print("\n  First 20 lines:")
    for i, line in enumerate(lines_layout[:20], 1):
        print(f"    {i:3d}: |{line}|")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

# ============================================================================
# SUMMARY & RECOMMENDATIONS
# ============================================================================
print("\n" + "="*100)
print("📊 SUMMARY & RECOMMENDATIONS")
print("="*100)

print("""
Compare the outputs above and answer these questions:

1️⃣ Which method extracted the cleanest line-separated text?
2️⃣ Which method found the most TEST_PATTERNS successfully?
3️⃣ Did coordinate-based extraction (Method 3) work well?
4️⃣ Did regex on compressed lines (Method 6) work?
5️⃣ Which library handled multi-column layout best?

Based on your analysis, we'll choose:
- ✅ Best Library (pdfplumber/PyMuPDF/pypdf2/pdfminer)
- ✅ Best Approach (line-by-line / coordinate-based / regex)
- ✅ Then rewrite utils/pdf_parser.py accordingly

Run this script and share the output!
""")