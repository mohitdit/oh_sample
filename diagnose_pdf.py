import pdfplumber
from pathlib import Path

pdf_path = Path("downloads/20235016815.pdf")

with pdfplumber.open(pdf_path) as pdf:
    print(f"Total pages: {len(pdf.pages)}")
    print("\n" + "="*80)
    
    for page_num, page in enumerate(pdf.pages, 1):
        print(f"\n### PAGE {page_num} ###\n")
        
        # Extract with layout=True
        text_layout = page.extract_text(layout=True)
        print("LAYOUT MODE (first 50 lines):")
        print("-" * 80)
        lines = text_layout.split('\n')[:50]
        for i, line in enumerate(lines, 1):
            print(f"{i:3d}: |{line}|")
        
        print("\n" + "="*80)