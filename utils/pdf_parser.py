import re
import json
from pathlib import Path
from datetime import datetime
import pdfplumber
from utils.logger import log


class OhioPdfParser:
    """
    Ohio PDF Parser - matches C# logic exactly
    Uses two-pass extraction: layout-preserved (raw) and cleaned text (pure)
    """
    
    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self.raw_lines = []  # Layout-preserved (like C# Raw mode)
        self.pure_lines = []  # Cleaned text (like C# Pure mode)
        
    def parse(self):
        """Main parsing entry point"""
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                # Extract in both modes
                for page in pdf.pages:
                    # Raw mode: preserve layout
                    raw_text = page.extract_text(layout=True) or ""
                    raw_lines = raw_text.split('\n')
                    self.raw_lines.extend([line for line in raw_lines if line.strip()])
                    
                    # Pure mode: clean text
                    pure_text = page.extract_text(layout=False) or ""
                    pure_lines = pure_text.split('\n')
                    self.pure_lines.extend([line for line in pure_lines if line.strip()])
            
            if not self.raw_lines:
                log.error(f"No text extracted from {self.pdf_path}")
                return None
            
            # Extract crash info (from raw_lines)
            crash_info = self._extract_crash_basic_info()
            case_info = self._extract_case_info()
            
            # Extract vehicles (from pure_lines - better for structured data)
            vehicles = self._extract_vehicles()
            
            # Extract persons (from raw_lines)
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
    
    def _extract_crash_basic_info(self) -> dict:
        """Extract basic crash information - matches C# BasicInfo region"""
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
        
        for l in range(len(self.raw_lines)):
            line = self.raw_lines[l]
            
            # Case Number (incident_number) - from LOCAL INFORMATION line
            if "LOCAL INFORMATION" in line:
                match = re.search(r'(?<=LOCAL INFORMATION).*', line)
                if match:
                    info["case_number"] = match.group(0).strip()
            
            # Report Number (report_number) - from REPORT NUMBER * section
            elif "REPORT NUMBER *" in line or "LOCAL REPORT NUMBER *" in line:
                if l + 1 < len(self.raw_lines):
                    next_line = self.raw_lines[l + 1]
                    # Pattern: extract before "X" or "PHOTOS"
                    match = re.search(r'([0-9\-A-Za-z ]*(?=X(\s|P)))|([0-9A-Za-z\- ]*(?=PHOTOS))', next_line)
                    if match:
                        info["report_number"] = match.group(0).strip()
            
            # Department - from REPORTING AGENCY NAME *
            elif line.startswith("REPORTING AGENCY NAME *"):
                if l + 1 < len(self.raw_lines):
                    next_line = self.raw_lines[l + 1]
                    if "NCIC *" not in next_line:
                        info["department"] = next_line.strip()
                        info["municipality"] = next_line.strip()
            
            # NCIC (municipality code) and vehicle count
            elif line.startswith("NCIC *"):
                if l + 1 < len(self.raw_lines):
                    next_line = self.raw_lines[l + 1]
                    if not next_line.startswith("NUMBER OF UNITS"):
                        parts = next_line.strip().split(' ')
                        if len(parts) >= 2:
                            info["municipality_code"] = parts[0]
                            try:
                                info["no_of_vehicles"] = int(parts[1])
                            except:
                                pass
            
            # County
            elif line.startswith("COUNTY*"):
                if l - 1 >= 0 and "UNSOLVED" in self.raw_lines[l - 1]:
                    if l + 1 < len(self.raw_lines):
                        next_line = self.raw_lines[l + 1]
                        if "CITY" not in next_line:
                            info["county"] = next_line.strip()
            
            # Locality
            elif line.startswith("LOCALITY*"):
                if l - 1 >= 0 and self.raw_lines[l - 1].endswith("TOWNSHIP"):
                    if l + 1 < len(self.raw_lines):
                        next_line = self.raw_lines[l + 1]
                        if "LOCATION: CITY, VILLAGE, TOWNSHIP*" not in next_line:
                            info["locality_code"] = next_line.strip()
            
            # Location (city/village/township name)
            elif line.startswith("LOCATION: CITY, VILLAGE, TOWNSHIP*"):
                if l + 1 < len(self.raw_lines):
                    next_line = self.raw_lines[l + 1]
                    if "CRASH DATE" not in next_line:
                        info["location"] = next_line.strip()
            
            # Crash Date/Time
            elif line.startswith("CRASH DATE / TIME*"):
                if l + 1 < len(self.raw_lines):
                    next_line = self.raw_lines[l + 1]
                    if "LATITUDE" not in next_line:
                        info["date_of_crash"] = next_line.strip()
            
            # Reference Road Name
            elif "REFERENCE ROAD NAME (ROAD, MILEPOST, HOUSE #)" in line:
                if l + 1 < len(self.raw_lines):
                    next_line = self.raw_lines[l + 1]
                    if "ROUTE TYPE" not in next_line:
                        info["reference_road_name"] = next_line.strip()
            
            # Location Road Name
            elif line.startswith("LOCATION ROAD NAME"):
                # Check if DISTANCE is 2-3 lines ahead
                if (l + 3 < len(self.raw_lines) and self.raw_lines[l + 3].startswith("DISTANCE")) or \
                   (l + 2 < len(self.raw_lines) and self.raw_lines[l + 2].startswith("DISTANCE")):
                    # Check if next line is not a float
                    try:
                        float(self.raw_lines[l + 1].strip())
                    except:
                        info["local_road_name"] = self.raw_lines[l + 1].strip()
        
        return info
    
    def _extract_case_info(self) -> dict:
        """Extract case routing info - matches C# CaseInfo"""
        info = {
            "crash_severity": 0,
            "locality": "TOWNSHIP",
            "route_type": "NA",
            "route_number": "NA",
            "route_prefix": "NA"
        }
        
        for l in range(len(self.raw_lines)):
            line = self.raw_lines[l]
            
            # Crash Severity
            if line.endswith("FATAL"):
                parts = re.split(r'1\s*-|1-', line)
                if len(parts) > 1:
                    try:
                        info["crash_severity"] = int(parts[0].strip())
                    except:
                        pass
            
            # Locality mapping
            elif line.startswith("LOCALITY*"):
                if l - 1 >= 0 and self.raw_lines[l - 1].endswith("TOWNSHIP"):
                    if l + 1 < len(self.raw_lines):
                        next_line = self.raw_lines[l + 1]
                        if "LOCATION: CITY, VILLAGE, TOWNSHIP*" not in next_line:
                            locality_map = ["CITY", "VILLAGE", "TOWNSHIP"]
                            try:
                                code = int(next_line.strip()) - 1
                                if 0 <= code < 3:
                                    info["locality"] = locality_map[code]
                            except:
                                pass
            
            # Route information - complex multi-line logic
            elif line == "LOCATION" and l + 1 < len(self.raw_lines) and self.raw_lines[l + 1] == "REFERENCE":
                if l + 2 < len(self.raw_lines) and "ROUTE NUMBER" in self.raw_lines[l + 2]:
                    # Check for PREFIX pattern (7-11 lines ahead)
                    prefix_found = False
                    for offset in [7, 8, 9, 10, 11]:
                        if l + offset < len(self.raw_lines) and "ROUTE TYPE ROUTE NUMBER PREFIX" in self.raw_lines[l + offset]:
                            prefix_found = True
                            # Get prefix from line before "1 - NORTH"
                            for p in range(l + offset, l + offset + 3):
                                if p < len(self.raw_lines) and "1 - NORTH" in self.raw_lines[p]:
                                    if p - 1 >= 0:
                                        info["route_prefix"] = self.raw_lines[p - 1].strip()
                            info["route_type"] = "NA"
                            info["route_number"] = "NA"
                            break
                    
                    if not prefix_found:
                        # Get route type
                        for offset in [7, 8, 9, 10]:
                            if l + offset < len(self.raw_lines) and "ROUTE TYPE ROUTE NUMBER" in self.raw_lines[l + offset]:
                                if l + offset - 1 >= 0:
                                    info["route_type"] = self.raw_lines[l + offset - 1].strip()
                                break
                        
                        # Get route number
                        for offset in [9, 10, 11, 12]:
                            if l + offset < len(self.raw_lines) and "PREFIX 1 - NORTH" in self.raw_lines[l + offset]:
                                if l + offset - 1 >= 0:
                                    info["route_number"] = self.raw_lines[l + offset - 1].strip()
                                break
                        
                        info["route_prefix"] = "NA"
                    break
        
        return info
    
    def _extract_vehicles(self) -> list:
        """Extract vehicle information - uses pure_lines like C# VehicleDetailsGet"""
        vehicles = []
        current_vehicle = None
        current_vehicle_info = None
        
        for i in range(len(self.pure_lines)):
            line = self.pure_lines[i]
            
            # Start of vehicle section
            if "UNIT #" in line and "OWNER NAME: LAST, FIRST, MIDDLE" in line and "SAME AS DRIVER" in line and "OWNER PHONE" in line:
                # Save previous vehicle if exists
                if current_vehicle is not None:
                    vehicles.append(self._build_vehicle_dict(current_vehicle, current_vehicle_info))
                
                # Start new vehicle
                current_vehicle = {}
                current_vehicle_info = {}
                
                if i + 1 < len(self.pure_lines):
                    parts = re.split(r'\s{2,}|DAMAGE SCALE', self.pure_lines[i + 1])
                    parts = [p.strip() for p in parts if p.strip() and p.strip() != ' ']
                    
                    if len(parts) >= 1:
                        try:
                            current_vehicle["vehicle_unit"] = int(parts[0])
                            current_vehicle_info["vehicle_unit"] = int(parts[0])
                        except:
                            pass
                    if len(parts) >= 2 and parts[1] != ",":
                        current_vehicle["owner_name"] = parts[1]
                    if len(parts) >= 3:
                        current_vehicle["owner_phone"] = parts[2]
                    
                    log.info(f"Processing Unit # {current_vehicle.get('vehicle_unit', '?')}")
            
            # Damage Severity
            elif current_vehicle and "2 - MINOR DAMAGE" in line and "4 - DISABLING DAMAGE" in line:
                match = re.search(r'\d{1,2}\s{1,15}(?=(2 - MINOR DAMAGE))', line)
                if match:
                    current_vehicle_info["damage_severity"] = match.group(0).strip()
            
            # Owner Address
            elif current_vehicle and "OWNER ADDRESS: STREET, CITY, STATE, ZIP" in line and "SAME AS DRIVER" in line:
                if i + 1 < len(self.pure_lines):
                    # Match address before large spacing and digit
                    matches = re.findall(r'[a-zA-Z0-9,. ]*(?=(\s{4,}\d\s{2,3}))', self.pure_lines[i + 1])
                    if not matches:
                        matches = re.findall(r'[a-zA-Z0-9,. ]*(?=(\s{4,}\d\s{1,2}-))', self.pure_lines[i + 1])
                    if matches and matches[0].strip():
                        current_vehicle["owner_address"] = matches[0].strip()
            
            # Commercial Carrier
            elif current_vehicle and "COMMERCIAL CARRIER: NAME, ADDRESS, CITY, STATE, ZIP" in line:
                if i + 1 < len(self.pure_lines):
                    parts = re.split(r'\s{3,}|DAMAGED AREA\(S\)', self.pure_lines[i + 1])
                    parts = [p.strip() for p in parts if p.strip() and p.strip() != ' ']
                    current_vehicle["carrier_name"] = parts[0] if len(parts) >= 1 else "NA"
                    current_vehicle["carrier_number"] = parts[1] if len(parts) >= 2 else "NA"
            
            # LP STATE, LICENSE PLATE, VIN
            elif current_vehicle and "LP STATE" in line and "LICENSE PLATE" in line and "VEHICLE IDENTIFICATION" in line:
                if i + 1 < len(self.pure_lines):
                    next_line = self.pure_lines[i + 1]
                    if "INSURANCE" in next_line and "INSURANCE COMPANY" in next_line:
                        # No vehicle data
                        current_vehicle["vin"] = "NA"
                        current_vehicle["plate_state"] = "NA"
                        current_vehicle["plate_no"] = "NA"
                        current_vehicle["year"] = 0
                        current_vehicle["make"] = "NA"
                    else:
                        parts = re.split(r'\s{2,}', next_line)
                        parts = [p.strip() for p in parts if p.strip()]
                        
                        # Extract VIN
                        vin_match = re.search(r'\w{17}', next_line)
                        if vin_match:
                            current_vehicle["vin"] = vin_match.group(0)
                        
                        if len(parts) >= 5:
                            current_vehicle["plate_state"] = parts[0]
                            current_vehicle["plate_no"] = parts[1]
                            try:
                                current_vehicle["year"] = int(parts[3])
                            except:
                                pass
                            current_vehicle["make"] = parts[4]
                        elif len(parts) == 1:
                            if "UNKNOWN" in parts[0] or "OTHER" in parts[0]:
                                current_vehicle["make"] = parts[0]
            
            # Insurance info
            elif current_vehicle and "INSURANCE" in line and "INSURANCE COMPANY" in line and "INSURANCE POLICY" in line:
                if i + 1 < len(self.pure_lines):
                    parts = re.split(r'\s{3,}', self.pure_lines[i + 1])
                    parts = [p.strip() for p in parts if p.strip()]
                    
                    if len(parts) == 6:
                        current_vehicle_info["insurance_verified"] = "YES" if parts[0] == "X" else "NO"
                        current_vehicle_info["insurance_company"] = parts[2]
                        current_vehicle["policy_no"] = parts[3]
                        current_vehicle["color"] = parts[4]
                        current_vehicle["model"] = parts[5]
                    elif len(parts) == 3:
                        current_vehicle["color"] = parts[1]
                        current_vehicle["model"] = parts[2]
                    elif len(parts) == 2:
                        # Check if second part is a color
                        try:
                            import webcolors
                            webcolors.name_to_hex(parts[1].lower())
                            current_vehicle["color"] = parts[1]
                        except:
                            if "UNKNOWN" in parts[1] or "OTHER" in parts[1]:
                                current_vehicle["make"] = parts[1]
                    elif len(parts) == 1:
                        # Check if it's a color
                        try:
                            import webcolors
                            webcolors.name_to_hex(parts[0].lower())
                            current_vehicle["color"] = parts[0]
                        except:
                            if "UNKNOWN" in parts[0] or "OTHER" in parts[0]:
                                current_vehicle["make"] = parts[0]
                    
                    # Set default insurance values if not found
                    if current_vehicle_info.get("insurance_verified") is None:
                        current_vehicle_info["insurance_company"] = "NA"
                        current_vehicle["policy_no"] = "NA"
            
            # Towed by
            elif current_vehicle and "TOWED BY: COMPANY" in line and "US DOT #" in line:
                if i + 2 < len(self.pure_lines):
                    parts = re.split(r'\s{2,}', self.pure_lines[i + 2])
                    parts = [p.strip() for p in parts if p.strip()]
                    
                    if len(parts) >= 3:
                        current_vehicle_info["us_dot"] = parts[2] if parts[2].isdigit() else "NA"
                    
                    if len(parts) == 4:
                        current_vehicle_info["towed_by"] = parts[3]
                    elif len(parts) == 3:
                        current_vehicle_info["towed_by"] = "NA" if parts[2].isdigit() else parts[2]
                    else:
                        current_vehicle_info["towed_by"] = "NA"
                    
                    if i + 3 < len(self.pure_lines) and self.pure_lines[i + 3].strip().startswith("X"):
                        current_vehicle["is_commercial"] = True
                    
                    current_vehicle["is_towed"] = current_vehicle_info.get("towed_by") != "NA"
            
            # Hit/Skip
            elif current_vehicle and line.strip().startswith("DEVICE") and "HIT/SKIP UNIT" in line:
                if i + 1 < len(self.pure_lines):
                    if re.search(r'\sX\s', self.pure_lines[i + 1]):
                        current_vehicle["is_hit_and_run"] = True
                
                # Occupants
                if i + 3 < len(self.pure_lines):
                    match = re.search(r'\s*\d{1,2}\s*(?=3 -)', self.pure_lines[i + 3])
                    if match:
                        current_vehicle_info["no_of_occupants"] = int(match.group(0).strip())
            
            # Vehicle Type
            elif current_vehicle and "UNIT TYPE" in line and i - 3 >= 0 and "(MINIVAN)" in self.pure_lines[i - 3]:
                vehicletypehelper = self.pure_lines[i - 3].split("(MINIVAN)")
                parts = re.split(r'\s{2,}', vehicletypehelper[0])
                parts = [p.strip() for p in parts if p.strip()]
                if parts:
                    try:
                        current_vehicle["vehicle_type"] = int(parts[0])
                    except:
                        pass
            
            # Number of Trailing Units
            elif current_vehicle and "# OF TRAILING UNITS" in line:
                match = re.search(r'\d', line)
                if match:
                    current_vehicle["no_of_trailer"] = int(match.group(0))
            
            # Special Function
            elif current_vehicle and "SPECIAL" in line and "SHARING" in line:
                if i - 1 >= 0:
                    match = re.search(r'\s*\d{1,2}\s*(?=3 -)', self.pure_lines[i - 1])
                    if match:
                        current_vehicle["special_function"] = match.group(0).strip()
                
                # Vehicle Body Type (5 lines ahead)
                if i + 5 < len(self.pure_lines) and "/ NOT APPLICABLE" in self.pure_lines[i + 5]:
                    match = re.search(r'\s*\d{1,2}\s*(?=\/ NOT APPLICABLE)', self.pure_lines[i + 5])
                    if match:
                        current_vehicle["veh_body_type"] = int(match.group(0).strip())
            
            # Parked status (from PRE-CRASH ACTIONS)
            elif current_vehicle and "PRE-CRASH" in line and i + 2 < len(self.pure_lines) and "ACTIONS" in self.pure_lines[i + 2]:
                if i - 2 >= 0:
                    parkedhelperarry = self.pure_lines[i - 2].split()
                    parts = [p.strip() for p in parkedhelperarry if p.strip()]
                    if len(parts) >= 2:
                        try:
                            value = int(parts[1])
                            current_vehicle["is_parked"] = (value == 10)
                        except:
                            pass
            
            # Contributing Circumstances
            elif current_vehicle and "CONTRIBUTING" in line and i + 1 < len(self.pure_lines) and "CIRCUMSTANCES" in self.pure_lines[i + 1]:
                if i - 2 >= 0:
                    helperarray = re.split(r'\s{2,}|4 - RAN  STOP SIGN', self.pure_lines[i - 2])
                    helperarray = [s.strip() for s in helperarray if s.strip()]
                    if helperarray:
                        try:
                            current_vehicle_info["contributing_circumstance"] = int(helperarray[0])
                        except:
                            pass
            
            # Crash Sequence Events
            elif current_vehicle and "E  V N T S (s)" in line:
                if i + 1 < len(self.pure_lines):
                    match = re.search(r'\d{1,2}\s*(?=1 \- OVERTURN\/ROLLOVER)', self.pure_lines[i + 1])
                    if match:
                        current_vehicle_info["crash_seq_1st_event"] = int(match.group(0).strip())
                
                if i + 6 < len(self.pure_lines):
                    match = re.search(r'\d{1,2}', self.pure_lines[i + 6])
                    if match:
                        current_vehicle_info["crash_seq_2nd_event"] = int(match.group(0).strip())
                
                if i + 12 < len(self.pure_lines):
                    match = re.search(r'(?<=\s3\s)\s*\d{1,2}\s*(?=EQUIPMENT)', self.pure_lines[i + 12])
                    if match:
                        current_vehicle_info["crash_seq_3rd_event"] = int(match.group(0).strip())
                
                if i + 16 < len(self.pure_lines):
                    match = re.search(r'(?<=\s4\s)\s*\d{1,2}\s*', self.pure_lines[i + 16])
                    if match:
                        current_vehicle_info["crash_seq_4th_event"] = int(match.group(0).strip())
            
            # Harmful Events
            elif current_vehicle and "FIRST HARMFUL EVENT" in line and "MOST HARMFUL EVENT" in line:
                match1 = re.search(r'\s*\d{1,2}\s*(?=FIRST HARMFUL EVENT)', line)
                if match1:
                    current_vehicle_info["harmful_event"] = int(match1.group(0).strip())
                
                match2 = re.search(r'(?<=FIRST HARMFUL EVENT)\s*\d{1,2}\s*(?=MOST HARMFUL EVENT)', line)
                if match2:
                    current_vehicle_info["most_harmful_event"] = int(match2.group(0).strip())
                
                # Save vehicle
                vehicles.append(self._build_vehicle_dict(current_vehicle, current_vehicle_info))
                current_vehicle = None
                current_vehicle_info = None
            
            # Damaged Area
            elif current_vehicle and "NO DAMAGE [ 0 ]" in line and i - 1 >= 0 and "DEFECTS" in self.pure_lines[i - 1]:
                if re.search(r'\s*X\s*(?=- NO DAMAGE)', line):
                    current_vehicle_info["damaged_area"] = "0"
                elif re.search(r'(?<=NO DAMAGE \[ 0 \])\s*X\s*(?=\- UNDERCARRIAGE)', line):
                    current_vehicle_info["damaged_area"] = "14"
                elif i + 3 < len(self.pure_lines) and re.search(r'(?<=PATHS)\s*X\s*(?=\- TOP)', self.pure_lines[i + 3]):
                    current_vehicle_info["damaged_area"] = "13"
                elif i + 3 < len(self.pure_lines) and re.search(r'(?<=TOP \[ 13 \])\s*X\s*(?=\- ALL)', self.pure_lines[i + 3]):
                    current_vehicle_info["damaged_area"] = "15"
                elif i + 7 < len(self.pure_lines) and re.search(r'\sX$', self.pure_lines[i + 7]):
                    current_vehicle_info["damaged_area"] = "16"
                else:
                    current_vehicle_info["damaged_area"] = "NA"
            
            # Initial Point of Contact
            elif current_vehicle and "INITIAL POINT OF CONTACT" in line and i + 2 < len(self.pure_lines) and "0 - NO DAMAGE" in self.pure_lines[i + 2]:
                if i + 4 < len(self.pure_lines):
                    match = re.search(r'(?<=PUSHING VEHICLE)\s*\d{1,2}\s*(?=1-12)', self.pure_lines[i + 4])
                    if match:
                        current_vehicle_info["initial_impact"] = match.group(0).strip()
            
            # Vehicle Defects
            elif current_vehicle and "VEHICLE" in line and i + 2 < len(self.pure_lines) and "DEFECTS" in self.pure_lines[i + 2] and i - 2 >= 0 and "1 - TURN SIGNALS" in self.pure_lines[i - 2]:
                match = re.search(r'\d{1,2}\s*(?=1 \- TURN SIGNALS)', self.pure_lines[i - 2])
                if match:
                    current_vehicle_info["vehicle_defects"] = match.group(0).strip()
            
            # Date of Birth signals end of vehicle section
            elif current_vehicle and "DATE OF BIRTH" in line:
                if current_vehicle:
                    vehicles.append(self._build_vehicle_dict(current_vehicle, current_vehicle_info))
                    current_vehicle = None
                    current_vehicle_info = None
                break
        
        # Add last vehicle if exists
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
            "persons": []  # Will be filled later
        }
    
    def _extract_persons(self) -> list:
        """Extract person information from raw_lines - matches C# PersonDetailsGet"""
        persons = []
        current_person = None
        current_person_info = None
        current_driver_info = None
        person_index = 0
        
        for i in range(len(self.raw_lines)):
            line = self.raw_lines[i]
            
            # Start of person section - INJURIES line
            if "INJURIES" in line and ("INJURED" in line or (i + 2 < len(self.raw_lines) and "INJURED" in self.raw_lines[i + 2])):
                # Save previous person if exists
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
            
            # Injuries
            if i + 2 < len(self.raw_lines) and "INJURED" in self.raw_lines[i + 2]:
                current_person_info["injuries"] = self.raw_lines[i + 1]
            else:
                current_person_info["injuries"] = "0"
            
            # Injured Taken By EMS
            if i + 2 < len(self.raw_lines) and "BY" in self.raw_lines[i + 2]:
                match = re.search(r'\d{1,2}', self.raw_lines[i + 2])
                if match:
                    current_person_info["injured_taken_by_ems"] = match.group(0).strip()
            elif i + 4 < len(self.raw_lines) and "BY" in self.raw_lines[i + 4]:
                match = re.search(r'\d{1,2}', self.raw_lines[i + 4])
                if match:
                    current_person_info["injured_taken_by_ems"] = match.group(0).strip()
            
            # EMS Agency Name
            if i + 5 < len(self.raw_lines) and "EMS AGENCY (NAME)" in self.raw_lines[i + 5] and i + 7 < len(self.raw_lines) and "INJURED TAKEN TO: MEDICAL FACILITY" in self.raw_lines[i + 7]:
                current_person_info["name_of_ems"] = self.raw_lines[i + 6].strip()
            elif i + 3 < len(self.raw_lines) and "EMS AGENCY (NAME)" in self.raw_lines[i + 3] and i + 5 < len(self.raw_lines) and "INJURED TAKEN TO: MEDICAL FACILITY" in self.raw_lines[i + 5]:
                current_person_info["name_of_ems"] = self.raw_lines[i + 4].strip()
            elif i + 5 < len(self.raw_lines) and "EMS AGENCY (NAME) INJURED TAKEN TO: MEDICAL FACILITY" in self.raw_lines[i + 5]:
                current_person_info["name_of_ems"] = "NA"
            else:
                current_person_info["name_of_ems"] = "NA"
            
            # Injured Taken To
            if i + 7 < len(self.raw_lines) and "INJURED TAKEN TO: MEDICAL FACILITY" in self.raw_lines[i + 7] and i + 9 < len(self.raw_lines) and "SAFETY EQUIPMENT" in self.raw_lines[i + 9]:
                current_person_info["injured_taken_to"] = self.raw_lines[i + 8].strip()
            elif i + 5 < len(self.raw_lines) and "INJURED TAKEN TO: MEDICAL FACILITY" in self.raw_lines[i + 5] and i + 7 < len(self.raw_lines) and "SAFETY EQUIPMENT" in self.raw_lines[i + 7]:
                current_person_info["injured_taken_to"] = self.raw_lines[i + 6].strip()
            elif i + 3 < len(self.raw_lines) and "INJURED TAKEN TO: MEDICAL FACILITY" in self.raw_lines[i + 3] and i + 5 < len(self.raw_lines) and "SAFETY EQUIPMENT" in self.raw_lines[i + 5]:
                current_person_info["injured_taken_to"] = self.raw_lines[i + 4].strip()
            else:
                current_person_info["injured_taken_to"] = "NA"
        
        # Seating Position
        elif current_person and "SEATING" in line and i + 1 < len(self.raw_lines) and "POSITION" in self.raw_lines[i + 1]:
            if i + 3 < len(self.raw_lines) and "AIR BAG USAGE" in self.raw_lines[i + 3]:
                match = re.search(r'^\d{1,2}', self.raw_lines[i + 2])
                if match:
                    seating_pos = int(match.group(0).strip())
                    current_person_info["seating_position"] = seating_pos
                    current_person["is_same_as_driver"] = (seating_pos == 1)
        
        # Air Bag Usage
        elif current_person and "AIR BAG USAGE" in line:
            if "EJECTION" in line or (i + 1 < len(self.raw_lines) and "EJECTION" in self.raw_lines[i + 1]):
                pass  # Use stored value
            elif i + 1 < len(self.raw_lines):
                try:
                    current_person_info["air_bag_status"] = int(self.raw_lines[i + 1].strip())
                    current_person_info["air_bag_deployed"] = current_person_info["air_bag_status"]
                except:
                    pass
        
        # Ejection
        elif current_person and "EJECTION" in line:
            if "TRAPPED" in line or (i + 1 < len(self.raw_lines) and "TRAPPED" in self.raw_lines[i + 1]):
                pass
            elif i + 1 < len(self.raw_lines):
                match = re.search(r'^\d{1,2}', self.raw_lines[i + 1])
                if match:
                    current_person_info["ejection"] = int(match.group(0).strip())
        
        # Trapped
        elif current_person and "TRAPPED" in line and (i + 1 < len(self.raw_lines) and "ADDRESS: STREET, CITY, STATE, ZIP" in self.raw_lines[i + 1] or i + 2 < len(self.raw_lines) and "ADDRESS: STREET, CITY, STATE, ZIP" in self.raw_lines[i + 2]):
            if i + 2 < len(self.raw_lines) and "ADDRESS" in self.raw_lines[i + 2]:
                try:
                    current_person_info["trapped"] = int(self.raw_lines[i + 1].strip())
                except:
                    pass
        
        # Unit Number and Name
        elif current_person and "UNIT  #" in line and i + 2 < len(self.raw_lines) and "NAME: LAST, FIRST, MIDDLE" in self.raw_lines[i + 2]:
            if i + 1 < len(self.raw_lines):
                try:
                    vehicle_num = int(self.raw_lines[i + 1].strip())
                    current_person["vehicle_number"] = vehicle_num
                    current_person_info["vehicle_unit"] = vehicle_num
                    current_driver_info["vehicle_unit"] = vehicle_num
                except:
                    pass
            
            # Person Name
            if i + 3 < len(self.raw_lines):
                person_name_line = self.raw_lines[i + 3]
                if "CONTACT PHONE" not in person_name_line and not re.search(r'\d{2}/\d{2}/\d{4}', person_name_line):
                    if "UNKNOWN" not in person_name_line:
                        names = person_name_line.split(',')
                        current_person["first_name"] = names[0].strip() if len(names) >= 1 else "NA"
                        current_person["last_name"] = names[1].strip() if len(names) >= 2 else "NA"
                        current_person["middle_name"] = names[2].strip() if len(names) == 3 else "NA"
                    else:
                        current_person["first_name"] = current_person["last_name"] = current_person["middle_name"] = "UNKNOWN"
                else:
                    current_person["first_name"] = current_person["last_name"] = current_person["middle_name"] = "NA"
            
            # Person Address
            if i - 2 >= 0 and "ADDRESS: STREET, CITY, STATE, ZIP" in self.raw_lines[i - 2]:
                person_address = self.raw_lines[i - 1]
                if person_address != "NA" and "UNKNOWN" not in person_address:
                    address_parts = person_address.split(',')
                    current_person["address"] = address_parts[0].strip() if len(address_parts) >= 3 else "NA"
                    current_person["city"] = address_parts[1].strip() if len(address_parts) >= 3 else (address_parts[0].strip() if len(address_parts) == 2 else "NA")
                    current_person["state"] = address_parts[2].strip() if len(address_parts) >= 3 else (address_parts[1].strip() if len(address_parts) == 2 and len(address_parts[1].strip()) == 2 else "NA")
                    current_person["zip"] = address_parts[3].strip() if len(address_parts) == 4 else "NA"
                else:
                    current_person["address"] = current_person["city"] = current_person["state"] = current_person["zip"] = "NA"
            
            # Date of Birth
            if i + 3 < len(self.raw_lines):
                dob_match = re.search(r'\d{1,2}\/\d{1,2}\/\d{4}', self.raw_lines[i + 3])
                if not dob_match and i + 4 < len(self.raw_lines):
                    dob_match = re.search(r'\d{1,2}\/\d{1,2}\/\d{4}', self.raw_lines[i + 4])
                if not dob_match and i + 5 < len(self.raw_lines):
                    dob_match = re.search(r'\d{1,2}\/\d{1,2}\/\d{4}', self.raw_lines[i + 5])
                
                current_person_info["date_of_birth"] = dob_match.group(0) if dob_match else "NA"
            
            # Age
            if i + 4 < len(self.raw_lines):
                if "AGE GENDER" in self.raw_lines[i + 4]:
                    current_person_info["age"] = 0
                elif "AGE" in self.raw_lines[i + 4] and "GENDER" not in self.raw_lines[i + 5] if i + 5 < len(self.raw_lines) else False:
                    try:
                        current_person_info["age"] = int(self.raw_lines[i + 5].strip())
                    except:
                        pass
                elif i + 6 < len(self.raw_lines) and "AGE" in self.raw_lines[i + 6] and "GENDER" not in self.raw_lines[i + 7] if i + 7 < len(self.raw_lines) else False:
                    try:
                        current_person_info["age"] = int(self.raw_lines[i + 7].strip())
                    except:
                        pass
            
            # Gender
            if i + 6 < len(self.raw_lines) and "GENDER" in self.raw_lines[i + 6] and "CONTACT PHONE" not in self.raw_lines[i + 7] if i + 7 < len(self.raw_lines) else False:
                current_person_info["gender"] = self.raw_lines[i + 7].strip() if i + 7 < len(self.raw_lines) else ""
            elif i + 8 < len(self.raw_lines) and "GENDER" in self.raw_lines[i + 8] and "CONTACT PHONE" not in self.raw_lines[i + 9] if i + 9 < len(self.raw_lines) else False:
                current_person_info["gender"] = self.raw_lines[i + 9].strip() if i + 9 < len(self.raw_lines) else ""
            
            # Phone Number
            if i + 10 < len(self.raw_lines) and "CONTACT PHONE" in self.raw_lines[i + 10]:
                if i + 11 < len(self.raw_lines) and "MOTORIST" not in self.raw_lines[i + 11] and "OCCUPANT" not in self.raw_lines[i + 11]:
                    current_person["phone_number"] = self.raw_lines[i + 11]
                    current_driver_info["contact_number"] = self.raw_lines[i + 11]
                else:
                    current_person["phone_number"] = "NA"
                    current_driver_info["contact_number"] = "NA"
        
        # OL State
        elif current_person and "OL STATE" in line and (i + 4 < len(self.raw_lines) and "OPERATOR LICENSE NUMBER" in self.raw_lines[i + 4] or i + 3 < len(self.raw_lines) and "OPERATOR LICENSE NUMBER" in self.raw_lines[i + 3]):
            if i + 1 < len(self.raw_lines) and "OL CLASS" not in self.raw_lines[i + 1]:
                current_driver_info["dl_state"] = self.raw_lines[i + 1].strip()
            else:
                current_driver_info["dl_state"] = "NA"
            
            # OL Class
            if i + 2 < len(self.raw_lines) and "OL CLASS" in self.raw_lines[i + 2] and i + 4 < len(self.raw_lines) and "OPERATOR LICENSE NUMBER" in self.raw_lines[i + 4]:
                current_driver_info["ol_class"] = self.raw_lines[i + 3].strip()
            elif i + 1 < len(self.raw_lines) and "OL CLASS" in self.raw_lines[i + 1] and i + 3 < len(self.raw_lines) and "OPERATOR LICENSE NUMBER" in self.raw_lines[i + 3]:
                current_driver_info["ol_class"] = self.raw_lines[i + 2].strip()
            else:
                current_driver_info["ol_class"] = "NA"
        
        # Restriction
        elif current_person and "RESTRICTION SELECT UP TO 3" in line:
            # Endorsement
            if i - 2 >= 0 and "ENDORSEMENT" in self.raw_lines[i - 2]:
                current_driver_info["endorsement"] = self.raw_lines[i - 1]
            else:
                current_driver_info["endorsement"] = "NA"
            
            # Restriction
            if i + 2 < len(self.raw_lines) and "DRIVER" in self.raw_lines[i + 2]:
                current_driver_info["restriction"] = self.raw_lines[i + 1]
            else:
                current_driver_info["restriction"] = "NA"
            
            # Driver Distracted By
            if i + 2 < len(self.raw_lines) and "BY" in self.raw_lines[i + 2]:
                parts = self.raw_lines[i + 2].strip().split(' ')
                current_driver_info["driver_distracted_by"] = parts[1] if len(parts) == 2 else "NA"
            elif i + 3 < len(self.raw_lines) and "BY" in self.raw_lines[i + 3]:
                parts = self.raw_lines[i + 3].strip().split(' ')
                current_driver_info["driver_distracted_by"] = parts[1] if len(parts) == 2 else "NA"
            elif i + 4 < len(self.raw_lines) and "BY" in self.raw_lines[i + 4]:
                parts = self.raw_lines[i + 4].strip().split(' ')
                current_driver_info["driver_distracted_by"] = parts[1] if len(parts) == 2 else "NA"
            else:
                current_driver_info["driver_distracted_by"] = "NA"
        
        # Operator License Number
        elif current_person and "OPERATOR LICENSE NUMBER" in line:
            if "OFFENSE CHARGED" in line:
                current_driver_info["driving_licence"] = "NA"
            elif i + 1 < len(self.raw_lines):
                current_driver_info["driving_licence"] = self.raw_lines[i + 1].strip()
            
            # Offense Charged
            if "OFFENSE CHARGED" in line and "LOCAL" not in line:
                if i + 1 < len(self.raw_lines):
                    current_driver_info["offense_charged"] = self.raw_lines[i + 1]
            elif i + 2 < len(self.raw_lines) and "OFFENSE CHARGED" in self.raw_lines[i + 2] and i + 4 < len(self.raw_lines) and "LOCAL" in self.raw_lines[i + 4]:
                current_driver_info["offense_charged"] = self.raw_lines[i + 3]
            else:
                current_driver_info["offense_charged"] = "NA"
        
        # Offense Description
        elif current_person and "OFFENSE DESCRIPTION" in line:
            if "CITATION NUMBER" in line:
                current_driver_info["offense_description"] = "NA"
            elif i + 1 < len(self.raw_lines):
                current_driver_info["offense_description"] = self.raw_lines[i + 1]
            
            # Citation Number
            if "CITATION NUMBER" in line and i + 1 < len(self.raw_lines) and "ENDORSEMENT" not in self.raw_lines[i + 1]:
                current_driver_info["citation_number"] = self.raw_lines[i + 1]
            elif i + 2 < len(self.raw_lines) and "CITATION NUMBER" in self.raw_lines[i + 2] and i + 3 < len(self.raw_lines) and "ENDORSEMENT" not in self.raw_lines[i + 3]:
                current_driver_info["citation_number"] = self.raw_lines[i + 3]
            else:
                current_driver_info["citation_number"] = "NA"
        
        # Alcohol/Drug Suspected
        elif current_person and "ALCOHOL / DRUG SUSPECTED" in line:
            if i + 1 < len(self.raw_lines):
                if "X" in self.raw_lines[i + 1] and "ALCOHOL" not in self.raw_lines[i + 1]:
                    current_driver_info["alcohol_drug_suspected"] = "Other Drug"
                elif "X ALCOHOL" in self.raw_lines[i + 1]:
                    current_driver_info["alcohol_drug_suspected"] = "Alcohol"
                elif i + 3 < len(self.raw_lines) and "X MARIJUANA" in self.raw_lines[i + 3]:
                    current_driver_info["alcohol_drug_suspected"] = "Marijuana"
                else:
                    current_driver_info["alcohol_drug_suspected"] = "NA"
        
        # Alcohol/Drug Tests
        elif current_person and "ALCOHOL TEST DRUG TEST(S)" in line:
            # Person Condition
            if i - 2 >= 0 and "CONDITION" in self.raw_lines[i - 2]:
                current_person["person_condition"] = self.raw_lines[i - 1]
            else:
                current_person["person_condition"] = "NA"
            
            # Alcohol Test
            if i + 1 < len(self.raw_lines) and "STATUS TYPE VALUE" in self.raw_lines[i + 1]:
                current_driver_info["alcohol_test_status"] = "NA"
                current_driver_info["alcohol_test_type"] = "NA"
                current_driver_info["alcohol_test_value"] = "NA"
            else:
                if i + 1 < len(self.raw_lines) and "STATUS" in self.raw_lines[i + 1] and i + 3 < len(self.raw_lines) and "TYPE" in self.raw_lines[i + 3]:
                    current_driver_info["alcohol_test_status"] = self.raw_lines[i + 2].strip()
                else:
                    current_driver_info["alcohol_test_status"] = "NA"
                
                if i + 3 < len(self.raw_lines) and "TYPE" in self.raw_lines[i + 3] and i + 5 < len(self.raw_lines) and "VALUE" in self.raw_lines[i + 5]:
                    current_driver_info["alcohol_test_type"] = self.raw_lines[i + 4]
                else:
                    current_driver_info["alcohol_test_type"] = "NA"
                
                if i + 5 < len(self.raw_lines) and "VALUE" in self.raw_lines[i + 5] and i + 7 < len(self.raw_lines) and "STATUS" in self.raw_lines[i + 7]:
                    value = self.raw_lines[i + 6].strip()
                    current_driver_info["alcohol_test_value"] = value if value != "." else "NA"
                else:
                    current_driver_info["alcohol_test_value"] = "NA"
        
        # Drug Test
        elif current_person and "TYPE RESULTS SELECT UP TO 4" in line:
            if "STATUS TYPE RESULTS SELECT UP TO 4" in line:
                current_driver_info["drug_test_status"] = "NA"
                current_driver_info["drug_test_type"] = "NA"
                current_driver_info["drug_test_value"] = "NA"
            else:
                if i - 1 >= 0:
                    arr = self.raw_lines[i - 1].strip().split()
                    arr = [s for s in arr if s.strip()]
                    
                    if len(arr) == 2:
                        current_driver_info["drug_test_status"] = arr[0].strip()
                        current_driver_info["drug_test_type"] = arr[1].strip()
                        current_driver_info["drug_test_value"] = "NA"
                    elif len(arr) == 1:
                        current_driver_info["drug_test_status"] = arr[0].strip()
                        current_driver_info["drug_test_type"] = "NA"
                        current_driver_info["drug_test_value"] = "NA"
                    else:
                        current_driver_info["drug_test_status"] = "NA"
                        current_driver_info["drug_test_type"] = "NA"
                        current_driver_info["drug_test_value"] = "NA"
    
    # Add last person
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
    
    return persons

