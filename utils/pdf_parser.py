import re
import json
from pathlib import Path
from datetime import datetime
import pdfplumber
from utils.logger import log


def convert_pdf_to_json(pdf_path: Path, crash_number: str = "", document_number: str = ""):
    """
    Main entry point to convert PDF to JSON
    Args:
        pdf_path: Path to the PDF file
        crash_number: Optional crash number
        document_number: Optional document number
    Returns:
        Dictionary containing the parsed JSON data, or None if parsing failed
    """
    try:
        parser = OhioPdfParser(pdf_path)
        json_data = parser.parse()
        
        if json_data:
            # Save JSON file
            json_path = pdf_path.parent / f"{pdf_path.stem}.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            
            log.info(f"✅ JSON saved: {json_path.name}")
            return json_data
        else:
            log.error(f"❌ Failed to parse PDF: {pdf_path.name}")
            return None
            
    except Exception as e:
        log.error(f"❌ Error converting PDF to JSON: {e}")
        import traceback
        traceback.print_exc()
        return None


class OhioPdfParser:
    """Parser for Ohio crash report PDFs matching C# legacy code logic"""
    
    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self.raw_lines = []
        self.pure_lines = []
        
    def parse(self):
        """Parse the PDF and return structured data"""
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                # Extract text in both raw and pure formats
                raw_text_pages = []
                pure_text_pages = []
                
                for page in pdf.pages:
                    raw_text = page.extract_text() or ""
                    raw_text_pages.append(raw_text)
                    
                # Combine all pages
                full_raw_text = "\n".join(raw_text_pages)
                self.raw_lines = [line for line in full_raw_text.split('\n') if line.strip()]
                
                # Pure text extraction (for vehicle details)
                with pdfplumber.open(self.pdf_path) as pdf:
                    pure_texts = []
                    for page in pdf.pages:
                        # Use layout mode for better parsing
                        pure_text = page.extract_text(layout=True) or ""
                        pure_texts.append(pure_text)
                
                full_pure_text = "\n".join(pure_texts)
                self.pure_lines = [line for line in full_pure_text.split('\n') if line.strip()]
            
            # Extract data following C# structure
            crash_info = self._extract_crash_info()
            case_detail = self._extract_case_detail()
            vehicles = self._extract_all_vehicles()
            
            # Build the final JSON structure
            return self._build_json_structure(crash_info, case_detail, vehicles)
            
        except Exception as e:
            log.error(f"Error parsing PDF {self.pdf_path}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _extract_crash_info(self) -> dict:
        """Extract basic crash information (matches ohioCaseBasicInfo)"""
        info = {
            "incident_number": "NA",
            "report_number": "NA",
            "department": "NA",
            "state_code": "",
            "state_abbreviation": "OH",
            "state_name": "OHIO",
            "county_code": "NA",
            "county": "NA",
            "municipality_code": "NA",
            "municipality": "NA",
            "crash_location": "NA",
            "crash_type_l1": "",
            "crash_type_l2": "",
            "date_of_crash": "NA",
            "total_killed": "",
            "total_injured": "",
            "total_vehicles": "0",
            "case_file_s3_path": "",
            "s3_bucket_name": "",
            "s3_access_key": "",
            "s3_secret_key": "",
            "pdf_file_path": str(self.pdf_path),
        }
        
        for i, line in enumerate(self.raw_lines):
            # Report Number (LOCAL INFORMATION)
            if "LOCAL INFORMATION" in line:
                report_match = re.search(r'P\d{14}', line)
                if report_match:
                    info["report_number"] = report_match.group(0)
            
            # Case Number (LOCAL REPORT NUMBER)
            elif line.startswith("REPORT NUMBER *") or "LOCAL REPORT NUMBER" in line:
                if i + 1 < len(self.raw_lines):
                    case_match = re.match(r'([0-9A-Za-z-]+)', self.raw_lines[i + 1].strip())
                    if case_match:
                        case_num = case_match.group(1)
                        # Remove trailing indicators
                        case_num = re.sub(r'(X(\s|P)|PHOTOS).*$', '', case_num).strip()
                        info["incident_number"] = case_num
            
            # Department (REPORTING AGENCY NAME)
            elif line.startswith("REPORTING AGENCY NAME *"):
                if i + 1 < len(self.raw_lines):
                    dept_line = self.raw_lines[i + 1].strip()
                    if "NCIC *" not in dept_line and dept_line:
                        info["department"] = dept_line
                        info["municipality"] = dept_line
            
            # Municipality Code (NCIC)
            elif line.startswith("NCIC *"):
                if i + 1 < len(self.raw_lines):
                    ncic_parts = self.raw_lines[i + 1].strip().split()
                    if ncic_parts and not ncic_parts[0].startswith("NUMBER"):
                        info["municipality_code"] = ncic_parts[0]
                        # Number of vehicles
                        if len(ncic_parts) > 1 and ncic_parts[0] != "NUMBER":
                            try:
                                info["total_vehicles"] = ncic_parts[1]
                            except:
                                pass
            
            # County
            elif line.startswith("COUNTY*") and i > 0 and "UNSOLVED" in self.raw_lines[i - 1]:
                if i + 1 < len(self.raw_lines):
                    county_line = self.raw_lines[i + 1].strip()
                    if "CITY" not in county_line:
                        info["county_code"] = county_line
                        info["county"] = county_line
            
            # Crash Location
            elif line.startswith("LOCATION: CITY, VILLAGE, TOWNSHIP*"):
                if i + 1 < len(self.raw_lines):
                    loc_line = self.raw_lines[i + 1].strip()
                    if "CRASH DATE" not in loc_line and loc_line:
                        info["crash_location"] = loc_line
            
            # Crash Date
            elif line.startswith("CRASH DATE / TIME*") or "CRASH DATE / TIME*" in line:
                if i + 1 < len(self.raw_lines):
                    datetime_match = re.search(r'(\d{2}/\d{2}/\d{4})', self.raw_lines[i + 1])
                    if datetime_match:
                        try:
                            dt = datetime.strptime(datetime_match.group(1), "%m/%d/%Y")
                            info["date_of_crash"] = dt.strftime("%Y-%m-%d")
                        except:
                            info["date_of_crash"] = datetime_match.group(1)
        
        return info
    
    def _extract_case_detail(self) -> list:
        """Extract case detail information (matches ohioCaseInfo)"""
        detail = {
            "local_information": "",
            "locality": "TOWNSHIP",
            "location": "NA",
            "route_type": "NA",
            "route_number": "NA",
            "route_prefix": "NA",
            "lane_speed_limit_1": "",
            "lane_speed_limit_2": "",
            "crash_severity": "5"
        }
        
        for i, line in enumerate(self.raw_lines):
            # Locality
            if line.startswith("LOCALITY*") and i > 0 and "TOWNSHIP" in self.raw_lines[i - 1]:
                if i + 1 < len(self.raw_lines):
                    locality_code = self.raw_lines[i + 1].strip()
                    if locality_code == "1":
                        detail["locality"] = "CITY"
                    elif locality_code == "2":
                        detail["locality"] = "VILLAGE"
                    elif locality_code == "3":
                        detail["locality"] = "TOWNSHIP"
            
            # Crash Severity
            elif "FATAL" in line:
                severity_match = re.match(r'^\s*(\d+)', line)
                if severity_match:
                    detail["crash_severity"] = severity_match.group(1)
            
            # Location Road Name
            elif line.startswith("LOCATION ROAD NAME"):
                if i + 1 < len(self.raw_lines):
                    next_line = self.raw_lines[i + 1]
                    # Check if it's not a distance value
                    if not re.match(r'^\d+(\.\d+)?$', next_line.strip()):
                        if i + 3 < len(self.raw_lines) and "DISTANCE" in self.raw_lines[i + 3]:
                            detail["location"] = next_line.strip()
                        elif i + 2 < len(self.raw_lines) and "DISTANCE" in self.raw_lines[i + 2]:
                            detail["location"] = next_line.strip()
            
            # Route Type and Number
            elif line == "LOCATION" and i + 1 < len(self.raw_lines) and self.raw_lines[i + 1] == "REFERENCE":
                # Look ahead for route information
                for j in range(i, min(i + 15, len(self.raw_lines))):
                    if "ROUTE TYPE ROUTE NUMBER" in self.raw_lines[j]:
                        # Check for PREFIX or route type/number
                        for k in range(j + 1, min(j + 10, len(self.raw_lines))):
                            route_type_match = re.match(r'^(SR|US|CR|IR|TR)$', self.raw_lines[k].strip())
                            if route_type_match:
                                detail["route_type"] = route_type_match.group(1)
                                # Route number is typically next
                                if k + 1 < len(self.raw_lines):
                                    route_num_match = re.match(r'^(\d+)', self.raw_lines[k + 1].strip())
                                    if route_num_match:
                                        detail["route_number"] = route_num_match.group(1)
                                break
                        break
        
        return [detail]
    
    def _extract_all_vehicles(self) -> list:
        """Extract all vehicle information"""
        vehicles = []
        person_index = 0
        
        # Find all UNIT # markers in raw_lines for person extraction
        # Find vehicle data in pure_lines
        
        vehicle_units = []
        for i, line in enumerate(self.pure_lines):
            if "UNIT #" in line and "OWNER NAME" in line:
                vehicle_units.append(i)
        
        for unit_idx, line_num in enumerate(vehicle_units):
            vehicle_data = self._extract_vehicle_from_pure(line_num, unit_idx + 1)
            if vehicle_data:
                # Now extract person data from raw_lines for this unit
                persons = self._extract_persons_for_unit(unit_idx + 1)
                vehicle_data["persons"] = persons
                vehicles.append(vehicle_data)
        
        return vehicles
    
    def _extract_vehicle_from_pure(self, start_idx: int, unit_num: int) -> dict:
        """Extract vehicle data from pure_lines (matches ohioBasicVehicleInfo + ohioVehicleInfo)"""
        vehicle = {
            "vehicle_unit": str(unit_num),
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
            }
        }
        
        # Parse from pure_lines starting at start_idx
        search_range = self.pure_lines[start_idx:min(start_idx + 80, len(self.pure_lines))]
        
        for i, line in enumerate(search_range):
            abs_i = start_idx + i
            
            # Owner name, phone, etc. from first line
            if "OWNER NAME" in line and "OWNER PHONE" in line:
                if i + 1 < len(search_range):
                    parts = search_range[i + 1].split('  ')
                    parts = [p.strip() for p in parts if p.strip()]
                    # Parts typically: [unit#, owner_name, phone, ...]
            
            # LP STATE, LICENSE PLATE, VIN
            elif "LP STATE" in line and "LICENSE PLATE" in line and "VEHICLE IDENTIFICATION" in line:
                if i + 1 < len(search_range):
                    data_line = search_range[i + 1]
                    parts = [p.strip() for p in data_line.split('  ') if p.strip()]
                    
                    if len(parts) >= 2:
                        vehicle["plate_state"] = f" {parts[0]}"
                        vehicle["plate_number"] = f" {parts[1]}"
                    
                    vin_match = re.search(r'\b([A-HJ-NPR-Z0-9]{17})\b', data_line)
                    if vin_match:
                        vehicle["vin"] = vin_match.group(1)
                    
                    if len(parts) >= 4:
                        try:
                            vehicle["vehicle_year"] = parts[3]
                        except:
                            pass
                    if len(parts) >= 5:
                        vehicle["make"] = f" {parts[4]}"
            
            # Insurance company, policy, color, model
            elif "INSURANCE" in line and "INSURANCE COMPANY" in line and "INSURANCE POLICY" in line:
                if i + 1 < len(search_range):
                    data_line = search_range[i + 1]
                    parts = [p.strip() for p in data_line.split('   ') if p.strip()]
                    
                    if len(parts) >= 1 and parts[0] == "X":
                        vehicle["vehicle_details"]["insurance_verified"] = "X"
                    if len(parts) >= 3:
                        vehicle["vehicle_details"]["insurance_company"] = parts[2]
                    if len(parts) >= 4:
                        vehicle["policy"] = parts[3]
                    if len(parts) >= 5:
                        vehicle["color"] = parts[4]
                    if len(parts) >= 6:
                        vehicle["model"] = parts[5]
            
            # Towed by
            elif "TOWED BY: COMPANY" in line and "US DOT" in line:
                if i + 2 < len(search_range):
                    tow_line = search_range[i + 2]
                    parts = [p.strip() for p in tow_line.split('  ') if p.strip()]
                    
                    for part in parts:
                        if not part.isdigit() and len(part) > 2:
                            vehicle["vehicle_details"]["towed_by"] = part
                            vehicle["is_towed"] = "1"
                            break
                    
                    # US DOT
                    for part in parts:
                        if part.isdigit():
                            vehicle["vehicle_details"]["us_dot"] = part
                            break
                
                # Check for commercial (X mark)
                if i + 3 < len(search_range):
                    if search_range[i + 3].strip().startswith("X"):
                        vehicle["is_commercial"] = "1"
            
            # Hit and Run
            elif "HIT/SKIP UNIT" in line:
                if i + 1 < len(search_range):
                    if re.search(r'\sX\s', search_range[i + 1]):
                        vehicle["is_hit_and_run"] = "1"
            
            # Vehicle Type
            elif "UNIT TYPE" in line:
                if i - 3 >= 0 and "MINIVAN" in search_range[i - 3]:
                    type_match = re.match(r'^\s*(\d+)', search_range[i - 3])
                    if type_match:
                        vehicle["vehicle_type"] = type_match.group(1)
            
            # Contributing Circumstance
            elif "CONTRIBUTING" in line and i + 1 < len(search_range) and "CIRCUMSTANCES" in search_range[i + 1]:
                if i - 2 >= 0:
                    parts = [p.strip() for p in search_range[i - 2].split('  ') if p.strip()]
                    if parts and parts[0].isdigit():
                        vehicle["vehicle_details"]["contributing_circumstance"] = parts[0]
            
            # Harmful Events
            elif "FIRST HARMFUL EVENT" in line and "MOST HARMFUL EVENT" in line:
                first_match = re.search(r'\s*(\d{1,2})\s*(?=FIRST HARMFUL EVENT)', line)
                if first_match:
                    vehicle["vehicle_details"]["harmful_event"] = first_match.group(1)
                
                most_match = re.search(r'(?<=FIRST HARMFUL EVENT)\s*(\d{1,2})\s*(?=MOST HARMFUL EVENT)', line)
                if most_match:
                    vehicle["vehicle_details"]["most_harmful_event"] = most_match.group(1)
        
        return vehicle
    
    def _extract_persons_for_unit(self, unit_num: int) -> list:
        """Extract person data for a specific unit from raw_lines"""
        persons = []
        
        # Find all person entries for this unit
        for i, line in enumerate(self.raw_lines):
            if line.startswith("UNIT  #") or "UNIT #" in line:
                # Check if next line has our unit number
                if i + 1 < len(self.raw_lines):
                    unit_match = re.match(r'^\s*(\d+)\s*$', self.raw_lines[i + 1].strip())
                    if unit_match and int(unit_match.group(1)) == unit_num:
                        person = self._extract_person_data(i)
                        if person:
                            persons.append(person)
        
        return persons
    
    def _extract_person_data(self, unit_line_idx: int) -> dict:
        """Extract person data starting from UNIT # line"""
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
        
        search_end = min(unit_line_idx + 60, len(self.raw_lines))
        
        for i in range(unit_line_idx, search_end):
            line = self.raw_lines[i]
            
            # Name
            if "NAME: LAST, FIRST, MIDDLE" in line:
                if i + 1 < len(self.raw_lines):
                    name_line = self.raw_lines[i + 1].strip()
                    if name_line and "CONTACT PHONE" not in name_line:
                        name_parts = name_line.split(',')
                        if len(name_parts) >= 1:
                            person["last_name"] = name_parts[0].strip()
                        if len(name_parts) >= 2:
                            person["first_name"] = name_parts[1].strip()
                        if len(name_parts) >= 3:
                            person["middle_name"] = name_parts[2].strip()
            
            # Address
            elif "ADDRESS: STREET, CITY, STATE, ZIP" in line:
                if i + 1 < len(self.raw_lines):
                    addr_line = self.raw_lines[i + 1].strip()
                    if addr_line and "SAME AS DRIVER" not in addr_line:
                        addr_parts = [p.strip() for p in addr_line.split(',')]
                        if len(addr_parts) >= 1:
                            person["address_block"]["address_line1"] = addr_parts[0]
                        if len(addr_parts) >= 2:
                            person["address_block"]["address_city"] = addr_parts[1]
                        if len(addr_parts) >= 3:
                            person["address_block"]["address_state"] = addr_parts[2]
                        if len(addr_parts) >= 4:
                            person["address_block"]["address_zip"] = addr_parts[3]
            
            # DOB
            elif "DATE OF BIRTH" in line:
                dob_match = re.search(r'(\d{2}/\d{2}/\d{4})', line)
                if not dob_match and i + 1 < len(self.raw_lines):
                    dob_match = re.search(r'(\d{2}/\d{2}/\d{4})', self.raw_lines[i + 1])
                if dob_match:
                    person["date_of_birth"] = dob_match.group(1)
            
            # Age
            elif "AGE" in line and "GENDER" in line:
                age_match = re.search(r'\b(\d{1,3})\b', line)
                if age_match:
                    person["age"] = age_match.group(1)
                elif i + 1 < len(self.raw_lines):
                    age_match = re.search(r'^(\d{1,3})', self.raw_lines[i + 1].strip())
                    if age_match:
                        person["age"] = age_match.group(1)
            
            # Gender
            elif "GENDER" in line:
                gender_match = re.search(r'\b([MFU])\b', line)
                if gender_match:
                    person["gender"] = gender_match.group(1)
                elif i + 1 < len(self.raw_lines):
                    gender_match = re.search(r'^([MFU])$', self.raw_lines[i + 1].strip())
                    if gender_match:
                        person["gender"] = gender_match.group(1)
            
            # Contact Phone
            elif "CONTACT PHONE" in line:
                if i + 1 < len(self.raw_lines):
                    phone_match = re.search(r'(\d{3}[-.]?\d{3}[-.]?\d{4})', self.raw_lines[i + 1])
                    if phone_match:
                        person["contact_number"] = phone_match.group(1)
            
            # OL STATE
            elif line.strip() == "OL STATE":
                if i + 1 < len(self.raw_lines):
                    state_match = re.match(r'^([A-Z]{2})$', self.raw_lines[i + 1].strip())
                    if state_match:
                        person["dl_state"] = state_match.group(1)
            
            # OL CLASS
            elif line.strip() == "OL CLASS":
                if i + 1 < len(self.raw_lines):
                    class_match = re.match(r'^(\d+)$', self.raw_lines[i + 1].strip())
                    if class_match:
                        person["ol_class"] = class_match.group(1)
            
            # Offense Charged
            elif "OFFENSE CHARGED" in line:
                if i + 1 < len(self.raw_lines):
                    offense_line = self.raw_lines[i + 1].strip()
                    if re.match(r'^\d{4}', offense_line):
                        person["offense_charged"] = offense_line
            
            # Offense Description
            elif "OFFENSE DESCRIPTION" in line:
                if i + 1 < len(self.raw_lines):
                    desc_line = self.raw_lines[i + 1].strip()
                    if desc_line and len(desc_line) > 3:
                        person["offense_description"] = desc_line
            
            # Citation Number
            elif "CITATION NUMBER" in line:
                if i + 1 < len(self.raw_lines):
                    citation_line = self.raw_lines[i + 1].strip()
                    if citation_line and len(citation_line) > 5:
                        person["citation_number"] = citation_line
        
        return person
    
    def _build_json_structure(self, crash_info: dict, case_detail: list, vehicles: list) -> dict:
        """Build final JSON matching the target format"""
        return {
            **crash_info,
            "case_detail": case_detail,
            "vehicles": vehicles
        }