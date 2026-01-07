import re
import json
from pathlib import Path
from datetime import datetime
import fitz  # PyMuPDF
from typing import Optional, Dict, List


class OhioPdfParser:
    """
    Ohio PDF Parser - Complete Implementation
    Extracts crash reports with proper JSON structure matching legacy C# output
    """
    
    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self.lines = []
        
    def parse(self) -> Optional[Dict]:
        """Main parsing entry point"""
        try:
            # Extract all text lines
            doc = fitz.open(self.pdf_path)
            for page in doc:
                text = page.get_text("text")
                page_lines = text.split('\n')
                self.lines.extend([line.strip() for line in page_lines if line.strip()])
            doc.close()
            
            if not self.lines:
                print(f"❌ No text from {self.pdf_path}")
                return None
            
            print(f"✅ Extracted {len(self.lines)} lines from PDF")
            
            # Debug: Show where vehicles/persons start
            for i, line in enumerate(self.lines):
                if "UNIT #" in line and "OWNER NAME" in line:
                    print(f"   🚗 Found UNIT # at line {i}")
                if "INJURIES" in line and i + 1 < len(self.lines) and "INJURED" in self.lines[i+1]:
                    print(f"   👤 Found INJURIES at line {i}")
            
            # Extract all sections
            basic_info = self._extract_basic_info()
            case_detail = self._extract_case_detail()
            vehicles = self._extract_all_vehicles()
            
            # Build final JSON matching expected structure
            return self._build_final_json(basic_info, case_detail, vehicles)
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _find_line(self, pattern, start=0):
        """Find line matching pattern"""
        for i in range(start, len(self.lines)):
            if isinstance(pattern, str):
                if pattern in self.lines[i]:
                    return i
            elif pattern.search(self.lines[i]):
                return i
        return -1
    
    def _safe_get(self, idx, offset=1, default=""):
        """Safely get line at index + offset"""
        target = idx + offset
        if 0 <= target < len(self.lines):
            return self.lines[target].strip()
        return default
    
    def _extract_basic_info(self):
        """Extract basic crash information"""
        info = {
            "incident_number": "",
            "report_number": "",
            "department": "",
            "state_code": "",
            "state_abbreviation": "OH",
            "state_name": "OHIO",
            "county_code": "",
            "county": "",
            "municipality_code": "",
            "municipality": "",
            "crash_location": "",
            "crash_type_l1": "",
            "crash_type_l2": "",
            "date_of_crash": "",
            "total_killed": "",
            "total_injured": "",
            "total_vehicles": "0",
            "case_file_s3_path": "",
            "s3_bucket_name": "",
            "s3_access_key": "",
            "s3_secret_key": "",
            "pdf_file_path": str(self.pdf_path.absolute())
        }
        
        # Local Report Number (incident_number)
        idx = self._find_line("LOCAL REPORT NUMBER")
        if idx >= 0:
            report = self._safe_get(idx, 1)
            m = re.match(r'([0-9-]+)', report)
            if m:
                info["incident_number"] = m.group(1)
        
        # Case Number (report_number) - after LOCAL INFORMATION
        idx = self._find_line("LOCAL INFORMATION")
        if idx >= 0:
            case = self._safe_get(idx, 1)
            m = re.match(r'^([A-Z0-9]+)', case)
            if m:
                info["report_number"] = m.group(1)
        
        # Department
        idx = self._find_line("REPORTING AGENCY NAME")
        if idx >= 0:
            dept = self._safe_get(idx, 1)
            if "NCIC" not in dept:
                info["department"] = dept
        
        # NCIC + vehicle count
        idx = self._find_line("NCIC *")
        if idx >= 0:
            ncic_line = self._safe_get(idx, 1)
            parts = ncic_line.split()
            if parts:
                info["municipality_code"] = parts[0]
                info["municipality"] = parts[0]
            if len(parts) > 1:
                try:
                    info["total_vehicles"] = parts[1]
                except:
                    pass
        
        # County
        for i, line in enumerate(self.lines):
            if "COUNTY*" in line:
                if i > 0 and "UNSOLVED" in self.lines[i-1]:
                    county = self._safe_get(i, 1)
                    if "CITY" not in county and "LOCALITY" not in county:
                        info["county"] = county
                        info["county_code"] = county
                        break
        
        # Location
        idx = self._find_line("LOCATION: CITY, VILLAGE, TOWNSHIP")
        if idx >= 0:
            loc = self._safe_get(idx, 1)
            loc = re.sub(r'\s*\(.*?\)', '', loc)  # Remove (Township of)
            if loc and "CRASH DATE" not in loc:
                info["crash_location"] = loc
        
        # Date - convert to YYYY-MM-DD format
        idx = self._find_line("CRASH DATE / TIME")
        if idx >= 0:
            date_str = self._safe_get(idx, 1)
            m = re.search(r'(\d{2})/(\d{2})/(\d{4})', date_str)
            if m:
                mm, dd, yyyy = m.groups()
                info["date_of_crash"] = f"{yyyy}-{mm}-{dd}"
        
        return info
    
    def _extract_case_detail(self):
        """Extract case detail information"""
        detail = {
            "local_information": "",
            "locality": "TOWNSHIP",
            "location": "NA",
            "route_type": "NA",
            "route_number": "NA",
            "route_prefix": "NA",
            "lane_speed_limit_1": "",
            "lane_speed_limit_2": "",
            "crash_severity": ""
        }
        
        # Crash Severity
        for line in self.lines:
            if "FATAL" in line:
                m = re.search(r'(\d+)\s*1\s*-', line)
                if m:
                    detail["crash_severity"] = m.group(1)
                break
        
        # Locality
        loc_map = {1: "CITY", 2: "VILLAGE", 3: "TOWNSHIP"}
        for i, line in enumerate(self.lines):
            if "LOCALITY*" in line:
                if i > 0 and "TOWNSHIP" in self.lines[i-1]:
                    loc_code = self._safe_get(i, 1)
                    if loc_code.isdigit():
                        code = int(loc_code)
                        if code in loc_map:
                            detail["locality"] = loc_map[code]
                break
        
        # Route info from REFERENCE section
        for i in range(len(self.lines)):
            if (self.lines[i] == "LOCATION" and 
                i + 1 < len(self.lines) and self.lines[i + 1] == "REFERENCE"):
                
                # Look for route type and number
                for offset in range(7, 15):
                    if i + offset >= len(self.lines):
                        break
                    
                    check_line = self.lines[i + offset]
                    
                    # Check for PREFIX pattern first
                    if "PREFIX" in check_line and "ROUTE TYPE ROUTE NUMBER PREFIX" in check_line:
                        # Get prefix from line before "1 - NORTH"
                        for p in range(i + offset, min(i + offset + 5, len(self.lines))):
                            if "1 - NORTH" in self.lines[p]:
                                if p > 0:
                                    prefix = self.lines[p - 1].strip()
                                    if prefix and not prefix.startswith("1"):
                                        detail["route_prefix"] = prefix
                        break
                    
                    # Check for separate ROUTE TYPE ROUTE NUMBER
                    elif "ROUTE TYPE ROUTE NUMBER" in check_line and "PREFIX" not in check_line:
                        # Route type is line before
                        if i + offset - 1 >= 0:
                            route_type = self.lines[i + offset - 1].strip()
                            if route_type and len(route_type) <= 3:
                                detail["route_type"] = route_type
                        
                        # Route number is a few lines ahead (before PREFIX)
                        for r in range(i + offset + 1, min(i + offset + 5, len(self.lines))):
                            if "PREFIX" in self.lines[r] and "NORTH" in self.lines[r]:
                                if r > 0:
                                    route_num = self.lines[r - 1].strip()
                                    if route_num and route_num.replace("-", "").isdigit():
                                        detail["route_number"] = route_num
                                break
                        break
                break
        
        # Location road name
        idx = self._find_line("LOCATION ROAD NAME")
        if idx >= 0:
            has_distance = any("DISTANCE" in self._safe_get(idx, o) for o in [2, 3])
            if has_distance:
                road = self._safe_get(idx, 1)
                try:
                    float(road)  # Skip if it's a number
                except:
                    if road:
                        detail["location"] = road
        
        return detail
    
    def _extract_all_vehicles(self):
        """Extract all vehicles from the PDF"""
        vehicles = []
        i = 0
        
        while i < len(self.lines):
            line = self.lines[i]
            
            # Look for vehicle header: "OWNER NAME" (comes BEFORE "UNIT #")
            if "OWNER NAME" in line and "SAME AS DRIVER" in line:
                # This is the start of a vehicle section
                if True:  # Always process when we find OWNER NAME
                    print(f"   🚗 Extracting vehicle starting at line {i}")
                    vehicle = self._extract_single_vehicle(i)
                    if vehicle:
                        vehicles.append(vehicle)
                        # Skip ahead to avoid re-processing
                        i += 50
                        continue
            
            i += 1
        
        print(f"   📊 Total vehicles extracted: {len(vehicles)}")
        return vehicles
    
    def _extract_single_vehicle(self, start_idx):
        """Extract a single vehicle starting from the given index"""
        vehicle = {
            "vehicle_unit": "",
            "is_commercial": "0",
            "make": "",
            "model": "",
            "vehicle_year": "",
            "plate_number": "",
            "plate_state": "",
            "plate_year": "",
            "vin": "",
            "policy": "",
            "is_driven": "",
            "is_left_at_scene": "",
            "is_towed": "0",
            "is_impounded": "",
            "is_disabled": "",
            "is_parked": "0",
            "is_pedestrian": "",
            "is_pedal_cyclist": "",
            "is_hit_and_run": "0",
            "vehicle_used": "",
            "vehicle_type": "1",
            "trailer_or_carrier_count": "0",
            "color": "",
            "vehicle_body_type": "",
            "vehicle_travel_direction": "",
            "vehicle_details": {
                "crash_seq_1st_event": "",
                "crash_seq_2nd_event": "",
                "crash_seq_3rd_event": "",
                "crash_seq_4th_event": "",
                "harmful_event": "",
                "authorized_speed": "",
                "estimated_original_speed": "",
                "estimated_impact_speed": "",
                "tad": "",
                "estimated_damage": "",
                "most_harmful_event": "",
                "insurance_company": "",
                "insurance_verified": "",
                "us_dot": "",
                "towed_by": "",
                "occupant_count": "",
                "initial_impact": "",
                "contributing_circumstance": "",
                "damage_severity": "",
                "damaged_area": "",
                "vehicle_defects": "",
                "overweight_permit": ""
            },
            "persons": []
        }
        
        # Search within next 200 lines for vehicle data
        end_idx = min(start_idx + 200, len(self.lines))
        
        # Owner Name is on line after "OWNER NAME: LAST, FIRST, MIDDLE" (which is start_idx)
        if start_idx + 1 < len(self.lines):
            owner_name = self.lines[start_idx + 1].strip()
            if owner_name and "UNIT #" not in owner_name:
                vehicle["owner_name"] = owner_name
                print(f"      Owner: {owner_name}")
        
        # Process each line looking for vehicle data
        for i in range(start_idx, end_idx):
            if i >= len(self.lines):
                break
                
            line = self.lines[i]
            
            # Extract unit number - it's on line after "UNIT #"
            if line == "UNIT #":
                if i + 1 < len(self.lines) and self.lines[i + 1].isdigit():
                    vehicle["vehicle_unit"] = self.lines[i + 1]
                    print(f"      Unit: {self.lines[i + 1]}")
            
            # Owner Phone - extract from combined line with owner name
            elif "DAMAGE SCALE" in line and re.search(r'\d{3}-\d{3}-\d{4}', line):
                # This line has: "1  FLINDERS, LARRY    740-285-2912    DAMAGE SCALE"
                match = re.search(r'(\d{3}-\d{3}-\d{4})', line)
                if match:
                    vehicle["owner_phone"] = match.group(1)
            
            # LP STATE, LICENSE PLATE, VIN
            elif "LP STATE" in line and "LICENSE PLATE" in line:
                # Next line should have: "KY 2802GB 3C6UR5FL6MG630586 2021 RAM"
                if i + 1 < len(self.lines):
                    next_line = self.lines[i + 1]
                    
                    # VIN (17 characters)
                    vin_match = re.search(r'\b[A-HJ-NPR-Z0-9]{17}\b', next_line)
                    if vin_match:
                        vehicle["vin"] = vin_match.group(0)
                    
                    # Plate state and number
                    parts = next_line.split()
                    if len(parts) >= 1:
                        vehicle["plate_state"] = parts[0]
                    if len(parts) >= 2:
                        vehicle["plate_number"] = parts[1]
                    
                    # Year and Make might be on same line
                    if len(parts) >= 4 and parts[3].isdigit() and len(parts[3]) == 4:
                        vehicle["vehicle_year"] = parts[3]
                        print(f"      Year: {parts[3]}")
                    if len(parts) >= 5:
                        vehicle["make"] = parts[4]
                        print(f"      Make: {parts[4]}")
            
            # VEHICLE YEAR label (if not already extracted)
            elif line == "VEHICLE YEAR" and not vehicle["vehicle_year"]:
                if i + 1 < len(self.lines) and self.lines[i + 1].isdigit():
                    vehicle["vehicle_year"] = self.lines[i + 1]
                    print(f"      Year: {self.lines[i + 1]}")
            
            # VEHICLE MAKE label (if not already extracted)
            elif line == "VEHICLE MAKE" and not vehicle["make"]:
                if i + 1 < len(self.lines):
                    make = self.lines[i + 1].strip()
                    if make and not make.isdigit():
                        vehicle["make"] = make
                        print(f"      Make: {make}")
            
            # Vehicle Model
            elif line == "VEHICLE MODEL":
                if i + 1 < len(self.lines):
                    model = self.lines[i + 1].strip()
                    if model and not model.isdigit():
                        vehicle["model"] = model
                        print(f"      Model: {model}")
            
            # Color
            elif line == "COLOR":
                if i + 1 < len(self.lines):
                    color = self.lines[i + 1].strip()
                    if color and "TOWED" not in color and not color.isdigit():
                        vehicle["color"] = color
            
            # Insurance Company
            elif "INSURANCE COMPANY" in line:
                for offset in [1, -1, 2]:
                    if 0 <= i + offset < len(self.lines):
                        comp = self.lines[i + offset].strip()
                        if comp and "INSURANCE" not in comp and "POLICY" not in comp and comp != "X" and len(comp) > 2:
                            vehicle["vehicle_details"]["insurance_company"] = comp
                            break
            
            # Insurance Verified
            elif "INSURANCE" in line and "VERIFIED" in line:
                if "X" in line or (i + 1 < len(self.lines) and "X" in self.lines[i + 1]):
                    vehicle["vehicle_details"]["insurance_verified"] = "YES"
            
            # Policy Number
            elif "POLICY" in line and "#" in line:
                if i + 1 < len(self.lines):
                    policy = self.lines[i + 1].strip()
                    if policy and "COLOR" not in policy and len(policy) > 3:
                        vehicle["policy"] = policy
            
            # Towed By
            elif "TOWED BY" in line:
                if i + 1 < len(self.lines):
                    towed = self.lines[i + 1].strip()
                    if towed and towed != "NA" and len(towed) > 1:
                        vehicle["vehicle_details"]["towed_by"] = towed
                        vehicle["is_towed"] = "1"
            
            # Hit and Run
            elif "HIT/SKIP" in line:
                if "X" in line or (i + 1 < len(self.lines) and "X" in self.lines[i + 1]):
                    vehicle["is_hit_and_run"] = "1"
            
            # Occupants
            elif "# OCCUPANTS" in line or line == "OCCUPANTS":
                for offset in [-1, 1, -2, 2]:
                    if 0 <= i + offset < len(self.lines):
                        occ = self.lines[i + offset].strip()
                        if occ.isdigit() and len(occ) <= 2:
                            vehicle["vehicle_details"]["occupant_count"] = occ
                            break
            
            # Vehicle Type
            elif "UNIT TYPE" in line:
                if i - 1 >= 0 and self.lines[i - 1].isdigit():
                    vehicle["vehicle_type"] = self.lines[i - 1]
            
            # Trailing Units
            elif "TRAILING UNITS" in line:
                m = re.search(r'\d', line)
                if m:
                    vehicle["trailer_or_carrier_count"] = m.group(0)
            
            # Parked
            elif "PRE-CRASH" in line:
                if i - 1 >= 0 and "10" in self.lines[i - 1]:
                    vehicle["is_parked"] = "1"
            
            # Harmful Events
            elif "FIRST HARMFUL EVENT" in line and "MOST HARMFUL EVENT" in line:
                m1 = re.search(r'(\d{1,2})\s+FIRST', line)
                if m1:
                    vehicle["vehicle_details"]["harmful_event"] = m1.group(1)
                m2 = re.search(r'FIRST HARMFUL EVENT\s+(\d{1,2})', line)
                if m2:
                    vehicle["vehicle_details"]["most_harmful_event"] = m2.group(1)
            
            # Damage Severity
            elif "MINOR DAMAGE" in line and "DISABLING DAMAGE" in line:
                m = re.search(r'(\d{1,2})\s+2\s*-\s*MINOR', line)
                if m:
                    vehicle["vehicle_details"]["damage_severity"] = m.group(1)
            
            # Contributing Circumstance
            elif "CONTRIBUTING" in line and "CIRCUMSTANCES" in line:
                if i - 1 >= 0:
                    contrib = self.lines[i - 1].strip()
                    m = re.match(r'(\d+)', contrib)
                    if m:
                        vehicle["vehicle_details"]["contributing_circumstance"] = m.group(1)
            
            # Stop when we hit the next vehicle or persons section
            elif "INJURIES" in line and i > start_idx + 30:
                break
            elif "OWNER NAME" in line and "SAME AS DRIVER" in line and i > start_idx + 10:
                break
        
        # Extract persons for this vehicle
        vehicle["persons"] = self._extract_persons_for_vehicle(start_idx, vehicle["vehicle_unit"])
        
        return vehicle
    
    def _extract_persons_for_vehicle(self, vehicle_start_idx, vehicle_unit):
        """Extract all persons for a specific vehicle"""
        persons = []
        
        # Search for persons starting after the vehicle section
        i = vehicle_start_idx + 30  # Skip vehicle header
        
        while i < len(self.lines) and i < vehicle_start_idx + 400:
            line = self.lines[i]
            
            # Look for person header: "INJURIES" followed by a NUMBER
            if line == "INJURIES":
                # Check if next line is a digit (injury code)
                if i + 1 < len(self.lines) and self.lines[i + 1].strip().isdigit():
                    is_person = True
                
                if is_person:
                    print(f"      👤 Extracting person at line {i}")
                    person = self._extract_single_person(i, vehicle_unit)
                    if person:
                        persons.append(person)
                    i += 40  # Skip ahead
                    continue
            
            # Stop if we hit next vehicle
            elif "UNIT #" in line and i > vehicle_start_idx + 50:
                break
            
            i += 1
        
        print(f"      👥 Extracted {len(persons)} person(s) for unit {vehicle_unit}")
        return persons
    
    def _extract_single_person(self, start_idx, vehicle_unit):
        """Extract a single person"""
        person = {
            "person_type": "",
            "first_name": "",
            "middle_name": "",
            "last_name": "",
            "same_as_driver": "",
            "address_block": {
                "address_line1": "",
                "address_city": "",
                "address_state": "",
                "address_zip": ""
            },
            "seating_position": "",
            "date_of_birth": "",
            "gender": "",
            "alcohol_or_drug_involved": "",
            "ethnicity": "",
            "occupant": "",
            "airbag_deployed": "",
            "airbag_status": "",
            "trapped": "",
            "ejection": "",
            "injury": "",
            "ems_name": "",
            "injured_taken_by_ems": "",
            "age": "",
            "injured_taken_to": "",
            "driver_info_id": "",
            "alcohol_test_status": "",
            "alcohol_test_type": "",
            "alcohol_test_value": "",
            "drug_test_status": "",
            "drug_test_type": "",
            "drug_test_value": "",
            "offense_charged": "",
            "local_code": "",
            "offense_description": "",
            "citation_number": "",
            "contact_number": "",
            "ol_class": "",
            "endorsement": "",
            "restriction": "",
            "driver_distracted_by": "",
            "driving_license": "",
            "dl_state": "",
            "alcohol_or_drug_suspected": ""
        }
        
        end_idx = min(start_idx + 100, len(self.lines))
        
        for i in range(start_idx, end_idx):
            if i >= len(self.lines):
                break
            
            line = self.lines[i]
            
            # Injury code
            if "INJURIES" in line:
                if i + 1 < len(self.lines) and self.lines[i + 1].isdigit():
                    person["injury"] = self.lines[i + 1]
            
            # Seating Position
            elif "SEATING" in line and "POSITION" in line:
                for offset in [2, 3]:
                    if i + offset < len(self.lines) and self.lines[i + offset].isdigit():
                        seat = self.lines[i + offset]
                        person["seating_position"] = seat
                        person["same_as_driver"] = "1" if seat == "1" else "0"
                        break
            
            # Name - comes after "NAME: LAST, FIRST, MIDDLE"
            elif line == "NAME: LAST, FIRST, MIDDLE":
                # Name is on the NEXT line
                if i + 1 < len(self.lines):
                    name_line = self.lines[i + 1].strip()
                    if name_line and "DATE OF BIRTH" not in name_line:
                        # Parse: LAST, FIRST, MIDDLE
                        parts = name_line.split(',')
                        if len(parts) >= 1:
                            person["last_name"] = parts[0].strip()
                        if len(parts) >= 2:
                            person["first_name"] = parts[1].strip()
                        if len(parts) >= 3:
                            person["middle_name"] = parts[2].strip()
                        print(f"         Name: {name_line}")
            
            # Date of Birth
            elif "DATE OF BIRTH" in line:
                for offset in [1, 2, 3]:
                    if i + offset < len(self.lines):
                        m = re.search(r'(\d{2})/(\d{2})/(\d{4})', self.lines[i + offset])
                        if m:
                            person["date_of_birth"] = m.group(0)
                            break
            
            # Gender
            elif "GENDER" in line:
                if i + 1 < len(self.lines):
                    gender = self.lines[i + 1].strip()
                    if gender in ["M", "F", "U"]:
                        person["gender"] = gender
            
            # Age
            elif "AGE" in line and "GENDER" not in line:
                if i + 1 < len(self.lines) and self.lines[i + 1].isdigit():
                    person["age"] = self.lines[i + 1]
            
            # Driver's License State
            elif "OL STATE" in line:
                if i + 1 < len(self.lines):
                    dl_state = self.lines[i + 1].strip()
                    if dl_state and "OL CLASS" not in dl_state:
                        person["dl_state"] = dl_state
            
            # Offense Charged
            elif "OFFENSE CHARGED" in line:
                if i + 1 < len(self.lines):
                    offense = self.lines[i + 1].strip()
                    if offense and "LOCAL" not in offense:
                        person["offense_charged"] = offense
            
            # Citation Number
            elif "CITATION NUMBER" in line:
                if i + 1 < len(self.lines):
                    citation = self.lines[i + 1].strip()
                    if citation and "ENDORSEMENT" not in citation:
                        person["citation_number"] = citation
            
            # Stop at next person or vehicle
            elif ("INJURIES" in line and i > start_idx + 20) or \
                 ("UNIT #" in line and i > start_idx + 20):
                break
        
        return person
    
    def _build_final_json(self, basic_info, case_detail, vehicles):
        """Build the final JSON output"""
        return {
            **basic_info,
            "case_detail": [case_detail],
            "vehicles": vehicles
        }