def _map_persons_to_vehicles(self, vehicles: list, persons: list) -> list:
    """Map persons to their respective vehicles"""
    for person_data in persons:
        person_basic = person_data["basic"]
        person_info = person_data["info"]
        driver_info = person_data["driver"]
        
        vehicle_unit = person_basic.get("vehicle_number", 1)
        
        # Find matching vehicle
        for vehicle in vehicles:
            if vehicle["vehicle_unit"] == vehicle_unit:
                # Build person JSON for this vehicle
                person_json = {
                    "person_type": "",
                    "first_name": person_basic.get("first_name", ""),
                    "middle_name": person_basic.get("middle_name", ""),
                    "last_name": person_basic.get("last_name", ""),
                    "same_as_driver": "1" if person_basic.get("is_same_as_driver", False) else "0",
                    "address_block": {
                        "address_line1": person_basic.get("address", ""),
                        "address_city": person_basic.get("city", ""),
                        "address_state": person_basic.get("state", ""),
                        "address_zip": person_basic.get("zip", "")
                    },
                    "seating_position": str(person_info.get("seating_position", "")),
                    "date_of_birth": person_info.get("date_of_birth", ""),
                    "gender": person_info.get("gender", ""),
                    "alcohol_or_drug_involved": "",
                    "ethnicity": "",
                    "occupant": "",
                    "airbag_deployed": str(person_info.get("air_bag_deployed", "")),
                    "airbag_status": str(person_info.get("air_bag_status", "")),
                    "trapped": str(person_info.get("trapped", "")),
                    "ejection": str(person_info.get("ejection", "")),
                    "injury": str(person_info.get("injuries", "")),
                    "ems_name": person_info.get("name_of_ems", ""),
                    "injured_taken_by_ems": str(person_info.get("injured_taken_by_ems", "")),
                    "age": str(person_info.get("age", "")),
                    "injured_taken_to": person_info.get("injured_taken_to", ""),
                    "driver_info_id": "",
                    "alcohol_test_status": driver_info.get("alcohol_test_status", ""),
                    "alcohol_test_type": driver_info.get("alcohol_test_type", ""),
                    "alcohol_test_value": driver_info.get("alcohol_test_value", ""),
                    "drug_test_status": driver_info.get("drug_test_status", ""),
                    "drug_test_type": driver_info.get("drug_test_type", ""),
                    "drug_test_value": driver_info.get("drug_test_value", ""),
                    "offense_charged": driver_info.get("offense_charged", ""),
                    "local_code": "",
                    "offense_description": driver_info.get("offense_description", ""),
                    "citation_number": driver_info.get("citation_number", ""),
                    "contact_number": driver_info.get("contact_number", ""),
                    "ol_class": driver_info.get("ol_class", ""),
                    "endorsement": driver_info.get("endorsement", ""),
                    "restriction": driver_info.get("restriction", ""),
                    "driver_distracted_by": driver_info.get("driver_distracted_by", ""),
                    "driving_license": driver_info.get("driving_licence", ""),
                    "dl_state": driver_info.get("dl_state", ""),
                    "alcohol_or_drug_suspected": driver_info.get("alcohol_drug_suspected", "")
                }
                
                vehicle["persons"].append(person_json)
                break
    
    return vehicles

