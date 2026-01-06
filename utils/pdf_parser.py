import re
import json
from pathlib import Path
from datetime import datetime
import fitz  # PyMuPDF
from utils.logger import log


class OhioPdfParser:
    """
    Ohio PDF Parser - PyMuPDF version
    Uses fitz for clean line-by-line extraction
    """
    
    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self.lines = []  # All text lines
        self.blocks = []  # Structured blocks (backup)
        
    def parse(self):
        """Main parsing entry point"""
        try:
            doc = fitz.open(self.pdf_path)
            
            # Extract all pages
            for page in doc:
                # Get text lines
                text = page.get_text("text")
                page_lines = text.split('\n')
                self.lines.extend([line.strip() for line in page_lines if line.strip()])
                
                # Get blocks for backup
                blocks = page.get_text("blocks")
                self.blocks.extend(blocks)
            
            doc.close()
            
            if not self.lines:
                log.error(f"No text extracted from {self.pdf_path}")
                return None
            
            # Extract crash info
            crash_info = self._extract_crash_basic_info()
            case_info = self._extract_case_info()
            
            # Extract vehicles
            vehicles = self._extract_vehicles()
            
            # Extract persons
            persons = self._extract_persons()
            
            # Map persons to vehicles
            vehicles = self._map_persons_to_vehicles(vehicles, persons)
            
            # Build final JSON
            return self._build_final_json(crash_info, case_info, vehicles)
            
        except Exception as e:
            log.error(f"Parse error for {self.pdf_path}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _find_line(self, pattern, start_idx=0):
        """Find line index matching pattern"""
        for i in range(start_idx, len(self.lines)):
            if isinstance(pattern, str):
                if pattern in self.lines[i]:
                    return i
            else:  # regex
                if pattern.search(self.lines[i]):
                    return i
        return -1
    
    def _get_value_after(self, label, offset=1, start_idx=0):
        """Get value N lines after label"""
        idx = self._find_line(label, start_idx)
        if idx >= 0 and idx + offset < len(self.lines):
            return self.lines[idx + offset].strip()
        return ""
    
    def _extract_crash_basic_info(self) -> dict:
        """Extract basic crash information"""
        info = {
            "report_number": "",
            "case_number": "",
            "department": "",
            "municipality": "",
            "municipality_code": "",
            "no_of_vehicles": 0,
            "county": "",
            "locality_code": "",
            "location": "",
            "date_of_crash": "",
            "reference_road_name": "",
            "local_road_name": ""
        }
        
        # Case Number - LOCAL INFORMATION
        idx = self._find_line("LOCAL INFORMATION")
        if idx >= 0 and idx + 1 < len(self.lines):
            info["case_number"] = self.lines[idx + 1].strip()
        
        # Report Number - LOCAL REPORT NUMBER *
        idx = self._find_line("LOCAL REPORT NUMBER")
        if idx >= 0 and idx + 1 < len(self.lines):
            info["report_number"] = self.lines[idx + 1].strip()
        
        # Department - REPORTING AGENCY NAME *
        idx = self._find_line("REPORTING AGENCY NAME")
        if idx >= 0 and idx + 1 < len(self.lines):
            dept = self.lines[idx + 1].strip()
            if "NCIC" not in dept:
                info["department"] = dept
                info["municipality"] = dept
        
        # NCIC and vehicle count
        idx = self._find_line("NCIC *")
        if idx >= 0 and idx + 1 < len(self.lines):
            next_line = self.lines[idx + 1].strip()
            # Could be "OHP08" followed by "1" on next line, or "OHP08 1" on same line
            if idx + 2 < len(self.lines):
                ncic_line = next_line
                num_line = self.lines[idx + 2].strip()
                
                info["municipality_code"] = ncic_line
                try:
                    info["no_of_vehicles"] = int(num_line)
                except:
                    pass
        
        # County - COUNTY*
        for i, line in enumerate(self.lines):
            if line.startswith("COUNTY") and "*" in line:
                # Check if previous line has "UNSOLVED"
                if i > 0 and "UNSOLVED" in self.lines[i - 1]:
                    if i + 1 < len(self.lines):
                        county_val = self.lines[i + 1].strip()
                        if "CITY" not in county_val:
                            info["county"] = county_val
                break
        
        # Locality - LOCALITY*
        for i, line in enumerate(self.lines):
            if line.startswith("LOCALITY") and "*" in line:
                if i > 0 and "TOWNSHIP" in self.lines[i - 1]:
                    if i + 1 < len(self.lines):
                        loc_val = self.lines[i + 1].strip()
                        if "LOCATION: CITY" not in loc_val:
                            info["locality_code"] = loc_val
                break
        
        # Location (city/village/township name)
        idx = self._find_line("LOCATION: CITY, VILLAGE, TOWNSHIP")
        if idx >= 0 and idx + 1 < len(self.lines):
            loc = self.lines[idx + 1].strip()
            if "CRASH DATE" not in loc:
                info["location"] = loc
        
        # Crash Date/Time - CRASH DATE / TIME*
        idx = self._find_line("CRASH DATE / TIME")
        if idx >= 0 and idx + 1 < len(self.lines):
            date_val = self.lines[idx + 1].strip()
            if "LATITUDE" not in date_val:
                info["date_of_crash"] = date_val
        
        # Reference Road Name
        idx = self._find_line("REFERENCE ROAD NAME")
        if idx >= 0 and idx + 1 < len(self.lines):
            ref_road = self.lines[idx + 1].strip()
            if "ROUTE TYPE" not in ref_road:
                info["reference_road_name"] = ref_road
        
        # Location Road Name
        idx = self._find_line("LOCATION ROAD NAME")
        if idx >= 0:
            # Check if DISTANCE is 2-3 lines ahead
            if (idx + 3 < len(self.lines) and "DISTANCE" in self.lines[idx + 3]) or \
               (idx + 2 < len(self.lines) and "DISTANCE" in self.lines[idx + 2]):
                # Check next line is not a float
                if idx + 1 < len(self.lines):
                    try:
                        float(self.lines[idx + 1].strip())
                    except:
                        info["local_road_name"] = self.lines[idx + 1].strip()
        
        return info
    
    def _extract_case_info(self) -> dict:
        """Extract case routing info"""
        info = {
            "crash_severity": 0,
            "locality": "TOWNSHIP",
            "route_type": "NA",
            "route_number": "NA",
            "route_prefix": "NA"
        }
        
        # Crash Severity - find "FATAL" line
        for i, line in enumerate(self.lines):
            if "FATAL" in line:
                # Extract number before "1 -" or "1-"
                parts = re.split(r'1\s*-|1-', line)
                if len(parts) > 1:
                    try:
                        info["crash_severity"] = int(parts[0].strip())
                    except:
                        pass
                break
        
        # Locality mapping
        for i, line in enumerate(self.lines):
            if line.startswith("LOCALITY") and "*" in line:
                if i > 0 and "TOWNSHIP" in self.lines[i - 1]:
                    if i + 1 < len(self.lines):
                        loc_val = self.lines[i + 1].strip()
                        if "LOCATION: CITY" not in loc_val:
                            locality_map = ["CITY", "VILLAGE", "TOWNSHIP"]
                            try:
                                code = int(loc_val) - 1
                                if 0 <= code < 3:
                                    info["locality"] = locality_map[code]
                            except:
                                pass
                break
        
        # Route information - complex logic
        for i, line in enumerate(self.lines):
            if line == "LOCATION" and i + 1 < len(self.lines) and self.lines[i + 1] == "REFERENCE":
                if i + 2 < len(self.lines) and "ROUTE NUMBER" in self.lines[i + 2]:
                    # Check for PREFIX pattern (7-11 lines ahead)
                    prefix_found = False
                    for offset in [7, 8, 9, 10, 11]:
                        if i + offset < len(self.lines) and "ROUTE TYPE ROUTE NUMBER PREFIX" in self.lines[i + offset]:
                            prefix_found = True
                            # Get prefix from line before "1 - NORTH"
                            for p in range(i + offset, i + offset + 3):
                                if p < len(self.lines) and "1 - NORTH" in self.lines[p]:
                                    if p - 1 >= 0:
                                        info["route_prefix"] = self.lines[p - 1].strip()
                            info["route_type"] = "NA"
                            info["route_number"] = "NA"
                            break
                    
                    if not prefix_found:
                        # Get route type
                        for offset in [7, 8, 9, 10]:
                            if i + offset < len(self.lines) and "ROUTE TYPE ROUTE NUMBER" in self.lines[i + offset]:
                                if i + offset - 1 >= 0:
                                    info["route_type"] = self.lines[i + offset - 1].strip()
                                break
                        
                        # Get route number
                        for offset in [9, 10, 11, 12]:
                            if i + offset < len(self.lines) and "PREFIX 1 - NORTH" in self.lines[i + offset]:
                                if i + offset - 1 >= 0:
                                    info["route_number"] = self.lines[i + offset - 1].strip()
                                break
                        
                        info["route_prefix"] = "NA"
                    break
        
        return info
    
    def _extract_vehicles(self) -> list:
        """Extract vehicle information"""
        vehicles = []
        current_vehicle = None
        current_vehicle_info = None
        
        for i in range(len(self.lines)):
            line = self.lines[i]
            
            # Start of vehicle section - "UNIT #" with "OWNER NAME"
            if "UNIT" in line and "#" in line and i + 1 < len(self.lines) and "OWNER NAME" in self.lines[i + 1]:
                # Save previous vehicle
                if current_vehicle is not None:
                    vehicles.append(self._build_vehicle_dict(current_vehicle, current_vehicle_info))
                
                # Start new vehicle
                current_vehicle = {}
                current_vehicle_info = {}
                
                # Extract unit number (usually next line or in label line)
                if i + 2 < len(self.lines):
                    try:
                        # Try to find a number on the next few lines
                        for offset in range(2, 5):
                            if i + offset < len(self.lines):
                                potential_num = self.lines[i + offset].strip()
                                if potential_num.isdigit():
                                    current_vehicle["vehicle_unit"] = int(potential_num)
                                    current_vehicle_info["vehicle_unit"] = int(potential_num)
                                    break
                    except:
                        current_vehicle["vehicle_unit"] = 1
                        current_vehicle_info["vehicle_unit"] = 1
                
                log.info(f"Processing Unit # {current_vehicle.get('vehicle_unit', '?')}")
            
            # Owner Name (after UNIT #)
            elif current_vehicle and "OWNER NAME" in line and "SAME AS DRIVER" in line:
                if i + 1 < len(self.lines):
                    owner_line = self.lines[i + 1].strip()
                    if owner_line and owner_line != "," and "DAMAGE SCALE" not in owner_line:
                        current_vehicle["owner_name"] = owner_line
            
            # Owner Phone
            elif current_vehicle and "OWNER PHONE" in line:
                if i + 1 < len(self.lines):
                    phone = self.lines[i + 1].strip()
                    if phone and phone.replace("-", "").replace("(", "").replace(")", "").replace(" ", "").isdigit():
                        current_vehicle["owner_phone"] = phone
            
            # Damage Severity
            elif current_vehicle and "MINOR DAMAGE" in line and "DISABLING DAMAGE" in line:
                # Extract number before "2 - MINOR"
                match = re.search(r'(\d{1,2})\s+2\s*-\s*MINOR', line)
                if match:
                    current_vehicle_info["damage_severity"] = match.group(1).strip()
            
            # Owner Address
            elif current_vehicle and "OWNER ADDRESS" in line and "SAME AS DRIVER" in line:
                if i + 1 < len(self.lines):
                    addr = self.lines[i + 1].strip()
                    if addr and "COMMERCIAL CARRIER" not in addr:
                        current_vehicle["owner_address"] = addr
            
            # Commercial Carrier
            elif current_vehicle and "COMMERCIAL CARRIER" in line:
                if i + 1 < len(self.lines):
                    carrier = self.lines[i + 1].strip()
                    if carrier and "DAMAGED AREA" not in carrier:
                        current_vehicle["carrier_name"] = carrier
                    else:
                        current_vehicle["carrier_name"] = "NA"
                        current_vehicle["carrier_number"] = "NA"
            
            # LP STATE, LICENSE PLATE, VIN
            elif current_vehicle and "LP STATE" in line and "LICENSE PLATE" in line:
                # Next line should have state, plate, VIN info
                if i + 1 < len(self.lines):
                    next_line = self.lines[i + 1].strip()
                    
                    if "INSURANCE" in next_line:
                        current_vehicle["vin"] = "NA"
                        current_vehicle["plate_state"] = "NA"
                        current_vehicle["plate_no"] = "NA"
                        current_vehicle["year"] = 0
                        current_vehicle["make"] = "NA"
                    else:
                        # Try to extract VIN (17 characters)
                        vin_match = re.search(r'\b[A-HJ-NPR-Z0-9]{17}\b', next_line)
                        if vin_match:
                            current_vehicle["vin"] = vin_match.group(0)
                        
                        # Get state (2 letters at start)
                        parts = next_line.split()
                        if len(parts) >= 1:
                            current_vehicle["plate_state"] = parts[0]
                        if len(parts) >= 2:
                            current_vehicle["plate_no"] = parts[1]
            
            # YEAR and MAKE (usually on a line after LP STATE)
            elif current_vehicle and line.isdigit() and len(line) == 4 and line.startswith("20"):
                try:
                    current_vehicle["year"] = int(line)
                    # Make is usually next line
                    if i + 1 < len(self.lines):
                        make = self.lines[i + 1].strip()
                        if make and not make.isdigit() and "INSURANCE" not in make:
                            current_vehicle["make"] = make
                except:
                    pass
            
            # Insurance info
            elif current_vehicle and "INSURANCE COMPANY" in line:
                # Look for company name nearby
                for offset in [1, -1, 2]:
                    if i + offset >= 0 and i + offset < len(self.lines):
                        company = self.lines[i + offset].strip()
                        if company and "INSURANCE" not in company and "POLICY" not in company and company != "X":
                            current_vehicle_info["insurance_company"] = company
                            break
            
            # Policy Number
            elif current_vehicle and "POLICY" in line and "#" in line:
                if i + 1 < len(self.lines):
                    policy = self.lines[i + 1].strip()
                    if policy and "COLOR" not in policy:
                        current_vehicle["policy_no"] = policy
            
            # Color and Model
            elif current_vehicle and "COLOR" in line:
                if i + 1 < len(self.lines):
                    color = self.lines[i + 1].strip()
                    if color and "TOWED" not in color:
                        current_vehicle["color"] = color
                        # Model might be next
                        if i + 2 < len(self.lines):
                            model = self.lines[i + 2].strip()
                            if model and not model.isdigit():
                                current_vehicle["model"] = model
            
            # Towed by
            elif current_vehicle and "TOWED BY" in line:
                if i + 1 < len(self.lines):
                    towed = self.lines[i + 1].strip()
                    if towed and towed != "NA":
                        current_vehicle_info["towed_by"] = towed
                        current_vehicle["is_towed"] = True
                    else:
                        current_vehicle_info["towed_by"] = "NA"
                        current_vehicle["is_towed"] = False
            
            # US DOT
            elif current_vehicle and "US DOT" in line:
                if i + 1 < len(self.lines):
                    dot = self.lines[i + 1].strip()
                    if dot.isdigit():
                        current_vehicle_info["us_dot"] = dot
            
            # Hit/Skip
            elif current_vehicle and "HIT/SKIP" in line:
                if i + 1 < len(self.lines) and "X" in self.lines[i + 1]:
                    current_vehicle["is_hit_and_run"] = True
            
            # Occupants
            elif current_vehicle and "OCCUPANTS" in line:
                # Look for number nearby
                for offset in [-1, 1, -2]:
                    if i + offset >= 0 and i + offset < len(self.lines):
                        occ = self.lines[i + offset].strip()
                        if occ.isdigit():
                            current_vehicle_info["no_of_occupants"] = int(occ)
                            break
            
            # Vehicle Type
            elif current_vehicle and "UNIT TYPE" in line:
                # Look back for number
                if i - 1 >= 0:
                    vtype = self.lines[i - 1].strip()
                    if vtype.isdigit():
                        try:
                            current_vehicle["vehicle_type"] = int(vtype)
                        except:
                            pass
            
            # Trailing Units
            elif current_vehicle and "TRAILING UNITS" in line:
                match = re.search(r'\d', line)
                if match:
                    current_vehicle["no_of_trailer"] = int(match.group(0))
            
            # Vehicle Body Type
            elif current_vehicle and "NOT APPLICABLE" in line:
                # Look for number before
                match = re.search(r'(\d{1,2})\s*/', line)
                if match:
                    try:
                        current_vehicle["veh_body_type"] = int(match.group(1))
                    except:
                        pass
            
            # Parked
            elif current_vehicle and "PRE-CRASH" in line:
                # Check for "10" value indicating parked
                if i - 1 >= 0:
                    prev = self.lines[i - 1].strip()
                    if "10" in prev:
                        current_vehicle["is_parked"] = True
            
            # Contributing Circumstances
            elif current_vehicle and "CONTRIBUTING" in line and "CIRCUMSTANCES" in line:
                if i - 1 >= 0:
                    contrib = self.lines[i - 1].strip()
                    try:
                        current_vehicle_info["contributing_circumstance"] = int(contrib.split()[0])
                    except:
                        pass
            
            # Crash Sequence Events
            elif current_vehicle and "EVENTS" in line or "E V N T S" in line:
                # 1st event
                if i + 1 < len(self.lines):
                    match = re.search(r'(\d{1,2})', self.lines[i + 1])
                    if match:
                        current_vehicle_info["crash_seq_1st_event"] = int(match.group(1))
                
                # 2nd, 3rd, 4th events on subsequent lines
                for offset, key in [(6, "crash_seq_2nd_event"), (12, "crash_seq_3rd_event"), (16, "crash_seq_4th_event")]:
                    if i + offset < len(self.lines):
                        match = re.search(r'\d{1,2}', self.lines[i + offset])
                        if match:
                            current_vehicle_info[key] = int(match.group(1))
            
            # Harmful Events
            elif current_vehicle and "FIRST HARMFUL EVENT" in line and "MOST HARMFUL EVENT" in line:
                # Extract both numbers
                match1 = re.search(r'(\d{1,2})\s+FIRST', line)
                if match1:
                    current_vehicle_info["harmful_event"] = int(match1.group(1))
                
                match2 = re.search(r'FIRST HARMFUL EVENT\s+(\d{1,2})', line)
                if match2:
                    current_vehicle_info["most_harmful_event"] = int(match2.group(1))
                
                # Save vehicle and reset
                vehicles.append(self._build_vehicle_dict(current_vehicle, current_vehicle_info))
                current_vehicle = None
                current_vehicle_info = None
            
            # Initial Impact
            elif current_vehicle and "INITIAL POINT OF CONTACT" in line:
                # Look for number in nearby lines
                for offset in [1, 2, 3, 4]:
                    if i + offset < len(self.lines):
                        match = re.search(r'(\d{1,2})\s+1-12', self.lines[i + offset])
                        if match:
                            current_vehicle_info["initial_impact"] = match.group(1)
                            break
            
            # Vehicle Defects
            elif current_vehicle and "VEHICLE" in line and "DEFECTS" in line:
                if i - 2 >= 0:
                    match = re.search(r'(\d{1,2})', self.lines[i - 2])
                    if match:
                        current_vehicle_info["vehicle_defects"] = match.group(1)
            
            # End of vehicle section
            elif current_vehicle and "DATE OF BIRTH" in line:
                if current_vehicle:
                    vehicles.append(self._build_vehicle_dict(current_vehicle, current_vehicle_info))
                    current_vehicle = None
                    current_vehicle_info = None
                break
        
        # Add last vehicle
        if current_vehicle:
            vehicles.append(self._build_vehicle_dict(current_vehicle, current_vehicle_info))
        
        return vehicles
    
    def _build_vehicle_dict(self, veh: dict, veh_info: dict) -> dict:
        """Build intermediate vehicle dictionary"""
        return {
            "vehicle_unit": veh.get("vehicle_unit", 1),
            "is_commercial": veh.get("is_commercial", False),
            "make": veh.get("make", ""),
            "model": veh.get("model", ""),
            "year": veh.get("year", 0),
            "plate_no": veh.get("plate_no", ""),
            "plate_state": veh.get("plate_state", ""),
            "vin": veh.get("vin", ""),
            "policy_no": veh.get("policy_no", ""),
            "is_towed": veh.get("is_towed", False),
            "is_hit_and_run": veh.get("is_hit_and_run", False),
            "vehicle_type": veh.get("vehicle_type", 1),
            "no_of_trailer": veh.get("no_of_trailer", 0),
            "color": veh.get("color", ""),
            "veh_body_type": veh.get("veh_body_type", ""),
            "special_function": veh.get("special_function", ""),
            "is_parked": veh.get("is_parked", False),
            "vehicle_info": veh_info,
            "persons": []
        }
    
    def _extract_persons(self) -> list:
        """Extract person information"""
        persons = []
        current_person = None
        current_person_info = None
        current_driver_info = None
        person_index = 0
        
        for i in range(len(self.lines)):
            line = self.lines[i]
            
            # Start of person section - INJURIES
            if "INJURIES" in line and ("INJURED" in line or (i + 1 < len(self.lines) and "INJURED" in self.lines[i + 1])):
                # Save previous person
                if current_person is not None:
                    person_index += 1
                    current_person["person_index"] = person_index
                    current_person_info["person_index"] = person_index
                    current_driver_info["person_index"] = person_index
                    persons.append({
                        "basic": current_person,
                        "info": current_person_info,
                        "driver": current_driver_info
                    })
                
                # Start new person
                current_person = {}
                current_person_info = {}
                current_driver_info = {}
                
                # Get injury code
                if i + 1 < len(self.lines):
                    inj = self.lines[i + 1].strip()
                    if inj.isdigit():
                        current_person_info["injuries"] = inj
                    else:
                        current_person_info["injuries"] = "0"
            
            # Injured Taken By EMS
            elif current_person and "TAKEN" in line and "BY" in line:
                # Look for number
                for offset in [1, -1, 2]:
                    if i + offset >= 0 and i + offset < len(self.lines):
                        taken = self.lines[i + offset].strip()
                        if taken.isdigit() and len(taken) <= 2:
                            current_person_info["injured_taken_by_ems"] = taken
                            break
            
            # EMS Agency Name
            elif current_person and "EMS AGENCY" in line:
                if i + 1 < len(self.lines):
                    ems = self.lines[i + 1].strip()
                    if ems and "MEDICAL FACILITY" not in ems:
                        current_person_info["name_of_ems"] = ems
                    else:
                        current_person_info["name_of_ems"] = "NA"
            
            # Medical Facility
            elif current_person and "MEDICAL FACILITY" in line:
                if i + 1 < len(self.lines):
                    facility = self.lines[i + 1].strip()
                    if facility and "SAFETY" not in facility:
                        current_person_info["injured_taken_to"] = facility
                    else:
                        current_person_info["injured_taken_to"] = "NA"
            
            # Seating Position
            elif current_person and "SEATING" in line and "POSITION" in line:
                if i + 1 < len(self.lines):
                    seat = self.lines[i + 1].strip()
                    if seat.isdigit():
                        seating_pos = int(seat)
                        current_person_info["seating_position"] = seating_pos
                        current_person["is_same_as_driver"] = (seating_pos == 1)
            
            # Air Bag Usage
            elif current_person and "AIR BAG" in line:
                if i + 1 < len(self.lines):
                    airbag = self.lines[i + 1].strip()
                    if airbag.isdigit():
                        current_person_info["air_bag_status"] = int(airbag)
                        current_person_info["air_bag_deployed"] = int(airbag)
            
            # Ejection
            elif current_person and "EJECTION" in line and "TRAPPED" not in line:
                if i + 1 < len(self.lines):
                    eject = self.lines[i + 1].strip()
                    if eject.isdigit():
                        current_person_info["ejection"] = int(eject)
            
            # Trapped
            elif current_person and "TRAPPED" in line and "ADDRESS" not in line:
                if i + 1 < len(self.lines):
                    trap = self.lines[i + 1].strip()
                    if trap.isdigit():
                        current_person_info["trapped"] = int(trap)
            
            # Unit Number and Name
            elif current_person and "UNIT" in line and "#" in line and i + 1 < len(self.lines) and "NAME" in self.lines[i + 1]:
                # Get unit number
                if i + 2 < len(self.lines):
                    unit = self.lines[i + 2].strip()
                    if unit.isdigit():
                        vehicle_num = int(unit)
                        current_person["vehicle_number"] = vehicle_num
                        current_person_info["vehicle_unit"] = vehicle_num
                        current_driver_info["vehicle_unit"] = vehicle_num
                
                # Get person name (few lines down)
                #for offset in range(3