def main():
    """Test the parser"""
    pdf_path = Path("downloads/20235016815.pdf")
    
    if not pdf_path.exists():
        # Try alternative location
        pdf_path = Path("CrashOH1M5.pdf")
    
    if not pdf_path.exists():
        print(f"❌ PDF not found: {pdf_path}")
        return
    
    print("=" * 80)
    print("OHIO PDF PARSER - COMPLETE EXTRACTION")
    print("=" * 80)
    
    parser = OhioPdfParser(pdf_path)
    result = parser.parse()
    
    if result:
        # Save JSON
        output_dir = Path("json_output")
        output_dir.mkdir(exist_ok=True)
        output_file = output_dir / f"{pdf_path.stem}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)
        
        print(f"\n✅ JSON saved to: {output_file}")
        print(f"\n📊 Summary:")
        print(f"  - Report: {result['report_number']}")
        print(f"  - Incident: {result['incident_number']}")
        print(f"  - Date: {result['date_of_crash']}")
        print(f"  - Vehicles: {len(result['vehicles'])}")
        
        total_persons = sum(len(v['persons']) for v in result['vehicles'])
        print(f"  - Total Persons: {total_persons}")
        
        print(f"\n✅ EXTRACTION COMPLETE!")
    else:
        print("❌ Failed to parse PDF")


if __name__ == "__main__":
    main()