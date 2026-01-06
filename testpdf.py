#!/usr/bin/env python3
"""
Enhanced test script for Ohio PDF Parser
Shows detailed extraction results with proper formatting
"""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from utils.pdf_parser import OhioPdfParser


def print_header(title, char="="):
    """Print formatted header"""
    print(f"\n{char * 80}")
    print(f"{title:^80}")
    print(f"{char * 80}\n")


def test_parser():
    """Test the PDF parser"""
    
    pdf_path = Path("downloads/20235016815.pdf")
    if not pdf_path.exists():
        pdf_path = Path("CrashOH1M5.pdf")
    
    if not pdf_path.exists():
        print("❌ ERROR: No test PDF found")
        return False
    
    print_header("🧪 OHIO PDF PARSER - COMPLETE TEST")
    
    print(f"📄 Testing: {pdf_path.name}")
    print(f"   Size: {pdf_path.stat().st_size:,} bytes\n")
    
    # Parse
    parser = OhioPdfParser(pdf_path)
    result = parser.parse()
    
    if not result:
        print("❌ FAILED: Parser returned None")
        return False
    
    print_header("📊 EXTRACTION RESULTS", "-")
    
    # Basic Info
    print("🚨 CRASH INFORMATION:")
    print(f"   Incident Number:    {result.get('incident_number', 'N/A')}")
    print(f"   Report Number:      {result.get('report_number', 'N/A')}")
    print(f"   Department:         {result.get('department', 'N/A')}")
    print(f"   Municipality:       {result.get('municipality', 'N/A')}")
    print(f"   County:             {result.get('county', 'N/A')}")
    print(f"   Location:           {result.get('crash_location', 'N/A')}")
    print(f"   Date:               {result.get('date_of_crash', 'N/A')}")
    print(f"   Total Vehicles:     {result.get('total_vehicles', '0')}")
    
    # Case Details
    if result.get("case_detail"):
        detail = result["case_detail"][0]
        print(f"\n📋 CASE DETAILS:")
        print(f"   Severity:           {detail.get('crash_severity', 'N/A')}")
        print(f"   Locality:           {detail.get('locality', 'N/A')}")
        print(f"   Route Type:         {detail.get('route_type', 'N/A')}")
        print(f"   Route Number:       {detail.get('route_number', 'N/A')}")
    
    # Vehicles
    vehicles = result.get("vehicles", [])
    print(f"\n🚗 VEHICLES: {len(vehicles)}")
    
    for i, veh in enumerate(vehicles, 1):
        print(f"\n   Vehicle #{i} (Unit {veh.get('vehicle_unit', '?')})")
        print(f"   ├─ {veh.get('vehicle_year', '')} {veh.get('make', '')} {veh.get('model', '')}")
        print(f"   ├─ VIN:      {veh.get('vin', 'N/A')}")
        print(f"   ├─ Plate:    {veh.get('plate_state', '')} {veh.get('plate_number', '')}")
        print(f"   ├─ Color:    {veh.get('color', 'N/A')}")
        print(f"   ├─ Towed:    {'Yes' if veh.get('is_towed') == '1' else 'No'}")
        
        # Persons
        persons = veh.get("persons", [])
        print(f"   └─ Persons:  {len(persons)}")
        
        for j, person in enumerate(persons, 1):
            name_parts = [person.get('first_name', ''), person.get('last_name', '')]
            name = ' '.join(p for p in name_parts if p).strip() or "Unknown"
            
            print(f"      └─ Person {j}: {name}")
            print(f"         ├─ DOB:      {person.get('date_of_birth', 'N/A')}")
            print(f"         ├─ Gender:   {person.get('gender', 'N/A')}")
            print(f"         ├─ Seating:  Position {person.get('seating_position', 'N/A')}")
            print(f"         ├─ Driver:   {'Yes' if person.get('same_as_driver') == '1' else 'No'}")
            if person.get('injury'):
                print(f"         ├─ Injury:   Code {person.get('injury')}")
            if person.get('offense_charged'):
                print(f"         └─ Offense:  {person.get('offense_charged')}")
    
    # Save JSON
    print_header("💾 SAVING OUTPUT", "-")
    
    output_dir = Path("json_output")
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{pdf_path.stem}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    
    print(f"✅ Saved to: {output_file}")
    print(f"   Size: {output_file.stat().st_size:,} bytes")
    
    # Show JSON sample
    print_header("📝 JSON PREVIEW", "-")
    sample = json.dumps(result, indent=2)[:2000]
    print(sample)
    if len(json.dumps(result)) > 2000:
        print("\n... (truncated, see full output in json_output/)")
    
    print_header("✅ TEST COMPLETED", "=")
    
    # Summary
    total_persons = sum(len(v['persons']) for v in vehicles)
    print(f"\n📊 FINAL SUMMARY:")
    print(f"   ✓ Vehicles extracted: {len(vehicles)}")
    print(f"   ✓ Persons extracted:  {total_persons}")
    print(f"   ✓ JSON file created:  {output_file.name}")
    
    return True


if __name__ == "__main__":
    success = test_parser()
    
    if not success:
        print("\n❌ Test failed")
        sys.exit(1)
    else:
        print("\n🎉 All tests passed!")
        sys.exit(0)