def _build_final_json(self, crash_info: dict, case_info: dict, vehicles: list) -> dict:
    """Build final JSON structure matching expected output"""
    # Parse date
    date_of_crash = ""
    if crash_info.get("date_of_crash"):
        try:
            dt = datetime.strptime(crash_info["date_of_crash"].split()[0], "%m/%d/%Y")
            date_of_crash = dt.strftime("%Y-%m-%d")
        except:
            pass
    
    # Build vehicle JSON array
    vehicles_json = []
    for veh in vehicles:
        veh_info = veh.get("vehicle_info", {})
        
        vehicle_json = {
            "vehicle_unit": str(veh.get("vehicle_unit", "1")),
            "is_commercial": "1" if veh.get("is_commercial", False) else "0",
            "make": f" {veh.get('make', '')}",
            "model": veh.get("model", ""),
            "vehicle_year": str(veh.get("year", "")),
            "plate_number": f" {veh.get('plate_no', '')}",
            "plate_state": f" {veh.get('plate_state', '')}",
            "plate_year": "",
            "vin": veh.get("vin", ""),
            "policy": veh.get("policy_no", ""),
            "is_driven": "",
            "is_left_at_scene": "",
            "is_towed": "1" if veh.get("is_towed", False) else "0",
            "is_impounded": "",
            "is_disabled": "",
            "is_parked": "1" if veh.get("is_parked", False) else "0",
            "is_pedestrian": "",
            "is_pedal_cyclist": "",
            "is_hit_and_run": "1" if veh.get("is_hit_and_run", False) else "0",
            "vehicle_used": "",
            "vehicle_type": str(veh.get("vehicle_type", "1")),
            "trailer_or_carrier_count": str(veh.get("no_of_trailer", "0")),
            "color": veh.get("color", ""),
            "vehicle_body_type": str(veh.get("veh_body_type", "")),
            "vehicle_travel_direction": "",
            "vehicle_details": {
                "crash_seq_1st_event": str(veh_info.get("crash_seq_1st_event", "")),
                "crash_seq_2nd_event": str(veh_info.get("crash_seq_2nd_event", "")),
                "crash_seq_3rd_event": str(veh_info.get("crash_seq_3rd_event", "")),
                "crash_seq_4th_event": str(veh_info.get("crash_seq_4th_event", "")),
                "harmful_event": str(veh_info.get("harmful_event", "")),
                "authorized_speed": "",
                "estimated_original_speed": "",
                "estimated_impact_speed": "",
                "tad": "",
                "estimated_damage": "",
                "most_harmful_event": str(veh_info.get("most_harmful_event", "")),
                "insurance_company": veh_info.get("insurance_company", ""),
                "insurance_verified": veh_info.get("insurance_verified", ""),
                "us_dot": veh_info.get("us_dot", ""),
                    "towed_by": veh_info.get("towed_by", ""),
                    "occupant_count": str(veh_info.get("no_of_occupants", "")),
                    "initial_impact": veh_info.get("initial_impact", ""),
                    "contributing_circumstance": str(veh_info.get("contributing_circumstance", "")),
                    "damage_severity": veh_info.get("damage_severity", ""),
                    "damaged_area": veh_info.get("damaged_area", ""),
                    "vehicle_defects": veh_info.get("vehicle_defects", ""),
                    "overweight_permit": ""
                },
                "persons": veh.get("persons", [])
            }
            
            vehicles_json.append(vehicle_json)
        
        return {
            "incident_number": crash_info.get("case_number", ""),
            "report_number": crash_info.get("report_number", ""),
            "department": crash_info.get("department", ""),
            "state_code": "",
            "state_abbreviation": "OH",
            "state_name": "OHIO",
            "county_code": "",
            "county": crash_info.get("county", ""),
            "municipality_code": crash_info.get("municipality_code", ""),
            "municipality": crash_info.get("municipality_code", ""),
            "crash_location": crash_info.get("location", ""),
            "crash_type_l1": "",
            "crash_type_l2": "",
            "date_of_crash": date_of_crash,
            "total_killed": "",
            "total_injured": "",
            "total_vehicles": str(crash_info.get("no_of_vehicles", "")),
            "case_file_s3_path": "",
            "s3_bucket_name": "",
            "s3_access_key": "",
            "s3_secret_key": "",
            "pdf_file_path": str(self.pdf_path),
            "case_detail": [
                {
                    "local_information": "",
                    "locality": case_info.get("locality", "TOWNSHIP"),
                    "location": "NA",
                    "route_type": case_info.get("route_type", "NA"),
                    "route_number": case_info.get("route_number", "NA"),
                    "route_prefix": case_info.get("route_prefix", "NA"),
                    "lane_speed_limit_1": "",
                    "lane_speed_limit_2": "",
                    "crash_severity": str(case_info.get("crash_severity", ""))
                }
            ],
            "vehicles": vehicles_json
        }


def convert_pdf_to_json(pdf_path: Path, crash_number: str = "", document_number: str = "", output_dir: Path = None) -> dict:
    """
    Convert PDF to JSON
    
    Args:
        pdf_path: Path to the PDF file
        crash_number: Crash number (optional, for logging)
        document_number: Document number (optional, for logging)
        output_dir: Output directory for JSON files (default: json_output)
    
    Returns:
        Parsed JSON data or None if parsing failed
    """
    if output_dir is None:
        output_dir = Path("json_output")
    
    output_dir.mkdir(exist_ok=True)
    
    try:
        parser = OhioPdfParser(pdf_path)
        data = parser.parse()
        
        if data:
            json_path = output_dir / f"{pdf_path.stem}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            
            log.info(f"✅ Converted {pdf_path.name} → {json_path.name}")
            return data
        else:
            log.error(f"❌ Failed to parse {pdf_path.name}")
            return None
            
    except Exception as e:
        log.error(f"❌ Error converting {pdf_path.name}: {e}")
        import traceback
        traceback.print_exc()
        return None