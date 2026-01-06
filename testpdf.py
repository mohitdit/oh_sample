from pathlib import Path
from utils.pdf_parser import convert_pdf_to_json

# Test with the problematic PDF
pdf_path = Path("downloads/20235016815.pdf")
success = convert_pdf_to_json(pdf_path)

if success:
    # Check the output
    json_path = Path("json_output/20235016815.json")
    import json
    with open(json_path) as f:
        data = json.load(f)
        print(json.dumps(data, indent=2))