import pdfplumber
from pathlib import Path

pdf_path = Path("downloads/20235016815.pdf")

with pdfplumber.open(pdf_path) as pdf:
    page = pdf.pages[0]
    
    # Try both extraction modes
    text_layout = page.extract_text(layout=True)
    text_normal = page.extract_text(layout=False)
    
    print("=== LAYOUT MODE ===")
    layout_lines = text_layout.split('\n')
    for i, line in enumerate(layout_lines[:30]):
        print(f"{i}: '{line}'")
    
    print("\n=== NORMAL MODE ===")
    normal_lines = text_normal.split('\n')
    for i, line in enumerate(normal_lines[:30]):
        print(f"{i}: '{line}'")
    
    # Search for specific strings
    print("\n=== SEARCHING FOR KEY STRINGS ===")
    search_terms = [
        "LOCAL INFORMATION",
        "LOCAL REPORT NUMBER",
        "REPORTING AGENCY NAME",
        "NCIC",
        "Ohio State Highway Patrol",
        "OHP08",
        "Liberty"
    ]
    
    for term in search_terms:
        print(f"\nSearching for: '{term}'")
        for i, line in enumerate(layout_lines):
            if term in line:
                print(f"  Found at line {i}: '{line}'")
                if i+1 < len(layout_lines):
                    print(f"  Next line: '{layout_lines[i+1]}'")